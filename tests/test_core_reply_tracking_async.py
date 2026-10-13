"""Group bookkeeping never makes native replies await storage."""

import asyncio
from datetime import timedelta
from threading import Event, get_ident
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
from astrbot_host.core_reply_tracking import (
    finish_core_reply_tracking, mark_core_reply_inflight, prepare_core_reply_tracking,
)
from tests.group_host_support import GroupFixture


class CoreReplyTrackingAsyncTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()
        self.admission = self.app.tools.group_participation.admission
        self.observer = self.controller.session.core_reply_observations

    async def prepared_event(self, identifier):
        event = self.group_event(identifier=identifier, text="如何处理这个问题？")
        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        await prepared["native_source_future"]
        event.set_extra(CORE_REPLY_CONTEXT_EXTRA, {"delivery_guard_active": True})
        event.get_result = lambda: NS(result_content_type=NS(name="LLM_RESULT"))
        return event, prepared

    def attach(self, event, prepared, *, submit):
        return prepare_core_reply_tracking(event, prepared, admission=self.admission, now=self.clock.now,
                                           reason="question", mentioned=False, submit=submit)

    async def test_blocked_record_does_not_delay_send_and_close_drains_recorded_order(self):
        event, prepared = await self.prepared_event("async-group-record")
        entered, release = Event(), Event()
        calls, loop_thread = [], get_ident()
        original_record = self.admission.record_core_reply
        original_mark = self.admission.mark_core_reply
        original_log = self.admission.mark_core_reply_logged

        def record(*args, **kwargs):
            calls.append(("record", get_ident(), kwargs["at"]))
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test release was not received")
            return original_record(*args, **kwargs)

        def mark(*args, **kwargs):
            calls.append((kwargs["stage"], get_ident(), kwargs["at"]))
            return original_mark(*args, **kwargs)

        def log(*args, **kwargs):
            calls.append(("log:" + args[-1], get_ident(), None))
            return original_log(*args, **kwargs)

        with patch.object(self.admission, "record_core_reply", side_effect=record), \
                patch.object(self.admission, "mark_core_reply", side_effect=mark), \
                patch.object(self.admission, "mark_core_reply_logged", side_effect=log):
            try:
                self.attach(event, prepared, submit=self.observer.submit)
                self.assertTrue(await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), 3))
                mark_core_reply_inflight(event)
                self.clock.advance(timedelta(seconds=2))
                sent_at = self.clock.now()
                await asyncio.wait_for(event.send("正常原生回复"), 0.5)
                delivery = finish_core_reply_tracking(event)
                self.assertEqual(event.sent, ["正常原生回复"])
                self.assertEqual(delivery["send_returns"], 1)
                self.assertEqual([item[0] for item in calls], ["record"])
                closing = asyncio.create_task(self.observer.close())
                await asyncio.sleep(0)
                self.assertFalse(closing.done())
            finally:
                release.set()
            await asyncio.wait_for(closing, 3)

        self.assertEqual([item[0] for item in calls], [
            "record", "log:admitted", "inflight", "send_started", "send_returned", "completed", "log:completed"])
        self.assertTrue(all(item[1] != loop_thread for item in calls))
        self.assertTrue(all(item[2] == sent_at for item in calls if item[0] in ("send_started", "send_returned", "completed")))
        saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
        self.assertEqual(saved["state"], "completed")
        self.assertEqual((saved["send_attempts"], saved["send_returns"]), (1, 1))
        self.assertEqual(saved["logged_stages"], ["admitted", "completed"])
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())

    async def test_background_record_failures_do_not_stop_later_phases_or_native_send(self):
        event, prepared = await self.prepared_event("async-group-failure")
        calls = []

        def unavailable(*args, **kwargs):
            calls.append(kwargs.get("stage", "record"))
            raise OSError("optional bookkeeping is unavailable")

        with patch.object(self.admission, "record_core_reply", side_effect=unavailable), \
                patch.object(self.admission, "mark_core_reply", side_effect=unavailable):
            self.attach(event, prepared, submit=self.observer.submit)
            mark_core_reply_inflight(event)
            await event.send("继续原生回复")
            result = finish_core_reply_tracking(event)
            await self.observer.close()

        self.assertEqual(event.sent, ["继续原生回复"])
        self.assertEqual(result["send_state"], "returned")
        self.assertEqual(calls, ["record", "inflight", "send_started", "send_returned", "completed"])
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())

    async def test_submit_failure_never_falls_back_to_synchronous_storage(self):
        event, prepared = await self.prepared_event("async-group-submit-failure")

        def unavailable(work):
            raise RuntimeError("observer submission failed")

        with patch.object(self.admission, "record_core_reply") as record, \
                patch.object(self.admission, "mark_core_reply") as mark, \
                patch.object(self.admission, "mark_core_reply_logged") as logged:
            self.attach(event, prepared, submit=unavailable)
            mark_core_reply_inflight(event)
            await event.send("队列故障也能回复")
            finish_core_reply_tracking(event)
            record.assert_not_called()
            mark.assert_not_called()
            logged.assert_not_called()
        self.assertEqual(event.sent, ["队列故障也能回复"])

    async def test_no_submit_retains_synchronous_direct_call_compatibility(self):
        event, prepared = await self.prepared_event("sync-group-record")
        self.attach(event, prepared, submit=None)
        self.assertIsNotNone(self.admission.recorded_core_reply(prepared["context"], prepared["event_id"]))
        mark_core_reply_inflight(event)
        await event.send("直接调用兼容")
        finish_core_reply_tracking(event)
        saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
        self.assertEqual(saved["send_state"], "returned")
        self.assertEqual((saved["send_attempts"], saved["send_returns"]), (1, 1))

    async def test_empty_or_metadata_stream_does_not_become_a_send_receipt(self):
        for index, parts in enumerate(([], [NS(type="tool_call"), NS(type="agent_stats"), NS(type="break")],
                                       [NS(chain=[]), NS(chain=[NS(text="  ")])])):
            with self.subTest(index=index):
                event, prepared = await self.prepared_event("empty-stream-" + str(index))
                consumed = []

                async def native_stream(generator, **kwargs):
                    async for chunk in generator:
                        consumed.append(chunk)
                    # AstrBot's base streaming method sets this even for an empty stream.
                    event._has_send_oper = True

                async def chunks():
                    for chunk in parts:
                        yield chunk

                event.send_streaming = native_stream
                event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
                self.attach(event, prepared, submit=self.observer.submit)
                mark_core_reply_inflight(event)
                await event.send_streaming(chunks())
                await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
                saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
                self.assertEqual(saved["state"], "completed")
                self.assertEqual(saved["send_state"], "not_started")
                self.assertEqual((saved["send_attempts"], saved["send_returns"], saved["unknown_sends"]), (0, 0, 0))
                self.assertTrue(event._has_send_oper)
                self.assertEqual(consumed, parts)
                self.assertTrue(all(left is right for left, right in zip(consumed, parts)))

    async def test_stream_nested_sends_are_counted_without_an_outer_send(self):
        for fail_last in (False, True):
            with self.subTest(fail_last=fail_last):
                event, prepared = await self.prepared_event("nested-stream-" + str(fail_last))
                native_send = event.send

                async def send(message):
                    await native_send(message)
                    if fail_last and message == "第二段":
                        raise TimeoutError("native outcome is unknown")
                    return {"message_id": message + "-id"}

                async def native_stream(generator):
                    async for chunk in generator:
                        await event.send(chunk)

                async def chunks():
                    yield "第一段"
                    yield "第二段"

                event.send, event.send_streaming = send, native_stream
                event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
                self.attach(event, prepared, submit=self.observer.submit)
                mark_core_reply_inflight(event)
                if fail_last:
                    with self.assertRaises(TimeoutError):
                        await event.send_streaming(chunks())
                else:
                    await event.send_streaming(chunks())
                await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
                saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
                self.assertEqual(saved["send_attempts"], 2)
                self.assertEqual(saved["send_returns"], 1 if fail_last else 2)
                self.assertEqual(saved["unknown_sends"], 1 if fail_last else 0)
                self.assertEqual(saved["platform_ids"], ["第一段-id"] if fail_last else ["第一段-id", "第二段-id"])
                self.assertEqual(event.sent, ["第一段", "第二段"])

    async def test_native_media_stream_is_observed_but_pre_chunk_failure_is_not_a_send(self):
        event, prepared = await self.prepared_event("media-stream")
        media = NS(chain=[NS(type="Image")])
        consumed = []

        async def native_stream(generator):
            async for chunk in generator:
                consumed.append(chunk)

        async def chunks():
            yield media

        event.send_streaming = native_stream
        event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
        self.attach(event, prepared, submit=self.observer.submit)
        mark_core_reply_inflight(event)
        await event.send_streaming(chunks())
        await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
        saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
        self.assertEqual((saved["send_attempts"], saved["send_returns"]), (1, 1))
        self.assertIs(consumed[0], media)

        event, prepared = await self.prepared_event("pre-chunk-failure")
        failure = ValueError("provider failed before producing any reply")

        async def failed_chunks():
            raise failure
            yield  # pragma: no cover

        event.send_streaming = native_stream
        event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
        self.attach(event, prepared, submit=self.observer.submit)
        mark_core_reply_inflight(event)
        with self.assertRaises(ValueError) as raised:
            await event.send_streaming(failed_chunks())
        self.assertIs(raised.exception, failure)
        await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
        saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
        self.assertEqual(saved["send_state"], "not_started")
        self.assertEqual((saved["send_attempts"], saved["send_returns"], saved["unknown_sends"]), (0, 0, 0))

    async def test_managed_qq_stream_records_only_actual_segment_sends(self):
        from dataclasses import asdict
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot_host.core_reply import prepare_core_reply_event
        from astrbot_host.core_reply_segmentation import prepare_core_reply_segmentation
        from companion_v2.conversation.segmentation import SegmentationPolicy
        from companion_v2.conversation.segment_control import LLM_SEGMENT_MARKER
        from companion_v2.foundation.outcome import Outcome

        for index, body in enumerate((LLM_SEGMENT_MARKER, "第一条完整回复。第二条完整回复。")):
            event, prepared = await self.prepared_event("managed-qq-stream-" + str(index))

            async def native_stream(generator, **kwargs):
                self.fail("managed QQ text should use complete native sends")

            async def authorize(_):
                return Outcome.success(True)

            async def chunks():
                yield MessageChain(chain=[Plain(body)])

            event.send_streaming = native_stream
            event.get_platform_name = lambda: "aiocqhttp"
            event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
            prepared["segmentation_settings"] = {**asdict(SegmentationPolicy()), "part_gap_mode": "fixed", "part_gap_ms": 0}
            prepare_core_reply_event(event, prepared, authorize=authorize)
            self.attach(event, prepared, submit=self.observer.submit)
            mark_core_reply_inflight(event)
            prepare_core_reply_segmentation(event)
            await event.send_streaming(chunks())
            await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
            saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
            expected = 0 if index == 0 else 2
            self.assertEqual((saved["send_attempts"], saved["send_returns"], saved["unknown_sends"]), (expected, expected, 0))
            self.assertEqual(len(event.sent), expected)

    async def test_cleanup_removed_text_does_not_create_a_final_or_stream_send_receipt(self):
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot_host.core_reply import prepare_core_reply_event
        from companion_v2.foundation.outcome import Outcome

        for streaming in (False, True):
            event, prepared = await self.prepared_event("cleaned-empty-" + str(streaming))
            prepared["presentation_settings"] = {"content_cleanup_enabled": True,
                                                  "content_cleanup_words": '["删"]'}
            event.get_platform_name = lambda: "webchat"

            async def native_stream(generator):
                async for _ in generator:
                    self.fail("fully cleaned text must not reach the native stream")

            async def authorize(_):
                return Outcome.success(True)

            async def chunks():
                yield MessageChain(chain=[Plain("删")])

            event.send_streaming = native_stream
            event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT" if streaming else "LLM_RESULT"))
            prepare_core_reply_event(event, prepared, authorize=authorize)
            event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["delivery_guard_active"] = True
            self.attach(event, prepared, submit=self.observer.submit)
            mark_core_reply_inflight(event)
            if streaming:
                await event.send_streaming(chunks())
            else:
                await event.send("删")
                finish_core_reply_tracking(event)
            await asyncio.gather(*tuple(self.observer._pending), return_exceptions=True)
            saved = self.admission.recorded_core_reply(prepared["context"], prepared["event_id"])
            self.assertEqual((saved["send_attempts"], saved["send_returns"], saved["unknown_sends"]), (0, 0, 0))
            self.assertEqual(event.sent, [])
            self.assertTrue(event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["_text_presentation_removed"])


if __name__ == "__main__":
    unittest.main()
