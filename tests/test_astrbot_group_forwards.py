"""Native group forwards stay pinned to one authenticated outer message."""

import asyncio
import base64
from dataclasses import replace
from datetime import timedelta
from functools import partial
import json
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace as NS

from astrbot.core.message.components import Forward
from astrbot_host.audio.loader import load_native_audio
from astrbot_host.media import load_native_image
from astrbot_host.video.loader import load_native_video
from astrbot_host.group_authority import GroupAuthority
from companion_v2.adapters.astrbot.forwards import read_private_forwards
from companion_v2.adapters.astrbot.group_forwards import read_group_forwards
from companion_v2.conversation.forwards.models import MAX_NODES
from tests.forward_support import node_raw
from tests.group_media_support import GroupMediaFixture, group_raw
from tests.audio_support import audio_bytes
from tests.audio_support import FakeRecord
from tests.test_conversation_images import image_bytes
from tests.staging_bootstrap_support import wait_for_batch
from tests.video_support import video_bytes
from tests.video_support import FakeVideo
from tests.native_adapter_support import completion, final_text
from companion_v2.adapters.astrbot.model_wire import tool_alias
from astrbot.api.message_components import Plain
from companion_v2.conversation.forwards.service import forward_reference, node_reference
from companion_v2.execution.models import TaskContext, TaskError


def text_content(content):
    if isinstance(content, str):
        return content.partition("\n")[0]
    return next((part["text"] for part in content
                 if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)), "")


