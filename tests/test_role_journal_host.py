from dataclasses import replace
from datetime import timedelta
import unittest

from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.role_work.journal import (JournalContext, JournalDerivatives, JournalDraft,
    JournalKey, JournalKind, JournalRef, JournalState)
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE


class RoleJournalHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def draft(self, day="2026-09-21"):
        owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)
        return JournalDraft(JournalContext(JournalKey(owner, JournalKind.DIARY, day), SCOPE, "Asia/Shanghai"), body="还想再读一点。")

    async def test_host_reopen_preserves_journal_material_and_deleted_dates_without_generation(self):
        host = await self.start()
        service = host.application.role_journal
        self.assertIs(service.runtime, host.application.runtime)
        draft = self.draft()
        service.save(draft, expected_revision=0, operation_id="write")
        material = JournalDerivatives(JournalRef(draft.context.key, 1), dream_fragments=("翻页声",))
        service.save_derivatives(material, operation_id="derive")
        deleted = self.draft("2026-09-20")
        service.delete(deleted.context, expected_revision=0, operation_id="delete-day")
        await host.application.close()
        self.runtime.close()
        self.clock.advance(timedelta(days=2))
        reopened = await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)
        service = reopened.application.role_journal
        self.assertEqual(service.get(draft.context.key).draft, draft)
        self.assertEqual(service.derivatives(draft.context.key).material, material)
        self.assertEqual(service.head(deleted.context.key).state, JournalState.DELETED)
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_conversation_does_not_block_on_or_implicitly_rewrite_journal(self):
        host = await self.start()
        draft = self.draft()
        service = host.application.role_journal
        original = service.save(draft, expected_revision=0, operation_id="write")
        batch = host.receive(self.event()).unwrap()
        self.advance(host.application, 1)
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(service.head(draft.context.key), original.head)
        self.assertEqual(service.get(draft.context.key).draft, draft)
        service.save(replace(draft, body="新增一段记录。"), expected_revision=1, operation_id="edit")
        self.assertEqual(len(self.called), 1)
        self.assertEqual([part.text for part in self.sent], ["第一段", "第二段"])


if __name__ == "__main__":
    unittest.main()
