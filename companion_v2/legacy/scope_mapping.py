"""Explicit, evidence-bound preparation for adopting unresolved historical scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import json

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import (
    ReferenceValidationError, ScopeKind, ScopeRef, SourceRef, SubjectKind, SubjectRef, VersionRef, normalize_utc,
)
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, ResolvedIdentity
from companion_v2.identity_policy.personas import PersonaDirectory
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.runtime import StorageRuntime


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LegacyScopeMapping:
    mapping_id: str
    original: ScopeRef
    resolved: ScopeRef
    evidence: SourceRef
    authority: str
    revision: int
    mapped_at: datetime
    identity: ResolvedIdentity
    state: str = "active"

    def __post_init__(self) -> None:
        if not self.mapping_id or not self.authority or self.mapping_id != self.mapping_id.strip():
            raise ReferenceValidationError("mapping identity and authority are required")
        if self.original.is_resolved or not self.resolved.is_resolved:
            raise ReferenceValidationError("mapping must upgrade an unresolved scope")
        if self.original.kind not in (ScopeKind.PRIVATE, ScopeKind.GROUP, ScopeKind.THREAD):
            raise ReferenceValidationError("this mapping applies only to historical conversation scopes")
        if (self.original.installation_id, self.original.platform, self.original.kind,
                self.original.native_scope_id) != (
                self.resolved.installation_id, self.resolved.platform, self.resolved.kind,
                self.resolved.native_scope_id):
            raise ReferenceValidationError("legacy mapping may only add trusted route dimensions")
        if self.evidence.scope != self.resolved or type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("mapping evidence or revision is invalid")
        principal = self.identity.principal
        if (principal.installation_id, principal.platform, principal.bot_id, principal.account_id) != (
                self.resolved.installation_id, self.resolved.platform, self.resolved.bot_id, self.resolved.account_id):
            raise ReferenceValidationError("mapping identity does not belong to the resolved bot/account route")
        if self.state not in ("active", "revoked"):
            raise ReferenceValidationError("invalid mapping state")
        object.__setattr__(self, "mapped_at", normalize_utc(self.mapped_at, field="mapped_at"))

    @property
    def original_key(self) -> str:
        return self.original.key

    def document(self) -> dict:
        evidence = {
            "source_id": self.evidence.source_id,
            "owner": self.evidence.owner,
            "scope": self.evidence.scope.document(),
            "version": asdict(self.evidence.version),
            "issued_at": self.evidence.issued_at.isoformat(),
            "expires_at": self.evidence.expires_at.isoformat() if self.evidence.expires_at else None,
        }
        return {**asdict(self), "original": self.original.document(), "resolved": self.resolved.document(),
                "evidence": evidence,
                "mapped_at": self.mapped_at.isoformat()}

    @classmethod
    def restore(cls, data: dict) -> LegacyScopeMapping:
        evidence = data["evidence"]
        reference = SourceRef(
            evidence["source_id"], evidence["owner"], ScopeRef.restore(evidence["scope"]),
            VersionRef(**evidence["version"]), datetime.fromisoformat(evidence["issued_at"]),
            datetime.fromisoformat(evidence["expires_at"]) if evidence["expires_at"] else None,
        )
        return cls(**{**data, "original": ScopeRef.restore(data["original"]),
                      "resolved": ScopeRef.restore(data["resolved"]),
                      "evidence": reference,
                      "identity": ResolvedIdentity(**{**data["identity"],
                          "principal": AuthenticatedHostPrincipal(**data["identity"]["principal"]),
                          "subject": SubjectRef(**{**data["identity"]["subject"],
                              "kind": SubjectKind(data["identity"]["subject"]["kind"])})}),
                      "mapped_at": datetime.fromisoformat(data["mapped_at"])})


class LegacyScopeMappingDirectory:
    """Records intent only; individual domain converters still prove each record."""

    def __init__(self, runtime: StorageRuntime, sources: SourceRepository) -> None:
        self.runtime, self.sources = runtime, sources

    def current(self, original: ScopeRef) -> Outcome[LegacyScopeMapping]:
        rows = self.runtime.read_all(
            "SELECT record_json FROM legacy_scope_mappings WHERE original_key = ? AND state = 'active'", (original.key,),
        )
        if not rows:
            return Outcome.failed("scope_unresolved", "legacy scope has no active evidence mapping")
        if len(rows) != 1:
            return Outcome.failed("legacy_scope_mapping_conflict", "legacy scope maps to more than one active route")
        return Outcome.success(LegacyScopeMapping.restore(json.loads(rows[0]["record_json"])))

    def register(self, mapping: LegacyScopeMapping, *, observed_at: datetime) -> Outcome[LegacyScopeMapping]:
        observed_at = normalize_utc(observed_at, field="observed_at")
        if mapping.original.installation_id != self.runtime.installation_id:
            return Outcome.failed("scope_installation_mismatch", "mapping belongs to another installation")
        with self.runtime.transaction() as connection:
            if mapping.revision != 1 or mapping.state != "active" or mapping.mapped_at > observed_at:
                return Outcome.failed("legacy_scope_mapping_invalid", "a new mapping must be an active first revision")
            valid = self._validate(mapping, observed_at)
            if valid.failure:
                return Outcome(failure=valid.failure)
            existing = connection.execute("SELECT revision FROM legacy_scope_mappings WHERE mapping_id = ?",
                                          (mapping.mapping_id,)).fetchone()
            if existing is not None:
                return Outcome.failed("legacy_scope_mapping_exists", "mapping identity is already registered")
            connection.execute("INSERT INTO legacy_scope_mappings VALUES (?, ?, ?, ?, ?)",
                               (mapping.mapping_id, mapping.original_key, mapping.revision, mapping.state,
                                _json(mapping.document())))
        return Outcome.success(mapping)

    def resolve(self, original: ScopeRef, *, observed_at: datetime) -> Outcome[ScopeRef]:
        observed_at = normalize_utc(observed_at, field="observed_at")
        with self.runtime.read_snapshot():
            result = self.current(original)
            if result.failure is not None:
                return Outcome(failure=result.failure)
            mapping = result.unwrap()
            valid = self._validate(mapping, observed_at)
            return Outcome.success(mapping.resolved) if valid.is_success else Outcome(failure=valid.failure)

    def _validate(self, mapping: LegacyScopeMapping, observed_at: datetime) -> Outcome[bool]:
        if observed_at < mapping.mapped_at:
            return Outcome.failed("legacy_scope_mapping_not_active", "mapping has not taken effect")
        evidence = self._evidence(mapping.evidence, observed_at)
        if evidence.failure is not None:
            return Outcome.failed("legacy_mapping_evidence_unavailable", "mapping evidence is absent, revoked, expired or changed")
        current = PersistentIdentityDirectory(self.runtime).resolve_authenticated(mapping.identity.principal, observed_at=observed_at)
        if (current.failure or (current.value.subject, current.value.binding_id, current.value.binding_revision) !=
                (mapping.identity.subject, mapping.identity.binding_id, mapping.identity.binding_revision)):
            return Outcome.failed("legacy_mapping_identity_changed", "the mapping's original host identity is no longer current")
        route = PersonaDirectory(self.runtime).route(mapping.resolved)
        if route is None or (route.scene_kind is ScopeKind.PRIVATE and route.user != mapping.identity.subject):
            return Outcome.failed("scope_unresolved", "mapping requires registered conversation participants")
        return Outcome.success(True)

    def _evidence(self, reference: SourceRef, observed_at: datetime) -> Outcome[bool]:
        result = self.sources.validate_reference(reference, observed_at=observed_at)
        return Outcome.success(True) if result.is_success else Outcome(failure=result.failure)

    def revoke(self, mapping_id: str, *, expected_revision: int, observed_at: datetime) -> LegacyScopeMapping:
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT record_json FROM legacy_scope_mappings WHERE mapping_id = ?",
                                     (mapping_id,)).fetchone()
            if row is None:
                raise ReferenceValidationError("legacy_scope_mapping_not_found")
            current = LegacyScopeMapping.restore(json.loads(row["record_json"]))
            if type(expected_revision) is not int or current.revision != expected_revision:
                raise ReferenceValidationError("legacy_scope_mapping_revision_conflict")
            updated = replace(current, revision=current.revision + 1,
                              mapped_at=normalize_utc(observed_at, field="observed_at"), state="revoked")
            connection.execute("UPDATE legacy_scope_mappings SET revision = ?, state = ?, record_json = ? WHERE mapping_id = ?",
                               (updated.revision, updated.state, _json(updated.document()), mapping_id))
            return updated
