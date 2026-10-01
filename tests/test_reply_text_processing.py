from dataclasses import asdict, replace
import json
import unittest

from companion_v2.configuration.models import ConfigurationError
from companion_v2.conversation.reply_preparation import prepare_reply
from companion_v2.conversation.reply_settings import validate
from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER
from companion_v2.conversation.text_processing import ReplyTextPolicy, TEXT_DEFAULTS
from companion_v2.conversation.voice_reply import VoiceReplyPolicy


def policy(**changes):
    return ReplyTextPolicy(**changes)


class ReplyTextProcessingTests(unittest.TestCase):
    def test_forbidden_word_guard_is_opt_in_scoped_and_case_aware(self):
        disabled = policy(recall_forbidden_words='["秘密"]')
        self.assertIsNone(disabled.forbidden_word_guard("这里有秘密"))
        group_only = policy(enable_forbidden_word_recall=True, recall_forbidden_words='["Secret"]',
                            recall_forbidden_scope="group_only")
        self.assertIsNone(group_only.forbidden_word_guard("secret", scope_kind="private"))
        self.assertEqual(group_only.forbidden_word_guard("secret", scope_kind="group"), "Secret")
        bot_only = policy(enable_forbidden_word_recall=True, recall_forbidden_words='["Secret"]',
                          recall_forbidden_scope="bot_only")
        self.assertIsNone(bot_only.forbidden_word_guard("secret", is_bot_output=False))
        self.assertEqual(bot_only.forbidden_word_guard("secret", is_bot_output=True), "Secret")
        bot_and_group = policy(enable_forbidden_word_recall=True, recall_forbidden_words='["Secret"]',
                               recall_forbidden_scope="bot_and_group")
        self.assertIsNone(bot_and_group.forbidden_word_guard("secret", scope_kind="private", is_bot_output=False))
        self.assertEqual(bot_and_group.forbidden_word_guard("secret", scope_kind="group", is_bot_output=False), "Secret")
        sensitive = policy(enable_forbidden_word_recall=True, recall_forbidden_words='["Secret"]',
                           recall_forbidden_word_case_sensitive=True)
        self.assertIsNone(sensitive.forbidden_word_guard("secret"))
        self.assertEqual(sensitive.forbidden_word_guard("Secret"), "Secret")

    def test_forbidden_word_configuration_is_registered_and_validated(self):
        fields = asdict(ReplyTextPolicy())
        fields.update({"enable_forbidden_word_recall": True, "recall_forbidden_words": '["spam"]',
                       "recall_forbidden_scope": "bot_and_group"})
        validate({**asdict(SegmentationPolicy()), "streaming": True, "part_gap_ms": 0,
                  **fields})
        with self.assertRaises(ConfigurationError):
            validate({**asdict(SegmentationPolicy()), "streaming": True, "part_gap_ms": 0,
                      **fields, "recall_forbidden_scope": "invalid"})

    def test_defaults_use_word_cleanup_and_v1_newline_list(self):
        presentation = policy()
        self.assertEqual(presentation.content_cleanup_mode, "words")
        self.assertEqual(json.loads(presentation.content_cleanup_words), ["\n"])
        self.assertFalse(presentation.content_cleanup_enabled)
        self.assertEqual(replace(presentation, content_cleanup_enabled=True).clean_parts(("甲\n乙。",)),
                         ("甲乙。",))

    def test_ordered_replacements_precede_rule_length_and_support_tokens(self):
        presentation = policy(content_replacement_enabled=True,
            content_replacements=json.dumps(["hi => 你好呀", {"from": "呀", "to": "哇"},
                                              "<tab> => <space>", "删 => <empty>"]))
        segmentation = SegmentationPolicy(enabled=True, rules_enabled=True,
            threshold=7, min_segment_chars=1, max_segments=3)
        result = prepare_reply("hi。hi。\t删", segmentation, presentation)
        self.assertEqual(result.parts, ("你好哇。", "你好哇。 "))
        self.assertIn("格式数据", presentation.instruction)

    def test_protected_markdown_nested_quotes_urls_and_declared_facts_are_literal(self):
        protected = ('（外层 hi（内层 hi））', '“hi，原句”', 'https://host.test/hi?q=hi',
                     '```text\nhi\n```', '[hi](https://host.test/hi)', '<pc_tts>hi</pc_tts>',
                     "hi 是事实。")
        text = "hi\n\n" + "\n\n".join(protected)
        presentation = policy(content_replacement_enabled=True,
                              content_replacements='[{"from":"hi","to":"嗨"}]')
        replaced = presentation.replace_text(text, statements=(protected[-1],))
        self.assertTrue(replaced.startswith("嗨\n\n"))
        for literal in protected:
            self.assertIn(literal, replaced)

    def test_inline_media_and_url_do_not_protect_adjacent_prose(self):
        presentation = policy(content_replacement_enabled=True, content_replacements='["hi => 嗨"]')
        text = 'hi <pc_tts>hi</pc_tts> hi https://host.test/hi_name hi'
        self.assertEqual(presentation.replace_text(text),
                         '嗨 <pc_tts>hi</pc_tts> 嗨 https://host.test/hi_name 嗨')
        self.assertEqual(presentation.replace_text('**hi <pc_tts>hi</pc_tts> hi**'),
                         '**hi <pc_tts>hi</pc_tts> hi**')

    def test_cleanup_all_and_trailing_words_preserve_protected_spans_across_parts(self):
        presentation = policy(content_cleanup_enabled=True, content_cleanup_words='["。", "，"]')
        self.assertEqual(presentation.clean_parts(("甲。乙，", "（丙。", "丁，）戊。")),
                         ("甲乙", "（丙。", "丁，）戊"))
        trailing = replace(presentation, content_cleanup_scope="trailing")
        self.assertEqual(trailing.clean_parts(("甲。乙。， \n", "丙。（丁。）", "戊。（己。）。，")),
                         ("甲。乙", "丙。（丁。）", "戊。（己。）"))
        facts = ("甲。", "乙。")
        self.assertEqual(presentation.clean_parts(facts, statements=("甲。乙。",)), facts)

    def test_regex_cleanup_zero_width_and_execution_budget(self):
        presentation = policy(content_cleanup_enabled=True, content_cleanup_mode="regex",
                              content_cleanup_rule=r"[。!]+")
        self.assertEqual(presentation.clean_parts(("甲。乙!!（丙!）",)), ("甲乙（丙!）",))
        self.assertEqual(replace(presentation, content_cleanup_scope="trailing").clean_parts(("甲。乙!!",)), ("甲。乙",))
        self.assertEqual(replace(presentation, content_cleanup_rule=r"(?=$)",
                                content_cleanup_scope="trailing").clean_parts(("甲。",)), ("甲。",))
        with self.assertRaises(ValueError):
            replace(presentation, content_cleanup_rule=r"(a|aa)+$").clean_parts(("a" * 2000 + "!",))

    def test_empty_parts_are_removed_without_moving_authored_speech_to_another_part(self):
        presentation = policy(content_cleanup_enabled=True, content_cleanup_words='["删", "\\n"]',
                              content_replacement_enabled=True,
                              content_replacements='["说 => 改", "语 => 换"]')
        segmentation = SegmentationPolicy(enabled=True)
        voice = VoiceReplyPolicy(generation_mode="model_tag", segment_mode="first")
        text = f"删\n{MARKER}\n<pc_tts>语。</pc_tts>说\n{MARKER}\n后文"
        prepared = prepare_reply(text, segmentation, presentation, voice)
        self.assertEqual(prepared.parts, ("语。改", "后文"))
        self.assertEqual(prepared.kept_indices, (1, 2))
        self.assertEqual(prepared.speech(voice), (("语。", "planned"), ("", "segment_skipped")))
        derived = replace(voice, generation_mode="plain", segment_mode="each")
        self.assertEqual([entry[0] for entry in prepared.speech(derived)], list(prepared.parts))
        with self.assertRaises(ValueError):
            prepare_reply("删", segmentation, presentation)

    def test_reserved_markers_survive_replacements_until_normal_segmentation(self):
        presentation = policy(content_replacement_enabled=True,
                              content_replacements='["PRIVATE => OTHER", "甲 => 嗨"]')
        prepared = prepare_reply(f"甲\n{MARKER}\n乙", SegmentationPolicy(enabled=True), presentation)
        self.assertEqual(prepared.parts, ("嗨\n", "乙"))

    def test_settings_are_complete_or_legacy_and_invalid_rules_fail_before_save(self):
        legacy = {**asdict(SegmentationPolicy()), "streaming": False, "part_gap_ms": 0}
        self.assertEqual(validate(legacy), SegmentationPolicy())
        self.assertEqual(validate({**legacy, **TEXT_DEFAULTS}), SegmentationPolicy())
        with self.assertRaises(ConfigurationError):
            validate({**legacy, "content_cleanup_enabled": True})
        invalid = ({"content_cleanup_enabled": 1}, {"content_cleanup_rule": "["},
                   {"content_cleanup_scope": "middle"}, {"content_cleanup_words": '[""]'},
                   {"content_replacements": '[{"from":"a","from":"b","to":"c"}]'},
                   {"content_replacements": '[{"from":"","to":"x"}]'},
                   {"content_replacements": '["broken"]'})
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                validate({**legacy, **TEXT_DEFAULTS, **changes})
        expansion = policy(content_replacement_enabled=True,
                           content_replacements=json.dumps([{"from": "a", "to": "b" * 500}]))
        with self.assertRaises(ValueError):
            expansion.replace_text("a" * 200)


if __name__ == "__main__":
    unittest.main()
