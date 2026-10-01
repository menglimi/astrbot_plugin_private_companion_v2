from dataclasses import replace
from unittest.mock import patch

from companion_v2.capabilities import (
    CapabilityAuthorizationState, CapabilityDesiredState, CapabilityRepository, FurnitureAvailability,
)
from companion_v2.foundation.refs import ReferenceValidationError, SubjectKind, SubjectRef
from companion_v2.screen.models import SCREEN_EXTENSION, SCREEN_READ

from tests.g6_support import G6Fixture, INSTALLATION, NOW, descriptor


class CapabilityTests(G6Fixture):
    def test_catalog_and_installation_do_not_grant_role_or_consent(self) -> None:
        self.capabilities.register_descriptor(descriptor(), registered_at=NOW).unwrap()
        self.assertEqual(self.capabilities.projections().unwrap(), ())
        self.install()
        projection = self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role).unwrap()
        self.assertIsNone(projection.role_selection)
        self.assertEqual(projection.furniture[0].availability, FurnitureAvailability.ACQUIRED)
        self.assertEqual(self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role).failure.code, "capability_role_not_enabled")
        self.assertEqual(self.access().failure.code, "capability_consent_missing")

    def test_restart_preserves_role_settings_consent_and_shared_projection(self) -> None:
        self.enable_screen()
        self.capabilities.set_settings(
            extension_id=SCREEN_EXTENSION, scope=self.scope, proactive_enabled=False,
            thought_weight=73, expected_revision=0, observed_at=NOW,
        ).unwrap()
        before = self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role, scope=self.scope).unwrap()
        authorization = self.access().unwrap()
        self.runtime.close()
        self.capabilities = CapabilityRepository(self.open_runtime())
        self.assertEqual(self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role, scope=self.scope).unwrap(), before)
        self.assertEqual(self.capabilities.projections().unwrap()[0].furniture, before.furniture)
        self.assertEqual(self.access().unwrap(), authorization)
        self.assertTrue(self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role).is_success)

    def test_pause_preserves_choices_revoke_works_and_acquire_cannot_resume(self) -> None:
        self.enable_screen()
        self.capabilities.pause(extension_id=SCREEN_EXTENSION, expected_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.access().failure.code, "capability_not_admissible")
        selected = descriptor()
        self.assertEqual(self.capabilities.acquire(
            extension_id=SCREEN_EXTENSION, package_id=selected.package_id, package_version=selected.package_version,
            expected_revision=2, observed_at=NOW,
        ).unwrap().desired_state, CapabilityDesiredState.PAUSED)
        self.revoke()
        self.capabilities.resume(extension_id=SCREEN_EXTENSION, expected_revision=2, observed_at=NOW).unwrap()
        self.assertEqual(self.access().failure.code, "capability_consent_revoked")
        self.assertTrue(self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role).is_success)

    def test_discard_blocks_late_update_and_reacquire_restores_choices_not_consent(self) -> None:
        self.enable_screen()
        self.capabilities.register_descriptor(descriptor("2.0.0"), registered_at=NOW).unwrap()
        self.capabilities.request_discard(extension_id=SCREEN_EXTENSION, expected_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.capabilities.projections().unwrap()[0].furniture[0].availability, FurnitureAvailability.REMOVING)
        self.assertEqual(self.capabilities.update(
            extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id, package_version="2.0.0",
            expected_revision=1, observed_at=NOW,
        ).failure.code, "capability_revision_conflict")
        self.runtime.close()
        self.capabilities = CapabilityRepository(self.open_runtime())
        self.revoke()
        removed = self.capabilities.complete_discard(extension_id=SCREEN_EXTENSION, expected_revision=2, observed_at=NOW).unwrap()
        self.assertEqual(removed.retained_dataset_owners, ("screen",))
        self.assertEqual(self.capabilities.projections().unwrap()[0].furniture, ())
        self.assertEqual(self.capabilities.acquire(
            extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id, package_version="1.0.0",
            expected_revision=0, observed_at=NOW,
        ).failure.code, "capability_revision_conflict")
        restored = self.capabilities.acquire(
            extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id, package_version="2.0.0",
            expected_revision=3, observed_at=NOW,
        ).unwrap()
        self.assertEqual(restored.retained_dataset_owners, ("screen",))
        self.assertEqual(restored.acquired_at, removed.acquired_at)
        self.assertTrue(self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role).is_success)
        self.assertEqual(self.access().failure.code, "capability_consent_revoked")

    def test_update_keeps_furniture_identity_and_rejects_publisher_or_dataset_takeover(self) -> None:
        self.enable_screen()
        original = self.capabilities.projections().unwrap()[0]
        self.capabilities.register_descriptor(descriptor("2.0.0"), registered_at=NOW).unwrap()
        updated = self.capabilities.update(
            extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id, package_version="2.0.0",
            expected_revision=1, observed_at=NOW,
        ).unwrap()
        projected = self.capabilities.projections().unwrap()[0]
        self.assertEqual(projected.installation, updated)
        self.assertEqual(projected.furniture[0].furniture, original.furniture[0].furniture)
        for change in (
            {"publisher_id": "other"}, {"package_id": "other"},
            {"dataset_owners": ("memory",)}, {"furniture": ()},
        ):
            with self.subTest(change=change):
                result = self.capabilities.register_descriptor(replace(descriptor("3.0.0"), **change), registered_at=NOW)
                self.assertEqual(result.failure.code, "capability_identity_conflict")
        self.assertEqual(self.capabilities.register_descriptor(
            replace(descriptor("2.0.0"), artifact_hash="different"), registered_at=NOW,
        ).failure.code, "capability_descriptor_conflict")

    def test_scope_role_isolation_and_cas_do_not_change_other_choices(self) -> None:
        self.enable_screen()
        foreign_role = replace(self.role, installation_id="other")
        with self.assertRaises(ReferenceValidationError):
            self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=foreign_role, enabled=False, expected_revision=1, observed_at=NOW)
        with self.assertRaises(ReferenceValidationError):
            self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=foreign_role)
        other_role = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b")
        self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=other_role, enabled=False, expected_revision=0, observed_at=NOW).unwrap()
        self.assertTrue(self.capabilities.require_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role).is_success)
        self.assertEqual(self.capabilities.authorize(
            extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ, subject=self.subject,
            scope=replace(self.scope, native_scope_id="private-b"),
        ).failure.code, "capability_consent_missing")
        self.revoke()
        result = self.capabilities.set_authorization(
            extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ, subject=self.subject, scope=self.scope,
            state=CapabilityAuthorizationState.ACTIVE, expected_revision=1, observed_at=NOW,
        )
        self.assertEqual(result.failure.code, "capability_authorization_revision_conflict")
        self.assertEqual(self.access().failure.code, "capability_consent_revoked")

    def test_two_managers_cannot_apply_an_update_after_another_discards(self) -> None:
        self.enable_screen()
        other = CapabilityRepository(self.open_runtime())
        self.capabilities.register_descriptor(descriptor("2.0.0"), registered_at=NOW).unwrap()
        seen = other.installation(extension_id=SCREEN_EXTENSION).unwrap()
        self.capabilities.request_discard(extension_id=SCREEN_EXTENSION, expected_revision=seen.revision, observed_at=NOW).unwrap()
        result = other.update(
            extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id,
            package_version="2.0.0", expected_revision=seen.revision, observed_at=NOW,
        )
        self.assertEqual(result.failure.code, "capability_revision_conflict")
        self.assertEqual(other.projections().unwrap()[0].installation.desired_state, CapabilityDesiredState.DISCARD_REQUESTED)

    def test_projection_keeps_one_snapshot_during_another_connection_update(self) -> None:
        self.enable_screen()
        other = CapabilityRepository(self.open_runtime())
        self.capabilities.register_descriptor(descriptor("2.0.0"), registered_at=NOW).unwrap()
        original_read = self.capabilities._current_descriptor
        def concurrent_change(extension_id):
            other.update(
                extension_id=SCREEN_EXTENSION, package_id=descriptor().package_id,
                package_version="2.0.0", expected_revision=1, observed_at=NOW,
            ).unwrap()
            other.set_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role, enabled=False, expected_revision=1, observed_at=NOW).unwrap()
            return original_read(extension_id)
        with patch.object(self.capabilities, "_current_descriptor", side_effect=concurrent_change):
            snapshot = self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role).unwrap()
        self.assertEqual(snapshot.installation.package_version, "1.0.0")
        self.assertEqual(snapshot.furniture[0].installed_revision, 1)
        self.assertTrue(snapshot.role_selection.enabled)
        latest = self.capabilities.projection(extension_id=SCREEN_EXTENSION, role=self.role).unwrap()
        self.assertEqual(latest.installation.package_version, "2.0.0")
        self.assertFalse(latest.role_selection.enabled)

    def access(self):
        return self.capabilities.authorize(
            extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ, subject=self.subject, scope=self.scope,
        )

    def revoke(self) -> None:
        self.capabilities.set_authorization(
            extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ, subject=self.subject, scope=self.scope,
            state=CapabilityAuthorizationState.REVOKED, expected_revision=1, observed_at=NOW,
        ).unwrap()
