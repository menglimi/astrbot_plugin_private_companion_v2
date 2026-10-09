from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace

from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.reply_settings import FORWARD_DEFAULTS, GROUP_AIR_DEFAULTS, validate as validate_reply_settings
from companion_v2.conversation.segmentation import LLM_SEGMENT_MARKER
from companion_v2.conversation.text_processing import TEXT_DEFAULTS
from companion_v2.model_gateway.response_diagnostics import ResponseDiagnostics, ResponseTextSummary
from companion_v2.execution.models import encode
from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.foundation.refs import ScopeKind
from companion_v2.conversation.media.understanding import SCOPE_PERMISSION_FIELDS, media_scope_enabled
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
        recent = status["recent"][0]
        self.assertEqual(recent["batch_id"], self.first_batch)
        self.assertEqual(recent["calls"][0]["state"], "generated")
        self.assertEqual(recent["turn_type"], "conversation.reply")
        self.assertEqual(recent["current_inputs"], 1)
        self.assertEqual(status["recent_limit"], 80)
        self.assertIsNone(recent["calls"][0]["response_diagnostics"])
        self.assertEqual(recent["parts"][0]["state"], "delivered")
        self.assertEqual(recent["parts"][0]["candidate_reason"], "voice_disabled")
        self.assertEqual(recent["parts"][0]["component_order"], [])
        self.assertEqual(recent["response_type"], "text_or_mixed")
        self.assertEqual(recent["group_history_items"], 0)
        self.assertEqual(recent["injected_materials"], [])
        self.assertNotIn("captured", recent)
        self.assertNotIn("自定义提示词", json.dumps(recent, ensure_ascii=False))
        self.assertIsInstance(recent["offered_tools"], list)
        self.assertIsInstance(recent["filtered_tools"], list)
        self.assertIsInstance(recent["rounds"], list)
        self.assertIsInstance(recent["tool_calls"], list)

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
        self.assertEqual(preview["parts"], ("甲", "乙"))
        self.assertEqual(preview["mode"], "offline_preview")
        self.assertEqual(preview["image_position"], "after_text")
        self.assertEqual(len(self.called), before)

    async def test_reply_diagnostics_limit_and_response_summary_apply_to_the_current_window(self):
        diagnostic = ResponseDiagnostics(True, "stop", "validated",
            raw=ResponseTextSummary.from_text('{"text":"private model body"}'),
            visible=ResponseTextSummary.from_text("private model body"))
        call_id = self.app.runtime.read_one("SELECT call_id FROM model_calls ORDER BY rowid LIMIT 1", ())["call_id"]
        with self.app.runtime.transaction() as connection:
            connection.execute("INSERT INTO model_call_diagnostics VALUES (?, ?, ?)",
                               (call_id, encode(diagnostic.to_record()), self.app.now().isoformat()))
            for index in range(12):
                connection.execute("""INSERT INTO conversation_batches(batch_id, origin_key, context_json,
                    role_instruction, state, revision, created_at, contributions_json)
                    SELECT ?, origin_key, context_json, role_instruction, 'sealed', 1, created_at, '{}'
                    FROM conversation_batches WHERE batch_id = ?""", (f"diagnostic-batch-{index}", self.first_batch))
        status = self.manager.status(self.core).unwrap()
        self.assertEqual(len(status["recent"]), 13)
        original = next(item for item in status["recent"] if item["batch_id"] == self.first_batch)
        self.assertEqual(original["calls"][0]["response_diagnostics"], diagnostic.to_record())
        self.assertNotIn("private model body", json.dumps(status["recent"]))
        saved = self.manager.configure(self.core, self.request(status, {"reply_diagnostic_limit": 10}, "diagnostic-limit")).unwrap()
        self.assertEqual(saved["status"]["recent_limit"], 10)
        self.assertEqual(len(saved["status"]["recent"]), 10)

    async def test_configuration_is_cas_idempotent_and_captured_by_next_batch(self):
        before = self.manager.status(self.core).unwrap()
        changes = {"enabled": True, "rules_enabled": False, "threshold": 8, "max_segments": 3,
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

    async def test_forward_reading_setting_is_validated_and_sealed_per_batch(self):
        before = self.manager.status(self.core).unwrap()
        self.assertEqual({key: before["settings"][key] for key in FORWARD_DEFAULTS}, FORWARD_DEFAULTS)
        saved = self.manager.configure(self.core, self.request(
            before, {"forward_message_adaptation_enabled": False}, "disable-forward-reading")).unwrap()
        batch = self.host.receive(self.event("forward-reading-disabled")).unwrap()
        self.advance(self.app)
        await self.done(self.app, batch)
        captured = json.loads(self.app.messages.batch(batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertFalse(captured["forward_message_adaptation_enabled"])
        self.assertTrue(json.loads(self.app.messages.batch(self.first_batch)["contributions_json"])
                        ["reply_settings"]["settings"]["forward_message_adaptation_enabled"])
        legacy = dict(before["settings"])
        legacy.pop("forward_message_adaptation_enabled")
        validate_reply_settings(legacy)
        with self.assertRaises(ConfigurationError):
            validate_reply_settings({**saved["status"]["settings"], "forward_message_adaptation_enabled": 1})

    async def test_image_narration_controls_are_bounded_and_saved_per_window(self):
        status = self.manager.status(self.core).unwrap()
        settings = status["settings"]
        self.assertFalse(settings["enable_private_image_self_recognition"])
        self.assertTrue(settings["enable_private_image_vision_cache"])
        changes = {"enable_private_image_self_recognition": True,
                   "private_image_vision_custom_prompt": "优先描述清晰可读的文字。",
                   "private_image_vision_max_chars": 600,
                   "private_image_vision_wait_seconds": 4,
                   "private_image_provider_failure_cooldown_seconds": 90}
        saved = self.manager.configure(self.core, self.request(status, changes, "image-narration")).unwrap()
        self.assertEqual({key: saved["status"]["settings"][key] for key in changes}, changes)
        invalid = dict(saved["status"]["settings"], private_image_vision_wait_seconds=31)
        self.assertEqual(self.manager.preview(self.core, invalid, "正文").failure.code,
                         "reply_configuration_invalid")

    async def test_media_scope_permissions_are_role_shared_and_gate_private_or_group_work(self):
        status = self.manager.status(self.core).unwrap()
        changes = {
            "image_understanding_private_enabled": False,
            "image_understanding_group_enabled": True,
            "video_understanding_private_enabled": True,
            "video_understanding_group_enabled": False,
            "file_understanding_private_enabled": False,
            "file_understanding_group_enabled": True,
        }
        saved = self.manager.configure(self.core,
            self.request(status, changes, "media-scope-permissions")).unwrap()
        settings = saved["status"]["settings"]
        self.assertEqual({key: settings[key] for key in changes}, changes)
        for name in changes:
            expected_layers = ["role", "window"] if name in SCOPE_PERMISSION_FIELDS else ["window"]
            self.assertEqual(saved["status"]["fields"][name]["editable_layers"], expected_layers)
        self.assertFalse(media_scope_enabled(settings, "image_understanding", ScopeKind.PRIVATE))
        self.assertTrue(media_scope_enabled(settings, "image_understanding", ScopeKind.GROUP))
        self.assertTrue(media_scope_enabled(settings, "video_understanding", ScopeKind.PRIVATE))
        self.assertFalse(media_scope_enabled(settings, "video_understanding", ScopeKind.GROUP))
        self.assertFalse(media_scope_enabled(settings, "file_understanding", ScopeKind.PRIVATE))
        self.assertTrue(media_scope_enabled(settings, "file_understanding", ScopeKind.GROUP))

        group_scope = replace(self.context.scope, kind=ScopeKind.GROUP, native_scope_id="group-window")
        group_target = ConfigTarget(group_scope.installation_id, ConfigLayer.WINDOW,
            self.context.role_binding.role, group_scope)
        group_manager = ReplyManagement(self.app, target=group_target)
        group_settings = group_manager.status(self.core).unwrap()["settings"]
        self.assertEqual({key: group_settings[key] for key in changes}, changes)

    async def test_video_and_file_understanding_controls_are_saved_per_window(self):
        status = self.manager.status(self.core).unwrap()
        settings = status["settings"]
        changes = {
            "video_understanding_enabled": True,
            "video_understanding_max_chars": 3200,
            "video_understanding_wait_seconds": 25,
            "video_understanding_prompt": "先概括动作顺序。",
            "video_self_recognition_hint": "角色水印是蓝色月牙。",
            "file_understanding_enabled": True,
            "file_understanding_formats": "text_only",
            "file_understanding_format_groups": "文本\nPDF\nWord（DOCX）",
            "file_understanding_max_size_mb": 6,
            "file_understanding_max_chars": 12000,
            "file_understanding_timeout_seconds": 12,
            "file_understanding_prompt": "优先解释标题和表格。",
        }
        saved = self.manager.configure(self.core,
            self.request(status, changes, "media-understanding-preferences")).unwrap()
        self.assertEqual({key: saved["status"]["settings"][key] for key in changes}, changes)

        invalid = dict(saved["status"]["settings"], file_understanding_timeout_seconds=31)
        self.assertEqual(self.manager.preview(self.core, invalid, "正文").failure.code,
                         "reply_configuration_invalid")

    async def test_text_defaults_preview_and_sealed_send_use_the_same_policy(self):
        original = self.manager.status(self.core).unwrap()
        # HostFixture disables punctuation cleanup until this test enables it.
        self.assertEqual({key: original["settings"][key] for key in TEXT_DEFAULTS},
                         {**TEXT_DEFAULTS, "content_cleanup_enabled": False})
        changes = {"enabled": True, "llm_controlled": True, "content_cleanup_enabled": True,
                   "content_cleanup_words": '["。", "\\n"]',
                   "content_replacement_enabled": True, "content_replacements": '["hi => 你好"]'}
        saved = self.manager.configure(self.core, self.request(original, changes, "text-enable")).unwrap()["status"]
        text = "hi。\n" + LLM_SEGMENT_MARKER + "\nhi。\n"
        preview = self.manager.preview(self.core, saved["settings"], text).unwrap()
        self.assertEqual(preview["parts"], ("你好", "你好"))
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
        self.assertEqual(preview["parts"], ("最初。前文", "次。"))
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

    async def test_explicit_turn_language_uses_matching_tts_provider_without_changing_saved_language(self):
        status = self.manager.status(self.core).unwrap()
        self.manager.configure(self.core, self.request(status, {
            "voice_enabled": True,
            "voice_trigger_mode": "always",
            "voice_language": "zh",
            "voice_en_provider_id": "english-tts",
        }, "voice-turn-language")).unwrap()
        self.model_behavior = lambda _envelope: asyncio.sleep(0, result=answered("Hello there."))

        batch = self.host.receive(self.event(text="这次请用英语回答我")).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")

        plans = self.app.runtime.read_all("""SELECT v.provider_id FROM conversation_voice_parts v
            JOIN conversation_parts p USING(part_id) WHERE p.batch_id = ? ORDER BY p.sequence""", (batch,))
        captured = json.loads(self.app.messages.batch(batch)["contributions_json"])["reply_settings"]["settings"]
        self.assertTrue(plans)
        self.assertEqual({row["provider_id"] for row in plans}, {"english-tts"})
        self.assertEqual(captured["voice_language"], "zh")
