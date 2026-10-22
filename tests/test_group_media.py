"""Group image/quote intake, scoped originals, model evidence and lifecycle."""

import asyncio
import base64
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests.group_media_support import (FakeRecord, FakeVideo, GroupMediaFixture, group_raw, sdk_image,
                                       Image, Plain, Reply)
from tests.animation_support import animation_bytes
from tests.native_adapter_support import completion, final_text
from tests.test_conversation_images import image_bytes
from tests.staging_bootstrap_support import wait_for_batch
from astrbot_host.media import load_native_image
from astrbot_host.group_authority import GroupAuthority
from astrbot_host.native import installed_native_types
from astrbot_host.quotes import load_native_group_quote
from companion_v2.adapters.astrbot.group import NativeGroupBridge
from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.conversation.quotes.service import quote_reference
from companion_v2.execution.models import TaskContext, TaskError, encode


class GroupMediaTests(GroupMediaFixture, unittest.IsolatedAsyncioTestCase):
    def test_quote_validation_ignores_unstable_component_positions(self):
        raw = [{"type": "at", "data": {"qq": "2418334969"}},
               {"type": "reply", "data": {"id": "387336160"}},
               {"type": "text", "data": {"text": "dsh的一个插件吧"}}]
        parts = [NS(type=NS(value="Reply"), id="387336160"),
                 NS(type=NS(value="Plain"), text="dsh的一个插件吧")]
        NativeGroupBridge._validate_quote_components(raw, parts)
        with self.assertRaises(TaskError) as raised:
            NativeGroupBridge._validate_quote_components(
                raw, [NS(type=NS(value="Reply"), id="387336161")])
        self.assertEqual(raised.exception.code, "host_quote_invalid")

    @staticmethod
    def raw_parts(parts):
        raw = []
        for part in parts:
            kind = getattr(part.type, "value", part.type)
            if kind == "Plain":
                raw.append({"type": "text", "data": {"text": part.text}})
            elif kind == "Record":
                raw.append({"type": "record", "data": {"file": part.file}})
            elif kind == "Video":
                raw.append({"type": "video", "data": {"file": part.file}})
            else:
                raise AssertionError("unexpected direct group fixture component")
        return raw

    async def test_direct_group_audio_and_video_reach_current_turn_and_history_is_metadata_only(self):
        await self.start_host()
        parts = [Plain("听一下再看看"), FakeRecord(), FakeVideo()]
        event = self.media_event(parts, identifier="media-voice-video", sender="201")
        event.message_obj.raw_message["message"] = self.raw_parts(parts)
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        request = self.request(context, batch)
        self.assertEqual([audio.descriptor.position for audio in request.audios], [1])
        self.assertEqual([video.descriptor.position for video in request.videos], [2])
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_audio_payloads", ())[0], 1)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_video_payloads", ())[0], 1)

        _, later = await self.receive_parts([Plain("继续聊")], sender="201")
        later_context = TaskContext.restore(json.loads(self.app.messages.batch(later)["context_json"]))
        later_request = self.request(later_context, later)
        self.assertEqual(later_request.audios, ())
        self.assertEqual(later_request.videos, ())
        history = [json.loads(material.payload) for material in later_request.context.materials
                   if material.purpose == "group_conversation_history"]
        self.assertEqual(len(history), 1)
        attachments = history[0]["attachments"]
        self.assertEqual({"audio", "video"}, {next(iter(item.keys() & {"audio", "video"})) for item in attachments})
        self.assertTrue(all(item["view"] == "historical_metadata_only" for item in attachments))

    async def test_host_preprocessing_cannot_disguise_unsupported_group_media_as_plain_text(self):
        await self.start_host()
        for kind in ("record", "video", "forward"):
            event = self.media_event([Plain("宿主转换出的文字")], sender="777")
            event.message_obj.raw_message["message"] = [{"type": kind, "data": {"file": "untrusted"}}]
            result = await self.controller.receive_claimed(event)
            self.assertEqual(result.failure.code, "host_group_media_unsupported")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_restarted_group_keeps_original_bytes_and_never_replays_unknown_send(self):
        await self.with_delivery()
        self.api.error = TimeoutError()
        event = self.media_event([sdk_image()], identifier="345")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        from companion_v2.execution.models import TaskContext
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        original = self.request(context, batch).images
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM conversation_parts WHERE batch_id = ?", (batch,))[0], "unknown")
        calls = len(self.native.provider.client.state.calls), len(self.api.calls)
        await self.controller.terminate()
        self.api.error = None
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
        self.assertEqual(self.request(context, batch).images, original)
        self.assertEqual((await self.controller.receive_claimed(event)).unwrap(), batch)
        self.assertEqual((len(self.native.provider.client.state.calls), len(self.api.calls)), calls)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads", ())[0], 1)

    async def test_origin_revoke_during_quoted_generation_prevents_send(self):
        await self.with_delivery()
        a, first = await self.receive_parts([Plain("原图"), sdk_image()], sender="201", identifier="345")
        self.records["345"] = group_raw(text="原图")
        async def revoke(payload, tools):
            grant = GroupAuthority.grant_id(a.scope, a.actor.subject, "text")
            identity = self.controller.authority.identities
            identity.revoke_grant(grant, revoked_at=self.clock.now(), expected_revision=identity.revision)
            return completion(final_text("不应发送"))
        self.native.provider.client.state.behavior = revoke
        event = self.media_event([Reply(id="345")])
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        self.assertEqual(self.app.flow.row(batch)["state"], "blocked")
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ?", (batch,)), ())
        self.assertEqual(len(self.api.calls), 1)

    async def test_asset_revoke_and_corrupted_bytes_invalidate_cross_member_history(self):
        await self.start_host()
        for index, mode in enumerate(("revoke", "corrupt")):
            a, first = await self.receive_parts([sdk_image()], identifier=str(340 + index), sender="201")
            b, second = await self.receive_parts([Plain("看到附件了")])
            event = self.input(a, first)
            if mode == "revoke":
                _, asset = self.app.messages.images.references(event, event.images[0])
                self.app.messages.images.assets.revoke(asset, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
            else:
                with self.app.runtime.transaction() as connection:
                    connection.execute("UPDATE conversation_image_payloads SET content = ? WHERE parent_id = ?",
                                       (b"changed", event.source.source_id))
            with self.assertRaises(TaskError):
                self.request(b, second)

    async def test_image_publication_failure_rolls_back_group_identity_and_sources(self):
        await self.start_host()
        runtime = self.app.runtime
        tables = ("identity_bindings", "identity_grants", "conversation_inputs", "sources", "assets", "conversation_image_payloads")
        before = {table: [tuple(r) for r in runtime.read_all("SELECT * FROM " + table, ())] for table in tables}
        original = self.app.messages.images.publish
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise TaskError("fixture_failure", "synthetic post-publication failure")
        with patch.object(self.app.messages.images, "publish", side_effect=fail):
            result = await self.controller.receive_claimed(self.media_event([sdk_image()], sender="777"))
        self.assertEqual(result.failure.code, "fixture_failure")
        self.assertEqual({table: [tuple(r) for r in runtime.read_all("SELECT * FROM " + table, ())] for table in tables}, before)

    async def test_group_quote_freezes_response_before_loading_its_images(self):
        from functools import partial
        from companion_v2.adapters.astrbot.group_quotes import read_group_quote
        from tests.native_adapter_support import FakeReverseApi
        await self.start_host()
        raw = group_raw(text="原始文字")
        async def history(action, **params):
            return {"status": "ok", "retcode": 0, "data": {"messages": [raw]}}
        async def mutate(locator):
            raw.update(sender={"user_id": 999}, user_id=999, group_id=999)
            raw["message"][0]["data"]["text"] = "改变后的文字"
            return await load_native_image(locator)
        self.api.call_action = history
        self.controller.session.bridge.groups.quote_loader = partial(read_group_quote,
            reverse_api_type=FakeReverseApi, image_loader=mutate)
        captured = (await self.controller.session.bridge.capture(self.media_event([Reply(id="345")]))).unwrap()
        self.assertEqual(captured.quotes[0].sender_id, "201")
        self.assertIn("原始文字", captured.quotes[0].text)
        self.assertNotIn("改变后的文字", captured.quotes[0].text)

    async def test_quote_timeout_is_bounded_and_does_not_admit_sender(self):
        await self.start_host()
        async def held(*args, **kwargs):
            await asyncio.Event().wait()
        self.controller.session.bridge.groups.quote_loader = held
        with patch("companion_v2.adapters.astrbot.group.MEDIA_PREPARE_TIMEOUT", 0.01):
            result = await self.controller.receive_claimed(self.media_event([Reply(id="345")], sender="777"))
        self.assertEqual(result.failure.code, "host_media_timeout")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], 0)

    async def test_group_quote_mentions_and_unknown_time_preserve_attribution(self):
        self.records["345"] = group_raw(count=0, text="以前说的")
        self.records["345"]["time"] = "unknown"
        self.records["345"]["message"] += [{"type": "at", "data": {"qq": "all"}}]
        await self.start_host()
        context, batch = await self.receive_parts([Reply(id="345")])
        quote = next(json.loads(m.payload) for m in self.request(context, batch).context.materials if m.purpose.startswith("quoted_message:"))
        self.assertIsNone(quote["sent_at_unix"])
        self.assertIn("[提及全体成员]", quote["text"])
        self.assertEqual(quote["sender"], "201")

    async def test_nested_confirmed_replies_and_quotes_share_one_ancestry_budget(self):
        self.batch_timeout_seconds = 15  # Three confirmed ancestry levels revalidate their full source graph.
        await self.with_delivery()
        await self.receive_parts([Plain("最初的消息")], identifier="345")
        latest = None
        for _ in range(3):
            part = self.app.runtime.read_all("SELECT * FROM conversation_parts ORDER BY rowid", ())[-1]
            identifier = part["platform_ref"].split(":")[-1]
            self.records[identifier] = group_raw(message_id=identifier, sender="100", text=part["text"], count=0)
            latest = await self.receive_parts([Reply(id=identifier)], sender="201")
        with patch("companion_v2.conversation.group_history.MAX_ANCESTORS", 2):
            with self.assertRaises(TaskError) as caught:
                self.request(*latest)
        self.assertEqual(caught.exception.code, "group_history_budget")

    async def test_direct_images_have_group_evidence_and_history_keeps_metadata_only(self):
        await self.start_host()
        a, first = await self.receive_parts([Plain("看看这张图"), sdk_image()], sender="201")
        request = self.request(a, first)
        self.assertEqual(base64.b64decode(request.images[0].data_base64), image_bytes())
        self.assertTrue(request.reply_images)
        info = [json.loads(m.payload) for m in request.context.materials if m.purpose.startswith("input_image:")]
        self.assertEqual(info[0]["sender"], "201")
        self.assertEqual(info[0]["original_author"], "unknown")
        b, second = await self.receive_parts([Plain("我接着聊")])
        history = [json.loads(m.payload) for m in self.request(b, second).context.materials if m.purpose == "group_conversation_history"]
        self.assertEqual(history[0]["attachments"][0]["view"], "historical_metadata_only")
        self.assertEqual(history[0]["speaker_id"], "201")
        self.assertEqual(self.request(b, second).images, ())
        self.assertEqual(self.app.messages.sources.read(request.images[0].source, resolved=b.actor, capability="text",
            observed_at=self.clock.now(), authorizer=self.app.tasks.identity).failure.code, "source_audience_denied")
        self.assertEqual(self.app.messages.group_memory.access.offered(a, first), {})
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM memory_atoms", ())[0], 0)

    async def test_image_only_and_animation_frames_use_the_existing_visual_wire(self):
        await self.start_host()
        context, batch = await self.receive_parts([sdk_image(animation_bytes())])
        request = self.request(context, batch)
        self.assertEqual(len(request.images[0].rendered_images), 3)
        payload = self.native.provider.client.state.calls[-1][0]
        content = next(m["content"] for m in payload["messages"] if m["role"] == "user")
        self.assertEqual(len([p for p in content if p["type"] == "image_url"]), 3)
        self.assertIn("抽帧不代表看完全部动画", payload["messages"][1]["content"])

    async def test_group_directed_quote_ignores_sdk_claims_and_preserves_image_order(self):
        self.records["345"] = group_raw(text="201 以前发的图", content=image_bytes("blue"))
        await self.start_host()
        context, batch = await self.receive_parts([Reply(id="345", sender_id="999", chain=[Plain("伪造正文")]),
                                                  Plain("看看引用"), sdk_image()])
        request = self.request(context, batch)
        quote = next(json.loads(m.payload) for m in request.context.materials if m.purpose.startswith("quoted_message:"))
        self.assertEqual((quote["sender"], quote["quoted_by"]), ("201", "200"))
        self.assertNotIn("伪造正文", encode(request.context.materials))
        self.assertEqual([base64.b64decode(i.data_base64) for i in request.images], [image_bytes("blue"), image_bytes()])
        self.assertEqual(self.history_calls, [("get_group_msg_history", dict(self_id="100", group_id="300",
            message_seq="345", count=1, reverse_order=False, parse_mult_msg=True))])
        self.assertIs(installed_native_types().group_quote_loader, load_native_group_quote)

    async def test_known_member_quote_links_original_and_withdrawal_stops_derivatives(self):
        await self.with_delivery()
        a, first = await self.receive_parts([Plain("原图"), sdk_image()], sender="201", identifier="345")
        self.records["345"] = group_raw(text="原图")
        b, quoted = await self.receive_parts([Reply(id="345"), Plain("讨论这张图")])
        event = self.input(b, quoted)
        source = quote_reference(event.source, event.quotes[0].position)
        before = [tuple(r) for r in self.app.runtime.read_all("SELECT * FROM conversation_delivery_receipts", ())]
        self.app.withdraw(a, self.input(a, first).scoped_key).unwrap()
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM sources WHERE source_id = ?", (source.source_id,))[0], "revoked")
        with self.assertRaises(TaskError):
            self.request(b, quoted)
        c, later = await self.receive_parts([Plain("继续")], sender="202")
        history = [json.loads(m.payload) for m in self.request(c, later).context.materials if m.purpose == "group_conversation_history"]
        self.assertEqual(history, [])
        self.assertEqual([tuple(r) for r in self.app.runtime.read_all("SELECT * FROM conversation_delivery_receipts ORDER BY rowid LIMIT 2", ())], before)
        self.assertFalse((await self.controller.receive_claimed(self.media_event([Reply(id="345")]))).is_success)

    async def test_quote_of_confirmed_bot_reply_links_all_original_evidence(self):
        await self.with_delivery()
        a, first = await self.receive_parts([Plain("原提问"), sdk_image()], sender="201")
        part = self.app.runtime.read_one("SELECT * FROM conversation_parts WHERE batch_id = ?", (first,))
        identifier = part["platform_ref"].split(":")[-1]
        self.records[identifier] = group_raw(message_id=identifier, sender="100", text=part["text"], count=0)
        b, quoted = await self.receive_parts([Reply(id=identifier), Plain("接着说")])
        event = self.input(b, quoted)
        source = quote_reference(event.source, event.quotes[0].position)
        self.app.withdraw(a, self.input(a, first).scoped_key).unwrap()
        self.assertEqual(self.app.runtime.read_one("SELECT state FROM sources WHERE source_id = ?", (source.source_id,))[0], "revoked")
        with self.assertRaises(TaskError):
            self.request(b, quoted)

    async def test_known_bot_reply_cannot_be_relabelled_as_an_unknown_members_quote(self):
        await self.with_delivery()
        _, batch = await self.receive_parts([Plain("原提问")])
        part = self.app.runtime.read_one("SELECT * FROM conversation_parts WHERE batch_id = ?", (batch,))
        identifier = part["platform_ref"].split(":")[-1]
        self.records[identifier] = group_raw(message_id=identifier, sender="999", text=part["text"], count=0)
        result = await self.controller.receive_claimed(self.media_event([Reply(id=identifier)]))
        self.assertEqual(result.failure.code, "quote_original_changed")

    async def test_private_and_other_group_original_cannot_be_republished_as_group_quote(self):
        await self.start_host()
        await self.accepted(identifier="345", text="私聊原话")
        self.records["345"] = group_raw(sender="200", text="私聊原话", count=0)
        failure = await self.controller.receive_claimed(self.media_event([Reply(id="345")]))
        self.assertEqual(failure.failure.code, "quote_original_scope_mismatch")
        await self.receive_parts([Plain("其他群原话")], identifier="346", target="group-b")
        self.records["346"] = group_raw(message_id="346", sender="200", text="其他群原话", count=0)
        failure = await self.controller.receive_claimed(self.media_event([Reply(id="346")]))
        self.assertEqual(failure.failure.code, "quote_original_scope_mismatch")

    async def test_other_persona_and_unique_session_known_originals_remain_isolated(self):
        await self.start_host()
        await self.receive_parts([Plain("当前人格原话")], identifier="345")
        self.records["345"] = group_raw(sender="200", text="当前人格原话", count=0)
        for options in ({"unique": True}, {}):
            if not options:
                self.native.selections["qq-main:GroupMessage:300"] = "second"
            failure = await self.controller.receive_claimed(self.media_event([Reply(id="345")], **options))
            self.assertEqual(failure.failure.code, "quote_original_scope_mismatch")

    async def test_bad_group_quote_routes_and_components_publish_nothing(self):
        await self.start_host()
        baseline = self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0]
        mutations = [lambda r: r.update(group_id=301), lambda r: r.update(self_id=101),
            lambda r: r.update(message_type="private"), lambda r: r.update(message_id=999),
            lambda r: r.update(anonymous={"id": 1}), lambda r: r.update(user_id=999),
            lambda r: r.update(message=[{"type": "reply", "data": {"id": "344"}}]),
            lambda r: r.update(message=[{"type": "forward", "data": {"id": "opaque"}}])]
        for mutate in mutations:
            self.records["345"] = group_raw()
            mutate(self.records["345"])
            result = await self.controller.receive_claimed(self.media_event([Reply(id="345")], sender="777"))
            self.assertFalse(result.is_success)
            self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], baseline)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_changed_known_quote_text_images_or_sender_roll_back_admission(self):
        await self.start_host()
        await self.receive_parts([Plain("原文"), sdk_image()], identifier="345", sender="201")
        baseline = self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0]
        for raw in (group_raw(text="被篡改"), group_raw(text="原文", content=image_bytes("blue")),
                    group_raw(text="原文", sender="202")):
            self.records["345"] = raw
            result = await self.controller.receive_claimed(self.media_event([Reply(id="345")]))
            self.assertFalse(result.is_success)
            self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], baseline)

    async def test_mutating_sdk_event_during_download_keeps_captured_sender_and_text(self):
        await self.start_host()
        event = self.media_event([Plain("冻结前"), sdk_image()], sender="201")
        async def mutate(locator):
            event.message_obj.sender.user_id = "999"
            event.message_obj.message = [Plain("冻结后")]
            return await load_native_image(locator)
        self.controller.session.bridge.groups.image_loader = mutate
        captured = (await self.controller.session.bridge.capture(event)).unwrap()
        self.assertEqual(captured.principal.native_account_id, "201")
        self.assertIn("冻结前", captured.text)
        self.assertNotIn("冻结后", captured.text)

    async def test_role_or_connection_change_during_media_capture_is_rejected(self):
        await self.start_host()
        group = self.controller.session.bridge.groups
        async def changed_role(locator):
            self.native.selections["qq-main:GroupMessage:300"] = "second"
            return await load_native_image(locator)
        group.image_loader = changed_role
        result = await self.controller.receive_claimed(self.media_event([sdk_image()]))
        self.assertEqual(result.failure.code, "host_persona_changed")
        self.native.selections["qq-main:GroupMessage:300"] = "original"
        async def changed_connection(locator):
            self.native.platform.client._wsr_api_clients["100"] = object()
            return await load_native_image(locator)
        group.image_loader = changed_connection
        result = await self.controller.receive_claimed(self.media_event([sdk_image()]))
        self.assertEqual(result.failure.code, "host_client_mismatch")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], 0)

    async def test_stop_while_preparing_group_image_cannot_admit_late_input(self):
        await self.start_host()
        session = self.controller.session
        entered, release = asyncio.Event(), asyncio.Event()
        async def held(locator):
            entered.set()
            await release.wait()
            return await load_native_image(locator)
        session.bridge.groups.image_loader = held
        pending = asyncio.create_task(self.controller.receive_claimed(self.media_event([sdk_image()])))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            (await self.controller.stop()).unwrap()
        finally:
            release.set()
        self.assertEqual((await asyncio.wait_for(pending, 3)).failure.code, "host_not_running")
        self.assertEqual(session.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], 0)

    async def test_direct_and_quoted_images_share_the_same_intake_budget(self):
        self.records["345"] = group_raw(count=5)
        await self.start_host()
        result = await self.controller.receive_claimed(self.media_event([Reply(id="345"), *(sdk_image() for _ in range(4))]))
        self.assertEqual(result.failure.code, "host_group_media_limit")
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads", ())[0], 0)

    async def test_tool_continuation_retains_group_image_evidence(self):
        async def model(payload, _):
            if not any(m["role"] == "tool" for m in payload["messages"]):
                return completion(tools=[NS(id="query", type="function", function=NS(
                    name=tool_alias("group.memory.query"), arguments="{}"))])
            content = next(m["content"] for m in payload["messages"] if m["role"] == "user")
            materials = json.loads(content[0]["text"])["materials"]
            image = next(m for m in materials if m["purpose"].startswith("input_image:"))
            return completion(final_text("图里有红色。", evidence=image["evidence"]))
        self.native.provider.client.state.behavior = model
        await self.start_host()
        context, batch = await self.receive_parts([sdk_image()])
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        for payload, _ in self.native.provider.client.state.calls:
            content = next(m["content"] for m in payload["messages"] if m["role"] == "user")
            self.assertEqual(len([p for p in content if p["type"] == "image_url"]), 1)
        self.assertEqual(len(self.request(context, batch).images), 1)