class AstrBotGroupForwardTests(GroupMediaFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.types = replace(self.types, forward=Forward,
            forward_loader=partial(read_private_forwards, reverse_api_type=type(self.api), image_loader=load_native_image),
            group_forward_loader=partial(read_group_forwards, reverse_api_type=type(self.api), image_loader=load_native_image,
                audio_loader=load_native_audio, video_loader=load_native_video))
        self.controller = self.make_controller(self.config)

    def forward_event(self, identifier="1201", *, sender="201", resource="group-forward"):
        event = self.media_event([Forward(id=resource)], identifier=identifier, sender=sender)
        event.message_obj.raw_message["message"] = [{"type": "forward", "data": {"id": resource}}]
        return event

    def store_group_forward(self, identifier, *, sender="201", resource="group-forward", nodes=None):
        raw = group_raw(message_id=identifier, sender=sender, text="", count=0)
        raw["message"] = [{"type": "forward", "data": {"id": resource,
            "content": nodes if nodes is not None else [node_raw("群记录原文", sender="999")]}}]
        self.records[str(identifier)] = raw

    async def restart_host(self):
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()

    async def accept_forward(self, identifier="1201", *, sender="201", nodes=None):
        self.store_group_forward(identifier, sender=sender, nodes=nodes)
        batch = (await self.controller.receive_claimed(self.forward_event(identifier, sender=sender))).unwrap()
        await wait_for_batch(self.controller.session, batch)
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        return context, batch

    async def test_expanded_nested_group_nodes_and_image_are_original_sources(self):
        await self.start_host()
        self.store_group_forward("1201", nodes=[node_raw("外层记录", sender="999", images=(image_bytes(),),
            nested=[node_raw("嵌套记录", sender="888")])])
        event = self.forward_event()
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        self.assertEqual(self.history_calls, [("get_group_msg_history", {
            "self_id": "100", "group_id": "300", "message_seq": "1201", "count": 1,
            "reverse_order": False, "parse_mult_msg": True})])
        row = self.app.messages.batch(batch)
        context = TaskContext.restore(json.loads(row["context_json"]))
        request = self.request(context, batch)
        self.assertEqual(len(request.images), 1)
        self.assertEqual(request.images[0].parent.scope.native_scope_id, "300")
        payload = self.native.provider.client.state.calls[0][0]["messages"]
        user_content = next(item["content"] for item in payload if item["role"] == "user")
        user_text = text_content(user_content)
        material = json.loads(user_text)
        nodes = [json.loads(item["text"]) for item in material["materials"]
                 if item["owner"] == "conversation.forward_node"]
        self.assertEqual([node["node_path"] for node in nodes], [[0], [0, 2, 0]])
        self.assertEqual([node["displayed_sender"] for node in nodes], ["999", "888"])
        self.assertTrue(all(node["forwarded_by"] == "201" for node in nodes))
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads", ())[0], 1)

    async def test_group_forward_audio_reaches_model_with_explicit_unread_video_fallback(self):
        views = []
        async def respond(payload, _):
            content = next(m["content"] for m in payload["messages"] if m["role"] == "user")
            views.append(content)
            materials = json.loads(content[0]["text"])["materials"]
            voice = next(m for m in materials if m["purpose"].startswith("forwarded_audio:"))
            if len(views) == 1:
                return completion(tools=[NS(id="group-forward-query", type="function", function=NS(
                    name=tool_alias("group.memory.query"), arguments="{}"))])
            return completion(final_text("节点附有语音和视频采样画面。", evidence=voice["evidence"]))
        self.native.provider.client.state.behavior = respond
        await self.with_delivery()
        voice, clip = audio_bytes(), video_bytes(count=12)
        node = node_raw("外层记录", nested=[node_raw("群记录中的音视频", sender="999", audios=(voice,), videos=(clip,))])
        self.store_group_forward("1201", nodes=[node])
        batch = (await self.controller.receive_claimed(self.forward_event())).unwrap()
        await wait_for_batch(self.controller.session, batch)
        row = self.app.messages.batch(batch)
        context = TaskContext.restore(json.loads(row["context_json"]))
        request = self.request(context, batch)
        self.assertEqual((len(request.audios), len(request.videos)), (1, 1))
        self.assertEqual(request.audios[0].descriptor.byte_count, len(voice))
        self.assertEqual(request.videos[0].descriptor.coverage, "sampled_frames")
        self.assertEqual(len(request.videos[0].frames), 4)
        node_material = next(json.loads(item.payload) for item in request.context.materials
                             if item.owner == "conversation.forward_node" and "audio_components" in item.payload)
        self.assertEqual(node_material["node_path"], [0, 1, 0])
        self.assertEqual(len(node_material["audio_components"]), 1)
        self.assertEqual(len(node_material["video_components"]), 1)
        audio_material = next(json.loads(item.payload) for item in request.context.materials
                              if item.purpose.startswith("forwarded_audio:"))
        self.assertEqual(audio_material["attribution"], "forward_record_claim")
        self.assertEqual(audio_material["sender_claim"], "999")
        self.assertEqual((audio_material["sender"], audio_material["forwarded_by"]), ("unknown", "201"))
        self.assertEqual(len(views), 2)
        self.assertEqual(views[0][1:], views[1][1:])
        evidence_materials = [[m for m in json.loads(view[0]["text"])["materials"]
                               if m["evidence"] and m["owner"].startswith("conversation.")] for view in views]
        self.assertEqual(evidence_materials[0], evidence_materials[1])
        self.assertEqual([part["type"] for part in views[0]].count("input_audio"), 1)
        self.assertEqual([part["type"] for part in views[0]].count("image_url"), 0)
        video_status = [m for m in json.loads(views[0][0]["text"])["materials"]
                        if m["purpose"] == "current_video_narration"]
        self.assertEqual(len(video_status), 1)
        self.assertIn("尚未读取视频", video_status[0]["text"])
        video_material = next(json.loads(item.payload) for item in request.context.materials
                              if item.purpose.startswith("forwarded_video:"))
        self.assertEqual(video_material["audio_status"], "not_inspected")
        self.assertEqual(self.app.flow.row(batch)["state"], "complete")
        self.assertEqual([action for action, _ in self.api.calls], ["send_group_msg"])

    async def test_group_forward_history_is_metadata_only_and_revalidates_sources(self):
        await self.start_host()
        voice, clip = audio_bytes(), video_bytes(count=12)
        node = node_raw("带旧附件的记录", sender="999", images=(image_bytes(),))
        node["message"].extend((
            {"type": "record", "data": {"file": "base64://" + base64.b64encode(voice).decode("ascii"), "url": ""}},
            {"type": "video", "data": {"file": "base64://" + base64.b64encode(clip).decode("ascii"), "url": ""}},
        ))
        self.store_group_forward("1201", nodes=[node])
        first = self.forward_event()
        first_batch = (await self.controller.receive_claimed(first)).unwrap()
        await wait_for_batch(self.controller.session, first_batch)
        first_context = TaskContext.restore(json.loads(self.app.messages.batch(first_batch)["context_json"]))
        before = self.request(first_context, first_batch)
        calls = len(self.history_calls), len(self.native.provider.client.state.calls)
        await self.restart_host()
        with patch("astrbot_host.video.loader.load_native_video", side_effect=AssertionError("recovery cannot decode")), \
                patch("astrbot_host.audio.loader.load_native_audio", side_effect=AssertionError("recovery cannot decode")):
            restored = self.request(first_context, first_batch)
        self.assertEqual((restored.audios, restored.videos, restored.images), (before.audios, before.videos, before.images))
        self.assertEqual((len(self.history_calls), len(self.native.provider.client.state.calls)), calls)
        second = self.media_event([Plain("继续聊")], identifier="1202", sender="202")
        second_batch = (await self.controller.receive_claimed(second)).unwrap()
        await wait_for_batch(self.controller.session, second_batch)
        row = self.app.messages.batch(second_batch)
        context = TaskContext.restore(json.loads(row["context_json"]))
        request = self.request(context, second_batch)
        self.assertEqual(request.images, ())
        self.assertEqual((request.audios, request.videos), ((), ()))
        history = next(json.loads(item.payload) for item in request.context.materials
                       if item.purpose == "group_conversation_history")
        attachments = history["attachments"]
        self.assertEqual(len([item for item in attachments if "audio" in item]), 1)
        self.assertEqual(len([item for item in attachments if "video" in item]), 1)
        self.assertEqual(history["speaker_id"], "201")
        self.assertTrue(all(item["attribution"] == "forward_record_claim" for item in attachments))
        self.assertTrue(all(item["view"] == "historical_metadata_only" for item in attachments))
        self.assertNotIn("base64", json.dumps(history, ensure_ascii=False))
        messages = self.native.provider.client.state.calls[-1][0]["messages"]
        user_content = next(item["content"] for item in messages if item["role"] == "user")
        user_text = text_content(user_content)
        self.assertIn("forwarded_records", user_text)
        self.assertIn("historical_metadata_only", user_text)
        self.assertNotIn("image_url", json.dumps(user_content, ensure_ascii=False))
        self.assertNotIn("input_audio", json.dumps(user_content, ensure_ascii=False))

    async def test_group_context_drops_member_messages_older_than_configured_window(self):
        await self.start_host()
        await self.receive_parts([Plain("十三小时前的祸兽专名")], sender="201")
        self.clock.advance(timedelta(hours=13))
        context, batch = await self.receive_parts([Plain("普通掉半血吗？")], sender="202")
        history = [json.loads(item.payload) for item in self.request(context, batch).context.materials
                   if item.purpose == "group_conversation_history"]
        self.assertNotIn("十三小时前的祸兽专名", json.dumps(history, ensure_ascii=False))
        self.assertNotIn("普通掉半血吗？", json.dumps(history, ensure_ascii=False))

    async def test_withdrawal_revokes_group_forward_and_removes_it_from_later_history(self):
        await self.start_host()
        voice, clip = audio_bytes(), video_bytes(count=12)
        node_value = node_raw("可撤回的旧记录", sender="999", images=(image_bytes(),))
        node_value["message"].extend((
            {"type": "record", "data": {"file": "base64://" + base64.b64encode(voice).decode("ascii"), "url": ""}},
            {"type": "video", "data": {"file": "base64://" + base64.b64encode(clip).decode("ascii"), "url": ""}},
        ))
        self.store_group_forward("1201", nodes=[node_value])
        first = self.forward_event()
        first_batch = (await self.controller.receive_claimed(first)).unwrap()
        await wait_for_batch(self.controller.session, first_batch)
        first_context = TaskContext.restore(json.loads(self.app.messages.batch(first_batch)["context_json"]))
        original = self.input(first_context, first_batch)
        root = forward_reference(original.source, original.forwards[0].position)
        node = node_reference(root, original.forwards[0].nodes[0].path)

        second = self.media_event([Plain("继续聊")], identifier="1202", sender="201")
        second_batch = (await self.controller.receive_claimed(second)).unwrap()
        await wait_for_batch(self.controller.session, second_batch)
        second_context = TaskContext.restore(json.loads(self.app.messages.batch(second_batch)["context_json"]))
        second_history = [json.loads(material.payload) for material in self.request(second_context, second_batch).context.materials
                          if material.purpose == "group_conversation_history"]
        self.assertIn("forwarded_records", json.dumps(second_history, ensure_ascii=False))

        self.app.withdraw(first_context, original.scoped_key).unwrap()
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        self.assertTrue((await self.controller.load_existing()).is_success)
        self.assertTrue((await self.controller.start()).is_success)
        for reference in (root, node):
            self.assertEqual(self.app.messages.sources.validate_reference(
                reference, observed_at=self.clock.now()).failure.code, "source_revoked")
        for owner in ("conversation.image", "conversation.audio", "conversation.video"):
            sources = self.app.runtime.read_all("SELECT state FROM sources WHERE owner = ?", (owner,))
            self.assertTrue(sources, owner)
            self.assertTrue(all(row["state"] == "revoked" for row in sources), owner)

        third = self.media_event([Plain("再继续")], identifier="1203", sender="202")
        third_batch = (await self.controller.receive_claimed(third)).unwrap()
        await wait_for_batch(self.controller.session, third_batch)
        third_context = TaskContext.restore(json.loads(self.app.messages.batch(third_batch)["context_json"]))
        history = [json.loads(material.payload) for material in self.request(third_context, third_batch).context.materials
                   if material.purpose == "group_conversation_history"]
        self.assertNotIn("forwarded_records", json.dumps(history, ensure_ascii=False))

    async def test_group_forward_rejects_wrong_sender_and_host_preprocessed_card(self):
        await self.start_host()
        self.store_group_forward("1201", sender="999")
        baseline = self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0]
        result = await self.controller.receive_claimed(self.forward_event())
        self.assertFalse(result.is_success)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], baseline)
        event = self.forward_event("1202")
        event.message_obj.raw_message["message"] = [{"type": "forward", "data": {"id": "group-forward"}}]
        event.message_obj.message = [Plain("宿主转换后的正文")]
        result = await self.controller.receive_claimed(event)
        self.assertEqual(result.failure.code, "host_group_media_unsupported")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], baseline)

    async def test_revoked_media_invalidates_saved_cross_member_history_after_restart(self):
        await self.start_host()
        nodes = [node_raw("可撤权附件", audios=(audio_bytes(),), videos=(video_bytes(),))]
        for index, mode in enumerate(("waveform", "video", "frame", "audio_source")):
            with self.subTest(mode=mode):
                a, first = await self.accept_forward(str(1301 + index * 2), nodes=nodes)
                original_request = self.request(a, first)
                b, later = await self.receive_parts([Plain("讨论这份记录")], sender="202")
                event = self.input(a, first)
                forward, node = event.forwards[0], event.forwards[0].nodes[0]
                audio_parent = self.app.messages.forwards.audio_event(event, forward, node)
                video_parent = self.app.messages.forwards.video_event(event, forward, node)
                audio_source, _, wave = self.app.messages.audio.references(audio_parent, node.audios[0])
                video_source, video_asset = self.app.messages.videos.references(video_parent, node.videos[0])
                frame_parent = self.app.messages.videos.frame_event(video_parent, node.videos[0])
                frame_source, frame_asset = self.app.messages.images.references(frame_parent, frame_parent.images[0])
                evidence = []
                snapshot = json.loads(self.app.messages.batch(later)["contributions_json"])["group_context"]
                first_row = self.app.runtime.read_one("SELECT * FROM conversation_inputs WHERE batch_id = ?", (first,))
                reference = self.app.messages.group_context.input_ref(first_row)
                self.assertIn(reference, snapshot["references"])
                self.app.messages.group_context.replies.read(reference, b, self.app.messages.batch(later)["role_instruction"],
                    self.clock.now(), self.app.messages.group_context.cutoff(later), evidence=evidence)
                self.assertTrue({audio_source, video_source, frame_source}.issubset(evidence))
                self.assertEqual(self.app.messages.sources.read(original_request.audios[0].source,
                    resolved=b.actor, capability="text", observed_at=self.clock.now(),
                    authorizer=self.app.tasks.identity).failure.code, "source_audience_denied")
                owner, reference = {
                    "waveform": (self.app.messages.audio.assets, wave),
                    "video": (self.app.messages.videos.assets, video_asset),
                    "frame": (self.app.messages.images.assets, frame_asset),
                    "audio_source": (self.app.messages.sources, audio_source),
                }[mode]
                owner.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
                await self.restart_host()
                with self.assertRaises(TaskError) as caught:
                    self.request(b, later)
                self.assertEqual(caught.exception.code, "source_revoked" if mode == "audio_source" else "asset_revoked")
                c, following = await self.receive_parts([Plain("再继续")], sender="202")
                history = [json.loads(m.payload) for m in self.request(c, following).context.materials
                           if m.purpose == "group_conversation_history"]
                self.assertNotIn("forwarded_records", json.dumps(history, ensure_ascii=False))

    async def test_original_forwarder_revocation_during_later_generation_blocks_delivery(self):
        await self.with_delivery()
        a, first = await self.accept_forward(nodes=[node_raw("转发附件", audios=(audio_bytes(),), videos=(video_bytes(),))])
        self.assertEqual(self.app.flow.row(first)["state"], "complete")
        async def revoke(payload, _):
            grant = GroupAuthority.grant_id(a.scope, a.actor.subject, "text")
            identity = self.controller.authority.identities
            identity.revoke_grant(grant, revoked_at=self.clock.now(), expected_revision=identity.revision)
            return completion(final_text("不应发出的旧资料答复"))
        self.native.provider.client.state.behavior = revoke
        event = self.media_event([Plain("接着讨论记录")], sender="202")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        self.assertEqual(self.app.flow.row(batch)["state"], "blocked")
        self.assertEqual([action for action, _ in self.api.calls], ["send_group_msg"])

    async def test_direct_and_forward_media_share_audio_video_and_frame_budgets(self):
        from tests.animation_support import animation_bytes
        from tests.group_media_support import sdk_image
        await self.start_host()
        cases = (
            (node_raw(audios=(audio_bytes(),) * 4), [FakeRecord()], "host_group_media_limit"),
            (node_raw(videos=(video_bytes(),) * 2), [FakeVideo()], "host_group_media_limit"),
            (node_raw(videos=(video_bytes(),) * 2), [sdk_image(animation_bytes(count=10)) for _ in range(3)],
             "host_forward_limit"),
        )
        for index, (node, direct, code) in enumerate(cases):
            with self.subTest(index=index):
                identifier = str(1401 + index)
                self.store_group_forward(identifier, nodes=[node])
                event = self.forward_event(identifier)
                for part in direct:
                    kind = getattr(part.type, "value", part.type).lower()
                    raw = {"type": kind, "data": {"file": part.file}}
                    event.message_obj.message.append(part)
                    event.message_obj.raw_message["message"].append(raw)
                    self.records[identifier]["message"].append(raw)
                result = await self.controller.receive_claimed(event)
                self.assertFalse(result.is_success, index)
                self.assertEqual(result.failure.code, code)
                for table in ("conversation_inputs", "conversation_audio_payloads", "conversation_video_payloads", "sources"):
                    self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM " + table, ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_forward_media_loaders_are_optional_and_account_change_during_capture_is_rejected(self):
        await self.start_host()
        bridge = self.controller.session.bridge.groups
        for index, options in enumerate(({"video_loader": load_native_video}, {"audio_loader": load_native_audio})):
            identifier = str(1201 + index)
            self.store_group_forward(identifier, nodes=[node_raw(audios=(audio_bytes(),), videos=(video_bytes(),))])
            bridge.forward_loader = partial(read_group_forwards, reverse_api_type=type(self.api),
                image_loader=load_native_image, **options)
            result = await self.controller.receive_claimed(self.forward_event(identifier))
            self.assertTrue(result.is_success, result.failure)
            batch = result.unwrap()
            await wait_for_batch(self.controller.session, batch)
            context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
            captured = self.input(context, batch)
            self.assertEqual(type(captured).__name__, "InboundConversationEvent")
            payload = json.dumps(self.native.provider.client.state.calls[-1][0], ensure_ascii=False)
            self.assertIn("[合并转发不可用]", payload)
        self.store_group_forward("1203", nodes=[node_raw(audios=(audio_bytes(),), videos=(video_bytes(),))])
        baseline_sources = self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0]
        baseline_inputs = self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0]
        baseline_calls = len(self.native.provider.client.state.calls)
        connection = self.native.platform.client._wsr_api_clients["100"]
        async def changed(locator):
            captured = await load_native_audio(locator)
            self.native.platform.client._wsr_api_clients["100"] = object()
            return captured
        bridge.forward_loader = partial(read_group_forwards, reverse_api_type=type(self.api),
            image_loader=load_native_image, audio_loader=changed, video_loader=load_native_video)
        try:
            result = await self.controller.receive_claimed(self.forward_event("1203"))
        finally:
            self.native.platform.client._wsr_api_clients["100"] = connection
        self.assertEqual(result.failure.code, "host_forward_account_changed")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], baseline_sources)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], baseline_inputs)
        self.assertEqual(len(self.native.provider.client.state.calls), baseline_calls)

    async def test_group_forward_node_budget_rejects_before_loading_images_or_publishing(self):
        await self.start_host()
        nodes = [node_raw("超出节点上限", sender="999", images=(image_bytes(),))
                 for _ in range(MAX_NODES + 1)]
        self.store_group_forward("1201", nodes=nodes)
        with patch("companion_v2.adapters.astrbot.group_forwards.capture_forward_cards",
                   new=AsyncMock(side_effect=AssertionError("over-budget nodes must fail before image loading"))) as capture:
            result = await self.controller.receive_claimed(self.forward_event())

        self.assertFalse(result.is_success)
        self.assertEqual(result.failure.code, "host_forward_limit")
        capture.assert_not_awaited()
        for table in ("conversation_inputs", "conversation_image_payloads", "sources", "assets"):
            self.assertEqual(self.app.runtime.read_one(f"SELECT COUNT(*) FROM {table}", ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_group_forward_connection_replacement_during_read_rejects_without_intake(self):
        await self.start_host()
        self.store_group_forward("1201", nodes=[node_raw("连接替换", sender="999")])
        event = self.forward_event()
        clients = event.bot._wsr_api_clients
        original_connection = clients["100"]
        original_action = self.api.call_action

        async def replace_after_read(action, **params):
            result = await original_action(action, **params)
            clients["100"] = object()
            return result

        self.api.call_action = replace_after_read
        result = await self.controller.receive_claimed(event)
        clients["100"] = original_connection

        self.assertFalse(result.is_success)
        self.assertEqual(result.failure.code, "host_forward_account_changed")
        for table in ("conversation_inputs", "conversation_image_payloads", "sources", "assets"):
            self.assertEqual(self.app.runtime.read_one(f"SELECT COUNT(*) FROM {table}", ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_group_forward_read_errors_keep_only_the_original_text_and_host_recovers(self):
        await self.start_host()
        original_action = self.api.call_action
        cases = (asyncio.TimeoutError("sensitive timeout detail"), RuntimeError("sensitive transport detail"))

        for index, error in enumerate(cases):
            failed_id = str(1201 + index * 2)
            recovered_id = str(1202 + index * 2)
            self.store_group_forward(failed_id, nodes=[node_raw("暂时不可用", sender="999")])
            self.store_group_forward(recovered_id, nodes=[node_raw("恢复后的记录", sender="999")])
            baseline_inputs = self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0]

            async def fail_read(*_, _error=error, **__):
                raise _error

            self.api.call_action = fail_read
            failed = await self.controller.receive_claimed(self.forward_event(failed_id))
            self.assertTrue(failed.is_success, failed.failure)
            batch = failed.unwrap()
            await wait_for_batch(self.controller.session, batch)
            context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
            captured = self.input(context, batch)
            self.assertEqual(type(captured).__name__, "InboundConversationEvent")
            self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0],
                             baseline_inputs + 1)
            request = self.request(context, batch)
            material_text = "".join(item.payload for item in request.context.materials)
            wire_text = json.dumps(self.native.provider.client.state.calls[-1][0], ensure_ascii=False)
            self.assertNotIn(str(error), material_text)
            self.assertNotIn("暂时不可用", material_text)
            self.assertNotIn(str(error), wire_text)
            self.assertNotIn("暂时不可用", wire_text)
            self.assertIn("[合并转发不可用]", wire_text)

            self.api.call_action = original_action
            recovered = await self.controller.receive_claimed(self.forward_event(recovered_id))
            self.assertTrue(recovered.is_success, recovered.failure)
            await wait_for_batch(self.controller.session, recovered.unwrap())

        self.api.call_action = original_action

    async def test_optional_read_failure_cannot_adopt_a_replaced_account_connection(self):
        await self.start_host()
        original_action = self.api.call_action
        clients = self.native.platform.client._wsr_api_clients
        connection = clients["100"]
        for index, error in enumerate((asyncio.TimeoutError(), RuntimeError("lost transport"))):
            identifier = str(1601 + index)
            self.store_group_forward(identifier)

            async def changed_then_failed(*_, _error=error, **__):
                clients["100"] = object()
                raise _error

            self.api.call_action = changed_then_failed
            try:
                result = await self.controller.receive_claimed(self.forward_event(identifier))
            finally:
                clients["100"] = connection
                self.api.call_action = original_action
            self.assertFalse(result.is_success)
            self.assertEqual(result.failure.code, "host_client_mismatch")
            for table in ("conversation_inputs", "conversation_image_payloads", "sources", "assets"):
                self.assertEqual(self.app.runtime.read_one(f"SELECT COUNT(*) FROM {table}", ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])


if __name__ == "__main__":
    unittest.main()
