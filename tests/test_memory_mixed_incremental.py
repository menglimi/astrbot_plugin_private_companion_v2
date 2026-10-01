"""Bounded source/experience/mixed recall against temporary, synthetic V2 data."""

from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import digest, encode
from companion_v2.memory.models import AtomRef
from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.search import SearchIndex
from companion_v2.memory.sent_sources import ConfirmedReplySources
from companion_v2.memory.writer import MemoryWriter
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION
from tests.execution_support import remove_v26
from tests.memory_support import MemoryFixture


class MixedMemoryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def view(self, identifier, *, evidence=None, title="cobalt", revision=0):
        return self.recall.experiences.save(self.context, view_id=identifier, expected_revision=revision,
            title=title, statements=({"text": title, "evidence": (evidence or self.evidence(identifier),), "atoms": ()},),
            entities=("desk",)).unwrap()

    def finish(self, first, intent="", **options):
        items, pages = list(first["items"]), [first]
        while pages[-1]["next_cursor"]:
            pages.append(self.query(intent, cursor=pages[-1]["next_cursor"], **options).unwrap())
            items.extend(pages[-1]["items"])
        return items, pages

    def rows(self, table):
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM " + table).fetchall()

    def test_all_three_kinds_resume_cold_build_after_restart_without_returning_a_prefix(self):
        for number in range(4):
            evidence = self.evidence("cobalt-" + str(number))
            self.view("v-" + str(number), evidence=evidence)
        for kind in ("sources", "experiences", "all"):
            with self.subTest(kind=kind):
                self.recall.begin(self.context, "query")
                self.recall.recall_index.sync_items = 3
                first = self.query("cobalt", kind=kind).unwrap()
                self.assertEqual(first["items"], [])
                self.assertEqual(first["index_state"], "catching_up")
                self.assertFalse(first["complete"])
                self.recall = MemoryQuery(self.memory)
                self.recall.recall_index.sync_items = 3
                items, pages = self.finish(first, "cobalt", kind=kind)
                self.assertEqual(len(items), 8 if kind == "all" else 4)
                self.assertTrue(pages[-1]["complete"])

    def test_hot_queries_read_only_matching_originals_and_new_object_notices(self):
        for number in range(12):
            self.view("v-" + str(number), title="background")
        self.view("target", evidence=self.evidence("voyager"), title="voyager")
        for kind in ("sources", "experiences", "all"):
            self.query("voyager", kind=kind).unwrap()
        original = self.runtime.read_all
        reads = []
        def checked(sql, args):
            if any(table in sql for table in ("conversation_inputs", "memory_views", "memory_atoms", "memory_recall_changes")):
                reads.append(sql)
            return original(sql, args)
        with patch.object(self.runtime, "read_all", side_effect=checked), \
                patch.object(self.recall, "_documents", side_effect=AssertionError("full documents")), \
                patch.object(self.recall.index, "sync", side_effect=AssertionError("full sync")), \
                patch.object(self.recall.objects, "project", side_effect=AssertionError("unchanged projection")):
            for kind in ("sources", "experiences", "all"):
                with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals:
                    result = self.query("voyager", kind=kind).unwrap()
                self.assertEqual(len(result["items"]), 2 if kind == "all" else 1)
                self.assertEqual(originals.call_count, len(result["items"]))
        self.assertEqual(reads, [])
        self.evidence("new-source")
        with patch.object(self.recall.objects, "project", wraps=self.recall.objects.project) as projected:
            self.query("voyager", kind="all").unwrap()
        self.assertEqual(projected.call_count, 1)

    def test_long_source_resumes_by_span_and_finds_tail_without_truncating_history(self):
        self.evidence("background " * 650 + " voyager")
        self.recall.recall_index.sync_items = 1
        first = self.query("voyager", kind="sources").unwrap()
        self.assertFalse(first["complete"])
        self.assertEqual(len(self.rows("recall_documents")), 1)
        items, pages = self.finish(first, "voyager", kind="sources")
        self.assertGreater(len(pages), 3)
        self.assertTrue(any("voyager" in item["excerpt"] for item in items))
        self.assertGreater(items[0]["start"], 1900)
        self.assertTrue(pages[-1]["complete"])

    def test_old_target_beyond_one_build_batch_is_not_cut_off_by_recent_history(self):
        self.accept(self.event("voyager"))
        batch = None
        for number in range(259):
            batch = self.accept(self.event("background-" + str(number)), batch_id=batch if number % 32 else None)
        first = self.query("voyager", kind="sources").unwrap()
        self.assertEqual(first["index_state"], "catching_up")
        with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals:
            items, pages = self.finish(first, "voyager", kind="sources")
        self.assertEqual(len(items), 1)
        self.assertIn("voyager", items[0]["excerpt"])
        self.assertEqual(originals.call_count, 1)
        self.assertTrue(pages[-1]["complete"])

    def test_chinese_bot_and_role_identifiers_match_the_transactional_feed_key(self):
        self.context = self.alternate_context(bot_id="机器人甲", role_id="角色甲")
        self.grant(self.context.actor, self.context.scope, "text")
        self.evidence("voyager")
        result = self.query("voyager", kind="sources").unwrap()
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("voyager", result["items"][0]["excerpt"])

    def test_source_arriving_during_catchup_and_experience_correction_are_replayed(self):
        evidence = self.evidence("cobalt")
        self.view("v1", evidence=evidence)
        self.view("v2", evidence=evidence)
        self.recall.recall_index.sync_items = 2
        first = self.query("", kind="all").unwrap()
        self.view("v1", evidence=evidence, title="vermilion", revision=1)
        self.evidence("late voyager")
        items, pages = self.finish(first, kind="all")
        self.assertEqual(next(i for i in items if i.get("view_id") == "v1")["revision"], 2)
        self.assertTrue(any("voyager" in i.get("excerpt", "") for i in items))
        self.assertTrue(pages[-1]["complete"])
        experiences, _ = self.finish(self.query("cobalt", kind="experiences").unwrap(), "cobalt", kind="experiences")
        self.assertEqual([value["view_id"] for value in experiences], ["v2"])

    def test_all_query_updates_facts_and_does_not_scan_another_namespace(self):
        original = self.proposed()
        fact = self.remember(original)
        self.remember(replace(original, namespace="other", object="voyager", representation="voyager"), "other")
        self.query("", kind="all").unwrap()
        self.memory.submit(self.context, replace(original, operation="correct", target=fact,
            object="vermilion", representation="vermilion", evidence=(self.evidence("correction"),)), operation_key="correct").unwrap()
        self.assertEqual(self.query("voyager", kind="all").unwrap()["items"], [])
        result = self.query("vermilion", kind="all").unwrap()["items"]
        self.assertEqual([(i["atom_id"], i["revision"]) for i in result], [(fact.atom_id, 2)])

    def test_source_revocations_between_pages_have_bounded_reads_and_reach_later_matches(self):
        for number in range(3):
            self.evidence("cobalt-" + str(number))
        self.query("", kind="sources").unwrap()
        entries = sorted(self.rows("recall_documents"), key=lambda row: row["id"])
        for row in entries[:2]:
            source = self.recall.objects.source(self.context, "human", row["object_id"])[0]
            self.memory.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.recall.recall_index.candidate_items = 2
        with patch.object(self.recall.objects, "read", wraps=self.recall.objects.read) as originals:
            first = self.query("", kind="sources").unwrap()
        self.assertEqual(originals.call_count, 2)
        self.assertEqual(first["items"], [])
        self.assertTrue(first["scan_limited"])
        last = self.query("", kind="sources", cursor=first["next_cursor"]).unwrap()
        self.assertEqual(len(last["items"]), 1)
        self.assertTrue(last["unavailable_sources"])
        self.assertFalse(last["complete"])

    def test_revoked_source_before_first_build_retains_coverage_gap_after_restart(self):
        evidence = self.evidence("private cobalt")
        self.memory.sources.revoke(evidence.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.evidence("available voyager")
        self.recall.recall_index.sync_items = 1
        first = self.query("voyager", kind="sources").unwrap()
        self.assertTrue(first["unavailable_sources"])
        self.recall = MemoryQuery(self.memory)
        items, pages = self.finish(first, "voyager", kind="sources")
        self.assertEqual(len(items), 1)
        self.assertTrue(pages[-1]["unavailable_sources"])
        self.assertFalse(pages[-1]["complete"])
        self.assertFalse(any("cobalt" in r["document_json"] for r in self.rows("recall_documents")))

    def test_withdrawal_removes_terms_and_stales_existing_result_cursor(self):
        for number in range(3):
            self.evidence("cobalt-" + str(number))
        first = self.query("cobalt", kind="sources", limit=1).unwrap()
        evidence = self.recall.resolve(self.context, "query", first["items"][0]["handle"])
        row = self.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE json_extract(event_json, '$.source.source_id') = ?",
                                    (evidence.source.source_id,))
        with self.runtime.transaction() as db:
            db.execute("UPDATE conversation_inputs SET withdrawn = 1 WHERE event_key = ?", (row[0],))
        self.assertEqual(self.query("cobalt", kind="sources", cursor=first["next_cursor"]).failure.code, "memory_cursor_stale")
        self.assertEqual(len(self.query("cobalt", kind="sources").unwrap()["items"]), 2)
        self.assertEqual(len(self.rows("recall_documents")), 2)

    def test_authority_is_checked_after_warming_and_other_relationships_remain_isolated(self):
        self.evidence("voyager")
        self.query("voyager", kind="sources").unwrap()
        for name, other in self.other_memory_owners().items():
            self.recall.begin(other, name)
            self.assertEqual(self.recall.query(other, name, query_intent="voyager", kind="all").unwrap()["items"], [])
        from companion_v2.execution.models import TaskError
        def denied(context, ref, **options):
            raise TaskError("source_audience_denied", "synthetic current grant change")
        with patch.object(self.memory.access, "source", side_effect=denied):
            hidden = self.query("voyager", kind="sources").unwrap()
        self.assertEqual(hidden["items"], [])
        self.assertFalse(hidden["complete"])
        self.assertEqual(len(self.query("voyager", kind="sources").unwrap()["items"]), 1)

    def test_cached_experience_filters_cannot_override_original_entities(self):
        self.view("v")
        self.query("cobalt", kind="experiences").unwrap()
        with closing(sqlite3.connect(self.recall.index.path)) as db, db:
            db.execute("UPDATE recall_documents SET metadata_json = json_set(metadata_json, '$.entities', json('[\"invented\"]'))")
        result = self.query("cobalt", kind="experiences", subjects=("invented",)).unwrap()
        self.assertEqual(result["items"], [])
        self.assertFalse(result["complete"])

    def test_outer_rollback_and_same_reused_tail_do_not_hide_different_committed_sources(self):
        self.query("", kind="sources").unwrap()
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.runtime.transaction():
                self.evidence("phantom")
                self.evidence("same tail")
                self.assertEqual(len(self.query("", kind="sources").unwrap()["items"]), 2)
                raise RuntimeError("abort")
        self.evidence("real")
        self.evidence("same tail")
        result = self.query("", kind="sources").unwrap()
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(any("real" in i["excerpt"] for i in result["items"]))
        self.assertFalse(any("phantom" in i["excerpt"] for i in result["items"]))

    def test_failed_batch_rolls_back_terms_and_checkpoint_without_charging_session(self):
        self.evidence("first")
        self.evidence("second")
        original = self.recall.recall_index._put
        calls = []
        def fail(*args):
            calls.append(1)
            if len(calls) == 2:
                raise sqlite3.DatabaseError("synthetic")
            return original(*args)
        with patch.object(self.recall.recall_index, "_put", side_effect=fail):
            self.assertEqual(self.query("", kind="sources").failure.code, "memory_index_unavailable")
        self.assertEqual(self.rows("recall_documents"), [])
        self.assertEqual(self.rows("recall_sync"), [])
        self.assertEqual(len(self.query("", kind="sources").unwrap()["items"]), 2)

    def test_warm_mixed_query_is_read_only_on_cache_and_cold_lock_is_retryable(self):
        self.view("v")
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(self.query("cobalt", kind="all").failure.code, "memory_index_busy")
        expected = self.query("cobalt", kind="all").unwrap()["items"]
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            self.recall = MemoryQuery(self.memory)
            self.assertEqual(self.query("cobalt", kind="all").unwrap()["items"], expected)

    def test_forget_erases_new_projection_and_does_not_rehydrate_source_or_view_terms(self):
        proposal = self.proposed()
        reference = self.remember(proposal)
        self.view("v", evidence=proposal.evidence[0], title="private cobalt")
        self.query("", kind="all").unwrap()
        for row in self.rows("recall_documents"):
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(1., 0.), expected_hash=row["hash"])
        self.query("", kind="all", vector=(1., 0.), model="test@1").unwrap()
        self.assertTrue(self.rows("recall_vector_jobs"))
        self.memory.forget(self.context, reference, evidence=(self.evidence("forget"),), operation_key="forget").unwrap()
        for table in ("recall_documents", "recall_vectors", "recall_vector_jobs", "recall_vector_scores"):
            self.assertEqual(self.rows(table), [])
        self.assertEqual(self.query("cobalt", kind="all").unwrap()["items"], [])
        self.assertFalse(any("cobalt" in row["document_json"] or "咖啡" in row["document_json"] for row in self.rows("recall_documents")))

    async def test_confirmed_reply_is_materialized_only_on_hit_and_has_bot_attribution(self):
        batch = await self.generate()
        await self.deliver_next(batch)
        self.memory.access.sent_sources = ConfirmedReplySources(type("Memory", (), {"writer": self.memory})(), self.messages)
        with patch.object(self.memory.access.sent_sources, "materialize", wraps=self.memory.access.sent_sources.materialize) as materialize:
            self.query("unrelated", kind="sources").unwrap()
            self.assertEqual(materialize.call_count, 0)
            result = self.query("First", kind="sources").unwrap()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["source_kind"], "bot_message")
        self.assertEqual(result["items"][0]["speaker_id"], self.context.role_binding.role.subject_id)
        self.recall = MemoryQuery(self.memory)
        self.assertEqual(self.query("First", kind="sources").unwrap()["items"], result["items"])

    def test_v1_search_cache_upgrade_preserves_existing_vectors_and_builds_new_recall(self):
        document = {"id": "legacy", "kind": "source", "revision": 1, "text": "legacy"}
        self.recall.index.sync("legacy-owner", [document])
        self.recall.index.put_vector("legacy-owner", "legacy", model="test@1", values=(1., 0.), expected_hash=digest(document))
        with closing(sqlite3.connect(self.recall.index.path)) as db, db:
            for table in ("recall_lexical", "recall_documents", "recall_vectors", "recall_sync", "recall_epoch",
                          "recall_vector_jobs", "recall_vector_scores"):
                db.execute("DROP TABLE " + table)
            db.execute("PRAGMA user_version = 1")
        self.recall = MemoryQuery(self.memory)
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SearchIndex.FORMAT)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 1)
        self.evidence("voyager")
        self.assertEqual(len(self.query("voyager", kind="sources").unwrap()["items"]), 1)

    def test_vector_scan_resumes_and_includes_the_last_candidate_in_exact_ranking(self):
        for number in range(4):
            self.evidence("background-" + str(number))
        self.query("", kind="sources").unwrap()
        documents = sorted(self.rows("recall_documents"), key=lambda row: row["id"])
        for row in documents:
            vector = (1., 0.) if row["id"] == documents[-1]["id"] else (0., 1.)
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=vector, expected_hash=row["hash"])
        self.recall.recall_index.vector_items = 1
        options = {"kind": "sources", "vector": (1., 0.), "model": "test@1", "limit": 1}
        first = self.query("no-lexical-match", **options).unwrap()
        self.assertEqual(first["items"], [])
        self.assertEqual(first["index_state"], "ranking")
        self.assertFalse(first["vector_coverage"]["complete"])
        self.recall = MemoryQuery(self.memory)
        self.recall.recall_index.vector_items = 1
        items, pages = self.finish(first, "no-lexical-match", **options)
        target = self.recall.objects.source(self.context, "human", documents[-1]["object_id"])[1]
        self.assertEqual(items[0]["excerpt"], target)
        self.assertEqual(pages[-1]["vector_coverage"]["embedded"], 4)
        self.assertEqual(pages[-1]["vector_coverage"]["eligible"], 4)
        self.assertEqual(len(items), 4)

    def test_vector_update_invalidates_results_and_lexical_fusion_works(self):
        self.evidence("cobalt")
        self.evidence("cobalt voyager")
        self.query("", kind="sources").unwrap()
        docs = self.rows("recall_documents")
        for row in docs:
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(1., 0.), expected_hash=row["hash"])
        options = {"kind": "sources", "vector": (1., 0.), "model": "test@1", "limit": 1}
        first = self.query("cobalt", **options).unwrap()
        self.assertEqual(len(first["items"]), 1)
        self.assertIsNotNone(first["next_cursor"])
        row = docs[0]
        self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(0., 1.), expected_hash=row["hash"])
        self.assertEqual(self.query("cobalt", cursor=first["next_cursor"], **options).failure.code, "memory_cursor_stale")

    def test_vector_progress_survives_exhausted_turn_budgets_and_advancing_clock(self):
        for number in range(4):
            self.evidence("voyager-" + str(number))
        self.query("", kind="sources").unwrap()
        for row in self.rows("recall_documents"):
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(1., 0.), expected_hash=row["hash"])
        self.memory.access.policy = replace(self.memory.policy, turn_calls=1)
        for turn in range(4):
            self.recall = MemoryQuery(self.memory)
            self.recall.recall_index.vector_items = 1
            self.clock.advance(timedelta(seconds=1))
            session = "vector-turn-" + str(turn)
            self.recall.begin(self.context, session)
            options = {"query_intent": "voyager", "kind": "sources", "vector": (1., 0.), "model": "test@1"}
            result = self.recall.query(self.context, session, **options).unwrap()
            self.assertEqual(self.recall.query(self.context, session, **options).failure.code, "memory_query_budget_exhausted")
        self.assertEqual(len(result["items"]), 4)
        self.assertTrue(result["complete"])
        self.assertEqual(len(self.rows("recall_vector_jobs")), 1)

    def test_reused_vector_scores_reapply_time_filters_for_each_new_query(self):
        base = self.proposed()
        expiring = self.remember(replace(base, predicate="expiring", valid_to=self.clock.now() + timedelta(seconds=1)), "first")
        lasting = self.remember(replace(base, predicate="lasting"), "second")
        self.recall.recall_index.advance(self.context, "personal", "facts")
        for row in self.rows("recall_documents"):
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(1., 0.), expected_hash=row["hash"])
        options = {"kind": "facts", "vector": (1., 0.), "model": "test@1"}
        first = self.query("", **options).unwrap()
        self.assertEqual({v["atom_id"] for v in first["items"]}, {expiring.atom_id, lasting.atom_id})
        self.clock.advance(timedelta(seconds=2))
        last = self.query("", **options).unwrap()
        self.assertEqual([v["atom_id"] for v in last["items"]], [lasting.atom_id])
        self.assertEqual(last["vector_coverage"]["embedded"], 1)
        self.assertEqual(last["vector_coverage"]["eligible"], 1)
        self.assertEqual(len(self.rows("recall_vector_jobs")), 1)

    def test_empty_query_hybrid_ranks_all_candidates_without_lexical_rank_bias(self):
        for number in range(3):
            self.evidence("background-" + str(number))
        self.query("", kind="sources").unwrap()
        docs = sorted(self.rows("recall_documents"), key=lambda row: row["id"])
        row = docs[-1]
        self.recall.index.put_vector(row["owner"], row["id"], model="test@1", values=(1., 0.), expected_hash=row["hash"])
        result = self.query("", kind="sources", vector=(1., 0.), model="test@1").unwrap()
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0]["excerpt"], json.loads(row["document_json"])["text"])

    def test_hybrid_recall_uses_mmr_after_authority_and_keeps_cursor_order(self):
        self.evidence("near-a")
        self.evidence("near-b")
        self.evidence("diverse")
        self.query("", kind="sources").unwrap()
        documents = self.rows("recall_documents")
        for row in documents:
            text = json.loads(row["document_json"])["text"]
            vector = (1., 0.) if "near-" in text else (0., 1.)
            self.recall.index.put_vector(row["owner"], row["id"], model="test@1",
                                         values=vector, expected_hash=row["hash"])
        options = {"kind": "sources", "vector": (1., 0.), "model": "test@1",
                   "limit": 1, "candidate_limit": 3}
        first = self.query("", **options).unwrap()
        items, pages = self.finish(first, "", **options)
        excerpts = [item["excerpt"] for item in items]
        self.assertEqual(len(items), 3)
        self.assertIn("near-", excerpts[0])
        self.assertIn("diverse", excerpts[1])
        self.assertIn("near-", excerpts[2])
        self.assertGreater(len(pages), 1)

        revoked = next(row for row in documents
                       if json.loads(row["document_json"])["text"] == excerpts[0])
        reference = self.recall.objects.source(self.context, "human", revoked["object_id"])[0]
        self.memory.sources.revoke(reference, expected_governance_revision=1,
                                   observed_at=self.clock.now()).unwrap()
        result = self.query("", kind="sources", vector=(1., 0.), model="test@1",
                            limit=3, candidate_limit=3).unwrap()
        self.assertEqual(len(result["items"]), 2)
        self.assertFalse(any(item["excerpt"] == excerpts[0] for item in result["items"]))
        self.assertTrue(result["unavailable_sources"])

    def test_cache_rebuild_and_other_partition_ranking_changes_stale_cursors(self):
        self.view("v1")
        self.view("v2")
        first = self.query("cobalt", kind="experiences", limit=1).unwrap()
        self.query("", kind="sources").unwrap()
        self.assertEqual(self.query("cobalt", kind="experiences", cursor=first["next_cursor"]).failure.code, "memory_cursor_stale")
        first = self.query("cobalt", kind="experiences", limit=1).unwrap()
        self.recall.index.clear()
        self.assertEqual(self.query("cobalt", kind="experiences", cursor=first["next_cursor"]).failure.code, "memory_cursor_stale")

    def test_expiring_fact_on_mixed_pages_does_not_shift_later_candidate_positions(self):
        proposal = replace(self.proposed(), single_value=False)
        facts = [self.remember(replace(proposal, predicate=str(n)), str(n)) for n in range(3)]
        first_ref = sorted(facts, key=lambda value: value.atom_id)[0]
        self.memory.submit(self.context, replace(proposal, predicate=str(facts.index(first_ref)), operation="correct", target=first_ref,
            valid_to=self.clock.now() + timedelta(seconds=1), evidence=(self.evidence("expiry"),)), operation_key="expire").unwrap()
        first = self.query("", kind="all", subjects=("self",), limit=1).unwrap()
        self.assertEqual(first["items"][0]["atom_id"], first_ref.atom_id)
        self.clock.advance(timedelta(seconds=2))
        last = self.query("", kind="all", subjects=("self",), cursor=first["next_cursor"]).unwrap()
        self.assertEqual({v["atom_id"] for v in last["items"]}, {v.atom_id for v in facts if v != first_ref})

    def test_experience_listing_bounds_revoked_reads_and_exposes_continuation(self):
        for number in range(3):
            self.view("v" + str(number))
        for number in range(2):
            value = self.recall.experiences.read(self.context, "v" + str(number)).unwrap()
            from companion_v2.memory import codec
            reference = codec.source(value["source"])
            self.memory.sources.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.recall.experiences.candidate_items = 2
        first = self.recall.experiences.list(self.context, entity="desk").unwrap()
        self.assertEqual(first["items"], [])
        self.assertEqual(first["candidates_examined"], 2)
        self.assertTrue(first["scan_limited"])
        last = self.recall.experiences.list(self.context, entity="desk", after_id=first["next_cursor"]).unwrap()
        self.assertEqual([v["view_id"] for v in last["items"]], ["v2"])

    def test_index_pages_keep_turn_budget_and_can_resume_from_another_session(self):
        for number in range(3):
            self.evidence(str(number))
        self.memory.access.policy = replace(self.memory.policy, turn_calls=2)
        self.recall.recall_index.sync_items = 1
        first = self.query("", kind="sources").unwrap()
        second = self.query("", kind="sources", cursor=first["next_cursor"]).unwrap()
        self.assertEqual(self.query("", kind="sources", cursor=second["next_cursor"]).failure.code, "memory_query_budget_exhausted")
        self.recall.begin(self.context, "later")
        result = self.recall.query(self.context, "later", query_intent="", kind="sources").unwrap()
        self.assertEqual(len(result["items"]), 3)


