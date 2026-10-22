"""The prompt editor changes the templates consumed by the original contact path."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.model_gateway.management import ModelManagement
from companion_v2.proactive.configuration import GROUP
from companion_v2.proactive.preferences import ContactPreferences
from companion_v2.proactive.prompts import INSTRUCTION, request_for
from companion_v2.proactive.prompt_templates import PROMPT_DEFAULTS
from tests.proactive_support import ContactFixture


class PromptTemplateTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app = await self.enabled()
        self.context = self.contact_context()
        self.manager = ModelManagement(self.app, self.context)

    def task(self, manager=None):
        return next(task for task in (manager or self.manager).status(self.core).unwrap()["tasks"]
                    if task["kind"] == "proactive.compose")

    def section(self, key, task=None):
        return next(section for section in (task or self.task())["prompt_sections"] if section["key"] == key)

    def patch(self, key, *, prompt=None, reset=False, token=None, operation="edit-template", operator=None):
        data = {"kind": "proactive.compose", "section": key, "operation_key": operation,
                "edit_token": token or self.section(key)["edit_token"],
                "changes": {} if reset else {"prompt": prompt}, "reset": ["prompt"] if reset else []}
        return self.manager.configure(operator or self.core, data)

    def composed(self, purpose="chat", *, dialogue=(), history=(), last_reply=None,
                 automatic_origin=None, preferences=None):
        opportunity = self.opportunity()
        job = SimpleNamespace(intent=self.intent(opportunity, purpose=purpose), context=self.context,
            automatic_origin=automatic_origin, interaction=None, role_instruction="角色自己的设定")
        return request_for(job, (), preferences or self.preferences(self.app), history,
                           dialogue=dialogue, last_reply=last_reply)

    async def test_edit_replaces_business_template_and_reaches_the_provider(self):
        original = self.section("expression")["prompt"]
        text = "自然展开一个有内容的感想，按转折分段。"
        self.patch("expression", prompt=text).unwrap()
        task = (await self.contact(self.app)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        request = self.called[0].original
        self.assertIn(text, request.instruction)
        self.assertNotIn(original, request.instruction)
        self.assertIn(INSTRUCTION, request.instruction)
        self.assertEqual(request.role_instruction, "这是原角色人格，保持自然。")

    async def test_news_replaces_only_news_templates_and_expands_length(self):
        self.settings(self.app, {"proactive_intensity_body_chars": 280}).unwrap()
        self.patch("news_sharing", prompt="遇到新鲜事后自然分享亮点，再说具体感想。", operation="news-style").unwrap()
        self.patch("news_length", prompt="新闻全部正文 {chars} 字以内，保留自然段落。", operation="news-length").unwrap()
        news = self.composed("news").instruction
        chat = self.composed().instruction
        self.assertIn("新闻全部正文 280 字以内", news)
        self.assertNotIn(PROMPT_DEFAULTS["news_sharing_prompt"], news)
        self.assertNotIn("遇到新鲜事后自然分享亮点", chat)
        self.assertIn("无需压成一句", chat)
        self.assertNotIn("一句话能说完就只说一句", chat + news)

    async def test_recent_meal_answer_and_unanswered_contact_are_explicit_continuity_cues(self):
        now = self.clock.now()
        dialogue = ({"role": "user", "text": "吃了啦", "received_at": now.isoformat()},)
        request = self.composed("meal", dialogue=dialogue, automatic_origin={"meal_event": {"kind": "noon"}})
        self.assertIn("同一餐次不要再次询问是否吃饭", request.instruction)
        self.assertIn("最近一条角色主动消息之后用户还没有新发言", request.instruction)
        self.assertIn("角色自己的小幅状态变化通常留在内部连续性中，不逐条播报", request.instruction)
        self.assertIn("历史材料有限或未显示答案，不证明对方还没吃", request.instruction)
        recent = [material for material in request.context.materials
                  if material.purpose == "recent_private_dialogue"]
        self.assertEqual(len(recent), 1)
        self.assertIn("吃了啦", recent[0].payload)

    async def test_full_exchange_is_shared_across_contact_purposes_without_inferred_labels(self):
        base = self.preferences(self.app)
        observed_at = datetime(2026, 9, 21, 5, 27, tzinfo=timezone.utc)
        preferences = ContactPreferences(base.snapshot, base.values, observed_at)
        dialogue = ({"role": "assistant", "text": "午饭吃得怎么样？", "delivered_at":
                     "2026-09-21T04:30:20+00:00", "_history_round": "lunch"},
                    {"role": "user", "text": "碗都洗好啦", "received_at":
                     "2026-09-21T04:30:54+00:00", "_history_round": "lunch"},
                    {"role": "assistant", "text": "那就好，下午慢慢来", "delivered_at":
                     "2026-09-21T04:31:29+00:00", "_history_round": "lunch"})

        for purpose in ("meal", "greeting", "care", "chat"):
            with self.subTest(purpose=purpose):
                request = self.composed(purpose, dialogue=dialogue, preferences=preferences)
                intent = next(item for item in request.context.materials if item.purpose == "contact_intent")
                self.assertNotIn("continuity_signal", json.loads(intent.payload))
                recent = [json.loads(item.payload) for item in request.context.materials
                          if item.purpose == "recent_private_dialogue"]
                self.assertEqual([item["text"] for item in recent[0]["messages"]],
                                 [item["text"] for item in dialogue])
                self.assertIn("这一连续性判断适用于所有主动目的", request.instruction)
                self.assertIn("独立于话题去重开关和时间窗", request.instruction)
                self.assertIn("后来的明确纠正、另一餐或新的情境则要重新理解", request.instruction)

    async def test_ambiguous_statements_keep_their_original_meaning_and_date(self):
        base = self.preferences(self.app)
        observed_at = datetime(2026, 9, 21, 5, 27, tzinfo=timezone.utc)
        preferences = ContactPreferences(base.snapshot, base.values, observed_at)
        for text in ("你吃饱了吗？", "还没吃", "我没吃饱", "他吃了，我还没顾上", "吃了？并没有哦",
                     "嗯，刚刚那份已经解决啦", "晚饭吃了", "昨天吃饱啦", "先去躺一会儿，不一定睡",
                     "任务都交了，等明天反馈", "我还没吃饭这几个字怎么翻译？"):
            with self.subTest(text=text):
                request = self.composed("chat", dialogue=({"role": "user", "text": text,
                    "received_at": "2026-09-21T04:30:54+00:00"},), preferences=preferences)
                self.assertNotIn("continuity_signal", {item.purpose for item in request.context.materials})
                recent = next(item for item in request.context.materials if item.purpose == "recent_private_dialogue")
                self.assertEqual(json.loads(recent.payload)["text"], text)

        yesterday = self.composed("chat", dialogue=({"role": "user", "text": "吃饱啦",
            "received_at": "2026-09-20T04:30:54+00:00"},), preferences=preferences)
        self.assertNotIn("continuity_signal", {item.purpose for item in yesterday.context.materials})
        recent = next(item for item in yesterday.context.materials if item.purpose == "recent_private_dialogue")
        self.assertEqual(json.loads(recent.payload)["received_at"], "2026-09-20T04:30:54+00:00")

    async def test_later_correction_follows_the_old_reply_and_proactive_message(self):
        request = self.composed("care", dialogue=(
            {"role": "user", "text": "刚才说的是昨晚，今天还没顾上", "received_at": "2026-09-21T05:05:00+00:00"},
            {"role": "assistant", "text": "午饭吃了吗？", "delivered_at": "2026-09-21T12:30:20+08:00",
             "_history_round": "lunch"},
            {"role": "user", "text": "吃饱啦", "received_at": "2026-09-21T04:30:54+00:00",
             "_history_round": "lunch"}),
            history=({"owner": GROUP, "text": "手边这本书真有趣", "delivered_at": "2026-09-21T04:55:00+00:00"},),
            last_reply={"text": "吃饱了就好呀", "delivered_at": "2026-09-21T04:31:29+00:00"})
        past = [json.loads(item.payload) for item in request.context.materials
                if item.purpose in ("recent_private_dialogue", "last_confirmed_reply", "dedup_candidate",
                                    "confirmed_background_message", "confirmed_reply_context")]
        self.assertEqual([item.get("text", [msg["text"] for msg in item.get("messages", ())]) for item in past],
                         [["午饭吃了吗？", "吃饱啦"], "吃饱了就好呀", "手边这本书真有趣", "刚才说的是昨晚，今天还没顾上"])

    async def test_relationship_inheritance_reset_and_window_isolation(self):
        target = ConfigTarget(self.context.scope.installation_id, ConfigLayer.RELATIONSHIP,
            self.context.role_binding.role, bot_id=self.context.scope.bot_id, subject=self.context.actor.subject)
        self.settings(self.app, {"news_sharing_prompt": "关系层的新闻表达"}, target=target, actor=self.core).unwrap()
        self.assertEqual(self.section("news_sharing")["field"]["source"], "relationship")
        self.patch("news_sharing", prompt="这个窗口的新闻表达", operation="window-news").unwrap()
        other = ModelManagement(self.app, self.other_window_context())
        self.assertEqual(self.section("news_sharing", self.task(other))["prompt"], "关系层的新闻表达")
        reset = self.patch("news_sharing", reset=True, operation="restore-news").unwrap()
        field = self.section("news_sharing", reset["task"])["field"]
        self.assertEqual((field["value"], field["source"], field["explicit"]), ("关系层的新闻表达", "relationship", False))

    async def test_conflicts_replay_validation_and_authorization(self):
        token = self.section("expression")["edit_token"]
        first = self.patch("expression", prompt="窗口表达", token=token).unwrap()
        replay = self.patch("expression", prompt="窗口表达", token=token).unwrap()
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["operation_id"], replay["operation_id"])
        conflict = self.patch("expression", prompt="过期草稿", token=token, operation="stale-template")
        self.assertEqual(conflict.failure.code, "configuration_revision_conflict")
        for value in ("删了变量", "{chars.__class__}", "{chars!r}", "{chars:10000}", "{unknown}", "{"):
            with self.subTest(value=value):
                invalid = self.patch("length", prompt=value, operation="invalid-template")
                self.assertEqual(invalid.failure.code, "invalid_contact_preference")
        forbidden = self.patch("expression", prompt="非管理员表达", operator=self.important, operation="forbidden")
        self.assertEqual(forbidden.failure.code, "core_access_required")
        fixed = self.manager.configure(self.core, {"kind": "proactive.compose", "section": "business",
            "operation_key": "fixed", "edit_token": token, "changes": {"prompt": "覆盖事实规则"}, "reset": []})
        self.assertEqual(fixed.failure.code, "model_prompt_section_readonly")

    async def test_catalog_shows_complete_fixed_templates_without_private_messages(self):
        sections = self.task()["prompt_sections"]
        self.assertNotIn("coherence", {section["key"] for section in sections})
        self.assertNotIn("消息正文组织", str(sections))
        self.assertEqual({section["key"] for section in sections if section["editable"]},
                         {"expression", "news_sharing", "length", "news_length", "style"})
        self.assertEqual(self.section("business")["prompt"], INSTRUCTION)
        self.assertIn("准确来源、原日期和链接留到对方追问时再给", self.section("news_sharing")["prompt"])
        self.assertNotIn("角色自己的设定", str(sections))
        self.assertNotIn("用户先前说过", str(sections))
