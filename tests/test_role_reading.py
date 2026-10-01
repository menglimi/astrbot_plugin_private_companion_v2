"""Trusted reading reports persist exact provenance in isolated V2 activities."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskContext, TaskError, digest
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.role_work import RoleActivity, RoleActivityState as State
from companion_v2.role_work.journal import JournalContext, JournalDraft, JournalKey, JournalKind, MaterialKind
from companion_v2.sources.models import SourceRecord
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE


class ReadingFixture(HostFixture):
    async def setup_reading(self):
        self.reading_grant = self.grant(self.important, SCOPE, "role.reading.record")
        self.writing_grant = self.grant(self.important, SCOPE, "role.journal.write")
        self.host_instance = await self.start(self.host())
        self.app = self.host_instance.application
        binding = self.app.tasks.identity.resolve_role(SCOPE, observed_at=NOW).unwrap()
        self.reading_context = TaskContext(self.important, binding, AudienceRef(SCOPE, (self.important.subject,)))
        self.owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)
        self.original_text = "未读开头。真正读过的这一段。未读结尾。"
        self.original_source = self.source("original", self.original_text, issued_at=NOW - timedelta(days=1))
        self.add_activity("reading")

    def target(self, day="2026-09-21"):
        return JournalContext(JournalKey(self.owner, JournalKind.DIARY, day), SCOPE, "Asia/Shanghai")

    def source(self, name, text, *, scope=SCOPE, issued_at=NOW, expires_at=None, recipients=None):
        ref = SourceRef(name, "reading.fixture", scope, VersionRef(name, 1), issued_at, expires_at)
        self.app.role_journal.sources.publish(SourceRecord(ref,
            AudienceRef(scope, recipients if recipients is not None else (self.important.subject,)),
            digest(text), text), observed_at=NOW).unwrap()
        return ref

    def add_activity(self, name, *, state=State.ACTIVE, scope=SCOPE, at=NOW, description=""):
        return self.app.role_life.add_activity(RoleActivity(name, ROLE.subject_id, scope, at, state,
                                                           description=description))

    def record(self, **changes):
        options = dict(activity_id="reading", source=self.original_source, content_hash=digest(self.original_text),
            start_offset=5, end_offset=15, completed_at=NOW, expected_revision=1, operation_id="read-complete")
        options.update(changes)
        return self.app.role_reading.record_completion(self.reading_context, **options)


class ReadingTests(ReadingFixture, unittest.IsolatedAsyncioTestCase):
    async def test_completion_survives_restart_and_replay_keeps_exact_span_and_time(self):
        await self.setup_reading()
        saved = self.record().unwrap()
        self.assertEqual((saved.state, saved.revision), (State.COMPLETED, 2))
        self.assertEqual(saved.reading.source, self.original_source)
        self.assertEqual((saved.reading.start_offset, saved.reading.end_offset, saved.reading.completed_at), (5, 15, NOW))
        self.assertFalse(saved.reading.covers_source)
        await self.app.close()
        self.runtime.close()
        self.clock.advance(timedelta(days=1))
        self.runtime = self.open_runtime()
        self.host_instance = await self.start(self.host(runtime=self.runtime), task_generation=1, model_generation=1)
        self.app = self.host_instance.application
        self.assertEqual(self.record().unwrap(), saved)
        self.assertEqual(self.app.role_life.activity("reading", owner=self.owner), saved)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM role_life_operations", ())), 1)
        self.assertEqual(self.record(end_offset=16).failure.code, "idempotency_key_conflict")
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_plan_or_cancelled_activity_never_becomes_read_by_a_completion_report(self):
        await self.setup_reading()
        for state in (State.PLANNED, State.CANCELLED):
            self.add_activity(state.value, state=state)
            with self.assertRaises(ValueError):
                self.record(activity_id=state.value, operation_id="invalid-" + state.value)
            self.assertEqual(self.app.role_life.activity(state.value, owner=self.owner).state, state)
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_life_operations", ()), ())

    async def test_wrong_hash_times_and_spans_leave_no_completion_or_operation(self):
        await self.setup_reading()
        for changes, code in ((dict(content_hash="wrong"), "reading_source_changed"),
                              (dict(completed_at=NOW + timedelta(seconds=1)), "reading_time_invalid"),
                              (dict(completed_at=NOW - timedelta(seconds=1)), "reading_time_invalid"),
                              (dict(activity_id="missing"), "reading_activity_unavailable")):
            self.assertEqual(self.record(**changes).failure.code, code)
        for changes in (dict(start_offset=True), dict(start_offset=-1), dict(end_offset=1000),
                        dict(start_offset=5, end_offset=5)):
            with self.assertRaises(ValueError):
                self.record(**changes)
        blank = self.source("blank", "  ")
        self.assertEqual(self.record(source=blank, content_hash=digest("  "), start_offset=0, end_offset=2).failure.code,
                         "reading_span_empty")
        self.assertIsNone(self.app.role_life.activity("reading", owner=self.owner).reading)
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_life_operations", ()), ())

    async def test_retracted_source_current_grant_and_scope_are_rechecked_before_commit(self):
        await self.setup_reading()
        foreign = replace(SCOPE, session_id="other-window")
        self.add_activity("other", scope=foreign)
        self.assertEqual(self.record(activity_id="other").failure.code, "reading_context_mismatch")
        denied = self.source("denied", self.original_text, recipients=(self.standard.subject,))
        self.assertEqual(self.record(source=denied).failure.code, "source_audience_denied")
        self.identity.revoke_grant(self.reading_grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.record().failure.code, "authorization_revoked")
        self.grant(self.important, SCOPE, "role.reading.record")
        self.app.role_journal.sources.revoke(self.original_source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.record().failure.code, "source_revoked")
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_life_operations", ()), ())

    async def test_partial_reading_produces_only_consumed_excerpt_and_keeps_journal_source_dependency(self):
        await self.setup_reading()
        saved = self.record().unwrap()
        actions = self.app.journal_material_producer.for_day(self.target())
        excerpts = self.app.journal_reading_material_producer.for_day(self.reading_context, self.target())
        self.assertEqual(len(actions.materials), 1)
        self.assertEqual((actions.materials[0].kind, excerpts.materials[0].kind), (MaterialKind.ACTION, MaterialKind.READING))
        self.assertEqual(actions.materials[0].origin, excerpts.materials[0].origin)
        self.assertIn(self.original_text[5:15], excerpts.materials[0].text)
        self.assertNotIn("未读开头", excerpts.materials[0].text)
        self.assertNotIn("未读结尾", excerpts.materials[0].text)
        activity_ref = VersionRef(saved.activity_id, saved.revision)
        with self.assertRaises(TaskError) as missing:
            self.app.role_journal.save(JournalDraft(self.target(), body="今天读了一段文章。", activities=(activity_ref,)),
                                      expected_revision=0, operation_id="missing-source")
        self.assertEqual(missing.exception.code, "journal_reading_source_required")
        draft = JournalDraft(self.target(), body="今天读了一段文章。", sources=actions.source_refs,
                             activities=actions.activity_refs, materials=actions.materials + excerpts.materials)
        self.app.role_journal.save(draft, expected_revision=0, operation_id="reading-diary")
        self.assertEqual(self.app.role_journal.get(self.target().key).activity_evidence[0].reading, saved.reading)
        self.app.role_journal.sources.revoke(self.original_source, expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError):
            self.app.role_journal.get(self.target().key)
        with self.assertRaises(TaskError):
            self.app.journal_reading_material_producer.for_day(self.reading_context, self.target())

    async def test_reading_date_uses_actual_completion_and_empty_pages_continue(self):
        await self.setup_reading()
        self.add_activity("a-generic-completion", state=State.COMPLETED, description="文字里提到读完一本书。")
        self.clock.advance(timedelta(hours=16))
        saved = self.record(completed_at=self.clock.now(), start_offset=0, end_offset=len(self.original_text)).unwrap()
        self.assertTrue(saved.reading.covers_source)
        producer = self.app.journal_reading_material_producer
        self.assertEqual(producer.for_day(self.reading_context, self.target()).materials, ())
        next_day = self.target("2026-09-22")
        first = producer.for_day(self.reading_context, next_day, limit=1)
        self.assertEqual(first.materials, ())
        self.assertEqual(first.next_cursor, "a-generic-completion")
        second = producer.for_day(self.reading_context, next_day, limit=1, after_id=first.next_cursor)
        self.assertEqual(len(second.materials), 1)
        self.assertEqual(second.materials[0].local_date, "2026-09-22")
        self.assertIn(self.original_text, second.materials[0].text)

    async def test_receipt_cannot_follow_text_mutation_or_outlive_host(self):
        await self.setup_reading()
        self.record().unwrap()
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE sources SET payload_json = ? WHERE source_id = ?",
                               (json.dumps("被替换的原文"), self.original_source.source_id))
        with self.assertRaises(TaskError) as changed:
            self.app.journal_reading_material_producer.for_day(self.reading_context, self.target())
        self.assertEqual(changed.exception.code, "reading_source_changed")
        await self.app.close()
        self.assertEqual(self.record().failure.code, "host_not_running")
