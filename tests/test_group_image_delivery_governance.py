"""Group image dispatch races, sealed history and durable recovery without replay."""

import asyncio
import base64
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from astrbot_host.group_authority import GroupAuthority
from companion_v2.conversation.media.reply import OWNER
from companion_v2.delivery.models import DeliveryReceipt, LocalSender
from companion_v2.execution.models import TaskContext, TaskError, digest
from tests.animation_support import animation_bytes
from tests.group_host_support import group_config
from tests.group_image_delivery_support import GroupImageDeliveryFixture
from tests.group_media_support import sdk_image, Plain, Reply
from tests.image_delivery_support import image_reply
from tests.staging_bootstrap_support import wait_for_batch


class GroupImageGovernanceTests(GroupImageDeliveryFixture, unittest.IsolatedAsyncioTestCase):
    async def settle(self, batch):
        await wait_for_batch(self.controller.session, batch, timeout_seconds=self.batch_timeout_seconds)

    def context(self, batch):
        return TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))

    async def test_changed_authority_or_original_during_role_await_prevents_whole_send(self):
        await self.with_delivery()
        for index, mode in enumerate(("asset", "frame", "source", "manifest", "corrupt_manifest",
                                      "missing_manifest", "bytes", "group_grant", "withdraw")):
            with self.subTest(mode=mode):
                (await self.controller.authorize_group_delivery("group-a")).unwrap()
                original_sender = self.app.delivery.sender
                changed = False

                async def guarded(envelope):
                    async def during_lookup(_):
                        nonlocal changed
                        if changed:
                            return
                        changed = True
                        row = self.app.runtime.read_one("SELECT batch_id FROM conversation_parts WHERE part_id = ?", (envelope.part_id,))
                        batch = row[0]
                        event = self.input(envelope.context, batch)
                        source, asset = self.app.messages.images.references(event, event.images[0])
                        manifest = self.app.messages.reply_images.reference(self.app.messages.batch(batch), envelope.context)
                        if mode in ("asset", "frame", "source", "manifest"):
                            owner, reference = {
                                "asset": (self.app.messages.images.assets, asset),
                                "frame": (self.app.messages.sources, envelope.images[0].frames[-1].source),
                                "source": (self.app.messages.sources, source),
                                "manifest": (self.app.messages.sources, manifest),
                            }[mode]
                            owner.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
                        elif mode == "group_grant":
                            (await self.controller.revoke_group_delivery("group-a")).unwrap()
                        elif mode == "withdraw":
                            self.app.withdraw(envelope.context, event.scoped_key).unwrap()
                        else:
                            with self.app.runtime.transaction() as connection:
                                if mode == "corrupt_manifest":
                                    connection.execute("UPDATE sources SET payload_json = ? WHERE source_id = ?", ('"changed"', manifest.source_id))
                                elif mode == "missing_manifest":
                                    connection.execute("DELETE FROM source_dependencies WHERE dependent_id = ?", (manifest.source_id,))
                                    connection.execute("DELETE FROM sources WHERE source_id = ?", (manifest.source_id,))
                                else:
                                    connection.execute("UPDATE conversation_image_payloads SET content = ? WHERE parent_id = ?", (b"changed", event.source.source_id))
                    self.native.before_resolve = during_lookup
                    try:
                        return await original_sender.send(envelope)
                    finally:
                        self.native.before_resolve = None

                self.app.delivery.sender = LocalSender(original_sender.binding, guarded, supports_images=True)
                batch = (await self.controller.receive_claimed(self.media_event(
                    [sdk_image(animation_bytes())], sender=str(800 + index), unique=True))).unwrap()
                await self.settle(batch)
                self.app.delivery.sender = original_sender
                self.assertTrue(changed)
                self.assertEqual(self.parts(batch)[0]["state"], "failed")
                self.assertFalse(self.sends())
                self.assertFalse(self.app.messages.history(self.context(batch)).unwrap()["items"])

    async def test_original_member_revocation_blocks_saved_history_and_bot_quotes_after_restart(self):
        await self.with_delivery()
        a, first = await self.receive_parts([sdk_image()], sender="201")
        identifier = self.sent_original(first)
        b, quoted = await self.receive_parts([Reply(id=identifier)], sender="202")
        c, later = await self.receive_parts([Plain("接着聊图片")], sender="203")
        identity = self.controller.authority.identities
        grant = GroupAuthority.grant_id(a.scope, a.actor.subject, "text")
        identity.revoke_grant(grant, revoked_at=self.clock.now(), expected_revision=identity.revision)
        await self.restart()
        for context, batch in ((b, quoted), (c, later)):
            with self.assertRaises(TaskError):
                self.request(context, batch)
            self.assertFalse(self.app.messages.history(context).unwrap()["items"][0]["body_available"])
        self.assertFalse((await self.controller.receive_claimed(self.media_event([Reply(id=identifier)], sender="204"))).is_success)
        self.assertEqual(len(self.sends()), 3)

    async def test_sealed_original_input_fingerprint_is_checked_for_image_reply_history(self):
        await self.with_delivery()
        a, first = await self.receive_parts([sdk_image()], sender="201")
        b, later = await self.receive_parts([Plain("后续消息")], sender="202")
        original = self.input(a, first)
        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_inputs SET event_hash = ? WHERE event_key = ?", ("changed", original.scoped_key))
        await self.restart()
        with self.assertRaises(TaskError):
            self.request(b, later)

    async def test_unknown_ack_requires_original_image_hash_after_restart_without_replay(self):
        await self.with_delivery()
        self.api.error = TimeoutError("synthetic lost group image ACK")
        event = self.media_event([sdk_image()])
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await self.settle(batch)
        self.assertEqual(self.parts(batch)[0]["state"], "unknown")
        await self.restart()
        self.api.error = None
        self.assertEqual((await self.controller.receive_claimed(event)).unwrap(), batch)
        context = self.context(batch)
        self.assertFalse(self.app.messages.history(context).unwrap()["items"])
        part = self.parts(batch)[0]
        receipt = DeliveryReceipt(part["part_id"], part["operation_id"], context.key, part["payload_hash"],
            self.controller.session.sender_binding, "delivered", "late-group-image-ack",
            "onebot-message:" + digest([context.scope.platform, context.scope.account_id])[:24] + ":9876", self.clock.now())
        wrong = replace(receipt, payload_hash=digest(part["text"]))
        self.assertEqual(self.app.record_receipt(wrong).failure.code, "message_receipt_mismatch")
        self.app.record_receipt(receipt).unwrap()
        self.app.reconcile_delivery(context, part["part_id"]).unwrap()
        await self.settle(batch)
        self.assertEqual(self.parts(batch)[0]["state"], "delivered")
        self.assertEqual(len(self.app.messages.history(context).unwrap()["items"][0]["images"]), 1)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_restart_sends_only_pending_image_part_with_original_selection_and_bytes(self):
        async def respond(payload, _):
            return image_reply(payload, text="第一段\n原图在这里。")
        self.native.provider.client.state.behavior = respond
        self.config = group_config(group_delivery_mode="onebot_group")
        self.config["runtime"]["part_gap_seconds"] = 3
        self.controller = self.make_controller(self.config)
        await self.start_host()
        (await self.controller.authorize_group_delivery("group-a")).unwrap()
        self.app.generator.split = lambda text: tuple(text.splitlines(keepends=True))
        body = animation_bytes()
        batch = (await self.controller.receive_claimed(self.media_event([sdk_image(body)]))).unwrap()
        async def spaced():
            while self.app.flow.row(batch)["reason"] != "part_spacing":
                self.assertNotIn(self.app.flow.row(batch)["state"], ("blocked", "closed"))
                await asyncio.sleep(0.005)
        await asyncio.wait_for(spaced(), self.batch_timeout_seconds)
        self.assertEqual([p["state"] for p in self.parts(batch)], ["delivered", "pending"])
        receipt = self.parts(batch)[0]["receipt_ref"]
        await self.restart()
        with patch("astrbot_host.media.inspect_image", side_effect=AssertionError("recovery must use saved bytes")):
            self.clock.advance(timedelta(seconds=3))
            self.app.notify()
            await self.settle(batch)
        self.assertEqual([p["state"] for p in self.parts(batch)], ["delivered", "delivered"])
        self.assertEqual(self.parts(batch)[0]["receipt_ref"], receipt)
        self.assertEqual([[p["type"] for p in call["message"]] for call in self.sends()], [["text"], ["text", "image"]])
        self.assertEqual(base64.b64decode(self.sends()[1]["message"][1]["data"]["file"].removeprefix("base64://")), body)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_pending_preview_image_cannot_gain_later_sending_authority(self):
        self.config = group_config()
        self.config["runtime"].update(quiet_seconds=2, maximum_wait_seconds=5)
        self.controller = self.make_controller(self.config)
        await self.start_host()
        event = self.media_event([sdk_image()])
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await self.controller.terminate()
        self.config = group_config(group_delivery_mode="onebot_group")
        self.controller = self.make_controller(self.config)
        await self.start_host()
        (await self.controller.authorize_group_delivery("group-a")).unwrap()
        self.assertEqual((await self.controller.receive_claimed(event)).unwrap(), batch)
        self.clock.advance(timedelta(seconds=3))
        self.app.notify()
        await self.settle(batch)
        preview = self.controller.preview("group-a", batch).unwrap()
        self.assertEqual(preview["delivery_mode"], "preview")
        self.assertEqual(preview["configured_delivery_mode"], "onebot_group")
        self.assertEqual(len(preview["parts"][0]["images"]), 1)
        self.assertFalse(preview["sent"] or self.sends())

    async def test_stop_during_image_preparation_cannot_dispatch_after_restart(self):
        await self.with_delivery()
        entered = asyncio.Event()
        async def held(_):
            if self.app.runtime.read_one("SELECT 1 FROM sources WHERE owner = ?", (OWNER,)):
                entered.set()
                await asyncio.Event().wait()
        self.native.before_resolve = held
        batch = (await self.controller.receive_claimed(self.media_event([sdk_image()]))).unwrap()
        await asyncio.wait_for(entered.wait(), self.batch_timeout_seconds)
        (await self.controller.stop()).unwrap()
        self.assertFalse(self.sends())
        self.native.before_resolve = None
        self.clock.advance(timedelta(seconds=1))
        (await self.controller.start()).unwrap()
        await self.settle(batch)
        self.assertFalse(self.sends())
        self.assertFalse(self.app.messages.history(self.context(batch)).unwrap()["items"])
