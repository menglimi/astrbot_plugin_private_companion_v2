from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.refs import ReferenceValidationError, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
INSTALLATION = "object-access-installation"
USER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "user-a")
OTHER = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "user-b")
PRINCIPAL = AuthenticatedHostPrincipal(INSTALLATION, "host", "onebot", "account-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "window-a")
OTHER_SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "group-b")


class ObjectAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-object-access-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.runtime = self.open_runtime()
        self.identity = PersistentIdentityDirectory(self.runtime)
        self.policy = ObjectAccessPolicy(self.runtime)
        self.identity.bind(binding_id="binding-a", principal=PRINCIPAL, subject=USER, valid_from=NOW,
                           expected_revision=self.identity.revision)
        self.actor = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.policy.register_object("memo:a", owner=USER, scope=SCOPE, domain="memo")
        self.policy.register_object("memo:b", owner=OTHER, scope=SCOPE, domain="memo")
        self.policy.register_object("memo:c", owner=OTHER, scope=OTHER_SCOPE, domain="memo")

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def tier(self, tier):
        self.policy.set_tier(USER, tier, expected_revision=self.policy.revision, observed_at=NOW)

    def grant(self, action, *, scope=SCOPE, tier=AuthorizationTier.STANDARD, expires_at=None):
        self.identity.issue_grant(grant_id=action, subject=USER, scope=scope, capability=action,
                                  tier=tier, valid_from=NOW, expires_at=expires_at,
                                  expected_revision=self.identity.revision)

    def access(self, *, owner=USER, key="memo:a", action="memo.read", scope=SCOPE, actor=None, now=NOW):
        return self.policy.authorize(actor or self.actor, scope=scope, action=action, owner=owner,
                                     object_key=key, observed_at=now)

    def share(self, actions=("memo.read",), *, expires_at=None):
        self.policy.share_object("memo:b", USER, actions, expected_revision=self.policy.revision,
                                 observed_at=NOW, expires_at=expires_at)

    def test_default_standard_needs_exact_feature_and_ownership(self):
        self.assertEqual(self.access().failure.code, "authorization_denied")
        self.grant("memo.read")
        self.assertEqual(self.access().unwrap().tier, AuthorizationTier.STANDARD)
        self.assertEqual(self.access(owner=OTHER, key="memo:b").failure.code, "object_access_denied")
        self.assertEqual(self.access(owner=OTHER, key="memo:c", scope=OTHER_SCOPE).failure.code, "scope_not_granted")

    def test_capability_grant_tier_does_not_establish_installation_membership(self):
        self.grant("memo.read", tier=AuthorizationTier.CORE)
        self.assertEqual(self.access().unwrap().tier, AuthorizationTier.STANDARD)
        self.assertFalse(self.access(owner=OTHER, key="memo:b").is_success)
        self.assertFalse(self.access(action="memo.edit").is_success)
        self.grant("access.policy.set", tier=AuthorizationTier.CORE)
        self.assertEqual(self.access(action="access.policy.set", key=None).failure.code, "core_access_required")

    def test_important_has_noncore_feature_but_not_other_owner_or_unknown_action(self):
        self.tier(AuthorizationTier.IMPORTANT)
        self.assertTrue(self.access().is_success)
        self.assertEqual(self.access(owner=OTHER, key="memo:b").failure.code, "object_access_denied")
        self.assertEqual(self.access(action="access.policy.set", key=None).failure.code, "core_access_required")
        self.assertEqual(self.access(action="unknown.privileged").failure.code, "unknown_access_action")

    def test_core_cross_scope_still_requires_real_identity_and_registered_object(self):
        self.tier(AuthorizationTier.CORE)
        self.assertTrue(self.access(owner=OTHER, key="memo:c", scope=OTHER_SCOPE).is_success)
        self.assertTrue(self.access(owner=OTHER, key=None, scope=OTHER_SCOPE, action="memo.create").is_success)
        self.assertTrue(self.access(action="access.policy.set", key=None).is_success)
        self.assertEqual(self.access(owner=OTHER, key="missing").failure.code, "object_not_registered")
        self.assertEqual(self.access(owner=OTHER, key="memo:c").failure.code, "object_scope_mismatch")
        forged = replace(self.actor, subject=OTHER)
        self.assertEqual(self.access(actor=forged).failure.code, "binding_rebound")

    def test_share_is_exact_action_and_never_opens_create_or_owner_container(self):
        self.tier(AuthorizationTier.IMPORTANT)
        self.share()
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)
        self.assertEqual(self.access(owner=OTHER, key="memo:b", action="memo.edit").failure.code, "object_access_denied")
        self.assertFalse(self.access(owner=OTHER, key=None, action="memo.create").is_success)
        self.assertFalse(self.access(owner=OTHER, key=None, action="memo.list").is_success)
        for action in ("memo.create", "memo.list", "access.policy.set", "reminder.read", "unknown"):
            with self.subTest(action=action), self.assertRaises(ReferenceValidationError):
                self.share((action,))

    def test_standard_shared_object_still_needs_current_feature_opening(self):
        self.share()
        self.assertFalse(self.access(owner=OTHER, key="memo:b").is_success)
        self.grant("memo.read")
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)
        self.identity.revoke_grant("memo.read", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.access(owner=OTHER, key="memo:b").failure.code, "authorization_revoked")

    def test_share_expiration_and_revocation_are_seen_without_snapshot_refresh(self):
        self.tier(AuthorizationTier.IMPORTANT)
        self.share(expires_at=NOW + timedelta(seconds=2))
        self.assertTrue(self.access(owner=OTHER, key="memo:b", now=NOW + timedelta(seconds=1)).is_success)
        self.assertEqual(self.access(owner=OTHER, key="memo:b", now=NOW + timedelta(seconds=2)).failure.code,
                         "object_share_expired")
        other = ObjectAccessPolicy(self.open_runtime())
        other.revoke_share("memo:b", USER, expected_revision=other.revision, observed_at=NOW)
        self.assertEqual(self.access(owner=OTHER, key="memo:b").failure.code, "object_share_revoked")

    def test_tier_downgrade_rechecks_current_grants_and_shares(self):
        self.tier(AuthorizationTier.CORE)
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)
        self.tier(AuthorizationTier.IMPORTANT)
        self.assertFalse(self.access(owner=OTHER, key="memo:b").is_success)
        self.share()
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)
        self.tier(AuthorizationTier.STANDARD)
        self.assertFalse(self.access(owner=OTHER, key="memo:b").is_success)
        self.grant("memo.read")
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)

    def test_binding_rebound_or_revoked_does_not_keep_tier_authority(self):
        self.tier(AuthorizationTier.CORE)
        self.identity.bind(binding_id="binding-b", principal=PRINCIPAL, subject=OTHER, valid_from=NOW,
                           expected_revision=self.identity.revision)
        self.assertEqual(self.access().failure.code, "binding_rebound")
        rebound = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.assertFalse(self.access(owner=OTHER, key="memo:b", actor=rebound).is_success)
        self.identity.revoke_binding("binding-b", revoked_at=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.access(actor=rebound).failure.code, "binding_revoked")

    def test_expired_binding_blocks_core_and_expired_grant_blocks_standard(self):
        self.grant("memo.read", expires_at=NOW + timedelta(seconds=1))
        self.assertEqual(self.access(now=NOW + timedelta(seconds=1)).failure.code, "authorization_expired")
        self.tier(AuthorizationTier.CORE)
        self.identity.bind(binding_id="binding-b", principal=PRINCIPAL, subject=USER, valid_from=NOW,
                           expires_at=NOW + timedelta(seconds=1), expected_revision=self.identity.revision)
        actor = self.identity.resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        self.assertEqual(self.access(actor=actor, now=NOW + timedelta(seconds=1)).failure.code, "binding_expired")

    def test_registration_is_immutable_and_policy_mutations_use_cas(self):
        revision = self.policy.revision
        self.policy.register_object("memo:a", owner=USER, scope=SCOPE, domain="memo")
        self.assertEqual(self.policy.revision, revision)
        with self.assertRaisesRegex(ReferenceValidationError, "ownership_conflict"):
            self.policy.register_object("memo:a", owner=OTHER, scope=SCOPE, domain="memo")
        self.tier(AuthorizationTier.IMPORTANT)
        with self.assertRaisesRegex(ReferenceValidationError, "revision_conflict"):
            self.policy.share_object("memo:b", USER, ("memo.read",), expected_revision=revision, observed_at=NOW)
        self.assertEqual(self.access(owner=OTHER, key="memo:b").failure.code, "object_access_denied")

    def test_visible_objects_include_only_current_exact_scope_owner_or_shares(self):
        self.tier(AuthorizationTier.IMPORTANT)
        self.share()
        def visible(**extra):
            return self.policy.permitted_object_keys(self.actor, scope=SCOPE, action="memo.read", observed_at=NOW, **extra).unwrap()
        self.assertEqual(visible(), ("memo:a", "memo:b"))
        self.assertEqual(visible(owner=OTHER), ("memo:b",))
        self.policy.revoke_share("memo:b", USER, expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(visible(), ("memo:a",))

    def test_restart_preserves_tier_and_revocation_without_cross_installation_fallback(self):
        self.tier(AuthorizationTier.IMPORTANT)
        self.share()
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.policy = ObjectAccessPolicy(self.runtime)
        self.assertTrue(self.access(owner=OTHER, key="memo:b").is_success)
        foreign = ScopeRef("foreign-installation", "onebot", ScopeKind.PRIVATE, "window-a")
        self.assertEqual(self.access(scope=foreign).failure.code, "scope_installation_mismatch")
        with self.assertRaises(ReferenceValidationError):
            self.policy.set_tier(SubjectRef("foreign-installation", SubjectKind.HUMAN, "person"),
                                 AuthorizationTier.CORE, expected_revision=self.policy.revision, observed_at=NOW)

    def test_composed_transaction_rollback_removes_registration_tier_and_share(self):
        revision = self.policy.revision
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.runtime.transaction():
                self.tier(AuthorizationTier.CORE)
                self.share()
                self.policy.register_object("memo:d", owner=OTHER, scope=SCOPE, domain="memo")
                raise RuntimeError("abort")
        self.assertEqual(self.policy.revision, revision)
        self.assertFalse(self.access().is_success)
        self.assertEqual(self.runtime.read_all("SELECT * FROM object_access_shares", ()), ())
        self.assertIsNone(self.runtime.read_one("SELECT * FROM access_objects WHERE object_key = 'memo:d'", ()))
