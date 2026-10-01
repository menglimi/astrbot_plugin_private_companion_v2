from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest

from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import (
    AuthenticatedHostPrincipal,
    AuthorizationTier,
    FailureCode,
    UntrustedIdentityClaim,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "identity_policy" / "scenarios.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def observed_at(fixture: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(fixture["observed_at"]))


def principal_for(fixture: dict[str, object]) -> AuthenticatedHostPrincipal:
    principal = fixture["principal"]
    assert isinstance(principal, dict)
    return AuthenticatedHostPrincipal(
        installation_id=str(fixture["installation_id"]),
        host_id=str(principal["host_id"]),
        platform=str(principal["platform"]),
        native_account_id=str(principal["native_account_id"]),
    )


def subject_for(fixture: dict[str, object], *, subject_id: str | None = None) -> SubjectRef:
    subject = fixture["subject"]
    assert isinstance(subject, dict)
    return SubjectRef(
        installation_id=str(fixture["installation_id"]),
        kind=SubjectKind(str(subject["kind"])),
        subject_id=subject_id or str(subject["subject_id"]),
    )


def scope_for(fixture: dict[str, object], key: str) -> ScopeRef:
    scope = fixture[key]
    assert isinstance(scope, dict)
    return ScopeRef(
        installation_id=str(fixture["installation_id"]),
        platform=str(scope["platform"]),
        kind=ScopeKind(str(scope["kind"])),
        native_scope_id=str(scope["native_scope_id"]),
    )


def configured_directory(
    fixture: dict[str, object],
    *,
    binding_expires_at: datetime | None = None,
    grant_expires_at: datetime | None = None,
) -> IdentityDirectory:
    directory = IdentityDirectory()
    now = observed_at(fixture)
    subject = subject_for(fixture)
    private_scope = scope_for(fixture, "private_scope")
    directory.bind(
        binding_id="binding-a",
        principal=principal_for(fixture),
        subject=subject,
        valid_from=now - timedelta(minutes=1),
        expires_at=binding_expires_at,
    )
    directory.issue_grant(
        grant_id="grant-a",
        subject=subject,
        scope=private_scope,
        capability=str(fixture["capability"]),
        tier=AuthorizationTier.IMPORTANT,
        valid_from=now - timedelta(minutes=1),
        expires_at=grant_expires_at,
    )
    return directory


class IdentityPolicyTests(unittest.TestCase):
    def test_authenticated_principal_resolves_and_authorizes_in_exact_scope(self) -> None:
        fixture = load_fixture()
        directory = configured_directory(fixture)
        now = observed_at(fixture)

        resolved = directory.resolve_authenticated(principal_for(fixture), observed_at=now)
        access = directory.authorize(
            resolved.unwrap(),
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now,
        )

        self.assertTrue(access.is_success)
        self.assertEqual(access.unwrap().subject, subject_for(fixture))
        self.assertEqual(access.unwrap().grant_id, "grant-a")

    def test_body_claim_unbound_account_and_cross_scope_are_not_fallbacks(self) -> None:
        fixture = load_fixture()
        directory = configured_directory(fixture)
        now = observed_at(fixture)

        untrusted = directory.reject_untrusted_claim(
            UntrustedIdentityClaim(claimed_account_id="account-a", origin="message-body")
        )
        self.assertEqual(untrusted.failure.code, FailureCode.UNTRUSTED_IDENTITY_INPUT.value)

        unknown = AuthenticatedHostPrincipal(
            installation_id=str(fixture["installation_id"]),
            host_id="astrbot-fixture-host",
            platform="onebot",
            native_account_id="account-not-bound",
        )
        unbound = directory.resolve_authenticated(unknown, observed_at=now)
        self.assertEqual(unbound.failure.code, FailureCode.UNBOUND_IDENTITY.value)

        resolved = directory.resolve_authenticated(principal_for(fixture), observed_at=now).unwrap()
        cross_scope = directory.authorize(
            resolved,
            scope=scope_for(fixture, "group_scope"),
            capability=str(fixture["capability"]),
            observed_at=now,
        )
        self.assertEqual(cross_scope.failure.code, FailureCode.SCOPE_NOT_GRANTED.value)

    def test_revocation_and_expiry_return_explicit_failures(self) -> None:
        fixture = load_fixture()
        now = observed_at(fixture)

        revoked_directory = configured_directory(fixture)
        resolved = revoked_directory.resolve_authenticated(
            principal_for(fixture), observed_at=now
        ).unwrap()
        revoked_directory.revoke_grant("grant-a", revoked_at=now + timedelta(seconds=1))
        revoked = revoked_directory.authorize(
            resolved,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now + timedelta(minutes=1),
        )
        self.assertEqual(revoked.failure.code, FailureCode.AUTHORIZATION_REVOKED.value)

        expired_directory = configured_directory(
            fixture,
            grant_expires_at=now + timedelta(seconds=1),
        )
        expired_resolved = expired_directory.resolve_authenticated(
            principal_for(fixture), observed_at=now
        ).unwrap()
        expired = expired_directory.authorize(
            expired_resolved,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now + timedelta(minutes=1),
        )
        self.assertEqual(expired.failure.code, FailureCode.AUTHORIZATION_EXPIRED.value)

        expired_binding_directory = configured_directory(
            fixture,
            binding_expires_at=now + timedelta(seconds=1),
        )
        expired_binding = expired_binding_directory.resolve_authenticated(
            principal_for(fixture), observed_at=now + timedelta(minutes=1)
        )
        self.assertEqual(expired_binding.failure.code, FailureCode.BINDING_EXPIRED.value)

    def test_rebinding_invalidates_old_resolution_and_requires_a_new_grant(self) -> None:
        fixture = load_fixture()
        directory = configured_directory(fixture)
        now = observed_at(fixture)
        previous = directory.resolve_authenticated(principal_for(fixture), observed_at=now).unwrap()
        replacement_subject = subject_for(fixture, subject_id="subject-b")
        directory.bind(
            binding_id="binding-b",
            principal=principal_for(fixture),
            subject=replacement_subject,
            valid_from=now + timedelta(seconds=1),
        )
        directory.issue_grant(
            grant_id="grant-b",
            subject=replacement_subject,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            tier=AuthorizationTier.IMPORTANT,
            valid_from=now + timedelta(seconds=1),
        )

        stale = directory.authorize(
            previous,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now + timedelta(minutes=1),
        )
        self.assertEqual(stale.failure.code, FailureCode.BINDING_REBOUND.value)

        current = directory.resolve_authenticated(
            principal_for(fixture), observed_at=now + timedelta(minutes=1)
        ).unwrap()
        access = directory.authorize(
            current,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now + timedelta(minutes=1),
        )
        self.assertTrue(access.is_success)
        self.assertEqual(access.unwrap().subject, replacement_subject)

    def test_snapshot_reconstructs_same_current_identity_after_restart(self) -> None:
        fixture = load_fixture()
        directory = configured_directory(fixture)
        now = observed_at(fixture)
        before = directory.resolve_authenticated(principal_for(fixture), observed_at=now).unwrap()

        restarted = IdentityDirectory.from_snapshot(directory.snapshot())
        after = restarted.resolve_authenticated(principal_for(fixture), observed_at=now).unwrap()
        access = restarted.authorize(
            after,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now,
        )

        self.assertEqual(after.subject, before.subject)
        self.assertEqual(after.binding_id, before.binding_id)
        self.assertTrue(access.is_success)

    def test_revoked_grant_remains_revoked_after_restart(self) -> None:
        fixture = load_fixture()
        directory = configured_directory(fixture)
        now = observed_at(fixture)
        directory.revoke_grant("grant-a", revoked_at=now + timedelta(seconds=1))

        restarted = IdentityDirectory.from_snapshot(directory.snapshot())
        resolved = restarted.resolve_authenticated(
            principal_for(fixture), observed_at=now + timedelta(minutes=1)
        ).unwrap()
        denied = restarted.authorize(
            resolved,
            scope=scope_for(fixture, "private_scope"),
            capability=str(fixture["capability"]),
            observed_at=now + timedelta(minutes=1),
        )

        self.assertEqual(
            denied.failure.code,
            FailureCode.AUTHORIZATION_REVOKED.value,
        )
