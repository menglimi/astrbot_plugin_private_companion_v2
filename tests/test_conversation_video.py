"""Video input through tools, text replies, provenance and recovery."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from companion_v2.adapters.astrbot.model_wire import build_wire, tool_alias, decode_response
from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.model_gateway.models import ModelEnvelope
from companion_v2.sources.dependencies import key
from tests.audio_support import FakeRecord
from tests.animation_support import animation_bytes
from tests.native_adapter_support import completion, final_text
from tests.test_conversation_images import FakeImage
from tests.video_support import VideoFixture, FakeVideo, video_bytes


class ConversationVideoTests(VideoFixture, unittest.IsolatedAsyncioTestCase):
    async def test_video_only_and_tool_continuation_preserve_sampled_evidence_and_confirmed_history(self):
        views = []
        async def respond(payload, _):
            content = payload["messages"][2]["content"]
            views.append(content[1:])
            materials = json.loads(content[0]["text"])["materials"]
            video = next(m for m in materials if m["owner"] == "conversation.video")
            self.assertEqual(json.loads(video["text"])["audio_status"], "not_inspected")
            if len(views) == 1:
                return completion(tools=[NS(id="video-read", type="function", function=NS(name=tool_alias("memo.list"), arguments="{}"))])
            return completion(final_text("采样画面有颜色变化。", evidence=video["evidence"]))
        self.native.provider.client.state.behavior = respond
        host = await self.setup_host()
        batch = host.receive(await self.capture(self.video_event())).unwrap()
        app, context = host.application, self.context(host.application, batch)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(len(views), 2)
        self.assertEqual(views[0], views[1])
        self.assertEqual(len([part for part in views[0] if part["type"] == "image_url"]), 4)
        self.assertEqual(app.messages.history(context).unwrap()["items"][0]["text"], "采样画面有颜色变化。")
        event = self.original(app, batch)
        source, asset = app.messages.videos.references(event, event.videos[0])
        access = app.memory.writer.access.sent_sources
        reference, = tuple(access.rows(context))
        access.materialize(context, reference)
        deps = app.runtime.read_all("SELECT input_id, input_lineage, input_revision FROM source_dependencies WHERE dependent_id = ?", (reference.source_id,))
        self.assertIn(key(source), [tuple(r) for r in deps])
        app.messages.videos.assets.revoke(asset, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError) as caught:
            access.validate(context, reference)
        self.assertEqual(caught.exception.code, "asset_revoked")
        app.withdraw(context, event.scoped_key).unwrap()
        self.assertEqual(app.messages.sources.validate_reference(reference, observed_at=self.clock.now()).failure.code, "source_revoked")

    async def test_mixed_image_audio_video_keeps_original_positions_and_frame_send_is_not_offered(self):
        host = await self.quiet_host()
        event = self.video_event()
        event.message_obj.message = [FakeVideo(), NS(type="Plain", text="看看这个"), FakeImage(), FakeRecord()]
        batch = host.receive(await self.capture(event)).unwrap()
        request = self.request(host.application, batch)
        self.assertEqual([v.descriptor.position for v in request.videos], [0])
        self.assertEqual([i.descriptor.position for i in request.images], [2])
        self.assertEqual([a.descriptor.position for a in request.audios], [3])
        wire = build_wire(ModelEnvelope(replace(request, reply_images=True), "fixture", 100, "fixture"))
        self.assertEqual(wire.image_count, 5)
        self.assertEqual(tuple(wire.reply_images.values()), (request.images[0].source,))
        for source in (request.videos[0].source, request.videos[0].frames[0].source):
            self.assertNotIn(source, wire.reply_images.values())
        self.assertIn("音轨均未检查", request.instruction)

    async def test_video_count_and_combined_frame_budget_split_batches(self):
        host = await self.quiet_host()
        first = host.receive(await self.capture(self.video_event("one", count=2))).unwrap()
        second = host.receive(await self.capture(self.video_event("two"))).unwrap()
        self.assertNotEqual(first, second)
        app = host.application
        app.cancel(self.context(app, first), first).unwrap()
        app.cancel(self.context(app, second), second).unwrap()
        third = host.receive(await self.capture(self.video_event("three", count=2))).unwrap()
        event = self.image_event("images", content=animation_bytes(count=10))
        event.message_obj.message.extend(FakeImage() for _ in range(5))
        fourth = host.receive(await self.capture(event)).unwrap()
        self.assertNotEqual(third, fourth)

    async def test_stored_over_budget_merge_is_rejected_before_blob_reads(self):
        host = await self.quiet_host()
        first = host.receive(await self.capture(self.video_event("one", count=2))).unwrap()
        second = host.receive(await self.capture(self.video_event("two"))).unwrap()
        app = host.application
        with app.runtime.transaction() as db:
            db.execute("UPDATE conversation_inputs SET batch_id = ?, position = 2 WHERE batch_id = ?", (first, second))
        with patch.object(app.messages.videos, "read", side_effect=AssertionError("must not read blobs")), self.assertRaises(TaskError) as caught:
            self.request(app, first)
        self.assertEqual(caught.exception.code, "video_turn_limit")

    async def test_frame_publication_failure_rolls_back_video_source_and_whole_intake(self):
        host = await self.quiet_host()
        captured = await self.capture(self.video_event())
        with patch.object(host.application.messages.images, "publish", side_effect=TaskError("image_content_changed", "synthetic")):
            self.assertEqual(host.receive(captured).failure.code, "image_content_changed")
        for table in ("conversation_inputs", "conversation_video_payloads", "conversation_image_payloads"):
            self.assertEqual(host.application.runtime.read_one("SELECT COUNT(*) FROM " + table, ())[0], 0)
        self.assertEqual(host.application.runtime.read_one("SELECT COUNT(*) FROM sources WHERE owner IN ('conversation.host_input', 'conversation.video')", ())[0], 0)

    async def test_replay_conflict_cannot_replace_video_bytes_or_saved_frames(self):
        host = await self.quiet_host()
        captured = await self.capture(self.video_event())
        batch = host.receive(captured).unwrap()
        before = self.request(host.application, batch).videos
        changed = host.receive(await self.capture(self.video_event(content=video_bytes(tint=50))))
        self.assertEqual(changed.failure.code, "message_event_conflict")
        self.assertEqual(self.request(host.application, batch).videos, before)
        self.assertEqual(host.receive(captured).unwrap(), batch)

    async def test_revoked_video_or_frame_and_changed_blob_block_reads(self):
        host = await self.quiet_host()
        for index, mode in enumerate(("original_asset", "frame_asset", "original_body", "frame_body", "missing")):
            batch = host.receive(await self.capture(self.video_event(str(index)))).unwrap()
            app, event = host.application, self.original(host.application, batch)
            reference, asset = app.messages.videos.references(event, event.videos[0])
            parent = app.messages.videos.frame_event(event, event.videos[0])
            frame, frame_asset = app.messages.images.references(parent, parent.images[0])
            if mode.endswith("asset"):
                app.messages.videos.assets.revoke(asset if mode == "original_asset" else frame_asset,
                    expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
            else:
                with app.runtime.transaction() as db:
                    if mode == "missing":
                        db.execute("DELETE FROM conversation_video_payloads WHERE parent_id = ?", (event.source.source_id,))
                    elif mode == "frame_body":
                        db.execute("UPDATE conversation_image_payloads SET content = ? WHERE source_id = ?", (b"changed", frame.source_id))
                    else:
                        db.execute("UPDATE conversation_video_payloads SET content = ? WHERE source_id = ?", (b"changed", reference.source_id))
            with self.assertRaises(TaskError) as caught:
                self.request(app, batch)
            expected = "asset_revoked" if mode.endswith("asset") else "video_original_unavailable" if mode == "missing" else "image_content_changed" if mode == "frame_body" else "video_content_changed"
            self.assertEqual(caught.exception.code, expected)
            app.cancel(self.context(app, batch), batch).unwrap()

    async def test_restart_reuses_video_and_frames_without_download_or_decoder(self):
        host = await self.quiet_host()
        captured = await self.capture(self.video_event())
        batch = host.receive(captured).unwrap()
        before = self.request(host.application, batch).videos
        await host.application.close()
        self.clock.advance(timedelta(seconds=0.2))
        new = self.host(runtime=self.open_runtime(), event_port=self.bridge.ports, identity_port=self.bridge.ports,
            role_port=self.bridge.ports, providers=(self.native_model.local_provider(),), sender=self.native_sender.local_sender(),
            runtime_identity=RuntimeIdentity("companion", "runtime-2", "astrbot", "host"))
        with patch("astrbot_host.video.loader.decode_video", side_effect=AssertionError("must not decode again")):
            await self.start(new, 1, 1)
            self.assertEqual(self.request(new.application, batch).videos, before)
            self.assertEqual(new.receive(captured).unwrap(), batch)

    async def test_visual_capability_is_required_and_unknown_model_calls_are_not_repeated(self):
        provider = replace(self.native_model.local_provider(), capabilities=("text", "tools", "audio"))
        host = await self.setup_host(providers=(provider,))
        batch = host.receive(await self.capture(self.video_event())).unwrap()
        await self.done(host.application, batch)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_unknown_video_model_result_does_not_repeat_on_replay(self):
        async def timeout(payload, _):
            raise TimeoutError("synthetic lost response")
        self.native.provider.client.state.behavior = timeout
        host = await self.setup_host()
        captured = await self.capture(self.video_event())
        batch = host.receive(captured).unwrap()
        await self.done(host.application, batch)
        self.assertEqual(host.receive(captured).unwrap(), batch)
        await asyncio.sleep(0)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_original_withdrawn_during_sdk_preparation_cannot_dispatch(self):
        host = await self.setup_host()
        original = type(self.native.provider)._prepare_chat_payload
        async def withdraw(native, **kwargs):
            app = host.application
            batch = app.runtime.read_one("SELECT batch_id FROM conversation_inputs", ())[0]
            app.withdraw(self.context(app, batch), self.original(app, batch).scoped_key).unwrap()
            return await original(native, **kwargs)
        with patch.object(type(self.native.provider), "_prepare_chat_payload", withdraw):
            batch = host.receive(await self.capture(self.video_event())).unwrap()
            await self.done(host.application, batch)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_capture_rechecks_persona_and_uses_frozen_video_location(self):
        event = self.video_event()
        async def mutate(locator):
            event.message_obj.message[0].file = "file:///C:/other.mp4"
            self.assertTrue(locator.locator.startswith("base64://"))
            return self.captured_video(locator.position)
        self.bridge.video_loader = mutate
        self.assertEqual((await self.capture(event)).videos[0].content, video_bytes())
        async def change(locator):
            self.native.cid = "changed"
            return self.captured_video(locator.position)
        self.bridge.video_loader = change
        self.assertEqual((await self.bridge.capture(self.video_event())).failure.code, "host_persona_changed")
