"""Speech planning and durable route-specific TTS cooldowns."""

from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import json
import unittest

from companion_v2.conversation.segmentation import LLM_SEGMENT_MARKER, SegmentationPolicy
from companion_v2.conversation.voice_reply import (
    VoiceReplyDelivery, VoiceReplyPolicy, capability_instruction, eligible, planned_speech,
    requested_voice_language, separate_spoken, speech_chunks, speech_decisions, strip_voice_markup,
    voice_policy_for_turn,
)
from companion_v2.conversation.voice_markup import visible_speech
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import NOW


class VoicePolicyTests(unittest.TestCase):
    def test_schema_defaults_and_trigger_modes(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
        defaults = {name: item["default"] for name, item in schema["voice_reply"]["items"].items()
                    if name != "enabled"}
        self.assertEqual(defaults, asdict(VoiceReplyPolicy()))
        request = VoiceReplyPolicy(trigger_mode="request", trigger_keywords="朗读, read aloud")
        self.assertTrue(eligible(request, input_text="请朗读这句话", kind="private", batch_id="a"))
        self.assertFalse(eligible(request, input_text="普通聊天", kind="private", batch_id="a"))
        targeted = VoiceReplyPolicy(trigger_mode="request", trigger_keywords="朗读",
            primary_mention_keywords="专属词\n定向短语，ONLY ME", primary_mention_probability=1)
        self.assertEqual(targeted.primary_mention_words(), ("专属词", "定向短语", "only me"))
        self.assertTrue(eligible(targeted, input_text="请回复专属词", kind="group", batch_id="a",
                                 primary_mention=True))
        self.assertFalse(eligible(targeted, input_text="普通聊天", kind="group", batch_id="a",
                                  primary_mention=True))
        self.assertFalse(eligible(replace(targeted, primary_mention_probability=0),
            input_text="专属词", kind="group", batch_id="a", primary_mention=True))
        probability = VoiceReplyPolicy(probability=0, group_probability=1)
        self.assertFalse(eligible(probability, input_text="", kind="private", batch_id="a"))
        self.assertTrue(eligible(probability, input_text="", kind="group", batch_id="a"))
        self.assertEqual(probability.provider_for_language(), "")
        self.assertEqual(VoiceReplyPolicy(language="ja", provider_id="fallback", ja_provider_id="japanese")
                         .provider_for_language(), "japanese")

    def test_voice_perception_describes_best_effort_delivery_without_provider_identity(self):
        policy = VoiceReplyPolicy(language="ja", delivery_mode="voice_only", provider_id="private-provider")
        instruction = capability_instruction(policy)
        self.assertIn("目标语种日语", instruction)
        self.assertIn("退回文字", instruction)
        self.assertNotIn("private-provider", instruction)

    def test_partial_conversion_uses_authored_short_spans_and_preserves_text_delivery(self):
        policy = VoiceReplyPolicy(conversion_scope="partial", delivery_mode="voice_and_text")
        self.assertIn("无需让语音覆盖整条回复", policy.instruction)
        self.assertNotIn("各段都保持一致", policy.instruction)
        visible, spans = separate_spoken("<pc_tts>晚安。</pc_tts>附上明天的安排。", policy)
        self.assertEqual(visible, "晚安。附上明天的安排。")
        self.assertEqual(planned_speech(visible, (visible,), spans, policy), ("晚安。",))
        self.assertEqual(policy.delivery_mode, "voice_and_text")

    def test_private_and_group_cooldowns_inherit_independently(self):
        policy = VoiceReplyPolicy(cooldown_seconds=90, private_cooldown_seconds=0,
                                  group_cooldown_seconds=180)
        self.assertEqual(policy.cooldown("private"), 0)
        self.assertEqual(policy.cooldown("group"), 180)
        self.assertEqual(replace(policy, group_cooldown_seconds=-1).cooldown("group"), 90)
        for changes in ({"private_cooldown_seconds": -2}, {"group_cooldown_seconds": True},
                        {"conversion_scope": "voice_only"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(policy, **changes)

    def test_turn_language_override_is_explicit_temporary_and_selects_matching_provider(self):
        saved = VoiceReplyPolicy(language="zh", provider_id="fallback", en_provider_id="english-tts",
                                 ja_provider_id="japanese-tts")
        for text, language, provider in (
            ("这次请用英语回答我", "en", "english-tts"),
            ("请用日语朗读", "ja", "japanese-tts"),
            ("Please reply in English", "en", "english-tts"),
            ("英語で答えてください", "en", "english-tts"),
        ):
            with self.subTest(text=text):
                current = voice_policy_for_turn(saved, text)
                self.assertEqual((current.language, current.provider_for_language()), (language, provider))
        self.assertEqual(saved.language, "zh")

    def test_turn_language_override_ignores_negation_and_translation_questions(self):
        for text in (
            "不要用英语回答",
            "Don't reply in English",
            "帮我翻译成英语",
            "Translate this sentence into Japanese",
            "英语单词怎么读",
            "请解释‘用英语回答’是什么意思",
        ):
            with self.subTest(text=text):
                self.assertEqual(requested_voice_language(text), "")

    def test_translation_prompt_pairs_each_foreign_span_with_a_complete_chinese_translation(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="en", foreign_text_mode="translation")
        self.assertIn("每个语音标签后紧接", policy.instruction)
        self.assertIn("完整对应", policy.instruction)

    def test_selected_always_and_request_modes_do_not_revert_to_optional_voice(self):
        for mode in ("always", "request"):
            policy = VoiceReplyPolicy(generation_mode="model_tag", trigger_mode=mode)
            self.assertIn("完整", policy.instruction)
            self.assertNotIn("没有合适内容就不用标签", policy.instruction)
            self.assertNotIn("可选语音", capability_instruction(policy))
        self.assertIn("按语境决定是否使用语音", VoiceReplyPolicy(trigger_mode="adaptive").instruction)

    def test_v1_voice_tags_keep_foreign_speech_and_chinese_translation(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="ja", foreign_text_mode="translation")
        for source in ("<tts>おやすみ。</tts>晚安。", "&lt;tts lang='ja'&gt;おやすみ。&lt;/tts&gt;晚安。"):
            self.assertEqual(separate_spoken(source, policy), ("晚安。", ((0, "おやすみ。"),)))
            self.assertEqual(separate_spoken(source, None), ("おやすみ。晚安。", ()))
        self.assertEqual(separate_spoken("<tts>保留正文", None), ("保留正文", ()))

    def test_voice_tags_tolerate_case_separator_entity_and_orphan_variants(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="ja", foreign_text_mode="translation")
        samples = (
            ("<PC-TTS lang='ja'>おやすみ。</pcc tts>晚安。", "おやすみ。", "晚安。"),
            ("&lt;P C TTS&gt;おはよう。&#x3C;/pc_tts&#x3E;早安。", "おはよう。", "早安。"),
            ("<PCC.TTS>ありがとう。</PC_TTS>谢谢。", "ありがとう。", "谢谢。"),
        )
        for source, speech, translation in samples:
            with self.subTest(source=source):
                self.assertEqual(separate_spoken(source, policy), (translation, ((0, speech),)))
        self.assertEqual(strip_voice_markup("正文 </pcc-tts> 后续 <PC_TTS"), "正文  后续 ")

    def test_model_tag_translation_keeps_spoken_spans_with_explicit_boundaries(self):
        policy = VoiceReplyPolicy(trigger_mode="adaptive", language="ja", foreign_text_mode="translation")
        source = (f"<pc_tts>こんにちは。</pc_tts>你好。\n{LLM_SEGMENT_MARKER}\n"
                  "<pc_tts>またね。</pc_tts>再见。")
        visible, spans = separate_spoken(source, policy)
        parts = SegmentationPolicy(enabled=True, llm_controlled=True).parts(visible)
        self.assertEqual(parts, ("你好。\n", "再见。"))
        self.assertEqual(planned_speech(visible, parts, spans, policy), ("こんにちは。", "またね。"))
        self.assertEqual(planned_speech(visible, parts, spans, replace(policy, segment_mode="last")),
                         ("", "またね。"))

    def test_missing_translation_preserves_original_and_stray_tags_do_not_shift_spans(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="en", foreign_text_mode="translation")
        source = f"<pc_tts>Hello.</pc_tts>\n{LLM_SEGMENT_MARKER}"
        visible, spans = separate_spoken(source, policy)
        self.assertEqual(SegmentationPolicy(enabled=True, llm_controlled=True).parts(visible), ("Hello.\n",))
        self.assertEqual(planned_speech(visible, ("Hello.\n",), spans, policy), ("Hello.",))
        visible, _ = separate_spoken("<pc_tts>Hello.</pc_tts>English continuation.", policy)
        self.assertEqual(visible, "Hello.English continuation.")
        visible, _ = separate_spoken("<pc_tts>Hello.</pc_tts>こんにちは。", policy)
        self.assertEqual(visible, "Hello.こんにちは。")
        visible, _ = separate_spoken("<pc_tts>Hello.</pc_tts>你好。", policy)
        self.assertEqual(visible, "你好。")
        source = f"stray </pc_tts>\n{LLM_SEGMENT_MARKER}\n<pc_tts>Goodbye.</pc_tts>再见。"
        visible, spans = separate_spoken(source, policy)
        self.assertNotIn("<pc_tts>", visible)
        self.assertEqual(planned_speech(visible, SegmentationPolicy(enabled=True, llm_controlled=True).parts(visible),
                                        spans, policy)[-1], "Goodbye.")

    def test_voice_wrappers_are_removed_when_voice_is_inactive_and_malformed_tags_are_unwrapped(self):
        source = "<pc_tts locale='en'>Hello.</pc_tts> &#x3C;pc_tts&#x3E;再见。&#x3C;/pc_tts&#x3E;"
        self.assertEqual(separate_spoken(source, None), ("Hello. 再见。", ()))
        self.assertEqual(separate_spoken("<pc_tts>普通正文。", VoiceReplyPolicy()), ("普通正文。", ()))

    def test_translation_fallback_is_per_tag_even_when_earlier_tag_has_translation(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="en", foreign_text_mode="translation")
        source = ("<pc_tts>Hello.</pc_tts>你好。\n" + LLM_SEGMENT_MARKER +
                  "\n<pc_tts>Goodbye.</pc_tts>")
        visible, spans = separate_spoken(source, policy)
        parts = SegmentationPolicy(enabled=True, llm_controlled=True).parts(visible)
        self.assertEqual(parts, ("你好。\n", "Goodbye."))
        self.assertEqual(planned_speech(visible, parts, spans, policy), ("Hello.", "Goodbye."))

    def test_plain_segment_selection_and_speech_limit(self):
        parts = ("第一段。", "第二段。")
        policy = VoiceReplyPolicy(segment_mode="first", max_speech_chars=4)
        self.assertEqual(planned_speech("".join(parts), parts, (), policy), ("第一段。", ""))
        self.assertEqual(planned_speech("".join(parts), parts, (), replace(policy, max_speech_chars=3)), ("", ""))
        self.assertEqual(speech_decisions("".join(parts), parts, (), policy),
                         (("第一段。", "planned"), ("", "segment_skipped")))
        self.assertEqual(speech_decisions("".join(parts), parts, (), replace(policy, max_speech_chars=3)),
                         (("", "too_long"), ("", "segment_skipped")))
        self.assertEqual(speech_decisions("", ("",), (), VoiceReplyPolicy()), (("", "empty_part"),))
        with self.assertRaises(ValueError):
            VoiceReplyPolicy(probability=2)
        with self.assertRaises(ValueError):
            VoiceReplyPolicy(timeout_seconds=True)

    def test_performance_cues_stay_in_speech_and_leave_ordinary_body_untouched(self):
        policy = VoiceReplyPolicy(generation_mode="model_tag")
        source = "数组[0]：<pc_tts>[温柔地]别急，<soft>慢慢来。</soft></pc_tts>参考 <soft> 的说明。"
        visible, spans = separate_spoken(source, policy)
        self.assertEqual(visible, "数组[0]：别急，慢慢来。参考 <soft> 的说明。")
        self.assertEqual(spans, ((6, "[温柔地]别急，<soft>慢慢来。</soft>"),))
        self.assertEqual(separate_spoken(source, None)[0], visible)
        translated = VoiceReplyPolicy(generation_mode="model_tag", language="ja", foreign_text_mode="translation")
        self.assertEqual(separate_spoken(
            "<pc_tts>[優しく]おやすみ。<whisper>また明日。</whisper></pc_tts>晚安，明天见。", translated),
            ("晚安，明天见。", ((0, "[優しく]おやすみ。<whisper>また明日。</whisper>"),)))

    def test_speech_chunks_balance_nested_tags_without_splitting_directions(self):
        speech = "[轻声，慢一点]今天辛苦了。<soft>好好休息。<slow>明天见。</slow></soft>"
        chunks = speech_chunks(speech, 6)
        self.assertEqual("".join(visible_speech(chunk) for chunk in chunks), visible_speech(speech))
        self.assertEqual(chunks, ("[轻声，慢一点]今天辛苦了。", "<soft>好好休息。</soft>",
                                  "<soft><slow>明天见。</slow></soft>"))
        unbroken = speech_chunks("[温柔地]你好，<soft>晚安。</soft>", 20)
        self.assertEqual(unbroken, ("[温柔地]你好，<soft>晚安。</soft>",))


class VoiceCooldownTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-voice-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id="voice-test")
        self.addCleanup(self.runtime.close)
        self.time = NOW
        self.delivery = VoiceReplyDelivery(self.runtime, lambda: self.time)

    def envelope(self, part_id, *, bot="bot-a", account="100", conversation="conversation-a",
                 persona="persona-a", kind=ScopeKind.PRIVATE):
        scope = ScopeRef("voice-test", "qq-main", kind, "200", bot, account, conversation, "session-a")
        role = SubjectRef("voice-test", SubjectKind.BOT, persona)
        return NS(part_id=part_id, context=NS(scope=scope, role_binding=NS(role=role)))

    def add_plan(self, part_id, *, cooldown=90, batch_id=None, sequence=1):
        batch_id = batch_id or part_id
        with self.runtime.transaction() as connection:
            if batch_id == part_id:
                connection.execute("""INSERT INTO conversation_batches
                    (batch_id, origin_key, context_json, role_instruction, state, revision, created_at, contributions_json)
                    VALUES (?, 'origin', '{}', '', 'ready', 1, ?, '{}')""", (batch_id, NOW.isoformat()))
            connection.execute("""INSERT INTO conversation_parts
                (part_id, batch_id, sequence, text, payload_hash, state)
                VALUES (?, ?, ?, 'hello', 'hash', 'pending')""", (part_id, batch_id, sequence))
            connection.execute("""INSERT INTO conversation_voice_parts
                (part_id, speech, provider_id, delivery_mode, position, timeout_seconds, cooldown_seconds)
                VALUES (?, 'hello', '', 'voice_and_text', 'after_media', 30, ?)""", (part_id, cooldown))

    def test_cooldown_survives_restart_and_isolates_bot_account_conversation_persona_and_kind(self):
        first = self.envelope("first")
        self.add_plan("first")
        self.assertIsNotNone(self.delivery.claim(first))
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id="voice-test")
        self.addCleanup(self.runtime.close)
        self.delivery = VoiceReplyDelivery(self.runtime, lambda: self.time)
        self.add_plan("blocked")
        self.assertIsNone(self.delivery.claim(self.envelope("blocked")))
        for part, changes in (("bot", {"bot": "bot-b"}), ("account", {"account": "101"}),
                              ("conversation", {"conversation": "conversation-b"}),
                              ("persona", {"persona": "persona-b"}),
                              ("group", {"kind": ScopeKind.GROUP})):
            self.add_plan(part)
            self.assertIsNotNone(self.delivery.claim(self.envelope(part, **changes)))
        self.time += timedelta(seconds=91)
        self.assertIsNotNone(self.delivery.claim(self.envelope("blocked")))

    def test_release_is_owner_bound_and_zero_cooldown_does_not_claim(self):
        self.add_plan("first")
        self.add_plan("second")
        first = self.delivery.claim(self.envelope("first"))
        self.assertIsNotNone(first)
        self.delivery.release(first, "second")
        self.assertIsNone(self.delivery.claim(self.envelope("second")))
        self.delivery.release(first, "first")
        self.assertIsNotNone(self.delivery.claim(self.envelope("second")))
        self.add_plan("free", cooldown=0)
        self.assertNotIn("cooldown_key", self.delivery.claim(self.envelope("free")))

    def test_each_segment_in_same_reply_keeps_voice_while_next_reply_cools_down(self):
        self.add_plan("first")
        self.add_plan("next-part", batch_id="first", sequence=2)
        self.add_plan("next-reply")
        first = self.delivery.claim(self.envelope("first"))
        following = self.delivery.claim(self.envelope("next-part"))
        self.assertIsNotNone(first)
        self.assertIsNotNone(following)
        self.assertNotIn("cooldown_key", following)
        self.delivery.release(following, "next-part")
        self.assertIsNone(self.delivery.claim(self.envelope("next-reply")))
