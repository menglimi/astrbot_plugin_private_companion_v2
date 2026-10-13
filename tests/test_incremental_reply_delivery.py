"""Actual SDK streams and trusted delivery receipts before the final model frame."""

import asyncio
from dataclasses import replace
import json
import unittest

from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER
from companion_v2.conversation.reply_settings import configuration_fields, validate
from companion_v2.configuration.models import ConfigurationError
from companion_v2.adapters.astrbot.model_wire import build_wire, tool_alias
from companion_v2.adapters.astrbot.reply_stream import OrderedReplyStream
from tests import test_segmented_stream_delivery as segmented_support
from tests.segmentation_stream_support import StreamingFixture, chunk, text_chunks, USAGE


def ordered_text(text, *, action="text", claims=None):
    return json.dumps({"action": action, "claims": claims or [{"id": "c1", "kind": "subjective",
        "statement": text, "evidence": None}], "text": text}, ensure_ascii=False)


class IncrementalReplyWireTests(StreamingFixture, unittest.IsolatedAsyncioTestCase):
    async def test_escaped_json_strings_and_surrogates_can_span_every_character(self):
        text = '我在这里。\n第二段含 "引号"、\\ 和 👩‍💻。'
        envelope = await self.envelope()
        stream = OrderedReplyStream(build_wire(envelope))
        wire = json.dumps(json.loads(ordered_text(text)), ensure_ascii=True)
        drafts = [draft for char in wire if (draft := stream.feed(char)) is not None]
        self.assertEqual(drafts[-1].text, text)
        self.assertTrue(all(text.startswith(draft.text) for draft in drafts))
        self.assertNotIn('"action"', drafts[-1].text)

    async def test_duplicate_or_unknown_header_fields_are_rejected(self):
        envelope = await self.envelope()
        for raw in ('{"action":"text","action":"text",', '{"action":"text","unknown":1,'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                OrderedReplyStream(build_wire(envelope)).feed(raw)

    async def test_legacy_text_first_waits_for_complete_response(self):
        from tests.native_adapter_support import final_text
        envelope = await self.envelope()
        self.assertIsNone(OrderedReplyStream(build_wire(envelope)).feed(final_text("我在这里。慢慢说。")))

    def test_mode_defaults_and_previous_snapshots(self):
        values = {field.field_id.removeprefix("conversation.presentation."): field.default
                  for field in configuration_fields(SegmentationPolicy(), True, 0)}
        self.assertEqual(validate(values).streaming_mode, "buffered")
        self.assertEqual(validate({**values, "streaming_mode": "incremental"}).streaming_mode, "incremental")
        values.pop("streaming_mode")
        self.assertEqual(validate(values).streaming_mode, "buffered")
        with self.assertRaises(ConfigurationError):
            validate({**values, "streaming_mode": "invalid"})


class IncrementalReplyDeliveryTests(StreamingFixture, unittest.IsolatedAsyncioTestCase):
    start_stream_host = segmented_support.SegmentedStreamDeliveryTests.start_stream_host
    parts = segmented_support.SegmentedStreamDeliveryTests.parts
    texts = segmented_support.SegmentedStreamDeliveryTests.texts

    async def start_incremental(self, **changes):
        return await self.start_stream_host(segmentation=SegmentationPolicy(
            streaming_mode="incremental", **changes))

    async def test_first_segment_is_delivered_before_stream_end_and_tail_once(self):
        waiting, release = asyncio.Event(), asyncio.Event()
        text = "第一句话完成。第二句话慢慢说。"

        async def pause():
            waiting.set()
            await release.wait()

        async def respond(_):
            self.assertTrue(any("最后 text" in str(m["content"]) for m in _["messages"]))
            return [chunk(reasoning="内部思考"), *text_chunks(ordered_text(text), size=1)[:-2], pause,
                    chunk(finish="stop"), chunk(usage=USAGE)]

        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_incremental()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await asyncio.wait_for(waiting.wait(), 10)
        await self.until(lambda: self.parts(app, batch) and self.parts(app, batch)[0]["state"] == "delivered")
        self.assertEqual(self.texts(), ["第一句话完成。"])
        self.assertEqual(app.messages.batch(batch)["part_count"], 1)
        self.assertEqual(app.runtime.read_one("SELECT state FROM conversation_reply_streams WHERE batch_id = ?", (batch,))["state"], "open")
        release.set()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(self.texts(), ["第一句话完成。", "第二句话慢慢说。"])
        self.assertEqual([p["state"] for p in self.parts(app, batch)], ["delivered", "delivered"])
        self.assertEqual(len(self.client_state.calls), 1)
        self.assertEqual(host.receive(snapshot).unwrap(), batch)
        self.assertEqual(len(self.texts()), 2)

    async def _cleaned_mode(self, mode):
        from companion_v2.configuration.registry import FieldRegistry
        presentation = {"part_gap_mode": "fixed", "content_cleanup_enabled": True,
                        "content_cleanup_mode": mode, "content_cleanup_scope": "trailing",
                        "content_cleanup_words": json.dumps(["。", "，"]),
                        "content_cleanup_rule": r"[。，]+"}
        self.registry = FieldRegistry(version=self.registry.version, fields=(
            *self.registry.fields.values(), *(replace(field, default=presentation[field.field_id.rsplit(".", 1)[1]])
                if field.field_id.rsplit(".", 1)[1] in presentation else field
                for field in configuration_fields(SegmentationPolicy(
                    streaming_mode="incremental", rule_mode=mode, max_segments=2), True, 0))))
        text = "第一句好。第二句也好。第三句结束。"
        self.client_state.text = ordered_text(text)
        snapshot = await self.capture()
        host = await self.start_incremental(rule_mode=mode, max_segments=2)
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(self.texts(), ["第一句好", "第二句也好。第三句结束"])

    async def test_cross_chunk_words_clean_only_segment_tails(self):
        await self._cleaned_mode("words")

    async def test_cross_chunk_regex_clean_only_segment_tails(self):
        await self._cleaned_mode("regex")

    async def test_stream_interruption_keeps_confirmed_part_and_does_not_replay(self):
        text = "第一句话完成。第二句话还没完。"
        raw = ordered_text(text)
        sent = asyncio.Event()
        api = self.native.platform.client._api._wsr_api
        original = api.call_action

        async def action(*args, **kwargs):
            result = await original(*args, **kwargs)
            sent.set()
            return result

        api.call_action = action

        async def wait_sent():
            await asyncio.wait_for(sent.wait(), 10)
            await asyncio.sleep(0.05)

        async def respond(_):
            return [*text_chunks(raw, size=2)[:-2], wait_sent, TimeoutError("synthetic stream interrupted")]

        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_incremental()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        self.assertEqual((await self.done(app, batch))["state"], "blocked")
        self.assertEqual(self.texts(), ["第一句话完成。"])
        self.assertEqual(app.runtime.read_one("SELECT state FROM conversation_reply_streams WHERE batch_id = ?", (batch,))["state"], "interrupted")
        self.assertTrue(self.client_state.streams[0].closed)
        host.receive(snapshot).unwrap()
        self.advance(app, 10)
        await asyncio.sleep(0.02)
        self.assertEqual(self.texts(), ["第一句话完成。"])
        self.assertEqual(len(self.client_state.calls), 1)

    async def test_unknown_send_stops_generation_before_next_segment(self):
        self.client_state.text = ordered_text("第一句话完成。第二句话完成。第三句慢慢说。")
        self.native.platform.client._api._wsr_api.error = TimeoutError("synthetic acknowledgement loss")
        snapshot = await self.capture()
        host = await self.start_incremental()
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "blocked")
        self.assertEqual(self.texts(), ["第一句话完成。"])
        self.assertEqual(self.parts(host.application, batch)[0]["state"], "unknown")

    async def test_confirmed_pre_dispatch_failure_names_failed_part_and_withholds_tail(self):
        self.client_state.text = ordered_text("第一句话完成。第二句话也完成。")
        checks = 0

        def authorize():
            nonlocal checks
            checks += 1
            if checks == 2:
                self.native.selected = "changed"

        self.native_sender.authorize = authorize
        host = await self.start_stream_host(segmentation=SegmentationPolicy(
            streaming_mode="buffered", llm_controlled=False))
        app = host.application
        batch = host.receive(await self.capture()).unwrap()
        with self.assertLogs("companion_v2.diagnostics.inbound", level="WARNING") as captured:
            result = await self.done(app, batch)

        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["reason"], "message_delivery_failed")
        parts = self.parts(app, batch)
        self.assertEqual([part["state"] for part in parts], ["failed", "pending"])
        self.assertEqual(self.texts(), [])
        self.assertIn("part=%s:failed" % parts[0]["part_id"], captured.output[0])

    async def test_spacing_wait_keeps_receiving_stream_and_starts_after_previous_receipt(self):
        text = "第一句话完成。第二句话完成。第三句话完成。"
        received, release = asyncio.Event(), asyncio.Event()

        async def pause():
            received.set()
            await release.wait()

        async def respond(_):
            return [*text_chunks(ordered_text(text), size=2)[:-2], pause,
                    chunk(finish="stop"), chunk(usage=USAGE)]

        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_stream_host(gap=2, segmentation=SegmentationPolicy(streaming_mode="incremental"))
        app = host.application
        batch = host.receive(snapshot).unwrap()
        await asyncio.wait_for(received.wait(), 10)
        await self.until(lambda: self.parts(app, batch) and self.parts(app, batch)[0]["state"] == "delivered")
        self.assertEqual(self.texts(), ["第一句话完成。"])
        self.assertEqual(len(self.parts(app, batch)), 2)
        self.advance(app, 1)
        await asyncio.sleep(0.12)
        self.assertEqual(len(self.texts()), 1)
        self.advance(app, 1)
        await self.until(lambda: self.parts(app, batch)[1]["state"] == "delivered")
        release.set()
        await self.until(lambda: len(self.parts(app, batch)) == 3)
        self.advance(app, 2)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(self.texts(), ["第一句话完成。", "第二句话完成。", "第三句话完成。"])

    async def test_withdrawal_after_first_receipt_stops_tail_and_closes_stream(self):
        waiting = asyncio.Event()

        async def pause():
            waiting.set()
            await asyncio.Event().wait()

        async def respond(_):
            return [*text_chunks(ordered_text("第一句话完成。第二句话没完。"), size=1)[:-2], pause]

        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_incremental()
        app = host.application
        batch = host.receive(snapshot).unwrap()
        await asyncio.wait_for(waiting.wait(), 10)
        await self.until(lambda: self.parts(app, batch) and self.parts(app, batch)[0]["state"] == "delivered")
        event_key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))["event_key"]
        app.withdraw(self.context(app, batch), event_key).unwrap()
        await self.done(app, batch)
        await self.until(lambda: self.client_state.streams[0].closed)
        self.assertEqual(self.texts(), ["第一句话完成。"])

    async def test_invalid_observed_evidence_sends_only_the_local_failure_notice(self):
        from companion_v2.conversation.generation import MODEL_FAILURE_NOTICE

        text = "这是一条事实。后面也要校验。"
        self.client_state.text = ordered_text(text, claims=[{"id": "bad", "kind": "observed", "statement": text,
                                                          "evidence": "e_not_offered"}])
        snapshot = await self.capture()
        host = await self.start_incremental()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual("".join(self.texts()), MODEL_FAILURE_NOTICE)
        self.assertNotIn(text, "".join(self.texts()))
        self.assertTrue(all(part["state"] == "delivered" for part in self.parts(app, batch)))
        self.assertEqual(app.runtime.read_all("SELECT * FROM conversation_reply_streams WHERE batch_id = ?", (batch,)), ())
        self.assertIsNone(app.runtime.read_one("SELECT call_id FROM conversation_batches WHERE batch_id = ?", (batch,))["call_id"])

    async def test_code_and_decimal_dots_keep_their_literal_text(self):
        text = "版本是3.14。后面这一句话。\n\n```py\nprint('保持。代码。')\n```"
        self.client_state.text = ordered_text(text)
        snapshot = await self.capture()
        host = await self.start_incremental()
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(self.texts(), ["版本是3.14。", "后面这一句话。", "```py\nprint('保持。代码。')\n```"])

    async def test_model_markers_split_across_chunks_and_tools_wait_for_final_round(self):
        text = f"第一条回复\n{MARKER}\n第二条回复"
        count = 0

        async def respond(_):
            nonlocal count
            count += 1
            if count == 1:
                return [chunk(tools=[dict(index=0, id="read", type="function",
                    function=dict(name=tool_alias("memo.list"), arguments="{}"))]),
                    chunk(finish="tool_calls"), chunk(usage=USAGE)]
            return text_chunks(ordered_text(text), size=1)

        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_incremental(llm_controlled=True)
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(self.texts(), ["第一条回复", "第二条回复"])
        self.assertEqual(count, 2)
