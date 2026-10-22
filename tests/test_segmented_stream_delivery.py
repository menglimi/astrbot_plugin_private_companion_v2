import asyncio
import base64
import json
import unittest

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.generation import MODEL_FAILURE_NOTICE
from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.segmentation import SegmentationPolicy, LLM_SEGMENT_MARKER as MARKER
from companion_v2.conversation.voice_reply import VoiceReplyDelivery, VoiceReplyPolicy
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from tests.native_adapter_support import FakeEvent, final_text
from tests.segmentation_stream_support import StreamingFixture, chunk, text_chunks, USAGE


class SegmentedStreamDeliveryTests(StreamingFixture, unittest.IsolatedAsyncioTestCase):
    async def start_stream_host(self, *, gap=0, runtime=None, generation=0, voice_policy=None,
                                segmentation=None):
        self.native_sender.voice_delivery = VoiceReplyDelivery(runtime or self.runtime, self.clock.now)
        return await self.start(self.host(runtime=runtime, event_port=self.bridge.ports, identity_port=self.bridge.ports,
            role_port=self.bridge.ports, providers=(self.native_model.local_provider(),),
            sender=self.native_sender.local_sender(), budget=BudgetPolicy(*(Amount(10**8, 10**9) for _ in range(5))),
            policy=ConversationPolicy(0, 0, 180, gap), segmentation=segmentation or SegmentationPolicy(
                enabled=True, llm_controlled=True, rules_enabled=False),
            voice_policy=voice_policy), generation, generation)

    def parts(self, app, batch):
        return app.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch,))

    def diagnostics(self, app, batch):
        recent = ReplyManagement(app, self.context(app, batch)).status(self.core).unwrap()["recent"]
        parts = next(item["parts"] for item in recent if item["batch_id"] == batch)
        return [(part["state"], part["candidate_reason"], part["render_state"],
                 part["component_order"], part["text_hidden"]) for part in parts]

    def texts(self):
        return [params["message"][0]["data"]["text"] for _, params in self.native.platform.client._api._wsr_api.calls]

    async def test_full_tool_stream_then_segment_stream_delivers_once_in_order(self):
        waiting, release = asyncio.Event(), asyncio.Event()
        text = f"我在这里。\n{MARKER}\n慢慢说。\n{MARKER}\n不用着急。"
        async def pause():
            waiting.set()
            await release.wait()
        async def respond(payload):
            if not any(m["role"] == "tool" for m in payload["messages"]):
                return [chunk(tools=[dict(index=0, id="read", type="function",
                    function=dict(name=tool_alias("memo.list"), arguments="{"))]),
                    chunk(tools=[dict(index=0, function=dict(arguments="}"))]),
                    chunk(finish="tool_calls"), chunk(usage=USAGE)]
            tool_result = next(message for message in payload["messages"] if message["role"] == "tool")
            self.assertIn("succeeded", tool_result["content"])
            pieces = text_chunks(final_text(text))
            return pieces[:-2] + [pause] + pieces[-2:]
        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_stream_host()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await asyncio.wait_for(waiting.wait(), 3)
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.texts(), [])
        release.set()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        expected = ["我在这里。", "慢慢说。", "不用着急。"]
        self.assertEqual(self.texts(), expected)
        self.assertTrue(all(p["state"] == "delivered" for p in self.parts(app, batch)))
        self.assertEqual(self.diagnostics(app, batch),
                         [("delivered", "voice_disabled", "not_applicable", ["text"], 0)] * 3)
        history = app.messages.history(self.context(app, batch)).unwrap()["items"]
        self.assertEqual([h["text"] for h in history], expected)
        self.assertTrue(all(c["stream"] for c in self.client_state.calls))
        self.assertEqual(len(self.client_state.calls), 2)
        for call in self.client_state.calls:
            self.assertEqual(call["messages"][0]["content"], snapshot.instruction)
            self.assertIn(MARKER, call["messages"][1]["content"])
        self.assertEqual(host.receive(snapshot).unwrap(), batch)
        self.assertEqual(self.texts(), expected)

    async def test_gap_starts_after_previous_ack_and_unknown_ack_stops_tail(self):
        self.client_state.text = final_text(f"第一段\n{MARKER}\n第二段\n{MARKER}\n第三段")
        snapshot = await self.capture()
        host = await self.start_stream_host(gap=2)
        app = host.application
        api = self.native.platform.client._api._wsr_api
        original = api.call_action
        async def action(*args, **kwargs):
            result = await original(*args, **kwargs)
            if len(api.calls) == 2:
                raise TimeoutError("lost acknowledgement")
            return result
        api.call_action = action
        batch = host.receive(snapshot).unwrap()
        await self.until(lambda: len(self.parts(app, batch)) == 3 and self.parts(app, batch)[0]["state"] == "delivered")
        self.assertEqual(self.texts(), ["第一段"])
        self.advance(app, 1)
        await asyncio.sleep(0.02)
        self.assertEqual(len(api.calls), 1)
        self.advance(app, 1)
        self.assertEqual((await self.done(app, batch))["state"], "blocked")
        self.assertEqual([p["state"] for p in self.parts(app, batch)], ["delivered", "unknown", "pending"])
        self.assertEqual(self.diagnostics(app, batch), [
            ("delivered", "voice_disabled", "not_applicable", ["text"], 0),
            ("unknown", "voice_disabled", "not_applicable", ["text"], 0),
            ("pending", "voice_disabled", "not_applicable", [], 0)])
        self.assertEqual([h["text"] for h in app.messages.history(self.context(app, batch)).unwrap()["items"]], ["第一段"])
        host.receive(snapshot).unwrap()
        self.advance(app, 10)
        await asyncio.sleep(0.02)
        self.assertEqual(self.texts(), ["第一段", "第二段"])
        await app.close()
        restored = await self.start_stream_host(runtime=self.open_runtime(), generation=1)
        await asyncio.sleep(0.02)
        self.assertEqual(restored.application.flow.row(batch)["state"], "blocked")
        self.assertEqual(self.diagnostics(restored.application, batch), [
            ("delivered", "voice_disabled", "not_applicable", ["text"], 0),
            ("unknown", "voice_disabled", "not_applicable", ["text"], 0),
            ("pending", "voice_disabled", "not_applicable", [], 0)])
        self.assertEqual(len(self.client_state.calls), 1)
        self.assertEqual(self.texts(), ["第一段", "第二段"])

    async def test_withdrawal_while_streaming_cancels_and_discards_all_parts(self):
        entered = asyncio.Event()
        async def pause():
            entered.set()
            await asyncio.Event().wait()
        async def respond(_):
            return [chunk(final_text(f"甲\n{MARKER}\n乙")), pause]
        self.client_state.behavior = respond
        host = await self.start_stream_host()
        snapshot = await self.capture()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await asyncio.wait_for(entered.wait(), 3)
        event_key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))["event_key"]
        app.withdraw(self.context(app, batch), event_key).unwrap()
        await self.done(app, batch)
        await self.until(lambda: self.client_state.streams[0].closed)
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.texts(), [])
        self.assertEqual(len(self.client_state.calls), 1)
        calls = app.runtime.read_all("SELECT state, actual_tokens FROM model_calls", ())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["state"], "unknown")
        self.assertIsNone(calls[0]["actual_tokens"])

    async def test_truncated_complete_json_stream_never_becomes_sendable(self):
        async def respond(_):
            return text_chunks(final_text(f"甲\n{MARKER}\n乙"), finish=None)
        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_stream_host()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await self.done(app, batch)
        self.assertEqual("".join(part["text"] for part in self.parts(app, batch)), MODEL_FAILURE_NOTICE)
        self.assertEqual("".join(self.texts()), MODEL_FAILURE_NOTICE)
        self.assertTrue(all(part["state"] == "delivered" for part in self.parts(app, batch)))
        self.assertEqual(len(self.client_state.calls), 1)
        call = app.runtime.read_one("SELECT state, actual_tokens FROM model_calls", ())
        self.assertEqual((call["state"], call["actual_tokens"]), ("unknown", 40))

    async def test_reasoning_after_finish_boundary_never_becomes_sendable(self):
        async def respond(_):
            return [chunk('{"text":"甲"}'), chunk(finish="stop"),
                    chunk(reasoning="迟到的推理片段"), chunk(usage=USAGE)]
        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_stream_host()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await self.done(app, batch)
        self.assertEqual("".join(part["text"] for part in self.parts(app, batch)), MODEL_FAILURE_NOTICE)
        self.assertEqual("".join(self.texts()), MODEL_FAILURE_NOTICE)
        self.assertTrue(all(part["state"] == "delivered" for part in self.parts(app, batch)))
        self.assertEqual(len(self.client_state.calls), 1)
        call = app.runtime.read_one("SELECT state, actual_tokens FROM model_calls", ())
        self.assertEqual((call["state"], call["actual_tokens"]), ("unknown", None))

    async def test_streamed_natural_segments_keep_original_image_order_on_last_part(self):
        from astrbot.core.message.components import Image, Plain
        from astrbot_host.media import load_native_image
        from tests.image_delivery_support import offered_images
        from tests.test_conversation_images import image_bytes
        self.bridge.image_type, self.bridge.image_loader = Image, load_native_image
        event = FakeEvent(self.native)
        originals = (image_bytes("red"), image_bytes("blue"))
        event.message_obj.message = [Plain("附上两张原图"), *(Image.fromBytes(content) for content in originals)]
        snapshot = await self.capture(event)
        waiting, release = asyncio.Event(), asyncio.Event()
        async def pause():
            waiting.set()
            await release.wait()
        async def respond(payload):
            value = json.loads(final_text("先看看这张图。再补一句。"))
            value["images"] = offered_images(payload)
            self.assertEqual(len(value["images"]), 2)
            pieces = text_chunks(json.dumps(value, ensure_ascii=False), size=3)
            return pieces[:-2] + [pause] + pieces[-2:]
        self.client_state.behavior = respond
        host = await self.start_stream_host(segmentation=SegmentationPolicy(
            enabled=True, rules_enabled=True, threshold=500, min_segment_chars=1, max_segments=2))
        app = host.application
        batch = host.receive(snapshot).unwrap()
        await asyncio.wait_for(waiting.wait(), 3)
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        release.set()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        sends = self.native.platform.client._api._wsr_api.calls
        self.assertEqual([[p["type"] for p in params["message"]] for _, params in sends],
                         [["text"], ["text", "image", "image"]])
        self.assertEqual([params["message"][0]["data"]["text"] for _, params in sends],
                         ["先看看这张图。", "再补一句。"])
        self.assertEqual([p["data"]["file"] for p in sends[1][1]["message"][1:]],
                         ["base64://" + base64.b64encode(content).decode("ascii") for content in originals])
        self.assertEqual(len(self.client_state.calls), 1)
        self.assertTrue(self.client_state.calls[0]["stream"])
        history = app.messages.history(self.context(app, batch)).unwrap()["items"]
        self.assertEqual([len(h.get("images", ())) for h in history], [0, 2])
        self.assertEqual(self.diagnostics(app, batch), [
            ("delivered", "voice_disabled", "not_applicable", ["text"], 0),
            ("delivered", "voice_disabled", "not_applicable", ["text", "image", "image"], 0)])

    async def test_streamed_tool_reply_combines_segments_images_and_tts_in_one_ordered_plan(self):
        from astrbot.core.message.components import Image, Plain
        from astrbot_host.media import load_native_image
        from tests.image_delivery_support import offered_images
        from tests.test_conversation_images import image_bytes

        self.bridge.image_type, self.bridge.image_loader = Image, load_native_image
        event = FakeEvent(self.native)
        event.message_obj.message = [Plain("附上原图"), Image.fromBytes(image_bytes())]
        text = (f"<pc_tts>第一段。</pc_tts>第一段正文。\n{MARKER}\n"
                "<pc_tts>第二段。</pc_tts>第二段正文。")
        async def respond(payload):
            if not any(message["role"] == "tool" for message in payload["messages"]):
                return [chunk(tools=[dict(index=0, id="read", type="function",
                    function=dict(name=tool_alias("memo.list"), arguments="{}"))]),
                    chunk(finish="tool_calls"), chunk(usage=USAGE)]
            value = json.loads(final_text(text))
            value["images"] = offered_images(payload)
            return text_chunks(json.dumps(value, ensure_ascii=False))

        spoken = []
        async def render(_, speech, *, provider_id, timeout_seconds):
            spoken.append((speech, provider_id, timeout_seconds))
            return {"type": "record", "data": {"file": "base64://YQ=="}}

        self.client_state.behavior = respond
        self.native_sender.voice = render
        self.native_sender.voice_delivery = VoiceReplyDelivery(self.runtime, self.clock.now)
        policy = VoiceReplyPolicy(trigger_mode="always", generation_mode="model_tag", segment_mode="each",
                                  delivery_mode="voice_and_text", position="after_media")
        snapshot = await self.capture(event)
        host = await self.start_stream_host(voice_policy=policy)
        batch = host.receive(snapshot).unwrap()
        app = host.application
        self.assertEqual((await self.done(app, batch))["state"], "complete")

        sends = self.native.platform.client._api._wsr_api.calls
        self.assertEqual([[part["type"] for part in params["message"]] for _, params in sends],
                         [["text"], ["record"], ["text", "image"], ["record"]])
        self.assertEqual([part["text"] for part in self.parts(app, batch)],
                         ["第一段。第一段正文。", "第二段。第二段正文。"])
        self.assertEqual(spoken, [("第一段。", "", 30), ("第二段。", "", 30)])
        self.assertEqual(len(self.client_state.calls), 2)
        self.assertTrue(all(call["stream"] for call in self.client_state.calls))
        voice_parts = app.runtime.read_all("SELECT sequence, speech FROM conversation_voice_parts v "
                                           "JOIN conversation_parts p ON p.part_id = v.part_id "
                                           "WHERE p.batch_id = ? ORDER BY sequence", (batch,))
        self.assertEqual([(row["sequence"], row["speech"]) for row in voice_parts],
                         [(1, "第一段。"), (2, "第二段。")])
        self.assertEqual(self.diagnostics(app, batch), [
            ("delivered", "planned", "ready", ["text", "voice"], 0),
            ("delivered", "planned", "ready", ["text", "image", "voice"], 0)])

    async def test_leading_images_keep_sealed_order_across_stream_config_change_tts_failure_and_restart(self):
        from astrbot.core.message.components import Image, Plain
        from astrbot_host.media import load_native_image
        from tests.image_delivery_support import offered_images
        from tests.test_conversation_images import image_bytes

        self.bridge.image_type, self.bridge.image_loader = Image, load_native_image
        originals = (image_bytes("red"), image_bytes("blue"))
        event = FakeEvent(self.native)
        event.message_obj.message = [Plain("把原图和回复放在一起"), *(Image.fromBytes(b) for b in originals)]
        waiting, release = asyncio.Event(), asyncio.Event()
        text = (f"<pc_tts>第一段。</pc_tts>\n{MARKER}\n"
                f"<pc_tts>第二段。</pc_tts>\n{MARKER}\n"
                "<pc_tts>第三段。</pc_tts>附上原图。")

        async def pause():
            waiting.set()
            await release.wait()

        async def respond(payload):
            if not any(message["role"] == "tool" for message in payload["messages"]):
                return [chunk(tools=[dict(index=0, id="read", type="function",
                    function=dict(name=tool_alias("memo.list"), arguments="{}"))]),
                    chunk(finish="tool_calls"), chunk(usage=USAGE)]
            value = json.loads(final_text(text))
            value["images"] = list(reversed(offered_images(payload)))
            pieces = text_chunks(json.dumps(value, ensure_ascii=False), size=3)
            return pieces[:-2] + [pause] + pieces[-2:]

        spoken = []
        async def render(_, speech, *, provider_id, timeout_seconds):
            spoken.append((speech, provider_id, timeout_seconds))
            return None if speech == "第二段。" else {"type": "record", "data": {"file": "base64://YQ=="}}

        self.client_state.behavior = respond
        self.native_sender.voice = render
        self.native_sender.voice_delivery = VoiceReplyDelivery(self.runtime, self.clock.now)
        host = await self.start_stream_host(gap=2)
        app = host.application
        batch = host.receive(await self.capture(event)).unwrap()
        manager = ReplyManagement(app, self.context(app, batch))
        status = manager.status(self.core).unwrap()
        self.assertFalse(status["settings"]["voice_enabled"])
        manager.configure(self.core, {"operation_key": "leading-images", "edit_token": status["edit_token"],
                                     "changes": {"image_position": "before_text", "voice_enabled": True,
                                                 "voice_generation_mode": "model_tag", "voice_delivery_mode": "voice_only",
                                                 "voice_position": "before_text", "voice_provider_id": "sealed-tts",
                                                 "voice_timeout_seconds": 12}}).unwrap()
        await asyncio.wait_for(waiting.wait(), 3)
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        captured = json.loads(app.messages.batch(batch)["contributions_json"])["reply_settings"]
        self.assertEqual(captured["settings"]["image_position"], "before_text")
        self.assertEqual(captured["settings"]["voice_provider_id"], "sealed-tts")
        self.assertTrue(all("<pc_tts>" in call["messages"][1]["content"] for call in self.client_state.calls))
        status = manager.status(self.core).unwrap()
        manager.configure(self.core, {"operation_key": "later-images", "edit_token": status["edit_token"],
                                     "changes": {"image_position": "after_text", "voice_enabled": False,
                                                 "voice_provider_id": "later-tts", "voice_position": "after_media"}}).unwrap()
        release.set()
        await self.until(lambda: app.flow.row(batch)["reason"] == "part_spacing")
        sends = self.native.platform.client._api._wsr_api.calls
        self.assertEqual([[p["type"] for p in params["message"]] for _, params in sends], [["record"]])
        self.assertEqual(self.diagnostics(app, batch), [
            ("delivered", "planned", "ready", ["voice"], 1),
            ("pending", "planned", "pending", [], 0),
            ("pending", "planned", "pending", [], 0)])

        await app.close()
        runtime = self.open_runtime()
        self.native_sender.voice_delivery = VoiceReplyDelivery(runtime, self.clock.now)
        restored = await self.start_stream_host(gap=2, runtime=runtime, generation=1)
        app = restored.application
        self.advance(app, 2)
        await self.until(lambda: self.parts(app, batch)[1]["state"] == "delivered")
        self.advance(app, 2)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual([[p["type"] for p in params["message"]] for _, params in sends],
                         [["record"], ["text"], ["record"], ["image", "image", "text"]])
        self.assertEqual(self.diagnostics(app, batch), [
            ("delivered", "planned", "ready", ["voice"], 1),
            ("delivered", "planned", "empty", ["text"], 0),
            ("delivered", "planned", "ready", ["image", "image", "voice", "text"], 0)])
        self.assertEqual([p["data"]["file"] for p in sends[3][1]["message"][:2]],
                         ["base64://" + base64.b64encode(b).decode("ascii") for b in reversed(originals)])
        self.assertEqual(spoken, [(speech, "sealed-tts", 12) for speech in ("第一段。", "第二段。", "第三段。")])
        self.assertEqual(len(self.client_state.calls), 2)
        self.assertTrue(all(call["stream"] for call in self.client_state.calls))
        context = self.context(app, batch)
        self.assertEqual(ReplyManagement(app, context).status(self.core).unwrap()["settings"]["image_position"], "after_text")
        binding = app.messages.reply_images.read_binding(app.messages.batch(batch), context, self.clock.now(),
                                                        with_position=True)
        self.assertEqual(binding[3], "before_text")
        history = app.messages.history(context).unwrap()["items"]
        self.assertEqual([len(item.get("images", ())) for item in history], [0, 0, 2])

        self.client_state.behavior = None
        self.client_state.text = final_text("这一轮文字回复。")
        next_batch = restored.receive(await self.capture(FakeEvent(self.native, event_id="voice-disabled"))).unwrap()
        self.assertEqual((await self.done(app, next_batch))["state"], "complete")
        self.assertEqual(len(spoken), 3)
        self.assertEqual([p["type"] for p in sends[-1][1]["message"]], ["text"])
        self.assertNotIn("<pc_tts>", self.client_state.calls[-1]["messages"][1]["content"])
        self.assertIsNone(app.runtime.read_one("SELECT v.part_id FROM conversation_voice_parts v "
            "JOIN conversation_parts p ON p.part_id = v.part_id WHERE p.batch_id = ?", (next_batch,)))
        self.assertEqual(self.diagnostics(app, next_batch),
                         [("delivered", "voice_disabled", "not_applicable", ["text"], 0)])

    async def test_silent_action_finishes_without_creating_a_delivery_part(self):
        self.client_state.text = json.dumps({"action": "silent", "text": "", "claims": []})
        host = await self.start_stream_host()
        app = host.application
        batch = host.receive(await self.capture()).unwrap()

        result = await self.done(app, batch)

        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["reason"], "model_silent")
        self.assertEqual(app.messages.batch(batch)["presentation_action"], "silent")
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_poke_only_action_uses_native_poke_without_sending_an_empty_message(self):
        self.client_state.text = json.dumps({"action": "poke", "text": "", "claims": []})
        host = await self.start_stream_host()
        app = host.application
        batch = host.receive(await self.capture()).unwrap()

        result = await self.done(app, batch)

        calls = self.native.platform.client._api._wsr_api.calls
        self.assertEqual(result["state"], "complete")
        self.assertEqual(app.messages.batch(batch)["presentation_action"], "poke")
        self.assertEqual([part["state"] for part in self.parts(app, batch)], ["delivered"])
        self.assertEqual([action for action, _ in calls], ["friend_poke"])
        self.assertEqual(calls[0][1]["user_id"], int(self.context(app, batch).scope.native_scope_id))

    async def test_unknown_poke_only_action_is_not_replayed(self):
        self.client_state.text = json.dumps({"action": "poke", "text": "", "claims": []})
        host = await self.start_stream_host()
        app = host.application
        api = self.native.platform.client._api._wsr_api
        original = api.call_action

        async def timed_out(action, **params):
            api.calls.append((action, params))
            raise TimeoutError("poke acknowledgement was lost")

        api.call_action = timed_out
        batch = host.receive(await self.capture()).unwrap()

        result = await self.done(app, batch)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual([part["state"] for part in self.parts(app, batch)], ["unknown"])
        self.assertEqual([action for action, _ in api.calls], ["friend_poke"])

        api.call_action = original
        app.notify()
        await asyncio.sleep(0.05)
        self.assertEqual([action for action, _ in api.calls], ["friend_poke"])

    async def test_voice_only_action_sends_only_voice_and_never_falls_back_to_text(self):
        response = {"action": "voice_only", "text": "我在这里。", "claims": [
            {"id": "c1", "kind": "subjective", "statement": "我在这里。", "evidence": None}]}
        self.client_state.text = json.dumps(response, ensure_ascii=False)
        async def render(_, speech, *, provider_id="", timeout_seconds=30):
            return {"type": "record", "data": {"file": "base64://YQ=="}}
        self.native_sender.voice = render
        host = await self.start_stream_host(voice_policy=VoiceReplyPolicy())
        app = host.application
        first = host.receive(await self.capture()).unwrap()
        self.assertEqual((await self.done(app, first))["state"], "complete")
        api = self.native.platform.client._api._wsr_api
        self.assertEqual([part["type"] for part in api.calls[-1][1]["message"]], ["record"])
        self.assertEqual(app.messages.batch(first)["presentation_action"], "voice_only")

        async def unavailable(_, speech, *, provider_id="", timeout_seconds=30):
            return None
        self.native_sender.voice = unavailable
        second = host.receive(await self.capture(FakeEvent(self.native, event_id="voice-only-failed"))).unwrap()
        self.assertEqual((await self.done(app, second))["state"], "blocked")
        self.assertEqual([part["state"] for part in self.parts(app, second)], ["failed"])
        self.assertEqual(len(api.calls), 1)

    async def test_original_turn_deadline_interrupts_stream_without_publishing(self):
        entered = asyncio.Event()
        async def pause():
            entered.set()
            await asyncio.Event().wait()
        async def respond(_):
            return [chunk('{"text":"尚未完成'), pause]
        self.client_state.behavior = respond
        snapshot = await self.capture()
        host = await self.start_stream_host()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await asyncio.wait_for(entered.wait(), 3)
        self.advance(app, 181)
        await self.done(app, batch)
        await self.until(lambda: self.client_state.streams[0].closed)
        self.assertEqual(self.parts(app, batch), ())
        self.assertEqual(self.texts(), [])
        self.assertEqual(len(self.client_state.calls), 1)
