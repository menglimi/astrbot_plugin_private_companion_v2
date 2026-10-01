"""Deterministic in-memory implementation of G1 identity and grant semantics."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ReferenceValidationError, ScopeRef, SubjectRef, normalize_utc

from .models import (
    AuthenticatedHostPrincipal,
    AuthorizationTier,
    AuthorizedAccess,
    BindingState,
    CapabilityGrant,
    FailureCode,
    GrantState,
    IdentityBinding,
    IdentityPolicySnapshot,
    ResolvedIdentity,
    UntrustedIdentityClaim,
)


class IdentityDirectory:
    """Versioned account links and grants with no identity fallback path.

    G1 keeps the directory in memory so its rules can be replayed before G2 introduces
    storage. `snapshot()` is a detached handoff used to simulate a process restart.
    """

    def __init__(
        self,
        *,
        bindings: tuple[IdentityBinding, ...] = (),
        grants: tuple[CapabilityGrant, ...] = (),
        policy_revision: int = 1,
    ) -> None:
        if policy_revision < 1:
            raise ReferenceValidationError("policy_revision must be positive")
        self._bindings = {item.binding_id: item for item in bindings}
        if len(self._bindings) != len(bindings):
            raise ReferenceValidationError("binding_id must be unique")
        self._grants = {item.grant_id: item for item in grants}
        if len(self._grants) != len(grants):
            raise ReferenceValidationError("grant_id must be unique")
        self._policy_revision = policy_revision
        self._bindings_by_principal: dict[AuthenticatedHostPrincipal, tuple[IdentityBinding, ...]] = {}
        self._rebuild_binding_index()

    @classmethod
    def from_snapshot(cls, snapshot: IdentityPolicySnapshot) -> "IdentityDirectory":
        return cls(
            bindings=snapshot.bindings,
            grants=snapshot.grants,
            policy_revision=snapshot.policy_revision,
        )

    def snapshot(self) -> IdentityPolicySnapshot:
        return IdentityPolicySnapshot(
            policy_revision=self._policy_revision,
            bindings=tuple(sorted(self._bindings.values(), key=lambda item: item.binding_id)),
            grants=tuple(sorted(self._grants.values(), key=lambda item: item.grant_id)),
        )

    def bind(
        self,
        *,
        binding_id: str,
        principal: AuthenticatedHostPrincipal,
        subject: SubjectRef,
        valid_from: datetime,
        expires_at: datetime | None = None,
    ) -> IdentityBinding:
        """Create the current binding and mark any previous current binding superseded."""

        if binding_id in self._bindings:
            raise ReferenceValidationError("binding_id already exists")
        records = self._bindings_by_principal.get(principal, ())
        next_revision = max((item.revision for item in records), default=0) + 1
        current = self._current_binding(principal)
        if current is not None and current.state is BindingState.ACTIVE:
            self._bindings[current.binding_id] = replace(
                current,
                state=BindingState.SUPERSEDED,
                replaced_by=binding_id,
            )
        created = IdentityBinding(
            binding_id=binding_id,
            principal=principal,
            subject=subject,
            revision=next_revision,
            valid_from=valid_from,
            expires_at=expires_at,
        )
        self._bindings[binding_id] = created
        self._policy_revision += 1
        self._rebuild_binding_index()
        return created

    def revoke_binding(self, binding_id: str, *, revoked_at: datetime) -> IdentityBinding:
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise KeyError(binding_id)
        if binding.state is not BindingState.ACTIVE:
            raise ReferenceValidationError("only active bindings can be revoked")
        updated = replace(
            binding,
            revision=binding.revision + 1,
            state=BindingState.REVOKED,
            revoked_at=revoked_at,
        )
        self._bindings[binding_id] = updated
        self._policy_revision += 1
        self._rebuild_binding_index()
        return updated

    def issue_grant(
        self,
        *,
        grant_id: str,
        subject: SubjectRef,
        scope: ScopeRef,
        capability: str,
        tier: AuthorizationTier,
        valid_from: datetime,
        expires_at: datetime | None = None,
    ) -> CapabilityGrant:
        if grant_id in self._grants:
            raise ReferenceValidationError("grant_id already exists")
        grant = CapabilityGrant(
            grant_id=grant_id,
            subject=subject,
            scope=scope,
            capability=capability,
            tier=tier,
            revision=1,
            valid_from=valid_from,
            expires_at=expires_at,
        )
        self._grants[grant_id] = grant
        self._policy_revision += 1
        return grant

    def revoke_grant(self, grant_id: str, *, revoked_at: datetime) -> CapabilityGrant:
        grant = self._grants.get(grant_id)
        if grant is None:
            raise KeyError(grant_id)
        if grant.state is not GrantState.ACTIVE:
            raise ReferenceValidationError("only active grants can be revoked")
        updated = replace(
            grant,
            revision=grant.revision + 1,
            state=GrantState.REVOKED,
            revoked_at=revoked_at,
        )
        self._grants[grant_id] = updated
        self._policy_revision += 1
        return updated

    def resolve_authenticated(
        self,
        principal: AuthenticatedHostPrincipal,
        *,
        observed_at: datetime,
    ) -> Outcome[ResolvedIdentity]:
        observed_at = normalize_utc(observed_at, field="observed_at")
        binding = self._current_binding(principal)
        if binding is None:
            return Outcome.failed(
                FailureCode.UNBOUND_IDENTITY.value,
                "authenticated account has no current binding",
            )
        failure = self._binding_failure(binding, observed_at)
        if failure is not None:
            return failure
        return Outcome.success(
            ResolvedIdentity(
                principal=principal,
                subject=binding.subject,
                binding_id=binding.binding_id,
                binding_revision=binding.revision,
                policy_revision=self._policy_revision,
            )
        )

    def reject_untrusted_claim(
        self,
        claim: UntrustedIdentityClaim,
    ) -> Outcome[ResolvedIdentity]:
        """Explicitly reject identity supplied by content, a request body, or a model."""

        del claim
        return Outcome.failed(
            FailureCode.UNTRUSTED_IDENTITY_INPUT.value,
            "content-provided identity cannot establish a host binding",
        )

    def authorize(
        self,
        resolved: ResolvedIdentity,
        *,
        scope: ScopeRef,
        capability: str,
        observed_at: datetime,
    ) -> Outcome[AuthorizedAccess]:
        observed_at = normalize_utc(observed_at, field="observed_at")
        if scope.installation_id != resolved.principal.installation_id:
            return Outcome.failed(
                FailureCode.SCOPE_INSTALLATION_MISMATCH.value,
                "requested scope belongs to another installation",
            )
        current = self._current_binding(resolved.principal)
        if current is None or current.binding_id != resolved.binding_id:
            return Outcome.failed(
                FailureCode.BINDING_REBOUND.value,
                "the resolved account binding has changed",
            )
        failure = self._binding_failure(current, observed_at)
        if failure is not None:
            return failure
        if current.revision != resolved.binding_revision or current.subject != resolved.subject:
            return Outcome.failed(
                FailureCode.BINDING_REBOUND.value,
                "the resolved account binding is no longer current",
            )

        matching = tuple(
            item
            for item in self._grants.values()
            if item.subject == resolved.subject
            and item.capability == capability
            and item.scope == scope
        )
        active = tuple(
            item for item in matching if self._grant_is_active(item, observed_at)
        )
        if active:
            grant = max(active, key=lambda item: (item.revision, item.grant_id))
            return Outcome.success(
                AuthorizedAccess(
                    subject=resolved.subject,
                    scope=scope,
                    capability=capability,
                    binding_id=current.binding_id,
                    binding_revision=current.revision,
                    grant_id=grant.grant_id,
                    grant_revision=grant.revision,
                    policy_revision=self._policy_revision,
                )
            )
        if matching:
            return self._grant_failure(matching, observed_at)

        same_subject_and_capability = tuple(
            item
            for item in self._grants.values()
            if item.subject == resolved.subject and item.capability == capability
        )
        if same_subject_and_capability:
            return Outcome.failed(
                FailureCode.SCOPE_NOT_GRANTED.value,
                "capability is not granted in this exact scope",
            )
        return Outcome.failed(
            FailureCode.AUTHORIZATION_DENIED.value,
            "no capability grant matches this subject, scope, and action",
        )

    def _rebuild_binding_index(self) -> None:
        grouped: dict[AuthenticatedHostPrincipal, list[IdentityBinding]] = {}
        for binding in self._bindings.values():
            grouped.setdefault(binding.principal, []).append(binding)
        indexed: dict[AuthenticatedHostPrincipal, tuple[IdentityBinding, ...]] = {}
        for principal, records in grouped.items():
            revisions = [item.revision for item in records]
            if len(revisions) != len(set(revisions)):
                raise ReferenceValidationError("binding revisions must be unique per principal")
            active = [item for item in records if item.state is BindingState.ACTIVE]
            if len(active) > 1:
                raise ReferenceValidationError("only one active binding is allowed per principal")
            indexed[principal] = tuple(
                sorted(records, key=lambda item: (item.revision, item.binding_id))
            )
        self._bindings_by_principal = indexed

    def _current_binding(
        self,
        principal: AuthenticatedHostPrincipal,
    ) -> IdentityBinding | None:
        records = self._bindings_by_principal.get(principal, ())
        return records[-1] if records else None

    @staticmethod
    def _binding_failure(
        binding: IdentityBinding,
        observed_at: datetime,
    ) -> Outcome[ResolvedIdentity] | None:
        if binding.state is BindingState.REVOKED:
            return Outcome.failed(
                FailureCode.BINDING_REVOKED.value,
                "account binding has been revoked",
            )
        if binding.state is BindingState.SUPERSEDED:
            return Outcome.failed(
                FailureCode.BINDING_REBOUND.value,
                "account binding has been superseded",
            )
        if observed_at < binding.valid_from:
            return Outcome.failed(
                FailureCode.BINDING_NOT_ACTIVE.value,
                "account binding is not active yet",
            )
        if binding.expires_at is not None and observed_at >= binding.expires_at:
            return Outcome.failed(
                FailureCode.BINDING_EXPIRED.value,
                "account binding has expired",
            )
        return None

    @staticmethod
    def _grant_is_active(grant: CapabilityGrant, observed_at: datetime) -> bool:
        return (
            grant.state is GrantState.ACTIVE
            and observed_at >= grant.valid_from
            and (grant.expires_at is None or observed_at < grant.expires_at)
        )

    @staticmethod
    def _grant_failure(
        grants: tuple[CapabilityGrant, ...],
        observed_at: datetime,
    ) -> Outcome[AuthorizedAccess]:
        if any(item.state is GrantState.REVOKED for item in grants):
            return Outcome.failed(
                FailureCode.AUTHORIZATION_REVOKED.value,
                "matching capability grant has been revoked",
            )
        if any(
            item.expires_at is not None and observed_at >= item.expires_at
            for item in grants
        ):
            return Outcome.failed(
                FailureCode.AUTHORIZATION_EXPIRED.value,
                "matching capability grant has expired",
            )
        return Outcome.failed(
            FailureCode.AUTHORIZATION_NOT_ACTIVE.value,
            "matching capability grant is not active yet",
        )
