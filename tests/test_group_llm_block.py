import unittest
from datetime import timedelta

from companion_v2.conversation.group_llm_block import (
    GroupLLMBlock,
    group_block_key,
    minutes_since,
)
from tests.test_management_access import NOW, ManagementFixture


class GroupLLMBlockTests(ManagementFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.block = GroupLLMBlock(self.runtime, now=lambda: NOW)
        self.key = group_block_key(platform_id="onebot", account_id="login-a",
                                   bot_id="bot-a", group_id="10001")
        self.other = group_block_key(platform_id="onebot", account_id="login-a",
                                     bot_id="bot-a", group_id="10002")

    def test_block_status_and_release_are_per_group_and_replay_safe(self):
        self.assertIsNone(self.block.status(self.key))
        first = self.block.block(self.key, operator="20001", reason="test")
        self.assertEqual(first["state"], "blocked")
        self.assertFalse(first["replayed"])
        self.assertEqual(first["operator"], "20001")
        replay = self.block.block(self.key, operator="20002")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operator"], "20001")
        self.assertIsNone(self.block.status(self.other))
        started = self.block.status(self.key)
        self.assertEqual(started["started_at"], first["started_at"])
        released = self.block.release(self.key, operator="20001")
        self.assertEqual(released["state"], "blocked")
        self.assertIsNone(self.block.status(self.key))
        self.assertIsNone(self.block.release(self.key, operator="20001"))
        # A later block starts a new revision instead of reusing the released one.
        again = self.block.block(self.key, operator="20001")
        self.assertFalse(again["replayed"])
        self.assertGreater(again["revision"], first["revision"])

    def test_status_survives_a_new_reader_for_the_same_runtime(self):
        self.block.block(self.key, operator="20001")
        self.assertIsNotNone(GroupLLMBlock(self.runtime, now=lambda: NOW).status(self.key))

    def test_minutes_since_bounds_and_rejects_unknown_timestamps(self):
        self.assertEqual(minutes_since("2026-09-21T00:00:00+00:00", NOW + timedelta(minutes=90)), 90)
        self.assertIsNone(minutes_since(None, NOW))
        self.assertIsNone(minutes_since("not-a-time", NOW))


if __name__ == "__main__":
    unittest.main()
