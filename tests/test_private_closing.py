"""The deterministic private closing guard is conservative and has no side effects."""

from datetime import datetime, timedelta, timezone
import unittest

from companion_v2.configuration.models import ConfigurationError
from companion_v2.conversation import private_closing as closing


NOW = datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc)


def dialogue(*items):
    return [
        {"speaker": "user", "text": text, "at": (NOW - timedelta(seconds=60)).isoformat()}
        if index == 0 else
        {"speaker": "assistant", "text": text, "at": (NOW - timedelta(seconds=30)).isoformat()}
        for index, text in enumerate(items)
    ]


class PrivateClosingDetectionTests(unittest.TestCase):
    def test_pure_closings_cover_goodnight_farewell_thanks_ack_and_english(self):
        for text, expected in (
            ("晚安", ("goodnight",)),
            ("晚安啦", ("goodnight",)),
            ("晚安，明天见", ("goodnight", "farewell")),
            ("谢谢，晚安", ("thanks", "goodnight")),
            ("晚安宝贝", ("goodnight",)),
            ("好哒，我去睡了", ("ack", "goodnight")),
            ("那我也睡了，晚安", ("goodnight",)),
            ("晚安，做个好梦", ("goodnight",)),
            ("晚安，你也是", ("goodnight",)),
            ("晚安，明天还要早起", ("goodnight",)),
            ("睡咯", ("goodnight",)),
            ("白白", ("farewell",)),
            ("晚安，么么", ("goodnight", "affection")),
            ("good night", ("goodnight",)),
            ("拜拜", ("farewell",)),
            ("早点休息", ("goodnight",)),
            ("嗯嗯", ("ack",)),
            ("好的", ("ack",)),
            ("早安", ("morning",)),
        ):
            with self.subTest(text=text):
                self.assertEqual(closing.closing_categories(text), expected)

    def test_questions_requests_media_and_new_content_are_not_closings(self):
        for text in ("晚安，明天记得叫我", "晚安我睡不着", "今天好累", "晚安？",
                     "好，我去", "晚安，还有件事想和你说", "23:00 晚安", ""):
            with self.subTest(text=text):
                self.assertEqual(closing.closing_categories(text), ())
                self.assertFalse(closing.is_closing(text))

    def test_role_message_must_end_in_a_strong_closing_without_a_question(self):
        for text in ("晚安，好好休息", "今天辛苦啦，早点睡", "晚安啦", "晚安，明天见",
                     "good night", "早点休息"):
            with self.subTest(text=text):
                self.assertTrue(closing.role_closed(text))
        for text in ("晚安，明天要我提醒你吗？", "好的", "嗯嗯", "今天怎么样",
                     "明天早点睡然后叫我", ""):
            with self.subTest(text=text):
                self.assertFalse(closing.role_closed(text))


class PrivateClosingDecisionTests(unittest.TestCase):
    def test_role_closed_within_window_suppresses_the_second_goodnight(self):
        decision = closing.closing_decision(
            closing.Settings(), dialogue("我睡了", "晚安，好梦"),
            current_text="晚安", at=NOW)
        self.assertTrue(decision["suppress_reply"])
        self.assertEqual(decision["action"], "silent")
        self.assertEqual(decision["reason"], "role_already_closed")
        self.assertEqual(decision["categories"], ("goodnight",))

    def test_repeated_user_closing_suppresses_even_when_role_did_not_close(self):
        decision = closing.closing_decision(
            closing.Settings(), dialogue("晚安", "这么早？"),
            current_text="晚安", at=NOW)
        self.assertTrue(decision["suppress_reply"])
        self.assertEqual(decision["reason"], "repeated_user_closing")
        self.assertFalse(decision["last_assistant_closing"])
        self.assertTrue(decision["prior_user_closing"])

    def test_new_content_and_media_are_never_suppressed(self):
        items = dialogue("我睡了", "晚安，好梦")
        for text, media in (("晚安，明天七点叫我", False), ("晚安", True), ("我睡不着", False)):
            with self.subTest(text=text, media=media):
                decision = closing.closing_decision(
                    closing.Settings(), items, current_text=text, at=NOW, has_media=media)
                self.assertFalse(decision["suppress_reply"])

    def test_window_and_missing_history_fail_open(self):
        items = dialogue("我睡了", "晚安，好梦")
        late = closing.closing_decision(
            closing.Settings(), items, current_text="晚安", at=NOW + timedelta(hours=1))
        self.assertFalse(late["suppress_reply"])
        self.assertEqual(late["reason"], "outside_window")
        empty = closing.closing_decision(
            closing.Settings(), (), current_text="晚安", at=NOW)
        self.assertFalse(empty["suppress_reply"])
        self.assertEqual(empty["reason"], "no_role_reply")
        broken = closing.closing_decision(
            closing.Settings(), [{"speaker": "assistant", "text": "晚安"}],
            current_text="晚安", at=NOW)
        self.assertFalse(broken["suppress_reply"])
        self.assertEqual(broken["reason"], "history_time_unknown")

    def test_disabled_guard_returns_no_suppression(self):
        decision = closing.closing_decision(
            closing.Settings(enabled=False), dialogue("我睡了", "晚安"), current_text="晚安", at=NOW)
        self.assertFalse(decision["suppress_reply"])
        self.assertEqual(decision["reason"], "disabled")

    def test_instruction_is_only_for_visible_closing_context(self):
        strong = closing.closing_decision(
            closing.Settings(), dialogue("我睡了", "晚安，好梦"),
            current_text="晚安，明天七点叫我", at=NOW)
        self.assertIn("对话收尾", closing.closing_instruction(closing.Settings(), strong))
        self.assertEqual(closing.closing_instruction(
            closing.Settings(prompt_enabled=False), strong), "")
        quiet = closing.closing_decision(
            closing.Settings(), dialogue("今天好累", "好，那你先忙"), current_text="好", at=NOW)
        self.assertEqual(closing.closing_instruction(closing.Settings(), quiet), "")


class PrivateClosingSettingsTests(unittest.TestCase):
    def test_defaults_validate_and_bounds_are_enforced(self):
        settings = closing.Settings.from_values({})
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.window_seconds, 1800)
        self.assertTrue(settings.prompt_enabled)
        for values in (
            {"private_closing_guard_enabled": 1},
            {"private_closing_guard_prompt_enabled": "yes"},
            {"private_closing_guard_window_seconds": 30},
            {"private_closing_guard_window_seconds": 7201},
            {"private_closing_guard_window_seconds": True},
        ):
            with self.subTest(values=values), self.assertRaises(ConfigurationError):
                closing.Settings.from_values(values)


if __name__ == "__main__":
    unittest.main()
