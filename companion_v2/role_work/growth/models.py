"""Versioned, source-backed skill and long-term goal records for one role."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import (
    ReferenceValidationError,
    RoleOwnerRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    normalize_utc,
)


class GrowthKind(str, Enum):
    SKILL = "skill"
    GOAL = "goal"


class GrowthState(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    RETIRED = "retired"


def _text(value: str, *, field: str, maximum: int, empty: bool = False) -> None:
    if (not isinstance(value, str) or len(value) > maximum
            or (not empty and not value.strip())):
        raise ReferenceValidationError(f"{field} must be bounded text")


@dataclass(frozen=True)
class RoleGrowthRecord:
    growth_id: str
    owner: RoleOwnerRef
    scope: ScopeRef
    kind: GrowthKind
    title: str
    description: str
    progress_note: str
    sources: tuple[SourceRef, ...]
    created_at: datetime
    updated_at: datetime
    revision: int = 1
    state: GrowthState = GrowthState.PROPOSED
    proposed_by: SubjectRef | None = None
    confirmed_by: SubjectRef | None = None
    changed_by: SubjectRef | None = None

    def __post_init__(self) -> None:
        _text(self.growth_id, field="growth_id", maximum=512)
        if not isinstance(self.owner, RoleOwnerRef):
            raise ReferenceValidationError("growth needs a stable role owner")
        if (not isinstance(self.scope, ScopeRef) or not self.scope.is_resolved
                or self.scope.kind is not ScopeKind.PRIVATE
                or self.scope.installation_id != self.owner.installation_id
                or self.scope.bot_id != self.owner.bot_id):
            raise ReferenceValidationError("growth needs its role's resolved private scope")
        if not isinstance(self.kind, GrowthKind) or not isinstance(self.state, GrowthState):
            raise ReferenceValidationError("growth kind and state must be explicit")
        _text(self.title, field="title", maximum=512)
        _text(self.description, field="description", maximum=8192, empty=True)
        _text(self.progress_note, field="progress_note", maximum=8192, empty=True)
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ReferenceValidationError("growth requires at least one original source")
        if any(not isinstance(source, SourceRef) for source in self.sources):
            raise ReferenceValidationError("growth sources must be SourceRef values")
        if len(set(self.sources)) != len(self.sources):
            raise ReferenceValidationError("growth sources must be unique")
        for source in self.sources:
            if (not source.scope.is_resolved or source.scope.kind is not ScopeKind.PRIVATE
                    or source.scope.installation_id != self.owner.installation_id
                    or source.scope.bot_id != self.owner.bot_id):
                raise ReferenceValidationError("growth source must remain in this role's private Bot scope")
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("growth revision must be positive")
        for name in ("proposed_by", "confirmed_by", "changed_by"):
            actor = getattr(self, name)
            if actor is not None and (
                not isinstance(actor, SubjectRef)
                or actor.kind is not SubjectKind.HUMAN
                or actor.installation_id != self.owner.installation_id
            ):
                raise ReferenceValidationError(f"{name} must be an identified human from this installation")
        if self.proposed_by is None:
            raise ReferenceValidationError("growth proposal needs an attributed human author")
        if self.state is GrowthState.PROPOSED and self.confirmed_by is not None:
            raise ReferenceValidationError("a proposed growth record has no current confirmation")
        if self.state in (GrowthState.ACTIVE, GrowthState.PAUSED, GrowthState.ACHIEVED) and self.confirmed_by is None:
            raise ReferenceValidationError("an active growth record needs an attributed confirmation")
        if self.kind is GrowthKind.SKILL and self.state is GrowthState.ACHIEVED:
            raise ReferenceValidationError("a skill is not a binary achieved goal")
        created_at = normalize_utc(self.created_at, field="created_at")
        updated_at = normalize_utc(self.updated_at, field="updated_at")
        if updated_at < created_at or any(source.issued_at > updated_at for source in self.sources):
            raise ReferenceValidationError("growth timestamps precede their original evidence")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


def confirm_growth(
    record: RoleGrowthRecord, *, expected_revision: int, observed_at: datetime,
    scope: ScopeRef, actor: SubjectRef,
) -> RoleGrowthRecord:
    if type(expected_revision) is not int or record.revision != expected_revision:
        raise ReferenceValidationError("growth revision conflict")
    target = GrowthState.ACTIVE
    allowed = {GrowthState.PROPOSED, GrowthState.PAUSED}
    if record.state not in allowed:
        raise ReferenceValidationError("growth record cannot be activated from its current state")
    return _transition(record, target=target, expected_revision=expected_revision,
                       observed_at=observed_at, scope=scope, actor=actor)


def transition_growth(
    record: RoleGrowthRecord, *, state: GrowthState, expected_revision: int,
    observed_at: datetime, scope: ScopeRef, actor: SubjectRef,
) -> RoleGrowthRecord:
    if type(expected_revision) is not int or record.revision != expected_revision:
        raise ReferenceValidationError("growth revision conflict")
    allowed = {
        GrowthState.PROPOSED: {GrowthState.ACTIVE, GrowthState.RETIRED},
        GrowthState.ACTIVE: {GrowthState.PAUSED, GrowthState.ACHIEVED, GrowthState.RETIRED},
        GrowthState.PAUSED: {GrowthState.ACTIVE, GrowthState.ACHIEVED, GrowthState.RETIRED},
        GrowthState.ACHIEVED: set(),
        GrowthState.RETIRED: set(),
    }
    if state not in allowed[record.state]:
        raise ReferenceValidationError("growth transition is not valid for its current state")
    if record.kind is GrowthKind.SKILL and state is GrowthState.ACHIEVED:
        raise ReferenceValidationError("skill growth uses qualitative progress, not achieved status")
    return _transition(record, target=state, expected_revision=expected_revision,
                       observed_at=observed_at, scope=scope, actor=actor)


def _transition(record, *, target, expected_revision, observed_at, scope, actor):
    if (not isinstance(actor, SubjectRef) or actor.kind is not SubjectKind.HUMAN
            or actor.installation_id != record.owner.installation_id):
        raise ReferenceValidationError("growth transition needs the identified human who confirmed it")
    at = normalize_utc(observed_at, field="growth transition time")
    if at < record.updated_at:
        raise ReferenceValidationError("growth update cannot move backwards in time")
    return RoleGrowthRecord(
        growth_id=record.growth_id, owner=record.owner, scope=scope, kind=record.kind,
        title=record.title, description=record.description, progress_note=record.progress_note,
        sources=record.sources, created_at=record.created_at, updated_at=at,
        revision=record.revision + 1, state=target,
        proposed_by=record.proposed_by,
        confirmed_by=actor if target is GrowthState.ACTIVE else record.confirmed_by,
        changed_by=actor,
    )


def revise_growth(
    record: RoleGrowthRecord, *, expected_revision: int, title: str,
    description: str, progress_note: str, sources: tuple[SourceRef, ...],
    observed_at: datetime, scope: ScopeRef, actor: SubjectRef,
) -> RoleGrowthRecord:
    if type(expected_revision) is not int or record.revision != expected_revision:
        raise ReferenceValidationError("growth revision conflict")
    if record.state in (GrowthState.ACHIEVED, GrowthState.RETIRED):
        raise ReferenceValidationError("closed growth record cannot be revised")
    if not isinstance(actor, SubjectRef) or actor.kind is not SubjectKind.HUMAN:
        raise ReferenceValidationError("growth revision needs an identified human author")
    at = normalize_utc(observed_at, field="growth revision time")
    if at < record.updated_at:
        raise ReferenceValidationError("growth update cannot move backwards in time")
    return RoleGrowthRecord(
        growth_id=record.growth_id, owner=record.owner, scope=scope, kind=record.kind,
        title=title, description=description, progress_note=progress_note, sources=tuple(sources),
        created_at=record.created_at, updated_at=at, revision=record.revision + 1,
        state=GrowthState.PROPOSED, proposed_by=actor,
        confirmed_by=None, changed_by=actor,
    )


def apply_growth_progress(
    record: RoleGrowthRecord, *, expected_revision: int, progress_note: str,
    sources: tuple[SourceRef, ...], observed_at: datetime, scope: ScopeRef,
    actor: SubjectRef,
) -> RoleGrowthRecord:
    if type(expected_revision) is not int or record.revision != expected_revision:
        raise ReferenceValidationError("growth revision conflict")
    if record.state not in (GrowthState.ACTIVE, GrowthState.PAUSED):
        raise ReferenceValidationError("only confirmed, open growth accepts progress")
    if scope != record.scope or (not isinstance(actor, SubjectRef)
            or actor.kind is not SubjectKind.HUMAN
            or actor.installation_id != record.owner.installation_id):
        raise ReferenceValidationError("growth progress needs its original scope and human reviewer")
    _text(progress_note, field="progress_note", maximum=8192)
    if (not isinstance(sources, tuple) or any(not isinstance(source, SourceRef) or source.scope != scope
            for source in sources)):
        raise ReferenceValidationError("growth progress sources must use the original private scope")
    at = normalize_utc(observed_at, field="growth progress time")
    if at < record.updated_at:
        raise ReferenceValidationError("growth update cannot move backwards in time")
    merged = tuple(dict.fromkeys((*record.sources, *sources)))
    return RoleGrowthRecord(
        growth_id=record.growth_id, owner=record.owner, scope=record.scope, kind=record.kind,
        title=record.title, description=record.description, progress_note=progress_note,
        sources=merged, created_at=record.created_at, updated_at=at,
        revision=record.revision + 1, state=record.state,
        proposed_by=record.proposed_by, confirmed_by=record.confirmed_by, changed_by=actor,
    )
