"""Native replies continue receipt-backed contacts in the original private window."""

import json
from types import SimpleNamespace as NS
import unittest

from astrbot_host.core_reply_context import build_core_reply_prompt
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_role_tool_loop import answered


class CoreReplySentHistoryTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    def prompt(self, app, *, context=None, received_at=None):
        return build_core_reply_prompt(app, context or self.contact_context(),
            NS(text="好啊", event_id="accept-invitation", received_at=received_at or self.clock.now()),
            at=self.clock.now())

    async def test_native_reply_reads_only_confirmed_current_window_contacts_and_rechecks_source(self):
        app = await self.enabled()
        source = self.source(app)

        async def model(_):
            return answered(json.dumps({"decision": "send", "text": "要不要一起下一局五子棋？"},
                                       ensure_ascii=False))

        async def accepted(envelope):
            return self.receipt(envelope, "accepted")

        self.model_behavior, self.send_behavior = model, accepted
        opportunity = self.opportunity("native-history-invite")
        task = (await self.contact(app, opportunity,
            (self.intent(opportunity, purpose="invitation", sources=(source,)),))).unwrap().task
        await self.delivery_state(app, task.task_id, "accepted")
        self.assertNotIn("sent_messages", self.prompt(app).sections)

        self.advance(app, 1)
        before_delivery = self.clock.now()
        self.advance(app, 1)
        app.record_receipt(self.receipt(self.sent[0])).unwrap()
        await self.delivery_state(app, task.task_id, "delivered")

        prompt = self.prompt(app)
        self.assertIn("sent_messages", prompt.sections)
        self.assertIn("要不要一起下一局五子棋？", prompt.context_instruction)
        self.assertIn("最近仍未结束的话头或具体邀请", prompt.context_instruction)
        self.assertIn("游戏、一起活动或通话工具", prompt.context_instruction)
        self.assertNotIn("五子棋", prompt.stable_instruction)
        self.assertNotIn("sent_messages", self.prompt(app, received_at=before_delivery).sections)
        other = self.other_window_context("unrelated-private-window")
        self.assertNotIn("五子棋", self.prompt(app, context=other).context_instruction)

        app.proactive.sources.revoke(source, expected_governance_revision=1,
                                     observed_at=self.clock.now()).unwrap()
        self.assertNotIn("sent_messages", self.prompt(app).sections)

    async def test_confirmed_diagnostic_invitation_is_available_without_turning_scenario_into_real_history(self):
        app = await self.enabled()

        async def model(_):
            return answered(json.dumps({"decision": "send", "text": "想听听你的声音，要不要打个语音电话？"},
                                       ensure_ascii=False))

        self.model_behavior = model
        opportunity = self.opportunity("native-history-diagnostic")
        task = (await self.contact(app, opportunity,
            (self.intent(opportunity, purpose="invitation"),), administrator_test=True)).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        prompt = self.prompt(app)
        self.assertIn("想听听你的声音，要不要打个语音电话？", prompt.context_instruction)
        self.assertIn("情境不证明现实经历或约定", prompt.context_instruction)
        self.assertIn("工具成功前", prompt.context_instruction)
        self.assertEqual(len(self.contact_calls()), 1)


if __name__ == "__main__":
    unittest.main()
