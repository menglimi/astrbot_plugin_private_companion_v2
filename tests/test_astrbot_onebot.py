import base64
from dataclasses import replace
import unittest
from unittest.mock import patch

from companion_v2.conversation.delivery import DeliveryEnvelope
from companion_v2.conversation.media.models import PromptImage
from companion_v2.delivery.media import ImageDeliveryEnvelope, payload_hash
from companion_v2.delivery.plan import PokePlan
from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import SourceRef, VersionRef
from tests.native_adapter_support import NativeFixture
from tests.test_semantic_integration import picture


class OneBotSenderTests(NativeFixture, unittest.IsolatedAsyncioTestCase):
    async def envelope(self):
        await super().envelope()
        return DeliveryEnvelope("part-1", "operation-1", self.native_context, 1, "你好", digest("你好"),
                                self.native_sender.binding, lambda: True)

    async def test_real_ack_keeps_original_route(self):
        envelope = await self.envelope()
        api = self.native.platform.client._api._wsr_api
        api.result = {"message_id": 123}
        receipt = await self.native_sender.send(envelope)
        self.assertEqual(receipt.status, "delivered")
        self.assertTrue(receipt.platform_ref.endswith(":123"))
        self.assertEqual(receipt.origin_key, envelope.context.key)
        self.assertEqual(receipt.operation_id, envelope.operation_id)
        self.assertEqual(api.calls[0][1]["self_id"], "100")

    async def test_signed_message_ids_are_confirmed_without_changing_accounts(self):
        envelope = await self.envelope()
        api = self.native.platform.client._api._wsr_api
        for message_id in (-123, "-456"):
            with self.subTest(message_id=message_id):
                api.result = {"message_id": message_id}
                receipt = await self.native_sender.send(envelope)
                self.assertEqual(receipt.status, "delivered")
                self.assertTrue(receipt.platform_ref.endswith(":" + str(message_id)))
                self.assertEqual(api.calls[-1][1]["self_id"], "100")

    async def test_qq_emoji_format_applies_only_to_catalog_reactions(self):
        envelope = await self.envelope()
        captured = picture()
        scope = envelope.context.scope
        now = self.clock.now()
        source = SourceRef("reaction-image", "conversation.image", scope, VersionRef("reaction-image", 1), now)
        self.native_sender.reaction_image_format = lambda: "qq_emoji"
        api = self.native.platform.client._api._wsr_api
        for owner, expected in (("expression.reactions", 1), ("conversation.image", None)):
            parent = SourceRef("parent-" + owner, owner, scope, VersionRef("parent-" + owner, 1), now)
            image = PromptImage(source, parent, captured.descriptor,
                                base64.b64encode(captured.content).decode("ascii"))
            selected = ImageDeliveryEnvelope(envelope.part_id, envelope.operation_id, envelope.context,
                envelope.sequence, "", payload_hash("", (image,)), envelope.sender,
                envelope.before_dispatch, (image,))
            self.assertEqual((await self.native_sender.send(selected)).status, "delivered")
            message = api.calls[-1][1]["message"]
            self.assertEqual([component["type"] for component in message], ["image"])
            self.assertEqual(message[0]["data"].get("sub_type"), expected)
        self.assertEqual((await self.native_sender.send(replace(envelope, text="", payload_hash=digest("")))).status,
                         "not_sent")

    async def test_no_message_id_boolean_timeout_and_failure_are_unknown(self):
        envelope = await self.envelope()
        api = self.native.platform.client._api._wsr_api
        for result in (True, None, {}, {"message_id": "-01"}, {"message_id": -1},
                       {"message_id": "-1"}, {"message_id": 0}, {"message_id": True}):
            with self.subTest(result=result):
                api.result = result
                receipt = await self.native_sender.send(envelope)
                self.assertEqual(receipt.status, "unknown")
                self.assertIsNone(receipt.delivered_at)
        api.error = TimeoutError("the response might be lost")
        self.assertEqual((await self.native_sender.send(envelope)).status, "unknown")
        self.assertEqual(len(api.calls), 9)

    async def test_qq_eventchecker_1200_is_a_known_refusal(self):
        envelope = await self.envelope()
        api = self.native.platform.client._api._wsr_api
        api.error = RuntimeError("QQ/NTQQ 拒绝发送（retcode=1200，EventChecker sendMsg）")

        receipt = await self.native_sender.send(envelope)

        self.assertEqual(receipt.status, "not_sent")
        self.assertEqual(receipt.failure_code, "qq_eventchecker_1200")
        self.assertIsNone(receipt.delivered_at)
        api.error = None
        api.result = {"status": "failed", "retcode": 1200, "message": "EventChecker sendMsg"}
        receipt = await self.native_sender.send(envelope)
        self.assertEqual(receipt.status, "not_sent")
        self.assertEqual(receipt.failure_code, "qq_eventchecker_1200")

    async def test_non_eventchecker_send_exception_remains_unknown(self):
        envelope = await self.envelope()
        self.native.platform.client._api._wsr_api.error = RuntimeError("retcode=1200 but unrelated")

        receipt = await self.native_sender.send(envelope)

        self.assertEqual(receipt.status, "unknown")
        self.assertIsNone(receipt.failure_code)

    async def test_disconnected_original_login_never_uses_another_available_login(self):
        envelope = await self.envelope()
        self.native.platform.client._wsr_api_clients.pop("100")
        receipt = await self.native_sender.send(envelope)
        self.assertEqual(receipt.status, "not_sent")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_voice_wait_rechecks_authority_persona_and_original_login(self):
        envelope = await self.envelope()
        clients = self.native.platform.client._wsr_api_clients
        original = clients["100"]
        api = self.native.platform.client._api._wsr_api
        for change in ("revoke", "persona", "disconnect"):
            with self.subTest(change=change):
                self.select_window_persona("original")
                clients["100"] = original
                authorized = True

                def authorize():
                    return None if authorized else Outcome.failed("authorization_revoked", "revoked")

                async def voice(_, __):
                    nonlocal authorized
                    if change == "revoke":
                        authorized = False
                    elif change == "persona":
                        self.select_window_persona("changed")
                    else:
                        clients.pop("100")
                    return {"type": "record", "data": {"file": "base64://YQ=="}}

                self.native_sender.authorize = authorize
                self.native_sender.voice = voice
                self.assertEqual((await self.native_sender.send(envelope)).status, "not_sent")
                self.assertEqual(api.calls, [])

    async def test_missing_owner_fence_wrong_recipient_and_changed_persona_prevent_send(self):
        envelope = await self.envelope()
        self.assertEqual((await self.native_sender.send(replace(envelope, before_dispatch=None))).status, "not_sent")
        actor = replace(envelope.context.actor, principal=replace(envelope.context.actor.principal, native_account_id="201"))
        self.assertEqual((await self.native_sender.send(replace(envelope, context=replace(envelope.context, actor=actor)))).status, "not_sent")
        self.select_window_persona("changed")
        with self.assertLogs("companion_v2.adapters.astrbot.onebot", level="WARNING") as captured:
            receipt = await self.native_sender.send(envelope)
        self.assertEqual(receipt.status, "not_sent")
        self.assertIn("stage=final_dispatch_check", captured.output[0])
        self.assertIn("reason=host_persona_window_unbound", captured.output[0])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_text_delivery_verifies_live_persona_once_at_dispatch(self):
        envelope = await self.envelope()
        with patch.object(self.bridge, "verify_role", wraps=self.bridge.verify_role) as verify:
            receipt = await self.native_sender.send(envelope)
            self.assertEqual(verify.await_count, 1)
        self.assertEqual(receipt.status, "delivered")

    async def test_persona_change_after_poke_keeps_combined_result_unknown(self):
        envelope = await self.envelope()
        api = self.native.platform.client._api._wsr_api
        original = api.call_action

        async def action(name, **params):
            result = await original(name, **params)
            if name == "friend_poke":
                self.select_window_persona("changed")
            return result

        api.call_action = action
        receipt = await self.native_sender.send(replace(envelope, poke=PokePlan()))

        self.assertEqual(receipt.status, "unknown")
        self.assertEqual([name for name, _ in api.calls], ["friend_poke"])

    async def test_unknown_send_is_not_replayed_or_written_to_confirmed_history(self):
        snapshot = await self.capture()
        self.native.platform.client._api._wsr_api.error = TimeoutError()
        host = await self.setup_host()
        batch = host.receive(snapshot).unwrap()
        app = host.application
        self.assertEqual((await self.done(app, batch))["state"], "blocked")
        self.assertEqual(host.receive(snapshot).unwrap(), batch)
        self.advance(app, 5)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        self.assertEqual(app.messages.history(self.context(app, batch)).unwrap()["items"], [])
