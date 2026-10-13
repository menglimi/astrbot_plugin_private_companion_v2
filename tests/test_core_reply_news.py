"""Core SDK tool dispatch performs news lookup only on a model tool request."""

from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as _host_import
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.pipeline.process_stage.follow_up import _ACTIVE_AGENT_RUNNERS
from astrbot.core.provider.entities import LLMResponse, ProviderRequest

from astrbot_host.core_reply_tool_dispatch import observe_core_tool_dispatch_begin, restore_core_tool_dispatch
from astrbot_host.core_reply_tools import native_tool_name
from companion_v2.proactive.external_materials import parse_news_response
from tests.multi_host_support import MultiFixture
from tests.test_core_reply_owner_tools import NativeOwnerCalls


class CoreReplyNewsTests(NativeOwnerCalls, MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()

    async def run_news(self, *, unavailable=False):
        fetched = []

        async def fetch():
            fetched.append(True)
            if unavailable:
                raise TimeoutError("fixture feed unavailable")
            return parse_news_response({"items": [{"id": "sdk-news", "title": "新的模型发布了",
                "summary": "公开摘要", "source": "示例媒体", "url": "https://news.example/sdk",
                "published_at": (self.clock.now() - timedelta(minutes=5)).isoformat()}]})

        port = NS(fetch=fetch, source_label="示例资讯源", fingerprint="sdk-news-fixture")
        event = self.event(identifier="sdk-news", text="最近AI有什么有趣的新消息")
        with patch.object(self.app.contact_schedule.news_events, "_source", return_value=port):
            prepared, request = await self.bind(event)
            self.assertEqual(fetched, [])
            name = native_tool_name("conversation.news.lookup")
            self.assertIsNotNone(request.func_tool.get_tool(name))
            req = ProviderRequest(prompt=prepared["text"], system_prompt=request.system_prompt, func_tool=request.func_tool)
            rounds = []

            async def text_chat(**arguments):
                rounds.append(arguments)
                if len(rounds) == 1:
                    return LLMResponse(role="assistant", tools_call_name=[name],
                        tools_call_args=[{"query": prepared["text"]}], tools_call_ids=["sdk-news-call"])
                return LLMResponse(role="assistant", completion_text="暂时没查到可靠消息。" if unavailable else "这条消息挺有意思！")

            provider = NS(provider_config={"id": "fixture-model", "modalities": ["text"]},
                          get_model=lambda: "fixture-model", text_chat=text_chat)
            wrapper = NS(context=NS(event=event), messages=[], tool_call_timeout=5)

            class Hooks(BaseAgentRunHooks):
                async def on_agent_begin(self, run_context):
                    observe_core_tool_dispatch_begin(event, run_context)

                async def on_agent_done(self, run_context, response):
                    restore_core_tool_dispatch(event, run_context)

            runner = ToolLoopAgentRunner()
            await runner.reset(provider, req, wrapper, FunctionToolExecutor(), Hooks())
            _ACTIVE_AGENT_RUNNERS[event.unified_msg_origin] = runner
            self.addCleanup(_ACTIVE_AGENT_RUNNERS.pop, event.unified_msg_origin, None)
            for _ in range(2):
                _ = [value async for value in runner.step()]
            self.assertTrue(runner.done())
            self.assertTrue(runner.final_llm_resp.completion_text)
            result = json.loads(next(message.content for message in wrapper.messages if message.role == "tool"))
            self.assertEqual(fetched, [True])
            self.assertEqual(result["state"], "succeeded", result)
            if unavailable:
                self.assertEqual(result["payload"]["state"], "unavailable")
            else:
                self.assertEqual(result["payload"]["content"]["items"][0]["title"], "新的模型发布了")
                self.assertNotIn("_receipt", result["payload"]["content"])
                news = self.app.tools.semantic.news_context
                self.assertEqual(news.validate_native(prepared["context"], result), result)
            self.assert_no_reply_work()

    async def test_real_sdk_reads_news_without_optional_telemetry_or_a_reply_batch(self):
        await self.run_news()

    async def test_news_network_failure_returns_unavailable_and_core_finishes_the_reply(self):
        await self.run_news(unavailable=True)


if __name__ == "__main__":
    unittest.main()
