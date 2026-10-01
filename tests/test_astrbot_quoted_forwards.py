"""One peer-pinned quote read freezes expanded forwards before attachment awaits."""

from copy import deepcopy
from functools import partial
import unittest
from unittest.mock import AsyncMock

from astrbot_host.media import load_native_image
from companion_v2.adapters.astrbot.quotes import read_private_quote
from companion_v2.conversation.quotes.forward_models import CapturedForwardQuote
from tests.animation_support import animation_bytes
from tests.forward_support import ForwardFixture, node_raw, quoted_forward_raw
from tests.native_adapter_support import FakeReverseApi
from tests.test_conversation_images import FakeImage, image_bytes
from tests.test_conversation_quotes import FakeReply


class AstrBotQuotedForwardTests(ForwardFixture, unittest.IsolatedAsyncioTestCase):
    async def test_one_pinned_read_retains_both_senders_and_ignores_reply_chain(self):
        for sender in ("100", "200"):
            with self.subTest(sender=sender):
                self.raw = quoted_forward_raw(sender=sender, nodes=[node_raw(sender="999")])
                self.api.calls.clear()
                quote = (await self.capture(self.quote_event())).quotes[0]
                self.assertIsInstance(quote, CapturedForwardQuote)
                self.assertEqual((quote.sender_id, quote.sent_at), (sender, 1700000000))
                self.assertEqual(quote.forwards[0].nodes[0].sender_id, "999")
                self.assertNotIn("forged", quote.text)
                self.assertEqual(self.api.calls, [("get_friend_msg_history", {
                    "self_id": "100", "user_id": "200", "message_seq": "345", "count": 1,
                    "reverse_order": False, "parse_mult_msg": True})])

    async def test_same_resource_cards_keep_independent_content_and_native_positions(self):
        self.raw = quoted_forward_raw(cards=2, direct=True)
        self.raw["message"][2]["data"]["content"] = [node_raw("另一张卡片")]
        quote = (await self.capture(self.quote_event())).quotes[0]
        self.assertEqual([f.position for f in quote.forwards], [1, 2])
        self.assertEqual([f.nodes[0].text.splitlines()[0] for f in quote.forwards], ["记录中的一句话", "另一张卡片"])
        self.assertEqual(quote.images[0].descriptor.position, 0)
        self.assertEqual(len(self.api.calls), 1)

    async def test_unsupported_tree_fails_before_even_the_outer_image_download(self):
        loader = AsyncMock(side_effect=AssertionError("freeze every node first"))
        self.bridge.quote_loader = partial(read_private_quote, reverse_api_type=FakeReverseApi, image_loader=loader)
        for kind in ("reply", "record", "video", "forward"):
            with self.subTest(kind=kind):
                self.raw = quoted_forward_raw(direct=True)
                self.raw["message"][1]["data"]["content"][1]["message"].append({"type": kind, "data": {"id": "345"}})
                result = await self.bridge.capture(self.quote_event())
                self.assertEqual(result.failure.code, "host_forward_unsupported")
        self.raw = quoted_forward_raw(direct=True)
        del self.raw["message"][1]["data"]["content"]
        self.assertEqual((await self.bridge.capture(self.quote_event())).failure.code, "host_forward_unsupported")
        loader.assert_not_awaited()

    async def test_returned_tree_and_direct_image_locators_are_frozen_together(self):
        raw = quoted_forward_raw(direct=True, nodes=[node_raw(images=(image_bytes("green"),))])
        async def dispatch(*_, **__):
            return {"messages": [raw]}
        self.api.call_action = dispatch
        async def mutate(locator):
            raw["sender"]["user_id"] = 999
            node = raw["message"][1]["data"]["content"][0]
            node["sender"]["user_id"] = "888"
            node["message"][0]["data"]["text"] = "等待中改写"
            node["message"][1]["data"]["file"] = FakeImage(image_bytes("blue")).file
            return await load_native_image(locator)
        self.bridge.quote_loader = partial(read_private_quote, reverse_api_type=FakeReverseApi, image_loader=mutate)
        quote = (await self.capture(self.quote_event())).quotes[0]
        node = quote.forwards[0].nodes[0]
        self.assertEqual((quote.sender_id, node.sender_id), ("100", "300"))
        self.assertTrue(node.text.startswith("记录中的一句话"))
        self.assertEqual(node.images[0].content, image_bytes("green"))

    async def test_connection_replacement_during_node_image_stops_remaining_downloads(self):
        self.raw = quoted_forward_raw(nodes=[node_raw(images=(image_bytes(), image_bytes("green")))])
        downloads = []
        async def replace_connection(locator):
            downloads.append(locator)
            self.api._api_clients["100"] = object()
            return await load_native_image(locator)
        self.bridge.quote_loader = partial(read_private_quote, reverse_api_type=FakeReverseApi, image_loader=replace_connection)
        self.assertEqual((await self.bridge.capture(self.quote_event())).failure.code, "host_quote_account_changed")
        self.assertEqual(len(downloads), 1)

    async def test_role_change_during_nested_image_cannot_admit_quote(self):
        self.raw = quoted_forward_raw()
        async def change_role(locator):
            self.native.cid = "changed-during-quoted-forward"
            return await load_native_image(locator)
        self.bridge.quote_loader = partial(read_private_quote, reverse_api_type=FakeReverseApi, image_loader=change_role)
        self.assertEqual((await self.bridge.capture(self.quote_event())).failure.code, "host_persona_changed")

    async def test_direct_and_quoted_forwards_share_cards_nodes_and_text_limits(self):
        for nodes, cards in (([node_raw()], 4), ([node_raw()] * 20, 1), ([node_raw("x" * 33000)], 1)):
            with self.subTest(cards=cards, nodes=len(nodes)):
                self.raw = quoted_forward_raw(nodes=nodes, cards=cards)
                self.forward_raw = {"messages": deepcopy(nodes)}
                event = self.forward_event()
                event.message_obj.message.append(FakeReply())
                self.assertEqual((await self.bridge.capture(event)).failure.code, "host_forward_limit")

    async def test_direct_quoted_and_forwarded_images_share_original_and_frame_limits(self):
        for images in ((image_bytes(),) * 7, (animation_bytes(count=10),) * 4):
            self.raw = quoted_forward_raw(nodes=[node_raw(images=images)])
            event = self.quote_event(direct=True)
            event.message_obj.message.append(FakeImage())
            self.assertEqual((await self.bridge.capture(event)).failure.code, "host_image_limit")

    async def test_quote_direct_images_share_budget_with_its_forward_frames(self):
        self.raw = quoted_forward_raw(direct=True, nodes=[node_raw(images=(animation_bytes(count=10),) * 4)])
        self.assertEqual((await self.bridge.capture(self.quote_event())).failure.code, "host_forward_limit")

    async def test_invalid_outer_identity_rejects_before_forward_images(self):
        loader = AsyncMock(side_effect=AssertionError("original identity must pass before any download"))
        self.bridge.quote_loader = partial(read_private_quote, reverse_api_type=FakeReverseApi, image_loader=loader)
        for change in ({"self_id": 101}, {"message_id": 999}, {"sender": {"user_id": 888}}, {"group_id": 999}):
            self.raw = {**quoted_forward_raw(), **change}
            self.assertEqual((await self.bridge.capture(self.quote_event())).failure.code, "host_quote_scope_mismatch")
        loader.assert_not_awaited()
