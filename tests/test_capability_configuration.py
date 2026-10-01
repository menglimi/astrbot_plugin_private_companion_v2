from __future__ import annotations

from datetime import timedelta
import asyncio
import hashlib
import sqlite3

from companion_v2.capabilities import CapabilityRepository
from companion_v2.capabilities.configuration import CapabilityConfigurationOwner
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.configuration.service import ConfigurationService
from companion_v2.foundation.refs import AssetRef, AudienceRef, OperationRef, SourceRef, VersionRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.screen import (
    SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ, ScreenCapture, ScreenCaptureRef,
    ScreenCoverage, ScreenFeedbackKind, ScreenInterpretation, ScreenMediaKind,
    ScreenProcessingPipeline, ScreenRepository,
)
from companion_v2.sources import AssetRecord, AssetRepository, SourceRecord, SourceRepository
from companion_v2.storage.repositories import OperationRepository

from tests.g6_support import G6Fixture, NOW


class ProactiveLocalRole:
    def interpret(self, request):
        return ScreenInterpretation("A synthetic window label is available.", request.input_units, ScreenFeedbackKind.PROACTIVE)


class CapabilityConfigurationTests(G6Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.enable_screen()
        self.identities = PersistentIdentityDirectory(self.runtime)
        self.identities.bind(binding_id="binding-a", principal=self.principal, subject=self.subject,
                             valid_from=NOW, expected_revision=1)
        for capability in (SCREEN_READ, SCREEN_PROCESS, "configuration.read", "configuration.write"):
            self.identities.issue_grant(
                grant_id=f"grant-{capability}", subject=self.subject, scope=self.scope,
                capability=capability, tier=AuthorizationTier.CORE, valid_from=NOW,
                expected_revision=self.identities.revision,
            )
        self.resolved = self.identities.resolve_authenticated(self.principal, observed_at=NOW).unwrap()
        self.owner = CapabilityConfigurationOwner(self.runtime, extension_id=SCREEN_EXTENSION)
        self.service = ConfigurationService(
            self.runtime, FieldRegistry(version="capability-config.v1", fields=self.owner.fields), owners=(self.owner,),
        )
        self.target = ConfigTarget(self.scope.installation_id, ConfigLayer.SCOPE, scope=self.scope)
        self.sequence = 0

    def read(self):
        return self.service.read(self.resolved, target=self.target, group_id=self.owner.group_id, observed_at=NOW).unwrap()

    def save(self, changes, *, snapshot=None, reset=()):
        self.sequence += 1
        snapshot = snapshot or self.read()
        operation = OperationRef(f"configuration-{self.sequence}", self.owner.owner_id, self.scope,
                                 VersionRef(f"configuration-lineage-{self.sequence}", 1), f"config-key-{self.sequence}")
        return self.service.patch(self.resolved, target=self.target, group_id=self.owner.group_id,
                                  operation=operation, expected_edit_token=snapshot.edit_token,
                                  changes=changes, reset_to_inherit=reset, observed_at=NOW)

    def test_management_and_furniture_use_existing_owner_without_duplicate_values(self):
        self.capabilities.set_settings(extension_id=SCREEN_EXTENSION, scope=self.scope, proactive_enabled=True,
                                       thought_weight=1 / 3, expected_revision=0, observed_at=NOW).unwrap()
        self.assertEqual(self.read().values[self.owner.weight_key], 1 / 3)
        self.save({self.owner.enabled_key: False}).unwrap()
        furniture = self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role, scope=self.scope).unwrap()
        self.assertFalse(furniture.settings.proactive_enabled)
        self.assertEqual(furniture.settings.thought_weight, 1 / 3)
        self.assertEqual(furniture.settings.revision, self.read().revision)
        self.assertEqual(self.runtime.read_all("SELECT * FROM configuration_values", ()), ())
        self.assertTrue(self.read().fields[self.owner.enabled_key].explicit)

    def test_owner_write_and_common_receipt_roll_back_together(self):
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TRIGGER reject_capability_config BEFORE INSERT ON configuration_changes
                                  BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.save({self.owner.enabled_key: True})
        self.assertIsNone(self.capabilities.projection(extension_id=SCREEN_EXTENSION, scope=self.scope).unwrap().settings)
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_internal_owner_change_invalidates_stale_page_without_shadow_copy(self):
        old = self.read()
        self.capabilities.set_settings(extension_id=SCREEN_EXTENSION, scope=self.scope, proactive_enabled=False,
                                       thought_weight=10, expected_revision=0, observed_at=NOW).unwrap()
        self.assertEqual(self.save({self.owner.weight_key: 2}, snapshot=old).failure.code, "configuration_revision_conflict")
        self.assertEqual(self.read().values[self.owner.weight_key], 10)

    def test_discard_fences_late_page_and_scope_preferences_do_not_fake_inheritance(self):
        old = self.read()
        self.assertEqual(self.save({}, reset=(self.owner.weight_key,)).failure.code, "configuration_inheritance_not_supported")
        self.capabilities.request_discard(extension_id=SCREEN_EXTENSION, expected_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.save({self.owner.enabled_key: True}, snapshot=old).failure.code, "configuration_revision_conflict")
        self.assertFalse(self.save({self.owner.enabled_key: True}).is_success)
        self.assertEqual(self.read().values[self.owner.enabled_key], False)
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_restart_recovers_same_owner_and_bounded_change_notification(self):
        receipt = self.save({self.owner.weight_key: 2.5}).unwrap()
        self.assertEqual(set(receipt.changed_fields), {self.owner.enabled_key, self.owner.weight_key})
        self.runtime.close()
        runtime = self.open_runtime()
        owner = CapabilityConfigurationOwner(runtime, extension_id=SCREEN_EXTENSION)
        service = ConfigurationService(runtime, FieldRegistry(version="capability-config.v1", fields=owner.fields), owners=(owner,))
        restored = service.read(self.resolved, target=self.target, group_id=owner.group_id, observed_at=NOW).unwrap()
        self.assertEqual(restored.values[owner.weight_key], 2.5)
        feed = service.changes_since(self.resolved, target=self.target, group_id=owner.group_id, after=0, observed_at=NOW).unwrap()
        self.assertEqual(len(feed.sequences), 1)
        self.assertEqual(CapabilityRepository(runtime).projection(extension_id=SCREEN_EXTENSION, scope=self.scope).unwrap().settings.thought_weight, 2.5)

    def test_missing_or_foreign_storage_owner_is_rejected_at_assembly(self):
        fields = FieldRegistry(version="capability-config.v1", fields=self.owner.fields)
        with self.assertRaises(ValueError):
            ConfigurationService(self.runtime, fields)
        other_owner = CapabilityConfigurationOwner(self.open_runtime(), extension_id=SCREEN_EXTENSION)
        with self.assertRaises(ValueError):
            ConfigurationService(self.runtime, fields, owners=(other_owner,))

    def test_screen_reads_the_setting_saved_through_shared_service(self):
        self.identities.bind_role(scope=self.scope, role=self.role, expected_revision=0)
        screens = ScreenRepository(self.runtime, authorizer=self.identities)
        reference = ScreenCaptureRef(
            "capture-config", SourceRef("source-config", "screen", self.scope, VersionRef("source-lineage", 1), NOW, NOW + timedelta(hours=1)),
            AssetRef("asset-config", "screen", self.scope, VersionRef("asset-lineage", 1), "fixture-pixels"),
        )
        text = "synthetic screen material"
        SourceRepository(self.runtime).publish(SourceRecord(reference.source, AudienceRef(self.scope, (self.subject,)),
                                             hashlib.sha256(text.encode("utf-8")).hexdigest(), text), observed_at=NOW).unwrap()
        AssetRepository(self.runtime).publish(AssetRecord(reference.asset, AudienceRef(self.scope, (self.subject,))), observed_at=NOW).unwrap()
        capture = ScreenCapture(reference, "fixture-device", ScreenMediaKind.IMAGE,
                                ScreenCoverage("fixture-window", ("window.title",), ()), NOW, NOW, NOW)
        screens.register_capture(capture, role=self.role, resolved=self.resolved, observed_at=NOW).unwrap()
        pipeline = ScreenProcessingPipeline(screens=screens, operations=OperationRepository(self.runtime),
                                            role_port=ProactiveLocalRole(), now=lambda: NOW)

        def process(request_id):
            return asyncio.run(pipeline.process(request_id=request_id, capture=reference, role=self.role,
                                    role_instruction="Role fixture.", purpose="Read the synthetic title.",
                                    input_units=("window.title",), processor_id="fixture-role", resolved=self.resolved))

        self.assertEqual(process("before-enable").failure.code, "screen_proactive_disabled")
        self.save({self.owner.enabled_key: True}).unwrap()
        self.assertEqual(process("after-enable").unwrap().result.anchor.kind, ScreenFeedbackKind.PROACTIVE)
        self.save({self.owner.enabled_key: False}).unwrap()
        self.assertEqual(process("after-disable").failure.code, "screen_proactive_disabled")
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())
