from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from companion_v2.capabilities import CapabilityAuthorizationState, CapabilityManagementService
from companion_v2.capabilities.configuration import CapabilityConfigurationOwner
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry, ValueKind
from companion_v2.configuration.service import ConfigurationService
from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.personas import ConversationRoute, PersonaBinding, PersonaDirectory, PersonaSelector, SelectorKind
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.screen.models import SCREEN_EXTENSION, SCREEN_READ
from companion_v2.storage.runtime import StorageRuntime
from tests.g6_support import descriptor


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "management-installation"
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a", "conversation-a", "session-a")


class ManagementFixture(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-management-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = self.open_runtime()
        self.identity = PersistentIdentityDirectory(self.runtime)
        self.policy = ObjectAccessPolicy(self.runtime)
        self.counter = 0
        self.core = self.person("core", AuthorizationTier.CORE)
        self.important = self.person("important", AuthorizationTier.IMPORTANT)
        self.standard = self.person("standard", AuthorizationTier.STANDARD)
        self.personas = PersonaDirectory(self.runtime)
        self.personas.register_route(ConversationRoute(SCOPE, user=self.important.subject), observed_at=NOW)
        self.personas.set_binding(PersonaBinding("base", PersonaSelector(INSTALLATION, SelectorKind.BOT, bot_id="bot-a"),
                                  ROLE, 0, NOW, "fixture", "admin"), expected_revision=0, observed_at=NOW)
        self.registry = FieldRegistry(version="management.v1", fields=(
            FieldDefinition("output.enabled", "output", "output", ValueKind.BOOLEAN, True),
            FieldDefinition("security.enabled", "security", "security", ValueKind.BOOLEAN, True, core_only=True),
        ))
        self.configuration = ConfigurationService(self.runtime, self.registry)
        self.window = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE)
        self.global_target = ConfigTarget(INSTALLATION, ConfigLayer.INSTALLATION)
        self.management = CapabilityManagementService(self.runtime)
        self.management.repository.register_descriptor(descriptor(), registered_at=NOW).unwrap()

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def person(self, name, tier):
        principal = AuthenticatedHostPrincipal(INSTALLATION, "host", "onebot", name, "bot-a", "login-a")
        subject = SubjectRef(INSTALLATION, SubjectKind.HUMAN, name)
        self.identity.bind(binding_id=name, principal=principal, subject=subject, valid_from=NOW,
                           expected_revision=self.identity.revision)
        self.policy.set_tier(subject, tier, expected_revision=self.policy.revision, observed_at=NOW)
        return self.identity.resolve_authenticated(principal, observed_at=NOW).unwrap()

    def grant(self, actor, scope, action, *, tier=AuthorizationTier.STANDARD, expires_at=None):
        self.counter += 1
        return self.identity.issue_grant(grant_id=f"grant-{self.counter}", subject=actor.subject, scope=scope,
            capability=action, tier=tier, valid_from=NOW, expires_at=expires_at, expected_revision=self.identity.revision)

    def operation(self, scope, *, owner="configuration"):
        self.counter += 1
        identifier = f"operation-{self.counter}"
        return OperationRef(identifier, owner, scope, VersionRef(identifier, 1), identifier)

    def read(self, actor, target=None, group="output", now=NOW):
        return self.configuration.read(actor, target=target or self.window, group_id=group, observed_at=now)

    def write(self, actor, snapshot, value=False, operation=None):
        return self.configuration.patch(actor, target=snapshot.target, group_id=snapshot.group_id,
            operation=operation or self.operation(snapshot.target.authorization_scope), expected_edit_token=snapshot.edit_token,
            changes={f"{snapshot.group_id}.enabled": value}, observed_at=NOW)

    def acquire(self, actor=None, *, operation=None, artifact_hash=None):
        selected = descriptor()
        return self.management.select_package(actor or self.core, extension_id=SCREEN_EXTENSION, action="acquire",
            package_id=selected.package_id, package_version=selected.package_version,
            artifact_hash=artifact_hash or selected.artifact_hash, expected_revision=0,
            operation=operation or self.operation(self.management.management_scope(SCREEN_EXTENSION), owner=self.management.OWNER),
            observed_at=NOW)


