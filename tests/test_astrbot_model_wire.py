from dataclasses import replace
import json
from types import SimpleNamespace as NS
import unittest

from companion_v2.adapters.astrbot.model_wire import build_wire, tool_alias
from companion_v2.execution.models import TaskError, encode
from companion_v2.model_gateway.failures import ModelFailure
from companion_v2.model_gateway.models import MAX_TOOL_CATALOG, Amount, ToolCall, ToolExchange, ToolSpec
from tests.native_adapter_support import NativeFixture, completion, final_text

REPORTED_USAGE = Amount(40, 90, input_tokens=30, cached_input_tokens=10, output_tokens=10)


class NativeModelTests(NativeFixture, unittest.IsolatedAsyncioTestCase):
    async def test_native_catalog_preserves_all_64_aliases_and_rejects_overflow_before_io(self):
        tools = tuple(ToolSpec(f"fixture.action.{index}", "local tool", '{"type":"object"}')
                      for index in range(MAX_TOOL_CATALOG))
        envelope = await self.envelope(tools=tools)
        wire = build_wire(envelope)
        self.assertEqual(len(wire.tools), MAX_TOOL_CATALOG)
        self.assertEqual(set(wire.aliases.values()), {tool.action for tool in tools})
        async def respond(payload, offered):
            self.assertEqual(len(offered.tools), MAX_TOOL_CATALOG)
            self.assertTrue(all(tool.handler is None for tool in offered.tools))
            return completion(tools=[NS(id="last", type="function",
                function=NS(name=tool_alias(tools[-1].action), arguments='{}'))])
        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.tool_calls, (ToolCall("last", tools[-1].action, '{}'),))
        overflow = replace(envelope, tools=(*tools, ToolSpec("fixture.overflow", "local", '{}')))
        with self.assertRaises(ValueError):
            build_wire(overflow)
        self.assertEqual((await self.native_model.generate(overflow)).status, "not_started")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_journal_wire_keeps_persona_and_uses_structured_writing_without_reply_claims(self):
        envelope = await self.envelope()
        for output_format in ("journal", "journal_derivatives", "journal_selection"):
            request = replace(envelope.original, output_format=output_format,
                              instruction="按私人书写格式输出 JSON。")
            selected = replace(envelope, original=request)
            payload = {"body": "只剩一点轻松。", "afterglow": "", "recall": "fragments", "form": "片段"}
            if output_format == "journal_selection":
                payload = {"material_ids": ["material-1"]}
            async def respond(*_):
                return completion(encode(payload))
            self.native.provider.client.state.behavior = respond
            response = await self.native_model.generate(selected)
            self.assertEqual(response.status, "generated")
            self.assertEqual(json.loads(response.draft.text), payload)
            self.assertEqual(response.draft.claims, ())
            self.assertEqual(response.usage, REPORTED_USAGE)
            wire = build_wire(selected)
            self.assertEqual(wire.messages[0]["content"], envelope.original.role_instruction)
            self.assertNotIn('"claims"', wire.messages[1]["content"])
            self.assertNotIn("本轮能力与会话背景", wire.messages[1]["content"])
            self.assertEqual(wire.tools, ())
        with self.assertRaises(ValueError):
            build_wire(replace(selected, tools=(ToolSpec("memo.create", "写入", "{}"),)))

    async def test_model_perception_tracks_offered_tools_without_claiming_screen_access(self):
        envelope = await self.envelope()
        first = build_wire(replace(envelope, provider_capabilities=("text", "tools", "image")))
        self.assertEqual(first.messages[0]["content"], envelope.original.role_instruction)
        self.assertIn("当前是私聊", first.messages[1]["content"])
        self.assertIn("本轮会话的平台标识：", first.messages[1]["content"])
        self.assertIn("本轮接入配置允许提交：文本、图片输入、结构化工具调用", first.messages[1]["content"])
        self.assertIn("遵循原人格与世界观自然表达", first.messages[1]["content"])
        self.assertIn("不等于底层模型已验证理解", first.messages[1]["content"])
        self.assertIn("本轮没有可调用工具", first.messages[1]["content"])
        self.assertIn("不能查看当前屏幕", first.messages[1]["content"])
        self.assertNotIn("native-model", first.messages[1]["content"])
        offered = replace(envelope, provider_capabilities=("text", "tools"), tools=(
            ToolSpec("screen.capture", "截屏", '{"type":"object"}'),
            ToolSpec("image.generate", "生图", '{"type":"object"}')))
        second = build_wire(offered)
        self.assertIn("需先调用 screen.capture", second.messages[1]["content"])
        self.assertIn("生成图片需调用 image.generate", second.messages[1]["content"])
        self.assertNotIn("编辑图片需调用 image.edit", second.messages[1]["content"])
        self.assertNotIn("本轮未提供识屏工具", second.messages[1]["content"])
        edited = build_wire(replace(envelope, tools=(ToolSpec("image.edit", "修图", '{}'),)))
        self.assertIn("编辑图片需调用 image.edit", edited.messages[1]["content"])
        self.assertNotIn("生成图片需调用 image.generate", edited.messages[1]["content"])

    async def test_model_perception_follows_the_dispatched_override(self):
        envelope = await self.envelope(model_override="fallback-model")
        wire = build_wire(envelope, model_name="fallback-model")
        self.assertIn("目标对话模型标识：fallback-model", wire.messages[1]["content"])
        self.assertIn("不代表底层实际型号或能力已验证", wire.messages[1]["content"])
        self.assertNotIn("fixture", wire.messages[1]["content"])
        async def respond(*_):
            return completion()
        self.native.provider.client.state.behavior = respond
        self.assertEqual((await self.native_model.generate(envelope)).status, "generated")
        payload, _ = self.native.provider.client.state.calls[0]
        self.assertEqual(payload["model"], "fallback-model")
        self.assertIn("目标对话模型标识：fallback-model", payload["messages"][1]["content"])
        self.assertNotIn("目标对话模型标识：fixture", payload["messages"][1]["content"])

    async def test_model_label_is_bounded_to_one_line(self):
        envelope = await self.envelope()
        wire = build_wire(envelope, model_name="model-a\n" + "x" * 100)
        self.assertIn("目标对话模型标识：model-a " + "x" * 72 + "；", wire.messages[1]["content"])
        self.assertNotIn("model-a\nx", wire.messages[1]["content"])

    async def test_native_provider_capabilities_follow_explicit_host_modalities(self):
        full = ("text", "tools", "image", "audio")
        self.assertEqual(self.native_model.local_provider().capabilities, full)
        self.native.provider.provider_config["modalities"] = []
        self.assertEqual(self.make_model().local_provider().capabilities, full)
        self.native.provider.provider_config["modalities"] = ["text", "image", "tool_use", "text"]
        self.assertEqual(self.make_model().local_provider().capabilities, ("text", "tools", "image"))
        self.native.provider.provider_config["modalities"] = ["text", "audio"]
        self.assertEqual(self.make_model().local_provider().capabilities, ("text", "audio"))

    async def test_local_provider_carries_the_model_name_for_the_management_face(self):
        """管理面靠这个字段区分同类型的两个 Provider；丢了它就只能靠 id 猜。

        取值必须来自宿主的 get_model()，而不是 provider_config 里的原始配置——
        两者可以不一致（换过模型但配置没同步），而实际发出去的请求用的是前者。
        """
        self.assertEqual(self.native_model.local_provider().model, self.native.provider.model_name)
        self.native.provider.model_name = "switched-after-load"
        self.assertEqual(self.make_model().local_provider().model, "switched-after-load")

    async def test_grounded_final_original_persona_output_limit_and_rated_usage(self):
        envelope = await self.envelope()
        wire = build_wire(envelope)
        evidence = next(iter(wire.evidence))
        async def respond(payload, tools):
            return completion(final_text("你刚刚说了你好。", evidence=evidence))
        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "generated")
        self.assertEqual(response.usage, REPORTED_USAGE)
        self.assertEqual(response.draft.claims[0].evidence, envelope.original.event.source)
        self.assertTrue(response.receipt_ref.endswith(":response-1"))
        payload, _ = self.native.provider.client.state.calls[0]
        self.assertEqual(payload["max_tokens"], 100)
        self.assertEqual(payload["messages"][0]["content"], envelope.original.role_instruction)
        self.assertNotIn("materials", payload["messages"][0]["content"])
        self.assertGreater(self.native_model.reserve(envelope).tokens, 100)
        self.assertEqual(self.native.provider.client.max_retries, 2)

    async def test_provider_cache_creation_receipt_is_preserved(self):
        envelope = await self.envelope()

        async def respond(*_):
            raw = completion()
            raw.usage.cache_creation_input_tokens = 4
            return raw

        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)

        self.assertEqual(response.usage, Amount(40, 90, input_tokens=30, cached_input_tokens=10,
                                                cache_creation_tokens=4, output_tokens=10))

    async def test_tools_are_aliases_only_and_execution_remains_in_v2(self):
        tool = ToolSpec("memo.list", "查看便签", '{"type":"object"}')
        envelope = await self.envelope(tools=(tool,))
        async def respond(payload, tools):
            self.assertIsNone(tools.tools[0].handler)
            return completion(tools=[NS(id="tool-1", type="function",
                function=NS(name=tool_alias("memo.list"), arguments='{"limit":2}'))])
        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.tool_calls, (ToolCall("tool-1", "memo.list", '{"limit":2}'),))
        exchange = ToolExchange(response.tool_calls[0], '{"state":"succeeded","items":[]}')
        history = build_wire(replace(envelope, tools=(), tool_history=(exchange,))).messages
        self.assertEqual(history[-2]["tool_calls"][0]["function"]["name"], tool_alias("memo.list"))
        self.assertEqual(history[-1]["tool_call_id"], "tool-1")

    async def test_missing_usage_never_becomes_zero_and_no_retry_on_timeout(self):
        envelope = await self.envelope()
        async def no_usage(*_): return completion(usage=False)
        self.native.provider.client.state.behavior = no_usage
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "generated")
        self.assertIsNone(response.usage)
        async def timeout(*_): raise TimeoutError("private endpoint information")
        self.native.provider.client.state.behavior = timeout
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.failure, ModelFailure.TRANSPORT)
        self.assertIsNone(response.usage)
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        self.assertNotIn("private", repr(response))

    async def test_malformed_final_preserves_usage_without_sending_or_retry(self):
        envelope = await self.envelope()
        variants = ["普通文字", '{"text":"你好","claims":[]}', final_text("你在医院。", evidence="invented"),
                    '{"text":"a","text":"b","claims":[]}']
        for text in variants:
            with self.subTest(text=text):
                async def respond(*_): return completion(text)
                self.native.provider.client.state.behavior = respond
                response = await self.native_model.generate(envelope)
                self.assertEqual(response.status, "unknown")
                self.assertEqual(response.failure, ModelFailure.WIRE_DECODE)
                self.assertEqual(response.usage, REPORTED_USAGE)
                self.assertIsNone(response.draft)
        self.assertEqual(len(self.native.provider.client.state.calls), len(variants))

    async def test_native_invalid_tool_json_is_not_repaired_into_an_operation(self):
        envelope = await self.envelope(tools=(ToolSpec("memo.list", "list", '{"type":"object"}'),))
        cases = [('{bad', tool_alias("memo.list"), "call-1"), ('[]', tool_alias("memo.list"), "call-1"),
                 ('{}', "undeclared", "call-1"), ('{}', tool_alias("memo.list"), ""),
                 ('{"limit":1,"limit":2}', tool_alias("memo.list"), "call-1")]
        for arguments, name, call_id in cases:
            with self.subTest(arguments=arguments, name=name, call_id=call_id):
                async def respond(*_):
                    return completion(tools=[NS(id=call_id, type="function", function=NS(name=name, arguments=arguments))])
                self.native.provider.client.state.behavior = respond
                response = await self.native_model.generate(envelope)
                self.assertEqual(response.status, "unknown")
                self.assertEqual(response.tool_calls, ())
                self.assertEqual(response.usage, REPORTED_USAGE)

    async def test_provider_replacement_config_change_and_missing_fence_do_not_dispatch(self):
        envelope = await self.envelope()
        self.native.provider.provider_config["custom_extra_body"]["temperature"] = 0.2
        self.assertEqual((await self.native_model.generate(envelope)).status, "not_started")
        self.native.provider.provider_config["custom_extra_body"]["temperature"] = 0.7
        self.assertEqual((await self.native_model.generate(replace(envelope, before_dispatch=None))).status, "not_started")
        def revoked(): raise TaskError("revoked", "owner cancelled during preparation")
        response = await self.native_model.generate(replace(envelope, before_dispatch=revoked))
        self.assertEqual(response.usage, Amount(0, 0))
        self.assertEqual(response.failure, ModelFailure.PREPARATION)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_host_persona_switch_during_generation_discards_tools_and_keeps_usage(self):
        envelope = await self.envelope()
        async def respond(*_):
            self.native.selected = "different"
            return completion()
        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.failure, ModelFailure.ROLE_RECHECK)
        self.assertEqual(response.usage, REPORTED_USAGE)
        self.assertIsNone(response.draft)

    async def test_provider_change_after_response_has_its_own_failure_classification(self):
        envelope = await self.envelope()

        async def respond(*_):
            self.native.provider.model_name = "changed-after-dispatch"
            return completion()

        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.failure, ModelFailure.PROVIDER_RECHECK)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.usage, REPORTED_USAGE)
        self.assertIsNone(response.draft)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_native_parse_failure_retains_usage_without_exception_text(self):
        envelope = await self.envelope()

        async def respond(*_):
            raw = completion("private unparsed response")
            raw.choices = []
            return raw

        self.native.provider.client.state.behavior = respond
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.failure, ModelFailure.NATIVE_PARSE)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.usage, REPORTED_USAGE)
        self.assertNotIn("private unparsed response", repr(response))
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_truncated_output_and_inconsistent_usage_are_not_successful_zeroes(self):
        envelope = await self.envelope()
        async def respond(*_): return completion(finish="length")
        self.native.provider.client.state.behavior = respond
        self.assertEqual((await self.native_model.generate(envelope)).status, "unknown")
        async def bad_usage(*_):
            raw = completion()
            raw.usage.total_tokens = 0
            return raw
        self.native.provider.client.state.behavior = bad_usage
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "generated")
        self.assertIsNone(response.usage)

    async def test_reserved_config_overrides_and_unbounded_prompt_are_rejected_before_io(self):
        for key in ("messages", "model", "tools", "max_tokens", "max_completion_tokens", "stream", "n"):
            self.native.provider.provider_config["custom_extra_body"] = {key: 1}
            with self.subTest(key=key), self.assertRaises(ValueError): self.make_model()
        self.native.provider.provider_config["custom_extra_body"] = {}
        provider = self.make_model(maximum_input_estimate=1024)
        envelope = await self.envelope()
        with self.assertRaises(TaskError): provider.reserve(envelope)
        self.assertEqual((await provider.generate(envelope)).status, "not_started")
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_assembled_tool_round_keeps_owner_and_final_reply(self):
        snapshot = await self.capture()
        async def respond(payload, tools):
            if not any(m["role"] == "tool" for m in payload["messages"]):
                return completion(tools=[NS(id="read-memos", type="function",
                    function=NS(name=tool_alias("memo.list"), arguments='{}'))])
            self.assertIn("succeeded", payload["messages"][-1]["content"])
            return completion()
        self.native.provider.client.state.behavior = respond
        host = await self.setup_host()
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
