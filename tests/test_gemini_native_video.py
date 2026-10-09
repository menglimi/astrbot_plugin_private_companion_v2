"""The native video adapter must send captured MP4 bytes as a Gemini video Part."""

import base64
from dataclasses import replace
import json
from types import SimpleNamespace as NS
import unittest

from tests.video_support import VideoFixture, video_bytes
from tests.native_adapter_support import final_text
from tests.test_model_gateway import ModelFixture
from companion_v2.adapters.astrbot.model_wire import build_wire, tool_alias
from companion_v2.adapters.astrbot.provider import UsageTariff
from companion_v2.adapters.astrbot.provider_catalog import TextProviderSettings
from companion_v2.model_gateway.models import ModelEnvelope, ToolExchange, ToolSpec
from astrbot_host.video.gemini_provider import GeminiNativeVideoProvider


class NativeVideoTransportTests(VideoFixture, unittest.IsolatedAsyncioTestCase):
    async def test_original_bytes_and_tool_continuation_use_native_video_parts(self):
        host = await self.quiet_host()
        batch = host.receive(await self.capture(self.video_event())).unwrap()
        request = self.request(host.application, batch)
        request = replace(request, native_video_input=True)
        tool = ToolSpec("memo.list", "Read memos", '{"type":"object","properties":{},"additionalProperties":false}')
        envelope = ModelEnvelope(request, "fixture", 128, "fixture", tools=(tool,),
                                 before_dispatch=lambda: None)
        wire = build_wire(envelope, model_name="gemini-2.5-flash")
        content = next(message["content"] for message in wire.messages if message["role"] == "user")
        payload = next(item["video_data"] for item in content if item["type"] == "video_data")
        self.assertEqual(payload["mime_type"], "video/mp4")
        self.assertEqual(base64.b64decode(payload["data"], validate=True), video_bytes())
        self.assertFalse(any(item["type"] == "image_url" for item in content))

        class FakeGemini:
            provider_config = {"id": "gemini-native", "model": "gemini-2.5-flash"}
            model_name = "gemini-2.5-flash"
            default_params = {}

            def __init__(self):
                self.client = NS(models=NS(generate_content=self.generate_content))
                self.sent = None
                self.calls = []

            def meta(self):
                return NS(id="gemini-native")

            def get_model(self):
                return self.model_name

            async def _prepare_query_config(self, payloads, tools, choice, instruction, modalities, temperature):
                return {"max_output_tokens": payloads["max_tokens"], "system_instruction": instruction}

            async def generate_content(self, **kwargs):
                self.sent = kwargs
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    candidate = NS(finish_reason=NS(name="STOP"), content=NS(parts=[NS(
                        text=None, thought=False, function_call=NS(name=tool_alias("memo.list"), args={}))]))
                    return NS(candidates=[candidate], response_id="response-tool",
                              usage_metadata=NS(prompt_token_count=50, candidates_token_count=20,
                                                cached_content_token_count=0))
                evidence = next(iter(wire.evidence))
                reply = json.dumps({"text": "视频中有连续变化的画面。", "claims": [{
                    "id": "video-claim", "kind": "observed",
                    "statement": "视频中有连续变化的画面。", "evidence": evidence,
                }]}, ensure_ascii=False)
                candidate = NS(finish_reason=NS(name="STOP"), content=NS(parts=[NS(text=reply, thought=False)]))
                return NS(candidates=[candidate], response_id="response-1",
                          usage_metadata=NS(prompt_token_count=50, candidates_token_count=20,
                                            cached_content_token_count=0))

        native = FakeGemini()
        context = NS(get_provider_by_id=lambda provider_id: native if provider_id == "gemini-native" else None)
        bridge = NS(verify_role=lambda *args: _ok())
        native_types = NS(video_provider_type=FakeGemini, version="4.28.1",
            function_tool=lambda **kwargs: NS(**kwargs),
            tool_set=lambda **kwargs: NS(**kwargs))
        settings = TextProviderSettings("gemini-native", UsageTariff(1, 1, 1),
            maximum_output_tokens=128, maximum_input_estimate=131072)
        adapter = GeminiNativeVideoProvider(context, bridge, native_types, native, settings=settings)
        result = await adapter.generate(envelope)
        self.assertEqual(result.status, "generated")
        self.assertEqual(len(result.tool_calls), 1)
        continuation = ModelEnvelope(request, "fixture", 128, "fixture", tools=(tool,),
            tool_history=(ToolExchange(result.tool_calls[0], '{"state":"succeeded"}'),),
            before_dispatch=lambda: None)
        result = await adapter.generate(continuation)
        self.assertEqual(result.status, "generated")
        self.assertEqual(result.draft.text, "视频中有连续变化的画面。")
        sent_part = native.calls[0]["contents"][0].parts[-1]
        self.assertEqual(sent_part.inline_data.mime_type, "video/mp4")
        self.assertEqual(sent_part.inline_data.data, video_bytes())
        continued = native.calls[1]["contents"]
        self.assertEqual(continued[1].role, "model")
        self.assertIsNotNone(continued[1].parts[0].function_call)
        self.assertEqual(continued[2].role, "user")
        self.assertEqual(continued[2].parts[0].function_response.response["name"], tool_alias("memo.list"))


class NativeGeminiConversationTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    async def test_text_only_replies_and_tool_continuations_use_the_native_provider(self):
        tool = ToolSpec("memo.list", "Read memos",
                        '{"type":"object","properties":{},"additionalProperties":false}')

        class FakeGemini:
            provider_config = {"id": "gemini-native", "model": "gemini-3.8-flash"}
            model_name = "gemini-3.8-flash"
            default_params = {}

            def __init__(self):
                self.calls = []
                self.client = NS(models=NS(generate_content=self.generate_content))

            def meta(self):
                return NS(id="gemini-native")

            def get_model(self):
                return self.model_name

            async def _prepare_query_config(self, payloads, tools, choice, instruction, modalities, temperature):
                return {"max_output_tokens": payloads["max_tokens"], "system_instruction": instruction}

            async def generate_content(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["contents"][0].parts[0].text == "Reply OK.":
                    return NS(candidates=[NS(content=NS(parts=[NS(text="OK")]))])
                if len(self.calls) > 1:
                    echoed = [part for content in kwargs["contents"] for part in content.parts
                              if part.function_call is not None]
                    if len(echoed) != 1 or echoed[0].thought_signature != b"sealed-native-signature":
                        raise ValueError("Gemini continuation lost its original signature")
                part = (NS(text=None, thought=False,
                           function_call=NS(name=tool_alias("memo.list"), args={}),
                           thought_signature=b"sealed-native-signature")
                        if len(self.calls) == 1 else
                        NS(text=final_text("继续聊吧。"), thought=False, function_call=None))
                return NS(candidates=[NS(finish_reason=NS(name="STOP"), content=NS(parts=[part]))],
                          response_id="response-" + str(len(self.calls)),
                          usage_metadata=NS(prompt_token_count=50, candidates_token_count=20,
                                            cached_content_token_count=0))

        native = FakeGemini()
        context = NS(get_provider_by_id=lambda provider_id:
                     native if provider_id == "gemini-native" else None)
        native_types = NS(video_provider_type=FakeGemini, version="4.27.2",
                          function_tool=lambda **kwargs: NS(**kwargs),
                          tool_set=lambda **kwargs: NS(**kwargs))
        adapter = GeminiNativeVideoProvider(context, NS(verify_role=lambda *args: _ok()),
            native_types, native, settings=TextProviderSettings("gemini-native", UsageTariff(1, 1, 1),
                maximum_output_tokens=128, maximum_input_estimate=131072))
        request = self.request()
        envelope = ModelEnvelope(request, "fixture", 128, "fixture", tools=(tool,),
                                 before_dispatch=lambda: None)

        first = await adapter.generate(envelope)
        self.assertEqual(first.status, "generated")
        self.assertEqual(first.tool_calls[0].action, "memo.list")
        self.assertTrue(all(part.inline_data is None
                            for part in native.calls[0]["contents"][0].parts))

        final = await adapter.generate(replace(envelope, tool_history=(
            ToolExchange(first.tool_calls[0], '{"state":"succeeded"}'),)))
        self.assertEqual(final.draft.text, "继续聊吧。")
        self.assertEqual(len(native.calls), 2)
        self.assertEqual(native.calls[1]["contents"][-1].role, "user")
        self.assertEqual(native.calls[1]["contents"][-1].parts[0].function_response.name,
                         tool_alias("memo.list"))
        self.assertEqual(native.calls[1]["contents"][1].parts[0].thought_signature,
                         b"sealed-native-signature")
        await adapter.probe()
        self.assertEqual(native.calls[-1]["contents"][0].parts[0].text, "Reply OK.")
        self.assertEqual(native.calls[-1]["config"]["max_output_tokens"], 64)


async def _ok():
    return True


if __name__ == "__main__":
    unittest.main()
