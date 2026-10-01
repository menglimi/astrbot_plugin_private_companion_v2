"""Source, evidence, and asset records with explicit governance state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import (
    AssetRef,
    AudienceRef,
    ReferenceValidationError,
    SourceRef,
    VersionRef,
    normalize_utc,
)


class GovernanceState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


def _positive(value: int, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReferenceValidationError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class SourceRecord:
    reference: SourceRef
    audience: AudienceRef
    content_hash: str
    payload: str
    state: GovernanceState = GovernanceState.ACTIVE
    governance_revision: int = 1

    def __post_init__(self) -> None:
        if self.audience.scope != self.reference.scope:
            raise ReferenceValidationError("source audience must use the source scope")
        _opaque(self.content_hash, field="content_hash")
        if not isinstance(self.payload, str):
            raise ReferenceValidationError("source payload must be text")
        _positive(self.governance_revision, field="source_governance_revision")


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source: SourceRef
    version: VersionRef
    observed_at: datetime
    content_hash: str
    payload: str
    state: GovernanceState = GovernanceState.ACTIVE
    governance_revision: int = 1

    def __post_init__(self) -> None:
        _opaque(self.evidence_id, field="evidence_id")
        object.__setattr__(
            self,
            "observed_at",
            normalize_utc(self.observed_at, field="observed_at"),
        )
        _opaque(self.content_hash, field="content_hash")
        if not isinstance(self.payload, str):
            raise ReferenceValidationError("evidence payload must be text")
        _positive(self.governance_revision, field="evidence_governance_revision")


@dataclass(frozen=True)
class AssetRecord:
    reference: AssetRef
    audience: AudienceRef
    state: GovernanceState = GovernanceState.ACTIVE
    governance_revision: int = 1

    def __post_init__(self) -> None:
        if self.audience.scope != self.reference.scope:
            raise ReferenceValidationError("asset audience must use the asset scope")
        _positive(self.governance_revision, field="asset_governance_revision")
