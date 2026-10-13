"""Default multi-host assembly of the real Image provider with SDK group wire."""

import base64
import hashlib
import json
from types import SimpleNamespace as NS
import unittest

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.tool_loop import GROUP_EXTERNAL_ACTIONS
from tests.group_image_delivery_support import GroupImageDeliveryFixture
from tests.group_media_support import Plain, sdk_image
from tests.image_delivery_support import image_reply, offered_images
from tests.native_adapter_support import completion
from tests.native_image_support import ImageBackend
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_conversation_images import image_bytes
from astrbot_host.native_extensions.image_native.types import BackendResult


class NativeGroupImageFlowTests(GroupImageDeliveryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.image_backend = ImageBackend(BackendResult)
        self.native.provider.client.state.behavior = None

    def test_masked_edit_is_not_exposed_to_group_tools(self):
        self.assertIn("image.generate", GROUP_EXTERNAL_ACTIONS)
        self.assertIn("image.edit", GROUP_EXTERNAL_ACTIONS)
        self.assertNotIn("image.mask_edit", GROUP_EXTERNAL_ACTIONS)

    async def prepare_image_group(self):
        await self.with_delivery()
        registry = self.controller.native_extensions
        self.assertIsNotNone(registry.image_extension_api())
        registry.image_extension_api().companion_v2_native().owner.backend = self.image_backend
        context, _ = await self.receive_parts([Plain("准备原生图片能力")])
        self.assertIsNotNone(self.app.tools.external)
        self.package = next(declaration.descriptor.package for declaration in registry.declarations()
                            if declaration.descriptor.tool.action == "image.generate")
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
        # The management API reconciles a module acquired after host startup.
        # Repository writes alone intentionally do not start native services.
        await registry.reconcile_service(self.package.extension_id)
        await registry._lease(self.package.extension_id).start()
        self.assertEqual(registry.status(self.package.extension_id)["state"], "running")
        self.capabilities = repository
        self.native.provider.client.state.behavior = self.native_image_model
        return context

    async def native_image_model(self, payload, _):
        if not any(message["role"] == "tool" for message in payload["messages"]):
            return completion(tools=[NS(id="native-group-image", type="function", function=NS(
                name=tool_alias("image.generate"), arguments=json.dumps({"prompt": "生成一张红色图片"}, ensure_ascii=False)))])
        return image_reply(payload, text="这是本次生成的图片。")

    async def native_group_edit_model(self, payload, _):
        if not any(message["role"] == "tool" for message in payload["messages"]):
            arguments = {"prompt": "把第二张图片改成蓝色", "reference_indices": [1],
                         "reference_roles": ["edit_source"]}
            return completion(tools=[NS(id="native-group-edit", type="function", function=NS(
                name=tool_alias("image.edit"), arguments=json.dumps(arguments, ensure_ascii=False)))])
        return image_reply(payload, text="已按第二张图片完成修改。",
                           handles=offered_images(payload)[-1:])

    async def native_group_role_reference_model(self, payload, _):
        if not any(message["role"] == "tool" for message in payload["messages"]):
            arguments = {"prompt": "保留角色身份并放入雨夜街景", "reference_ids": ["shared-role-reference"],
                         "reference_roles": ["identity"]}
            return completion(tools=[NS(id="native-group-edit", type="function", function=NS(
                name=tool_alias("image.edit"), arguments=json.dumps(arguments, ensure_ascii=False)))])
        return image_reply(payload, text="已使用角色参考图完成修改。")

    def register_group_role_reference(self, context):
        from companion_v2.references.configuration import (
            GROUP, ReferenceConfigurationOwner, configuration_fields, target_for,
        )
        from companion_v2.references.models import (
            ContentDigest, ReferenceAsset, ReferenceKind, ReferenceRole, ReferenceSource,
        )
        from companion_v2.references.repositories import ReferenceAssetRepository
        from companion_v2.references.service import owner_key

        ReferenceConfigurationOwner(self.app.runtime).write(
            target_for(context), configuration_fields(),
            changes={GROUP + ".enabled": True, GROUP + ".group_enabled": True}, reset=(),
            expected_revision=0, observed_at=self.clock.now())
        payload = image_bytes("purple")
        asset = ReferenceAsset("shared-role-reference", ReferenceKind.REFERENCE_IMAGE,
            ReferenceRole.IDENTITY, ContentDigest(hashlib.sha256(payload).hexdigest()),
            len(payload), "image/png", "role-reference:test:shared-role-reference",
            ReferenceSource.OPERATOR, label="角色身份参考", created_at=self.clock.now())
        ReferenceAssetRepository(self.app.runtime).put(
            owner_key(context), asset, created_at=self.clock.now(), payload=payload)
        return payload

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

    async def test_group_edit_can_select_only_an_image_from_the_current_group_turn(self):
        await self.prepare_image_group()
        self.native.provider.client.state.behavior = self.native_group_edit_model
        context, _ = await self.receive_parts([
            Plain("只把第二张图改成蓝色"), sdk_image(image_bytes("red")), sdk_image(image_bytes("green")),
        ])

        self.assertEqual(len(self.image_backend.calls), 1)
        invocation, references = self.image_backend.calls[0]
        self.assertEqual(invocation.operation, "edit")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].role, "edit_source")
        self.assertEqual(references[0].data, image_bytes("green"))
        self.assertEqual([part["type"] for part in self.sends()[-1]["message"]], ["text", "image"])

    async def test_group_edit_can_use_role_reference_only_after_group_opt_in(self):
        context = await self.prepare_image_group()
        payload = self.register_group_role_reference(context)
        self.native.provider.client.state.behavior = self.native_group_role_reference_model

        group_context, batch = await self.receive_parts([Plain("用角色参考图做一张雨夜街景")])

        request = self.request(group_context, batch)
        self.assertIn("shared-role-reference", request.instruction)
        self.assertEqual(len(self.image_backend.calls), 1)
        invocation, references = self.image_backend.calls[0]
        self.assertEqual(invocation.operation, "edit")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].role, "identity")
        self.assertEqual(references[0].data, payload)


if __name__ == "__main__":
    unittest.main()
