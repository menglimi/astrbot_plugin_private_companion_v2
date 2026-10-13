"""Regression cases for the actual high-frequency group wakeup log."""

from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.participation import (CONFIG_GROUP, GroupParticipationConfigurationOwner,
                                                    configuration_fields as participation_fields)
from companion_v2.conversation.reply_settings import ReplyConfigurationOwner, configuration_fields, target_for
from companion_v2.decision.prompt import build_state, decision_questions, render_model_state
from tests.group_host_support import GroupFixture, group_config
from tests.test_main_no_reply import ENTRY


class GroupWakeupBoundaryTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = self.make_controller(group_config(group_delivery_mode="onebot_group"))
        self.app = await self.start_host()
        self.plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        self.plugin.staging = self.controller

    def event(self, identifier, text, *, sender="200", mention=False):
        event = self.group_event(identifier=identifier, text=text, sender=sender)
        event.is_at_or_wake_command = event.is_wake = False
        if mention:
            event.message_obj.message.insert(0, NS(type="At", qq="100"))
        return event

    async def configure(self, **changes):
        context = (await self.controller.observe_group_early(self.event("settings", "设置"))).unwrap()
        owner = ReplyConfigurationOwner(self.app.runtime)
        common = self.controller.settings.common
        fields = configuration_fields(common.segmentation, common.streaming, common.policy.part_gap_seconds)
        target = target_for(context)
        owner.write(target, fields, changes={"conversation.presentation." + key: value for key, value in changes.items()},
                    reset=(), expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        return context

    async def test_default_and_closed_questions_do_not_call_laya_or_main_model(self):
        with patch.object(ENTRY, "prepare_core_reply_decision", new_callable=AsyncMock) as decision:
            for index, text in enumerate(("机器人就是用来超的", "bot 又坏了", "我们真的能打吗", "怎么一股ds味", "有没有这个", "谁知道如何修复这个错误？")):
                event = self.event("default-" + str(index), text)
                await self.plugin.receive_companion_message(event)
                self.assertTrue(event.call_llm, text)
                self.assertFalse(event.is_at_or_wake_command, text)
            decision.assert_not_called()
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_disabling_question_cannot_be_reopened_by_interjection(self):
        context = await self.configure(group_wakeup_question_enabled=False)
        owner, fields = GroupParticipationConfigurationOwner(self.app.runtime), participation_fields()
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)
        owner.write(target, fields, changes={CONFIG_GROUP + ".enable_group_interjection": True}, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())
        result = (await self.controller.group_reply_candidate(self.event("no-question-bypass", "有没有人知道怎么配置这个插件？"))).unwrap()
        self.assertFalse(result["admitted"])

    async def test_enabled_questions_use_threshold_and_short_reactions_remain_silent(self):
        await self.configure(group_wakeup_question_enabled=True, group_wakeup_question_threshold=95)
        ordinary = (await self.controller.group_reply_candidate(self.event("below", "有没有人知道怎么配置这个插件？"))).unwrap()
        self.assertFalse(ordinary["admitted"])
        urgent = (await self.controller.group_reply_candidate(self.event("urgent", "急求，插件启动报错，谁知道怎么修复？"))).unwrap()
        self.assertEqual(urgent["reason"], "question")
        await self.configure(group_wakeup_question_threshold=65)
        for index, text in enumerate(("我们真的能打吗", "怎么一股ds味", "为啥？", "这是什么情况？")):
            result = (await self.controller.group_reply_candidate(self.event("reaction-" + str(index), text))).unwrap()
            self.assertFalse(result["admitted"], text)
        public = (await self.controller.group_reply_candidate(self.event("help", "谁知道如何修复这个错误？"))).unwrap()
        self.assertEqual(public["reason"], "question")
        self.assertTrue(public["participation_policy"]["question_enabled"])

    async def test_explicit_calls_and_context_words_are_independent_opt_ins(self):
        await self.configure(group_wakeup_question_enabled=False, group_wakeup_bot_name="小星",
                             group_wakeup_context_words=json.dumps(["星图"], ensure_ascii=False))
        for event, reason in ((self.event("at", "怎么一股ds味", mention=True), "mention"),
                              (self.event("name", "小星帮我看看"), "direct_word"),
                              (self.event("context", "这个星图挺好看"), "context_word")):
            result = (await self.controller.group_reply_candidate(event)).unwrap()
            self.assertEqual(result["reason"], reason)
            self.assertFalse(result["participation_policy"]["question_enabled"])

    async def test_intervening_other_member_prevents_inflight_followup(self):
        event = self.event("first", "帮我看看", mention=True)
        await self.plugin.receive_companion_message(event)
        self.clock.advance(timedelta(seconds=1))
        await self.controller.observe_group_early(self.event("other", "这个我来回答", sender="201"))
        self.clock.advance(timedelta(seconds=1))
        result = (await self.controller.group_reply_candidate(self.event("changed-topic", "晚饭吃什么"))).unwrap()
        self.assertFalse(result["admitted"])


