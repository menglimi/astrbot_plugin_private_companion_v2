from __future__ import annotations

import asyncio
import json
import unittest

from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.reply_settings import GROUP_AIR_DEFAULTS
from companion_v2.conversation.segmentation import LLM_SEGMENT_MARKER
from companion_v2.conversation.text_processing import TEXT_DEFAULTS
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered


class ReplyManagementTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.host = await self.start()
        self.app = self.host.application
        self.first_batch = self.host.receive(self.event("reply-settings-first")).unwrap()
        self.advance(self.app)
        await self.done(self.app, self.first_batch)
        self.context = self.context(self.app, self.first_batch)
        self.manager = ReplyManagement(self.app, self.context)

    def request(self, status, changes, key="reply-settings"):
        return {"operation_key": key, "edit_token": status["edit_token"], "changes": changes}

    async def test_status_diagnostics_and_preview_are_local_and_consistent(self):
        status = self.manager.status(self.core).unwrap()
        self.assertEqual(status["recent"][0]["batch_id"], self.first_batch)
        self.assertEqual(status["recent"][0]["calls"][0]["state"], "generated")
        self.assertEqual(status["recent"][0]["parts"][0]["state"], "delivered")
        self.assertEqual(status["recent"][0]["parts"][0]["candidate_reason"], "voice_disabled")
        self.assertEqual(status["recent"][0]["parts"][0]["component_order"], [])

        with self.app.runtime.transaction() as connection:
            connection.execute("DELETE FROM conversation_voice_diagnostics WHERE part_id IN "
                               "(SELECT part_id FROM conversation_parts WHERE batch_id = ?)", (self.first_batch,))
        old = self.manager.status(self.core).unwrap()["recent"][0]["parts"][0]
        self.assertIsNone(old["candidate_reason"])
        self.assertIsNone(old["component_order"])

        settings = dict(status["settings"])
        settings.update(enabled=True, llm_controlled=True, rules_enabled=False)
        text = "甲\n" + LLM_SEGMENT_MARKER + "\n乙"
        before = len(self.called)
        preview = self.manager.preview(self.core, settings, text).unwrap()
        self.assertEqual(preview["parts"], ("甲\n", "乙"))
        self.assertEqual(preview["mode"], "offline_preview")
        self.assertEqual(preview["image_position"], "after_text")
        self.assertEqual(len(self.called), before)

    async def test_configuration_is_cas_idempotent_and_captured_by_next_batch(self):
        before = self.manager.status(self.core).unwrap()
        changes = {"enabled": True, "rules_enabled": True, "threshold": 8, "max_segments": 3,
                   "image_position": "before_text"}
        first = self.manager.configure(self.core, self.request(before, changes, "enable-reply")).unwrap()
        self.assertFalse(first["replayed"])
        self.assertNotEqual(first["status"]["edit_token"], before["edit_token"])

        replay = self.manager.configure(self.core, self.request(before, changes, "enable-reply")).unwrap()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation_id"], first["operation_id"])

        conflicting = self.manager.configure(self.core, self.request(before, {"enabled": False}, "enable-reply"))
        self.assertEqual(conflicting.failure.code, "idempotency_key_conflict")

        stale = self.manager.configure(self.core, self.request(before, {"enabled": False}, "stale-token"))
        self.assertEqual(stale.failure.code, "configuration_revision_conflict")

        second_batch = self.host.receive(self.event("reply-settings-second")).unwrap()
        self.advance(self.app)
        await self.done(self.app, second_batch)
        captured = json.loads(self.app.messages.batch(second_batch)["contributions_json"])["reply_settings"]
        self.assertTrue(captured["settings"]["enabled"])
        self.assertTrue(captured["settings"]["rules_enabled"])
        self.assertEqual(captured["settings"]["threshold"], 8)
        self.assertEqual(captured["settings"]["image_position"], "before_text")

        legacy = dict(before["settings"])
        legacy.pop("image_position")
        legacy = {key: value for key, value in legacy.items() if not key.startswith("voice_")}
        self.assertEqual(self.manager.preview(self.core, legacy, "旧回复").unwrap()["image_position"], "after_text")

    async def test_group_air_settings_are_editable_and_sealed_per_batch(self):
        original = json.loads(self.app.messages.batch(self.first_batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertEqual({key: original[key] for key in GROUP_AIR_DEFAULTS}, GROUP_AIR_DEFAULTS)
        status = self.manager.status(self.core).unwrap()
        changes = {"group_air_guard_enabled": False, "group_air_guard_window_seconds": 300,
                   "group_air_guard_max_bot_replies": 5, "group_air_guard_polite_loop_limit": 4}
        saved = self.manager.configure(self.core, self.request(status, changes, "group-air")).unwrap()
        self.assertEqual({key: saved["status"]["settings"][key] for key in changes}, changes)
        batch = self.host.receive(self.event("group-air-next")).unwrap()
        self.advance(self.app)
        await self.done(self.app, batch)
        captured = json.loads(self.app.messages.batch(batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertEqual({key: captured[key] for key in changes}, changes)
        historical = json.loads(self.app.messages.batch(self.first_batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertEqual({key: historical[key] for key in GROUP_AIR_DEFAULTS}, GROUP_AIR_DEFAULTS)

    async def test_text_defaults_preview_and_sealed_send_use_the_same_policy(self):
        original = self.manager.status(self.core).unwrap()
        self.assertEqual({key: original["settings"][key] for key in TEXT_DEFAULTS}, TEXT_DEFAULTS)
        changes = {"enabled": True, "content_cleanup_enabled": True,
                   "content_replacement_enabled": True, "content_replacements": '["hi => 你好"]'}
        saved = self.manager.configure(self.core, self.request(original, changes, "text-enable")).unwrap()["status"]
        text = "hi。\n" + LLM_SEGMENT_MARKER + "\nhi。\n"
        preview = self.manager.preview(self.core, saved["settings"], text).unwrap()
        self.assertEqual(preview["parts"], ("你好。", "你好。"))
        entered, release = asyncio.Event(), asyncio.Event()

        async def model(envelope):
            entered.set()
            await release.wait()
            return answered(text)

        self.model_behavior = model
        sent_before = len(self.sent)
        batch = self.host.receive(self.event("text-sealed")).unwrap()
        self.advance(self.app)
        await asyncio.wait_for(entered.wait(), 3)
        self.manager.configure(self.core, self.request(saved,
            {"content_replacements": '["hi => 新偏好"]'}, "text-next-preference")).unwrap()
        release.set()
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual(tuple(envelope.text for envelope in self.sent[sent_before:]), preview["parts"])
        captured = json.loads(self.app.messages.batch(batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertEqual(captured["content_replacements"], changes["content_replacements"])
        self.assertIn("正文呈现偏好", self.called[-1].original.instruction)

    async def test_invalid_preview_is_rejected_without_model_or_storage_changes(self):
        status = self.manager.status(self.core).unwrap()
        before_calls = len(self.called)
        invalid = dict(status["settings"])
        invalid["max_segments"] = 0
        result = self.manager.preview(self.core, invalid, "正文")
        self.assertEqual(result.failure.code, "reply_configuration_invalid")
        self.assertEqual(len(self.called), before_calls)
        invalid = dict(status["settings"], image_position="unsupported")
        result = self.manager.preview(self.core, invalid, "正文")
        self.assertEqual(result.failure.code, "reply_configuration_invalid")

    async def test_voice_preview_uses_real_segment_and_component_rules_without_synthesis(self):
        settings = dict(self.manager.status(self.core).unwrap()["settings"])
        settings.update(enabled=True, llm_controlled=True, voice_enabled=True,
                        voice_generation_mode="model_tag", voice_segment_mode="last",
                        voice_delivery_mode="voice_only", voice_position="before_text",
                        image_position="before_text", voice_language="ja", voice_ja_provider_id="ja-tts")
        text = "<pc_tts>最初。</pc_tts>前文\n" + LLM_SEGMENT_MARKER + "\n<pc_tts>次。</pc_tts>"
        calls, sends = len(self.called), len(self.sent)
        preview = self.manager.preview(self.core, settings, text, 2).unwrap()
        self.assertEqual(preview["parts"], ("最初。前文\n", "次。"))
        self.assertEqual(preview["image_count"], 2)
        self.assertEqual(preview["voice"], {"enabled": True, "provider_id": "ja-tts",
                                           "instruction": preview["voice"]["instruction"]})
        self.assertEqual([item["speech"] for item in preview["components"]], ["", "次。"])
        self.assertEqual([item["success_order"] for item in preview["components"]],
                         [("text",), ("image", "image", "voice")])
        self.assertEqual(preview["components"][1]["fallback_order"], ("image", "image", "text"))
        self.assertTrue(preview["components"][1]["text_hidden"])
        self.assertEqual((len(self.called), len(self.sent)), (calls, sends))
        self.assertEqual(self.manager.preview(self.core, settings, text, True).failure.code, "reply_preview_invalid")
        self.assertEqual(self.manager.preview(self.core, settings, text, 9).failure.code, "reply_preview_invalid")

    async def test_voice_settings_are_validated_saved_and_captured(self):
        status = self.manager.status(self.core).unwrap()
        self.assertFalse(status["settings"]["voice_enabled"])
        change = {"voice_enabled": True, "voice_trigger_mode": "request", "voice_language": "en",
                  "voice_en_provider_id": "english-tts", "voice_probability": 0.4}
        saved = self.manager.configure(self.core, self.request(status, change, "voice-enable")).unwrap()
        self.assertEqual(saved["status"]["settings"]["voice_en_provider_id"], "english-tts")
        self.assertTrue(self.manager.configure(self.core, self.request(status, change, "voice-enable")).unwrap()["replayed"])
        batch = self.host.receive(self.event("voice-settings-next")).unwrap()
        self.advance(self.app)
        await self.done(self.app, batch)
        captured = json.loads(self.app.messages.batch(batch)["contributions_json"])["reply_settings"]
        self.assertEqual(captured["settings"]["voice_probability"], 0.4)
        self.assertEqual(captured["settings"]["voice_language"], "en")
        current = saved["status"]
        self.assertEqual(self.manager.configure(self.core, self.request(current,
            {"voice_timeout_seconds": 0}, "invalid-voice")).failure.code, "invalid_configuration_value")
        self.assertEqual(self.manager.status(self.core).unwrap()["edit_token"], current["edit_token"])
