"""Persistent G1 policy using the same rules and indexed, current-snapshot reads."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import (
    ReferenceValidationError, ScopeKind, ScopeRef, SubjectKind, SubjectRef,
)
from companion_v2.storage.codec import decode_timestamp, scope_values
from companion_v2.storage.runtime import StorageRuntime

from .directory import IdentityDirectory
from .models import (
    AuthenticatedHostPrincipal, AuthorizationTier, AuthorizedAccess, BindingState,
    CapabilityGrant, GrantState, IdentityBinding, IdentityPolicySnapshot, ResolvedIdentity, RoleBinding,
)
from .personas import PersonaBinding, PersonaDirectory, SelectorKind


def _dump(record: object) -> str:
    return json.dumps(asdict(record), ensure_ascii=True, sort_keys=True, default=lambda v: v.isoformat())


def _subject(data: dict) -> SubjectRef:
    return SubjectRef(data["installation_id"], SubjectKind(data["kind"]), data["subject_id"])


def _binding(payload: str) -> IdentityBinding:
    data = json.loads(payload)
    data["principal"] = AuthenticatedHostPrincipal(**data["principal"])
    data["subject"] = _subject(data["subject"])
    data["state"] = BindingState(data["state"])
    for key in ("valid_from", "expires_at", "revoked_at"):
        data[key] = decode_timestamp(data[key]) if data[key] is not None else None
    return IdentityBinding(**data)


def _grant(payload: str) -> CapabilityGrant:
    data = json.loads(payload)
    data["subject"] = _subject(data["subject"])
    scope = data["scope"]
    data["scope"] = ScopeRef.restore(scope)
    data["state"] = GrantState(data["state"])
    data["tier"] = AuthorizationTier(data["tier"])
    for key in ("valid_from", "expires_at", "revoked_at"):
        data[key] = decode_timestamp(data[key]) if data[key] is not None else None
    return CapabilityGrant(**data)


class PersistentIdentityDirectory:
    """Mutations are trusted control-plane primitives, not public management routes."""

    def __init__(self, runtime: StorageRuntime) -> None:
        self.runtime = runtime

    @property
    def revision(self) -> int:
        row = self.runtime.read_one("SELECT revision FROM identity_policy_metadata WHERE singleton = 1", ())
        if row is None:
            raise ReferenceValidationError("identity policy metadata is missing")
        return row["revision"]

    def _installation(self, installation_id: str) -> None:
        if installation_id != self.runtime.installation_id:
            raise ReferenceValidationError("identity crosses installation")

    def _expect(self, revision: int) -> None:
        if type(revision) is not int or revision != self.revision:
            raise ReferenceValidationError("identity_revision_conflict")

    def _directory(
        self, principal: AuthenticatedHostPrincipal, *, subject: SubjectRef | None = None,
        capability: str | None = None,
    ) -> IdentityDirectory:
        self._installation(principal.installation_id)
        rows = self.runtime.read_all(
            """SELECT payload_json FROM identity_bindings WHERE installation_id = ?
               AND host_id = ? AND platform = ? AND native_account_id = ? AND bot_id = ? AND account_id = ? ORDER BY revision""",
            (principal.installation_id, principal.host_id, principal.platform, principal.native_account_id,
             principal.bot_id or "", principal.account_id or ""),
        )
        grants = ()
        if subject is not None and capability is not None:
            self._installation(subject.installation_id)
            grants = tuple(_grant(row["payload_json"]) for row in self.runtime.read_all(
                "SELECT payload_json FROM identity_grants WHERE subject_kind = ? AND subject_id = ? AND capability = ?",
                (subject.kind.value, subject.subject_id, capability),
            ))
        return IdentityDirectory(
            bindings=tuple(_binding(row["payload_json"]) for row in rows),
            grants=grants, policy_revision=self.revision,
        )

    def snapshot(self) -> IdentityPolicySnapshot:
        with self.runtime.read_snapshot():
            return IdentityPolicySnapshot(
                policy_revision=self.revision,
                bindings=tuple(_binding(r["payload_json"]) for r in self.runtime.read_all(
                    "SELECT payload_json FROM identity_bindings ORDER BY binding_id", (),
                )),
                grants=tuple(_grant(r["payload_json"]) for r in self.runtime.read_all(
                    "SELECT payload_json FROM identity_grants ORDER BY grant_id", (),
                )),
            )

    def grants_for_subject(self, subject: SubjectRef) -> tuple[CapabilityGrant, ...]:
        """Read one subject's indexed grants without materializing the whole directory."""
        self._installation(subject.installation_id)
        with self.runtime.read_snapshot():
            rows = self.runtime.read_all(
                """SELECT payload_json FROM identity_grants
                   WHERE subject_kind = ? AND subject_id = ? ORDER BY grant_id""",
                (subject.kind.value, subject.subject_id),
            )
            return tuple(_grant(row["payload_json"]) for row in rows)

    def resolve_authenticated(
        self, principal: AuthenticatedHostPrincipal, *, observed_at: datetime,
    ) -> Outcome[ResolvedIdentity]:
        if principal.installation_id != self.runtime.installation_id:
            return Outcome.failed("scope_installation_mismatch", "account belongs to another installation")
        with self.runtime.read_snapshot():
            return self._directory(principal).resolve_authenticated(principal, observed_at=observed_at)

    def authorize(
        self, resolved: ResolvedIdentity, *, scope: ScopeRef, capability: str, observed_at: datetime,
    ) -> Outcome[AuthorizedAccess]:
        if (resolved.principal.installation_id != self.runtime.installation_id
                or resolved.subject.installation_id != self.runtime.installation_id):
            return Outcome.failed("scope_installation_mismatch", "account belongs to another installation")
        with self.runtime.read_snapshot():
            return self._directory(
                resolved.principal, subject=resolved.subject, capability=capability,
            ).authorize(resolved, scope=scope, capability=capability, observed_at=observed_at)

    def bind(
        self, *, binding_id: str, principal: AuthenticatedHostPrincipal, subject: SubjectRef,
        valid_from: datetime, expected_revision: int, expires_at: datetime | None = None,
    ) -> IdentityBinding:
        with self.runtime.transaction() as connection:
            self._expect(expected_revision)
            if connection.execute("SELECT 1 FROM identity_bindings WHERE binding_id = ?", (binding_id,)).fetchone():
                raise ReferenceValidationError("binding_id already exists")
            directory = self._directory(principal)
            created = directory.bind(
                binding_id=binding_id, principal=principal, subject=subject,
                valid_from=valid_from, expires_at=expires_at,
            )
            self._save_bindings(connection, directory.snapshot())
            return created

    def revoke_binding(self, binding_id: str, *, revoked_at: datetime, expected_revision: int) -> IdentityBinding:
        with self.runtime.transaction() as connection:
            self._expect(expected_revision)
            row = connection.execute("SELECT payload_json FROM identity_bindings WHERE binding_id = ?", (binding_id,)).fetchone()
            if row is None:
                raise KeyError(binding_id)
            directory = self._directory(_binding(row["payload_json"]).principal)
            updated = directory.revoke_binding(binding_id, revoked_at=revoked_at)
            self._save_bindings(connection, directory.snapshot())
            return updated

    @staticmethod
    def _save_bindings(connection, snapshot: IdentityPolicySnapshot) -> None:
        for binding in snapshot.bindings:
            principal = binding.principal
            connection.execute(
                """INSERT INTO identity_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(binding_id) DO UPDATE SET revision = excluded.revision, payload_json = excluded.payload_json""",
                (binding.binding_id, principal.installation_id, principal.host_id, principal.platform,
                 principal.native_account_id, principal.bot_id or "", principal.account_id or "", binding.revision, _dump(binding)),
            )
        connection.execute("UPDATE identity_policy_metadata SET revision = ? WHERE singleton = 1", (snapshot.policy_revision,))

    def issue_grant(
        self, *, grant_id: str, subject: SubjectRef, scope: ScopeRef, capability: str,
        tier: AuthorizationTier, valid_from: datetime, expected_revision: int,
        expires_at: datetime | None = None,
    ) -> CapabilityGrant:
        self._installation(subject.installation_id)
        with self.runtime.transaction() as connection:
            self._expect(expected_revision)
            if connection.execute("SELECT 1 FROM identity_grants WHERE grant_id = ?", (grant_id,)).fetchone():
                raise ReferenceValidationError("grant_id already exists")
            directory = IdentityDirectory(policy_revision=self.revision)
            grant = directory.issue_grant(
                grant_id=grant_id, subject=subject, scope=scope, capability=capability,
                tier=tier, valid_from=valid_from, expires_at=expires_at,
            )
            connection.execute("INSERT INTO identity_grants VALUES (?, ?, ?, ?, ?)", (
                grant.grant_id, subject.kind.value, subject.subject_id, capability, _dump(grant),
            ))
            connection.execute("UPDATE identity_policy_metadata SET revision = ? WHERE singleton = 1", (directory.snapshot().policy_revision,))
            return grant

    def revoke_grant(self, grant_id: str, *, revoked_at: datetime, expected_revision: int) -> CapabilityGrant:
        with self.runtime.transaction() as connection:
            self._expect(expected_revision)
            row = connection.execute("SELECT payload_json FROM identity_grants WHERE grant_id = ?", (grant_id,)).fetchone()
            if row is None:
                raise KeyError(grant_id)
            directory = IdentityDirectory(grants=(_grant(row["payload_json"]),), policy_revision=self.revision)
            updated = directory.revoke_grant(grant_id, revoked_at=revoked_at)
            connection.execute("UPDATE identity_grants SET payload_json = ? WHERE grant_id = ?", (_dump(updated), grant_id))
            connection.execute("UPDATE identity_policy_metadata SET revision = ? WHERE singleton = 1", (directory.snapshot().policy_revision,))
            return updated

    def resolve_role(self, scope: ScopeRef, *, observed_at: datetime) -> Outcome[RoleBinding]:
        """Registered routes use the resolver exclusively; old exact rows are compatibility-only."""
        if scope.installation_id != self.runtime.installation_id:
            return Outcome.failed("scope_installation_mismatch", "role belongs to another installation")
        with self.runtime.read_snapshot():
            personas = PersonaDirectory(self.runtime)
            if personas.route(scope) is not None:
                result = personas.resolve(scope, observed_at=observed_at)
                return Outcome.success(result.unwrap().binding) if result.is_success else Outcome(failure=result.failure)
            binding = self._exact_role_binding(scope)
            return (Outcome.success(binding) if binding else
                    Outcome.failed("role_binding_missing", "scope has no registered persona binding"))

    def role_binding(self, scope: ScopeRef, *, observed_at: datetime | None = None) -> RoleBinding | None:
        """Compatibility convenience; execution paths use resolve_role to retain diagnostics."""
        return self.resolve_role(scope, observed_at=observed_at or datetime.now(timezone.utc)).value

    def _exact_role_binding(self, scope: ScopeRef) -> RoleBinding | None:
        self._installation(scope.installation_id)
        row = self.runtime.read_one(
            "SELECT role_id, revision FROM role_bindings WHERE installation_id = ? AND platform = ? AND scope_kind = ? AND native_scope_id = ? AND bot_id = ? AND account_id = ? AND conversation_id = ? AND session_id = ?",
            scope_values(scope),
        )
        if row is None:
            return None
        return RoleBinding(scope, SubjectRef(scope.installation_id, SubjectKind.BOT, row["role_id"]), row["revision"])

    def bind_role(self, *, scope: ScopeRef, role: SubjectRef, expected_revision: int,
                  observed_at: datetime | None = None) -> RoleBinding:
        self._installation(scope.installation_id)
        self._installation(role.installation_id)
        if role.kind is not SubjectKind.BOT:
            raise ReferenceValidationError("role binding requires a bot subject")
        with self.runtime.transaction() as connection:
            personas = PersonaDirectory(self.runtime)
            route = personas.route(scope)
            if route is not None:
                now = observed_at or datetime.now(timezone.utc)
                current = self.resolve_role(scope, observed_at=now)
                if current.failure is not None and current.failure.code != "role_binding_missing":
                    raise ReferenceValidationError(current.failure.code)
                revision = current.value.revision if current.value else 0
                if type(expected_revision) is not int or expected_revision != revision:
                    raise ReferenceValidationError("role_binding_revision_conflict")
                identifier = personas.window_binding_id(scope)
                previous = personas.binding(identifier)
                selector = next(selector for selector, _ in route.selectors() if selector.kind is SelectorKind.SESSION)
                proposal = PersonaBinding(identifier, selector, role, 0, now, "exact-window-command", "trusted-control-plane")
                if previous:
                    proposal = replace(proposal, revision=previous.revision + 1)
                personas.set_binding(proposal, expected_revision=previous.revision if previous else 0, observed_at=now)
                resolved = self.resolve_role(scope, observed_at=now)
                if resolved.failure or personas.resolve(scope, observed_at=now).unwrap().selected.binding_id != identifier:
                    raise ReferenceValidationError("persona_binding_override_denied")
                return resolved.unwrap()
            current = self._exact_role_binding(scope)
            revision = current.revision if current else 0
            if type(expected_revision) is not int or expected_revision != revision:
                raise ReferenceValidationError("role_binding_revision_conflict")
            result = RoleBinding(scope, role, revision + 1)
            connection.execute(
                """INSERT INTO role_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(installation_id, platform, scope_kind, native_scope_id, bot_id, account_id, conversation_id, session_id)
                   DO UPDATE SET role_id = excluded.role_id, revision = excluded.revision""",
                (*scope_values(scope), role.subject_id, result.revision),
            )
            return result
