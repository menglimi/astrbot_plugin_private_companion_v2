from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from companion_v2.agenda.models import AgendaError, AgendaTarget, Frequency, GapPolicy, MemoCursor, Schedule
from companion_v2.agenda.service import AgendaService
from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2028, 1, 31, 1, tzinfo=timezone.utc)
INSTALLATION = "agenda-installation"
PRINCIPAL = AuthenticatedHostPrincipal(INSTALLATION, "host-a", "onebot", "account-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-a")
TARGET = AgendaTarget(SCOPE, ROLE, USER)
ACTIONS = (
    "memo.create", "memo.read", "memo.list", "memo.edit", "memo.complete", "memo.reopen", "memo.pin",
    "memo.unpin", "memo.delete", "memo.delete.commit", "memo.reminder.set", "reminder.create", "reminder.reschedule",
    "reminder.cancel", "reminder.read", "reminder.list", "reminder.deliver", "operation.lookup",
)


class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-agenda-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.runtime = self.open_runtime()
        self.service = AgendaService(self.runtime)
        self.identity = self.service.identity
        self.identity.bind(binding_id="binding-a", principal=PRINCIPAL, subject=USER, valid_from=NOW,
                           expected_revision=self.identity.revision)
        for action in ACTIONS:
            self.identity.issue_grant(grant_id=action, subject=USER, scope=SCOPE, capability=action,
                                      tier=AuthorizationTier.STANDARD, valid_from=NOW,
                                      expected_revision=self.identity.revision)
        self.identity.bind_role(scope=SCOPE, role=ROLE, expected_revision=0)
        self.actor = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.operation_sequence = 0

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def op(self, name=None):
        self.operation_sequence += 1
        name = name or f"operation-{self.operation_sequence}"
        return OperationRef(name, "agenda", SCOPE, VersionRef(name, 1), name)

    def create(self, *, memo_id="memo-a", title="喝水计划", body="只记录，不默认设置提醒", schedule=None,
               purpose="open_loop", observed_at=NOW, operation=None):
        return self.service.create_memo(self.actor, target=TARGET, memo_id=memo_id, title=title, body=body,
                                        schedule=schedule, purpose=purpose, operation=operation or self.op(),
                                        expected_role_revision=1, observed_at=observed_at)

    def change(self, action, *, memo_id="memo-a", revision=1, changes=None, observed_at=NOW, operation=None):
        return self.service.change_memo(self.actor, target=TARGET, memo_id=memo_id, action=action,
                                        expected_revision=revision, expected_role_revision=1, operation=operation or self.op(),
                                        changes=changes, observed_at=observed_at)

    def remind(self, *, reminder_id="reminder-a", memo_id=None, schedule=None, operation=None):
        return self.service.create_reminder(self.actor, target=TARGET, reminder_id=reminder_id,
                                            memo_id=memo_id, expected_memo_revision=1 if memo_id else None,
                                            schedule=schedule if memo_id else (schedule or Schedule(NOW, "Asia/Shanghai")),
                                            message="喝点水吧" if not memo_id else "", operation=operation or self.op(),
                                            expected_role_revision=1, observed_at=NOW)

    def reminder_change(self, action, *, revision=1, schedule=None, memo_revision=None, operation=None):
        return self.service.change_reminder(self.actor, target=TARGET, reminder_id="reminder-a", action=action,
                                            expected_revision=revision, expected_role_revision=1, operation=operation or self.op(),
                                            schedule=schedule, expected_memo_revision=memo_revision, observed_at=NOW)

    def memo(self):
        return self.service.read_memo(self.actor, target=TARGET, memo_id="memo-a", observed_at=NOW).unwrap()

    def due_claim(self, now=NOW):
        page = self.service.due(observed_at=now)
        self.assertTrue(page.occurrence_ids)
        return self.service.accept_due(page.occurrence_ids[0], observed_at=now).unwrap()

    def test_memo_without_reminder_and_standalone_reminder_have_separate_receipts(self):
        memo_receipt = self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.assertEqual(memo_receipt.scheduling, "not_requested")
        self.assertEqual(self.service.due(observed_at=NOW).occurrence_ids, ())
        reminder_receipt = self.remind().unwrap()
        self.assertEqual(reminder_receipt.scheduling, "local_registered")
        prepared = self.service.prepare_local(self.due_claim(), observed_at=NOW).unwrap()
        self.assertEqual(prepared.recipient, USER)
        self.assertEqual(prepared.message, "喝点水吧")
        self.assertEqual(prepared.delivery, "not_started")
        self.assertEqual(self.runtime.read_all("SELECT * FROM outbox", ()), ())
        self.assertEqual(len(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW).unwrap()), 1)

    def test_open_loops_expire_and_explicit_reopen_starts_a_new_lifetime(self):
        memo = self.create().unwrap()
        original = self.memo()
        self.assertEqual(original.expires_at, NOW + timedelta(days=30))
        expired_at = original.expires_at + timedelta(seconds=1)
        self.assertTrue(original.expired(expired_at))
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=expired_at,
            state="active", purpose="open_loop", include_expired=True).unwrap()[0].memo_id, memo.object_id)
        self.change("edit", changes={"body": "稍后继续"}, observed_at=NOW + timedelta(days=29))
        self.assertEqual(self.memo().expires_at, original.expires_at)
        reopened = self.change("reopen", revision=2, observed_at=expired_at).unwrap()
        self.assertEqual(reopened.revision, 3)
        current = self.service.read_memo(self.actor, target=TARGET, memo_id=memo.object_id,
                                         observed_at=expired_at).unwrap()
        self.assertFalse(current.expired(expired_at))
        self.assertEqual(current.expires_at, expired_at + timedelta(days=30))

    def test_ordinary_note_is_not_an_open_loop_and_due_window_is_bounded(self):
        self.create(purpose="note").unwrap()
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW,
            state="active", purpose="open_loop").unwrap(), ())
        scheduled = self.create(memo_id="scheduled-loop", purpose="open_loop",
            schedule=Schedule(NOW + timedelta(days=5), "Asia/Shanghai"), operation=self.op()).unwrap()
        memo = self.service.read_memo(self.actor, target=TARGET, memo_id=scheduled.object_id,
                                      observed_at=NOW).unwrap()
        self.assertEqual(memo.expires_at, NOW + timedelta(days=12))

    def test_default_and_legacy_memos_remain_notes(self):
        name = "implicit-note"
        receipt = self.service.create_memo(self.actor, target=TARGET, memo_id=name, title="随手记",
            body="普通备忘", operation=self.op(), expected_role_revision=1, observed_at=NOW).unwrap()
        row = self.runtime.read_one("SELECT record_json FROM agenda_memos WHERE memo_id = ?", (name,))
        record = json.loads(row["record_json"])
        record.pop("purpose")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE agenda_memos SET record_json = ? WHERE memo_id = ?",
                               (json.dumps(record, ensure_ascii=False), name))
        restored = self.service.repository.memo(receipt.object_id)
        self.assertEqual(restored.purpose, "note")
        self.assertIsNone(restored.expires_at)
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW,
            state="active", purpose="open_loop").unwrap(), ())

    def test_expired_rows_do_not_starve_a_page_of_active_open_loops(self):
        expired_ids = [f"a-expired-{index}" for index in range(4)]
        for memo_id in expired_ids:
            self.create(memo_id=memo_id, operation=self.op()).unwrap()
            row = self.runtime.read_one("SELECT record_json FROM agenda_memos WHERE memo_id = ?", (memo_id,))
            record = json.loads(row["record_json"])
            record["expires_at"] = (NOW - timedelta(days=1)).isoformat()
            with self.runtime.transaction() as connection:
                connection.execute("UPDATE agenda_memos SET record_json = ? WHERE memo_id = ?",
                                   (json.dumps(record, ensure_ascii=False), memo_id))
        for memo_id in ("z-active-a", "z-active-b", "z-active-c"):
            self.create(memo_id=memo_id, operation=self.op()).unwrap()
        page = self.service.list_memos(self.actor, target=TARGET, observed_at=NOW,
            limit=2, state="active", purpose="open_loop").unwrap()
        self.assertEqual([memo.memo_id for memo in page], ["z-active-a", "z-active-b"])

    def test_lost_create_response_and_lookup_replay_original_result_after_new_edit(self):
        operation = self.op()
        original = self.create(operation=operation).unwrap()
        self.change("edit", changes={"body": "新正文"}).unwrap()
        replay = self.create(operation=operation).unwrap()
        lookup = self.service.receipt(self.actor, target=TARGET, operation_id=operation.operation_id, observed_at=NOW).unwrap()
        self.assertEqual(replay.revision, original.revision)
        self.assertEqual(lookup, replay)
        self.assertTrue(replay.replayed)
        self.assertEqual(self.memo().body, "新正文")
        self.assertEqual(self.create(operation=operation, body="不同请求").failure.code, "idempotency_key_conflict")

    def test_partial_patch_preserves_schedule_and_explicit_empty_body(self):
        schedule = Schedule(NOW, "Asia/Shanghai", Frequency.MONTHLY)
        self.create(schedule=schedule).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        self.change("edit", changes={"body": ""}).unwrap()
        memo = self.memo()
        self.assertEqual(memo.body, "")
        self.assertEqual(memo.schedule, schedule)
        self.assertEqual(memo.creator.subject, USER)
        reminder = self.service.read_reminder(self.actor, target=TARGET, reminder_id="reminder-a", observed_at=NOW).unwrap()
        self.assertEqual(reminder.memo_id, "memo-a")
        self.assertEqual(self.change("edit", revision=2, changes={"unrecognized": False}).failure.code, "invalid_agenda_patch")
        self.assertEqual(self.memo().revision, 2)

    def test_missing_memo_update_never_creates_and_cross_owner_ids_are_not_readable(self):
        self.assertEqual(self.change("edit").failure.code, "agenda_object_not_found")
        self.assertEqual(self.runtime.read_all("SELECT * FROM agenda_memos", ()), ())
        self.create().unwrap()
        other = replace(TARGET, owner=SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-b"))
        result = self.service.read_memo(self.actor, target=other, memo_id="memo-a", observed_at=NOW)
        self.assertEqual(result.failure.code, "agenda_object_not_found")
        other_role = replace(TARGET, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b"))
        self.assertEqual(self.service.read_memo(self.actor, target=other_role, memo_id="memo-a", observed_at=NOW).failure.code,
                         "role_binding_changed")

    def test_month_end_completion_retries_advance_one_period_only(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.MONTHLY, count=3)).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        claim = self.due_claim()
        operation = self.op()
        self.change("complete", operation=operation).unwrap()
        self.assertTrue(self.change("complete", operation=operation).unwrap().replayed)
        memo = self.memo()
        self.assertEqual((memo.sequence, memo.completion_count), (1, 1))
        self.assertEqual(memo.schedule.at(memo.sequence), datetime(2028, 2, 29, 1, tzinfo=timezone.utc))
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).failure.code, "occurrence_superseded")
        self.change("complete", revision=2).unwrap()
        self.assertEqual(self.memo().schedule.at(self.memo().sequence).day, 31)
        self.change("complete", revision=3).unwrap()
        self.assertEqual(self.memo().state, "completed")
        self.assertEqual(self.service.repository.linked_reminder("memo-a").state, "cancelled")

    def test_two_connections_stale_completion_cannot_advance_again(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.DAILY)).unwrap()
        other = AgendaService(self.open_runtime())
        self.change("complete").unwrap()
        result = other.change_memo(self.actor, target=TARGET, memo_id="memo-a", action="complete", expected_revision=1,
                                   expected_role_revision=1, operation=self.op(), observed_at=NOW)
        self.assertEqual(result.failure.code, "agenda_revision_conflict")
        self.assertEqual(self.memo().completion_count, 1)

    def test_unchanged_schedule_in_edit_does_not_rewind_completed_occurrence(self):
        schedule = Schedule(NOW, "Asia/Shanghai", Frequency.MONTHLY)
        self.create(schedule=schedule).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        self.change("complete").unwrap()
        rows_before = [tuple(row) for row in self.runtime.read_all("SELECT * FROM agenda_occurrences", ())]
        result = self.change("edit", revision=2, changes={"schedule": schedule}).unwrap()
        self.assertEqual(result.revision, 2)
        self.assertEqual(rows_before, [tuple(row) for row in self.runtime.read_all("SELECT * FROM agenda_occurrences", ())])
        self.change("edit", revision=2, changes={"schedule": schedule, "body": "只修改正文"}).unwrap()
        self.assertEqual((self.memo().sequence, self.memo().completion_count), (1, 1))
        self.assertEqual(self.service.repository.linked_reminder("memo-a").revision, 2)
        self.assertEqual(self.service.due(observed_at=NOW).occurrence_ids, ())

    def test_reschedule_fences_old_claim_and_updates_linked_memo_atomically(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        old = self.due_claim()
        future = Schedule(NOW + timedelta(hours=2), "Asia/Shanghai")
        self.reminder_change("reschedule", schedule=future, memo_revision=1).unwrap()
        self.assertEqual(self.memo().schedule, future)
        self.assertEqual(self.service.prepare_local(old, observed_at=NOW).failure.code, "occurrence_superseded")
        self.assertEqual(self.service.due(observed_at=NOW).occurrence_ids, ())
        result = self.service.prepare_local(self.due_claim(NOW + timedelta(hours=2)), observed_at=NOW + timedelta(hours=2)).unwrap()
        self.assertEqual(result.due_at, future.anchor)

    def test_cancel_after_preparation_invalidates_handoff_and_keeps_original_result(self):
        self.remind().unwrap()
        claim = self.due_claim()
        prepared = self.service.prepare_local(claim, observed_at=NOW).unwrap()
        operation = self.op()
        receipt = self.reminder_change("cancel", operation=operation).unwrap()
        self.assertEqual(receipt.scheduling, "local_cancelled")
        self.assertEqual(self.service.validate_preparation(prepared.occurrence_id, observed_at=NOW).failure.code, "occurrence_superseded")
        self.assertTrue(self.reminder_change("cancel", operation=operation).unwrap().replayed)
        self.assertEqual(self.service.due(observed_at=NOW).occurrence_ids, ())

    def test_reopen_does_not_restore_cancelled_reminder_without_explicit_reschedule(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        self.change("complete").unwrap()
        self.change("reopen", revision=2).unwrap()
        self.assertEqual(self.memo().state, "active")
        self.assertEqual(self.service.repository.linked_reminder("memo-a").state, "cancelled")
        self.assertEqual(self.service.due(observed_at=NOW).occurrence_ids, ())
        self.reminder_change("reschedule", revision=2, schedule=Schedule(NOW, "Asia/Shanghai"), memo_revision=3).unwrap()
        self.assertTrue(self.service.due(observed_at=NOW).occurrence_ids)

    def test_clear_due_and_delete_cancel_pending_work_and_keep_metadata_receipts(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        claim = self.due_claim()
        self.service.prepare_local(claim, observed_at=NOW).unwrap()
        self.change("edit", changes={"schedule": None}).unwrap()
        self.assertIsNone(self.memo().schedule)
        self.assertEqual(self.service.repository.linked_reminder("memo-a").state, "cancelled")
        operation = self.op()
        self.change("delete", revision=2, operation=operation).unwrap()
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW).unwrap(), ())
        self.assertTrue(self.change("delete", revision=2, operation=operation).unwrap().replayed)
        self.assertEqual(self.service.repository.memo("memo-a").title, "")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) AS n FROM agenda_occurrences WHERE prepared_json IS NOT NULL", ())["n"], 0)
        self.assertEqual(self.change("reopen", revision=3).failure.code, "agenda_object_not_found")

    def test_pin_only_changes_ordering_and_leaves_accepted_preparation_valid(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        claim = self.due_claim()
        self.change("pin").unwrap()
        prepared = self.service.prepare_local(claim, observed_at=NOW).unwrap()
        self.change("unpin", revision=2).unwrap()
        self.assertEqual(self.service.validate_preparation(claim.occurrence_id, observed_at=NOW).unwrap(), prepared)
        self.assertEqual(self.service.repository.linked_reminder("memo-a").revision, 1)

    def test_prepared_old_body_cannot_be_read_after_content_edit(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        claim = self.due_claim()
        self.service.prepare_local(claim, observed_at=NOW).unwrap()
        self.change("edit", changes={"body": "修订后的正文"}).unwrap()
        self.assertEqual(self.service.validate_preparation(claim.occurrence_id, observed_at=NOW).failure.code, "preparation_unavailable")
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).failure.code, "agenda_revision_conflict")
        new_claim = self.due_claim()
        self.assertEqual(new_claim.occurrence_id, claim.occurrence_id)
        self.assertIn("修订后的正文", self.service.prepare_local(new_claim, observed_at=NOW).unwrap().message)
        self.assertEqual(self.service.repository.linked_reminder("memo-a").revision, 1)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_occurrences", ())), 1)

    def test_revocation_is_rechecked_at_claim_preparation_and_lookup(self):
        self.remind().unwrap()
        claim = self.due_claim()
        self.identity.revoke_grant("reminder.deliver", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).failure.code, "authorization_revoked")
        self.assertEqual(self.service.accept_due(claim.occurrence_id, observed_at=NOW).failure.code, "authorization_revoked")
        self.identity.revoke_grant("operation.lookup", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.service.receipt(self.actor, target=TARGET, operation_id="operation-1", observed_at=NOW).failure.code,
                         "authorization_revoked")

    def test_account_and_role_binding_changes_do_not_retarget_existing_work(self):
        self.remind().unwrap()
        claim = self.due_claim()
        other_role = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b")
        self.identity.bind_role(scope=SCOPE, role=other_role, expected_revision=1)
        self.identity.bind_role(scope=SCOPE, role=ROLE, expected_revision=2)
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).failure.code, "role_binding_changed")
        self.assertEqual(self.create().failure.code, "role_binding_changed")
        self.identity.bind(binding_id="binding-b", principal=PRINCIPAL,
                           subject=SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-b"), valid_from=NOW,
                           expected_revision=self.identity.revision)
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).failure.code, "binding_rebound")

    def test_expired_grant_blocks_due_and_prepared_payload(self):
        self.remind().unwrap()
        claim = self.due_claim()
        self.service.prepare_local(claim, observed_at=NOW).unwrap()
        self.identity.revoke_grant("reminder.deliver", revoked_at=NOW, expected_revision=self.identity.revision)
        self.identity.issue_grant(grant_id="short-deliver", subject=USER, scope=SCOPE, capability="reminder.deliver",
                                  tier=AuthorizationTier.STANDARD, valid_from=NOW, expires_at=NOW + timedelta(seconds=1),
                                  expected_revision=self.identity.revision)
        self.assertTrue(self.service.validate_preparation(claim.occurrence_id, observed_at=NOW).is_success)
        self.assertFalse(self.service.validate_preparation(claim.occurrence_id, observed_at=NOW + timedelta(seconds=1)).is_success)

    def test_failure_rolls_back_memo_schedule_result_and_operation_together(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.DAILY)).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        before = [tuple(row) for row in self.runtime.read_all("SELECT * FROM agenda_occurrences", ())]
        operation = self.op()
        with patch.object(self.service.operations, "transition", side_effect=sqlite3.OperationalError("synthetic commit failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.change("complete", operation=operation)
        self.assertEqual(self.memo().completion_count, 0)
        self.assertEqual(self.service.repository.linked_reminder("memo-a").revision, 1)
        self.assertEqual([tuple(row) for row in self.runtime.read_all("SELECT * FROM agenda_occurrences", ())], before)
        self.assertIsNone(self.runtime.read_one("SELECT * FROM operations WHERE operation_id = ?", (operation.operation_id,)))
        self.change("complete", operation=operation).unwrap()

    def test_duplicate_link_and_invalid_fields_do_not_leave_reserved_operations(self):
        self.create(schedule=Schedule(NOW, "Asia/Shanghai")).unwrap()
        self.remind(memo_id="memo-a").unwrap()
        count = len(self.runtime.read_all("SELECT * FROM operations", ()))
        self.assertEqual(self.remind(reminder_id="second", memo_id="memo-a").failure.code, "reminder_already_linked")
        self.assertFalse(self.change("edit", changes={"title": "", "body": "must not save"}).is_success)
        self.assertFalse(self.change("edit", changes={"schedule": "tomorrow"}).is_success)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM operations", ())), count)
        self.assertEqual(self.memo().body, "只记录，不默认设置提醒")

    def test_due_scan_cursor_moves_past_unauthorized_item_without_leaking_content(self):
        for number in range(3):
            self.remind(reminder_id=f"reminder-{number}").unwrap()
        first = self.service.due(observed_at=NOW, limit=1)
        self.identity.revoke_grant("reminder.deliver", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertFalse(self.service.accept_due(first.occurrence_ids[0], observed_at=NOW).is_success)
        second = self.service.due(observed_at=NOW, limit=1, after=first.next_cursor)
        third = self.service.due(observed_at=NOW, limit=1, after=second.next_cursor)
        self.assertEqual(len(set(first.occurrence_ids + second.occurrence_ids + third.occurrence_ids)), 3)
        self.assertIsNone(third.next_cursor)
        self.assertEqual(self.service.due(observed_at=NOW - timedelta(seconds=1)).occurrence_ids, ())
        with self.assertRaises(AgendaError):
            self.service.due(observed_at=NOW, limit=0)

    def test_local_recurrence_and_repeated_prepare_only_register_next_once(self):
        self.remind(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.DAILY, count=2)).unwrap()
        claim = self.due_claim()
        prepared = self.service.prepare_local(claim, observed_at=NOW).unwrap()
        self.assertEqual(prepared.continuation, "next_registered")
        self.assertEqual(self.service.prepare_local(claim, observed_at=NOW).unwrap(), prepared)
        self.assertEqual(self.service.accept_due(claim.occurrence_id, observed_at=NOW).unwrap(), claim)
        tomorrow = NOW + timedelta(days=1)
        last = self.service.prepare_local(self.due_claim(tomorrow), observed_at=tomorrow).unwrap()
        self.assertEqual(last.continuation, "finished")
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_occurrences", ())), 2)

    def test_two_workers_share_one_local_claim_and_one_next_occurrence(self):
        self.remind(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.DAILY, count=2)).unwrap()
        first_claim = self.due_claim()
        other = AgendaService(self.open_runtime())
        second_claim = other.accept_due(first_claim.occurrence_id, observed_at=NOW).unwrap()
        self.assertEqual(first_claim, second_claim)
        first = self.service.prepare_local(first_claim, observed_at=NOW).unwrap()
        second = other.prepare_local(second_claim, observed_at=NOW).unwrap()
        self.assertEqual(first, second)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_occurrences", ())), 2)

    def test_dst_gap_preserves_current_preparation_and_reports_unresolved_next_time(self):
        zone = ZoneInfo("America/New_York")
        anchor = datetime(2028, 3, 11, 2, 30, tzinfo=zone)
        schedule = Schedule(anchor, zone.key, Frequency.DAILY)
        self.remind(schedule=schedule).unwrap()
        claim = self.due_claim(anchor)
        prepared = self.service.prepare_local(claim, observed_at=anchor).unwrap()
        self.assertEqual(prepared.continuation, "schedule_needs_resolution")
        self.assertEqual(prepared.delivery, "not_started")
        self.assertEqual(self.service.prepare_local(claim, observed_at=anchor).unwrap(), prepared)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM agenda_occurrences", ())), 1)

    def test_list_filters_owner_before_pagination_search_and_rechecks_permissions(self):
        self.create(memo_id="memo-0", title="A", body="visible").unwrap()
        self.create(memo_id="memo-2", title="B", body="visible").unwrap()
        other_user = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-b")
        other_principal = replace(PRINCIPAL, native_account_id="account-b")
        self.identity.bind(binding_id="binding-b", principal=other_principal, subject=other_user, valid_from=NOW,
                           expected_revision=self.identity.revision)
        self.identity.issue_grant(grant_id="other-create", subject=other_user, scope=SCOPE, capability="memo.create",
                                  tier=AuthorizationTier.STANDARD, valid_from=NOW, expected_revision=self.identity.revision)
        actor = self.identity.resolve_authenticated(other_principal, observed_at=NOW).unwrap()
        self.service.create_memo(actor, target=replace(TARGET, owner=other_user), memo_id="memo-1", title="private",
                                 body="secret", operation=self.op(), expected_role_revision=1, observed_at=NOW).unwrap()
        visible = self.service.list_memos(self.actor, target=TARGET, observed_at=NOW, after=MemoCursor(False, "memo-0"), limit=1).unwrap()
        self.assertEqual(tuple(m.memo_id for m in visible), ("memo-2",))
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW, search="secret").unwrap(), ())
        self.assertEqual(self.service.read_memo(self.actor, target=TARGET, memo_id="memo-1", observed_at=NOW).failure.code,
                         "agenda_object_not_found")
        self.identity.revoke_grant("memo.list", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertFalse(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW).is_success)

    def test_schedule_permission_is_the_same_for_create_and_edit(self):
        self.identity.revoke_grant("memo.reminder.set", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.create(schedule=Schedule(NOW, "Asia/Shanghai")).failure.code, "authorization_revoked")
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())
        self.create().unwrap()
        self.assertEqual(self.change("edit", changes={"schedule": Schedule(NOW, "Asia/Shanghai")}).failure.code, "authorization_revoked")
        self.assertIsNone(self.memo().schedule)

    def test_pinned_memos_sort_before_unpinned_across_paginated_results(self):
        for memo_id in ("a", "b", "z"):
            self.create(memo_id=memo_id).unwrap()
        self.change("pin", memo_id="z").unwrap()
        first = self.service.list_memos(self.actor, target=TARGET, observed_at=NOW, limit=1).unwrap()
        self.assertEqual(first[0].memo_id, "z")
        cursor = MemoCursor(first[0].pinned, first[0].memo_id)
        second = self.service.list_memos(self.actor, target=TARGET, observed_at=NOW, limit=2, after=cursor).unwrap()
        self.assertEqual(tuple(m.memo_id for m in second), ("a", "b"))
        self.assertEqual(self.service.list_memos(self.actor, target=TARGET, observed_at=NOW, after=MemoCursor(False, "b")).unwrap(), ())

    def test_new_process_recovers_accepted_due_without_identity_snapshot_and_prepares_once(self):
        self.remind(schedule=Schedule(NOW, "Asia/Shanghai", Frequency.DAILY, count=2)).unwrap()
        claim = self.due_claim()
        self.runtime.close()
        script = """
import json, sys
from companion_v2.agenda.service import AgendaService
from companion_v2.storage.runtime import StorageRuntime
from tests.test_agenda import INSTALLATION, NOW
with StorageRuntime.open(data_root=sys.argv[1], installation_id=INSTALLATION) as runtime:
    service = AgendaService(runtime)
    claim = service.accept_due(sys.argv[2], observed_at=NOW).unwrap()
    result = service.prepare_local(claim, observed_at=NOW).unwrap()
    again = service.prepare_local(claim, observed_at=NOW).unwrap()
    print(json.dumps({'same': result == again, 'delivery': result.delivery, 'recipient': result.recipient.subject_id,
                      'count': len(runtime.read_all('SELECT * FROM agenda_occurrences', ()))}))
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.root), claim.occurrence_id],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                                encoding="utf-8", timeout=20, check=True)
        self.assertEqual(json.loads(result.stdout), {"same": True, "delivery": "not_started", "recipient": USER.subject_id, "count": 2})


class ScheduleTests(unittest.TestCase):
    def test_leap_anchor_returns_to_february_29_and_month_end_does_not_drift(self):
        schedule = Schedule(datetime(2024, 2, 29, 1, tzinfo=timezone.utc), "Asia/Shanghai", Frequency.YEARLY)
        self.assertEqual(schedule.at(1).day, 28)
        self.assertEqual(schedule.at(4).day, 29)
        monthly = Schedule(NOW, "Asia/Shanghai", Frequency.MONTHLY)
        self.assertEqual([monthly.at(i).day for i in range(4)], [31, 29, 31, 30])

    def test_daily_wall_clock_and_dst_gap_or_fold_have_explicit_policy(self):
        zone = ZoneInfo("America/New_York")
        daily = Schedule(datetime(2026, 3, 7, 9, tzinfo=zone), zone.key, Frequency.DAILY)
        self.assertEqual(daily.at(1) - daily.anchor, timedelta(hours=23))
        self.assertEqual(daily.at(1).astimezone(zone).hour, 9)
        gap = Schedule(datetime(2026, 3, 7, 2, 30, tzinfo=zone), zone.key, Frequency.DAILY)
        with self.assertRaisesRegex(AgendaError, "does not exist"):
            gap.at(1)
        self.assertEqual(replace(gap, gap_policy=GapPolicy.SHIFT_FORWARD).at(1).astimezone(zone).hour, 3)
        fold = Schedule(datetime(2026, 10, 31, 1, 30, tzinfo=zone), zone.key, Frequency.DAILY)
        self.assertEqual(replace(fold, fold=1).at(1) - fold.at(1), timedelta(hours=1))

    def test_invalid_timezone_naive_dates_and_boolean_intervals_are_rejected(self):
        for arguments in ({"timezone_name": "Missing/Zone"}, {"interval": True}, {"count": 0}, {"fold": True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                Schedule(**{"anchor": NOW, "timezone_name": "Asia/Shanghai", **arguments})
        with self.assertRaises(ValueError):
            Schedule(NOW.replace(tzinfo=None), "Asia/Shanghai")
        self.assertIsNone(Schedule(NOW, "Asia/Shanghai").at(1))


if __name__ == "__main__":
    unittest.main()
