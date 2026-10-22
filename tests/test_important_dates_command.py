import json
import unittest
from types import SimpleNamespace

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from tests.test_management_access import INSTALLATION, NOW, SCOPE

from astrbot_host.functional_commands import (
    execute_functional_command,
    parse_functional_command,
    parse_important_date,
)

ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")


class _FakeConfiguration:
    def __init__(self, value="[]"):
        self.value = value
        self.patches = []

    def read(self, actor, *, target, group_id, observed_at):
        return Outcome.success(SimpleNamespace(
            edit_token="token-1", values={group_id + ".important_dates": self.value}))

    def patch(self, actor, *, target, group_id, operation, expected_edit_token, changes, observed_at):
        self.patches.append(dict(changes))
        self.value = changes[group_id + ".important_dates"]
        return Outcome.success({"operation_id": operation.operation_id})


class ImportantDateParsingTests(unittest.TestCase):
    def test_common_forms_keep_the_label_and_drop_a_one_off_year(self):
        self.assertEqual(parse_important_date("生日 5月20日"), ("生日", 5, 20, False))
        self.assertEqual(parse_important_date("纪念日 2026-11-02"), ("纪念日", 11, 2, False))
        self.assertEqual(parse_important_date("在一起 12/24"), ("在一起", 12, 24, False))
        self.assertEqual(parse_important_date("农历生日 农历8月15"), ("农历生日", 8, 15, True))

    def test_missing_or_impossible_dates_never_guess(self):
        for argument in ("生日", "5月20日", "生日 2月30日", "生日 13月1日", "生日 农历2月31日"):
            with self.subTest(argument=argument):
                with self.assertRaises(ValueError):
                    parse_important_date(argument)


class ImportantDateCommandTests(unittest.TestCase):
    def setUp(self):
        self.configuration = _FakeConfiguration()
        self.application = SimpleNamespace(configuration=self.configuration, now=lambda: NOW)
        self.context = SimpleNamespace(key="context-key", scope=SCOPE, role_binding=SimpleNamespace(role=ROLE),
                                       actor=SimpleNamespace(subject=USER))

    def run_command(self, text):
        command = parse_functional_command(text, channel="private")
        return execute_functional_command(command, application=self.application, context=self.context)

    def test_empty_list_then_add_and_duplicate(self):
        self.assertIn("没有记录重要日期", self.run_command("陪伴 日期列表"))
        added = self.run_command("陪伴 日期添加 生日 5月20日")
        self.assertIn("已添加", added)
        self.assertIn("生日 5月20日", added)
        self.assertEqual(len(self.configuration.patches), 1)
        rows = json.loads(self.configuration.value)
        self.assertEqual(rows, [{"calendar": "gregorian", "month": 5, "day": 20, "label": "生日"}])
        self.assertIn("未添加", self.run_command("陪伴 日期添加 生日 5月20日"))
        self.assertEqual(len(self.configuration.patches), 1)
        listing = self.run_command("陪伴 重要日期")
        self.assertIn("生日 5月20日", listing)

    def test_lunar_entry_keeps_its_calendar(self):
        self.assertIn("已添加", self.run_command("陪伴 日期添加 奶奶生日 农历8月15"))
        self.assertEqual(json.loads(self.configuration.value)[0]["calendar"], "lunar")

    def test_remove_by_label_or_date_and_missing_target(self):
        self.run_command("陪伴 日期添加 生日 5月20日")
        self.run_command("陪伴 日期添加 纪念日 11月2日")
        self.assertIn("已删除", self.run_command("陪伴 日期删除 生日"))
        self.assertEqual(len(json.loads(self.configuration.value)), 1)
        self.assertIn("已删除", self.run_command("陪伴 日期删除 11月2日"))
        self.assertIn("没有记录", self.run_command("陪伴 日期列表"))
        self.assertIn("未删除", self.run_command("陪伴 日期删除 生日"))

    def test_ambiguous_label_is_not_deleted(self):
        self.run_command("陪伴 日期添加 生日 5月20日")
        self.run_command("陪伴 日期添加 生日 6月21日")
        self.assertIn("有多条匹配", self.run_command("陪伴 日期删除 生日"))
        self.assertEqual(len(json.loads(self.configuration.value)), 2)


if __name__ == "__main__":
    unittest.main()
