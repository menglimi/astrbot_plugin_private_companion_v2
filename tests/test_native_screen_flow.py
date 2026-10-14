"""Native Screen capture through the V2 host, using synthetic JPEG bytes only."""

import base64
from dataclasses import replace
from datetime import timedelta
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
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskError
from companion_v2.model_gateway.models import ToolCall
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.proactive.configuration import target_for
from companion_v2.proactive.diagnostic_models import DiagnosticSourceError
from companion_v2.proactive.service import contact_profile
from companion_v2.product import PRODUCT_VERSION
from companion_v2.screen import SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ, ScreenOriginalStore
from companion_v2.screen.interpretation import screen_interpretation_profile
from companion_v2.screen.review import ScreenObservationReview
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

    async def diagnostic_host(self):
        self.profiles += (contact_profile("primary", max_output_tokens=100),
                          screen_interpretation_profile("primary", max_output_tokens=100))
        self.registry = FieldRegistry(version="screen-diagnostic.v1", fields=configuration_fields(self.profiles))
        self.grant(self.important, SCOPE, "extension.tool.invoke")
        self.grant(self.important, SCOPE, "proactive.contact")

        async def respond(envelope):
            if envelope.original.output_format == "screen_interpretation":
                return answered('{"interpretation":"画面里有绿色图案。"}')
            if envelope.original.output_format == "proactive_contact":
                return answered('{"decision":"send","text":"这个绿色图案看起来很清爽。"}')
            return answered("收到。")

        self.model_behavior = respond
        host = await self.screen_host()
        app = host.application
        batch = host.receive(self.event()).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        for group, target, changes in (
            ("screen", ConfigTarget(SCOPE.installation_id, ConfigLayer.WINDOW, self.window.role, SCOPE),
                {"interpretation_enabled": True}),
            ("proactive.contact", target_for(context),
                {"enabled": True, "automatic_enabled": False, "screen.enabled": True, "screen_glance_enabled": True}),
        ):
            snapshot = app.configuration.read(self.important, target=target, group_id=group,
                                              observed_at=self.clock.now()).unwrap()
            app.configuration.patch(self.important, target=target, group_id=group,
                expected_edit_token=snapshot.edit_token, changes={group + "." + key: value for key, value in changes.items()},
                operation=self.operation(target.authorization_scope, owner=group), observed_at=self.clock.now()).unwrap()
        return app, context

    async def test_screen_diagnostic_captures_and_interprets_its_new_original_then_delivers(self):
        app, context = await self.diagnostic_host()
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM capability_settings WHERE extension_id = ?",
                                               (SCREEN_EXTENSION,)))
        events = app.contact_schedule.screen_events
        original_instruction = "\n原角色设定\n"
        old, _ = await events.diagnostic(context, app.screen_peek, test_id="old-test", role_instruction=original_instruction)
        candidate = await app.contact_schedule.diagnostic_candidate(context, "screen", test_id="new-test")
        self.assertEqual(self.captures, 2)
        old_capture = old[2]["capture_id"]
        new_capture = candidate["diagnostic_origin"]["screen_event"]["capture_id"]
        self.assertNotEqual(new_capture, old_capture, "existing analysis cannot substitute for a new screen test")
        self.assertEqual([stage["stage"] for stage in candidate["stages"]], ["screen_capture", "screen_interpretation"])
        calls = [call.original for call in self.called if call.original.output_format == "screen_interpretation"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].role_instruction, original_instruction,
                         "the native persona fence requires the exact original including whitespace")
        self.assertEqual(base64.b64decode(calls[-1].images[0].data_base64), self.jpeg)
        result = await app.proactive.contact(context, candidate["opportunity"], candidate["intents"],
            role_instruction=candidate["role_instruction"], selection_seed="new-test", administrator_test=True,
            diagnostic_source_backed=True, diagnostic_origin=candidate["diagnostic_origin"])
        self.assertIsNone(result.failure, result.failure)
        task = result.unwrap().task
        await self.until(lambda: app.proactive.observe(context, task.task_id).unwrap()["delivery"] == "delivered")
        self.assertTrue(app.proactive.observe(context, task.task_id).unwrap()["receipt_ref"])

    async def test_visible_screen_contact_switch_overrides_legacy_feedback_setting(self):
        app, context = await self.diagnostic_host()
        self.capabilities.set_settings(extension_id=SCREEN_EXTENSION, scope=SCOPE, proactive_enabled=True,
                                      thought_weight=1.0, expected_revision=0, observed_at=self.clock.now()).unwrap()
        group, target = "proactive.contact", target_for(context)
        before = app.configuration.read(self.important, target=target, group_id=group,
                                        observed_at=self.clock.now()).unwrap()
        app.configuration.patch(self.important, target=target, group_id=group,
            expected_edit_token=before.edit_token, changes={group + ".screen_glance_enabled": False},
            operation=self.operation(target.authorization_scope, owner=group), observed_at=self.clock.now()).unwrap()
        self.assertFalse(app.screen_peek.ready(context, self.clock.now()))
        self.assertFalse(app.screen_interpretation._proactive_allowed(context))
        self.assertEqual(self.captures, 0)

    async def test_last_proactive_original_and_analysis_survive_reload_and_expiry(self):
        app, context = await self.diagnostic_host()
        marker, _ = await app.contact_schedule.screen_events.diagnostic(context, app.screen_peek,
            test_id="retained-test", role_instruction="\n原角色设定\n")
        review = ScreenObservationReview(app, context)
        saved = review.latest(self.core, self.clock.now())["observation"]
        self.assertEqual(saved["capture_id"], marker[2]["capture_id"])
        self.assertEqual(saved["analysis"]["text"], "画面里有绿色图案。")
        with self.assertRaises(TaskError) as denied:
            review.latest(self.important, self.clock.now())
        self.assertEqual(denied.exception.code, "core_access_required")
        calls_before = len(self.called)
        host = await self.restart_screen(SimpleNamespace(application=app))
        self.clock.advance(timedelta(minutes=31))
        restored = ScreenObservationReview(host.application, context)
        self.assertEqual(restored.latest(self.core, self.clock.now())["observation"], saved)
        original = restored.original(self.core, self.clock.now(), saved["capture_id"])
        self.assertEqual(base64.b64decode(original["data_url"].split(",", 1)[1]), sample_jpeg())
        self.assertEqual((self.captures, len(self.called)), (1, calls_before))
        CapabilityRepository(self.runtime).set_authorization(extension_id=SCREEN_EXTENSION,
            capability_id=SCREEN_READ, subject=self.important.subject, scope=SCOPE,
            state=CapabilityAuthorizationState.REVOKED, expected_revision=1,
            observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError):
            restored.latest(self.core, self.clock.now())
        self.assertTrue(ScreenOriginalStore(self.runtime.data_root)._path(saved["content_hash"]).is_file())

    async def test_new_failed_analysis_keeps_new_original_and_never_uses_previous_result(self):
        from companion_v2.model_gateway.models import Amount, ProviderResponse
        app, context = await self.diagnostic_host()
        events = app.contact_schedule.screen_events
        await events.diagnostic(context, app.screen_peek, test_id="good-review", role_instruction="原角色设定")
        previous = ScreenObservationReview(app, context).latest(self.core, self.clock.now())["observation"]

        async def not_started(envelope):
            return ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref="model:not-started")

        self.model_behavior = not_started
        self.clock.advance(timedelta(seconds=1))
        with self.assertRaises(DiagnosticSourceError):
            await events.diagnostic(context, app.screen_peek, test_id="failed-review", role_instruction="原角色设定")
        latest = ScreenObservationReview(app, context).latest(self.core, self.clock.now())["observation"]
        self.assertNotEqual(latest["capture_id"], previous["capture_id"])
        self.assertEqual(latest["analysis"]["state"], "failed")
        self.assertIsNone(latest["analysis"]["text"])
        self.assertEqual(self.captures, 2)
        with self.assertRaises(TaskError) as changed:
            ScreenObservationReview(app, context).original(self.core, self.clock.now(), previous["capture_id"])
        self.assertEqual(changed.exception.code, "screen_observation_changed")
        self.capture_error = RuntimeError("synthetic capture failure")
        self.clock.advance(timedelta(seconds=1))
        with self.assertRaises(DiagnosticSourceError):
            await events.diagnostic(context, app.screen_peek, test_id="device-failure", role_instruction="原角色设定")
        kept = ScreenObservationReview(app, context).latest(self.core, self.clock.now())
        self.assertEqual(kept["observation"]["capture_id"], latest["capture_id"])
        self.assertNotEqual(kept["latest_attempt"]["task_id"], latest["peek_task_id"])

    async def test_screen_diagnostic_rejects_text_only_primary_or_fallback_before_capture(self):
        primary = self.providers[0]
        self.providers += (replace(primary, binding=replace(primary.binding, provider="vision-fallback")),)
        app, context = await self.diagnostic_host()
        router = app.gateway.router
        target = ConfigTarget(SCOPE.installation_id, ConfigLayer.WINDOW, self.window.role, SCOPE)
        snapshot = app.configuration.read(self.important, target=target,
            group_id="model.screen.interpretation", observed_at=self.clock.now()).unwrap()
        app.configuration.patch(self.important, target=target, group_id="model.screen.interpretation",
            expected_edit_token=snapshot.edit_token,
            changes={"model.screen.interpretation.fallback": "vision-fallback"},
            operation=self.operation(target.authorization_scope, owner="configuration"),
            observed_at=self.clock.now()).unwrap()
        original = router.providers
        for provider_id in original:
            with self.subTest(provider=provider_id):
                router.providers = {identifier: replace(provider, capabilities=("text", "tools"))
                                    if identifier == provider_id else provider
                                    for identifier, provider in original.items()}
                with self.assertRaises(DiagnosticSourceError) as caught:
                    await app.contact_schedule.screen_events.diagnostic(context, app.screen_peek,
                        test_id="text-only-" + provider_id, role_instruction="原角色设定")
                error = caught.exception
                self.assertEqual((error.code, error.state, error.stage),
                                 ("model_capability_mismatch", "failed", "screen_interpretation"))
                self.assertIn("未采集截图", str(error))
                self.assertEqual(self.captures, 0)
                self.assertFalse(self.runtime.read_all(
                    "SELECT 1 FROM execution_tasks WHERE kind IN ('screen.peek', 'screen.interpretation')", ()))
                self.assertFalse(any(call.original.output_format == "screen_interpretation" for call in self.called))
        router.providers = original

    async def test_screen_diagnostic_unknown_device_is_visible_and_same_attempt_never_recaptures(self):
        app, context = await self.diagnostic_host()
        self.capture_error = OSError("device unavailable after dispatch")
        for index in range(2):
            with self.assertRaises(DiagnosticSourceError) as caught:
                await app.contact_schedule.screen_events.diagnostic(context, app.screen_peek,
                    test_id="unknown-test", role_instruction="原角色设定")
            if index == 0:
                self.assertEqual((caught.exception.state, caught.exception.stage), ("unknown", "screen_capture"))
        self.assertEqual(self.captures, 1)
        self.assertFalse(any(call.original.output_format == "screen_interpretation" for call in self.called))

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