class ConfigurationAccessTests(ManagementFixture):
    def test_core_manages_explicit_target_without_grants_and_retains_identity_checks(self):
        for target in (self.global_target, self.window):
            snapshot = self.read(self.core, target, group="security").unwrap()
            self.write(self.core, snapshot).unwrap()
        other_role = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")
        current = self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap()
        self.identity.bind_role(scope=SCOPE, role=other_role, expected_revision=current.revision, observed_at=NOW)
        self.assertTrue(self.read(self.core).is_success)
        self.identity.revoke_binding(self.core.binding_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.read(self.core).failure.code, "binding_revoked")

    def test_important_owns_private_preferences_but_needs_delegation_for_other_scopes(self):
        self.write(self.important, self.read(self.important).unwrap()).unwrap()
        self.assertFalse(self.read(self.important, self.global_target).is_success)
        other = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b", session_id="session-b")
        self.personas.register_route(ConversationRoute(other, user=self.standard.subject), observed_at=NOW)
        target = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, other)
        self.assertFalse(self.read(self.important, target).is_success)
        delegated = self.grant(self.important, other, "configuration.read")
        self.assertTrue(self.read(self.important, target).is_success)
        self.identity.revoke_grant(delegated.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.read(self.important, target).failure.code, "authorization_revoked")

    def test_core_only_group_cannot_be_opened_by_a_grant_claiming_core_tier(self):
        for actor in (self.important, self.standard):
            self.grant(actor, SCOPE, "configuration.read", tier=AuthorizationTier.CORE)
            self.assertEqual(self.read(actor, group="security").failure.code, "core_access_required")
        self.assertTrue(self.read(self.standard).is_success)
        self.assertFalse(self.write(self.standard, self.read(self.standard).unwrap()).is_success)

    def test_downgrade_fences_old_edit_and_adoption_even_if_lower_tier_retains_access(self):
        snapshot = self.read(self.core).unwrap()
        self.grant(self.core, SCOPE, "configuration.read")
        self.grant(self.core, SCOPE, "configuration.write")
        snapshot = self.read(self.core).unwrap()
        other_policy = ObjectAccessPolicy(self.open_runtime())
        other_policy.set_tier(self.core.subject, AuthorizationTier.STANDARD,
                              expected_revision=other_policy.revision, observed_at=NOW)
        self.assertEqual(self.write(self.core, snapshot).failure.code, "configuration_revision_conflict")
        self.configuration.start_consumer("output", expected_generation=0)
        self.assertEqual(self.configuration.report_application(self.core, snapshot=snapshot, generation=1,
                         succeeded=True, observed_at=NOW).failure.code, "configuration_revision_conflict")

    def test_tier_change_restart_and_rebound_use_current_subject(self):
        self.runtime.close()
        runtime = self.open_runtime()
        service = ConfigurationService(runtime, self.registry)
        self.assertTrue(service.read(self.core, target=self.global_target, group_id="security", observed_at=NOW).is_success)
        identity = PersistentIdentityDirectory(runtime)
        identity.bind(binding_id="replacement", principal=self.core.principal, subject=self.standard.subject,
                      valid_from=NOW, expected_revision=identity.revision)
        self.assertEqual(service.read(self.core, target=self.window, group_id="output", observed_at=NOW).failure.code,
                         "binding_rebound")

    def test_capability_preferences_use_same_policy_and_existing_storage_owner(self):
        self.acquire().unwrap()
        owner = CapabilityConfigurationOwner(self.runtime, extension_id=SCREEN_EXTENSION)
        service = ConfigurationService(self.runtime, FieldRegistry(version="capabilities.v1", fields=owner.fields), owners=(owner,))
        target = ConfigTarget(INSTALLATION, ConfigLayer.SCOPE, scope=SCOPE)
        before = service.read(self.important, target=target, group_id=owner.group_id, observed_at=NOW).unwrap()
        service.patch(self.important, target=target, group_id=owner.group_id,
                      expected_edit_token=before.edit_token, changes={owner.enabled_key: True, owner.weight_key: 2.5},
                      operation=self.operation(SCOPE, owner=owner.owner_id), observed_at=NOW).unwrap()
        projection = self.management.repository.projection(extension_id=SCREEN_EXTENSION, scope=SCOPE).unwrap()
        self.assertEqual((projection.settings.proactive_enabled, projection.settings.thought_weight), (True, 2.5))
        self.assertEqual(self.runtime.read_all("SELECT * FROM configuration_values", ()), ())


