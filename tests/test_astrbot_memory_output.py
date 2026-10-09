from dataclasses import replace
import json
import unittest

from companion_v2.execution.models import encode
from companion_v2.memory.reflection_output import REFLECTION_SCHEMA
from companion_v2.model_gateway.models import Amount
from tests.native_adapter_support import NativeFixture, completion


class NativeMemoryOutputTests(NativeFixture, unittest.IsolatedAsyncioTestCase):
    async def request(self, mode="text"):
        envelope = await self.envelope()
        return replace(envelope, original=replace(envelope.original, output_format="memory_reflection",
            response_format=mode, response_schema_json=encode(REFLECTION_SCHEMA)))

    async def test_malformed_text_is_a_received_memory_return_with_settled_usage(self):
        async def malformed(*_):
            return completion('```json\n{"summary":')
        self.native.provider.client.state.behavior = malformed
        response = await self.native_model.generate(await self.request())
        self.assertEqual(response.status, "generated")
        self.assertIsNone(response.draft)
        self.assertEqual(response.captured_output.text, '```json\n{"summary":')
        self.assertEqual(response.captured_output.finish_reason, "stop")
        self.assertEqual(response.usage, Amount(40, 90, input_tokens=30, cached_input_tokens=10, output_tokens=10))
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_completion_reasons_are_kept_without_native_json_repair(self):
        for finish, text, expected in (("length", "{}", "length"), ("content_filter", "", "refusal"),
                                       ("stop", "", "stop"), ("stop", "x" * 70000, "oversized")):
            with self.subTest(finish=finish, expected=expected):
                async def reply(*_):
                    return completion(text, finish=finish)
                self.native.provider.client.state.behavior = reply
                response = await self.native_model.generate(await self.request())
                self.assertEqual(response.status, "generated")
                self.assertEqual(response.captured_output.finish_reason, expected)
                self.assertLessEqual(len(response.captured_output.text), 65536)

    async def test_explicit_structured_modes_are_passed_to_provider(self):
        for mode in ("text", "json_object", "json_schema"):
            await self.native_model.generate(await self.request(mode))
            payload, tools = self.native.provider.client.state.calls[-1]
            self.assertIsNone(tools)
            if mode == "text":
                self.assertNotIn("response_format", payload)
            else:
                self.assertEqual(payload["response_format"]["type"], mode)
                if mode == "json_schema":
                    schema = payload["response_format"]["json_schema"]
                    self.assertTrue(schema["strict"])
                    self.assertEqual(schema["schema"], json.loads(encode(REFLECTION_SCHEMA)))
        plain = await self.request()
        structured = await self.request("json_schema")
        self.assertGreater(self.native_model.reserve(structured).tokens, self.native_model.reserve(plain).tokens)

    async def test_unsolicited_tools_never_become_memory_operations(self):
        from types import SimpleNamespace as NS
        async def tools(*_):
            return completion(tools=[NS(id="unoffered", type="function", function=NS(name="delete", arguments="{}"))])
        self.native.provider.client.state.behavior = tools
        response = await self.native_model.generate(await self.request())
        self.assertEqual(response.captured_output.finish_reason, "invalid")
        self.assertEqual(response.tool_calls, ())


if __name__ == "__main__":
    unittest.main()
