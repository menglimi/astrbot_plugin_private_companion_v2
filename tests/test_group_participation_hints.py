"""Participation hints use admitted history, original input time and reply rounds."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import unittest

from companion_v2.conversation.group_timing import short_input_wait
from companion_v2.conversation.participation_prompts import group_hints
from companion_v2.foundation.refs import ScopeKind


NOW = datetime(2026, 9, 27, 10, tzinfo=timezone.utc)


class GroupParticipationHintTests(unittest.TestCase):
    def hints(self, recent=(), batches=None, settings=None, materials=(), sender="200", images=()):
        request = NS(event=NS(received_at=NOW), context=NS(materials=materials), images=images)
        context = NS(actor=NS(principal=NS(native_account_id=sender)))
        return group_hints(request, context, settings or {}, recent, batches or {})

    def test_segmented_reply_is_one_round_and_future_receipts_do_not_count(self):
        recent = [dict(type="confirmed_group_reply", part_id=part, delivered_at=at.isoformat())
                  for part, at in (("a", NOW - timedelta(seconds=2)),
                                   ("b", NOW - timedelta(seconds=1)), ("future", NOW + timedelta(seconds=1)))]
        hint = self.hints(recent, {"a": "round-1", "b": "round-1", "future": "round-2"})
        self.assertIn("有 1 轮已确认 Bot 回复", hint)
        self.assertIn("疲劳参考 1.0 点", hint)
        self.assertIn("距当前输入约 1 秒", hint)

    def test_fatigue_recovers_against_original_input_not_recovery_clock(self):
        recent = [dict(type="confirmed_group_reply", part_id=part, delivered_at=at.isoformat())
                  for part, at in (("a", NOW - timedelta(minutes=91)), ("b", NOW - timedelta(minutes=90)))]
        hint = self.hints(recent, {"a": "round-1", "b": "round-2"})
        self.assertIn("疲劳参考 0.99 点", hint)
        self.assertIn("冷却参考 90 秒", hint)
        self.assertEqual(hint, self.hints(recent, {"a": "round-1", "b": "round-2"}))

    def test_merged_fragments_reduce_interest_once_without_inventing_cold_history(self):
        hint = self.hints(settings={"group_wakeup_cold_group_enabled": True},
                          materials=(NS(purpose="merged_input:2"), NS(purpose="merged_input:3")))
        self.assertIn("已合并当前成员 3 条输入", hint)
        self.assertIn("相对降低 65%", hint)
        self.assertIn("没有可用于估计间隔的此前群历史", hint)
        self.assertNotIn("疲劳参考", hint)

    def test_primary_words_require_authenticated_speaker_and_name_switch_is_independent(self):
        settings = {"group_wakeup_primary_member_ids": '["201"]',
                    "group_wakeup_owner_direct_words": '["专属称呼"]',
                    "group_wakeup_bot_name": "小星", "group_wakeup_bot_name_enabled": False}
        self.assertNotIn("专属称呼", self.hints(settings=settings))
        self.assertIn("专属称呼", self.hints(settings=settings, sender="201"))
        self.assertNotIn("小星", self.hints(settings=settings, sender="201"))
        self.assertNotIn("群唤醒参考", self.hints(settings={"group_wakeup_enabled": False}))

    def test_group_image_is_only_a_prompt_hint_for_current_authorized_images(self):
        settings = {"group_wakeup_image_enabled": True, "group_wakeup_image_weight": 0.35}
        self.assertNotIn("图片中与你明确兴趣", self.hints(settings=settings))
        hint = self.hints(settings=settings, images=(object(),))
        self.assertIn("图片中与你明确兴趣", hint)
        self.assertIn("参考权重 35%", hint)
        self.assertIn("不要求接话", hint)

    def test_media_labels_and_thread_metadata_are_not_group_interest_evidence(self):
        hint = self.hints()
        self.assertIn("不是成员表达、兴趣词、情绪或复读内容", hint)
        self.assertIn("话题标题、线程签名等路由元数据也不是兴趣证据", hint)
        self.assertIn("图片只能在单独开启图片唤醒后作为额外线索", hint)

    def test_only_possible_plain_group_fragments_wait(self):
        event = NS(scope=NS(kind=ScopeKind.GROUP))
        self.assertEqual(short_input_wait(event, "[提及机器人] 瓦", {}), 15)
        for text in ("", "好", "晚安", "你好", "抱抱", "谢谢", "瓦？", "我要问你"):
            with self.subTest(text=text):
                self.assertEqual(short_input_wait(event, text, {}), 0)
        self.assertEqual(short_input_wait(event, "瓦", {"group_wakeup_enabled": False}), 0)
        self.assertEqual(short_input_wait(event, "瓦", {"group_wakeup_short_text_wait_ms": 0}), 0)
        for field in ("images", "quotes", "forwards", "audios", "videos"):
            self.assertEqual(short_input_wait(NS(scope=event.scope, **{field: (object(),)}), "瓦", {}), 0)
        self.assertEqual(short_input_wait(NS(scope=NS(kind=ScopeKind.PRIVATE)), "瓦", {}), 0)


if __name__ == "__main__":
    unittest.main()
