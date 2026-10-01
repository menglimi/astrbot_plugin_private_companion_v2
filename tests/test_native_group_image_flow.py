"""Default multi-host assembly of the real Image provider with SDK group wire."""

import base64
import json
from types import SimpleNamespace as NS
import unittest

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.tool_loop import GROUP_EXTERNAL_ACTIONS
from tests.group_image_delivery_support import GroupImageDeliveryFixture
from tests.group_media_support import Plain
from tests.image_delivery_support import image_reply
from tests.native_adapter_support import completion
from tests.native_image_support import NativeImageFixture
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_conversation_images import image_bytes


class NativeGroupImageFlowTests(NativeImageFixture, GroupImageDeliveryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.native_registry = self.create_image_port(self.root / "native-image-provider", self.clock.now)
        self.native.get_all_stars = lambda: [self.image_star]
        self.native.provider.client.state.behavior = None

    def test_masked_edit_is_not_exposed_to_group_tools(self):
        self.assertIn("image.generate", GROUP_EXTERNAL_ACTIONS)
        self.assertIn("image.edit", GROUP_EXTERNAL_ACTIONS)
        self.assertNotIn("image.mask_edit", GROUP_EXTERNAL_ACTIONS)

    async def prepare_image_group(self):
        await self.with_delivery()
        context, _ = await self.receive_parts([Plain("准备原生图片能力")])
        self.assertIsNotNone(self.app.tools.external)
        self.package = self.native_registry.declarations()[0].descriptor.package
        repository = CapabilityRepository(self.app.runtime)
        repository.register_descriptor(self.package, registered_at=self.clock.now()).unwrap()
        repository.acquire(extension_id=self.package.extension_id, package_id=self.package.package_id,
            package_version=self.package.package_version, expected_revision=0, observed_at=self.clock.now()).unwrap()
        repository.set_role_enabled(extension_id=self.package.extension_id, role=context.role_binding.role,
            bot_id=context.scope.bot_id, enabled=True, expected_revision=0, observed_at=self.clock.now()).unwrap()
        for capability in self.package.capabilities:
            repository.set_authorization(extension_id=self.package.extension_id, capability_id=capability,
                subject=context.actor.subject, scope=context.scope, state=CapabilityAuthorizationState.ACTIVE,
                expected_revision=0, observed_at=self.clock.now()).unwrap()
        self.capabilities = repository
        self.native.provider.client.state.behavior = self.native_image_model
        return context

    async def native_image_model(self, payload, _):
        if not any(message["role"] == "tool" for message in payload["messages"]):
            return completion(tools=[NS(id="native-group-image", type="function", function=NS(
                name=tool_alias("image.generate"), arguments=json.dumps({"prompt": "生成一张红色图片"}, ensure_ascii=False)))])
        return image_reply(payload, text="这是本次生成的图片。")

    async def test_sdk_group_generation_delivery_history_and_confirmed_quote(self):
        await self.prepare_image_group()
        initial_sends = len(self.sends())
        context, batch = await self.receive_parts([Plain("生成一张图片")])
        self.assertEqual(len(self.image_backend.calls), 1)
        self.assertEqual(len(self.sends()), initial_sends + 1)
        message = self.sends()[-1]["message"]
        self.assertEqual([part["type"] for part in message], ["text", "image"])
        self.assertEqual(base64.b64decode(message[1]["data"]["file"].removeprefix("base64://")), image_bytes("red"))
        original = self.sent_original(batch)
        self.native.provider.client.state.behavior = None
        other, later = await self.receive_parts([Plain("继续话题")], sender="201")
        request = self.request(other, later)
        self.assertFalse(request.images)
        history = [json.loads(m.payload) for m in request.context.materials if m.purpose == "group_conversation_history"]
        picture_history = [item for item in history if item.get("type") == "confirmed_group_reply" and item.get("images")]
        self.assertEqual(len(picture_history), 1)
        self.assertEqual(picture_history[0]["images"][0]["view"], "historical_metadata_only")
        quoted_context, quoted_batch = await self.quoted(original, sender="201")
        self.assertEqual(len(self.request(quoted_context, quoted_batch).images), 1)
        self.capabilities.set_authorization(extension_id=self.package.extension_id, capability_id="image.generate",
            subject=context.actor.subject, scope=context.scope, state=CapabilityAuthorizationState.REVOKED,
            expected_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertFalse(self.app.messages.history(context).unwrap()["items"][-1]["body_available"])
        self.assertEqual(len(self.image_backend.calls), 1)

    async def test_group_without_image_consent_never_dispatches_backend(self):
        await self.with_delivery()
        self.native.provider.client.state.behavior = self.native_image_model
        batch = (await self.controller.receive_claimed(self.media_event([Plain("生成一张图片")]))).unwrap()
        await wait_for_batch(self.controller.session, batch, timeout_seconds=10)
        self.assertEqual(self.image_backend.calls, [])
        self.assertFalse(any(part["type"] == "image" for send in self.sends() for part in send["message"]))


if __name__ == "__main__":
    unittest.main()
