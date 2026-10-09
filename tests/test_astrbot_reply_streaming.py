import asyncio
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER
from companion_v2.model_gateway.models import Amount, ToolSpec
from tests.native_adapter_support import final_text
from tests.segmentation_stream_support import StreamingFixture, chunk, text_chunks, USAGE


EXPECTED_USAGE = Amount(40, 90, input_tokens=30, cached_input_tokens=10, output_tokens=10)


class AstrBotReplyStreamingTests(StreamingFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_http_sse_decoder_handles_split_utf8_and_json_bytes(self):
        import httpx
        from openai import AsyncOpenAI
        text = f"中文 👩‍💻。\n{MARKER}\n第二段。"
        packets = text_chunks(final_text(text), size=3)
        body = ("".join("data: " + p.model_dump_json() + "\n\n" for p in packets)
                + "data: [DONE]\n\n").encode("utf-8")
        seen, streams = [], []
        width = 1

        class Bytes(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                for offset in range(0, len(body), width):
                    yield body[offset:offset + width]

            async def aclose(self):
                self.closed = True

        async def request(request):
            seen.append(json.loads(request.content))
            stream = Bytes()
            streams.append(stream)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

        http = httpx.AsyncClient(transport=httpx.MockTransport(request))
        client = AsyncOpenAI(api_key="synthetic-not-a-key", base_url="https://fixture.invalid/v1", http_client=http)
        self.addAsyncCleanup(client.close)
        self.native.provider.client = client
        model = self.real_model()
        envelope = await self.envelope()
        for width in (1, 11, 64):
            with self.subTest(network_packet_bytes=width):
                result = await model.generate(envelope)
                self.assertEqual(result.status, "generated", result.failure)
                self.assertEqual(result.draft.text, text)
                self.assertEqual(result.usage, EXPECTED_USAGE)
                self.assertEqual(SegmentationPolicy(enabled=True, llm_controlled=True).parts(result.draft.text), ("中文 👩‍💻。\n", "第二段。"))
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(p["stream"] and p["stream_options"]["include_usage"] for p in seen))
        self.assertTrue(all(s.closed for s in streams))

    async def test_arbitrary_chunk_boundaries_match_complete_output_without_duplication(self):
        text = f"我在这里 👩‍💻。\n{MARKER}\n慢慢说。\n\n```python\nprint('hello。')\n```"
        self.client_state.text = final_text(text)
        envelope = await self.envelope()
        whole = await self.real_model(streaming=False).generate(envelope)
        self.assertEqual(whole.status, "generated")
        for size in (1, 2, 7, 29, 10000):
            async def respond(_):
                return text_chunks(self.client_state.text, size=size)
            self.client_state.behavior = respond
            with self.subTest(size=size):
                streamed = await self.native_model.generate(envelope)
                self.assertEqual(streamed.status, "generated", streamed.failure)
                self.assertEqual(streamed.draft, whole.draft)
                self.assertEqual(streamed.usage, EXPECTED_USAGE)
                parts = SegmentationPolicy(enabled=True, llm_controlled=True).parts(streamed.draft.text)
                self.assertEqual(tuple(p.strip() for p in parts), ("我在这里 👩‍💻。", "慢慢说。\n\n```python\nprint('hello。')\n```"))
        self.assertEqual(len(self.client_state.calls), 6)
        self.assertTrue(all(s.closed for s in self.client_state.streams))
        self.assertTrue(all(c["stream_options"] == {"include_usage": True} for c in self.client_state.calls[1:]))
        self.assertEqual(self.native.provider.client.max_retries, 2)

    async def test_incremental_tool_arguments_are_executed_only_after_full_round(self):
        alias = tool_alias("memo.list")
        async def respond(_):
            return [chunk(reasoning="内部推理，不应发送。"),
                chunk(tools=[dict(index=0, id="read-1", type="function", function=dict(name=alias, arguments=""))]),
                *[chunk(tools=[dict(index=0, function=dict(arguments=char))]) for char in '{"limit":2}'],
                chunk(finish="tool_calls"), chunk(usage=USAGE)]
        self.client_state.behavior = respond
        result = await self.native_model.generate(await self.envelope(tools=(ToolSpec("memo.list", "查看便签", '{"type":"object"}'),)))
        self.assertEqual(result.status, "generated", result.failure)
        self.assertIsNone(result.draft)
        self.assertEqual(json.loads(result.tool_calls[0].arguments_json), {"limit": 2})
        self.assertEqual(result.tool_calls[0].action, "memo.list")
        self.assertEqual(result.usage, EXPECTED_USAGE)

    async def test_partial_empty_truncated_refused_malformed_and_mixed_streams_never_publish(self):
        valid = final_text(f"甲\n{MARKER}\n乙")
        variants = {
            "empty": [],
            "no_finish_even_with_complete_json": text_chunks(valid, finish=None),
            "length": text_chunks(valid, finish="length"),
            "filter": text_chunks(valid, finish="content_filter"),
            "malformed_json": text_chunks(valid[:-2]),
            "midstream_error": [chunk(valid[:12]), TimeoutError("synthetic private endpoint")],
            "changed_id": [chunk(valid[:5]), chunk(valid[5:], identifier="stream-2"), chunk(finish="stop")],
            "late_text": text_chunks(valid) + [chunk("late")],
            "duplicate_final_text": text_chunks(valid) + [chunk(valid)],
            "refusal": [chunk(refusal="拒绝"), *text_chunks(valid)],
        }
        envelope = await self.envelope()
        for name, items in variants.items():
            async def respond(_):
                return items
            self.client_state.behavior = respond
            with self.subTest(name=name):
                result = await self.native_model.generate(envelope)
                if name in ("filter", "refusal"):
                    self.assertEqual(result.status, "generated", result)
                    self.assertEqual(result.captured_output.finish_reason, "refusal")
                else:
                    self.assertEqual(result.status, "unknown", result)
                self.assertIsNone(result.draft)
                self.assertEqual(result.tool_calls, ())
                self.assertNotIn("synthetic private", repr(result))
                self.assertTrue(self.client_state.streams[-1].closed)
        self.assertEqual(len(self.client_state.calls), len(variants))

    async def test_missing_usage_is_unknown_and_truncation_keeps_actual_usage(self):
        async def respond(_):
            return text_chunks(final_text(), usage=False)
        self.client_state.behavior = respond
        result = await self.native_model.generate(await self.envelope())
        self.assertEqual(result.status, "generated")
        self.assertIsNone(result.usage)
        async def truncated(_):
            return text_chunks(final_text(), finish="length")
        self.client_state.behavior = truncated
        result = await self.native_model.generate(await self.envelope())
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.usage, EXPECTED_USAGE)

    async def test_cancellation_closes_socket_and_never_falls_back(self):
        entered = asyncio.Event()
        async def pause():
            entered.set()
            await asyncio.Event().wait()
        async def respond(_):
            return [chunk('{"text":"partial'), pause]
        self.client_state.behavior = respond
        pending = asyncio.create_task(self.native_model.generate(await self.envelope()))
        await asyncio.wait_for(entered.wait(), 2)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertTrue(self.client_state.streams[0].closed)
        self.assertEqual(len(self.client_state.calls), 1)

    async def test_persona_or_provider_changes_after_stream_discard_complete_reply(self):
        for field in ("persona", "provider"):
            async def change():
                if field == "persona":
                    self.native.selected = "other"
                else:
                    self.native.provider.model_name = "other"
            async def respond(_):
                return [*text_chunks(final_text()), change]
            self.client_state.behavior = respond
            with self.subTest(field=field):
                result = await self.native_model.generate(await self.envelope())
                self.assertEqual(result.status, "unknown")
                self.assertEqual(result.usage, EXPECTED_USAGE)
                self.assertIsNone(result.draft)
            self.native.selected = "original"
            self.native.provider.model_name = "fixture"

    async def test_background_structured_writing_retains_original_transport(self):
        self.client_state.text = '{"body":"私人日记"}'
        envelope = await self.envelope()
        result = await self.native_model.generate(replace(envelope, original=replace(envelope.original, output_format="journal")))
        self.assertEqual(result.status, "generated", result.failure)
        self.assertFalse(self.client_state.calls[0]["stream"])

    async def test_swallowed_native_accumulator_error_cannot_silently_change_valid_json(self):
        from astrbot.core.provider.sources.openai_source import ChatCompletionStreamState
        handle = ChatCompletionStreamState.handle_chunk
        def discard_character(state, item):
            if item.choices and item.choices[0].delta.content == "甲":
                raise ValueError("synthetic accumulator failure")
            return handle(state, item)
        self.client_state.text = final_text("甲乙")
        with patch.object(ChatCompletionStreamState, "handle_chunk", discard_character):
            result = await self.native_model.generate(await self.envelope())
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.draft)
        self.assertEqual(result.usage, EXPECTED_USAGE)
        self.assertEqual(len(self.client_state.calls), 1)

    async def test_malformed_streamed_tool_arguments_are_not_repaired_into_commands(self):
        alias = tool_alias("memo.list")
        async def respond(_):
            return [chunk(tools=[dict(index=0, id="read", type="function",
                function=dict(name=alias, arguments='{"limit":'))]),
                chunk(finish="tool_calls"), chunk(usage=USAGE)]
        self.client_state.behavior = respond
        result = await self.native_model.generate(await self.envelope(tools=(ToolSpec("memo.list", "list", '{"type":"object"}'),)))
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.tool_calls, ())
        self.assertEqual(result.usage, EXPECTED_USAGE)

    async def test_choice_usage_and_inconsistent_usage_do_not_turn_into_zero(self):
        async def respond(_):
            pieces = text_chunks(final_text(), usage=False)
            pieces[-1].choices[0].usage = USAGE
            return pieces
        self.client_state.behavior = respond
        result = await self.native_model.generate(await self.envelope())
        self.assertEqual(result.status, "generated", result.failure)
        self.assertEqual(result.usage, EXPECTED_USAGE)
        async def bad_usage(_):
            pieces = text_chunks(final_text(), usage=False)
            pieces.append(chunk(usage={**USAGE, "total_tokens": 0}))
            return pieces
        self.client_state.behavior = bad_usage
        result = await self.native_model.generate(await self.envelope())
        self.assertEqual(result.status, "generated")
        self.assertIsNone(result.usage)
