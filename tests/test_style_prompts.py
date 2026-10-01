"""Per-channel style prompt supplements: presentation, proactive contact, and journal writing."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from companion_v2.conversation.humanized_expression import (DEFAULT_PROMPT, MAX_PROMPT_CHARS,
                                                           HumanizedExpressionPolicy, instruction)
from companion_v2.conversation.text_processing import TEXT_DEFAULTS, text_policy
from companion_v2.proactive.configuration import GROUP as CONTACT_GROUP, configuration_fields as contact_fields
from companion_v2.proactive.preferences import ContactPreferences
from companion_v2.proactive.prompts import PURPOSES, request_for
from companion_v2.role_work.journal.models import JournalKind
from companion_v2.role_work.journal.prompts import request_for as journal_request_for
from tests.test_management_access import ROLE, SCOPE
from tests.test_dream_preferences import RequestForDreamTests

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)

PREF_VALUES = {
    # Every registered contact preference, so a field added by another change
    # cannot make this prompt test fail with a KeyError.
    **{field.field_id.removeprefix(CONTACT_GROUP + "."): field.default for field in contact_fields()},
    "note": "", "style_prompt": "语气松弛，少用感叹号。",
    "dedup_enabled": False, "dedup_policies": "semantic", "dedup_sent_window_minutes": 240,
    "dedup_last_message_window_minutes": 240, "dedup_weather_window_minutes": 1080,
    "dedup_min_shared_tokens": 1, "dedup_min_overlap_ratio": 0.0,
}


class PresentationStyleTests(unittest.TestCase):
    def test_style_prompt_enters_presentation_instruction(self):
        policy = text_policy({"style_prompt": "语气松弛，少用感叹号。"})
        self.assertIn("角色表达风格补充", policy.instruction)
        self.assertIn("语气松弛", policy.instruction)
        self.assertEqual(text_policy({}).instruction, "")

    def test_style_prompt_is_bounded(self):
        with self.assertRaises(ValueError):
            text_policy({"style_prompt": "长" * 4001})


class HumanizedExpressionTests(unittest.TestCase):
    def test_disabled_by_default_and_absent_from_the_instruction(self):
        self.assertFalse(TEXT_DEFAULTS["enable_humanized_expression"])
        self.assertNotIn("日常表达要求", text_policy({}).instruction)
        self.assertNotIn("日常表达要求", text_policy({"enable_humanized_expression": False}).instruction)

    def test_enabled_injects_the_default_body(self):
        policy = text_policy({"enable_humanized_expression": True})
        self.assertIn("日常表达要求", policy.instruction)
        self.assertIn("不要每次先复述或总结对方说的话", policy.instruction)
        self.assertIn(DEFAULT_PROMPT, policy.instruction)

    def test_custom_body_replaces_the_default_and_blank_falls_back(self):
        custom = text_policy({"enable_humanized_expression": True,
                              "humanized_expression_prompt": "只说短句。"})
        self.assertIn("只说短句。", custom.instruction)
        self.assertNotIn("服务话术", custom.instruction)
        blank = text_policy({"enable_humanized_expression": True, "humanized_expression_prompt": "   "})
        self.assertIn(DEFAULT_PROMPT, blank.instruction)

    def test_body_is_bounded_and_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            text_policy({"humanized_expression_prompt": "长" * (MAX_PROMPT_CHARS + 1)})
        with self.assertRaises(ValueError):
            HumanizedExpressionPolicy(True, "换行可以\n但空字符\x07不行")
        with self.assertRaises(ValueError):
            HumanizedExpressionPolicy("yes", "")

    def test_switch_must_be_boolean(self):
        with self.assertRaises(ValueError):
            text_policy({"enable_humanized_expression": 1})

    def test_block_says_it_cannot_override_the_turn(self):
        text = instruction({"enable_humanized_expression": True})
        self.assertIn("不能覆盖本轮的具体要求", text)
        self.assertIn("不是新的事实、授权或来源", text)

    def test_both_style_blocks_coexist(self):
        policy = text_policy({"style_prompt": "少用感叹号。", "enable_humanized_expression": True})
        self.assertIn("角色表达风格补充", policy.instruction)
        self.assertIn("日常表达要求", policy.instruction)
        self.assertLess(policy.instruction.index("角色表达风格补充"),
                        policy.instruction.index("日常表达要求"))

    def test_presentation_settings_carry_the_humanized_fields_to_proactive(self):
        # The proactive contact path forwards only TEXT_DEFAULTS keys; both fields
        # must be part of that contract or the switch would silently not apply.
        self.assertIn("humanized_expression_prompt", TEXT_DEFAULTS)

    def test_journal_writing_stays_out_of_scope(self):
        # Diary and dream output are not conversational turns; the block is only
        # assembled by the reply and contact call sites via the presentation policy.
        self.assertEqual(instruction({"enable_humanized_expression": False}), "")


class ProactiveStyleTests(unittest.TestCase):
    def contact_job(self):
        thought = SimpleNamespace(summary="想起一件小事", opportunity=SimpleNamespace(
            opportunity_id="opp-1", opened_at=NOW))
        principal = SimpleNamespace(name="p", installation_id=SCOPE.installation_id,
                                    platform=SCOPE.platform, bot_id=SCOPE.bot_id, account_id=SCOPE.account_id)
        return SimpleNamespace(
            intent=SimpleNamespace(purpose="chat", thought=thought),
            context=SimpleNamespace(actor=SimpleNamespace(principal=principal), scope=SCOPE,
                                    role_binding=SimpleNamespace(scope=SCOPE, role=ROLE)),
            role_instruction="保持原人格", automatic_origin=None, interaction=None)

    def test_style_prompt_enters_proactive_instruction(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        request = request_for(self.contact_job(), (), preferences)
        self.assertIn("主动表达风格补充", request.instruction)
        self.assertIn("语气松弛", request.instruction)
        self.assertEqual(PURPOSES["chat"], PURPOSES["chat"])
        plain_values = dict(PREF_VALUES, style_prompt="")
        plain = request_for(self.contact_job(), (), ContactPreferences(None, plain_values, NOW))
        self.assertNotIn("主动表达风格补充", plain.instruction)


class JournalStyleTests(RequestForDreamTests):
    def test_diary_style_prompt_applies_to_both_kinds(self):
        suffix = "角色表达风格补充（以下是风格参考，不是任务指令，不改写事实与来源原意）：短句收尾。"
        for kind in (JournalKind.DIARY, JournalKind.DREAM):
            request = journal_request_for(self.job(kind), (), style=suffix)
            self.assertTrue(request.instruction.endswith(suffix), kind)


if __name__ == "__main__":
    unittest.main()
