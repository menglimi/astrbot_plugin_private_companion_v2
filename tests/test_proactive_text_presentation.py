"""Contact presentation uses sealed preferences without changing delivery replay."""

import json
import unittest

from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.text_processing import text_policy
from tests.proactive_support import ContactFixture
from tests.test_role_tool_loop import answered


class ProactiveTextPresentationTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    def configure_text(self, app, changes, key):
        manager = ReplyManagement(app, self.contact_context())
        status = manager.status(self.core).unwrap()
        return manager.configure(self.core, {"operation_key": key, "edit_token": status["edit_token"],
                                             "changes": changes}).unwrap()

    async def test_contact_seals_text_preferences_and_changes_only_parsed_body(self):
        app = await self.enabled()
        changes = {"content_cleanup_enabled": True, "content_replacement_enabled": True,
                   "content_cleanup_scope": "all", "content_cleanup_words": '["<newline>"]',
                   "content_replacements": '["hi => 你好", "send => skip"]'}
        self.configure_text(app, changes, "contact-text-first")

        async def model(envelope):
            self.configure_text(app, {"content_replacements": '["hi => 新偏好"]'}, "contact-text-next")
            return answered(json.dumps({"decision": "send", "text": "hi。\n下一行。"}, ensure_ascii=False))

        self.model_behavior = model
        task = (await self.contact(app)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual(self.sent[0].text, "你好。下一行。")
        row = self.runtime.read_one("SELECT record_json FROM proactive_contacts WHERE task_id = ?", (task.task_id,))
        document = json.loads(row["record_json"])
        self.assertEqual(document["decision"], "send")
        self.assertEqual(document["presentation_settings"]["content_cleanup_mode"], "words")
        self.assertEqual(document["presentation_settings"]["content_replacements"], changes["content_replacements"])
        self.assertNotIn("正文呈现偏好", self.called[0].original.instruction)
        self.assertEqual((await self.contact(app)).unwrap().task.task_id, task.task_id)
        self.assertEqual((len(self.called), len(self.sent)), (1, 1))

    async def test_humanized_expression_reaches_the_contact_prompt_only_when_enabled(self):
        app = await self.enabled()
        async def model(envelope):
            return answered(json.dumps({"decision": "send", "text": "在的。"}, ensure_ascii=False))

        self.model_behavior = model
        task = (await self.contact(app)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertNotIn("日常表达要求", self.called[0].original.instruction)
        # A second contact in the same run would still be queued behind the first
        # worker, so the switch is applied to the window and proven on the prompt
        # envelope the same path builds. The page-level round trip is covered by
        # tests/test_reply_page.cjs.
        self.configure_text(app, {"enable_humanized_expression": True,
                                  "humanized_expression_prompt": "只说短句，别总结我。"}, "contact-humanized")
        captured = app.reply_settings.capture(self.contact_context(), app.now())["settings"]
        instruction = text_policy(captured).instruction
        self.assertIn("日常表达要求", instruction)
        self.assertIn("只说短句，别总结我。", instruction)

    async def test_internal_reaction_expression_metadata_never_reaches_contact_delivery(self):
        app = await self.enabled()
        metadata = ('<pc_reaction_expression>{"purpose":"轻吐槽","emotion":"无奈",'
                    '"intensity":2}</pc_reaction_expression>')

        async def model(envelope):
            text = "<pc_tts>在的，刚刚在忙。</pc_tts>\n" + metadata
            return answered(json.dumps({"decision": "send", "text": text}, ensure_ascii=False))

        self.model_behavior = model
        task = (await self.contact(app)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual(self.sent[0].text, "在的，刚刚在忙。")
        self.assertNotIn("pc_reaction_expression", self.sent[0].text)
        self.assertNotIn("pc_tts", self.sent[0].text)
        self.assertIn("pc_reaction_expression", self.called[0].original.instruction)
        self.assertIn("pc_tts", self.called[0].original.instruction)

    async def test_cleanup_empty_is_successful_skip_and_restart_never_replays(self):
        app = await self.enabled()
        self.configure_text(app, {"content_cleanup_enabled": True, "content_cleanup_words": '["删"]'},
                            "contact-text-empty")

        async def model(envelope):
            return answered('{"decision":"send","text":"删"}')

        self.model_behavior = model
        opportunity = self.opportunity()
        task = (await self.contact(app, opportunity)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        self.assertTrue(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["skipped"])
        row = self.runtime.read_one("SELECT record_json, body FROM proactive_contacts WHERE task_id = ?", (task.task_id,))
        self.assertEqual(row["body"], "")
        self.assertEqual(json.loads(row["record_json"])["presentation_reason"], "presentation_empty")
        self.assertEqual(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["skip_reason"],
                         "presentation_empty")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM background_deliveries", ())[0], 0)
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        self.configure_text(restarted, {"content_cleanup_enabled": False}, "contact-text-after-restart")
        self.assertEqual((await self.contact(restarted, opportunity)).unwrap().task.task_id, task.task_id)
        self.assertEqual((len(self.called), len(self.sent)), (1, 0))


if __name__ == "__main__":
    unittest.main()
