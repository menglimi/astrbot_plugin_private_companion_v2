from dataclasses import asdict, replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.foundation.refs import ReferenceValidationError, VersionRef
from companion_v2.role_work import RoleActivity, RoleActivityState
from companion_v2.role_work.journal import (DreamRecall, JournalContext, JournalDerivatives, JournalDraft, JournalKey,
    JournalKind, JournalOrigin, JournalRef, JournalState, RoleJournalService)
from tests.journal_support import JournalFixture
from tests.test_management_access import NOW, ROLE, SCOPE


class RoleJournalTests(JournalFixture, unittest.TestCase):
    def test_existing_v17_records_and_operation_hashes_survive_optional_provenance_fields(self):
        saved = self.save()
        derived = JournalDerivatives(JournalRef(self.key, 1), dream_fragments=("一道颜色",))
        receipt = self.service.save_derivatives(derived, operation_id="derive")
        old_draft = asdict(self.draft)
        old_draft.pop("materials")
        old_derived = asdict(derived)
        old_derived.pop("fragment_origins")
        with self.runtime.transaction() as connection:
            row = self.runtime.read_one("SELECT content_json FROM role_journals", ())
            content = json.loads(row["content_json"])
            content["draft"].pop("materials")
            connection.execute("UPDATE role_journals SET content_json = ?", (encode(content),))
            row = self.runtime.read_one("SELECT record_json FROM role_journal_derivatives", ())
            record = json.loads(row["record_json"])
            record["material"].pop("fragment_origins")
            connection.execute("UPDATE role_journal_derivatives SET record_json = ?", (encode(record),))
            connection.execute("UPDATE operations SET parameter_hash = ? WHERE operation_id = 'write'",
                               (digest([self.context, old_draft, "save", 0]),))
            connection.execute("UPDATE operations SET parameter_hash = ? WHERE operation_id = 'derive'",
                               (digest([old_derived, 0, "derive"]),))
        service = RoleJournalService(self.open_runtime(), now=lambda: NOW)
        self.assertEqual(service.get(self.key).draft, self.draft)
        self.assertEqual(service.derivatives(self.key).material, derived)
        self.assertEqual(service.save(self.draft, expected_revision=0, operation_id="write"), saved)
        self.assertEqual(service.save_derivatives(derived, operation_id="derive"), receipt)

    def test_local_date_and_original_timezone_survive_reopen_with_multiline_body(self):
        at = NOW + timedelta(hours=17)
        key = JournalKey.at(self.owner, JournalKind.DIARY, at, timezone="Asia/Shanghai")
        west = JournalKey.at(self.owner, JournalKind.DIARY, at, timezone="America/New_York")
        self.assertEqual((key.local_date, west.local_date), ("2026-09-22", "2026-09-21"))
        draft = replace(self.draft, context=replace(self.context, key=key), body="今天聊了模型。\n\n我还想继续了解。")
        receipt = self.save(draft, observed_at=at)
        self.runtime.close()
        service = RoleJournalService(self.open_runtime(), now=lambda: at + timedelta(days=1))
        entry = service.get(key)
        self.assertEqual(entry.draft, draft)
        self.assertEqual(entry.reference, JournalRef(key, receipt.head.revision))
        with self.assertRaises(TaskError) as raised:
            service.save(replace(draft, context=replace(draft.context, timezone="UTC")), expected_revision=1, operation_id="change-zone")
        self.assertEqual(raised.exception.code, "journal_context_conflict")

    def test_dream_fragments_and_afterglow_need_no_invented_full_story_or_factual_source(self):
        key = replace(self.key, kind=JournalKind.DREAM)
        draft = JournalDraft(replace(self.context, key=key), afterglow="只剩一阵轻松的感觉。", recall=DreamRecall.AFTERGLOW)
        self.save(draft)
        self.assertEqual(self.service.get(key).draft.body, "")
        self.assertEqual(self.runtime.read_all("SELECT * FROM sources", ()), ())
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_activities", ()), ())
        with self.assertRaises(ReferenceValidationError):
            replace(self.draft, recall=DreamRecall.FULL)
        with self.assertRaises(ReferenceValidationError):
            replace(draft, recall=None)

    def test_activity_evidence_is_an_exact_snapshot_not_a_claim_of_completion(self):
        activity = self.service.life.add_activity(RoleActivity("reading", ROLE.subject_id, SCOPE, NOW,
            RoleActivityState.ACTIVE, checkpoint="第三章"))
        draft = replace(self.draft, activities=(VersionRef("reading", 1),))
        self.save(draft)
        self.service.life.transition_activity("reading", owner=self.owner, expected_revision=1,
            state=RoleActivityState.PAUSED, operation_id="pause", checkpoint="第四章")
        self.assertEqual(self.service.get(self.key).activity_evidence, (activity,))
        with self.assertRaises(TaskError) as raised:
            self.save(draft, revision=1, operation="late-activity-input")
        self.assertEqual(raised.exception.code, "journal_activity_changed")
        self.assertEqual(self.service.operations.get("late-activity-input").failure.code, "operation_not_found")

    def test_two_connections_preserve_manual_edits_and_replay_returns_only_original_receipt(self):
        original = self.save()
        second = RoleJournalService(self.open_runtime(), now=lambda: NOW)
        edited = replace(self.draft, body="人工补充的一段。", origin=JournalOrigin.MANUAL)
        self.save(edited, revision=1, operation="edit")
        with self.assertRaises(TaskError) as raised:
            second.save(replace(self.draft, body="迟到的自动正文"), expected_revision=1, operation_id="late")
        self.assertEqual(raised.exception.code, "journal_revision_conflict")
        self.assertEqual(self.save(), original)
        self.assertEqual(second.get(self.key).draft, edited)
        self.assertNotIn(self.draft.body, encode(original))
        with self.assertRaises(TaskError):
            self.save(edited)
        self.assertEqual(second.operations.get("late").failure.code, "operation_not_found")

    def test_edit_clears_derivatives_and_old_parent_cannot_publish_new_material(self):
        self.save()
        material = JournalDerivatives(JournalRef(self.key, 1), summary="第三章", dream_fragments=("书页",), continuity="那个问题还没想通")
        first = self.service.save_derivatives(material, operation_id="derive")
        self.save(replace(self.draft, body="其实只读到第二章。"), revision=1, operation="correction")
        self.assertIsNone(self.service.derivatives(self.key))
        self.assertEqual(self.service.save_derivatives(material, operation_id="derive"), first)
        self.assertIsNone(self.service.derivatives(self.key))
        with self.assertRaises(TaskError) as raised:
            self.service.save_derivatives(material, operation_id="late-derive")
        self.assertEqual(raised.exception.code, "journal_dependency_changed")
        fresh = replace(material, parent=JournalRef(self.key, 2), summary="第二章")
        self.service.save_derivatives(fresh, operation_id="fresh-derive")
        self.assertEqual(self.service.derivatives(self.key).material, fresh)

    def test_derivative_revision_conflict_and_reopen_preserve_latest_material(self):
        self.save()
        original = JournalDerivatives(JournalRef(self.key, 1), summary="旧摘要")
        self.service.save_derivatives(original, operation_id="derive")
        updated = replace(original, summary="新的摘要")
        self.service.save_derivatives(updated, expected_revision=1, operation_id="re-derive")
        with self.assertRaises(TaskError) as raised:
            self.service.save_derivatives(original, expected_revision=1, operation_id="stale")
        self.assertEqual(raised.exception.code, "journal_derivative_conflict")
        self.runtime.close()
        service = RoleJournalService(self.open_runtime(), now=lambda: NOW)
        self.assertEqual(service.derivatives(self.key).material, updated)
        self.assertEqual(service.derivatives(self.key).revision, 2)

    def test_deleting_an_unwritten_date_prevents_late_and_new_automatic_writers_after_restart(self):
        removed = self.service.delete(self.context, expected_revision=0, operation_id="delete-before-write")
        self.runtime.close()
        self.service = RoleJournalService(self.open_runtime(), now=lambda: NOW)
        self.assertEqual(self.service.head(self.key), removed.head)
        for revision, code in ((0, "journal_revision_conflict"), (1, "journal_deleted")):
            with self.subTest(revision=revision), self.assertRaises(TaskError) as raised:
                self.save(revision=revision, operation=f"automatic-{revision}")
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.service.list_days(self.owner, kind=JournalKind.DIARY), ())
        self.assertEqual(self.service.list_days(self.owner, kind=JournalKind.DIARY, include_deleted=True), (removed.head,))

    def test_delete_clears_body_and_material_and_operation_replay_does_not_restore_them(self):
        write = self.save()
        material = JournalDerivatives(JournalRef(self.key, 1), summary="应该消失的摘要")
        derive = self.service.save_derivatives(material, operation_id="derive")
        removed = self.service.delete(self.context, expected_revision=1, operation_id="delete")
        self.assertEqual(self.service.delete(self.context, expected_revision=1, operation_id="delete"), removed)
        self.assertEqual(self.save(), write)
        self.assertEqual(self.service.save_derivatives(material, operation_id="derive"), derive)
        self.assertIsNone(self.runtime.read_one("SELECT content_json FROM role_journals", ())["content_json"])
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_journal_derivatives", ()), ())
        for read in (self.service.get, self.service.derivatives):
            with self.assertRaises(TaskError):
                read(self.key)
        for row in self.runtime.read_all("SELECT result_json FROM role_journal_operations", ()):
            self.assertNotIn("body", row["result_json"])
            self.assertNotIn("summary", row["result_json"])

    def test_only_explicit_restore_with_replacement_content_reopens_deleted_date(self):
        self.save()
        with self.assertRaises(TaskError):
            self.service.restore(self.draft, expected_revision=1, operation_id="restore-active")
        self.service.delete(self.context, expected_revision=1, operation_id="delete")
        restored = replace(self.draft, body="主动重新写下的内容。", origin=JournalOrigin.MANUAL)
        receipt = self.service.restore(restored, expected_revision=2, operation_id="restore")
        self.assertEqual((receipt.head.revision, receipt.head.state), (3, JournalState.ACTIVE))
        self.assertEqual(self.service.get(self.key).draft, restored)
        self.assertIsNone(self.service.derivatives(self.key))

    def test_changed_diary_invalidates_dependent_dream_and_later_continuity_material(self):
        self.save()
        dream_key = replace(self.key, kind=JournalKind.DREAM)
        dream = JournalDraft(replace(self.context, key=dream_key), body="梦里书页变成了楼梯。",
            recall=DreamRecall.FRAGMENTS, journals=(JournalRef(self.key, 1),))
        self.save(dream, operation="dream")
        next_key = replace(self.key, local_date="2026-09-22")
        next_day = replace(self.draft, context=replace(self.context, key=next_key), journals=(JournalRef(dream_key, 1),))
        self.save(next_day, operation="next-day")
        for key in (dream_key, next_key):
            self.service.save_derivatives(JournalDerivatives(JournalRef(key, 1), summary="原线索"), operation_id="derive-" + key.kind.value)
        self.save(replace(self.draft, body="更正过的原始记录。"), revision=1, operation="correct")
        for key in (dream_key, next_key):
            for read in (self.service.get, self.service.derivatives):
                with self.subTest(key=key, read=read), self.assertRaises(TaskError) as raised:
                    read(key)
                self.assertEqual(raised.exception.code, "journal_dependency_changed")

    def test_indirect_dependency_cycles_are_rejected_atomically(self):
        self.save()
        other_key = replace(self.key, local_date="2026-09-22")
        other = replace(self.draft, context=replace(self.context, key=other_key), journals=(JournalRef(self.key, 1),))
        self.save(other, operation="other")
        with self.assertRaises(TaskError) as raised:
            self.save(replace(self.draft, journals=(JournalRef(other_key, 1),)), revision=1, operation="cycle")
        self.assertEqual(raised.exception.code, "journal_dependency_cycle")
        self.assertEqual(self.service.get(self.key).reference.revision, 1)
        self.assertEqual(self.service.operations.get("cycle").failure.code, "operation_not_found")

    def test_revoked_original_source_blocks_diary_dream_and_derived_reads(self):
        source = self.source()
        self.save(replace(self.draft, sources=(source,)))
        dream_key = replace(self.key, kind=JournalKind.DREAM)
        dream = JournalDraft(replace(self.context, key=dream_key), afterglow="还记得翻页声。", recall=DreamRecall.AFTERGLOW,
            journals=(JournalRef(self.key, 1),))
        self.save(dream, operation="dream")
        material = JournalDerivatives(JournalRef(dream_key, 1), dream_fragments=("翻页声",))
        self.service.save_derivatives(material, operation_id="derive")
        self.service.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
        for key in (self.key, dream_key):
            for read in (self.service.get, self.service.derivatives):
                with self.assertRaises(TaskError) as raised:
                    read(key)
                self.assertEqual(raised.exception.code, "source_revoked")
        with self.assertRaises(TaskError):
            self.service.save_derivatives(material, expected_revision=1, operation_id="revoked-derive")
        # Deletion remains possible even when the original source is no longer readable.
        self.service.delete(self.context, expected_revision=1, operation_id="delete-revoked")

    def test_missing_expired_or_forged_source_cannot_enter_a_diary(self):
        source = self.source(expires_at=NOW + timedelta(hours=1))
        for ref, at, code in ((replace(source, source_id="missing"), NOW, "source_not_found"),
                              (source, NOW + timedelta(hours=1), "source_expired"),
                              (replace(source, owner="forged"), NOW, "source_reference_mismatch")):
            with self.subTest(code=code), self.assertRaises(TaskError) as raised:
                self.save(replace(self.draft, sources=(ref,)), operation=code, observed_at=at)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.service.head(self.key).state, JournalState.ABSENT)

    def test_role_archive_continues_across_windows_and_isolates_bots_and_personas(self):
        self.save()
        for owner in (replace(self.owner, persona_id="other"), replace(self.owner, bot_id="other-bot")):
            key = replace(self.key, owner=owner)
            context = replace(self.context, key=key, scope=replace(SCOPE, bot_id=owner.bot_id))
            self.save(replace(self.draft, context=context), operation=owner.persona_id + owner.bot_id)
            self.assertEqual([item.key for item in self.service.list_days(owner, kind=JournalKind.DIARY)], [key])
        next_key = replace(self.key, local_date="2026-09-22")
        second_window = replace(self.context, key=next_key, scope=replace(SCOPE, session_id="other-window"))
        self.save(replace(self.draft, context=second_window), operation="other-window")
        first = self.service.list_days(self.owner, kind=JournalKind.DIARY, limit=1)
        later = self.service.list_days(self.owner, kind=JournalKind.DIARY, after_date=first[-1].key.local_date)
        self.assertEqual([item.key for item in first + later], [self.key, next_key])
        with self.assertRaises(TaskError):
            self.service.head(replace(self.key, owner=replace(self.owner, installation_id="other-installation")))
        with self.assertRaises(ReferenceValidationError):
            replace(self.draft, journals=(JournalRef(replace(self.key, owner=replace(self.owner, persona_id="other")), 1),))

    def test_enclosing_transaction_rolls_back_body_derivatives_and_operation_receipts(self):
        with self.assertRaises(RuntimeError):
            with self.runtime.transaction():
                self.save()
                self.service.save_derivatives(JournalDerivatives(JournalRef(self.key, 1), summary="临时摘要"), operation_id="derive")
                raise RuntimeError("rollback")
        self.assertEqual(self.service.head(self.key).state, JournalState.ABSENT)
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_journal_derivatives", ()), ())
        for operation in ("write", "derive"):
            self.assertEqual(self.service.operations.get(operation).failure.code, "operation_not_found")

    def test_invalid_dates_revisions_and_clock_regression_do_not_mutate_records(self):
        for day in ("2026-02-30", "20260921", "2026-9-21"):
            with self.assertRaises(ValueError):
                replace(self.key, local_date=day)
        for value in (True, -1, 1.5):
            with self.assertRaises(ReferenceValidationError):
                self.save(revision=value)
        self.save()
        with self.assertRaises(ValueError):
            self.save(revision=1, operation="past", observed_at=NOW - timedelta(seconds=1))
        self.assertEqual(self.service.head(self.key).revision, 1)


if __name__ == "__main__":
    unittest.main()
