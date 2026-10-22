"""The management view over this window's withdrawn messages.

V1 answered a chat command from a short-lived cache. V2 keeps the admitted input
row and marks withdrawal in place, so these checks cover the V2 shape: the bounded
read works only while the window allows it, it needs a core operator, and it never
brings the withdrawn source back.
"""

from __future__ import annotations

import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.recall_management import RecallManagement
from companion_v2.conversation.recall_settings import GROUP
from companion_v2.conversation.recalls import MessageRecall
from tests.test_host_application import HostFixture
from tests.test_management_access import INSTALLATION, ROLE, SCOPE


class RecallTranscribeTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        # A dashboard operator manages this installation's memory; the window
        # participant has no such grant, exactly as in production.
        self.assertIsNotNone(self.core)

    def settings(self, app, changes):
        target = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE)
        snapshot = app.configuration.read(self.core, target=target, group_id=GROUP,
                                          observed_at=self.clock.now()).unwrap()
        return app.configuration.patch(self.core, target=target, group_id=GROUP,
            expected_edit_token=snapshot.edit_token,
            changes={GROUP + "." + key: value for key, value in changes.items()},
            operation=self.operation(target.authorization_scope, owner=GROUP), observed_at=self.clock.now())

    async def withdrawn_batch(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event()).unwrap()
        context = self.context(app, batch)
        notice = MessageRecall.from_scope(context.scope, "event-1", self.important.subject.subject_id)
        app.platform_recall(notice).unwrap()
        return app, context

    async def test_transcript_returns_the_withdrawn_text_only_when_enabled(self):
        app, context = await self.withdrawn_batch()
        # 撤回感知默认开启：核心管理员无需先去页面找开关就能读到撤回内容。
        self.settings(app, {"transcribe_window_minutes": 60}).unwrap()
        default_on = RecallManagement(app, context).transcribe(self.core).unwrap()
        self.assertEqual(default_on["state"], "ok")
        self.assertTrue(default_on["enabled"])
        # 关掉之后必须拒绝；边界仍然是"这一窗口的开关"。
        self.settings(app, {"transcribe_enabled": False}).unwrap()
        self.assertEqual(RecallManagement(app, context).transcribe(self.core).failure.code,
                         "recall_transcribe_disabled")
        self.settings(app, {"transcribe_enabled": True, "transcribe_window_minutes": 60}).unwrap()
        result = RecallManagement(app, context).transcribe(self.core).unwrap()
        self.assertEqual(result["state"], "ok")
        self.assertIn("输入 event-1", result["entries"][0]["text"])
        self.assertEqual(result["entries"][0]["author"], self.important.subject.subject_id)
        # Withdrawal stays withdrawal: the read never revives the original source.
        revived = [row["state"] for row in app.runtime.read_all("SELECT state FROM sources", ())]
        self.assertNotIn("active", revived)

    async def test_transcript_requires_a_core_operator(self):
        app, context = await self.withdrawn_batch()
        self.settings(app, {"transcribe_enabled": True}).unwrap()
        self.assertFalse(RecallManagement(app, context).transcribe(self.important).is_success)


__all__ = ["RecallTranscribeTests"]
