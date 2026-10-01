from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.memory.models import AtomRef, Proposal
from companion_v2.memory.writer import MemoryWriter
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord
from tests.memory_support import MemoryFixture
from tests.test_management_access import NOW


class MemoryWriterTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def test_open_vocabulary_idempotency_and_cas(self):
        item = self.proposed()
        ref = self.remember(item)
        self.assertEqual(self.remember(item), ref)
        self.assertEqual(self.memory.submit(self.context, replace(item, object="changed"), operation_key="save").failure.code,
                         "memory_operation_conflict")
        fixed = replace(item, operation="correct", target=ref, object="现在偶尔喝咖啡", representation="用户现在偶尔喝咖啡。",
                        evidence=(self.evidence("我现在偶尔喝咖啡了"),))
        result = self.memory.submit(self.context, fixed, operation_key="fix").unwrap()
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.memory.read(self.context, ref).failure.code, "memory_revision_conflict")
        self.assertEqual(self.memory.submit(self.context, fixed, operation_key="stale").failure.code, "memory_revision_conflict")
        self.assertEqual(self.memory.read(self.context, AtomRef(ref.atom_id, 2)).unwrap()["object"], "现在偶尔喝咖啡")
        self.assertEqual(self.memory.submit(self.context, item, operation_key="late").failure.code, "memory_corrected_evidence")

    def test_pending_is_not_active_and_source_revocation_prevents_commit(self):
        item = replace(self.proposed(), defer_until_boundary=True)
        receipt = self.memory.submit(self.context, item, operation_key="pending").unwrap()
        self.assertEqual(receipt["state"], "pending")
        self.assertEqual(self.query().unwrap()["items"], [])
        source = item.evidence[0].source
        self.memory.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(self.memory.commit_pending(self.context, receipt["operation_id"]).is_success)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_atoms", ())["n"], 0)

    def test_single_value_conflict_does_not_revoke_old_fact(self):
        item = self.proposed()
        ref = self.remember(item)
        different = replace(item, object="喝咖啡", representation="用户喜欢咖啡", evidence=(self.evidence("喜欢咖啡"),))
        self.assertEqual(self.memory.submit(self.context, different, operation_key="new").failure.code, "memory_fact_conflict")
        self.assertEqual(self.memory.read(self.context, ref).unwrap()["object"], "不喝咖啡")

    def test_source_withdrawal_invalidates_fact_and_dependent_role_material(self):
        item = self.proposed()
        ref = self.remember(item)
        from companion_v2.memory.codec import source
        fact_source = source(self.memory.read(self.context, ref).unwrap()["source"])
        derived = SourceRef("role-impression", "role", self.context.scope, VersionRef("impression", 1), NOW)
        self.memory.sources.publish(SourceRecord(derived, self.context.audience, digest("印象"), "印象"), observed_at=NOW).unwrap()
        link(self.runtime, derived, (fact_source,), NOW)
        self.memory.sources.revoke(item.evidence[0].source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(self.memory.read(self.context, ref).is_success)
        self.assertFalse(self.memory.sources.validate_reference(derived, observed_at=NOW).is_success)
        self.assertEqual(self.query().unwrap()["items"], [])

    def test_logical_forgetting_survives_restart_and_blocks_old_evidence(self):
        item = self.proposed()
        ref = self.remember(item)
        evidence = (self.evidence("忘记我的饮用偏好"),)
        result = self.memory.forget(self.context, ref, evidence=evidence, operation_key="forget").unwrap()
        self.assertEqual(result["forgetting"], "logical")
        self.assertEqual(self.memory.forget(self.context, ref, evidence=evidence, operation_key="forget").unwrap(), result)
        tasks, _, _ = self.components(self.open_runtime())
        reopened = MemoryWriter(tasks)
        self.assertEqual(reopened.submit(self.context, item, operation_key="resurrect").failure.code, "memory_evidence_forgotten")
        self.assertNotIn("咖啡", self.runtime.read_one("SELECT record_json FROM memory_atoms", ())["record_json"])
        self.assertEqual(self.query().unwrap()["items"], [])

    def test_user_attribution_requires_captured_human_source(self):
        item = self.proposed()
        forged = replace(item, evidence=(replace(item.evidence[0], speaker_id=None, source_kind="bot_message"),))
        self.assertEqual(self.memory.submit(self.context, forged, operation_key="bot").failure.code, "memory_attribution_unproven")
        mentioned = replace(item, subject="entity:source-1:小明", attribution="third_party", single_value=False)
        result = self.memory.submit(self.context, mentioned, operation_key="reported").unwrap()
        self.assertEqual(self.memory.read(self.context, AtomRef(result["atom_id"], 1)).unwrap()["attribution"], "third_party")

    def test_short_expiry_and_protected_permission(self):
        item = replace(self.proposed(), retention="short", valid_to=NOW + timedelta(seconds=2))
        ref = self.remember(item)
        self.clock.advance(timedelta(seconds=3))
        self.assertEqual(self.memory.read(self.context, ref).failure.code, "memory_expired")

    def test_dependency_cycle_is_rejected(self):
        item = self.proposed()
        original = item.evidence[0].source
        with self.assertRaisesRegex(ValueError, "support itself"):
            link(self.runtime, original, (original,), NOW)
