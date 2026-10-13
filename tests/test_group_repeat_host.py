"""Literal V1-style group repeats through V2 admission, with no model reply."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from PIL import Image as PillowImage

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.conversation.participation import (
    CONFIG_DEFAULTS, CONFIG_GROUP, GroupParticipationConfigurationOwner, configuration_fields,
)
from companion_v2.conversation.repeat_actions import GroupRepeatActions
from companion_v2.conversation.group_timing import repeat_burst, repeat_signature
from companion_v2.foundation.outcome import Outcome
from tests.group_host_support import GroupFixture, group_config
from tests.test_main_no_reply import ENTRY


class RepeatSignatureTests(unittest.TestCase):
    def test_media_labels_and_trailing_punctuation_never_supply_a_signature(self):
        for text in ("[图片]", "【图片】", "图片！", "图片？", "[图片 2]", "[图片1]", "【图片2】", "[图片不可用]",
                     "[语音]", "【语音 1】", "【视频】", "[文件]", "[合并转发]",
                     "[引用消息]", "[分享卡片]", "[图片] [图片 2]", "？？？"):
            with self.subTest(text=text):
                self.assertEqual(repeat_signature(text), "")
        self.assertEqual(repeat_signature("星渊没有变成妹妹！"), "星渊没有变成妹妹")
        self.assertEqual(repeat_signature("笑死 [图片]"), "笑死")

    def test_other_text_and_media_break_a_continuous_burst(self):
        from datetime import datetime, timezone
        at = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        for other in ("其他话题", "[图片]", ""):
            items = [{"kind": "member", "text": text, "speaker_id": str(index),
                      "received_at": (at - timedelta(seconds=5-index)).isoformat()}
                     for index, text in enumerate(("好", "好", other, "好", "好"))]
            burst = repeat_burst("好", items, at=at, window_seconds=120)
            self.assertEqual((burst["count"], burst["distinct"]), (2, 2))


class GroupRepeatHostTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = self.make_controller(group_config(group_delivery_mode="onebot_group"))
        self.app = await self.start_host()
        self.plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        self.plugin.staging = self.controller
        self.sequence = 0
        self.context = await self.configure()

    def event(self, text, *, identifier=None, sender="200", target="group-a", mention=None):
        self.sequence += 1
        event = self.group_event(identifier=identifier or "repeat-event-" + str(self.sequence),
                                 text=text, sender=sender, target=target)
        event.stopped = False
        event.stop_event = lambda: setattr(event, "stopped", True)
        if mention is not None:
            event.message_obj.message.insert(0, NS(type="At", qq=mention))
        return event

    async def configure(self, *, target="group-a", **changes):
        context = (await self.controller.observe_group_early(self.event("配置前的普通消息", target=target))).unwrap()
        owner, fields = GroupParticipationConfigurationOwner(self.app.runtime), configuration_fields()
        config_target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW,
                                     context.role_binding.role, context.scope)
        changes = {"enable_group_interjection": False, "group_repeat_trigger_threshold": 3,
                   "group_repeat_follow_probability": .8, "group_repeat_interrupt_probability": 0,
                   "group_repeat_interrupt_probability_step": .12, "group_interject_max_daily": 20, **changes}
        owner.write(config_target, fields, changes={CONFIG_GROUP + "." + key: value for key, value in changes.items()},
                    reset=(), expected_revision=owner.read(config_target, fields).revision, observed_at=self.clock.now())
        return context

    async def warm(self, text="星渊没有变成妹妹", *, target="group-a", senders=("201", "202")):
        for sender in senders:
            self.clock.advance(timedelta(seconds=1))
            event = self.event(text, sender=sender, target=target)
            await self.plugin.observe_companion_group_early(event)
            decision = (await self.controller.group_reply_candidate(event)).unwrap()
            self.assertNotEqual(decision["reason"], "repeat")
        self.clock.advance(timedelta(seconds=1))
        return self.event(text, target=target)

    async def act(self, event, *, roll=.5):
        with patch("companion_v2.conversation.repeat_actions.random.random", return_value=roll):
            await self.plugin.receive_companion_message(event)
        self.assertFalse(event.stopped)
        self.assertTrue(event.call_llm)  # AstrBot's flag suppresses the default model fallback.
        self.assertIsNone(event.get_extra(CORE_REPLY_CONTEXT_EXTRA))
        self.assert_no_model()

    def assert_no_model(self):
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_parts", ()), ())

    def sent_text(self, event):
        self.assertEqual(len(event.sent), 1)
        self.assertEqual(len(event.sent[0].chain), 1)
        self.assertEqual(event.sent[0].chain[0].type.value, "Plain")
        return event.sent[0].chain[0].text

    async def test_follow_sends_only_the_original_line_without_building_model_context(self):
        event = await self.warm("星渊没有变成妹妹！")
        with patch("astrbot_host.core_reply_context.build_core_reply_prompt") as build:
            await self.act(event)
        build.assert_not_called()
        self.assertEqual(self.sent_text(event), "星渊没有变成妹妹！")
        saved = self.app.tools.group_participation.admission.recorded_core_reply(self.context, event.message_obj.message_id)
        self.assertEqual((saved["reason"], saved["send_returns"], saved["participation"]["act"]),
                         ("repeat", 1, "repeat_follow"))

    async def test_interrupt_sends_only_the_custom_phrase(self):
        await self.configure(group_repeat_follow_probability=0, group_repeat_interrupt_probability=.8,
                             group_repeat_interrupt_text="复读机休息一下啦")
        event = await self.warm()
        await self.act(event, roll=.1)
        self.assertEqual(self.sent_text(event), "复读机休息一下啦")

    async def test_valid_interrupt_image_is_sent_alone_and_invalid_images_fall_back(self):
        image = self.root / "打断图.png"
        PillowImage.new("RGB", (2, 2), "blue").save(image)
        invalid = self.root / "伪图片.png"
        invalid.write_text("not an image", encoding="utf-8")
        for index, path in enumerate((image, self.root / "缺失.png", invalid)):
            with self.subTest(path=path.name):
                await self.configure(group_repeat_follow_probability=0, group_repeat_interrupt_probability=.8,
                    group_repeat_interrupt_text="请停止复读", group_repeat_interrupt_image_path=str(path))
                event = await self.warm("原句" + str(index))
                await self.act(event, roll=.1)
                if index == 0:
                    self.assertEqual(len(event.sent[0].chain), 1)
                    self.assertEqual(event.sent[0].chain[0].type.value, "Image")
                else:
                    self.assertEqual(self.sent_text(event), "请停止复读")

    async def test_a_missed_draw_and_a_repeated_event_never_fall_back_to_normal_reply(self):
        event = await self.warm()
        with patch("companion_v2.conversation.repeat_actions.random.random", return_value=.99) as draw:
            await self.plugin.receive_companion_message(event)
            await self.plugin.receive_companion_message(event)
        self.assertEqual(draw.call_count, 1)
        self.assertEqual(event.sent, [])
        self.assertTrue(event.call_llm)
        self.assertIsNone(event.get_extra(CORE_REPLY_CONTEXT_EXTRA))
        self.assert_no_model()
        self.clock.advance(timedelta(seconds=1))
        continued = self.event("星渊没有变成妹妹")
        await self.act(continued, roll=.85)  # Initial .8 miss grows both tendencies.
        self.assertEqual(self.sent_text(continued), "星渊没有变成妹妹")

    async def test_each_burst_acts_once_and_concurrent_handlers_send_once(self):
        event = await self.warm()
        admission = (await self.controller.group_reply_candidate(event)).unwrap()
        with patch("companion_v2.conversation.repeat_actions.random.random", return_value=.5):
            results = await asyncio.gather(*(self.controller.receive_group_repeat(event, admission) for _ in range(2)))
        self.assertTrue(all(result.is_success for result in results))
        self.assertEqual(self.sent_text(event), "星渊没有变成妹妹")
        self.clock.advance(timedelta(seconds=1))
        more = self.event("星渊没有变成妹妹", sender="203")
        await self.act(more, roll=.1)
        self.assertEqual(more.sent, [])

    async def test_same_timestamp_counts_distinct_events_but_never_counts_one_event_twice(self):
        first = self.event("同秒复读")
        for _ in range(2):
            self.assertFalse((await self.controller.group_reply_candidate(first)).unwrap()["admitted"])
        second = self.event("同秒复读")
        self.assertFalse((await self.controller.group_reply_candidate(second)).unwrap()["admitted"])
        third = self.event("同秒复读")
        self.assertEqual((await self.controller.group_reply_candidate(third)).unwrap()["reason"], "repeat")
        await self.act(third)
        self.assertEqual(self.sent_text(third), "同秒复读")
        break_event = self.event("切换话题")
        await self.controller.group_reply_candidate(break_event)
        for _ in range(2):
            self.assertFalse((await self.controller.group_reply_candidate(self.event("同秒复读"))).unwrap()["admitted"])
        new_burst = self.event("同秒复读")
        await self.act(new_burst)
        self.assertEqual(self.sent_text(new_burst), "同秒复读")

    async def test_distinct_member_mode_and_probability_step_match_v1(self):
        await self.configure(group_repeat_count_distinct_users_only=True, group_repeat_follow_probability=0,
                             group_repeat_interrupt_probability=0, group_repeat_interrupt_probability_step=.2)
        for _ in range(4):
            self.clock.advance(timedelta(seconds=1))
            same_member = self.event("多人复读", sender="200")
            self.assertFalse((await self.controller.group_reply_candidate(same_member)).unwrap()["admitted"])
        self.clock.advance(timedelta(seconds=1))
        self.assertFalse((await self.controller.group_reply_candidate(self.event("多人复读", sender="201"))).unwrap()["admitted"])
        self.clock.advance(timedelta(seconds=1))
        third_member = self.event("多人复读", sender="202")
        await self.act(third_member, roll=.99)
        self.assertEqual(third_member.sent, [])
        self.clock.advance(timedelta(seconds=1))
        repeat_member = self.event("多人复读", sender="202")
        await self.act(repeat_member, roll=.99)
        self.clock.advance(timedelta(seconds=1))
        no_extra_step = self.event("多人复读", sender="202")
        await self.act(no_extra_step, roll=.5)
        self.assertEqual(no_extra_step.sent, [])
        self.clock.advance(timedelta(seconds=1))
        fourth_member = self.event("多人复读", sender="203")
        await self.act(fourth_member, roll=.3)
        self.assertEqual(self.sent_text(fourth_member), "多人复读")

    async def test_unknown_send_is_not_replayed_even_after_new_observations(self):
        event = await self.warm()
        attempts = []

        async def uncertain_send(message):
            attempts.append(message)
            raise TimeoutError("unknown platform outcome")

        event.send = uncertain_send
        await self.act(event)
        actions = GroupRepeatActions(self.app.runtime)
        saved = actions.read(self.context, event.message_obj.message_id)
        self.assertEqual(saved["state"], "unknown")
        for index in range(130):
            actions.plan(self.context, "other-" + str(index), "无复读", at=self.clock.now(), burst=None,
                settings=CONFIG_DEFAULTS, used_today=0, timezone_name="Asia/Shanghai")
        replay = self.event("星渊没有变成妹妹", identifier=event.message_obj.message_id)
        await self.act(replay, roll=.1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(replay.sent, [])
        self.assertEqual(actions.read(self.context, event.message_obj.message_id)["state"], "unknown")

    async def test_repeat_does_not_open_active_or_completed_follow_up(self):
        event = await self.warm()
        ledger = self.app.tools.group_participation.admission

        async def inspect_inflight(_message):
            self.clock.advance(timedelta(seconds=1))
            during = self.event("再补充一点")
            self.assertFalse((await self.controller.group_reply_candidate(during)).unwrap()["admitted"])

        event.send = inspect_inflight
        await self.act(event)
        self.clock.advance(timedelta(seconds=1))
        for text in ("再补充一点", "[图片]"):
            follow_up = self.event(text)
            self.assertFalse((await self.controller.group_reply_candidate(follow_up)).unwrap()["admitted"])
        saved = ledger.recorded_core_reply(self.context, event.message_obj.message_id)
        self.assertEqual((saved["reason"], saved["state"]), ("repeat", "completed"))

    async def test_media_only_messages_never_trigger_and_break_an_existing_burst(self):
        for text in ("[图片]", "【图片 2】", "[图片1]", "[语音]", "图片！", "图片？"):
            for _ in range(3):
                self.clock.advance(timedelta(seconds=1))
                event = self.event(text)
                self.assertFalse((await self.controller.group_reply_candidate(event)).unwrap()["admitted"])
        await self.warm("好")
        media = self.event("")
        media.message_obj.message = [NS(type="Image", url="https://fixture.invalid/image.png")]
        media.message_obj.raw_message["message"] = [
            {"type": "image", "data": {"url": "https://fixture.invalid/image.png"}},
        ]
        await self.plugin.observe_companion_group_early(media)
        self.clock.advance(timedelta(seconds=1))
        after_media = self.event("好")
        self.assertFalse((await self.controller.group_reply_candidate(after_media)).unwrap()["admitted"])
        self.assert_no_model()

    async def test_directed_messages_keep_their_original_admission_instead_of_repeat(self):
        event = await self.warm()
        event.message_obj.message.insert(0, NS(type="At", qq="100"))
        self.assertEqual((await self.controller.group_reply_candidate(event)).unwrap()["reason"], "mention")
        self.clock.advance(timedelta(seconds=1))
        to_member = self.event("星渊没有变成妹妹", mention="999")
        self.assertFalse((await self.controller.group_reply_candidate(to_member)).unwrap()["admitted"])
        self.assert_no_model()

    async def test_repeated_questions_use_the_two_actions_instead_of_a_model_answer(self):
        event = await self.warm("这是怎么回事？")
        self.assertEqual((await self.controller.group_reply_candidate(event)).unwrap()["reason"], "repeat")
        await self.act(event)
        self.assertEqual(self.sent_text(event), "这是怎么回事？")

    async def test_repeat_counter_isolated_by_group_and_persona(self):
        await self.warm("好")
        other = self.event("好", target="group-b")
        self.assertFalse((await self.controller.group_reply_candidate(other)).unwrap()["admitted"])
        self.native.selections["qq-main"] = "second"
        changed_role = self.event("好")
        self.assertFalse((await self.controller.group_reply_candidate(changed_role)).unwrap()["admitted"])
        self.assert_no_model()

    async def test_repeat_quota_and_other_native_interjections_share_the_daily_limit(self):
        await self.configure(group_interject_max_daily=2)
        first = await self.warm("第一句")
        await self.act(first)
        ledger = self.app.tools.group_participation.admission
        # Use the exact current instruction as real native records do.
        prepared = (await self.controller.prepare_core_reply(self.event("普通接话"))).unwrap()
        ledger.record_core_reply(self.context, "ordinary-shared", instruction=prepared["instruction"],
                                 reason="interjection", mentioned=False, at=self.clock.now())
        ledger.mark_core_reply(self.context, "ordinary-shared", stage="send_returned", at=self.clock.now())
        ledger.mark_core_reply(self.context, "ordinary-shared", stage="completed", at=self.clock.now())
        capped = await self.warm("第二句")
        await self.act(capped)
        self.assertEqual(capped.sent, [])
        self.clock.advance(timedelta(days=1))
        next_day = await self.warm("第二句")
        await self.act(next_day)
        self.assertEqual(self.sent_text(next_day), "第二句")

    async def test_send_authorization_is_rechecked_and_tracking_failure_does_not_block_send(self):
        event = await self.warm("撤销测试")
        with patch.object(self.controller, "authorize_core_reply", return_value=Outcome.failed("permission_revoked", "revoked")):
            await self.act(event)
        self.assertEqual(event.sent, [])
        another = await self.warm("记录测试")
        with patch.object(self.app.tools.group_participation.admission, "mark_core_reply", side_effect=OSError("tracking unavailable")):
            await self.act(another)
        self.assertEqual(self.sent_text(another), "记录测试")

    async def test_repeat_preparation_failure_keeps_the_default_model_suppressed(self):
        event = await self.warm("准备失败测试")
        with patch.object(self.controller, "prepare_core_reply", return_value=Outcome.failed("host_core_reply_prepare_failed", "unavailable")):
            await self.plugin.receive_companion_message(event)
        self.assertTrue(event.call_llm)
        self.assertEqual(event.sent, [])
        self.assertIsNone(event.get_extra(CORE_REPLY_CONTEXT_EXTRA))
        self.assert_no_model()

    async def test_blank_image_path_is_valid_but_control_characters_are_rejected(self):
        await self.configure(group_repeat_interrupt_image_path="")
        with self.assertRaises(ConfigurationError):
            await self.configure(group_repeat_interrupt_image_path="bad\npath.png")
        with self.assertRaises(ConfigurationError):
            await self.configure(group_repeat_interrupt_image_path="x" * 4097)


if __name__ == "__main__":
    unittest.main()
