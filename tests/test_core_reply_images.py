"""Native core tools use the real optional Image owner and original attachments."""

import base64
from dataclasses import replace
import json
import io
from types import SimpleNamespace as NS
import unittest

from tests import test_astrbot_staging_host as _host_import
from astrbot.core.agent.message import Message, ToolCall
from astrbot.core.message.components import Image
from mcp.types import CallToolResult
from PIL import Image as PILImage

from astrbot_host.core_reply import prepare_core_reply_event
from astrbot_host.core_reply_tools import close_core_reply_tools, inject_core_reply_tools, native_tool_name
from companion_v2.adapters.astrbot.native import NativeConversationInput
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.media.quota import GROUP, QUOTA_FIELDS, ImageQuotaConfigurationOwner
from companion_v2.conversation.media.output_settings import (
    GROUP as OUTPUT_GROUP, ImageOutputConfigurationOwner, configuration_fields as output_fields,
)
from companion_v2.execution.models import TaskContext, require
from datetime import timedelta
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from tests.native_image_support import NativeImageFixture
from tests.test_astrbot_core_reply import FakeEvent
from tests.test_conversation_images import image_bytes
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE


class CoreReplyImagesTests(NativeImageFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.image_directory = self.root.parent / "image-native-v2"
        self.native_registry = self.create_image_port(self.image_directory, self.clock.now)
        self.native_registry._default_handlers = True
        self.providers = tuple(replace(provider, capabilities=("text", "tools", "image")) for provider in self.providers)
        self.sender = replace(self.sender, supports_images=True)
        package = self.native_registry.declarations()[0].descriptor.package
        capabilities = CapabilityRepository(self.runtime)
        require(capabilities.register_descriptor(package, registered_at=NOW))
        require(capabilities.acquire(extension_id=package.extension_id, package_id=package.package_id,
            package_version=package.package_version, expected_revision=0, observed_at=NOW))
        require(capabilities.set_role_enabled(extension_id=package.extension_id, role=self.window.role,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW))
        for capability in package.capabilities:
            require(capabilities.set_authorization(extension_id=package.extension_id, capability_id=capability,
                subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE,
                expected_revision=0, observed_at=NOW))

    async def asyncSetUp(self):
        self.app = (await self.start(self.host(tool_port=self.native_registry))).application
        self.addAsyncCleanup(close_core_reply_tools, self.app)
        self.context = TaskContext(self.important, require(self.identity.resolve_role(SCOPE, observed_at=NOW)),
                                   AudienceRef(SCOPE, (self.important.subject,)))

    def prepare(self, event_id="native-image", images=()):
        event = FakeEvent()
        parts = []
        for data in images:
            parts.append(Image.fromBase64(base64.b64encode(data).decode("ascii")))
        event.message_obj = NS(message=parts)
        original = NativeConversationInput(event_id, self.context.actor.principal,
            ConversationRoute(SCOPE, user=self.context.actor.subject), self.context.audience,
            "请帮我画图", self.clock.now(), self.context.role_binding.role, "原人格")
        prepared = {"context": self.context, "event_id": event_id, "native_input": original}
        async def authorize(value):
            return self.app.tasks.check_context_access(value["context"], action="conversation.reply", observed_at=self.clock.now())
        prepare_core_reply_event(event, prepared, authorize=authorize)
        request = NS(func_tool=None, system_prompt="原人格")
        inject_core_reply_tools(event, request, application=self.app)
        return event, request

    async def call(self, event, request, action, arguments, call_id):
        call = ToolCall(id=call_id, function=ToolCall.FunctionBody(
            name=native_tool_name(action), arguments=json.dumps(arguments)))
        wrapper = NS(context=NS(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        tool = request.func_tool.get_tool(native_tool_name(action))
        self.assertIsNotNone(tool)
        return await tool.call(wrapper, **arguments)

    def result(self, received, color):
        self.assertIsInstance(received, CallToolResult, received)
        result = json.loads(received.content[0].text)
        self.assertEqual((result["state"], result["effect"]), ("succeeded", "committed"), result)
        self.assertEqual(base64.b64decode(received.content[1].data), image_bytes(color))
        return result

    def assert_no_reply_work(self, event):
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) n FROM conversation_batches", ())["n"], 0)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) n FROM model_rounds", ())["n"], 0)
        self.assertEqual(self.called, [])
        self.assertEqual(self.sent, [])
        self.assertEqual(event.sent, [])

    def configure_images(self, owner, fields, changes):
        target = ConfigTarget(SCOPE.installation_id, ConfigLayer.ROLE,
                              self.context.role_binding.role, bot_id=SCOPE.bot_id)
        owner.write(target, fields, changes=changes, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=self.clock.now())

    async def test_native_daily_quota_counts_attempts_and_replays_without_a_second_charge(self):
        gate = self.app.messages.image_quota
        scope = gate._classify_context(self.context)
        self.configure_images(ImageQuotaConfigurationOwner(self.runtime), QUOTA_FIELDS,
                              {GROUP + "." + scope + "_max_daily": 1})
        event, request = self.prepare("native-quota")
        generated = await self.call(event, request, "image.generate", {"prompt": "红色"}, "quota-first")
        self.result(generated, "red")
        self.assertEqual(gate._used(self.context, scope, self.clock.now()), 1)
        replay = await self.call(event, request, "image.generate", {"prompt": "红色"}, "quota-first")
        self.assertEqual(replay.content, generated.content)
        denied = await self.call(event, request, "image.generate", {"prompt": "红色"}, "quota-second")
        self.assertEqual(json.loads(denied)["code"], "image_quota_exhausted")
        self.assertEqual(len(self.image_backend.calls), 1)
        self.clock.advance(timedelta(days=1))
        self.assertEqual(gate._used(self.context, scope, self.clock.now()), 0)
        self.assert_no_reply_work(event)

    async def test_native_image_request_switch_is_consumed_before_provider_dispatch(self):
        self.configure_images(ImageOutputConfigurationOwner(self.runtime), output_fields(),
                              {OUTPUT_GROUP + ".allow_user_requests": False})
        event, request = self.prepare("native-images-off")
        denied = await self.call(event, request, "image.generate", {"prompt": "红色"}, "disabled")
        self.assertEqual(json.loads(denied)["code"], "image_requests_disabled")
        self.assertEqual(self.image_backend.calls, [])
        self.assert_no_reply_work(event)

    async def test_generate_then_edit_saved_artifact_returns_native_mcp_original_without_independent_send(self):
        event, request = self.prepare()
        generation = await self.call(event, request, "image.generate", {"prompt": "红色"}, "generate")
        result = self.result(generation, "red")
        native = json.loads(result["payload"])["native"]
        artifact = native["artifacts"][0]["artifact_id"]
        edited = await self.call(event, request, "image.edit", {"prompt": "蓝色", "artifact_id": artifact}, "edit")
        self.result(edited, "blue")
        replay = await self.call(event, request, "image.generate", {"prompt": "红色"}, "generate")
        self.assertEqual(replay.content, generation.content)
        self.assertEqual(len(self.image_backend.calls), 2)
        self.assertEqual(len(self.image_backend.calls[1][1]), 1)
        album = self.app.messages.generated_images
        page = album.album_page(self.context, self.clock.now(), limit=1)
        self.assertEqual(len(page["items"]), 1)
        self.assertIsNotNone(page["next_cursor"])
        next_page = album.album_page(self.context, self.clock.now(), limit=1, cursor=page["next_cursor"])
        self.assertEqual(len(next_page["items"]), 1)
        self.assertNotEqual(page["items"][0].image_id, next_page["items"][0].image_id)
        for item in (*page["items"], *next_page["items"]):
            self.assertEqual(album.album_image(self.context, self.clock.now(), item.image_id), item)
            parent, source, asset = album.album_refs(item, self.context)
            self.assertEqual(parent, item.parent)
            self.assertTrue(self.app.messages.sources.validate_reference(source, observed_at=self.clock.now()).is_success)
        self.assertEqual(album.observability_page(self.context, self.clock.now())["total"], 2)
        selected = page["items"][0]
        self.app.messages.sources.revoke(selected.parent, expected_governance_revision=1,
                                         observed_at=self.clock.now()).unwrap()
        self.assertEqual(len(album.album_page(self.context, self.clock.now())["items"]), 1)
        self.assert_no_reply_work(event)

    async def test_edit_reads_actual_current_native_attachment_only_on_tool_invocation(self):
        event, request = self.prepare("native-edit-input", (image_bytes("red"),))
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM conversation_image_payloads", ())["n"], 0)
        received = await self.call(event, request, "image.edit", {"prompt": "蓝色"}, "edit-input")
        self.result(received, "blue")
        reference = self.image_backend.calls[0][1][0]
        self.assertEqual(reference.data, image_bytes("red"))
        self.assertEqual(reference.role, "edit_source")
        self.assert_no_reply_work(event)

    async def test_mask_edit_receives_original_input_and_mask_through_native_references(self):
        mask = PILImage.new("RGB", (3, 2), "black")
        mask.putpixel((0, 0), (255, 255, 255))
        mask_bytes = io.BytesIO()
        mask.save(mask_bytes, format="PNG")
        event, request = self.prepare("native-mask-input", (image_bytes("red"), mask_bytes.getvalue()))
        received = await self.call(event, request, "image.mask_edit", {
            "prompt": "蓝色", "source_index": 0, "mask_index": 1}, "mask-input")
        self.assertIsInstance(received, CallToolResult, received)
        self.assertEqual(json.loads(received.content[0].text)["state"], "succeeded")
        with PILImage.open(io.BytesIO(base64.b64decode(received.content[1].data))) as final:
            self.assertEqual(final.getpixel((0, 0)), (0, 0, 255))
            self.assertEqual(final.getpixel((1, 0)), (255, 0, 0))
        references = self.image_backend.calls[0][1]
        self.assertEqual([reference.role for reference in references], ["edit_source", "edit_mask"])
        self.assertEqual(references[1].data, mask_bytes.getvalue())
        self.assert_no_reply_work(event)


if __name__ == "__main__":
    unittest.main()
