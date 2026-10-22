"""The pre-model private closing guard silences only a redundant closing."""

import asyncio
from datetime import timedelta
import unittest

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from companion_v2.conversation.reply_settings import ReplyConfigurationOwner, configuration_fields, target_for
from companion_v2.model_gateway.core_observations import observations_for_role
from tests.multi_host_support import MultiFixture
from tests.test_main_no_reply import ENTRY


class PrivateClosingHostTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()
        self.plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        self.plugin.staging = self.controller
        self.observer = self.controller.session.core_reply_observations

    async def flush(self):
        while self.observer._pending:
            await asyncio.gather(*tuple(self.observer._pending), return_exceptions=False)

    async def role_replies(self, text, *, user_text="我先睡了", identifier="closing-first"):
        event = self.event(identifier=identifier, text=user_text)
        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        await self.flush()
        await self.observer.output(prepared, text, state="send_returned")
        await self.flush()
        return prepared

    async def intake(self, text, *, identifier="closing-current"):
        event = self.event(identifier=identifier, text=text)
        await self.plugin.receive_companion_message(event)
        await self.flush()
        return event

    @staticmethod
    def prepared(event):
        return event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["prepared"]

    def assert_ledger(self, reason_code):
        row = self.app.runtime.read_one(
            "SELECT * FROM inbound_no_replies WHERE reason_code = ?", (reason_code,))
        self.assertIsNotNone(row)
        self.assertEqual(row["channel"], "private")
        return row

    async def test_second_goodnight_is_suppressed_before_the_model(self):
        await self.role_replies("晚安，睡个好觉呀")
        event = await self.intake("晚安")
        self.assertTrue(getattr(event, "call_llm", False))
        self.assertFalse(getattr(event, "is_at_or_wake_command", False))
        self.assertEqual(event.sent, [])
        self.assertEqual(self.native.provider.client.state.calls, [])
        prepared = self.prepared(event)
        self.assertTrue(prepared["private_closing"]["suppress_reply"])
        self.assertEqual(prepared["private_closing"]["reason"], "role_already_closed")
        self.assertEqual(prepared["private_closing"]["action"], "silent")
        self.assert_ledger("private_closing_role_already_closed")
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(record["generation_state"], "suppressed")
        self.assertEqual(record["requests"], [])
        self.assertEqual(record["delivery"]["attempts"], 0)

    async def test_new_content_after_role_closing_still_gets_the_model(self):
        await self.role_replies("晚安，睡个好觉呀")
        event = await self.intake("晚安，明天七点叫我")
        self.assertFalse(getattr(event, "call_llm", False))
        self.assertTrue(event.is_at_or_wake_command)
        prepared = self.prepared(event)
        self.assertFalse(prepared["private_closing"]["suppress_reply"])
        self.assertEqual(prepared["private_closing"]["reason"], "not_a_closing")
        self.assertIn("【对话收尾】", prepared["prompt_instruction"])
        self.assertEqual(event.sent, [])

    async def test_repeated_user_closing_is_silent_even_when_the_role_did_not_close(self):
        await self.role_replies("这么早？", user_text="晚安")
        event = await self.intake("晚安")
        self.assertTrue(getattr(event, "call_llm", False))
        self.assertFalse(getattr(event, "is_at_or_wake_command", False))
        prepared = self.prepared(event)
        self.assertEqual(prepared["private_closing"]["reason"], "repeated_user_closing")
        self.assert_ledger("private_closing_repeated_user_closing")

    async def test_first_goodnight_without_history_keeps_the_ordinary_reply(self):
        event = await self.intake("晚安")
        self.assertFalse(getattr(event, "call_llm", False))
        self.assertTrue(event.is_at_or_wake_command)
        self.assertEqual(self.prepared(event)["private_closing"]["reason"], "no_role_reply")

    async def test_outside_the_window_the_ordinary_reply_resumes(self):
        await self.role_replies("晚安，睡个好觉呀")
        self.clock.advance(timedelta(seconds=3601))
        event = await self.intake("晚安")
        self.assertFalse(getattr(event, "call_llm", False))
        self.assertTrue(event.is_at_or_wake_command)
        self.assertEqual(self.prepared(event)["private_closing"]["reason"], "outside_window")

    async def test_disabled_guard_keeps_the_ordinary_reply(self):
        prepared = await self.role_replies("晚安，睡个好觉呀")
        common = self.controller.settings.common
        fields = configuration_fields(common.segmentation, common.streaming, common.policy.part_gap_seconds)
        owner, target = ReplyConfigurationOwner(self.app.runtime), target_for(prepared["context"])
        owner.write(target, fields,
                    changes={"conversation.presentation.private_closing_guard_enabled": False},
                    reset=(), expected_revision=owner.read(target, fields).revision,
                    observed_at=self.clock.now())
        event = await self.intake("晚安")
        self.assertFalse(getattr(event, "call_llm", False))
        self.assertTrue(event.is_at_or_wake_command)
        self.assertEqual(self.prepared(event)["private_closing"]["reason"], "disabled")


if __name__ == "__main__":
    unittest.main()
