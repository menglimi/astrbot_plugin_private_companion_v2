"""Exercise AstrBot's actual media tool and Context sender without network IO."""

from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_core_reply_pipeline import PipelineEvent
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.tools.message_tools import SendMessageToUserTool
from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA, prepare_core_reply_event
from astrbot_host.core_reply_native_send import inject_core_reply_send_tool
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome


class CoreReplyNativeSendTests(unittest.IsolatedAsyncioTestCase):
    def prepare(self, *, platform=True):
        event = PipelineEvent()
        self.platform = NS(meta=lambda: NS(id="qq-main"), send_by_session=AsyncMock())
        host = Context.__new__(Context)
        host.platform_manager = NS(platform_insts=[self.platform] if platform else [])
        host.astrbot_config_mgr = NS(get_conf=lambda _: {})
        self.host = host
        self.authorize = AsyncMock(return_value=Outcome.success(True))
        self.observed, self.stages = [], []
        prepare_core_reply_event(event, {"event_id": "native-send", "context": object()},
            authorize=self.authorize, on_sent=lambda prepared, text: self.observed.append(text),
            on_delivery=self.stages.append)
        original = SendMessageToUserTool()
        self.original = original
        self.shared_tools = ToolSet(tools=[original])
        request = ProviderRequest(func_tool=self.shared_tools)
        self.assertTrue(inject_core_reply_send_tool(event, request))
        wrapper = ContextWrapper(context=AstrAgentContext(context=host, event=event))
        return event, wrapper, request.func_tool.get_tool(original.name)

    async def test_real_native_tool_sends_via_core_without_mutating_shared_context(self):
        event, wrapper, tool = self.prepare()
        with patch("astrbot_host.core_reply_reactions.observe_core_media_send_returned") as media:
            result = await tool.call(wrapper, messages=[{"type": "plain", "text": "看我找到的！"},
                {"type": "image", "url": "https://example.invalid/original.png"}])
        self.assertIn("sent", result.lower())
        self.platform.send_by_session.assert_awaited_once()
        target, chain = self.platform.send_by_session.call_args.args
        self.assertEqual(str(target), event.unified_msg_origin)
        self.assertEqual(chain.get_plain_text(), "看我找到的！")
        self.assertEqual(self.observed, ["看我找到的！"])
        self.assertEqual(self.stages, ["started", "returned", "finished"])
        self.assertEqual(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["send_returns"], 1)
        self.assertEqual(event.sent, [])
        self.assertIs(wrapper.context.context, self.host)
        self.assertIs(self.shared_tools.get_tool(self.original.name), self.original)
        media.assert_called_once()

    async def test_permission_revoked_before_actual_native_tool_send(self):
        event, wrapper, tool = self.prepare()
        self.authorize.return_value = Outcome.failed("private_access_dialogue_denied", "revoked")
        with self.assertRaises(TaskError):
            await tool.call(wrapper, messages=[{"type": "plain", "text": "秘密"}])
        self.platform.send_by_session.assert_not_awaited()
        self.assertEqual(self.observed, [])
        self.assertTrue(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["denial_notified"])

    async def test_native_tool_text_uses_cleanup_and_replacement_and_keeps_media(self):
        event, wrapper, tool = self.prepare()
        event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["prepared"]["presentation_settings"] = {
            "content_cleanup_enabled": True, "content_cleanup_scope": "trailing",
            "content_cleanup_words": '["。"]', "content_replacement_enabled": True,
            "content_replacements": '["a => aa"]'}
        await tool.call(wrapper, messages=[{"type": "plain", "text": "a。"},
            {"type": "image", "url": "https://example.invalid/original.png"}])
        chain = self.platform.send_by_session.call_args.args[1]
        self.assertEqual(chain.get_plain_text(), "aa")
        self.assertEqual(len(chain.chain), 2)
        self.assertEqual(self.observed, ["aa"])
        self.assertIn("aa", event.get_extra("_send_message_to_user_current_session_plain_texts"))
        self.assertIn("a。", event.get_extra("_send_message_to_user_current_session_plain_texts"))

    async def test_native_tool_empty_after_cleanup_never_attempts_send(self):
        event, wrapper, tool = self.prepare()
        event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["prepared"]["presentation_settings"] = {
            "content_cleanup_enabled": True, "content_cleanup_words": '["删"]'}
        with self.assertRaises(TaskError) as removed:
            await tool.call(wrapper, messages=[{"type": "plain", "text": "删"}])
        self.assertEqual(removed.exception.code, "core_reply_text_removed")
        self.platform.send_by_session.assert_not_awaited()
        self.assertEqual(self.observed, [])

    async def test_current_reply_tool_rejects_cross_session_even_for_admin(self):
        event, wrapper, tool = self.prepare()
        event.role = "admin"
        with self.assertRaises(TaskError):
            await tool.call(wrapper, session="qq-main:FriendMessage:other",
                            messages=[{"type": "plain", "text": "秘密"}])
        self.platform.send_by_session.assert_not_awaited()
        self.assertEqual(self.stages, [])

    async def test_native_send_exception_remains_unknown_and_is_not_replayed(self):
        event, wrapper, tool = self.prepare()
        self.platform.send_by_session.side_effect = RuntimeError("unknown platform outcome")
        arguments = {"messages": [{"type": "image", "url": "https://example.invalid/original.png"}]}
        with self.assertRaises(RuntimeError):
            await tool.call(wrapper, **arguments)
        with self.assertRaises(TaskError) as repeated:
            await tool.call(wrapper, **arguments)
        self.assertEqual(repeated.exception.code, "core_reply_delivery_unknown")
        self.platform.send_by_session.assert_awaited_once()
        self.assertEqual(self.stages, ["started", "unknown", "finished"])
        self.assertEqual(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["send_unknown"], 1)
        self.assertEqual(self.observed, [])

    async def test_missing_platform_is_known_failure_not_success_or_unknown(self):
        event, wrapper, tool = self.prepare(platform=False)
        with self.assertRaises(TaskError) as missing:
            await tool.call(wrapper, messages=[{"type": "plain", "text": "你好"}])
        self.assertEqual(missing.exception.code, "core_reply_platform_unavailable")
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        self.assertEqual((state["send_failed"], state["send_returns"], state["send_unknown"]), (1, 0, 0))
        self.assertEqual(self.stages, ["started", "failed", "finished"])
        self.assertEqual(self.observed, [])

    async def test_media_observation_failure_does_not_block_core_send(self):
        event, wrapper, tool = self.prepare()
        with patch("astrbot_host.core_reply_reactions.observe_core_media_send_returned", side_effect=RuntimeError("statistics")):
            result = await tool.call(wrapper, messages=[{"type": "plain", "text": "你好"}])
        self.assertIn("sent", result.lower())
        self.platform.send_by_session.assert_awaited_once()
        self.assertEqual(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["send_returns"], 1)