class LayaRenderedContextTests(unittest.TestCase):
    def test_followup_classifier_gets_labeled_recent_exchange_without_replaying_it_as_current(self):
        facts = {"scope_kind": "group", "user_text": "明天吃什么呢", "speaker_id": "甲",
                 "candidate_reason": "reply_follow_up",
                 "recent_group_messages": [{"speaker_id": "甲", "text": "如何设置分段回复？"},
                                           {"speaker_id": "乙", "text": "我来回答你"}],
                 "recent_group_bot_messages": [{"returned_at": "2026-10-11T12:00:01+00:00",
                                                 "text": "你是想问周末聚餐去哪里吗？"}]}
        model = json.loads(render_model_state(build_state(facts)))["facts"]
        self.assertEqual(model["user_text"], facts["user_text"])
        context = model["past_group_context"]
        self.assertEqual([item["speaker"] for item in context], ["当前发言者", "其他群成员", "机器人"])
        self.assertIn("如何设置分段回复？", context[0]["message"])
        self.assertIn("周末聚餐", context[-1]["message"])
        self.assertNotIn("past_group_activity", model)
        self.assertEqual(json.loads(build_state(facts))["facts"]["recent_group_messages"], facts["recent_group_messages"])
        action = decision_questions(facts, {"action": True})["action"]
        self.assertIn("历史仅用于辨认上下文", action["instructions"])

    def test_private_classifier_gets_recent_dialogue_as_labeled_context(self):
        facts = {"scope_kind": "private", "user_text": "那周日呢？",
                 "recent_private_messages": [{"role": "user", "text": "我周末准备去杭州"},
                                             {"role": "assistant", "text": "可以看看西湖"}]}
        model = json.loads(render_model_state(build_state(facts)))["facts"]
        self.assertEqual(model["user_text"], "那周日呢？")
        self.assertEqual([item["speaker"] for item in model["past_private_context"]], ["用户", "机器人"])
        self.assertEqual(model["past_private_context"][0]["message"], "我周末准备去杭州")
        self.assertEqual(model["past_private_context"][1]["message"], "可以看看西湖")

    def test_closed_switches_and_wakeup_evidence_reach_actual_model_text(self):
        facts = {"scope_kind": "group", "user_text": "机器人就是用来超的", "candidate_reason": "context_word",
                 "group_participation_policy": {"question_enabled": False, "interjection_enabled": False},
                 "recent_bot_send_returns": [{"seconds_ago": 10}],
                 "recent_group_messages": [{"speaker_id": "甲", "text": "乙我来回答你"}]}
        model_text = render_model_state(build_state(facts))
        for text in ("context_word", "本群不开启未点名答疑和自主插话", "past_group_context",
                     "其他群成员", "乙我来回答你"):
            self.assertIn(text, model_text)
        model = json.loads(model_text)["facts"]
        self.assertEqual(model["group_participation_policy"], facts["group_participation_policy"])
        self.assertEqual(model["recent_bot_send_returns"], [{"seconds_ago": 10}])
        action = decision_questions(facts, {"action": True})["action"]
        self.assertNotIn("interject", action["criteria"])
        self.assertIn("本群已关闭答疑", action["instructions"])
