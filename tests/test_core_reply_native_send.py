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
from companion_v2.conversation.voice_reply import VoiceReplyPolicy
from companion_v2.foundation.outcome import Outcome


class CoreReplyNativeSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_tool_missing_speech_uses_current_runner_before_platform_delivery(self):
        from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
        from astrbot.core.message.components import Plain, Record
        from astrbot_host.core_reply_voice import prepare_core_reply_voice_message
        from astrbot_host.core_reply_voice_authoring import bind_core_voice_authoring, restore_core_voice_authoring
        from tests.test_core_reply_voice_authoring import Provider
        event, wrapper, tool = self.prepare()
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        state["prepared"]["voice_reply_policy"] = VoiceReplyPolicy(generation_mode="model_tag", language="ja",
            foreign_text_mode="translation")
        runner = ToolLoopAgentRunner()
        request = ProviderRequest(prompt="在干嘛呢")
        provider = Provider("<pc_tts>君と話してるよ。</pc_tts>我在陪你聊天呀。")
        await runner.reset(provider=provider, request=request, run_context=NS(context=NS(event=event), messages=[]),
            tool_executor=None, agent_hooks=None)
        bind_core_voice_authoring(event, runner)
        rendered = []
        async def render(_, text, **__):
            rendered.append(text)
            return {"type": "record", "data": {"file": "base64://YQ=="}}
        async def prepare(current, message, check, index, count):
            return await prepare_core_reply_voice_message(event, current, message, renderer=render,
                delivery=None, authorize=check)
        state["prepare_send"] = prepare
        try:
            await tool.call(wrapper, messages=[{"type":"plain", "text":"我在陪你聊天呀。"}])
        finally:
            restore_core_voice_authoring(event)
        chains = [call.args[1] for call in self.platform.send_by_session.call_args_list]
        self.assertEqual([[type(component) for component in chain.chain] for chain in chains], [[Plain], [Record]])
        self.assertEqual(rendered, ["君と話してるよ。"])
        self.assertEqual(chains[0].get_plain_text(), "我在陪你聊天呀。")
        self.assertIs(runner.req, request)
        self.assertIsNone(provider.calls[0]["func_tool"])

    async def test_native_tool_voice_is_captured_before_text_replacement_without_response_hook(self):
        from astrbot.core.message.components import Plain, Record
        from astrbot_host.core_reply_voice import prepare_core_reply_voice_message
        event, wrapper, tool = self.prepare()
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        state["prepared"].update(voice_reply_policy=VoiceReplyPolicy(generation_mode="model_tag", language="ja",
            foreign_text_mode="translation"), presentation_settings={"content_replacement_enabled": True,
            "content_replacements": '["晚安 => 早点休息"]'})
        rendered = []
        async def render(_, text, **__):
            rendered.append(text)
            return {"type": "record", "data": {"file": "base64://YQ=="}}
        async def prepare(current, message, check, index, count):
            return await prepare_core_reply_voice_message(event, current, message, renderer=render,
                delivery=None, authorize=check)
        state["prepare_send"] = prepare
        await tool.call(wrapper, messages=[{"type": "plain", "text": "<pc_tts>おやすみ。</pc_tts>晚安。"}])
        chains = [call.args[1] for call in self.platform.send_by_session.call_args_list]
        self.assertEqual(rendered, ["おやすみ。"])
        self.assertEqual([[type(component) for component in chain.chain] for chain in chains], [[Plain], [Record]])
        self.assertEqual(chains[0].get_plain_text(), "早点休息。")

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

    def attach_voice(self, event):
        from astrbot_host.core_reply_voice import prepare_core_reply_voice_message
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        state["prepared"]["voice_reply_policy"] = VoiceReplyPolicy()
        render = AsyncMock(return_value={"type": "record", "data": {"file": "base64://YQ=="}})
        async def prepare(current, message, authorize, index, count):
            return await prepare_core_reply_voice_message(event, current, message,
                renderer=render, delivery=None, authorize=authorize)
        state["prepare_send"] = prepare
        return render

    async def test_native_media_tool_also_synthesizes_and_separates_qq_voice(self):
        from astrbot.core.message.components import Plain, Record
        event, wrapper, tool = self.prepare()
        render = self.attach_voice(event)
        await tool.call(wrapper, messages=[{"type": "plain", "text": "你好"}])
        self.assertEqual(self.platform.send_by_session.await_count, 2)
        self.assertEqual([[type(part) for part in call.args[1].chain]
                          for call in self.platform.send_by_session.await_args_list], [[Plain], [Record]])
        render.assert_awaited_once()
        self.assertEqual(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["send_returns"], 2)

    async def test_partially_sent_voice_tool_records_text_and_never_replays_the_prefix(self):
        event, wrapper, tool = self.prepare()
        self.attach_voice(event)
        async def disconnect_after_text(*_):
            self.host.platform_manager.platform_insts = []
        self.platform.send_by_session.side_effect = disconnect_after_text
        arguments = {"messages": [{"type": "plain", "text": "你好"}]}
        with self.assertRaises(TaskError):
            await tool.call(wrapper, **arguments)
        state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
        self.assertEqual((state["send_returns"], state["send_failed"], state["send_unknown"]), (1, 1, 0))
        self.assertEqual(self.observed, ["你好"])
        self.assertIn("你好", event.get_extra("_send_message_to_user_current_session_plain_texts"))
        self.host.platform_manager.platform_insts = [self.platform]
        with self.assertRaises(TaskError):
            await tool.call(wrapper, **arguments)
        self.platform.send_by_session.assert_awaited_once()
