"""Verify media guidance in the SDK's actual primary and fallback requests."""

from copy import deepcopy
from types import SimpleNamespace as NS
import unittest

from astrbot.core.agent.message import Message, TextPart
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import LLMResponse, ProviderRequest

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA, inject_core_reply_prompt
from astrbot_host.core_reply_media_prompt import core_media_request_diagnostics, finalize_core_reply_media_prompt
from companion_v2.conversation.voice_reply import VoiceReplyPolicy
from companion_v2.expression.reply_intent import INSTRUCTION as REACTION_INSTRUCTION
from astrbot_host.fish_audio import DRAMA_DIRECTION
from tests.test_core_reply_voice import FakeEvent


class MediaPromptTests(unittest.IsolatedAsyncioTestCase):
    def event(self, *, voice=True, reaction=True):
        event = FakeEvent()
        event.set_extra(CORE_REPLY_CONTEXT_EXTRA, {"prepared": {"event_ref": "private-reference",
            "voice_reply_policy": VoiceReplyPolicy(generation_mode="model_tag", language="ja",
                foreign_text_mode="translation") if voice else None}, "_reaction_reply": {"enabled": reaction}})
        return event

    async def test_later_request_hook_replacement_does_not_drop_selected_presentation(self):
        event = self.event()
        req = NS(system_prompt="所有对话均通过文字。", prompt="笨笨的")
        inject_core_reply_prompt(event, req)
        # Another plugin replaced the request after our early hook. The SDK
        # uses run_context.messages, not req.system_prompt, from this point on.
        req.system_prompt = "所有对话均通过文字。\n其他插件的参考资料。"
        history = {"role": "user", "content": "不要把这条历史当成呈现设置"}
        run = NS(messages=[Message(role="system", content=req.system_prompt), deepcopy(history)])
        finalize_core_reply_media_prompt(event, run)
        first = deepcopy(run.messages)
        finalize_core_reply_media_prompt(event, run)
        self.assertEqual(run.messages, first)
        self.assertEqual(run.messages[1], history)
        self.assertIn("其他插件的参考资料", run.messages[0].content)
        self.assertIn("<pc_tts>", run.messages[0].content)
        self.assertIn(REACTION_INSTRUCTION, run.messages[0].content)
        diagnostics = core_media_request_diagnostics(event, run)
        self.assertTrue(diagnostics["presentation_present"])
        self.assertTrue(diagnostics["voice_prompt_present"])
        self.assertNotIn("笨笨的", str(diagnostics))

    async def test_content_parts_are_preserved_and_repeated_hooks_do_not_grow_context(self):
        event = self.event()
        system = Message(role="system", content=[TextPart(text="角色身份"), TextPart(text="其他插件资料")])
        run = NS(messages=[system, Message(role="user", content="早安")])
        finalize_core_reply_media_prompt(event, run)
        first = deepcopy(run.messages)
        finalize_core_reply_media_prompt(event, run)
        self.assertEqual(run.messages, first)
        self.assertEqual(len(system.content), 3)

    async def test_drama_direction_survives_final_hook_without_growing_the_prompt(self):
        event = self.event()
        event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["prepared"]["voice_provider_instruction"] = DRAMA_DIRECTION
        req = NS(system_prompt="角色", prompt="晚安")
        inject_core_reply_prompt(event, req)
        run = NS(messages=[Message(role="system", content=req.system_prompt)])
        finalize_core_reply_media_prompt(event, run)
        finalize_core_reply_media_prompt(event, run)
        self.assertEqual(run.messages[0].content.count(DRAMA_DIRECTION), 1)
        self.assertTrue(core_media_request_diagnostics(event, run)["voice_prompt_present"])

    async def test_disabled_media_does_not_change_messages_or_enable_reactions(self):
        event = self.event(voice=False, reaction=False)
        run = NS(messages=[{"role": "system", "content": "原有角色"}])
        finalize_core_reply_media_prompt(event, run)
        self.assertEqual(run.messages, [{"role": "system", "content": "原有角色"}])
        self.assertIsNone(core_media_request_diagnostics(event, run))

    async def test_sdk_provider_fallback_and_tool_continuation_retain_media_contract(self):
        event = self.event()
        providers = [CapturingProvider("primary", failed=True), CapturingProvider("fallback")]
        runner = ToolLoopAgentRunner()
        req = ProviderRequest(prompt="笨笨的", system_prompt="旧人格仅文字", contexts=[])
        run = NS(context=NS(event=event), messages=[])
        await runner.reset(provider=providers[0], request=req, run_context=run,
                           tool_executor=None, agent_hooks=None, fallback_providers=providers[1:])
        finalize_core_reply_media_prompt(event, run)
        replies = [item async for item in runner._iter_llm_responses_with_fallback()]
        self.assertEqual(replies[-1].role, "assistant")
        run.messages.extend([Message(role="assistant", content="正在查询"),
                             Message(role="user", content="工具结果：已查到")])
        await anext(runner._iter_llm_responses())
        for provider in providers:
            for sent in provider.calls:
                system = sent[0].content
                self.assertEqual(system.count("<companion_reply_presentation>"), 1)
                self.assertIn("<pc_tts>", system)
                self.assertIn(REACTION_INSTRUCTION, system)


class CapturingProvider:
    def __init__(self, name, *, failed=False):
        self.provider_config = {"id": name}
        self.failed, self.calls = failed, []

    async def text_chat(self, **kwargs):
        self.calls.append(deepcopy(kwargs["contexts"]))
        return LLMResponse(role="err" if self.failed else "assistant", completion_text="provider response")
