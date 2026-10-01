from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from companion_v2.memory.group.hits import (
    DEFAULT_GROUP_SAFETY_POLICY,
    GroupSafetyPolicy,
    RULE_IMPERSONATED_BOT_NAME,
    RULE_MENTION_BOMBARDMENT,
    RULE_REPEATED_MESSAGE,
    RULE_VERIFICATION_OR_PAYMENT,
    evaluate_message,
    persist_hits,
)
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V40_TO_V41_ID,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V40,
)


NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class GroupMemberSafetyRuleTests(unittest.TestCase):
    def test_rules_are_bounded_and_do_not_flag_normal_text(self):
        hits = evaluate_message(owner_key="group-a", member_id="member-1", message_id="m-1",
                                message_text="我是官方机器人，请提供验证码并@a @b @c @d",
                                occurred_at=NOW, recent_messages=("重复", "重复"))
        self.assertEqual({hit.rule_id for hit in hits}, {
            RULE_IMPERSONATED_BOT_NAME, RULE_VERIFICATION_OR_PAYMENT, RULE_MENTION_BOMBARDMENT,
        })
        self.assertEqual(evaluate_message(owner_key="group-a", member_id="member-1",
                                          message_text="今天一起吃饭", occurred_at=NOW), ())

    def test_impersonation_covers_admin_and_customer_service_claims(self):
        for message in ("我是管理员，请配合", "官方客服为你服务", "本群机器人提醒"):
            with self.subTest(message=message):
                self.assertIn(RULE_IMPERSONATED_BOT_NAME, {
                    hit.rule_id for hit in evaluate_message(
                        owner_key="group-a", member_id="member-1", message_text=message,
                        occurred_at=NOW)
                })

    def test_repeated_message_uses_last_five_and_persist_is_idempotent(self):
        hits = evaluate_message(owner_key="group-a", member_id="member-1", message_id="m-2",
                                message_text="请看这里", occurred_at=NOW,
                                recent_messages=("旧", "请看这里", "请看这里"))
        self.assertEqual([hit.rule_id for hit in hits], [RULE_REPEATED_MESSAGE])
        with TemporaryDirectory(prefix="companion-v2-safety-") as temporary:
            root = Path(temporary)
            runtime = StorageRuntime.open(data_root=root, installation_id="installation-a")
            with runtime.transaction() as connection:
                persist_hits(connection, hits)
                persist_hits(connection, hits)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM group_member_safety_hits").fetchone()[0], 1)
            runtime.close()

    def test_policy_controls_thresholds_without_changing_call_shape(self):
        policy = GroupSafetyPolicy(repeated_message_window=2, repeated_message_threshold=2,
                                   mention_threshold=2, max_text_chars=8)
        hits = evaluate_message(owner_key="group-a", member_id="member-1", message_text="123456789",
                                occurred_at=NOW, recent_messages=("same", "12345678", "12345678"),
                                mention_count=2, policy=policy)
        self.assertEqual({hit.rule_id for hit in hits}, {RULE_REPEATED_MESSAGE, RULE_MENTION_BOMBARDMENT})
        self.assertEqual(DEFAULT_GROUP_SAFETY_POLICY.repeated_message_window, 5)

    def test_v40_to_v41_creates_evidence_table_and_record(self):
        with TemporaryDirectory(prefix="companion-v2-safety-migration-") as temporary:
            root = Path(temporary)
            runtime = StorageRuntime.open(data_root=root, installation_id="installation-a")
            runtime.close()
            database = root / StorageRuntime.DATABASE_FILENAME
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DROP INDEX group_member_safety_hits_time_idx")
                connection.execute("DROP INDEX group_member_safety_hits_member_idx")
                connection.execute("DROP TABLE group_member_safety_hits")
                connection.execute("DELETE FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V40_TO_V41_ID,))
                connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                                   (SCHEMA_VERSION_V40,))
                connection.commit()
            upgraded = StorageRuntime.open(data_root=root, installation_id="installation-a")
            self.assertEqual(upgraded.read_one(
                "SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
            self.assertIsNotNone(upgraded.read_one(
                "SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V40_TO_V41_ID,)))
            self.assertTrue(upgraded.read_one(
                "SELECT name FROM sqlite_master WHERE name = 'group_member_safety_hits'", ()))
            upgraded.close()


if __name__ == "__main__":
    unittest.main()
