"""Native Screen capture through the V2 host, using synthetic JPEG bytes only."""

import base64
from dataclasses import replace
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageGrab

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.screen_provider import (
    NativeScreenProvider,
    PLUGIN_ID as SCREEN_PACKAGE_ID,
    capture_local_screen,
)
from companion_v2.adapters.astrbot.model_wire import build_wire
from companion_v2.capabilities import CapabilityAuthorizationState, CapabilityRepository
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.conversation.media.models import ImageDescriptor
from companion_v2.conversation.media.screen import ScreenPromptImage
from companion_v2.execution.models import TaskError
from companion_v2.model_gateway.models import ToolCall
from companion_v2.product import PRODUCT_VERSION
from companion_v2.screen import SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ, ScreenOriginalStore
from companion_v2.sources import SourceRepository
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered, requested


def sample_jpeg():
    image = Image.new("RGB", (8, 8), (25, 150, 70))
    body = io.BytesIO()
    image.save(body, format="JPEG")
    return body.getvalue()


class NativeScreenCaptureTests(unittest.TestCase):
    def test_default_capture_uses_pillow_and_returns_bounded_jpeg(self):
        with patch.object(ImageGrab, "grab", return_value=Image.new("RGB", (8, 8), "green")) as grab:
            body = capture_local_screen()
        grab.assert_called_once_with(all_screens=False)
        with Image.open(io.BytesIO(body)) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (8, 8)))


class NativeScreenFlowTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        # ManagementFixture seeds a different Screen package for its own tests.
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM capability_descriptors WHERE extension_id = ?", (SCREEN_EXTENSION,))
        self.jpeg = sample_jpeg()
        self.captures = 0
        self.capture_error = None
        self.provider_directory = self.root.parent / "screen-native-v2"
        self.native_registry = self.create_screen_registry()
        self.providers = tuple(replace(provider, capabilities=("text", "tools", "image"))
                               for provider in self.providers)
        self.package = self.native_registry.declarations()[0].descriptor.package
        self.capabilities = CapabilityRepository(self.runtime)
        self.capabilities.register_descriptor(self.package, registered_at=NOW).unwrap()
        self.capabilities.acquire(extension_id=SCREEN_EXTENSION, package_id=self.package.package_id,
                                  package_version=self.package.package_version, expected_revision=0,
                                  observed_at=NOW).unwrap()
        self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=self.window.role,
                                           bot_id=SCOPE.bot_id, enabled=True,
                                           expected_revision=0, observed_at=NOW).unwrap()
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.grant(self.important, SCOPE, capability)
            self.consent(capability, CapabilityAuthorizationState.ACTIVE, 0)
        self.model_behavior = self.screen_model

    def capture(self):
        self.captures += 1
        if self.capture_error is not None:
            raise self.capture_error
        return self.jpeg

    def create_screen_registry(self):
        provider = NativeScreenProvider(self.provider_directory, version=PRODUCT_VERSION,
            capture=self.capture, now=self.clock.now)
        self.screen_provider = provider
        self.addAsyncCleanup(provider.close)
        star = SimpleNamespace(root_dir_name=SCREEN_PACKAGE_ID,
            name=SCREEN_PACKAGE_ID, version=PRODUCT_VERSION, activated=True,
            star_cls=SimpleNamespace(extension_api=SimpleNamespace(
                companion_v2_native=lambda: provider)))
        registry = NativeExtensionRegistry(SimpleNamespace(get_all_stars=lambda: (star,)), now=self.clock.now)
        self.addCleanup(registry.close)
        self.assertEqual(len(registry.declarations()), 1)
        return registry

    def consent(self, capability, state, revision):
        return self.capabilities.set_authorization(extension_id=SCREEN_EXTENSION,
            capability_id=capability, subject=self.important.subject, scope=SCOPE,
            state=state, expected_revision=revision, observed_at=self.clock.now()).unwrap()

    async def screen_model(self, envelope):
        if not envelope.tool_history:
            return requested(ToolCall("capture", "screen.capture", "{}"))
        return answered("我看到了当前屏幕。")

    async def screen_host(self, **options):
        options.setdefault("policy", ConversationPolicy(0, 0, 180, 0))
        return await self.start(self.host(tool_port=self.native_registry, **options))

    async def complete_screen(self):
        host = await self.screen_host()
        batch = host.receive(self.event()).unwrap()
        state = await self.done(host.application, batch)
        self.assertEqual(state["state"], "complete", dict(state))
        return host, batch, self.context(host.application, batch)

    async def restart_screen(self, host):
        await host.application.close()
        self.screen_provider.close()
        generation = self.screen_provider.generation
        self.native_registry = self.create_screen_registry()
        self.assertEqual(self.screen_provider.generation, generation)
        restored = self.open_runtime()
        new = self.host(runtime=restored, tool_port=self.native_registry,
                        policy=ConversationPolicy(0, 0, 180, 0))
        return await self.start(new, 1, 1)

    def screen_images(self, host, batch, context, request=None):
        request = request or self.called[-1].original
        return host.application.messages.screen_images.read_batch(
            host.application.messages.batch(batch), context, self.clock.now(), request)

    async def test_capture_enters_model_context_without_becoming_sendable(self):
        host, batch, context = await self.complete_screen()
        self.assertEqual(self.captures, 1)
        self.assertEqual(len(self.called), 2)
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(getattr(self.sent[0], "images", ()))
        image = self.called[-1].original.images[0]
        self.assertIsInstance(image, ScreenPromptImage)
        self.assertEqual(base64.b64decode(image.data_base64), self.jpeg)
        self.assertEqual(image.source.owner, "screen")
        self.assertIn("screen_capture", self.called[-1].original.instruction)
        perception = build_wire(self.called[-1]).messages[1]["content"]
        self.assertIn("已收到按需采集的屏幕画面", perception)
        self.assertIn("采集时刻、画面覆盖范围", perception)
        self.assertNotIn("成功返回屏幕画面前，不能声称看到了屏幕", perception)
        self.assertEqual(host.application.messages.reply_images.read(
            host.application.messages.batch(batch), context, self.clock.now())[0], ())
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertIsNotNone(row["receipt_ref"])
        self.assertEqual(host.receive(self.event()).unwrap(), batch)
        self.assertEqual(self.captures, 1)

    async def test_capture_continues_when_reply_segmentation_is_enabled(self):
        host = await self.screen_host(segmentation=SegmentationPolicy(enabled=True))
        batch = host.receive(self.event()).unwrap()
        state = await self.done(host.application, batch)
        self.assertEqual(state["state"], "complete", dict(state))
        self.assertEqual(len(self.called), 2)
        self.assertIsInstance(self.called[-1].original.images[0], ScreenPromptImage)
        self.assertEqual(len(self.sent), 1)

    async def test_current_read_consent_controls_saved_original(self):
        host, batch, context = await self.complete_screen()
        self.assertEqual(len(self.screen_images(host, batch, context)), 1)
        self.consent(SCREEN_READ, CapabilityAuthorizationState.REVOKED, 1)
        with self.assertRaises(TaskError) as caught:
            self.screen_images(host, batch, context)
        self.assertEqual(caught.exception.code, "capability_consent_revoked")
        self.assertEqual(self.captures, 1)

    async def test_tampered_original_cannot_reenter_model_context(self):
        host, batch, context = await self.complete_screen()
        image = self.called[-1].original.images[0]
        path = ScreenOriginalStore(self.runtime.data_root)._path(image.descriptor.content_hash)
        path.write_bytes(b"changed")
        with self.assertRaises(TaskError) as caught:
            self.screen_images(host, batch, context)
        self.assertEqual(caught.exception.code, "screen_original_changed")

    async def test_source_withdrawal_hides_capture_but_keeps_operation_receipt(self):
        host, batch, context = await self.complete_screen()
        image = self.called[-1].original.images[0]
        SourceRepository(self.runtime).revoke(image.source,
            expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.screen_images(host, batch, context), ())
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        result, material = host.application.external.snapshot(row, context, self.clock.now())
        self.assertEqual((result["state"], result["effect"]), ("succeeded", "committed"))
        self.assertIsNotNone(result["receipt_ref"])
        self.assertIsNone(material)

    async def test_adoption_failure_keeps_capture_receipt_without_screen_material(self):
        self.jpeg = b"not a jpeg"
        host, batch, context = await self.complete_screen()
        self.assertEqual(self.captures, 1)
        self.assertEqual(self.called[-1].original.images, ())
        self.assertEqual(self.screen_images(host, batch, context), ())
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertTrue(row["error_code"].startswith("screen_adoption_unavailable:"))
        self.assertIsNotNone(row["receipt_ref"])
        self.assertEqual(self.runtime.read_one(
            "SELECT state FROM sources WHERE source_id = ?", ("native:" + row["invocation_id"],))[0],
            "revoked")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM screen_captures", ())[0], 0)

    async def test_final_host_guard_failure_rolls_back_screen_publication(self):
        original_guard = self.native_registry._guard

        def guard_after_publication(host_tool_id, invocation):
            if self.runtime.read_one("SELECT capture_id FROM screen_captures LIMIT 1", ()):
                raise TaskError("capability_consent_revoked", "synthetic final guard failure")
            return original_guard(host_tool_id, invocation)

        with patch.object(self.native_registry, "_guard", side_effect=guard_after_publication):
            host, batch, context = await self.complete_screen()
        self.assertEqual(self.captures, 1)
        self.assertEqual(self.called[-1].original.images, ())
        self.assertEqual(self.screen_images(host, batch, context), ())
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM screen_captures", ())[0], 0)
        self.assertEqual(self.runtime.read_one(
            "SELECT COUNT(*) FROM sources WHERE source_id LIKE 'screen-source-%'", ())[0], 0)
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "committed"))
        self.assertEqual(row["error_code"], "screen_adoption_unavailable:capability_consent_revoked")
        self.assertIsNotNone(row["receipt_ref"])
        self.assertEqual(self.runtime.read_one(
            "SELECT state FROM sources WHERE source_id = ?", ("native:" + row["invocation_id"],))[0],
            "revoked")

    async def test_restart_reads_original_receipt_without_recapture(self):
        host, batch, context = await self.complete_screen()
        receipt = tuple(self.runtime.read_one(
            "SELECT operation_id, receipt_ref FROM extension_tool_invocations", ()))
        new = await self.restart_screen(host)
        restored = self.context(new.application, batch)
        self.assertEqual(restored.key, context.key)
        self.assertEqual(self.screen_images(new, batch, restored)[0].descriptor.content_hash,
                         self.called[-1].original.images[0].descriptor.content_hash)
        self.assertEqual(tuple(new.application.runtime.read_one(
            "SELECT operation_id, receipt_ref FROM extension_tool_invocations", ())), receipt)
        self.assertEqual(self.captures, 1)

    async def test_unknown_capture_is_not_replayed_after_restart(self):
        self.capture_error = TimeoutError("synthetic capture result unknown")
        host, batch, _ = await self.complete_screen()
        self.assertEqual(self.captures, 1)
        self.assertEqual(self.called[-1].original.images, ())
        self.assertEqual(self.runtime.read_one(
            "SELECT state FROM extension_tool_invocations", ())[0], "unknown")
        with self.screen_provider._connect() as connection:
            request = json.loads(connection.execute(
                "SELECT request_json FROM operations", ()).fetchone()[0])
        new = await self.restart_screen(host)
        self.capture_error = None
        replay = await self.screen_provider.execute(request, before_dispatch=lambda: None)
        self.assertEqual(replay["state"], "unknown")
        self.assertEqual(new.receive(self.event()).unwrap(), batch)
        self.assertEqual(self.captures, 1)

    async def test_shared_media_budget_omits_additional_capture(self):
        host, batch, context = await self.complete_screen()
        existing = tuple(SimpleNamespace(descriptor=ImageDescriptor(
            index, "image/jpeg", 8, 8, 4 * 1024 * 1024,
            f"{index + 1:064x}")) for index in range(5))
        request = SimpleNamespace(event=SimpleNamespace(scope=SCOPE), images=existing,
                                  videos=(), audios=())
        self.assertEqual(self.screen_images(host, batch, context, request), ())
        self.assertEqual(self.captures, 1)


if __name__ == "__main__":
    unittest.main()