class RecallMigrationTests(MemoryFixture, unittest.TestCase):
    def historical(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            remove_v26(db)
            db.execute("UPDATE runtime_metadata SET value = 'companion-v2.storage.v25' WHERE key = 'schema_version'")
        return database, root, installation

    def test_v25_upgrade_backfills_only_pointers_and_existing_objects_remain_searchable(self):
        self.remember()
        database, root, installation = self.historical()
        runtime = StorageRuntime.open(data_root=root, installation_id=installation)
        self.addCleanup(runtime.close)
        rows = runtime.read_all("SELECT * FROM memory_recall_changes ORDER BY sequence", ())
        self.assertEqual({r["kind"] for r in rows}, {"human", "fact"})
        self.assertEqual(set(rows[0].keys()), {"sequence", "owner", "kind", "object_id", "token"})
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())[0], SCHEMA_VERSION)
        query = MemoryQuery(MemoryWriter(self.supervisor(runtime)))
        query.begin(self.context, "migrated")
        result = query.query(self.context, "migrated", query_intent="咖啡", kind="all").unwrap()
        self.assertEqual({item["kind"] for item in result["items"]}, {"source", "fact"})
        self.assertTrue(result["complete"])

    def test_failed_v26_backfill_rolls_back_notices_triggers_and_receipt_then_retries(self):
        self.remember()
        database, root, installation = self.historical()
        original = StorageRuntime._migrate_v25_to_v26
        def fail(runtime, connection):
            original(runtime, connection)
            raise StorageOpenError("synthetic failure after recall backfill")
        with patch.object(StorageRuntime, "_migrate_v25_to_v26", fail):
            with self.assertRaisesRegex(StorageOpenError, "synthetic failure"):
                StorageRuntime.open(data_root=root, installation_id=installation)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], "companion-v2.storage.v25")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_atoms").fetchone()[0], 1)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('memory_recall_changes', 'recall_human_insert', 'memory_guard_evidence_idx')").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v25-to-v26'").fetchone())
        runtime = StorageRuntime.open(data_root=root, installation_id=installation)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.read_one("SELECT COUNT(*) FROM memory_recall_changes", ())[0], 2)

    def test_tampered_change_trigger_is_rejected_on_reopen(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TRIGGER recall_human_update")
            db.execute("CREATE TRIGGER recall_human_update AFTER UPDATE ON conversation_inputs BEGIN SELECT 1; END")
        with self.assertRaisesRegex(StorageOpenError, "change tracking"):
            StorageRuntime.open(data_root=root, installation_id=installation)

    def test_tampered_v26_receipt_is_rejected_on_reopen(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE migration_id = 'companion-v2.storage.v25-to-v26'")
        with self.assertRaisesRegex(StorageOpenError, "untrusted v26 migration record"):
            StorageRuntime.open(data_root=root, installation_id=installation)

    def test_missing_change_trigger_is_rejected_on_reopen(self):
        database, root, installation = self.runtime.database_path, self.runtime.data_root, self.runtime.installation_id
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TRIGGER recall_human_update")
        with self.assertRaisesRegex(StorageOpenError, "change tracking"):
            StorageRuntime.open(data_root=root, installation_id=installation)
