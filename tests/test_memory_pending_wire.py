from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import patch

from companion_v2.execution.models import require, stamp
from companion_v2.memory.service import MemoryService
from companion_v2.memory.wire import EvidenceBudget
from companion_v2.memory.models import AtomRef
from tests.memory_support import MemoryFixture
from tests.memory_stream_support import commit_fault
from tests import test_memory_proposal_wire as proposal_support
from tests.test_memory_wire import runtime_scope


class MemoryPendingWireTests(MemoryFixture, unittest.TestCase):
    request = proposal_support.MemoryProposalWireTests.request
    query_receipt = proposal_support.MemoryProposalWireTests.query_receipt
    count = proposal_support.MemoryProposalWireTests.count

    def setUp(self):
        super().setUp()
        self.service = MemoryService(self.tasks)
        self.wire = self.service.bind_proposal_wire_v1(provider_id="companion_v2.memory", provider_generation="command-1",
            scope_for_context=runtime_scope, require_running=lambda: require(self.tasks.check_generation()))
        self.lookup = self.service.bind_operation_wire_v1(provider_id="companion_v2.memory", provider_generation="lookup-1", scope_for_context=runtime_scope)
        self.original = self.evidence()
        self.reference = self.wire.offer_source(self.context, self.original.source)

    def pending(self, **changes):
        request = self.request()
        request["payload"].update(defer_until_boundary=True, **changes)
        result = self.wire.handle(self.context, request)
        self.assertEqual(result["status"], "pending", result)
        self.assertEqual(result["output"]["commit_state"], "not_committed")
        return request, result["output"]

    def resolve(self, output, decision="accept", context=None, **kwargs):
        return self.wire.resolve_pending(context or self.context, output["operation_id"], decision=decision,
            deadline_at=stamp(self.clock.now() + timedelta(seconds=30)), **kwargs)

    def test_pending_does_not_create_a_fact_and_boundary_updates_replay_and_lookup(self):
        request, output = self.pending()
        self.assertEqual(self.count("memory_atoms"), 0)
        self.assertEqual(self.query_receipt()["status"], "pending")
        committed = self.resolve(output)
        self.assertEqual(committed["status"], "succeeded", committed)
        self.assertEqual(committed["output"]["original_provider_generation"], "command-1")
        self.assertEqual(self.count("memory_atoms"), 1)
        self.assertEqual(self.query_receipt()["output"], committed["output"])
        self.assertEqual(self.wire.handle(self.context, request)["output"], committed["output"])
        self.assertEqual(self.resolve(output)["output"], committed["output"])
        self.assertEqual(self.count("memory_changes"), 1)

    def test_pending_receipts_and_boundary_decisions_are_isolated_by_bot_and_persona(self):
        others = self.other_memory_owners()
        _, output = self.pending()
        for dimension, context in others.items():
            with self.subTest(dimension=dimension):
                self.assertEqual(self.service.writer.pending(context).unwrap(), [])
                self.assertEqual(self.service.writer.operation(context, output["operation_id"]).failure.code,
                                 "memory_operation_unavailable")
                results = [self.query_receipt(operation_id=output["operation_id"], context=context),
                           self.query_receipt(context=context)]
                results.extend(self.resolve(output, decision, context) for decision in ("accept", "discard"))
                for result in results:
                    self.assertEqual((result["status"], result["reason_code"], result["output"]),
                                     ("rejected", "target_unavailable", None))
        self.assertEqual(self.query_receipt()["output"], output)
        self.assertEqual(self.count("memory_atoms"), 0)
        committed = self.resolve(output)
        self.assertEqual(committed["status"], "succeeded", committed)
        for dimension, context in others.items():
            with self.subTest(dimension=dimension, state="committed"):
                result = self.query_receipt(operation_id=output["operation_id"], context=context)
                self.assertEqual((result["reason_code"], result["output"]), ("target_unavailable", None))
        self.assertEqual(self.count("memory_changes"), 1)

    def test_pending_query_pages_are_isolated_by_bot_and_persona(self):
        others = self.other_memory_owners()
        _, output = self.pending()
        query = self.service.bind_query_wire_v1(provider_id="companion_v2.memory", provider_generation="query-1",
            scope_for_context=runtime_scope, token_count=len, default_evidence_budget=EvidenceBudget(8, 2400, 800))
        for dimension, context in {**others, "original": self.context}.items():
            with self.subTest(dimension=dimension):
                request = self.request(wire=query, context=context, payload=dict(namespace="personal",
                    visibility="private", purpose="reply", query_intent="咖啡", include_pending=True))
                del request["idempotency_key"]
                items = []
                for _ in range(3):
                    result = query.handle(context, request)
                    self.assertEqual(result["status"], "succeeded", result)
                    items.extend(result["output"]["items"])
                    if not result["output"]["next_cursor"]:
                        break
                    request["payload"]["cursor"] = result["output"]["next_cursor"]
                self.assertIsNone(result["output"]["next_cursor"])
                if dimension == "original":
                    self.assertEqual([item["proposal_id"] for item in items], [output["proposal_id"]])
                else:
                    self.assertEqual(items, [])

    def test_same_proposal_and_idempotency_keys_have_independent_owner_receipts(self):
        contexts = {"original": self.context, **self.other_memory_owners()}
        outputs = {}
        for dimension, context in contexts.items():
            self.grant(context.actor, context.scope, "text")
            event = self.event("我不喝咖啡", context=context)
            self.accept(event, context=context)
            request = self.request(context=context)
            request["payload"].update(defer_until_boundary=True,
                evidence_refs=[self.wire.offer_source(context, event.source)])
            result = self.wire.handle(context, request)
            self.assertEqual(result["status"], "pending", result)
            outputs[dimension] = result["output"]
        self.assertEqual(len({output["operation_id"] for output in outputs.values()}), 3)
        for dimension, context in contexts.items():
            self.assertEqual(self.query_receipt(context=context)["output"], outputs[dimension])
            for other, output in outputs.items():
                if other != dimension:
                    result = self.query_receipt(context=context, operation_id=output["operation_id"])
                    self.assertEqual((result["reason_code"], result["output"]), ("target_unavailable", None))
        self.assertEqual(self.count("memory_atoms"), 0)

    def test_discard_survives_restart_without_creating_a_fact(self):
        request, output = self.pending()
        result = self.resolve(output, "discard")
        self.assertEqual(result["output"]["proposal_state"], "skipped")
        tasks, _, _ = self.components(self.open_runtime())
        lookup = MemoryService(tasks).bind_operation_wire_v1(provider_id="companion_v2.memory",
            provider_generation="lookup-2", scope_for_context=runtime_scope)
        self.assertEqual(self.query_receipt(wire=lookup)["output"], result["output"])
        self.assertEqual(self.wire.handle(self.context, request)["output"]["proposal_state"], "skipped")
        self.assertEqual(self.count("memory_atoms"), 0)

    def test_internal_reflection_decision_also_updates_original_wire_receipt(self):
        _, output = self.pending()
        receipt = self.service.writer.commit_pending(self.context, output["operation_id"]).unwrap()
        self.assertEqual(self.query_receipt()["output"], receipt["wire"]["output"])
        self.assertEqual(self.query_receipt()["output"]["proposal_state"], "persisted")

    def test_expired_handle_does_not_destroy_durable_pending_evidence(self):
        _, output = self.pending()
        self.clock.advance(timedelta(minutes=11))
        self.assertEqual(self.resolve(output)["status"], "succeeded")

    def test_expired_validity_prevents_boundary_commit(self):
        _, output = self.pending(retention="short", valid_to=stamp(self.clock.now() + timedelta(seconds=1)))
        self.clock.advance(timedelta(seconds=2))
        self.assertEqual(self.resolve(output)["reason_code"], "memory_expired")
        self.assertEqual(self.query_receipt()["status"], "pending")
        self.assertEqual(self.count("memory_atoms"), 0)

    def test_withdrawn_source_prevents_accept_but_allows_explicit_discard(self):
        _, output = self.pending()
        self.memory.sources.revoke(self.original.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertNotEqual(self.resolve(output)["status"], "succeeded")
        self.assertEqual(self.query_receipt()["status"], "pending")
        self.assertEqual(self.resolve(output, "discard")["output"]["proposal_state"], "skipped")
        self.assertEqual(self.count("memory_atoms"), 0)

    def test_boundary_commit_uncertainty_is_resolved_by_lookup_without_replaying(self):
        _, output = self.pending()
        with commit_fault(self.runtime, after=True), patch.object(self.service.writer, "commit_pending",
                wraps=self.service.writer.commit_pending) as commit:
            result = self.resolve(output)
        self.assertEqual((result["status"], result["retryable"], result["output"]["commit_state"]), ("uncertain", False, "uncertain"))
        self.assertEqual(commit.call_count, 1)
        final = self.query_receipt()["output"]
        self.assertEqual(final["commit_state"], "committed")
        self.assertEqual(self.resolve(output)["output"], final)
        self.assertEqual(self.count("memory_changes"), 1)

    def test_boundary_commit_failure_leaves_a_pending_operation(self):
        _, output = self.pending()
        with commit_fault(self.runtime, after=False):
            result = self.resolve(output)
        self.assertEqual((result["status"], result["retryable"]), ("uncertain", False))
        self.assertEqual(self.query_receipt()["status"], "pending")
        self.assertEqual(self.count("memory_changes"), 0)

    def test_boundary_final_deadline_rolls_back_fact_and_receipt(self):
        _, output = self.pending()
        commit = self.service.writer.commit_pending
        def slow_commit(*args):
            result = commit(*args)
            self.clock.advance(timedelta(seconds=31))
            return result
        with patch.object(self.service.writer, "commit_pending", side_effect=slow_commit):
            self.assertEqual(self.resolve(output)["reason_code"], "deadline_expired")
        self.assertEqual(self.query_receipt()["status"], "pending")
        self.assertEqual(self.count("memory_changes"), 0)

    def test_pending_cas_conflict_and_cross_session_are_explicit(self):
        target = self.remember()
        new_source = self.evidence("纠正咖啡偏好")
        self.reference = self.wire.offer_source(self.context, new_source.source)
        _, output = self.pending(operation="correct", target_atom_id=target.atom_id, expected_revision=1,
                                  object="喝茶", representation="喝茶")
        later = self.context_for(self.important, replace(self.context.scope, session_id="later"))
        self.assertEqual(self.resolve(output, context=later)["reason_code"], "memory_pending_context_changed")
        self.memory.submit(self.context, replace(self.proposed(), operation="correct", target=target,
            object="别的", representation="另一个偏好", evidence=(new_source,)), operation_key="another").unwrap()
        self.assertEqual(self.resolve(output)["reason_code"], "memory_revision_conflict")

    def test_small_boundary_response_budget_rolls_back_fact_and_keeps_pending_receipt(self):
        _, output = self.pending()
        result = self.resolve(output, max_output_bytes=1)
        self.assertEqual(result["reason_code"], "output_budget_exceeded")
        self.assertEqual(self.query_receipt()["status"], "pending")
        self.assertEqual(self.count("memory_atoms"), 0)

    def test_include_pending_returns_distinct_draft_and_invalidates_cursor_after_commit(self):
        _, output = self.pending()
        query = self.service.bind_query_wire_v1(provider_id="companion_v2.memory", provider_generation="query-1",
            scope_for_context=runtime_scope, token_count=len, default_evidence_budget=EvidenceBudget(8, 2400, 800))
        request = self.request(wire=query, payload=dict(namespace="personal", visibility="private", purpose="reply", query_intent="咖啡", include_pending=True))
        del request["idempotency_key"]
        first = query.handle(self.context, request)
        self.assertEqual(first["status"], "succeeded", first)
        self.assertEqual(first["output"]["items"], [])
        request["payload"]["cursor"] = first["output"]["next_cursor"]
        draft = query.handle(self.context, request)
        self.assertEqual(draft["status"], "succeeded", draft)
        item = draft["output"]["items"][0]
        self.assertEqual(item["item_kind"], "proposal")
        self.assertNotIn("atom_id", item)
        self.assertEqual(item["proposal_id"], output["proposal_id"])
        self.resolve(output)
        self.assertEqual(query.handle(self.context, request)["reason_code"], "cursor_invalid")

    def test_no_op_cannot_enter_pending_queue(self):
        request = self.request(payload=dict(namespace="personal", visibility="private", purpose="reply", proposal_id="skip",
            operation="no_op", target_atom_id=None, expected_revision=None, defer_until_boundary=True))
        self.assertEqual(self.wire.handle(self.context, request)["reason_code"], "invalid_defer_until_boundary")

    def test_fact_and_draft_pages_share_one_budget_and_keep_all_cursors(self):
        self.remember(replace(self.proposed(), predicate="第一条"), "first")
        self.remember(replace(self.proposed(), predicate="第二条"), "second")
        self.pending()
        query = self.service.bind_query_wire_v1(provider_id="companion_v2.memory", provider_generation="query-1",
            scope_for_context=runtime_scope, token_count=len, default_evidence_budget=EvidenceBudget(8, 2400, 800))
        request = self.request(wire=query, payload=dict(namespace="personal", visibility="private", purpose="reply", query_intent="咖啡", include_pending=True))
        del request["idempotency_key"]
        policy = replace(self.service.writer.access.policy, turn_calls=3)
        with patch.object(self.service.writer.access, "policy", policy):
            kinds = []
            for _ in range(3):
                result = query.handle(self.context, request)
                self.assertEqual(result["status"], "succeeded", result)
                kinds.extend(i["item_kind"] for i in result["output"]["items"])
                if result["output"]["next_cursor"]:
                    request["payload"]["cursor"] = result["output"]["next_cursor"]
            self.assertEqual(kinds, ["fact", "fact", "proposal"])
            self.assertEqual(query.handle(self.context, request)["reason_code"], "memory_query_budget_exhausted")
        sessions = self.runtime.read_all("SELECT calls FROM memory_sessions WHERE session_id LIKE 'memory-wire-%'", ())
        self.assertEqual([s["calls"] for s in sessions], [3])

    def test_pending_queries_do_not_cross_sessions_or_return_revoked_evidence(self):
        self.pending()
        query = self.service.bind_query_wire_v1(provider_id="companion_v2.memory", provider_generation="query-1",
            scope_for_context=runtime_scope, token_count=len, default_evidence_budget=EvidenceBudget(8, 2400, 800))
        for revoked in (False, True):
            context = self.context if revoked else self.context_for(self.important, replace(self.context.scope, session_id="later"))
            if revoked:
                self.memory.sources.revoke(self.original.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
            request = self.request(wire=query, context=context,
                payload=dict(namespace="personal", visibility="private", purpose="reply", query_intent="咖啡", include_pending=True))
            del request["idempotency_key"]
            for _ in range(2):
                result = query.handle(context, request)
                self.assertEqual(result["status"], "succeeded", result)
                self.assertEqual(result["output"]["items"], [])
                if not result["output"]["next_cursor"]:
                    break
                request["payload"]["cursor"] = result["output"]["next_cursor"]


if __name__ == "__main__":
    unittest.main()
