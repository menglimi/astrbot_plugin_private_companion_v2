"""Small, model-free checks for V1 issues addressed by the V2 pathways."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.conversation.group_admission import GroupReplyAdmission
from companion_v2.foundation.outcome import Outcome
from companion_v2.memory.time_intent import absolute_day_window
from astrbot_host.core_reply_context import _memory_materials


NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


class AbsoluteMemoryDayTests(unittest.TestCase):
    def test_chinese_numeric_and_iso_dates_share_the_same_local_day(self):
        for question in ("七月二十四号我们聊了什么", "7月24号我们聊了什么", "2026-07-24聊过什么"):
            with self.subTest(question=question):
                start, end = absolute_day_window(question, NOW, "Asia/Shanghai")
                self.assertEqual((start.isoformat(), end.isoformat()),
                                 ("2026-07-24T00:00:00+08:00", "2026-07-25T00:00:00+08:00"))

    def test_yearless_day_uses_last_nonfuture_occurrence(self):
        start, _ = absolute_day_window("12月31日还记得吗", NOW, "Asia/Shanghai")
        self.assertEqual(start.date().isoformat(), "2025-12-31")
        self.assertIsNone(absolute_day_window("2026-10-20聊了什么", NOW, "Asia/Shanghai"))
        self.assertIsNone(absolute_day_window("明天要干嘛", NOW, "Asia/Shanghai"))

    def test_core_reply_uses_date_filter_in_the_real_query_path(self):
        calls = []

        def query(*args, **kwargs):
            calls.append(kwargs)
            return Outcome.success({"items": [{"atom_id": "fact-1", "revision": 1}]})

        access = SimpleNamespace(check=lambda context: None, policy_for=lambda context:
                                 SimpleNamespace(automatic_context=True, context_items=2, query_items=2))
        memory = SimpleNamespace(writer=SimpleNamespace(access=access),
            runtime=SimpleNamespace(read_one=lambda *args: None),
            query=SimpleNamespace(begin=lambda *args, **kwargs: None, query=query))
        owner = SimpleNamespace(memory=memory, delegated=lambda: False,
                                contributions=lambda snapshot, context: snapshot)
        native_input = SimpleNamespace(event_id="date-question", text="七月二十四号我们聊了什么")
        with (patch("companion_v2.memory.habits.habit_capture", return_value=()),
              patch("companion_v2.memory.models.owner_key", return_value="test-owner"),
              patch("companion_v2.memory.pinned.select_pinned", return_value=((), 0))):
            snapshot = _memory_materials(owner, SimpleNamespace(key="private-route"),
                                         native_input, NOW, "Asia/Shanghai")
        self.assertEqual(snapshot["references"], [{"atom_id": "fact-1", "revision": 1}])
        self.assertEqual(calls[0]["query_intent"], "")
        self.assertEqual(calls[0]["time_start"].isoformat(), "2026-07-24T00:00:00+08:00")
        self.assertEqual(calls[0]["time_end"].isoformat(), "2026-07-25T00:00:00+08:00")


class GroupFollowUpTests(unittest.TestCase):
    def setUp(self):
        self.admission = GroupReplyAdmission.__new__(GroupReplyAdmission)
        self.admission.observations = {"current": []}
        self.admission._key = lambda context: "current"
        self.context = SimpleNamespace(key="group-route", scope=SimpleNamespace(key="group-scope"),
                                       actor=SimpleNamespace(
            principal=SimpleNamespace(native_account_id="member-b")))
        self.turn = {"context_key": "prior-member-route", "scope_key": "group-scope",
                     "speaker_id": "member-a",
                     "reason": "mention", "state": "completed", "send_state": "returned",
                     "returned_at": "2026-10-19T00:00:00+00:00"}

    def test_first_other_member_can_continue_a_returned_bot_turn(self):
        self.admission.observations["current"].append({
            "speaker_id": "member-b", "event_id": "answer",
            "received_at": "2026-10-19T00:00:20+00:00"})
        self.assertEqual(self.admission._core_continuation(
            self.context, self.turn, datetime(2026, 10, 19, 0, 0, 20, tzinfo=timezone.utc),
            event_id="answer"),
            "reply_follow_up")

    def test_intervening_member_message_ends_the_short_continuation(self):
        self.admission.observations["current"].append({
            "speaker_id": "member-c", "event_id": "earlier",
            "received_at": "2026-10-19T00:00:20+00:00"})
        self.assertEqual(self.admission._core_continuation(
            self.context, self.turn, datetime(2026, 10, 19, 0, 0, 20, tzinfo=timezone.utc),
            event_id="answer"), "")


if __name__ == "__main__":
    unittest.main()
