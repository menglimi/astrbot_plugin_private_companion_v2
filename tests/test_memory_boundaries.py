from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
from threading import Barrier
import unittest

from companion_v2.execution.models import digest
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.models import AtomRef, owner_key
from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.writer import MemoryWriter
from tests.memory_support import MemoryFixture


class MemoryBoundaryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def test_historical_validity_cannot_rewind_current_permissions(self):
        start = self.clock.now()
        ref = self.remember(replace(self.proposed(), valid_from=start, valid_to=start + timedelta(seconds=1)))
        self.clock.advance(timedelta(seconds=2))
        self.assertEqual(self.memory.read(self.context, ref).failure.code, "memory_expired")
        self.assertEqual(self.query(at_time=start).unwrap()["items"][0]["atom_id"], ref.atom_id)
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD, expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.assertFalse(self.memory.read(self.context, ref, at=start).is_success)
        self.assertFalse(self.recall.query(self.context, "query", query_intent="咖啡", at_time=start).is_success)

    def test_stable_owner_crosses_private_sessions_but_session_memory_does_not(self):
        durable = self.remember()
        transient = self.remember(replace(self.proposed(), predicate="临时事项", retention="session"), key="session")
        scope = replace(self.context.scope, session_id="later-session")
        later = self.context_for(self.important, scope)
        self.assertTrue(self.memory.read(later, durable).is_success)
        self.assertEqual(self.memory.read(later, transient).failure.code, "memory_session_mismatch")
        self.assertFalse(self.memory.read(self.context_for(self.core), durable).is_success)

    def test_durable_memory_recall_projects_across_private_sessions_for_same_owner(self):
        durable = self.remember()
        later_scope = replace(self.context.scope, native_scope_id="later", conversation_id="later",
                              session_id="later-session")
        later = self.context_for(self.important, later_scope)

        self.recall.begin(later, "later-query")
        result = self.recall.query(later, "later-query", query_intent="咖啡").unwrap()

        self.assertEqual([item["atom_id"] for item in result["items"]], [durable.atom_id])
        self.assertTrue(result["complete"])

        another_human = self.context_for(self.standard)
        self.grant(another_human.actor, another_human.scope, "memory.read")
        self.recall.begin(another_human, "other-query")
        isolated = self.recall.query(another_human, "other-query", query_intent="咖啡").unwrap()
        self.assertEqual(isolated["items"], [])

    def test_durable_memory_recall_does_not_follow_a_persona_switch(self):
        reference = self.remember()
        other_role = replace(self.context.role_binding.role, subject_id="persona-b")
        current = self.personas.binding("base")
        self.personas.set_binding(replace(current, role=other_role, revision=current.revision + 1),
                                  expected_revision=current.revision, observed_at=self.clock.now())
        changed_role = self.context_for(self.important)

        self.assertEqual(self.memory.read(self.context, reference).failure.code, "role_binding_changed")
        self.assertEqual(self.memory.read(changed_role, reference).failure.code, "memory_unavailable")
        self.recall.begin(changed_role, "changed-role-query")
        result = self.recall.query(changed_role, "changed-role-query", query_intent="咖啡").unwrap()

        self.assertEqual(result["items"], [])

        self.personas.set_binding(replace(current, revision=current.revision + 2),
                                  expected_revision=current.revision + 1, observed_at=self.clock.now())
        restored = self.context_for(self.important)
        self.assertEqual(owner_key(restored), owner_key(self.context))
        self.assertTrue(self.memory.read(restored, reference).is_success)
        self.recall.begin(restored, "restored-role-query")
        result = self.recall.query(restored, "restored-role-query", query_intent="咖啡").unwrap()
        self.assertEqual([item["atom_id"] for item in result["items"]], [reference.atom_id])

    def test_durable_memory_is_partitioned_by_logical_bot_even_for_same_human_and_persona(self):
        reference = self.remember()
        another_bot = self.alternate_context(bot_id="bot-b", role_id=self.context.role_binding.role.subject_id)
        self.assertNotEqual(owner_key(self.context), owner_key(another_bot))
        self.assertEqual(self.memory.read(another_bot, reference).failure.code, "memory_unavailable")
        self.recall.begin(another_bot, "other-bot-query")
        result = self.recall.query(another_bot, "other-bot-query", query_intent="咖啡").unwrap()
        self.assertEqual(result["items"], [])

    def test_durable_memory_is_partitioned_by_v2_persona_within_one_bot(self):
        reference = self.remember()
        another_persona = self.alternate_context(bot_id=self.context.scope.bot_id, role_id="persona-b",
                                                session_selector=True)
        self.assertEqual(another_persona.scope.bot_id, self.context.scope.bot_id)
        self.assertEqual(another_persona.actor, self.context.actor)
        self.assertNotEqual(owner_key(self.context), owner_key(another_persona))
        self.assertEqual(self.memory.read(another_persona, reference).failure.code, "memory_unavailable")
        self.recall.begin(another_persona, "other-persona-query")
        result = self.recall.query(another_persona, "other-persona-query", query_intent="咖啡").unwrap()
        self.assertEqual(result["items"], [])

    def test_only_one_correction_wins_concurrent_cas(self):
        item = self.proposed()
        ref = self.remember(item)
        evidence = self.evidence("纠正偏好")
        def correct(n):
            return self.memory.submit(self.context, replace(item, operation="correct", target=ref, evidence=(evidence,),
                object=str(n), representation="偏好 " + str(n)), operation_key="parallel-" + str(n))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(correct, (1, 2)))
        self.assertEqual(sum(r.is_success for r in results), 1)
        self.assertEqual(next(r.failure.code for r in results if not r.is_success), "memory_revision_conflict")

    def test_two_connections_keep_content_hash_history_and_receipts_consistent_under_contention(self):
        # Private Companion #254: body and hash must stay one committed version,
        # even when independent connections race on repeated corrections.
        item = self.proposed()
        reference = self.remember(item)
        other_tasks, _, _ = self.components(self.open_runtime())
        writers = (self.memory, MemoryWriter(other_tasks))
        with ThreadPoolExecutor(max_workers=2) as pool:
            for revision in range(2, 10):
                evidence = self.evidence("parallel correction " + str(revision))
                proposals = [replace(item, operation="correct", target=reference, evidence=(evidence,),
                    object=f"choice-{revision}-{index}", representation=f"用户的新偏好 {revision}-{index}") for index in range(2)]
                barrier = Barrier(2)
                def correct(index):
                    barrier.wait(timeout=5)
                    return writers[index].submit(self.context, proposals[index],
                        operation_key=f"two-connections-{revision}-{index}")
                results = list(pool.map(correct, range(2)))
                self.assertEqual(sum(result.is_success for result in results), 1)
                winner = next(index for index, result in enumerate(results) if result.is_success)
                self.assertEqual(results[1 - winner].failure.code, "memory_revision_conflict")
                reference = AtomRef(reference.atom_id, revision)
                for writer in writers:
                    fact = writer.read(self.context, reference).unwrap()
                    self.assertEqual(fact["representation"], proposals[winner].representation)
                    self.assertEqual(fact["object"], proposals[winner].object)
        history = self.runtime.read_all("""SELECT r.record_json, s.payload_json, s.content_hash
            FROM memory_revisions r JOIN sources s ON s.source_id = r.atom_id
            AND s.lineage_id = r.atom_id AND s.source_revision = r.revision
            WHERE r.atom_id = ? ORDER BY r.revision""", (reference.atom_id,))
        self.assertEqual(len(history), 9)
        for row in history:
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload, json.loads(row["record_json"])["proposal"]["representation"])
            self.assertEqual(row["content_hash"], digest(payload))
        operations = self.runtime.read_all("SELECT payload_hash, proposal_json, result_json FROM memory_operations", ())
        self.assertEqual(len(operations), 9)
        for row in operations:
            self.assertEqual(row["payload_hash"], digest(json.loads(row["proposal_json"])))
            self.assertEqual(json.loads(row["result_json"])["state"], "persisted")

    def test_missing_or_damaged_search_projection_rebuilds_from_facts(self):
        ref = self.remember()
        self.query().unwrap()
        self.recall.index.path.unlink()
        self.recall = MemoryQuery(self.memory)
        self.assertEqual(self.query().unwrap()["items"][0]["atom_id"], ref.atom_id)
        self.recall.index.path.write_bytes(b"not a sqlite database")
        self.recall = MemoryQuery(self.memory)
        self.assertEqual(self.query().unwrap()["items"][0]["atom_id"], ref.atom_id)
        self.assertEqual(self.memory.read(self.context, ref).unwrap()["revision"], 1)

    def test_explicit_oversized_terms_return_a_clear_failure(self):
        result = self.query("".join(chr(0x4e00 + n) for n in range(700)))
        self.assertEqual(result.failure.code, "memory_query_terms_exceeded")
