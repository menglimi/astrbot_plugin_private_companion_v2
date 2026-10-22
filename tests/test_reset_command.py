import unittest
from types import SimpleNamespace
from unittest.mock import patch

from companion_v2.conversation.reset import ConversationWindow
from companion_v2.foundation.outcome import Outcome
from tests.test_management_access import SCOPE

from astrbot_host.functional_commands import parse_functional_command
from astrbot_host.reset_command import _decide, reset_confirmation_code


class _FakeManagement:
    instances = []

    def __init__(self, memory, operator):
        self.operator = operator
        self.cleared = []
        type(self).instances.append(self)

    def preview_clear(self, context):
        return Outcome.success({"counts": {"active": 2, "already_inactive": 1},
                                "revision_token": "token-1"})

    def clear(self, context, *, expected_revision_token, operation_key):
        self.cleared.append((expected_revision_token, operation_key))
        return Outcome.success({"forgotten_count": 2})


class _FakeApplication:
    def __init__(self):
        self.memory = object()
        self.resets = []

    def reset_conversation_window(self, window, *, reset_id):
        self.resets.append((window, reset_id))
        return Outcome.success({"batches": ["batch-1", "batch-2"], "replayed": False})


class ResetCommandTests(unittest.TestCase):
    def setUp(self):
        _FakeManagement.instances = []
        self.application = _FakeApplication()
        self.session = SimpleNamespace(application=self.application, runtime=None)
        self.context = SimpleNamespace(scope=SCOPE, key="context-key")
        self.window = ConversationWindow.from_scope(SCOPE)

    def command(self, argument=""):
        text = "陪伴 全部重置" + ((" " + argument) if argument else "")
        return parse_functional_command(text, channel="private")

    def decide(self, command):
        with patch("astrbot_host.reset_command.MemoryManagement", _FakeManagement):
            return _decide(command, self.context, self.session)

    def test_preview_lists_scope_and_requires_an_echoed_code(self):
        text = self.decide(self.command())
        self.assertIn("尚未执行", text)
        self.assertIn("3 条记忆事实", text)
        self.assertIn("不会改动", text)
        self.assertEqual(self.application.resets, [])
        self.assertEqual(_FakeManagement.instances[-1].cleared, [])

    def test_wrong_code_changes_nothing(self):
        text = self.decide(self.command("确认 000000"))
        self.assertIn("未执行", text)
        self.assertEqual(self.application.resets, [])

    def test_confirmed_code_resets_window_then_clears_memory(self):
        code = reset_confirmation_code(self.window, "token-1")
        text = self.decide(self.command("确认 " + code))
        self.assertIn("已执行", text)
        self.assertIn("2 个批次", text)
        self.assertIn("2 条记忆事实", text)
        self.assertEqual(len(self.application.resets), 1)
        cleared = _FakeManagement.instances[-1].cleared
        self.assertEqual(cleared[0][0], "token-1")
        # Window reset and memory clear share one idempotency key.
        self.assertEqual(cleared[0][1], self.application.resets[0][1])
        self.assertTrue(self.application.resets[0][1].startswith("chat-reset-"))

    def test_reset_all_aliases_are_private_commands(self):
        self.assertEqual(parse_functional_command("陪伴 全部重置", channel="private").intent, "reset_all")
        self.assertEqual(parse_functional_command("陪伴 重置插件", channel="private").intent, "reset_all")
        self.assertIsNone(parse_functional_command("陪伴 全部重置", channel="group"))


if __name__ == "__main__":
    unittest.main()
