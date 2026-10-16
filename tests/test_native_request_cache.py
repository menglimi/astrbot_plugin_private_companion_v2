"""Native live facts reach the real SDK payload without churning its prefix."""

from copy import deepcopy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from tests import astrbot_data_root as _host_import_root
from astrbot.core.agent.message import Message, TextPart, dump_messages_with_checkpoints
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot_host.native_extensions.host_events import prepare_native_host_request
from astrbot_host.native_extensions.live.activity_methods import LiveActivityMethods
from astrbot_host.native_extensions.live.model_methods import LiveModelMethods
from tests.test_native_host_events import HostEvent, LocalGame, LocalLive, context_text, controller, game_room


class CapturingProvider:
    def __init__(self, name, *, failed=False):
        self.provider_config = {"id": name}
        self.calls, self.failed = [], failed

    async def text_chat(self, **kwargs):
        self.calls.append([message.model_dump() for message in kwargs["contexts"]])
        return LLMResponse(role="err" if self.failed else "assistant", completion_text="测试回复")


class NativeRequestCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_game_changes_preserve_prefix_and_only_current_facts_reach_provider(self):
        room, live = game_room(), LocalLive()
        host, active = controller(game=LocalGame([room]), live=live)
        history = [{"role": "user", "content": "之前的话"}, {"role": "assistant", "content": "之前的回复"}]
        other = TextPart(text="另一插件的本轮材料")
        req = ProviderRequest(prompt="先前是怎么回事", system_prompt="AstrBot 当前角色",
                              contexts=deepcopy(history), extra_user_content_parts=[other])
        event = HostEvent()
        prepare_native_host_request(host, event, req)
        first_system = req.system_prompt
        first_material = context_text(req)
        prepare_native_host_request(host, event, req)
        self.assertEqual(req.system_prompt, first_system)
        self.assertEqual(context_text(req), first_material)
        self.assertIs(req.extra_user_content_parts[0], other)
        self.assertEqual(req.contexts, history)

        primary, fallback = CapturingProvider("primary", failed=True), CapturingProvider("fallback")
        runner, run = ToolLoopAgentRunner(), NS(context=NS(event=event), messages=[])
        await runner.reset(provider=primary, request=req, run_context=run,
                           tool_executor=None, agent_hooks=None, fallback_providers=[fallback])
        await anext(runner._iter_llm_responses_with_fallback())
        for provider in (primary, fallback):
            sent = provider.calls[0]
            self.assertEqual(sent[0], {"role": "system", "content": first_system})
            self.assertEqual(sent[1:-1], history)
            self.assertIn("提问 3 次", str(sent[-1]))
            self.assertIn("今天的声音好可爱", str(sent[-1]))
            self.assertIn("另一插件的本轮材料", str(sent[-1]))
            self.assertNotIn("_no_save", str(sent))

        saved = dump_messages_with_checkpoints(run.messages[1:])
        self.assertNotIn("提问 3 次", str(saved))
        self.assertNotIn("今天的声音好可爱", str(saved))
        self.assertNotIn("companion_v2_native_", str(saved))
        self.assertIn(req.prompt, str(saved[-1]))
        self.assertIn("另一插件的本轮材料", str(saved[-1]))

        room.game.question_count = 4
        live.events = ["观众：这是最新的弹幕"]
        second = ProviderRequest(prompt="现在呢", system_prompt="AstrBot 当前角色", contexts=deepcopy(saved))
        prepare_native_host_request(host, HostEvent(), second)
        self.assertEqual(second.system_prompt, first_system)
        self.assertEqual(second.contexts, saved)
        second_run, second_runner = NS(context=NS(event=event), messages=[]), ToolLoopAgentRunner()
        await second_runner.reset(provider=fallback, request=second, run_context=second_run,
                                  tool_executor=None, agent_hooks=None)
        await anext(second_runner._iter_llm_responses())
        sent = fallback.calls[-1]
        self.assertEqual(sent[:-1], [{"role": "system", "content": first_system}, *saved])
        self.assertIn("提问 4 次", str(sent[-1]))
        self.assertIn("这是最新的弹幕", str(sent[-1]))
        self.assertNotIn("提问 3 次", str(sent))
        self.assertNotIn("今天的声音好可爱", str(sent))

        second_run.messages.extend([Message(role="assistant", content="正在查询"),
                                    Message(role="user", content="已授权工具的真实结果")])
        await anext(second_runner._iter_llm_responses())
        self.assertEqual(fallback.calls[-1][:-2], sent)

        live.events.clear()
        prepare_native_host_request(host, HostEvent(), second)
        self.assertEqual(second.system_prompt, first_system)
        self.assertNotIn("这是最新的弹幕", context_text(second))
        active.clear()
        prepare_native_host_request(host, HostEvent(), second)
        self.assertEqual(second.system_prompt, "AstrBot 当前角色")
        self.assertFalse(second.extra_user_content_parts)

    async def test_configured_controls_replace_owned_blocks_without_accumulation(self):
        runtime = LocalLive()
        runtime.config["soullink_enabled"] = True
        host, active = controller(live=runtime)
        req = ProviderRequest(system_prompt="角色人格\n\n其他插件的系统规则", prompt="摸摸")
        prepare_native_host_request(host, HostEvent(), req)
        original = req.system_prompt
        for _ in range(3):
            prepare_native_host_request(host, HostEvent(), req)
            self.assertEqual(req.system_prompt, original)
        self.assertEqual(req.system_prompt.count("## Soullink 实时表演"), 1)
        self.assertEqual(req.system_prompt.count("## Live2D 表情/动作控制"), 1)
        runtime.config["l2d_max_tags_per_reply"] = 2
        prepare_native_host_request(host, HostEvent(), req)
        self.assertIn("最多选择 2 个", req.system_prompt)
        self.assertNotIn("最多选择 1 个", req.system_prompt)
        self.assertEqual(req.system_prompt.count("## Live2D 表情/动作控制"), 1)
        runtime.config.update(soullink_enabled=False, autonomous_l2d_enabled=False)
        prepare_native_host_request(host, HostEvent(), req)
        self.assertEqual(req.system_prompt, "角色人格\n\n其他插件的系统规则")
        self.assertIn("今天的声音好可爱", context_text(req))
        active.clear()
        prepare_native_host_request(host, HostEvent(), req)
        self.assertFalse(req.extra_user_content_parts)

    async def test_vts_command_hint_is_temporary_and_does_not_change_system(self):
        req = ProviderRequest(system_prompt="角色人格", prompt="/vts_auth")
        owner = NS()
        LiveActivityMethods._inject_vts_command_fallback_instruction(owner, HostEvent(text="/vts_auth"), req)
        material = context_text(req)
        self.assertIn("只有实际操作回执才能证明成功", material)
        self.assertEqual(req.system_prompt, "角色人格")
        LiveActivityMethods._inject_vts_command_fallback_instruction(owner, HostEvent(text="/vts_auth"), req)
        self.assertEqual(context_text(req), material)
        messages = [Message.model_validate(await req.assemble_context())]
        self.assertNotIn("VTS 授权入口", str(dump_messages_with_checkpoints(messages)))
        LiveActivityMethods._inject_vts_command_fallback_instruction(owner, HostEvent(text="晚安"), req)
        self.assertFalse(req.extra_user_content_parts)

    async def test_legacy_live_entry_updates_temporary_facts_and_clears_on_disable(self):
        runtime = LocalLive()
        runtime._build_bili_live_auxiliary_context = AsyncMock(return_value="本批感谢礼物")
        req = ProviderRequest(system_prompt="角色人格", prompt="看看弹幕")
        await LiveModelMethods._inject_bili_live_context(runtime, HostEvent(), req)
        self.assertIn("今天的声音好可爱", context_text(req))
        self.assertIn("本批感谢礼物", context_text(req))
        self.assertEqual(req.system_prompt, "角色人格")
        runtime.events = ["观众：最新留言"]
        await LiveModelMethods._inject_bili_live_context(runtime, HostEvent(), req)
        self.assertIn("最新留言", context_text(req))
        self.assertNotIn("今天的声音好可爱", context_text(req))
        messages = [Message.model_validate(await req.assemble_context())]
        self.assertNotIn("B站直播间实时信息", str(dump_messages_with_checkpoints(messages)))
        runtime.config["bili_live_inject_enabled"] = False
        await LiveModelMethods._inject_bili_live_context(runtime, HostEvent(), req)
        self.assertFalse(req.extra_user_content_parts)
        self.assertEqual(req.system_prompt, "角色人格")


if __name__ == "__main__":
    unittest.main()
