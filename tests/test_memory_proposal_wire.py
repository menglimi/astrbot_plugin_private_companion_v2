from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskError, require, stamp
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.models import AtomRef, Proposal
from companion_v2.memory.service import MemoryService
from companion_v2.memory.wire import EvidenceBudget
from tests.memory_support import MemoryFixture
from tests.test_memory_wire import runtime_scope


class MemoryProposalWireTests(MemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.service = MemoryService(self.tasks)
        self.stopped = False
        self.wire = self.service.bind_proposal_wire_v1(provider_id="companion_v2.memory",
            provider_generation="command-1", scope_for_context=runtime_scope, require_running=self.running)
        self.lookup = self.service.bind_operation_wire_v1(provider_id="companion_v2.memory",
            provider_generation="lookup-1", scope_for_context=runtime_scope)
        self.original = self.evidence()
        self.reference = self.wire.offer_source(self.context, self.original.source)

    def running(self):
        if self.stopped:
            raise TaskError("host_not_running", "test host stopped")
        require(self.tasks.check_generation())

    def request(self, *, key="save", payload=None, context=None, wire=None):
        context, wire = context or self.context, wire or self.wire
        return dict(schema_version=wire.schema_version, capability_id=wire.capability_id,
            capability_version="1.0", provider_id=wire.provider_id, provider_generation=wire.provider_generation,
            request_id="request-1", trace_id="trace-1", deadline_at=stamp(self.clock.now() + timedelta(minutes=2)),
            scope=runtime_scope(context), required_features=[], idempotency_key=key,
            budget=dict(max_input_bytes=65536, max_output_bytes=65536, max_model_calls=0),
            payload=payload if payload is not None else dict(namespace="personal", visibility="private", purpose="reply",
                proposal_id="proposal-1", operation="add", target_atom_id=None, expected_revision=None,
                subject=dict(kind="companion.person", ref=context.actor.subject.subject_id), predicate="饮用偏好",
                object="不喝咖啡", representation="用户不喝咖啡。", polarity="affirmed", attribution="user",
                confidence=1.0, retention="durable", evidence_refs=[deepcopy(self.reference)]))

    def query_receipt(self, *, operation_id=None, key="save", namespace="personal", context=None, wire=None):
        wire = wire or self.lookup
        payload = dict(namespace=namespace, visibility="private", purpose="reply")
        if operation_id:
            payload["operation_id"] = operation_id
        else:
            payload.update(capability_id="memory.proposal.submit", idempotency_key=key)
        request = self.request(payload=payload, context=context, wire=wire)
        del request["idempotency_key"]
        return wire.handle(context or self.context, request)

    def saved(self, request=None):
        result = self.wire.handle(self.context, request or self.request())
        self.assertEqual(result["status"], "succeeded", result)
        return result["output"]

    def count(self, table):
        return self.runtime.read_one("SELECT COUNT(*) n FROM " + table, ())["n"]

    def assert_empty(self):
        for table in ("memory_atoms", "memory_operations", "memory_changes", "memory_revisions"):
            self.assertEqual(self.count(table), 0, table)
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM sources WHERE owner = 'memory.atom'", ()))

    def test_add_and_both_receipt_keys_survive_an_expired_handle(self):
        request = self.request()
        output = self.saved(request)
        self.assertEqual((output["proposal_state"], output["commit_state"], output["revision"]),
                         ("persisted", "committed", 1))
        self.assertEqual(self.memory.read(self.context, AtomRef(output["atom_id"], 1)).unwrap()["object"], "不喝咖啡")
        self.clock.advance(timedelta(minutes=11))
        replay = self.request()
        replay.update(request_id="new-request", trace_id="new-trace")
        self.assertEqual(self.saved(replay), output)
        for lookup in (self.query_receipt(), self.query_receipt(operation_id=output["operation_id"])):
            self.assertEqual(lookup["output"], output)
            self.assertNotIn("不喝咖啡", json.dumps(lookup, ensure_ascii=False))
        self.assertEqual((self.count("memory_atoms"), self.count("memory_changes")), (1, 1))

    def test_same_key_different_payload_conflicts_without_resolving_stale_evidence(self):
        self.saved()
        self.clock.advance(timedelta(minutes=11))
        changed = self.request()
        changed["payload"]["object"] = "喝咖啡"
        result = self.wire.handle(self.context, changed)
        self.assertEqual(result["reason_code"], "idempotency_conflict")
        self.assertEqual(self.count("memory_changes"), 1)

    def test_correct_preserves_pin_single_value_and_dependencies_then_retract_reports_target(self):
        dependency = self.remember(replace(self.proposed(), predicate="依据"), "dependency")
        original = self.remember(self.proposed(context_mode="pinned", dependencies=(dependency,)), "pinned")
        new_source = self.evidence("我现在喝茶")
        payload = self.request()["payload"] | dict(operation="correct", proposal_id="correct",
            target_atom_id=original.atom_id, expected_revision=1, object="喝茶", representation="用户现在喝茶。",
            retention="short", valid_to=stamp(self.clock.now() + timedelta(hours=1)),
            evidence_refs=[self.wire.offer_source(self.context, new_source.source)])
        fixed = self.saved(self.request(key="correct", payload=payload))
        atom = self.memory.read(self.context, AtomRef(original.atom_id, 2)).unwrap()
        stored = json.loads(self.runtime.read_one("SELECT record_json FROM memory_atoms WHERE atom_id = ?",
            (original.atom_id,))["record_json"])["proposal"]
        self.assertEqual((atom["context_mode"], stored["single_value"], stored["dependencies"][0]["atom_id"]),
                         ("pinned", True, dependency.atom_id))
        stale = self.wire.handle(self.context, self.request(key="stale", payload=payload))
        self.assertEqual(stale["reason_code"], "memory_revision_conflict")
        request = self.request(key="retract", payload=dict(namespace="personal", visibility="private", purpose="reply",
            proposal_id="retract", operation="retract", target_atom_id=original.atom_id, expected_revision=2,
            evidence_refs=payload["evidence_refs"]))
        removed = self.saved(request)
        self.assertEqual((removed["revision"], removed["effective_retention"], removed["retention_until"]),
                         (3, "short", fixed["retention_until"]))
        self.assertEqual(self.memory.read(self.context, AtomRef(original.atom_id, 3)).failure.code, "memory_inactive")
        self.assertEqual(self.query_receipt(key="correct")["output"], fixed)

    def test_no_op_has_a_durable_skipped_receipt_without_a_fact(self):
        request = self.request(payload=dict(namespace="personal", visibility="private", purpose="reply",
            proposal_id="skip", operation="no_op", target_atom_id=None, expected_revision=None))
        output = self.saved(request)
        self.assertEqual((output["proposal_state"], output["commit_state"]), ("skipped", "not_committed"))
        self.assertEqual(self.query_receipt()["output"], output)
        self.assertEqual((self.count("memory_atoms"), self.count("memory_changes")), (0, 0))

    def test_scope_and_generation_cannot_be_selected_by_request(self):
        for key, value in (("scope", runtime_scope(self.context) | {"persona_id": "other"}),
                           ("provider_generation", "previous")):
            result = self.wire.handle(self.context, self.request() | {key: value})
            self.assertIn(result["status"], ("permission_denied", "unavailable"))
            self.assertIsNone(result["output"])
        self.assert_empty()

    def test_fake_reference_or_metadata_never_certifies_an_assertion(self):
        for field, value in (("id", "fake"), ("source_type", "fake"), ("evidence_kind", "bot_message"),
                             ("source_revision", "fake"), ("expires_at", None)):
            request = self.request()
            request["payload"]["evidence_refs"][0][field] = value
            result = self.wire.handle(self.context, request)
            self.assertEqual(result["status"], "rejected", result)
        self.assert_empty()

    def test_expired_revoked_and_foreign_context_evidence_cannot_commit(self):
        expiring = self.wire.offer_source(self.context, self.original.source,
            expires_at=self.clock.now() + timedelta(seconds=1))
        self.clock.advance(timedelta(seconds=2))
        request = self.request()
        request["payload"]["evidence_refs"] = [expiring]
        self.assertEqual(self.wire.handle(self.context, request)["reason_code"], "memory_session_expired")
        later = self.context_for(self.important, replace(self.context.scope, session_id="later"))
        result = self.wire.handle(later, self.request(context=later))
        self.assertEqual(result["reason_code"], "evidence_unavailable")
        self.memory.sources.revoke(self.original.source, expected_governance_revision=1,
                                   observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.wire.handle(self.context, self.request())["status"], "rejected")
        self.assert_empty()

    def test_current_permission_is_required_for_submit_replay_and_lookup(self):
        self.saved()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        for result in (self.wire.handle(self.context, self.request()), self.query_receipt()):
            self.assertEqual(result["status"], "permission_denied", result)
            self.assertIsNone(result["output"])
        self.assertEqual(self.count("memory_operations"), 1)

    def test_unknown_and_other_namespace_or_owner_lookups_reveal_no_receipt(self):
        output = self.saved()
        other = self.context_for(self.standard)
        self.grant(other.actor, other.scope, "memory.read")
        for result in (self.query_receipt(key="missing"), self.query_receipt(namespace="other"),
                       self.query_receipt(operation_id=output["operation_id"], namespace="other"),
                       self.query_receipt(operation_id=output["operation_id"], context=other)):
            self.assertEqual((result["status"], result["reason_code"], result["output"]),
                             ("rejected", "target_unavailable", None))

    def test_receipts_and_replay_survive_reopen_and_new_generation(self):
        output = self.saved()
        tasks, _, _ = self.components(self.open_runtime())
        service = MemoryService(tasks)
        lookup = service.bind_operation_wire_v1(provider_id=self.lookup.provider_id,
            provider_generation="lookup-2", scope_for_context=runtime_scope)
        found = self.query_receipt(wire=lookup)
        self.assertEqual(found["provider_generation"], "lookup-2")
        self.assertEqual(found["output"], output)
        commands = service.bind_proposal_wire_v1(provider_id=self.wire.provider_id,
            provider_generation="command-2", scope_for_context=runtime_scope,
            require_running=lambda: require(tasks.check_generation()))
        result = commands.handle(self.context, self.request(wire=commands))
        self.assertEqual(result["output"], output)
        self.assertEqual(result["output"]["original_provider_generation"], "command-1")

    def test_query_issued_evidence_ref_can_be_submitted_without_forging_source_attribution(self):
        self.remember()
        query = self.service.bind_query_wire_v1(provider_id="companion_v2.memory", provider_generation="query-1",
            scope_for_context=runtime_scope, token_count=len, default_evidence_budget=EvidenceBudget(8, 2400, 800))
        request = self.request(wire=query, payload=dict(namespace="personal", visibility="private", purpose="reply", query_intent="咖啡"))
        del request["idempotency_key"]
        result = query.handle(self.context, request)
        reference = result["output"]["items"][0]["evidence"][0]["ref"]
        request = self.request()
        request["payload"].update(predicate="其他偏好描述", evidence_refs=[reference])
        self.saved(request)
        self.assertEqual(self.count("memory_atoms"), 2)

    def test_output_budget_and_deadline_reject_without_leaving_written_facts_or_receipts(self):
        request = self.request()
        request["budget"]["max_output_bytes"] = 1
        self.assertEqual(self.wire.handle(self.context, request)["reason_code"], "output_budget_exceeded")
        self.assert_empty()
        original = self.wire._output
        def slow(*args):
            result = original(*args)
            self.clock.advance(timedelta(minutes=3))
            return result
        with patch.object(self.wire, "_output", side_effect=slow):
            result = self.wire.handle(self.context, self.request())
        self.assertEqual(result["status"], "timeout")
        self.assert_empty()

    def test_result_envelope_counts_toward_budget_before_commit(self):
        output = self.saved()
        request = self.request(key="second")
        request["budget"]["max_output_bytes"] = len(json.dumps(output, ensure_ascii=False,
                                                               separators=(",", ":")).encode("utf-8"))
        result = self.wire.handle(self.context, request)
        self.assertEqual(result["reason_code"], "output_budget_exceeded")
        self.assertEqual((self.count("memory_atoms"), self.count("memory_operations")), (1, 1))

    def test_host_stop_before_outer_commit_rolls_back_all_changes(self):
        original = self.wire._output
        def stop(*args):
            output = original(*args)
            self.stopped = True
            return output
        with patch.object(self.wire, "_output", side_effect=stop):
            result = self.wire.handle(self.context, self.request())
        self.assertEqual(result["reason_code"], "host_not_running")
        self.assert_empty()

    def test_policy_change_before_commit_rolls_back_the_proposal(self):
        original = self.wire._output
        def change_policy(*args):
            output = original(*args)
            access = self.service.writer.access
            access.policy = replace(access.policy, query_items=1)
            return output
        with patch.object(self.wire, "_output", side_effect=change_policy):
            result = self.wire.handle(self.context, self.request())
        self.assertEqual(result["reason_code"], "memory_policy_changed")
        self.assert_empty()

    def test_receipt_namespace_does_not_expose_another_callers_operation(self):
        self.saved()
        with patch.object(self.service.writer.access, "operator", self.core):
            self.assertEqual(self.query_receipt()["reason_code"], "target_unavailable")

    def test_internal_writer_operations_are_not_misrepresented_as_wire_receipts(self):
        item = self.proposed()
        receipt = self.memory.submit(self.context, item, operation_key="internal").unwrap()
        result = self.query_receipt(operation_id=receipt["operation_id"])
        self.assertEqual((result["reason_code"], result["output"]), ("target_unavailable", None))

    def test_source_revocation_during_preparation_rolls_back_commit(self):
        original = self.wire._output
        def revoke(*args):
            output = original(*args)
            self.memory.sources.revoke(self.original.source, expected_governance_revision=1,
                                       observed_at=self.clock.now()).unwrap()
            return output
        with patch.object(self.wire, "_output", side_effect=revoke):
            result = self.wire.handle(self.context, self.request())
        self.assertEqual(result["status"], "rejected")
        self.assert_empty()

    def test_enclosing_write_or_read_transaction_cannot_produce_a_false_committed_receipt(self):
        for transaction in (self.runtime.transaction, self.runtime.read_snapshot):
            with transaction():
                result = self.wire.handle(self.context, self.request())
                self.assertEqual(result["reason_code"], "outer_transaction_required")
            self.assert_empty()

    def test_commit_acknowledgement_loss_is_uncertain_and_lookup_finds_the_single_commit(self):
        self.commit_failure(after=True)

    def test_sql_commit_failure_does_not_assert_that_the_operation_never_committed(self):
        self.commit_failure(after=False)

    def commit_failure(self, *, after):
        connection = self.runtime._require_connection()
        runtime = self.runtime
        class FaultyConnection:
            def __getattr__(self, name):
                return getattr(connection, name)
            def execute(self, statement, *args):
                if statement == "COMMIT" and runtime._write_depth:
                    if after:
                        connection.execute(statement, *args)
                    raise sqlite3.OperationalError("simulated commit acknowledgement failure")
                return connection.execute(statement, *args)
        with patch.object(self.runtime, "_require_connection", return_value=FaultyConnection()), \
                patch.object(self.service.writer, "submit", wraps=self.service.writer.submit) as submit:
            result = self.wire.handle(self.context, self.request())
        self.assertEqual((result["status"], result["retryable"], result["output"]["commit_state"]),
                         ("uncertain", False, "uncertain"))
        self.assertEqual(submit.call_count, 1)
        found = self.query_receipt(operation_id=result["output"]["operation_id"])
        if after:
            self.assertEqual(found["output"]["commit_state"], "committed")
            self.assertEqual(self.count("memory_changes"), 1)
        else:
            self.assertEqual(found["reason_code"], "target_unavailable")
            self.assert_empty()

    def test_simultaneous_same_key_commits_once(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: self.wire.handle(self.context, deepcopy(request)), range(2)))
        self.assertTrue(all(result["status"] == "succeeded" for result in results), results)
        self.assertEqual(results[0]["output"], results[1]["output"])
        self.assertEqual(self.count("memory_changes"), 1)

    def test_unsupported_profiles_and_malformed_requests_cannot_write(self):
        for field, value in (("object", {"text": "咖啡"}),
                             ("qualifiers", {"numeric": 3}), ("types", ["claim"]), ("extensions", {"vendor.any": {}})):
            request = self.request()
            request["payload"][field] = value
            self.assertEqual(self.wire.handle(self.context, request)["status"], "unavailable")
        for field, value in (("expected_revision", 1), ("confidence", True), ("retention", "unknown"),
                             ("evidence_refs", []), ("valid_to", "2026-09-24")):
            request = self.request()
            request["payload"][field] = value
            self.assertEqual(self.wire.handle(self.context, request)["status"], "rejected")
        self.assert_empty()


if __name__ == "__main__":
    unittest.main()
