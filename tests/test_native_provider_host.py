"""Native discovery wired into real V2 authorization and supervised child tasks."""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from astrbot_host.native_extensions import NativeExtensionRegistry
from companion_v2.capabilities import native_reads
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import encode
from companion_v2.model_gateway.models import ToolCall
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_native_extensions_registry import Context, Port, Star
from tests.test_role_tool_loop import answered, requested


class NativeProviderHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.port = Port()
        self.port.with_artifact = False
        self.port.document["tools"][0]["action"] = "native.test.run"
        self.native_context = Context(Star(self.port))
        self.native_registry = NativeExtensionRegistry(self.native_context, result_handlers={}, now=self.clock.now)
        self.addCleanup(self.native_registry.close)
        self.capabilities = CapabilityRepository(self.runtime)
        self.package = self.native_registry.declarations()[0].descriptor.package

    def native_host(self):
        return self.host(tool_port=self.native_registry, policy=ConversationPolicy(0, 0, 180, 0))

    def authorize(self):
        self.native_registry.register_catalog(observed_at=NOW).unwrap()
        p = self.package
        self.capabilities.acquire(extension_id=p.extension_id, package_id=p.package_id,
            package_version=p.package_version, expected_revision=0, observed_at=NOW).unwrap()
        self.capabilities.set_role_enabled(extension_id=p.extension_id, role=self.window.role,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        self.capabilities.set_authorization(extension_id=p.extension_id, capability_id="image.generate",
            subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE,
            expected_revision=0, observed_at=NOW).unwrap()

    async def invoke(self, prepare=None):
        host = self.native_host()
        self.authorize()
        self.port.prepare = prepare
        async def model(envelope):
            return (requested(ToolCall("native-call", "native.test.run", encode({"prompt": "sunset"})))
                    if not envelope.tool_history else answered("实际扩展确认已读取。"))
        self.model_behavior = model
        await self.start(host)
        batch = host.receive(self.event()).unwrap()
        await self.done(host.application, batch)
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        self.assertIsNotNone(row)
        return host, batch, row

    async def test_catalog_is_explicit_and_never_grants_access(self):
        host = self.native_host()
        self.assertEqual(self.capabilities.descriptors(extension_id="image"), ())
        p = self.native_registry.register_catalog(observed_at=NOW).unwrap()
        self.assertEqual(p, (self.package,))
        self.assertFalse(self.capabilities.installation(extension_id="image").is_success)
        self.assertEqual(self.runtime.read_all("SELECT * FROM capability_authorizations", ()), ())
        await self.start(host)
        batch = host.receive(self.event()).unwrap()
        await self.done(host.application, batch)
        self.assertNotIn("native.test.run", {t.action for t in self.called[0].tools})
        self.assertEqual(self.port.before, 0)

    async def test_stale_catalog_cannot_register_replaced_instance(self):
        self.native_host()
        self.native_context.star.star_cls = SimpleNamespace(extension_api=self.native_context.star.star_cls.extension_api)
        result = self.native_registry.register_catalog(observed_at=NOW)
        self.assertEqual(result.failure.code, "native_provider_changed")
        self.assertEqual(self.capabilities.descriptors(extension_id="image"), ())

    async def test_catalog_conflict_rolls_back_other_packages(self):
        port = Port()
        port.document["plugin_id"] = "zz_native_test"
        port.document["package"].update(extension_id="second", package_id="zz_native_test")
        port.document["tools"][0]["action"] = "second.generate"
        star = Star(port)
        star.root_dir_name = "zz_native_test"
        context = SimpleNamespace(get_all_stars=lambda: (self.native_context.star, star))
        registry = NativeExtensionRegistry(context)
        self.addCleanup(registry.close)
        host = self.host(tool_port=registry)
        package = registry.declarations()[-1].descriptor.package
        self.capabilities.register_descriptor(replace(package, artifact_hash="old-package"), registered_at=NOW).unwrap()
        result = registry.register_catalog(observed_at=NOW)
        self.assertEqual(result.failure.code, "capability_descriptor_conflict")
        self.assertEqual(self.capabilities.descriptors(extension_id="image"), ())

    async def test_dispatch_keeps_original_task_audience_and_receipt(self):
        host, batch, row = await self.invoke()
        self.assertEqual((row["state"], row["effect"], row["operation_id"]), ("succeeded", "committed", "op-1"))
        self.assertEqual(self.port.before, 1)
        self.assertTrue(host.application.external)
        self.assertEqual(len(self.sent), 1, dict(host.application.flow.row(batch)))

    async def test_consent_revocation_during_provider_wait_stops_effect(self):
        async def revoke():
            await asyncio.sleep(0)
            self.capabilities.set_authorization(extension_id="image", capability_id="image.generate",
                subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.REVOKED,
                expected_revision=1, observed_at=NOW).unwrap()
        _, _, row = await self.invoke(revoke)
        self.assertEqual(self.port.before, 0)
        self.assertEqual(row["state"], "unknown")

    async def test_a_read_only_provider_result_is_checked_by_its_domain_reader(self):
        """A Live read reaches its reader through the same host path as any native tool."""
        self.port.document["tools"] = [{
            "action": "live.events.recent", "capability": "live.events.recent", "source_owner": "live.native",
            "description": "recent events", "side_effect": "none", "timeout_seconds": 10,
            "parameters": {"type": "object", "properties": {"platform": {"type": "string"},
                "limit": {"type": "integer"}, "after_event_id": {"type": "string"}},
                "required": ["platform", "limit"], "additionalProperties": False}}]
        self.port.document["package"]["capabilities"] = ["live.events.recent"]
        self.port.document["package"]["dataset_owners"] = ["live.native"]
        self.port.result = {"platform": "bilibili",
                            "events": [{"event_id": "e-1", "text": "观众原话", "trust": "untrusted"}]}
        # A read-only declaration answers with no effect and no operation id.
        self.port.effect = "none"
        self.port.operation_id = None
        self.native_registry = NativeExtensionRegistry(self.native_context, now=self.clock.now)
        self.addCleanup(self.native_registry.close)
        host = self.native_host()
        self.native_registry.register_catalog(observed_at=NOW).unwrap()
        package = self.native_registry.declarations()[0].descriptor.package
        self.capabilities.acquire(extension_id=package.extension_id, package_id=package.package_id,
            package_version=package.package_version, expected_revision=0, observed_at=NOW).unwrap()
        self.capabilities.set_role_enabled(extension_id=package.extension_id, role=self.window.role,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        self.capabilities.set_authorization(extension_id=package.extension_id, capability_id="live.events.recent",
            subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE,
            expected_revision=0, observed_at=NOW).unwrap()
        async def model(envelope):
            return (requested(ToolCall("live-call", "live.events.recent", encode({"platform": "bilibili", "limit": 5})))
                    if not envelope.tool_history else answered("已读到直播事件。"))
        self.model_behavior = model
        await self.start(host)
        batch = host.receive(self.event()).unwrap()
        await self.done(host.application, batch)
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations", ())
        self.assertEqual((row["state"], row["effect"]), ("succeeded", "none"))
        journal = native_reads.NativeReadJournal(self.runtime, context=self.context(host.application, batch))
        self.assertEqual(journal.read("bilibili")["delivered"], ["e-1"])

    async def test_role_disable_during_wait_stops_effect(self):
        async def disable():
            await asyncio.sleep(0)
            self.capabilities.set_role_enabled(extension_id="image", role=self.window.role, bot_id=SCOPE.bot_id,
                enabled=False, expected_revision=1, observed_at=NOW).unwrap()
        _, _, row = await self.invoke(disable)
        self.assertEqual((row["state"], self.port.before), ("unknown", 0))

    async def test_package_pause_during_wait_stops_effect(self):
        async def pause():
            await asyncio.sleep(0)
            self.capabilities.pause(extension_id="image", expected_revision=1, observed_at=NOW).unwrap()
        _, _, row = await self.invoke(pause)
        self.assertEqual((row["state"], self.port.before), ("unknown", 0))

    def assert_unavailable_receipt(self, row):
        self.assertEqual((row["state"], row["effect"], row["operation_id"], row["receipt_ref"]),
                         ("succeeded", "committed", "op-1", "receipt-1"))
        reference = json.loads(row["result_source_json"])
        source = self.runtime.read_one("SELECT state, payload_json FROM sources WHERE source_id = ?",
                                       (reference["source_id"],))
        self.assertEqual(source["state"], "revoked")
        self.assertEqual(json.loads(json.loads(source["payload_json"]))["native"]["operation_id"], "op-1")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM conversation_image_payloads", ())[0], 0)

    async def test_consent_revocation_after_effect_keeps_receipt_and_never_replays(self):
        def revoke(request):
            self.capabilities.set_authorization(extension_id="image", capability_id="image.generate",
                subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.REVOKED,
                expected_revision=1, observed_at=NOW).unwrap()
        self.port.after = revoke
        host, batch, row = await self.invoke()
        self.assert_unavailable_receipt(row)
        self.assertEqual(self.sent, [])
        self.assertEqual(host.receive(self.event()).unwrap(), batch)
        self.assertEqual(self.port.before, 1)

    async def test_instance_replacement_after_effect_keeps_original_receipt(self):
        self.port.after = lambda request: setattr(self.native_context, "star", Star(Port()))
        _, _, row = await self.invoke()
        self.assert_unavailable_receipt(row)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.port.before, 1)

    async def test_corrupt_artifact_preserves_receipt_without_adoption(self):
        self.port.with_artifact = True
        async def corrupt():
            await asyncio.sleep(0)
            self.port.content = b"BAD"
        self.port.prepare_read = corrupt
        _, _, row = await self.invoke()
        self.assert_unavailable_receipt(row)
        self.assertEqual(self.port.before, 2)

    async def test_mismatched_receipt_remains_unknown_without_success_material(self):
        self.port.after = lambda request: request.update(origin_key="wrong-context")
        _, _, row = await self.invoke()
        self.assertEqual((row["state"], row["effect"]), ("unknown", "unknown"))
        self.assertIsNone(row["result_source_json"])
        self.assertEqual(self.port.before, 1)


if __name__ == "__main__":
    unittest.main()
