"""Memory archive and portable bundle contracts.

Idle eligibility, bundle validation and archive-token stability are pure logic
and are checked directly here. The preview/commit paths that need a live memory
service are exercised by their own host-level tests.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.foundation.refs import AudienceRef
from companion_v2.foundation.outcome import Outcome
from tests.test_management_access import SCOPE, ManagementFixture
from companion_v2.memory.archive import (BUNDLE_FORMAT, DEFAULT_IDLE_DAYS, MAX_BUNDLE_ATOMS,
    ArchiveDecision, MemoryArchive, _idle_days)
from companion_v2.memory.service import MemoryService
from tests.memory_support import MemoryFixture


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class IdleDaysTests(unittest.TestCase):
    def test_accepts_bounded_values(self):
        for value in (1, DEFAULT_IDLE_DAYS, 3650):
            self.assertEqual(_idle_days(value), value)

    def test_rejects_out_of_range_and_non_integers(self):
        for value in (0, -1, 3651, True, "180", None):
            with self.assertRaises((TaskError, ValueError)):
                _idle_days(value)


class EligibilityTests(unittest.TestCase):
    """_eligible is pure given rows, so it can be exercised without a database."""

    ARCHIVE = MemoryArchive.__new__(MemoryArchive)

    def rows(self, **overrides):
        # memory_atoms stores retention inside the proposal document, never as a
        # column, so the fixture has to nest it the way the writer does. no_op is
        # the one operation that needs no evidence, which keeps the fixture honest
        # while still exercising the retention branch.
        proposal = {"operation": "no_op", "namespace": "personal", "subject": "self",
                    "predicate": "喜欢", "object": "雨天", "representation": "喜欢雨天",
                    "retention": overrides.pop("retention", "durable"), "confidence": 1.0}
        record = {"proposal": proposal, "observed_at": NOW.isoformat(),
                  "forgotten": overrides.pop("forgotten", False)}
        if overrides.pop("archived", False):
            record["archive"] = {"state": "archived", "at": NOW.isoformat()}
        return {"atom_id": overrides.pop("atom_id", "a1"), "revision": 1,
                "namespace": "personal", "state": overrides.pop("state", "active"),
                "record_json": json.dumps(record),
                "updated_at": overrides.pop("updated_at", (NOW - timedelta(days=400)).isoformat())}

    def eligible(self, rows, *, idle_days=DEFAULT_IDLE_DAYS):
        return self.ARCHIVE._eligible(None, rows, NOW, idle_days)

    def test_selects_idle_durable_records(self):
        decisions = self.eligible([self.rows()])
        self.assertEqual([item.atom_id for item in decisions], ["a1"])
        self.assertEqual(decisions[0].reason, "idle_durable")

    def test_skips_recent_records(self):
        self.assertEqual(self.eligible([self.rows(updated_at=NOW.isoformat())]), [])

    def test_skips_non_durable_retention(self):
        for retention in ("session", "short", "protected"):
            self.assertEqual(self.eligible([self.rows(retention=retention)]), [])

    def test_skips_forgotten_and_already_archived(self):
        self.assertEqual(self.eligible([self.rows(forgotten=True)]), [])
        self.assertEqual(self.eligible([self.rows(archived=True)]), [])

    def test_skips_naive_timestamps(self):
        self.assertEqual(self.eligible([self.rows(updated_at=NOW.replace(tzinfo=None).isoformat())]), [])

    def test_skips_records_whose_proposal_is_missing_or_malformed(self):
        """A record with no readable proposal is skipped, never fatal."""
        for record in ({}, {"proposal": None}, {"proposal": "x"}, {"proposal": {"retention": "durable"}}):
            row = self.rows()
            row["record_json"] = json.dumps(record)
            self.assertEqual(self.eligible([row]), [], record)

    def test_retention_comes_from_the_proposal_not_a_column(self):
        """Retention is never a memory_atoms column; a stray one must be ignored."""
        row = self.rows(retention="durable")
        row["retention"] = "session"
        self.assertEqual([item.atom_id for item in self.eligible([row])], ["a1"])

    def test_carries_the_row_state_through_to_the_decision(self):
        decisions = self.eligible([self.rows(state="active")])
        self.assertEqual(decisions[0].state, "active")

    def test_idle_window_widens_the_set(self):
        recent = self.rows(updated_at=(NOW - timedelta(days=100)).isoformat())
        self.assertEqual(self.eligible([recent], idle_days=180), [])
        self.assertEqual(len(self.eligible([recent], idle_days=30)), 1)


class ArchiveTokenTests(ManagementFixture):
    """_token binds a decision set to one owner, so it needs a real task context."""

    def token(self, decisions, idle_days=DEFAULT_IDLE_DAYS):
        # owner_key derives from the full TaskContext, so a bare string cannot stand
        # in for it: the fixture must carry the same scope the caller would have.
        context = TaskContext(self.core, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                              AudienceRef(SCOPE, (self.core.subject,)))
        archive = MemoryArchive.__new__(MemoryArchive)
        archive.operator = self.core
        return archive._token(context, decisions, idle_days)

    def test_token_is_stable_and_covers_the_idle_window(self):
        decisions = [ArchiveDecision("a1", 1, "active", NOW, "idle_durable")]
        self.assertEqual(self.token(decisions), self.token(decisions))
        self.assertNotEqual(self.token(decisions), self.token(decisions, idle_days=30))

    def test_token_changes_with_revision_and_membership(self):
        base = [ArchiveDecision("a1", 1, "active", NOW, "idle_durable")]
        bumped = [ArchiveDecision("a1", 2, "active", NOW, "idle_durable")]
        extra = base + [ArchiveDecision("a2", 1, "active", NOW, "idle_durable")]
        self.assertNotEqual(self.token(base), self.token(bumped))
        self.assertNotEqual(self.token(base), self.token(extra))


class ArchivePreviewLabelsTests(unittest.TestCase):
    def test_labels_use_the_authorized_read_and_hide_unavailable_content(self):
        archive = MemoryArchive.__new__(MemoryArchive)
        reader = Mock(return_value=Outcome.success({"predicate": "饮用偏好", "representation": "喜欢茶" * 100}))
        archive.writer = SimpleNamespace(read=reader)
        context = object()
        display = archive._preview_labels(context, "atom-internal", 4)
        self.assertEqual(display["predicate"], "饮用偏好")
        self.assertEqual(len(display["representation"]), 240)
        args = reader.call_args.args
        self.assertIs(args[0], context)
        self.assertEqual((args[1].atom_id, args[1].revision), ("atom-internal", 4))
        reader.return_value = Outcome.failed("source_revoked", "internal source detail")
        self.assertEqual(archive._preview_labels(context, "atom-internal", 4), {"unavailable_reason": "source_revoked"})


class ArchivePreviewWorkflowTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.archive = MemoryArchive(MemoryService(self.tasks), self.core)

    def test_preview_labels_follow_the_original_record_through_archive_and_restore(self):
        ref = self.remember(replace(self.proposed(), retention="durable"))
        self.clock.advance(timedelta(days=DEFAULT_IDLE_DAYS + 1))
        preview = self.archive.preview(context=self.context).unwrap()
        self.assertEqual(preview["counts"]["eligible"], 1)
        self.assertEqual(preview["items"][0]["atom_id"], ref.atom_id)
        self.assertEqual(preview["items"][0]["predicate"], "饮用偏好")
        self.archive.commit(context=self.context, expected_archive_token=preview["archive_token"],
                            operation_key="archive").unwrap()
        archived = self.archive.preview(context=self.context).unwrap()
        self.assertEqual(archived["counts"]["eligible"], 0)
        self.assertEqual(archived["archived_items"][0]["atom_id"], ref.atom_id)
        self.assertEqual(archived["archived_items"][0]["representation"], "用户说自己不喝咖啡。")
        result = self.archive.restore(context=self.context, atom_ids=(ref.atom_id,), operation_key="restore").unwrap()
        self.assertEqual(result["items"], [{"atom_id": ref.atom_id, "revision": ref.revision}])
        self.assertEqual(self.archive.restore(context=self.context, atom_ids=(ref.atom_id,), operation_key="restore").unwrap(), result)
        conflict = self.archive.restore(context=self.context, atom_ids=("another-atom",), operation_key="restore")
        self.assertEqual(conflict.failure.code, "memory_operation_conflict")
        self.assertEqual(self.archive.preview(context=self.context).unwrap()["archived_items"], [])

    def test_revoked_evidence_cannot_leak_content_into_archived_labels(self):
        proposal = replace(self.proposed(), retention="durable")
        self.remember(proposal)
        self.clock.advance(timedelta(days=DEFAULT_IDLE_DAYS + 1))
        preview = self.archive.preview(context=self.context).unwrap()
        self.archive.commit(context=self.context, expected_archive_token=preview["archive_token"],
                            operation_key="archive").unwrap()
        self.memory.sources.revoke(proposal.evidence[0].source, expected_governance_revision=1,
                                   observed_at=self.clock.now()).unwrap()
        item = self.archive.preview(context=self.context).unwrap()["archived_items"][0]
        self.assertIn("unavailable_reason", item)
        self.assertNotIn("representation", item)
        self.assertNotIn("predicate", item)

class BundleValidationTests(unittest.TestCase):
    ARCHIVE = MemoryArchive.__new__(MemoryArchive)

    def bundle(self, atoms=None, **overrides):
        atoms = atoms if atoms is not None else [{"atom_id": "i1", "predicate": "喜欢"}]
        value = {"format": BUNDLE_FORMAT, "atom_count": len(atoms), "atoms": atoms}
        value.update(overrides)
        return value

    def test_accepts_a_well_formed_bundle(self):
        atoms = self.ARCHIVE._validate_bundle(self.bundle(), None)
        self.assertEqual(len(atoms), 1)

    def test_rejects_unknown_format(self):
        with self.assertRaises(TaskError) as caught:
            self.ARCHIVE._validate_bundle(self.bundle(format="other.v9"), None)
        self.assertEqual(caught.exception.code, "memory_bundle_invalid")

    def test_rejects_missing_atoms(self):
        for value in ({"format": BUNDLE_FORMAT}, {"format": BUNDLE_FORMAT, "atoms": "x"}):
            with self.assertRaises(TaskError):
                self.ARCHIVE._validate_bundle(value, None)

    def test_rejects_empty_and_oversized_bundles(self):
        with self.assertRaises(TaskError):
            self.ARCHIVE._validate_bundle(self.bundle(atoms=[]), None)
        with self.assertRaises(TaskError):
            self.ARCHIVE._validate_bundle(
                self.bundle(atoms=[{"atom_id": f"i{index}"} for index in range(MAX_BUNDLE_ATOMS + 1)]), None)

    def test_rejects_malformed_atoms(self):
        for atom in ({}, {"atom_id": ""}, {"atom_id": "  "}, {"atom_id": "a" * 513},
                     {"atom_id": 7}, "not-a-record"):
            with self.assertRaises(TaskError):
                self.ARCHIVE._validate_bundle(self.bundle(atoms=[atom]), None)

    def test_atom_ids_are_returned_in_bundle_order(self):
        atoms = self.ARCHIVE._validate_bundle(
            self.bundle(atoms=[{"atom_id": "b"}, {"atom_id": "a"}]), None)
        self.assertEqual([item["atom_id"] for item in atoms], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
