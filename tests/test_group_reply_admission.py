"""Group listening stays silent; admitted non-mention replies carry reasons."""

import asyncio
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.participation import CONFIG_GROUP, GroupParticipationConfigurationOwner, configuration_fields
from companion_v2.conversation.reply_settings import ReplyConfigurationOwner, target_for, configuration_fields as reply_fields
from companion_v2.execution.models import TaskContext
from tests.group_host_support import GroupFixture, group_config
from tests.test_group_participation import ACTION, command
from tests.native_adapter_support import completion, final_text
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_main_no_reply import ENTRY


class GroupReplyAdmissionTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = self.make_controller(group_config(group_delivery_mode="onebot_group"))
        self.app = await self.start_host()
        self.plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        self.plugin.staging = self.controller

    def event(self, identifier, text, *, sender="200", mention=False, reply=None, target="group-a"):
        event = self.group_event(identifier=identifier, text=text, sender=sender, target=target)
        event.stopped = False
        event.stop_event = lambda: setattr(event, "stopped", True)
        event.is_wake = True
        if mention:
            event.message_obj.message.insert(0, NS(type="At", qq="100"))
        if reply is not None:
            event.message_obj.message.insert(0, NS(type="Reply", id=reply))
        return event

    async def candidate(self, event):
        result = await self.controller.group_reply_candidate(event)
        self.assertTrue(result.is_success, result.failure)
        return result.unwrap()

    async def settle(self, batch):
        await wait_for_batch(self.controller.session, batch)
        async def wait():
            while any(work.batch_id == batch for work, _ in self.app._workers.values()):
                await asyncio.sleep(0.005)
        await asyncio.wait_for(wait(), 3)

    async def configure(self, **changes):
        context = (await self.controller.observe_group_early(self.event("settings", "普通群聊天"))).unwrap()
        settings = self.controller.settings.common
        fields = reply_fields(settings.segmentation, settings.streaming, settings.policy.part_gap_seconds)
        owner = ReplyConfigurationOwner(self.app.runtime)
        target = target_for(context)
        owner.write(target, fields, changes={"conversation.presentation." + key: value for key, value in changes.items()},
                    reset=(), expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        return context

    async def test_unmatched_messages_keep_observation_without_intake_logs_batches_or_model_calls(self):
        context = (await self.controller.observe_group_early(self.event("settings", "普通群聊天"))).unwrap()
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)
        owner, fields = GroupParticipationConfigurationOwner(self.app.runtime), configuration_fields()
        owner.write(target, fields, changes={CONFIG_GROUP + ".enable_group_social_context": True,
                                           CONFIG_GROUP + ".enable_group_mood_detection": True}, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        participation = self.app.tools.group_participation
        with patch.object(ENTRY.logger, "info") as info, patch.object(participation, "observe_early", wraps=participation.observe_early) as observe:
            for index, text in enumerate(("大家好", "晚饭吃面", "笑死", "？？？")):
                event = self.event("ordinary-" + str(index), text)
                await self.plugin.observe_companion_group_early(event)
                await self.plugin.receive_companion_message(event)
                self.assertFalse(event.stopped)
                self.assertTrue(event.call_llm)
            self.assertTrue(observe.called)
            self.assertFalse(any("接管入站" in call.args[0] or "入站已受理" in call.args[0] for call in info.call_args_list))
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM inbound_no_replies", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(self.app.runtime.read_all("SELECT key FROM runtime_metadata WHERE key LIKE '%:mood:%'", ()))

    async def test_mention_only_is_admitted_and_wake_listener_flag_is_not_a_trigger(self):
        self.assertFalse((await self.candidate(self.event("ordinary", "晚饭吃面")))["admitted"])
        decision = await self.candidate(self.event("at-only", "", mention=True))
        self.assertEqual(decision["reason"], "mention")
        self.assertTrue(decision["mentioned"])
        awakened = self.event("native-wake", "继续")
        awakened.is_at_or_wake_command = True
        self.assertEqual((await self.candidate(awakened))["reason"], "native_wakeup")
        quoted = self.event("native-quote", "", reply="previous-native-message")
        quoted.message_obj.message[0].sender_id = "100"
        quoted.is_at_or_wake_command = True
        self.assertEqual((await self.candidate(quoted))["reason"], "native_quote")
        mentioned_all = self.event("mention-all", "大家看看")
        mentioned_all.message_obj.message.insert(0, NS(type="At", qq="all"))
        mentioned_all.is_at_or_wake_command = True
        self.assertEqual((await self.candidate(mentioned_all))["reason"], "mention_all")

    async def test_interjection_requires_an_opening_and_repeat_counts_silent_observations(self):
        context = (await self.controller.observe_group_early(self.event("settings", "普通群聊天"))).unwrap()
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)
        owner, fields = GroupParticipationConfigurationOwner(self.app.runtime), configuration_fields()
        owner.write(target, fields, changes={CONFIG_GROUP + ".enable_group_interjection": True}, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        self.assertFalse((await self.candidate(self.event("no-opening", "晚饭吃面")))["admitted"])
        self.assertEqual((await self.candidate(self.event("opening", "这也太离谱了")))["reason"], "interjection")
        for index in range(3):
            self.clock.advance(timedelta(seconds=1))
            self.assertFalse((await self.candidate(self.event("silent-repeat-" + str(index), "好", sender=str(210 + index))))["admitted"])
        self.clock.advance(timedelta(seconds=1))
        self.assertEqual((await self.candidate(self.event("repeat-trigger", "好", sender="214")))["reason"], "repeat")

    async def test_direct_words_question_and_disabled_strategies_use_effective_settings(self):
        await self.configure(group_wakeup_bot_name="小星", group_wakeup_question_enabled=False)
        self.assertEqual((await self.candidate(self.event("named", "小星来看看")))["reason"], "direct_word")
        self.assertFalse((await self.candidate(self.event("question-off", "如何修复？")))["admitted"])
        await self.configure(group_wakeup_question_enabled=True)
        self.assertEqual((await self.candidate(self.event("question-on", "有没有人知道怎么修复")))["reason"], "question")
        await self.configure(group_wakeup_enabled=False)
        self.assertFalse((await self.candidate(self.event("wake-off", "小星来看看")))["admitted"])
        self.assertTrue((await self.candidate(self.event("at-when-off", "来看看", mention=True)))["admitted"])

    async def test_non_mention_reply_logs_policy_reason_and_confirmed_delivery(self):
        await self.configure(group_wakeup_bot_name="小星")
        event = self.event("named-reply", "小星来看看")
        with self.assertLogs("companion_v2.conversation.participation", level="INFO") as logs:
            await self.plugin.receive_companion_message(event)
            batch = self.app.runtime.read_one("SELECT batch_id FROM conversation_batches", ())["batch_id"]
            await self.settle(batch)
        self.assertEqual(len(logs.output), 2)
        self.assertTrue(all("非@群回复原因" in line and "trigger=direct_word" in line and "reason_source=policy" in line
                            and "命中配置的直接唤醒词或名称" in line for line in logs.output))
        self.assertIn("stage=delivered", logs.output[-1])
        self.assertFalse(event.stopped)
        self.assertTrue(event.call_llm)
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM conversation_parts", ())["state"], "delivered")

    async def test_model_reason_is_logged_and_repeated_poll_does_not_duplicate_it(self):
        async def respond(payload, tools):
            if not any(message["role"] == "tool" for message in payload["messages"]):
                return completion(tools=[command(ACTION, {"mode": "reply", "reason": "群里正在求助，我可以提供解决步骤"})])
            return completion(final_text("可以先检查设置。"))
        self.native.provider.client.state.behavior = respond
        event = self.event("help-reply", "如何处理这个问题？")
        with self.assertLogs("companion_v2.conversation.participation", level="INFO") as logs:
            await self.plugin.receive_companion_message(event)
            batch = self.app.runtime.read_one("SELECT batch_id FROM conversation_batches", ())["batch_id"]
            await self.settle(batch)
            context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
            self.app.tools.group_participation.log_reply_reason(context, batch, stage="delivered")
        self.assertEqual(len(logs.output), 2)
        self.assertTrue(all("群里正在求助，我可以提供解决步骤" in line and "reason_source=model" in line for line in logs.output))
        instruction = self.native.provider.client.state.calls[0][0]["messages"][1]["content"]
        self.assertIn("本轮没有明确 @", instruction)
        self.assertIn("mode=reply", instruction)

    async def test_active_follow_up_keeps_the_running_reply_and_excludes_other_speakers(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(payload, tools):
            entered.set()
            await release.wait()
            return completion(final_text("任务处理完了。"))
        self.native.provider.client.state.behavior = delayed
        await self.plugin.receive_companion_message(self.event("long-task", "处理这个任务", mention=True))
        await asyncio.wait_for(entered.wait(), 3)
        batch = self.app.runtime.read_one("SELECT batch_id FROM conversation_batches", ())["batch_id"]
        follow_up = self.event("follow-up", "再补充一点信息")
        self.assertEqual((await self.candidate(follow_up))["reason"], "active_follow_up")
        self.assertFalse((await self.candidate(self.event("other-speaker", "晚饭吃面", sender="201")))["admitted"])
        await self.plugin.receive_companion_message(follow_up)
        release.set()
        await self.settle(batch)
        self.assertEqual(self.app.messages.batch(batch)["state"], "ready")
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM conversation_parts WHERE batch_id = ?", (batch,))["state"], "delivered")

    async def test_quote_and_natural_follow_up_require_own_confirmed_group_reply(self):
        await self.plugin.receive_companion_message(self.event("first-reply", "说一句", mention=True))
        batch = self.app.runtime.read_one("SELECT batch_id FROM conversation_batches", ())["batch_id"]
        await self.settle(batch)
        reply_id = self.app.runtime.read_one("SELECT platform_ref FROM conversation_parts WHERE batch_id = ?", (batch,))["platform_ref"]
        self.clock.advance(timedelta(seconds=1))
        self.assertEqual((await self.candidate(self.event("natural-follow-up", "再补充一点")))["reason"], "reply_follow_up")
        self.assertFalse((await self.candidate(self.event("other", "晚饭吃面", sender="201")))["admitted"])
        self.assertEqual((await self.candidate(self.event("own-quote", "再补充一点", reply=reply_id)))["reason"], "quoted_reply")
        self.assertFalse((await self.candidate(self.event("wrong-group", "再补充一点", reply=reply_id, target="group-b")))["admitted"])
        self.clock.advance(timedelta(minutes=3))
        self.assertFalse((await self.candidate(self.event("later", "再补充一点")))["admitted"])


if __name__ == "__main__":
    unittest.main()
