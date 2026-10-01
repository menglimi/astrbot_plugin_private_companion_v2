"""Narrow host and policy ports; no AstrBot type enters the G1 core."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeRef

from .models import AuthenticatedHostPrincipal, AuthorizedAccess, ResolvedIdentity, RoleBinding


class RoleBindingPort(Protocol):
    """Read the current trusted binding, without selecting a role from message text."""

    def resolve_role(self, scope: ScopeRef, *, observed_at: datetime) -> Outcome[RoleBinding]:
        """Resolve the trusted current role, retaining missing/conflict diagnostics."""


class TrustedHostIdentityPort(Protocol):
    """Returns a principal only after the host authenticates the real event/session."""

    def authenticated_principal(self, host_event: object) -> Outcome[AuthenticatedHostPrincipal]:
        """Resolve trusted host identity without consulting content-provided IDs."""


class IdentityAuthorizationPort(Protocol):
    """Contract consumed by domains before reading, writing, or delivering."""

    def resolve_authenticated(
        self,
        principal: AuthenticatedHostPrincipal,
        *,
        observed_at: datetime,
    ) -> Outcome[ResolvedIdentity]:
        """Resolve a current binding from authenticated host identity."""

    def authorize(
        self,
        resolved: ResolvedIdentity,
        *,
        scope: ScopeRef,
        capability: str,
        observed_at: datetime,
    ) -> Outcome[AuthorizedAccess]:
        """Recheck current binding and exact-scope capability access."""
