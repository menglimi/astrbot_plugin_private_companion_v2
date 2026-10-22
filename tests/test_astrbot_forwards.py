"""Bounded forward reads, native account fences and immutable nested snapshots."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from functools import partial
import unittest
from unittest.mock import AsyncMock

from astrbot_host.media import load_native_image
from companion_v2.adapters.astrbot.forwards import read_private_forwards
from companion_v2.conversation.forwards.models import MAX_NODES, MAX_DEPTH, ForwardIntakePolicy
from tests.animation_support import animation_bytes
from tests.forward_support import FakeForward, ForwardFixture, node_raw, outer_raw
from tests.native_adapter_support import FakeReverseApi
from tests.test_conversation_images import FakeImage, image_bytes
from tests.test_conversation_quotes import FakeReply


class AstrBotForwardTests(ForwardFixture, unittest.IsolatedAsyncioTestCase):
    async def test_legacy_node_limit_is_preserved_through_capture_and_saved_descriptors(self):
        self.bridge.forward_intake = ForwardIntakePolicy(max_nodes=300)
        self.forward_raw = {"messages": [node_raw(f"第 {index} 条") for index in range(300)]}
        captured = await self.capture(self.forward_event())
        self.assertEqual(len(captured.forwards[0].nodes), 300)
        self.assertEqual(captured.forwards[0].nodes[-1].path, (299,))
        host = await self.quiet_host()
        batch = host.receive(captured).unwrap()
        event = self.original(host.application, batch)
        self.assertEqual(len(event.forwards[0].nodes), 300)
        self.assertEqual(event.forwards[0].nodes[-1].path, (299,))

    async def test_disabling_nested_parsing_retains_outer_content_without_child_media(self):
        self.bridge.forward_intake = ForwardIntakePolicy(parse_nested=False)
        loader = AsyncMock(side_effect=AssertionError("disabled children must not download media"))
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi,
                                             image_loader=loader)
        self.forward_raw = {"messages": [node_raw("外层", nested=[node_raw("内部", images=(image_bytes(),))])]}
        captured = await self.capture(self.forward_event())
        self.assertEqual(len(captured.forwards[0].nodes), 1)
        self.assertIn("嵌套转发未展开", captured.forwards[0].nodes[0].text)
        self.assertNotIn("内部", captured.forwards[0].nodes[0].text)
        loader.assert_not_awaited()

    async def test_only_pinned_forward_read_and_no_inline_content_or_node_identity_trust(self):
        self.forward_raw = {"messages": [node_raw(sender="200"), node_raw(sender="100", name="我是当前人格", at=None)]}
        captured = await self.capture(self.forward_event())
        self.assertEqual(self.api.calls, [("get_friend_msg_history", {"self_id": "100", "user_id": "200",
            "message_seq": "678", "count": 1, "reverse_order": False, "parse_mult_msg": True})])
        self.assertEqual([n.sender_id for n in captured.forwards[0].nodes], ["200", "100"])
        self.assertIsNone(captured.forwards[0].nodes[1].sent_at)
        self.assertNotIn("记录中的一句话", captured.text)
        self.assertNotIn("inline content", str(captured))

    async def test_peer_history_response_wrappers_are_normalized_without_widening_scope(self):
        for index, wrapper in enumerate(("direct", "data_messages", "data_list", "list")):
            event_id = str(678 + index)
            raw = outer_raw(event_id)
            if wrapper == "direct":
                response = {"messages": [raw]}
            elif wrapper == "data_messages":
                response = {"status": "ok", "retcode": 0, "data": {"messages": [raw]}}
            elif wrapper == "data_list":
                response = {"data": [raw]}
            else:
                response = [raw]

            async def dispatch(*_, response=response, **__):
                return response

            self.api.call_action = dispatch
            captured = await self.capture(self.forward_event(event_id))
            self.assertTrue(captured.forwards[0].nodes[0].text.startswith("记录中的一句话"), wrapper)

        async def ambiguous(*_, **__):
            raw = outer_raw()
            return {"messages": [raw], "data": {"messages": [raw]}}

        self.api.call_action = ambiguous
        result = await self.bridge.capture(self.forward_event())
        self.assertEqual(result.failure.code, "host_forward_unavailable")

    async def test_outer_history_must_match_account_peer_scene_and_exact_message(self):
        changes = (
            lambda raw: raw.update(self_id=101),
            lambda raw: raw.update(message_id=679),
            lambda raw: raw.update(message_id="--679"),
            lambda raw: raw.update(message_type="group", group_id=900),
            lambda raw: raw.update(sender={"user_id": 300}),
            lambda raw: raw.update(user_id=300),
            lambda raw: raw.update(sub_type="group"),
        )
        for change in changes:
            raw = outer_raw()
            change(raw)
            async def dispatch(*_, **__):
                return {"messages": [raw]}
            self.api.call_action = dispatch
            result = await self.bridge.capture(self.forward_event())
            self.assertEqual(result.failure.code, "host_forward_scope_mismatch")

    async def test_non_numeric_outer_message_id_is_a_forward_input_error(self):
        for identifier in ("outer-message-id", "--678", "+678", "0678", "0", str(2**63)):
            with self.subTest(identifier=identifier):
                result = await self.bridge.capture(self.forward_event(identifier))
                self.assertEqual(result.failure.code, "host_forward_invalid")
        self.assertEqual(self.api.calls, [])

    async def test_forward_history_timeout_is_single_attempt_without_fallback(self):
        async def timeout(action, **params):
            self.api.calls.append((action, params))
            raise asyncio.TimeoutError("synthetic private transport details")
        self.api.call_action = timeout
        result = await self.bridge.capture(self.forward_event())
        self.assertEqual(result.failure.code, "host_forward_timeout")
        self.assertNotIn("private transport details", result.failure.reason)
        self.assertEqual([action for action, _ in self.api.calls], ["get_friend_msg_history"])

    async def test_outer_history_cannot_drop_add_or_replace_forward_components(self):
        for cards in ([], [None], [{"type": "forward", "data": {"id": "wrong", "content": [node_raw()]}}],
                      [{"type": "forward", "data": {"id": "forward-resource", "content": [node_raw()]}}] * 2):
            raw = outer_raw()
            raw["message"] = cards or [{"type": "text", "data": {"text": "missing"}}]
            async def dispatch(*_, **__):
                return {"messages": [raw]}
            self.api.call_action = dispatch
            result = await self.bridge.capture(self.forward_event())
            self.assertIn(result.failure.code, ("host_forward_scope_mismatch", "host_forward_unsupported"))

    async def test_nested_expanded_records_keep_preorder_and_static_animation_originals(self):
        body = animation_bytes()
        self.forward_raw = {"messages": [node_raw(images=(image_bytes(),), nested=[node_raw(images=(body,))]), node_raw("末尾") ]}
        captured = (await self.capture(self.forward_event())).forwards[0]
        self.assertEqual([n.path for n in captured.nodes], [(0,), (0, 2, 0), (1,)])
        self.assertEqual(captured.nodes[1].images[0].content, body)
        self.assertEqual(len(captured.nodes[1].images[0].frames), 3)
        self.assertEqual(len(self.api.calls), 1)

    async def test_standard_content_nodes_and_inline_node_wrappers_are_supported(self):
        child = {"type": "node", "data": {"user_id": "500", "nickname": "显示名", "content": [{"type": "text", "data": {"text": "里面"}}]}}
        self.forward_raw = {"messages": [{"sender": {}, "content": [child]}]}
        nodes = (await self.capture(self.forward_event())).forwards[0].nodes
        self.assertEqual([n.path for n in nodes], [(0,), (0, 0, 0)])
        self.assertIsNone(nodes[0].sender_id)
        self.assertEqual(nodes[1].sender_id, "500")

    async def test_same_resource_id_can_identify_distinct_cards_in_one_outer_message(self):
        event = self.forward_event()
        event.message_obj.message.append(FakeForward())
        async def dispatch(action, **params):
            self.api.calls.append((action, params))
            cards = [{"type": "forward", "data": {"id": "forward-resource", "content": [node_raw(text)]}}
                     for text in ("第一份", "第二份")]
            return {"messages": [outer_raw(cards=cards)]}
        self.api.call_action = dispatch
        captured = await self.capture(event)
        self.assertEqual([f.position for f in captured.forwards], [1, 2])
        self.assertEqual([f.nodes[0].text for f in captured.forwards], ["第一份", "第二份"])
        self.assertEqual(len(self.api.calls), 1)

    async def test_unsupported_or_unexpanded_parts_never_become_partial_records(self):
        loader = AsyncMock(side_effect=AssertionError("unsupported trees must fail before image preparation"))
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=loader)
        for kind in ("reply", "record", "video", "forward"):
            self.api.calls.clear()
            self.forward_raw = {"messages": [node_raw(images=(image_bytes(),))]}
            self.forward_raw["messages"][0]["message"].append({"type": kind, "data": {"id": "inner"}})
            result = await self.bridge.capture(self.forward_event())
            self.assertEqual(result.failure.code, "host_forward_unsupported", kind)
            self.assertEqual([action for action, _ in self.api.calls], ["get_friend_msg_history"])
        loader.assert_not_awaited()

    async def test_non_node_wrappers_cannot_masquerade_as_expanded_nodes(self):
        loader = AsyncMock(side_effect=AssertionError("malformed trees must fail before image preparation"))
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=loader)
        for kind in ("reply", "video", "forward", None):
            for nested in (False, True):
                with self.subTest(kind=kind, nested=nested):
                    malformed = {**node_raw(images=(image_bytes(),)), "type": kind}
                    self.forward_raw = {"messages": [node_raw(nested=[malformed]) if nested else malformed]}
                    result = await self.bridge.capture(self.forward_event())
                    self.assertEqual(result.failure.code, "host_forward_unsupported")
        loader.assert_not_awaited()

    async def test_node_depth_and_text_budgets_are_enforced_before_image_loading(self):
        calls = []
        async def loader(locator):
            calls.append(locator)
            return await load_native_image(locator)
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=loader)
        cases = [{"messages": [node_raw()] * (MAX_NODES + 1)}, {"messages": [node_raw("x" * 65537)]}]
        nested = [node_raw()]
        for _ in range(MAX_DEPTH):
            nested = [node_raw(nested=nested)]
        cases.append({"messages": nested})
        for raw in cases:
            self.forward_raw = raw
            result = await self.bridge.capture(self.forward_event())
            self.assertEqual(result.failure.code, "host_forward_limit")
        self.assertEqual(calls, [])

    async def test_display_name_and_ambiguous_arrays_cannot_hide_other_content(self):
        raw = node_raw()
        raw["content"] = [{"type": "text", "data": {"text": "另一份正文"}}]
        for node in (raw, node_raw(name="x" * 257)):
            self.forward_raw = {"messages": [node]}
            self.assertFalse((await self.bridge.capture(self.forward_event())).is_success)

    async def test_direct_quoted_and_forwarded_images_share_one_budget(self):
        self.forward_raw = {"messages": [node_raw(images=(animation_bytes(count=10),) * 4)]}
        event = self.forward_event()
        event.message_obj.message.extend([FakeReply(), FakeImage()])
        result = await self.bridge.capture(event)
        self.assertEqual(result.failure.code, "host_image_limit")

    async def test_tree_is_frozen_before_first_image_await(self):
        raw = {"messages": [outer_raw(content=deepcopy(self.forward_raw["messages"]))]}
        async def dispatch(*_, **__):
            return raw
        self.api.call_action = dispatch
        async def mutate(locator):
            node = raw["messages"][0]["message"][0]["data"]["content"][1]
            node["message"][0]["data"]["text"] = "后改的正文"
            node["sender"]["user_id"] = "999"
            return await load_native_image(locator)
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=mutate)
        nodes = (await self.capture(self.forward_event())).forwards[0].nodes
        self.assertEqual((nodes[1].text, nodes[1].sender_id), ("第二位说话者", "400"))

    async def test_native_resource_is_frozen_before_role_lookup(self):
        event = self.forward_event()
        async def mutate(_):
            event.message_obj.message[1].id = "changed-resource"
        self.native.before_resolve = mutate
        await self.capture(event)
        self.assertEqual(self.api.calls[0][1]["message_seq"], "678")

    async def test_connection_change_during_read_or_image_prepare_rejects_snapshot(self):
        original = self.api.call_action
        async def changed(action, **params):
            result = await original(action, **params)
            self.native.platform.client._wsr_api_clients["100"] = object()
            return result
        self.api.call_action = changed
        self.assertEqual((await self.bridge.capture(self.forward_event())).failure.code, "host_forward_account_changed")
        self.api.call_action = original
        async def loader(locator):
            image = await load_native_image(locator)
            self.native.platform.client._wsr_api_clients["100"] = object()
            return image
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=loader)
        self.assertEqual((await self.bridge.capture(self.forward_event())).failure.code, "host_forward_account_changed")

    async def test_role_change_during_forward_read_rejects_snapshot(self):
        original = self.api.call_action
        async def changed(action, **params):
            result = await original(action, **params)
            self.native.persona["prompt"] += "changed"
            return result
        self.api.call_action = changed
        self.assertEqual((await self.bridge.capture(self.forward_event())).failure.code, "host_persona_changed")

    async def test_loader_must_return_the_original_forward_resource(self):
        original = self.bridge.forward_loader
        async def changed(*args, **kwargs):
            result = await original(*args, **kwargs)
            return (replace(result[0], position=2),)
        self.bridge.forward_loader = changed
        self.assertEqual((await self.bridge.capture(self.forward_event())).failure.code, "host_forward_invalid")

    async def test_cancellation_does_not_return_a_partial_capture(self):
        entered = asyncio.Event()
        async def hold(*_, **__):
            entered.set()
            await asyncio.Event().wait()
        self.api.call_action = hold
        pending = asyncio.create_task(self.bridge.capture(self.forward_event()))
        await asyncio.wait_for(entered.wait(), 2)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
