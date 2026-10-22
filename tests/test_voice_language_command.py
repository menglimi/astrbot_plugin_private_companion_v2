import unittest
from types import SimpleNamespace

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from tests.test_management_access import INSTALLATION, NOW, SCOPE

from astrbot_host.functional_commands import execute_functional_command, parse_functional_command

ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
GROUP = "conversation.presentation"


class _FakeConfiguration:
    def __init__(self, *, language="zh", enabled=True):
        self.values = {GROUP + ".voice_language": language, GROUP + ".voice_enabled": enabled}
        self.patches = []

    def read(self, actor, *, target, group_id, observed_at):
        return Outcome.success(SimpleNamespace(edit_token="edit-token", values=dict(self.values)))

    def patch(self, actor, *, target, group_id, operation, expected_edit_token, changes, observed_at):
        self.patches.append(dict(changes))
        self.values.update(changes)
        return Outcome.success({"operation_id": operation.operation_id})


class VoiceLanguageCommandTests(unittest.TestCase):
    def setUp(self):
        self.configuration = _FakeConfiguration()
        self.application = SimpleNamespace(configuration=self.configuration, now=lambda: NOW)
        self.context = SimpleNamespace(key="context-key", scope=SCOPE, role_binding=SimpleNamespace(role=ROLE),
                                       actor=SimpleNamespace(subject=USER))

    def run_command(self, text):
        command = parse_functional_command(text, channel="private")
        return execute_functional_command(command, application=self.application, context=self.context)

    def test_language_names_map_to_the_registered_values(self):
        self.assertEqual(parse_functional_command("陪伴 TTS语种 日语", channel="private").intent, "voice_language")
        receipt = self.run_command("陪伴 语音语种 日语")
        self.assertIn("已设置", receipt)
        self.assertIn("日语", receipt)
        self.assertEqual(self.configuration.patches[-1], {GROUP + ".voice_language": "ja"})
        self.assertIn("已设置", self.run_command("陪伴 TTS语种 英语"))
        self.assertEqual(self.configuration.patches[-1], {GROUP + ".voice_language": "en"})

    def test_unknown_or_unchanged_values_do_not_write(self):
        self.assertIn("未执行", self.run_command("陪伴 TTS语种 法语"))
        self.assertIn("没有更改", self.run_command("陪伴 TTS语种 中文"))
        self.assertEqual(self.configuration.patches, [])

    def test_disabled_voice_is_reported_instead_of_pretending(self):
        self.configuration.values[GROUP + ".voice_enabled"] = False
        receipt = self.run_command("陪伴 TTS语种 日语")
        self.assertIn("已设置", receipt)
        self.assertIn("语音回复开关当前关闭", receipt)


if __name__ == "__main__":
    unittest.main()