class CapabilityManagementAccessTests(ManagementFixture):
    def test_lifecycle_requires_installation_core_not_capability_grant_tier(self):
        self.grant(self.standard, self.management.management_scope(SCREEN_EXTENSION), "capability.acquire", tier=AuthorizationTier.CORE)
        for actor in (self.important, self.standard):
            self.assertEqual(self.acquire(actor).failure.code, "core_access_required")
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())
        receipt = self.acquire().unwrap()
        self.assertEqual(receipt.effect, "local_record_saved")
        self.assertEqual(self.management.operations.pending_outbox(), ())

    def test_retry_keeps_original_local_receipt_without_reacquiring_after_pause(self):
        operation = self.operation(self.management.management_scope(SCREEN_EXTENSION), owner=self.management.OWNER)
        self.acquire(operation=operation).unwrap()
        self.management.change_lifecycle(self.core, extension_id=SCREEN_EXTENSION, action="pause", expected_revision=1,
            operation=self.operation(operation.scope, owner=self.management.OWNER), observed_at=NOW).unwrap()
        retry = self.acquire(operation=operation).unwrap()
        self.assertTrue(retry.replayed)
        self.assertEqual(self.management.repository.installation(extension_id=SCREEN_EXTENSION).unwrap().desired_state.value, "paused")
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.management = CapabilityManagementService(self.runtime)
        self.assertTrue(self.acquire(operation=operation).unwrap().replayed)

    def test_content_mismatch_or_persistence_failure_rolls_back_operation_and_choice(self):
        self.assertEqual(self.acquire(artifact_hash="different").failure.code, "capability_artifact_mismatch")
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TRIGGER reject_completion BEFORE UPDATE ON operations
                                  BEGIN SELECT RAISE(ABORT, 'completion fault'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.acquire()
        self.assertEqual(self.runtime.read_all("SELECT * FROM capability_installations", ()), ())
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_permission_is_rechecked_before_replay_or_late_lifecycle_write(self):
        operation = self.operation(self.management.management_scope(SCREEN_EXTENSION), owner=self.management.OWNER)
        self.acquire(operation=operation).unwrap()
        other_policy = ObjectAccessPolicy(self.open_runtime())
        other_policy.set_tier(self.core.subject, AuthorizationTier.IMPORTANT,
                              expected_revision=other_policy.revision, observed_at=NOW)
        self.assertEqual(self.acquire(operation=operation).failure.code, "core_access_required")
        result = self.management.change_lifecycle(self.core, extension_id=SCREEN_EXTENSION, action="discard.request",
            expected_revision=1, operation=self.operation(operation.scope, owner=self.management.OWNER), observed_at=NOW)
        self.assertEqual(result.failure.code, "core_access_required")
        self.assertEqual(self.management.repository.installation(extension_id=SCREEN_EXTENSION).unwrap().revision, 1)

    def test_consent_is_personal_and_does_not_grant_package_management_or_source_access(self):
        self.acquire().unwrap()
        def consent(actor, subject):
            return self.management.set_consent(actor, extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ,
                subject=subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE, expected_revision=0,
                operation=self.operation(SCOPE, owner=self.management.OWNER), observed_at=NOW)
        self.assertEqual(consent(self.important, self.standard.subject).failure.code, "object_access_denied")
        consent(self.important, self.important.subject).unwrap()
        self.assertFalse(self.identity.authorize(self.important, scope=SCOPE, capability=SCREEN_READ, observed_at=NOW).is_success)
        self.assertFalse(consent(self.standard, self.standard.subject).is_success)
        self.grant(self.standard, SCOPE, "capability.consent.set")
        consent(self.standard, self.standard.subject).unwrap()
        self.assertEqual(self.acquire(self.important).failure.code, "core_access_required")

    def test_projection_only_exposes_requested_authorized_scope(self):
        self.acquire().unwrap()
        self.assertTrue(self.management.projection(self.important, extension_id=SCREEN_EXTENSION,
                                                  scope=SCOPE, observed_at=NOW).is_success)
        group = replace(SCOPE, kind=ScopeKind.GROUP)
        self.assertFalse(self.management.projection(self.important, extension_id=SCREEN_EXTENSION,
                                                   scope=group, observed_at=NOW).is_success)
        self.grant(self.standard, group, "capability.view", expires_at=NOW + timedelta(seconds=1))
        self.assertTrue(self.management.projection(self.standard, extension_id=SCREEN_EXTENSION,
                                                   scope=group, observed_at=NOW).is_success)
        self.assertEqual(self.management.projection(self.standard, extension_id=SCREEN_EXTENSION,
                         scope=group, observed_at=NOW + timedelta(seconds=1)).failure.code, "authorization_expired")
        other_role = SubjectRef(INSTALLATION, SubjectKind.BOT, "other-role")
        self.assertEqual(self.management.projection(self.important, extension_id=SCREEN_EXTENSION, role=other_role,
                         scope=SCOPE, observed_at=NOW).failure.code, "role_binding_changed")

    def test_role_selection_is_scoped_to_explicit_bot_and_does_not_grant_consent(self):
        self.acquire().unwrap()
        role_scope = self.management.role_scope(SCREEN_EXTENSION, ROLE, SCOPE.bot_id)
        result = self.management.set_role_enabled(self.core, extension_id=SCREEN_EXTENSION, role=ROLE,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW,
            operation=self.operation(role_scope, owner=self.management.OWNER)).unwrap()
        self.assertEqual(result.effect, "local_record_saved")
        self.assertTrue(self.management.repository.require_role_enabled(extension_id=SCREEN_EXTENSION, role=ROLE,
                                                                        bot_id=SCOPE.bot_id).is_success)
        self.assertFalse(self.management.repository.require_role_enabled(extension_id=SCREEN_EXTENSION, role=ROLE,
                                                                         bot_id="bot-b").is_success)
        self.assertEqual(self.management.repository.consent(extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ,
                         subject=self.important.subject, scope=SCOPE).failure.code, "capability_consent_missing")

    def test_update_pins_reviewed_content_and_discard_only_requests_local_removal(self):
        self.acquire().unwrap()
        selected = descriptor("2.0.0")
        self.management.repository.register_descriptor(selected, registered_at=NOW).unwrap()
        scope = self.management.management_scope(SCREEN_EXTENSION)
        self.management.select_package(self.core, extension_id=SCREEN_EXTENSION, action="update", package_id=selected.package_id,
            package_version=selected.package_version, artifact_hash=selected.artifact_hash, expected_revision=1,
            operation=self.operation(scope, owner=self.management.OWNER), observed_at=NOW).unwrap()
        self.assertEqual(self.management.repository.installation(extension_id=SCREEN_EXTENSION).unwrap().package_version, "2.0.0")
        self.management.change_lifecycle(self.core, extension_id=SCREEN_EXTENSION, action="discard.request", expected_revision=2,
            operation=self.operation(scope, owner=self.management.OWNER), observed_at=NOW).unwrap()
        self.assertEqual(self.management.repository.installation(extension_id=SCREEN_EXTENSION).unwrap().desired_state.value,
                         "discard_requested")
        self.assertEqual(self.management.change_lifecycle(self.core, extension_id=SCREEN_EXTENSION, action="complete_discard",
            expected_revision=3, operation=self.operation(scope, owner=self.management.OWNER), observed_at=NOW).failure.code,
            "unknown_access_action")

    def test_changed_parameters_or_wrong_operation_scope_cannot_reuse_original_command(self):
        scope = self.management.management_scope(SCREEN_EXTENSION)
        operation = self.operation(scope, owner=self.management.OWNER)
        self.acquire(operation=operation).unwrap()
        self.assertEqual(self.acquire(operation=operation, artifact_hash="changed").failure.code, "idempotency_key_conflict")
        self.assertEqual(self.management.change_lifecycle(self.core, extension_id=SCREEN_EXTENSION, action="pause", expected_revision=1,
            operation=self.operation(SCOPE, owner=self.management.OWNER), observed_at=NOW).failure.code, "operation_scope_mismatch")
        self.assertEqual(self.management.repository.installation(extension_id=SCREEN_EXTENSION).unwrap().revision, 1)


if __name__ == "__main__":
    unittest.main()
