"""Value objects for trusted account bindings and exact-scope grants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import (
    ReferenceValidationError,
    ScopeRef,
    SubjectKind,
    SubjectRef,
    normalize_utc,
)


class BindingState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class GrantState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class AuthorizationTier(str, Enum):
    CORE = "core"
    IMPORTANT = "important"
    STANDARD = "standard"


@dataclass(frozen=True)
class RoleBinding:
    """The exact role selection captured with a turn's role instruction."""

    scope: ScopeRef
    role: SubjectRef
    revision: int

    def __post_init__(self) -> None:
        if self.role.kind is not SubjectKind.BOT or self.role.installation_id != self.scope.installation_id:
            raise ReferenceValidationError("role binding requires a role in the same installation")
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("role binding revision must be positive")


class FailureCode(str, Enum):
    UNTRUSTED_IDENTITY_INPUT = "untrusted_identity_input"
    UNBOUND_IDENTITY = "unbound_identity"
    BINDING_REVOKED = "binding_revoked"
    BINDING_EXPIRED = "binding_expired"
    BINDING_NOT_ACTIVE = "binding_not_active"
    BINDING_REBOUND = "binding_rebound"
    SCOPE_INSTALLATION_MISMATCH = "scope_installation_mismatch"
    SCOPE_NOT_GRANTED = "scope_not_granted"
    AUTHORIZATION_REVOKED = "authorization_revoked"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    AUTHORIZATION_NOT_ACTIVE = "authorization_not_active"
    AUTHORIZATION_DENIED = "authorization_denied"


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    if len(value) > 512:
        raise ReferenceValidationError(f"{field} exceeds 512 characters")
    return value


def _positive(value: int, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReferenceValidationError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class AuthenticatedHostPrincipal:
    """An account identity supplied by an authenticated host adapter.

    This object intentionally has no message-body or display-name fields. Adapters may
    construct it only after the host has authenticated the event or management session.
    """

    installation_id: str
    host_id: str
    platform: str
    native_account_id: str
    bot_id: str | None = None
    account_id: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.installation_id, field="installation_id")
        _opaque(self.host_id, field="host_id")
        _opaque(self.platform, field="platform")
        _opaque(self.native_account_id, field="native_account_id")
        if (self.bot_id is None) != (self.account_id is None):
            raise ReferenceValidationError("principal bot and login account must be supplied together")
        for name in ("bot_id", "account_id"):
            if getattr(self, name) is not None:
                _opaque(getattr(self, name), field=name)


@dataclass(frozen=True)
class UntrustedIdentityClaim:
    """A bare identifier received from content, request bodies, or model output."""

    claimed_account_id: str
    origin: str

    def __post_init__(self) -> None:
        _opaque(self.claimed_account_id, field="claimed_account_id")
        _opaque(self.origin, field="origin")


@dataclass(frozen=True)
class IdentityBinding:
    """Versioned link between one authenticated host account and one subject."""

    binding_id: str
    principal: AuthenticatedHostPrincipal
    subject: SubjectRef
    revision: int
    valid_from: datetime
    expires_at: datetime | None = None
    state: BindingState = BindingState.ACTIVE
    replaced_by: str | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _opaque(self.binding_id, field="binding_id")
        _positive(self.revision, field="binding_revision")
        if self.principal.installation_id != self.subject.installation_id:
            raise ReferenceValidationError("binding subject crosses installation")
        valid_from = normalize_utc(self.valid_from, field="valid_from")
        object.__setattr__(self, "valid_from", valid_from)
        if self.expires_at is not None:
            expires_at = normalize_utc(self.expires_at, field="expires_at")
            if expires_at <= valid_from:
                raise ReferenceValidationError("binding expires_at must be after valid_from")
            object.__setattr__(self, "expires_at", expires_at)
        if self.state is BindingState.SUPERSEDED:
            if self.replaced_by is None:
                raise ReferenceValidationError("superseded binding requires replaced_by")
            _opaque(self.replaced_by, field="replaced_by")
        elif self.replaced_by is not None:
            raise ReferenceValidationError("only superseded bindings may set replaced_by")
        if self.state is BindingState.REVOKED:
            if self.revoked_at is None:
                raise ReferenceValidationError("revoked binding requires revoked_at")
            object.__setattr__(
                self,
                "revoked_at",
                normalize_utc(self.revoked_at, field="revoked_at"),
            )
        elif self.revoked_at is not None:
            raise ReferenceValidationError("only revoked bindings may set revoked_at")


@dataclass(frozen=True)
class CapabilityGrant:
    """An explicit subject, capability, and exact scope grant."""

    grant_id: str
    subject: SubjectRef
    scope: ScopeRef
    capability: str
    tier: AuthorizationTier
    revision: int
    valid_from: datetime
    expires_at: datetime | None = None
    state: GrantState = GrantState.ACTIVE
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _opaque(self.grant_id, field="grant_id")
        _opaque(self.capability, field="capability")
        _positive(self.revision, field="grant_revision")
        if self.subject.installation_id != self.scope.installation_id:
            raise ReferenceValidationError("grant subject crosses installation")
        valid_from = normalize_utc(self.valid_from, field="valid_from")
        object.__setattr__(self, "valid_from", valid_from)
        if self.expires_at is not None:
            expires_at = normalize_utc(self.expires_at, field="expires_at")
            if expires_at <= valid_from:
                raise ReferenceValidationError("grant expires_at must be after valid_from")
            object.__setattr__(self, "expires_at", expires_at)
        if self.state is GrantState.REVOKED:
            if self.revoked_at is None:
                raise ReferenceValidationError("revoked grant requires revoked_at")
            object.__setattr__(
                self,
                "revoked_at",
                normalize_utc(self.revoked_at, field="revoked_at"),
            )
        elif self.revoked_at is not None:
            raise ReferenceValidationError("only revoked grants may set revoked_at")


@dataclass(frozen=True)
class ResolvedIdentity:
    """A binding snapshot that must be rechecked before every privileged action."""

    principal: AuthenticatedHostPrincipal
    subject: SubjectRef
    binding_id: str
    binding_revision: int
    policy_revision: int


@dataclass(frozen=True)
class AuthorizedAccess:
    """An authorization observation scoped to one action and one exact destination."""

    subject: SubjectRef
    scope: ScopeRef
    capability: str
    binding_id: str
    binding_revision: int
    grant_id: str
    grant_revision: int
    policy_revision: int


@dataclass(frozen=True)
class IdentityPolicySnapshot:
    """A detached, deterministic representation used by G1 restart fixtures."""

    policy_revision: int
    bindings: tuple[IdentityBinding, ...]
    grants: tuple[CapabilityGrant, ...]

    def __post_init__(self) -> None:
        _positive(self.policy_revision, field="policy_revision")
