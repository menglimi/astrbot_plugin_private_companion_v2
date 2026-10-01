"""Private journal contact candidates with synthetic provider and transport."""

import json
import unittest

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import RoleOwnerRef, SourceRef, VersionRef
from companion_v2.proactive.journal_events import JOURNAL_SOURCE_OWNER, JournalContactEvents
from companion_v2.role_work.journal import DreamRecall, JournalContext, JournalDraft, JournalKey, JournalKind
from companion_v2.sources.models import SourceRecord
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_management_access import SCOPE
from tests.test_role_tool_loop import answered


class JournalContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_contacts(self, **settings):
        self.grant(self.important, SCOPE, "role.journal.write")
        self.host_instance, batch = await self.scheduled()
        self.app = self.host_instance.application
        self.origin = self.context(self.app, batch)
        self.settings(self.app, {"chat.enabled": False, **settings}).unwrap()
        self.assertIsInstance(self.app.contact_schedule.journal_events, JournalContactEvents)

    def journal(self, *, kind=JournalKind.DIARY, body="今天有一段只属于角色自己的回顾。", afterglow="", recall=None,
                operation="journal-save", revision=0):
        owner = RoleOwnerRef(self.origin.scope.installation_id, self.origin.scope.bot_id,
                             self.origin.role_binding.role.subject_id)
        key = JournalKey(owner, kind, self.clock.now().date().isoformat())
        context = JournalContext(key, self.origin.scope, "Asia/Shanghai")
        draft = JournalDraft(context, body=body, afterglow=afterglow, recall=recall)
        return self.app.role_journal.save(draft, expected_revision=revision, operation_id=operation,
                                          observed_at=self.clock.now())

    async def test_saved_diary_becomes_private_life_candidate_with_bounded_subjective_material(self):
        await self.setup_contacts()
        self.journal()
        self.advance(self.app, 60)
        await self.automatic_delivery(self.app)
        request = self.contact_calls()[0].original
        evidence = [m.payload for m in request.context.materials if m.owner == JOURNAL_SOURCE_OWNER]
        self.assertEqual(len(evidence), 1)
        self.assertNotIn("_receipt", evidence[0])
        self.assertIn("主观回顾", evidence[0])
        self.assertIn("只属于角色自己的回顾", evidence[0])
        self.assertEqual(json.loads(evidence[0])["event"], "private_journal_saved")
        self.assertEqual(json.loads(self.contacts(self.app)[0]["record_json"])["purpose"], "life")

    async def test_saved_dream_is_subjective_and_old_candidate_is_invalidated_by_edit(self):
        await self.setup_contacts()
        saved = self.journal(kind=JournalKind.DREAM, body="", afterglow="只剩一阵蓝色的余韵。", recall=DreamRecall.AFTERGLOW,
                             operation="dream-save")
        preferences = self.preferences(self.app, self.origin)
        candidate, _ = self.app.contact_schedule.journal_events.select(self.origin, preferences, self.clock.now())
        self.assertIsNotNone(candidate)
        _, intents, marker = candidate
        source = intents[0].thought.evidence.sources[0]
        evidence = self.app.proactive._records(self.origin, (source,), self.clock.now())[0]
        self.assertIn("主观记忆", evidence.payload)
        self.journal(kind=JournalKind.DREAM, body="", afterglow="后来记得更多一点。", recall=DreamRecall.AFTERGLOW,
                     operation="dream-edit", revision=saved.head.revision)
        with self.assertRaises(TaskError) as raised:
            self.app.contact_schedule.journal_events.validate(self.origin, marker, self.clock.now())
        self.assertEqual(raised.exception.code, "contact_journal_changed")

    async def test_journal_candidate_does_not_cross_private_scope(self):
        await self.setup_contacts()
        self.journal(operation="private-save")
        foreign = self.other_window_context("foreign-journal")
        self.grant(self.important, foreign.scope, "role.journal.write")
        preferences = self.preferences(self.app, foreign)
        candidate, more = self.app.contact_schedule.journal_events.select(foreign, preferences, self.clock.now())
        self.assertIsNone(candidate)
        self.assertFalse(more)

    async def test_deleted_diary_during_generation_cannot_be_sent(self):
        await self.setup_contacts()
        receipt = self.journal()

        async def remove(envelope):
            self.app.role_journal.delete(JournalContext(receipt.head.key, self.origin.scope, "Asia/Shanghai"),
                expected_revision=receipt.head.revision, operation_id="journal-delete", observed_at=self.clock.now())
            return answered('{"decision":"send","text":"已经删除的日记内容"}')

        self.model_behavior = remove
        self.advance(self.app, 60)
        await self.until(lambda: len(self.contact_calls()) == 1)
        await self.until(lambda: not self.app.proactive.active_handles)
        self.assertEqual(self.contacts(self.app), ())
        self.assertEqual(len(self.sent), 1)

    async def test_revoked_journal_input_and_tampered_operation_are_not_selected(self):
        await self.setup_contacts()
        source = SourceRef("journal-input", "journal.fixture", self.origin.scope,
                           VersionRef("journal-input", 1), self.clock.now())
        content = "一段仍有来源的旧对话。"
        self.app.proactive.sources.publish(SourceRecord(source, self.origin.audience, digest(content), content),
                                           observed_at=self.clock.now()).unwrap()
        owner = RoleOwnerRef(self.origin.scope.installation_id, self.origin.scope.bot_id,
                             self.origin.role_binding.role.subject_id)
        key = JournalKey(owner, JournalKind.DIARY, self.clock.now().date().isoformat())
        draft = JournalDraft(JournalContext(key, self.origin.scope, "Asia/Shanghai"), body="记下这段话。", sources=(source,))
        self.app.role_journal.save(draft, expected_revision=0, operation_id="journal-input-save",
                                   observed_at=self.clock.now())
        producer = self.app.contact_schedule.journal_events
        candidate, _ = producer.select(self.origin, self.preferences(self.app, self.origin), self.clock.now())
        self.assertIsNotNone(candidate)
        self.app.proactive.sources.revoke(source, expected_governance_revision=1,
                                          observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError):
            producer.validate(self.origin, candidate[2], self.clock.now())
        self.assertFalse(self.app.proactive.sources.validate_reference(
            candidate[1][0].thought.evidence.sources[0], observed_at=self.clock.now()).is_success)

    async def test_journal_receipt_hash_mismatch_blocks_candidate(self):
        await self.setup_contacts()
        self.journal()
        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE operations SET parameter_hash = ? WHERE operation_id = ?",
                               ("tampered", "journal-save"))
        candidate, _ = self.app.contact_schedule.journal_events.select(
            self.origin, self.preferences(self.app, self.origin), self.clock.now())
        self.assertIsNone(candidate)
