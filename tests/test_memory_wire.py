from dataclasses import replace
from contextlib import closing
from datetime import timedelta
import sqlite3
import unittest

from companion_v2.execution.models import stamp
from companion_v2.memory.service import MemoryService
from companion_v2.memory.wire import EvidenceBudget, runtime_scope_from_task_context
from tests.memory_support import MemoryFixture
from tests.test_management_access import NOW


PROVIDER_ID = "companion_v2.memory"
PROVIDER_GENERATION = "test-generation-1"


def runtime_scope(context):
    return runtime_scope_from_task_context(context, ecosystem_id="astrbot",
        runtime_instance_id="test-runtime-1", host_kind="astrbot")


class MemoryWireTests(MemoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.memory_service = MemoryService(self.tasks, policy=self.memory.policy)
        self.wire = self.memory_service.bind_query_wire_v1(
            provider_id=PROVIDER_ID,
            provider_generation=PROVIDER_GENERATION,
            scope_for_context=runtime_scope,
            token_count=len,
            default_evidence_budget=EvidenceBudget(8, 2400, 800),
        )

    def request(self, *, payload=None, scope=None, budget=None, trace_id="trace-1", request_id="request-1"):
        return {
            "schema_version": "memory.query.v1",
            "capability_id": "memory.query",
            "capability_version": "1.0",
            "provider_id": PROVIDER_ID,
            "provider_generation": PROVIDER_GENERATION,
            "request_id": request_id,
            "trace_id": trace_id,
            "deadline_at": stamp(NOW + timedelta(minutes=2)),
            "scope": scope if scope is not None else runtime_scope(self.context),
            "required_features": [],
            "budget": budget if budget is not None else {
                "max_input_bytes": 16384,
                "max_model_calls": 0,
                "max_output_bytes": 20000,
            },
            "payload": payload if payload is not None else {
                "namespace": "personal",
                "visibility": "private",
                "purpose": "reply",
                "query_intent": "咖啡",
                "time_range": None,
                "at_time": None,
                "allowed_retention": [],
                "include_pending": False,
                "conflict_policy": "current_only",
                "confidence_floor": None,
                "evidence_budget": {"max_items": 8, "max_chars": 2400, "max_tokens": 800},
                "cursor": None,
                "extensions": {},
            },
        }

    def test_query_maps_a_private_fact_and_revalidated_original_evidence(self):
        self.remember()

        result = self.wire.handle(self.context, self.request())

        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["schema_version"], "memory.result.v1")
        self.assertEqual(result["capability_id"], "memory.query")
        self.assertEqual(result["request_id"], "request-1")
        recall = result["output"]
        self.assertEqual(len(recall["items"]), 1)
        fact = recall["items"][0]
        self.assertEqual(fact["item_kind"], "fact")
        self.assertEqual(fact["fact_status"], "active")
        self.assertEqual(fact["assertion"]["subject"], {
            "kind": "companion.person", "ref": self.context.actor.subject.subject_id,
        })
        evidence = fact["evidence"][0]
        self.assertEqual(evidence["state"], "available")
        self.assertEqual(evidence["excerpt"], "private input 我不喝咖啡")
        self.assertEqual(recall["usage"]["evidence_chars"], len(evidence["excerpt"]))
        self.assertEqual(recall["usage"]["evidence_tokens"], len(evidence["excerpt"]))
        self.assertIsNone(recall["next_cursor"])

    def test_busy_cache_returns_unavailable_and_same_request_can_resume_after_release(self):
        fact = self.remember()
        with closing(sqlite3.connect(self.memory_service.query.index.path)) as other:
            other.execute("BEGIN IMMEDIATE")
            unavailable = self.wire.handle(self.context, self.request())
        self.assertEqual((unavailable["status"], unavailable["reason_code"]), ("unavailable", "memory_index_busy"))
        self.assertIsNone(unavailable["output"])
        result = self.wire.handle(self.context, self.request())
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["output"]["items"][0]["atom_id"], fact.atom_id)

    def test_scope_provider_and_unimplemented_query_features_are_not_trusted_or_silently_ignored(self):
        forged_scope = runtime_scope(self.context) | {"installation_id": "another-installation"}
        denied = self.wire.handle(self.context, self.request(scope=forged_scope))
        self.assertEqual((denied["status"], denied["reason_code"]), ("permission_denied", "scope_mismatch"))
        self.assertIsNone(denied["output"])

        wrong_provider = self.request()
        wrong_provider["provider_generation"] = "stale-generation"
        unavailable = self.wire.handle(self.context, wrong_provider)
        self.assertEqual((unavailable["status"], unavailable["reason_code"]),
                         ("unavailable", "provider_binding_mismatch"))

        with_pending = self.request(payload=self.request()["payload"] | {"include_pending": True})
        empty_pending = self.wire.handle(self.context, with_pending)
        self.assertEqual(empty_pending["status"], "succeeded")
        self.assertEqual(empty_pending["output"]["items"], [])

        unknown = self.request(payload=self.request()["payload"] | {"sql": "SELECT * FROM memory_atoms"})
        rejected = self.wire.handle(self.context, unknown)
        self.assertEqual((rejected["status"], rejected["reason_code"]), ("rejected", "invalid_payload"))

    def test_cursor_reuses_the_trace_bound_session_and_rejects_another_trace(self):
        base = replace(self.proposed(), single_value=False)
        self.remember(replace(base, predicate="饮用偏好", representation="不喝咖啡"), key="wire-one")
        self.remember(replace(base, predicate="颜色偏好", representation="喜欢蓝色"), key="wire-two")

        first = self.wire.handle(self.context, self.request())
        self.assertEqual(first["status"], "succeeded", first)
        cursor = first["output"]["next_cursor"]
        self.assertIsNotNone(cursor)
        next_payload = self.request()["payload"] | {"cursor": cursor}
        second = self.wire.handle(self.context, self.request(payload=next_payload, request_id="request-2"))
        self.assertEqual(second["status"], "succeeded", second)
        self.assertNotEqual(first["output"]["items"][0]["atom_id"], second["output"]["items"][0]["atom_id"])

        other_trace = self.wire.handle(self.context, self.request(payload=next_payload, trace_id="trace-2"))
        self.assertEqual((other_trace["status"], other_trace["reason_code"]), ("rejected", "cursor_invalid"))

    def test_effective_evidence_budget_returns_an_explicit_partial_excerpt(self):
        self.remember()
        payload = self.request()["payload"] | {
            "evidence_budget": {"max_items": 1, "max_chars": 4, "max_tokens": 4},
        }

        result = self.wire.handle(self.context, self.request(payload=payload))

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reason_code"], "evidence_budget_truncated")
        self.assertTrue(result["degraded"])
        fact = result["output"]["items"][0]
        self.assertEqual(fact["evidence"][0]["excerpt"], "priv")
        self.assertEqual(fact["missing"], ["evidence_budget_truncated"])

    def test_input_output_and_deadline_budgets_are_enforced(self):
        too_small_input = self.request(budget={"max_input_bytes": 1, "max_model_calls": 0})
        rejected = self.wire.handle(self.context, too_small_input)
        self.assertEqual((rejected["status"], rejected["reason_code"]),
                         ("rejected", "input_budget_exceeded"))

        self.remember()
        too_small_output = self.request(budget={"max_input_bytes": 16384, "max_model_calls": 0,
                                                "max_output_bytes": 1})
        output_rejected = self.wire.handle(self.context, too_small_output)
        self.assertEqual((output_rejected["status"], output_rejected["reason_code"]),
                         ("rejected", "output_budget_exceeded"))
        self.assertIsNone(output_rejected["output"])

        expired = self.request()
        expired["deadline_at"] = stamp(NOW - timedelta(seconds=1))
        timeout = self.wire.handle(self.context, expired)
        self.assertEqual((timeout["status"], timeout["reason_code"]), ("timeout", "deadline_expired"))

    def test_retention_and_confidence_filters_are_applied_before_recall(self):
        durable = replace(self.proposed(), predicate="preference.durable", confidence=0.9)
        temporary = replace(self.proposed(), predicate="preference.short", retention="short",
                            valid_to=NOW + timedelta(days=1), confidence=0.4)
        self.remember(durable, key="durable")
        self.remember(temporary, key="short")
        payload = self.request()["payload"] | {
            "allowed_retention": ["durable"],
            "confidence_floor": 0.8,
        }

        result = self.wire.handle(self.context, self.request(payload=payload))

        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual([item["assertion"]["predicate"] for item in result["output"]["items"]],
                         ["preference.durable"])

    def test_cold_index_returns_partial_with_a_usable_empty_page_cursor(self):
        base = replace(self.proposed(), single_value=False)
        for number in range(3):
            self.remember(replace(base, predicate="preference." + str(number)), key="seed-" + str(number))
        self.memory_service.query.fact_index.sync_items = 1
        first = self.wire.handle(self.context, self.request())
        self.assertEqual((first["status"], first["reason_code"]), ("partial", "memory_index_catching_up"))
        self.assertEqual(first["output"]["items"], [])
        self.assertEqual(first["output"]["coverage"][0]["status"], "partial")
        self.assertIsNotNone(first["output"]["next_cursor"])
        result, items = first, []
        while result["output"]["next_cursor"]:
            payload = self.request()["payload"] | {"cursor": result["output"]["next_cursor"]}
            result = self.wire.handle(self.context, self.request(request_id="continuation", payload=payload))
            self.assertIn(result["status"], ("partial", "succeeded"), result)
            items.extend(result["output"]["items"])
        self.assertEqual(len({item["atom_id"] for item in items}), 3)
        self.assertEqual(result["status"], "succeeded")

    def test_revoked_candidate_batch_reports_partial_without_hiding_later_matches(self):
        entries = []
        for number in range(2):
            proposal = replace(self.proposed(), predicate="preference." + str(number), single_value=False,
                               evidence=(self.evidence("separate-" + str(number)),))
            entries.append((self.remember(proposal, key=str(number)), proposal))
        entries.sort(key=lambda item: item[0].atom_id)
        # Empty intent is disallowed by wire, but identical matching text ranks
        # these equal-length facts by their stable identifiers.
        self.memory.sources.revoke(entries[0][1].evidence[0].source, expected_governance_revision=1,
                                   observed_at=self.clock.now()).unwrap()
        budget = self.request()["budget"] | {"max_candidates": 1}
        first = self.wire.handle(self.context, self.request(budget=budget))
        self.assertEqual((first["status"], first["reason_code"]), ("partial", "memory_candidates_pending"))
        self.assertEqual(first["output"]["items"], [])
        self.assertEqual(first["output"]["usage"]["candidates"], 1)
        payload = self.request()["payload"] | {"cursor": first["output"]["next_cursor"]}
        last = self.wire.handle(self.context, self.request(request_id="next", payload=payload, budget=budget))
        self.assertEqual(last["output"]["items"][0]["atom_id"], entries[1][0].atom_id)
        self.assertEqual(last["reason_code"], "memory_sources_incomplete")

    def test_scope_revision_types_and_error_correlation_stay_within_the_wire_contract(self):
        request = self.request()
        request["scope"]["persona_binding_revision"] = float(request["scope"]["persona_binding_revision"])
        result = self.wire.handle(self.context, request)
        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(result["output"])
        result = self.wire.handle(self.context, self.request(request_id="r" * 257, trace_id="t" * 257))
        self.assertEqual((result["request_id"], result["trace_id"]), ("invalid-request", "invalid-trace"))


if __name__ == "__main__":
    unittest.main()
