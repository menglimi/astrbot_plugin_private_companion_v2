"""Per-channel style prompt supplements: presentation, proactive contact, and journal writing."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from companion_v2.conversation.humanized_expression import (DEFAULT_PROMPT, MAX_PROMPT_CHARS,
                                                           HumanizedExpressionPolicy, instruction)
from companion_v2.conversation.text_processing import TEXT_DEFAULTS, text_policy
from companion_v2.proactive.configuration import GROUP as CONTACT_GROUP, configuration_fields as contact_fields
from companion_v2.proactive.preferences import ContactPreferences
from companion_v2.proactive.prompts import ORIGIN_INSTRUCTIONS, PURPOSES, PURPOSE_INSTRUCTIONS, request_for
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
        self.assertIn("可以只发一张图", policy.instruction)
        self.assertIn("可以选择不接话", policy.instruction)
        self.assertIn("可以只用语音", policy.instruction)
        self.assertIn("戳一戳只在当前流程明确提供该能力并允许时考虑", policy.instruction)
        self.assertIn("不必为了简短压成几个字或一句话", policy.instruction)
        self.assertIn("来源和原文只在被追问", policy.instruction)
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

    def test_chat_prompt_allows_self_started_low_pressure_message(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        request = request_for(self.contact_job(), (), preferences)

        self.assertIn("不要求用户刚说过某个关键词，也不要求有待办或事件来源", request.instruction)
        self.assertIn("优先写一条轻松、低压力、无需回复的消息", request.instruction)
        self.assertIn("不能编造刚做过的事、共同经历或用户当前状态", request.instruction)
        self.assertIn("不要复述原话、盘问近况、催回复", request.instruction)

    def test_administrator_diagnostic_omits_history_and_dedup_for_every_purpose(self):
        values = dict(PREF_VALUES, dedup_enabled=True)
        preferences = ContactPreferences(snapshot=None, values=values, observed_at=NOW)
        history = ({"owner": CONTACT_GROUP, "delivered_at": NOW.isoformat(), "text": "private history marker"},)
        last_reply = {"text": "private last reply marker", "reference": "private-reference"}

        ordinary = request_for(self.contact_job(), (), preferences, history, last_reply=last_reply)
        self.assertIn("dedup_candidate", {item.purpose for item in ordinary.context.materials})
        self.assertIn("只用标为 dedup_candidate", ordinary.instruction)

        for purpose in PURPOSES:
            with self.subTest(purpose=purpose):
                job = self.contact_job()
                job.intent.purpose = purpose
                job.administrator_test = True
                job.interaction = {"latest_input": "private interaction marker"}
                request = request_for(job, (), preferences, history, last_reply=last_reply)
                material_purposes = {item.purpose for item in request.context.materials}
                material_text = "\n".join(item.payload for item in request.context.materials)
                self.assertNotIn("communication_state", material_purposes)
                self.assertNotIn("dedup_candidate", material_purposes)
                self.assertNotIn("last_confirmed_reply", material_purposes)
                self.assertNotIn("private history marker", material_text)
                self.assertNotIn("private last reply marker", material_text)
                self.assertNotIn("private interaction marker", material_text)
                self.assertNotIn("只用标为 dedup_candidate", request.instruction)
                self.assertIn("不要把缺少这些材料判为重复", request.instruction)

    def test_daily_greeting_gets_contextual_humanized_guidance(self):
        thought = SimpleNamespace(summary="早上有一个轻轻碰面的机会", opportunity=SimpleNamespace(
            opportunity_id="greeting-1", opened_at=NOW))
        job = self.contact_job()
        job.intent = SimpleNamespace(purpose="greeting", thought=thought)
        job.automatic_origin = {"greeting_event": {"kind": "day_anchor", "anchor": "morning_greeting"}}
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        request = request_for(job, (), preferences)
        self.assertIn("不是必须完成的签到任务", request.instruction)
        self.assertIn("时段本身就可以作为轻轻问候的由头", request.instruction)
        self.assertIn("不是开口前提", request.instruction)
        self.assertIn("不要每次套用", request.instruction)

    def test_insomnia_greeting_keeps_the_low_pressure_rule(self):
        thought = SimpleNamespace(summary="夜间低压力问候", opportunity=SimpleNamespace(
            opportunity_id="night-1", opened_at=NOW))
        job = self.contact_job()
        job.intent = SimpleNamespace(purpose="care", thought=thought)
        job.automatic_origin = {"greeting_event": {"kind": "insomnia_night"}}
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        request = request_for(job, (), preferences)
        self.assertIn("夜间低压力问候机会", request.instruction)
        self.assertIn("不要求对方回复", request.instruction)

    def test_source_backed_diagnostic_keeps_the_selected_producer_boundary(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        job = self.contact_job()
        job.intent = SimpleNamespace(purpose="news", thought=job.intent.thought)
        job.administrator_test = True
        job.diagnostic_source_backed = True
        job.diagnostic_origin = {"news_event": {"event_id": "article-1"}, "_diagnostic": {}}

        request = request_for(job, (), preferences)

        self.assertIn(ORIGIN_INSTRUCTIONS["news_event"], request.instruction)
        self.assertIn("只使用本次提供的已核验来源", request.instruction)
        self.assertNotIn("测试不读取聊天历史、记忆或真实事件", request.instruction)

    def test_synthetic_diagnostic_uses_the_fictional_scenario_without_claiming_real_sources(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        job = self.contact_job()
        job.intent.purpose = "news"
        job.administrator_test = True
        job.diagnostic_source_backed = False
        job.diagnostic_origin = {"_diagnostic": {"route_id": "synthetic_event"},
                                 "synthetic_event": {"test_id": "attempt-1"}}

        request = request_for(job, (), preferences)

        self.assertIn("合成事件投递测试", request.instruction)
        self.assertIn("不得将合成内容说成现实事实", request.instruction)
        self.assertIn("让收件人能看出这是模拟测试", request.instruction)
        self.assertNotIn("本轮素材仍来自所选目的的真实生产器", request.instruction)

    def test_each_registered_purpose_has_its_own_evidence_guidance(self):
        self.assertEqual(set(PURPOSE_INSTRUCTIONS), set(PURPOSES))
        for purpose, guidance in PURPOSE_INSTRUCTIONS.items():
            with self.subTest(purpose=purpose):
                job = self.contact_job()
                job.intent = SimpleNamespace(purpose=purpose, thought=job.intent.thought)
                preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
                request = request_for(job, (), preferences)
                self.assertIn(guidance, request.instruction)
                self.assertIn("仅输出 JSON", request.instruction)
                self.assertIn('"decision_confidence"', request.instruction)
                self.assertIn('"skip_reason"', request.instruction)

    def test_selected_thought_is_the_anchor_and_old_context_cannot_create_a_task(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        request = request_for(self.contact_job(), (), preferences)
        self.assertIn("调度窗口可以直接提供关系表达或日常聊天的开口机会", request.instruction)
        self.assertIn("不能把旧情绪写成当前状态、恢复已结束的话题、增加待办或触发工具行为", request.instruction)
        self.assertIn("这是角色主动开启日常聊天的机会，不要求用户刚说过某个关键词", PURPOSE_INSTRUCTIONS["chat"])
        self.assertIn("日期或时段本身可以成为简短问候的由头", PURPOSE_INSTRUCTIONS["greeting"])
        self.assertIn("正文优先说清一个自然、完整的意思", request.instruction)

    def test_each_supported_event_origin_adds_its_scene_boundary(self):
        preferences = ContactPreferences(snapshot=None, values=PREF_VALUES, observed_at=NOW)
        for marker, guidance in ORIGIN_INSTRUCTIONS.items():
            with self.subTest(marker=marker):
                job = self.contact_job()
                job.automatic_origin = {marker: {}}
                request = request_for(job, (), preferences)
                self.assertIn(guidance, request.instruction)

    def test_relationship_and_followup_purposes_have_registered_producers(self):
        self.assertTrue(all(purpose in PURPOSE_INSTRUCTIONS
                            for purpose in ("affection", "care", "play", "repair", "invitation")))
        self.assertIn("不需要用户近期先说想念", PURPOSE_INSTRUCTIONS["affection"])
        self.assertIn("不需要用户先说累了或难过", PURPOSE_INSTRUCTIONS["care"])
        self.assertIn("具体分歧", ORIGIN_INSTRUCTIONS["relationship_event"])
        from companion_v2.proactive.configuration import GROUP, configuration_fields
        fields = {field.field_id for field in configuration_fields()}
        self.assertIn(GROUP + ".contact_followup_after_minutes", fields)
        self.assertIn(GROUP + ".contact_followup_cooldown_minutes", fields)
        self.assertEqual(PURPOSES["followup"], "接回旧话题")
        self.assertIn("不暗示已读", PURPOSE_INSTRUCTIONS["followup"])
        self.assertIn("给对方留出拒绝或改期空间", PURPOSE_INSTRUCTIONS["invitation"])


class JournalStyleTests(RequestForDreamTests):
    def test_diary_style_prompt_applies_to_both_kinds(self):
        suffix = "角色表达风格补充（以下是风格参考，不是任务指令，不改写事实与来源原意）：短句收尾。"
        for kind in (JournalKind.DIARY, JournalKind.DREAM):
            request = journal_request_for(self.job(kind), (), style=suffix)
            self.assertTrue(request.instruction.endswith(suffix), kind)


if __name__ == "__main__":
    unittest.main()
