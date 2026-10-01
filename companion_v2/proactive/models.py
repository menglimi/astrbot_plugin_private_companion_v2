"""Proactive planning records that separate opportunity, evidence, thought, and delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math

from companion_v2.foundation.refs import AssetRef, ReferenceValidationError, ScopeRef, SourceRef, normalize_utc
from companion_v2.sharing.models import ShareCandidate


class ThoughtKind(str, Enum):
    CONVERSATION = "conversation"
    SHARE = "share"


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    scope: ScopeRef
    opened_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.opportunity_id, field="opportunity_id")
        opened_at = normalize_utc(self.opened_at, field="opened_at")
        expires_at = normalize_utc(self.expires_at, field="expires_at")
        if expires_at <= opened_at:
            raise ReferenceValidationError("opportunity expires_at must be after opened_at")
        object.__setattr__(self, "opened_at", opened_at)
        object.__setattr__(self, "expires_at", expires_at)

    def is_expired_at(self, observed_at: datetime) -> bool:
        return normalize_utc(observed_at, field="observed_at") >= self.expires_at


@dataclass(frozen=True)
class EvidenceSnapshot:
    scope: ScopeRef
    captured_at: datetime
    sources: tuple[SourceRef, ...] = ()
    assets: tuple[AssetRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "captured_at",
            normalize_utc(self.captured_at, field="captured_at"),
        )
        if any(item.scope != self.scope for item in self.sources):
            raise ReferenceValidationError("evidence source crosses snapshot scope")
        if any(item.scope != self.scope for item in self.assets):
            raise ReferenceValidationError("evidence asset crosses snapshot scope")
        if len(set(self.sources)) != len(self.sources):
            raise ReferenceValidationError("evidence sources must be unique")
        if len(set(self.assets)) != len(self.assets):
            raise ReferenceValidationError("evidence assets must be unique")


@dataclass(frozen=True)
class Thought:
    thought_id: str
    opportunity: Opportunity
    kind: ThoughtKind
    summary: str
    evidence: EvidenceSnapshot
    weight: float
    share_candidate: ShareCandidate | None = None

    def __post_init__(self) -> None:
        _opaque(self.thought_id, field="thought_id")
        _opaque(self.summary, field="summary")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ReferenceValidationError("thought weight must be a positive finite number")
        if self.evidence.scope != self.opportunity.scope:
            raise ReferenceValidationError("thought evidence must match opportunity scope")
        if self.kind is ThoughtKind.SHARE:
            if self.share_candidate is None:
                raise ReferenceValidationError("share thought requires a real share candidate")
            if self.share_candidate.target_scope != self.opportunity.scope:
                raise ReferenceValidationError("share candidate must match opportunity scope")
        elif self.share_candidate is not None:
            raise ReferenceValidationError("only share thoughts may carry a share candidate")


@dataclass(frozen=True)
class ThoughtSelection:
    opportunity: Opportunity
    selected: Thought
    feasible_count: int
    weight_used: bool


@dataclass(frozen=True)
class DeliveryPlan:
    plan_id: str
    selection: ThoughtSelection
    created_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.plan_id, field="plan_id")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))

    @property
    def material_id(self) -> str | None:
        candidate = self.selection.selected.share_candidate
        return candidate.material.material_id if candidate is not None else None
