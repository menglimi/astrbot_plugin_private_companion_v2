# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    SystemMessageSegment,
    TextPart,
    UserMessageSegment,
    dump_messages_with_checkpoints,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.provider.entities import LLMResponse

from astrbot_plugin_private_companion.group_context_interception import (
    GROUP_CONTEXT_STASH_ATTR,
    intercept_astrbot_group_context,
    restore_astrbot_group_history,
    strip_astrbot_group_icl_parts,
)
from astrbot_plugin_private_companion.group_prompt_context import GROUP_HISTORY_INJECTED_ATTR
from astrbot_plugin_private_companion.main import PrivateCompanionPlugin
from astrbot_plugin_private_companion.config_migration import migrate_flat_config_into_schema_groups
from astrbot_plugin_private_companion.page_api import PrivateCompanionPageApi


ROOT = Path(__file__).resolve().parents[1]
GROUP_ICL_TEXT = (
    "<system_reminder>You are in a group chat. "
    "Belows are group chat context after your last reply:\n"
    "--- BEGIN CONTEXT---\n"
    "[群友/12:00:00]: 之前的消息\n"
    "--- END CONTEXT ---\n</system_reminder>"
)


class GroupContextInterceptionTests(unittest.TestCase):
    def test_only_astrbot_group_icl_part_is_removed(self) -> None:
        plugin_part = TextPart(text="<!-- private_companion_group_context_v1 -->\n插件群上下文")
        unrelated_part = TextPart(text="<system_reminder>其他插件提醒</system_reminder>")

        kept, removed = strip_astrbot_group_icl_parts(
            [TextPart(text=GROUP_ICL_TEXT), plugin_part, unrelated_part]
        )

        self.assertEqual(removed, 1)
        self.assertEqual(kept, [plugin_part, unrelated_part])

    def test_history_is_hidden_for_provider_then_restored_before_core_save(self) -> None:
        stored_history = [
            UserMessageSegment(content="旧问题").model_dump(),
            AssistantMessageSegment(content="旧回答").model_dump(),
        ]
        conversation = SimpleNamespace(cid="conversation-1", history=json.dumps(stored_history, ensure_ascii=False))
        request = SimpleNamespace(
            conversation=conversation,
            contexts=list(stored_history),
            extra_user_content_parts=[
                TextPart(text=GROUP_ICL_TEXT),
                TextPart(text="<!-- private_companion_group_context_v1 -->\n插件群上下文"),
            ],
        )
        event = SimpleNamespace()

        intercepted = intercept_astrbot_group_context(event, request)

        self.assertTrue(intercepted["history_intercepted"])
        self.assertEqual(intercepted["history_messages"], 2)
        self.assertEqual(intercepted["group_icl_removed"], 1)
        self.assertEqual(request.contexts, [])
        self.assertEqual(len(request.extra_user_content_parts), 1)
        self.assertEqual(json.loads(conversation.history), stored_history)

        run_context = SimpleNamespace(
            messages=[
                SystemMessageSegment(content="人格"),
                UserMessageSegment(content="当前问题"),
                AssistantMessageSegment(content="当前回答"),
            ]
        )
        restored = restore_astrbot_group_history(event, run_context)

        self.assertTrue(restored["restored"])
        self.assertEqual(
            [message.role for message in run_context.messages],
            ["system", "user", "assistant", "user", "assistant"],
        )
        saved = dump_messages_with_checkpoints(run_context.messages[1:])
        self.assertEqual([message["content"] for message in saved], ["旧问题", "旧回答", "当前问题", "当前回答"])
        self.assertIs(request.conversation, conversation)
        self.assertEqual(request.contexts, stored_history)

        repeated = restore_astrbot_group_history(event, run_context)
        self.assertEqual(repeated["reason"], "already_restored")
        self.assertEqual(
            [message.role for message in run_context.messages],
            ["system", "user", "assistant", "user", "assistant"],
        )

    def test_restore_failure_prevents_core_from_overwriting_old_history(self) -> None:
        request = SimpleNamespace(
            conversation=SimpleNamespace(cid="conversation-1"),
            contexts=[UserMessageSegment(content="旧问题").model_dump()],
            extra_user_content_parts=[],
        )
        event = SimpleNamespace()
        intercept_astrbot_group_context(event, request)
        getattr(event, GROUP_CONTEXT_STASH_ATTR)["conversation_id"] = "other-conversation"

        result = restore_astrbot_group_history(event, SimpleNamespace(messages=[]))

        self.assertTrue(result["failed"])
        self.assertIsNone(request.conversation)

    def test_schema_and_both_panels_expose_persona_setting_in_context_range(self) -> None:
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        item = schema["group_observation_config"]["items"]["intercept_astrbot_group_context"]
        history_item = schema["group_scene_config"]["items"]["enable_group_history_injection"]
        self.assertEqual(item["description"], "拦截AstrBot群聊对话注入")
        self.assertTrue(item["default"])
        self.assertEqual(
            item["hint"],
            "开启后，只有本轮插件群聊时间线确实包含历史消息时才拦截 AstrBot 会话历史和官方群聊 ICL，防止重复注入；插件刚安装、暂无群历史时会自动保留 AstrBot 官方上下文，避免旧聊天记录突然消失。",
        )
        self.assertEqual(
            item["condition"],
            {
                "enable_group_context_injection": True,
                "enable_group_history_injection": True,
            },
        )
        self.assertTrue(history_item["default"])

        for relative in ("pages/companion-panel/app.js", "pages/陪伴面板/app.js"):
            script = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('intercept_astrbot_group_context: "拦截AstrBot群聊对话注入"', script)
            self.assertIn(
                'enable_group_context_injection: ["max_group_recent_messages", "enable_group_history_injection", "group_scene_recent_limit", "group_scene_recent_max_chars", "intercept_astrbot_group_context"',
                script,
            )
            detail_section = script.split('title: "上下文范围"', 1)[1].split("},", 1)[0]
            self.assertIn("intercept_astrbot_group_context", detail_section)

    def test_legacy_flat_setting_migrates_to_group_observation_config(self) -> None:
        config = {
            "intercept_astrbot_group_context": False,
            "enable_group_history_injection": False,
        }

        migrate_flat_config_into_schema_groups(
            config,
            schema_path=ROOT / "_conf_schema.json",
            save=False,
        )

        self.assertFalse(
            config["group_observation_config"]["intercept_astrbot_group_context"]
        )
        self.assertFalse(
            config["group_scene_config"]["enable_group_history_injection"]
        )

    def test_page_api_accepts_and_normalizes_interception_setting(self) -> None:
        api = PrivateCompanionPageApi.__new__(PrivateCompanionPageApi)
        api.plugin = SimpleNamespace()
        api._schema_key_index_cache = None

        self.assertIn("intercept_astrbot_group_context", api._allowed_setting_keys())
        self.assertIn("enable_group_history_injection", api._allowed_setting_keys())
        self.assertTrue(
            api._normalize_setting_value("intercept_astrbot_group_context", "true")
        )
        self.assertFalse(
            api._normalize_setting_value("intercept_astrbot_group_context", "false")
        )
        self.assertTrue(
            api._normalize_setting_value("enable_group_history_injection", "true")
        )
        self.assertFalse(
            api._normalize_setting_value("enable_group_history_injection", "false")
        )
        self.assertEqual(2, api._normalize_setting_value("group_scene_recent_limit", 0))
        self.assertEqual(20, api._normalize_setting_value("group_scene_recent_limit", "invalid"))


class GroupContextInterceptionHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_hook_does_not_intercept_when_disabled_or_in_private_chat(self) -> None:
        plugin = PrivateCompanionPlugin.__new__(PrivateCompanionPlugin)
        plugin.enabled = True
        enabled = False
        plugin.persona_setting = lambda key, default=None: (
            enabled if key == "intercept_astrbot_group_context" else default
        )
        request = SimpleNamespace(
            conversation=SimpleNamespace(cid="conversation-1"),
            contexts=[UserMessageSegment(content="旧问题").model_dump()],
            extra_user_content_parts=[TextPart(text=GROUP_ICL_TEXT)],
            system_prompt="群聊人格\n<!-- private_companion_group_context_v1 -->\n插件群上下文",
            prompt="当前问题",
        )
        event = SimpleNamespace(
            unified_msg_origin="qq_official:GroupMessage:group-1",
            is_private_chat=lambda: False,
        )
        setattr(event, GROUP_HISTORY_INJECTED_ATTR, True)
        hook = PrivateCompanionPlugin.intercept_native_astrbot_group_context.__wrapped__

        await hook(plugin, event, request)
        self.assertFalse(hasattr(event, GROUP_CONTEXT_STASH_ATTR))
        self.assertEqual(len(request.contexts), 1)

        enabled = True
        event.is_private_chat = lambda: True
        await hook(plugin, event, request)
        self.assertFalse(hasattr(event, GROUP_CONTEXT_STASH_ATTR))
        self.assertEqual(len(request.extra_user_content_parts), 1)

    async def test_hook_preserves_astrbot_history_without_plugin_history(self) -> None:
        plugin = PrivateCompanionPlugin.__new__(PrivateCompanionPlugin)
        plugin.enabled = True
        plugin.persona_setting = lambda key, default=None: (
            True if key == "intercept_astrbot_group_context" else default
        )
        event = SimpleNamespace(
            unified_msg_origin="qq_official:GroupMessage:group-1",
            is_private_chat=lambda: False,
        )
        request = SimpleNamespace(
            conversation=SimpleNamespace(cid="conversation-1"),
            contexts=[UserMessageSegment(content="旧问题").model_dump()],
            extra_user_content_parts=[TextPart(text=GROUP_ICL_TEXT)],
            system_prompt="群聊人格",
            prompt="当前问题",
        )
        hook = PrivateCompanionPlugin.intercept_native_astrbot_group_context.__wrapped__

        await hook(plugin, event, request)

        # No plugin timeline yet: AstrBot's own history must survive.
        self.assertFalse(hasattr(event, GROUP_CONTEXT_STASH_ATTR))
        self.assertEqual(len(request.contexts), 1)
        self.assertEqual(len(request.extra_user_content_parts), 1)

        request.system_prompt += "\n<!-- private_companion_group_context_v1 -->\n插件群上下文"
        setattr(event, GROUP_HISTORY_INJECTED_ATTR, True)
        await hook(plugin, event, request)

        self.assertTrue(hasattr(event, GROUP_CONTEXT_STASH_ATTR))
        self.assertEqual(request.contexts, [])
        self.assertEqual(request.extra_user_content_parts, [])

    async def test_hook_keeps_astrbot_history_when_plugin_history_is_disabled(self) -> None:
        plugin = PrivateCompanionPlugin.__new__(PrivateCompanionPlugin)
        plugin.enabled = True
        plugin.persona_setting = lambda key, default=None: {
            "intercept_astrbot_group_context": True,
            "enable_group_history_injection": False,
        }.get(key, default)
        request = SimpleNamespace(
            conversation=SimpleNamespace(cid="conversation-1"),
            contexts=[UserMessageSegment(content="旧问题").model_dump()],
            extra_user_content_parts=[TextPart(text=GROUP_ICL_TEXT)],
            system_prompt="群聊人格\n<!-- private_companion_group_context_v1 -->\n插件群上下文",
            prompt="当前问题",
        )
        event = SimpleNamespace(
            unified_msg_origin="qq_official:GroupMessage:group-1",
            is_private_chat=lambda: False,
        )
        setattr(event, GROUP_HISTORY_INJECTED_ATTR, True)

        hook = PrivateCompanionPlugin.intercept_native_astrbot_group_context.__wrapped__
        await hook(plugin, event, request)

        self.assertFalse(hasattr(event, GROUP_CONTEXT_STASH_ATTR))
        self.assertEqual(1, len(request.contexts))
        self.assertEqual(1, len(request.extra_user_content_parts))

    async def test_astrbot_core_saves_restored_history_plus_current_turn(self) -> None:
        stored_history = [
            UserMessageSegment(content="旧问题").model_dump(),
            AssistantMessageSegment(content="旧回答").model_dump(),
        ]
        conversation = SimpleNamespace(cid="conversation-1", token_usage=0)
        request = SimpleNamespace(
            conversation=conversation,
            contexts=list(stored_history),
            extra_user_content_parts=[TextPart(text=GROUP_ICL_TEXT)],
            tool_calls_result=[],
        )
        event = SimpleNamespace(
            unified_msg_origin="qq_official:GroupMessage:group-1",
            get_extra=lambda _key, default=None: default,
        )
        intercept_astrbot_group_context(event, request)
        run_context = SimpleNamespace(
            messages=[
                SystemMessageSegment(content="人格"),
                UserMessageSegment(content="当前问题"),
                AssistantMessageSegment(content="当前回答"),
            ]
        )
        restore_astrbot_group_history(event, run_context)
        stage = InternalAgentSubStage.__new__(InternalAgentSubStage)
        stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())

        await stage._save_to_history(
            event,
            request,
            LLMResponse(role="assistant", completion_text="当前回答"),
            run_context.messages,
            runner_stats=None,
        )

        stage.conv_manager.update_conversation.assert_awaited_once()
        saved_history = stage.conv_manager.update_conversation.await_args.kwargs["history"]
        self.assertEqual(
            [message["content"] for message in saved_history],
            ["旧问题", "旧回答", "当前问题", "当前回答"],
        )
        self.assertNotIn("BEGIN CONTEXT", json.dumps(saved_history, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
