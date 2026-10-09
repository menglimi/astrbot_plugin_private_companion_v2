"""Group-pinned quote reads freeze all media and share the outer input budget."""

from functools import partial
import unittest
from unittest.mock import AsyncMock

from astrbot_host.audio.loader import load_native_audio
from astrbot_host.media import load_native_image
from astrbot_host.video.loader import load_native_video
from companion_v2.adapters.astrbot.group_quotes import read_group_quote
from companion_v2.execution.models import TaskContext
import json
from tests.animation_support import animation_bytes
from tests.audio_support import audio_bytes
from tests.forward_support import node_raw
from tests.group_quote_media_support import GroupQuoteMediaFixture, Forward, Reply, FakeRecord, FakeVideo
from tests.group_media_support import Plain, sdk_image
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_conversation_images import image_bytes
from tests.video_support import video_bytes


def current_request_text(wire):
    message = next(item for item in wire["messages"] if item["role"] == "user")
    materials = json.loads(message["content"])["materials"]
    return "\n".join(item["text"] for item in materials
                     if item["content_class"] == "current_user_request")


class AstrBotGroupQuoteMediaTests(GroupQuoteMediaFixture, unittest.IsolatedAsyncioTestCase):
    async def test_quote_freezes_direct_and_nested_media_before_the_first_download(self):
        await self.start_host()
        parts = [sdk_image(), FakeRecord(), FakeVideo(), Forward(id="group-quoted-forward")]
        self.store(parts=parts, nodes=[node_raw("原节点", sender="999", audios=(audio_bytes(value=2000),))])
        raw = self.records["345"]
        async def history(*_, **__):
            return {"messages": [raw]}
        async def mutate(locator):
            raw.update(sender={"user_id": 777}, user_id=777, group_id=999)
            raw["message"][1]["data"]["file"] = FakeRecord(audio_bytes(value=3000)).file
            node = raw["message"][3]["data"]["content"][0]
            node["sender"]["user_id"] = "555"
            node["message"][0]["data"]["text"] = "等待中篡改"
            node["message"][1]["data"]["file"] = FakeRecord().file
            return await load_native_image(locator)
        self.api.call_action = history
        self.controller.session.bridge.groups.quote_loader = partial(read_group_quote,
            reverse_api_type=type(self.api), image_loader=mutate,
            audio_loader=load_native_audio, video_loader=load_native_video)
        captured = (await self.controller.session.bridge.capture(self.media_event([Reply(id="345")]))).unwrap()
        quote = captured.quotes[0]
        self.assertEqual(quote.sender_id, "201")
        self.assertEqual(quote.audios[0].content, audio_bytes())
        self.assertEqual(quote.videos[0].content, video_bytes())
        node = quote.forwards[0].nodes[0]
        self.assertEqual(node.sender_id, "999")
        self.assertTrue(node.text.startswith("原节点"))
        self.assertEqual(node.audios[0].content, audio_bytes(value=2000))

    async def test_wrong_group_account_or_message_rejects_before_any_download(self):
        await self.start_host()
        loader = AsyncMock(side_effect=AssertionError("verify the original route first"))
        self.controller.session.bridge.groups.quote_loader = partial(read_group_quote,
            reverse_api_type=type(self.api), image_loader=loader, audio_loader=loader, video_loader=loader)
        for change in ({"group_id": 301}, {"self_id": 101}, {"message_id": 346}, {"user_id": 999},
                       {"message_type": "private"}, {"anonymous": {"id": 1}}):
            with self.subTest(change=change):
                self.store()
                self.records["345"].update(change)
                result = await self.controller.receive_claimed(self.media_event([Reply(id="345")], sender="777"))
                self.assertEqual(result.failure.code, "host_quote_scope_mismatch")
        loader.assert_not_awaited()
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], 0)

    async def test_missing_quote_media_needs_user_text_before_fallback(self):
        await self.start_host()
        loader = AsyncMock(side_effect=AssertionError("freeze and validate before downloading"))
        bridge = self.controller.session.bridge.groups
        bridge.quote_loader = partial(read_group_quote, reverse_api_type=type(self.api), image_loader=loader)
        for media in (FakeRecord(), FakeVideo()):
            self.store(parts=[sdk_image(), media])
            before_inputs = self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0]
            before_calls = len(self.native.provider.client.state.calls)
            result = await self.controller.receive_claimed(self.media_event([Reply(id="345")]))
            self.assertFalse(result.is_success)
            self.assertEqual(result.failure.code, "host_quote_unsupported")
            self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], before_inputs)
            self.assertEqual(len(self.native.provider.client.state.calls), before_calls)

            result = await self.controller.receive_claimed(
                self.media_event([Reply(id="345"), Plain("这条引用的附件无法读取，请按现有文字回答")]))
            self.assertTrue(result.is_success, result.failure)
            batch = result.unwrap()
            await wait_for_batch(self.controller.session, batch)
            context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
            captured = self.input(context, batch)
            self.assertEqual(type(captured).__name__, "InboundConversationEvent")
            current_text = current_request_text(self.native.provider.client.state.calls[-1][0])
            self.assertIn("[引用消息不可用]", current_text)
            self.assertIn("这条引用的附件无法读取", current_text)
        self.store(parts=[sdk_image(), Forward(id="group-quoted-forward")], nodes=[node_raw()])
        self.records["345"]["message"][1]["data"]["content"][0]["message"].append({"type": "reply", "data": {"id": "100"}})
        result = await self.controller.receive_claimed(
            self.media_event([Reply(id="345"), Plain("请基于可见上下文回应这条转发")]))
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        captured = self.input(context, batch)
        self.assertEqual(type(captured).__name__, "InboundConversationEvent")
        current_text = current_request_text(self.native.provider.client.state.calls[-1][0])
        self.assertIn("[引用消息不可用]", current_text)
        self.assertIn("请基于可见上下文回应这条转发", current_text)
        loader.assert_not_awaited()

    async def test_connection_replacement_during_direct_or_node_media_stops_capture(self):
        await self.start_host()
        connection = self.api._api_clients["100"]
        for nested in (False, True):
            for kind, part, body, native in (("audio", FakeRecord(), audio_bytes(), load_native_audio),
                                               ("video", FakeVideo(), video_bytes(), load_native_video)):
                with self.subTest(nested=nested, kind=kind):
                    self.api._api_clients["100"] = connection
                    calls = []
                    async def changed(locator):
                        calls.append(locator)
                        self.api._api_clients["100"] = object()
                        return await native(locator)
                    self.controller.session.bridge.groups.quote_loader = partial(read_group_quote,
                        reverse_api_type=type(self.api), image_loader=load_native_image,
                        audio_loader=changed if kind == "audio" else load_native_audio,
                        video_loader=changed if kind == "video" else load_native_video)
                    parts = [Forward(id="group-quoted-forward")] if nested else [part, part]
                    self.store(parts=parts, nodes=[node_raw(**{kind + "s": (body, body)})] if nested else None)
                    result = await self.controller.receive_claimed(self.media_event([Reply(id="345")]))
                    self.assertEqual(result.failure.code, "host_quote_account_changed")
                    self.assertEqual(len(calls), 1)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], 0)

    async def test_direct_and_quoted_forwards_share_card_node_and_text_budgets(self):
        await self.start_host()
        for nodes, cards in (([node_raw()], 4), ([node_raw()] * 20, 1), ([node_raw("x" * 33000)], 1)):
            with self.subTest(cards=cards, nodes=len(nodes)):
                self.store(parts=[Forward(id="group-quoted-forward")] * cards, nodes=nodes)
                self.store("678", sender="200", parts=[Forward(id="group-quoted-forward"), Reply(id="345")], nodes=nodes)
                result = await self.controller.receive_claimed(self.media_event(
                    [Forward(id="group-quoted-forward"), Reply(id="345")], identifier="678"))
                self.assertEqual(result.failure.code, "host_forward_limit")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], 0)

    async def test_direct_quote_and_forward_media_share_images_frames_and_audio_video_budgets(self):
        await self.start_host()
        cases = (
            (node_raw(images=(image_bytes(),) * 7),
             [sdk_image(), sdk_image()], "host_group_media_limit"),
            (node_raw(videos=(video_bytes(),) * 2), [sdk_image(animation_bytes(count=10)) for _ in range(3)], "host_group_media_limit"),
            (node_raw(audios=(audio_bytes(),) * 4), [FakeRecord()], "host_group_media_limit"),
            (node_raw(videos=(video_bytes(),) * 2), [FakeVideo()], "host_group_media_limit"),
        )
        for node, direct, code in cases:
            with self.subTest(code=code, direct=len(direct)):
                self.store(parts=[Forward(id="group-quoted-forward")], nodes=[node])
                result = await self.controller.receive_claimed(self.media_event([Reply(id="345"), *direct]))
                self.assertEqual(result.failure.code, code)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], 0)
