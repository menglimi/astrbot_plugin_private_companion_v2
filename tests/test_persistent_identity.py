from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import ReferenceValidationError, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "installation-config"
PRINCIPAL = AuthenticatedHostPrincipal(INSTALLATION, "host-a", "onebot", "account-a")
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-a")
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-a")


class PersistentIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(prefix="companion-v2-identity-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.runtime = self.open_runtime()
        self.identity = PersistentIdentityDirectory(self.runtime)

    def open_runtime(self) -> StorageRuntime:
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def prepare(self, *, expires_at=None) -> None:
        self.identity.bind(binding_id="binding-a", principal=PRINCIPAL, subject=USER, valid_from=NOW,
                           expires_at=expires_at, expected_revision=self.identity.revision)
        self.identity.issue_grant(grant_id="grant-a", subject=USER, scope=SCOPE, capability="source.read",
                                  tier=AuthorizationTier.STANDARD, valid_from=NOW,
                                  expected_revision=self.identity.revision)
        self.identity.bind_role(scope=SCOPE, role=ROLE, expected_revision=0)

    def test_bindings_grants_and_role_recover_without_handoff_snapshot(self) -> None:
        self.prepare()
        self.runtime.close()
        reopened = PersistentIdentityDirectory(self.open_runtime())
        resolved = reopened.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.assertEqual(resolved.subject, USER)
        self.assertTrue(reopened.authorize(resolved, scope=SCOPE, capability="source.read", observed_at=NOW).is_success)
        self.assertEqual(reopened.role_binding(SCOPE).role, ROLE)

    def test_other_connection_revocation_is_seen_without_cache_refresh(self) -> None:
        self.prepare()
        resolved = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        other = PersistentIdentityDirectory(self.open_runtime())
        other.revoke_grant("grant-a", revoked_at=NOW, expected_revision=other.revision)
        result = self.identity.authorize(resolved, scope=SCOPE, capability="source.read", observed_at=NOW)
        self.assertEqual(result.failure.code, "authorization_revoked")
        self.runtime.close()
        reopened = PersistentIdentityDirectory(self.open_runtime())
        self.assertEqual(reopened.authorize(resolved, scope=SCOPE, capability="source.read", observed_at=NOW).failure.code, "authorization_revoked")

    def test_rebind_does_not_transfer_old_subject_grant(self) -> None:
        self.prepare()
        resolved = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.identity.bind(binding_id="binding-b", principal=PRINCIPAL,
                           subject=SubjectRef(INSTALLATION, SubjectKind.HUMAN, "person-b"),
                           valid_from=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.identity.authorize(resolved, scope=SCOPE, capability="source.read", observed_at=NOW).failure.code, "binding_rebound")
        new = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.assertEqual(self.identity.authorize(new, scope=SCOPE, capability="source.read", observed_at=NOW).failure.code, "authorization_denied")

    def test_expiration_and_revoked_binding_survive_reopen(self) -> None:
        self.prepare(expires_at=NOW + timedelta(seconds=1))
        self.runtime.close()
        identity = PersistentIdentityDirectory(self.open_runtime())
        self.assertEqual(identity.resolve_authenticated(PRINCIPAL, observed_at=NOW + timedelta(seconds=1)).failure.code, "binding_expired")
        identity.revoke_binding("binding-a", revoked_at=NOW, expected_revision=identity.revision)
        self.assertEqual(identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).failure.code, "binding_revoked")

    def test_stale_policy_and_role_edits_do_not_replace_newer_choice(self) -> None:
        self.prepare()
        stale_revision = self.identity.revision
        other = PersistentIdentityDirectory(self.open_runtime())
        other.revoke_grant("grant-a", revoked_at=NOW, expected_revision=stale_revision)
        with self.assertRaisesRegex(ReferenceValidationError, "identity_revision_conflict"):
            self.identity.revoke_binding("binding-a", revoked_at=NOW, expected_revision=stale_revision)
        other.bind_role(scope=SCOPE, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b"), expected_revision=1)
        with self.assertRaisesRegex(ReferenceValidationError, "role_binding_revision_conflict"):
            self.identity.bind_role(scope=SCOPE, role=ROLE, expected_revision=1)
        self.assertEqual(self.identity.role_binding(SCOPE).role.subject_id, "role-b")

    def test_cross_installation_and_cross_scope_are_not_fallbacks(self) -> None:
        self.prepare()
        resolved = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        other_scope = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-b")
        self.assertEqual(self.identity.authorize(resolved, scope=other_scope, capability="source.read", observed_at=NOW).failure.code, "scope_not_granted")
        foreign = AuthenticatedHostPrincipal("other-installation", "host-a", "onebot", "account-a")
        self.assertEqual(self.identity.resolve_authenticated(foreign, observed_at=NOW).failure.code, "scope_installation_mismatch")
        with self.assertRaises(ReferenceValidationError):
            self.identity.bind_role(scope=SCOPE, role=SubjectRef("other-installation", SubjectKind.BOT, "role-a"), expected_revision=1)
