from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import encode
from companion_v2.memory.models import AtomRef
from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.writer import MemoryWriter
from tests.memory_support import MemoryFixture


class IncrementalMemoryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def populate(self, count, *, separate_sources=False):
        base = replace(self.proposed(), single_value=False, object="cobalt", representation="cobalt")
        entries = []
        for number in range(count):
            item = replace(base, predicate="item-" + str(number))
            if separate_sources:
                item = replace(item, evidence=(self.evidence("proof-" + str(number)),))
            entries.append((self.remember(item, key="item-" + str(number)), item))
        return sorted(entries, key=lambda item: item[0].atom_id)

    def finish(self, result, intent="", **kwargs):
        items = list(result["items"])
        while result["next_cursor"]:
            result = self.query(intent, cursor=result["next_cursor"], **kwargs).unwrap()
            items.extend(result["items"])
        return items, result

    def test_cold_index_is_resumable_after_restart_and_does_not_return_a_prefix_as_complete(self):
        entries = self.populate(5)
        self.recall.fact_index.sync_items = 2
        first = self.query("").unwrap()
        self.assertEqual(first["items"], [])
        self.assertEqual(first["index_state"], "catching_up")
        self.assertFalse(first["complete"])
        self.assertIsNotNone(first["next_cursor"])
        restarted_tasks, _, _ = self.components(self.open_runtime())
        self.recall = MemoryQuery(MemoryWriter(restarted_tasks))
        self.recall.fact_index.sync_items = 2
        items, last = self.finish(first)
        self.assertEqual([item["atom_id"] for item in items], [ref.atom_id for ref, _ in entries])
        self.assertTrue(last["complete"])
        self.assertEqual(last["index_state"], "ready")

    def test_warm_recall_materializes_only_matches_and_new_changes(self):
        self.populate(12)
        target = self.remember(replace(self.proposed(), predicate="destination", object="voyager",
                                      representation="voyager"), key="target")
        self.query("voyager").unwrap()
        self.remember(replace(self.proposed(), predicate="unrelated", object="nebula",
                              representation="nebula"), key="later")
        fetched = []
        original = self.runtime.read_all

        def read_all(statement, parameters):
            rows = original(statement, parameters)
            if "memory_atoms" in statement or "memory_changes" in statement:
                fetched.append((statement, len(rows)))
            return rows

        with patch.object(self.memory, "read", wraps=self.memory.read) as reads, \
                patch.object(self.runtime, "read_all", side_effect=read_all), \
                patch.object(self.recall.index, "sync", side_effect=AssertionError("full sync")):
            result = self.query("voyager").unwrap()
        self.assertEqual([item["atom_id"] for item in result["items"]], [target.atom_id])
        self.assertEqual(reads.call_count, 1)
        self.assertFalse(any("memory_atoms" in sql for sql, _ in fetched))
        self.assertEqual(sum(count for _, count in fetched), 1)
        fetched.clear()
        with patch.object(self.runtime, "read_all", side_effect=read_all):
            self.assertEqual(self.query("voyager").unwrap()["items"][0]["atom_id"], target.atom_id)
        self.assertEqual(fetched, [])

    def test_changes_during_bootstrap_are_replayed_before_results_are_returned(self):
        entries = self.populate(5)
        self.recall.fact_index.sync_items = 2
        first = self.query("").unwrap()
        ref, original = entries[0]
        self.memory.submit(self.context, replace(original, operation="correct", target=ref,
            object="updated", representation="updated", evidence=(self.evidence("new evidence"),)),
            operation_key="during-build").unwrap()
        added = self.remember(replace(original, predicate="late", object="late", representation="late"), key="late")
        items, last = self.finish(first)
        self.assertEqual({item["atom_id"] for item in items}, {r.atom_id for r, _ in entries} | {added.atom_id})
        updated = next(item for item in items if item["atom_id"] == ref.atom_id)
        self.assertEqual((updated["revision"], updated["object"]), (2, "updated"))
        self.assertTrue(last["complete"])

    def test_delta_correction_and_retraction_replace_terms(self):
        ref, original = self.populate(1)[0]
        self.query("cobalt").unwrap()
        corrected = replace(original, operation="correct", target=ref, object="vermilion",
                            representation="vermilion", evidence=(self.evidence("correction"),))
        self.memory.submit(self.context, corrected, operation_key="correct").unwrap()
        self.assertEqual(self.query("cobalt").unwrap()["items"], [])
        item = self.query("vermilion").unwrap()["items"][0]
        self.assertEqual(item["revision"], 2)
        self.memory.submit(self.context, replace(corrected, operation="retract", target=AtomRef(ref.atom_id, 2)),
                           operation_key="retract").unwrap()
        self.assertEqual(self.query("vermilion").unwrap()["items"], [])

    def test_filtered_and_session_facts_do_not_consume_the_candidate_page(self):
        self.populate(4)
        valid = self.remember(replace(self.proposed(), predicate="temporary", retention="session"), key="session")
        self.recall.fact_index.candidate_items = 1
        result = self.query("", allowed_retention=("session",), confidence_floor=0.9, subjects=("self",)).unwrap()
        self.assertEqual([item["atom_id"] for item in result["items"]], [valid.atom_id])
        self.assertTrue(result["complete"])
        later = self.context_for(self.important, replace(self.context.scope, session_id="later"))
        self.recall.begin(later, "later")
        hidden = self.recall.query(later, "later", query_intent="咖啡").unwrap()
        self.assertEqual(hidden["items"], [])
        self.assertTrue(hidden["complete"])
        self.assertEqual(self.query("咖啡").unwrap()["items"][0]["atom_id"], valid.atom_id)

    def test_revoked_matches_have_bounded_reads_and_a_continuation_to_later_valid_facts(self):
        entries = self.populate(3, separate_sources=True)
        self.query("").unwrap()
        revision = self.recall.memory_revision(self.context)
        for _, item in entries[:2]:
            self.memory.sources.revoke(item.evidence[0].source, expected_governance_revision=1,
                                       observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.recall.memory_revision(self.context), revision)
        self.recall.fact_index.candidate_items = 2
        with patch.object(self.memory, "read", wraps=self.memory.read) as reads:
            first = self.query("").unwrap()
        self.assertEqual(reads.call_count, 2)
        self.assertEqual(first["items"], [])
        self.assertTrue(first["scan_limited"])
        self.assertTrue(first["unavailable_sources"])
        last = self.query("", cursor=first["next_cursor"]).unwrap()
        self.assertEqual([item["atom_id"] for item in last["items"]], [entries[-1][0].atom_id])
        self.assertIsNone(last["next_cursor"])
        self.assertFalse(last["complete"])
        self.assertTrue(last["unavailable_sources"])

    def test_expiry_between_pages_does_not_shift_the_candidate_offset(self):
        entries = self.populate(3)
        ref, original = entries[0]
        self.memory.submit(self.context, replace(original, operation="correct", target=ref,
            valid_to=self.clock.now() + timedelta(seconds=1), evidence=(self.evidence("timed correction"),)),
            operation_key="expire-first").unwrap()
        first = self.query("", limit=1).unwrap()
        self.assertEqual(first["items"][0]["atom_id"], ref.atom_id)
        self.clock.advance(timedelta(seconds=2))
        last = self.query("", cursor=first["next_cursor"]).unwrap()
        self.assertEqual([item["atom_id"] for item in last["items"]], [r.atom_id for r, _ in entries[1:]])

    def test_other_partition_edits_invalidate_bm25_result_cursors(self):
        self.populate(3)
        first = self.query("cobalt", limit=1).unwrap()
        self.remember(replace(self.proposed(), namespace="another"), key="namespace")
        self.query("咖啡", namespace="another").unwrap()
        result = self.query("cobalt", limit=1, cursor=first["next_cursor"])
        self.assertEqual(result.failure.code, "memory_cursor_stale")

    def test_cache_rebuild_invalidates_result_cursors(self):
        self.populate(3)
        first = self.query("", limit=1).unwrap()
        self.recall.index.clear()
        self.assertEqual(self.query("", cursor=first["next_cursor"]).failure.code, "memory_cursor_stale")
        self.assertEqual(len(self.query("").unwrap()["items"]), 3)

    def test_cached_metadata_cannot_override_authoritative_subject_filters(self):
        self.remember()
        self.query().unwrap()
        with closing(sqlite3.connect(self.recall.index.path)) as db, db:
            db.execute("UPDATE fact_documents SET metadata_json = json_set(metadata_json, '$.subject', 'entity:someone-else')")
        result = self.query("咖啡", subjects=("entity:someone-else",)).unwrap()
        self.assertEqual(result["items"], [])
        self.assertFalse(result["complete"])

    def test_outer_rollback_and_reused_identical_tail_cannot_hide_new_committed_facts(self):
        base = replace(self.proposed(), single_value=False)
        self.query("").unwrap()
        anchor_item = replace(base, predicate="anchor")
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.runtime.transaction():
                phantom = self.remember(replace(base, predicate="phantom"), key="phantom")
                anchor = self.remember(anchor_item, key="anchor")
                self.assertEqual(len(self.query("").unwrap()["items"]), 2)
                raise RuntimeError("abort")
        real = self.remember(replace(base, predicate="real"), key="real")
        # Same seq=2, atom id, revision and semantic body as the rolled-back tail.
        self.assertEqual(self.remember(anchor_item, key="anchor"), anchor)
        items = self.query("").unwrap()["items"]
        self.assertEqual({item["atom_id"] for item in items}, {real.atom_id, anchor.atom_id})
        self.assertNotIn(phantom.atom_id, {item["atom_id"] for item in items})

    def test_failed_projection_batch_does_not_advance_checkpoint_or_keep_half_the_terms(self):
        self.populate(2)
        original = self.recall.fact_index._put
        calls = []

        def fail_second(*args):
            calls.append(True)
            if len(calls) == 2:
                raise sqlite3.DatabaseError("synthetic index failure")
            return original(*args)

        with patch.object(self.recall.fact_index, "_put", side_effect=fail_second):
            self.assertEqual(self.query("").failure.code, "memory_index_unavailable")
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fact_documents").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fact_sync").fetchone()[0], 0)
        self.assertEqual(len(self.query("").unwrap()["items"]), 2)

    def test_forgetting_erases_the_new_projection_and_old_terms_do_not_return(self):
        ref = self.remember()
        self.query().unwrap()
        self.memory.forget(self.context, ref, evidence=(self.evidence("forget"),), operation_key="forget").unwrap()
        with closing(sqlite3.connect(self.recall.index.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fact_documents").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fact_sync").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fact_lexical").fetchone()[0], 0)
        self.recall = MemoryQuery(self.memory)
        self.assertEqual(self.query().unwrap()["items"], [])

    def test_existing_v2_records_without_write_stamps_are_readable(self):
        ref = self.remember()
        row = self.runtime.read_one("SELECT record_json FROM memory_atoms WHERE atom_id = ?", (ref.atom_id,))
        legacy = json.loads(row["record_json"])
        legacy.pop("change_token")
        with self.runtime.transaction() as db:
            db.execute("UPDATE memory_atoms SET record_json = ? WHERE atom_id = ?", (encode(legacy), ref.atom_id))
            db.execute("UPDATE memory_revisions SET record_json = ? WHERE atom_id = ?", (encode(legacy), ref.atom_id))
        self.assertEqual(self.query().unwrap()["items"][0]["atom_id"], ref.atom_id)

    def test_index_continuations_consume_turn_budget_and_later_sessions_resume_work(self):
        self.populate(3)
        self.memory.access.policy = replace(self.memory.policy, turn_calls=2)
        self.recall.fact_index.sync_items = 1
        first = self.query("").unwrap()
        second = self.query("", cursor=first["next_cursor"]).unwrap()
        self.assertEqual(self.query("", cursor=second["next_cursor"]).failure.code, "memory_query_budget_exhausted")
        self.recall.begin(self.context, "next-turn")
        result = self.recall.query(self.context, "next-turn", query_intent="").unwrap()
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue(result["complete"])
