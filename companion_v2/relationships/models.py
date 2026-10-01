"""Versioned relationship context kept separate from user facts and preferences."""

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


class RelationshipMemoryKind(str, Enum):
    CONTEXT = "context"
    EMOTION_EPISODE = "emotion_episode"


class RelationshipMemoryState(str, Enum):
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    ADOPTED = "adopted"
    RETRACTED = "retracted"


class EmotionSubject(str, Enum):
    ROLE = "role"
    HUMAN = "human"


def _opaque(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 512:
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")


@dataclass(frozen=True)
class RelationshipMemory:
    """One sourced interpretation about a single role/person relationship.

    ``interpretation`` is the role's authored perspective, not an objective user
    profile. User facts, preferences and learned expression rules have separate
    owners and are deliberately not represented by this record.
    """

    memory_id: str
    owner: RoleOwnerRef
    subject: SubjectRef
    scope: ScopeRef
    kind: RelationshipMemoryKind
    interpretation: str
    sources: tuple[SourceRef, ...]
    created_at: datetime
    observed_at: datetime
    revision: int = 1
    state: RelationshipMemoryState = RelationshipMemoryState.PROPOSED
    emotion_subject: EmotionSubject | None = None
    updated_at: datetime | None = None
    reviewed_by: SubjectRef | None = None
    adopted_by: SubjectRef | None = None
    retracted_by: SubjectRef | None = None
    revised_by: SubjectRef | None = None

    def __post_init__(self) -> None:
        _opaque(self.memory_id, field="memory_id")
        if not isinstance(self.owner, RoleOwnerRef):
            raise ReferenceValidationError("relationship memory requires a stable role owner")
        if not isinstance(self.subject, SubjectRef) or self.subject.kind is not SubjectKind.HUMAN:
            raise ReferenceValidationError("relationship memory requires a resolved human subject")
        if self.subject.installation_id != self.owner.installation_id:
            raise ReferenceValidationError("relationship memory subject crosses installation")
        if (not isinstance(self.scope, ScopeRef) or not self.scope.is_resolved
                or self.scope.kind is not ScopeKind.PRIVATE
                or self.scope.installation_id != self.owner.installation_id
                or self.scope.bot_id != self.owner.bot_id):
            raise ReferenceValidationError("relationship memory needs its role's resolved private scope")
        if not isinstance(self.kind, RelationshipMemoryKind):
            raise ReferenceValidationError("relationship memory kind must be explicit")
        if not isinstance(self.state, RelationshipMemoryState):
            raise ReferenceValidationError("relationship memory state must be explicit")
        for field in ("reviewed_by", "adopted_by", "retracted_by", "revised_by"):
            reviewer = getattr(self, field)
            if reviewer is not None and (
                not isinstance(reviewer, SubjectRef)
                or reviewer.kind is not SubjectKind.HUMAN
                or reviewer.installation_id != self.owner.installation_id
            ):
                raise ReferenceValidationError(f"{field} must be a human from this installation")
        if self.state is RelationshipMemoryState.PROPOSED and any(
            reviewer is not None for reviewer in (self.reviewed_by, self.adopted_by, self.retracted_by)
        ):
            raise ReferenceValidationError("a proposed relationship memory has no review receipt")
        if self.adopted_by is not None and self.reviewed_by is None:
            raise ReferenceValidationError("adoption requires an attributed review")
        if self.retracted_by is not None and self.state is not RelationshipMemoryState.RETRACTED:
            raise ReferenceValidationError("only a retracted memory may carry a retraction receipt")
        if self.kind is RelationshipMemoryKind.EMOTION_EPISODE:
            if not isinstance(self.emotion_subject, EmotionSubject):
                raise ReferenceValidationError("emotion episode must identify whose emotion is described")
        elif self.emotion_subject is not None:
            raise ReferenceValidationError("relationship context does not name an emotion subject")
        if not isinstance(self.interpretation, str) or not self.interpretation.strip() or len(self.interpretation) > 16384:
            raise ReferenceValidationError("relationship interpretation must be non-blank bounded text")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ReferenceValidationError("relationship memory requires at least one source reference")
        if any(not isinstance(source, SourceRef) for source in self.sources):
            raise ReferenceValidationError("relationship memory sources must be SourceRef values")
        if len(set(self.sources)) != len(self.sources):
            raise ReferenceValidationError("relationship memory sources must be unique")
        for source in self.sources:
            if (source.scope.kind is not ScopeKind.PRIVATE or not source.scope.is_resolved
                    or source.scope.installation_id != self.owner.installation_id
                    or source.scope.bot_id != self.owner.bot_id):
                raise ReferenceValidationError("relationship memory source must retain a private scope for this role")
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("relationship memory revision must be positive")
        created_at = normalize_utc(self.created_at, field="created_at")
        observed_at = normalize_utc(self.observed_at, field="observed_at")
        updated_at = normalize_utc(
            self.created_at if self.updated_at is None else self.updated_at,
            field="updated_at",
        )
        if observed_at > updated_at or created_at > updated_at:
            raise ReferenceValidationError("relationship memory timestamps are inconsistent")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "updated_at", updated_at)


def transition_memory(memory: RelationshipMemory, *, state: RelationshipMemoryState,
                      expected_revision: int, observed_at: datetime,
                      scope: ScopeRef, actor: SubjectRef) -> RelationshipMemory:
    if type(expected_revision) is not int or memory.revision != expected_revision:
        raise ReferenceValidationError("relationship memory revision conflict")
    allowed = {
        RelationshipMemoryState.PROPOSED: {RelationshipMemoryState.REVIEWED, RelationshipMemoryState.RETRACTED},
        RelationshipMemoryState.REVIEWED: {RelationshipMemoryState.ADOPTED, RelationshipMemoryState.RETRACTED},
        RelationshipMemoryState.ADOPTED: {RelationshipMemoryState.RETRACTED},
        RelationshipMemoryState.RETRACTED: set(),
    }
    if not isinstance(state, RelationshipMemoryState) or state not in allowed[memory.state]:
        raise ReferenceValidationError("relationship memory transition is not valid")
    if (not isinstance(actor, SubjectRef) or actor.kind is not SubjectKind.HUMAN
            or actor.installation_id != memory.owner.installation_id):
        raise ReferenceValidationError("relationship memory transition requires an identified human reviewer")
    if state is RelationshipMemoryState.ADOPTED and memory.reviewed_by is None:
        raise ReferenceValidationError("relationship memory cannot be adopted without an attributed review")
    at = normalize_utc(observed_at, field="observed_at")
    if at < memory.updated_at:
        raise ReferenceValidationError("relationship memory update cannot move backwards in time")
    return RelationshipMemory(
        memory_id=memory.memory_id,
        owner=memory.owner,
        subject=memory.subject,
        scope=scope,
        kind=memory.kind,
        interpretation=memory.interpretation,
        sources=memory.sources,
        created_at=memory.created_at,
        observed_at=memory.observed_at,
        revision=memory.revision + 1,
        state=state,
        emotion_subject=memory.emotion_subject,
        updated_at=at,
        reviewed_by=actor if state is RelationshipMemoryState.REVIEWED else memory.reviewed_by,
        adopted_by=actor if state is RelationshipMemoryState.ADOPTED else memory.adopted_by,
        retracted_by=actor if state is RelationshipMemoryState.RETRACTED else memory.retracted_by,
        revised_by=memory.revised_by,
    )


def revise_memory(memory: RelationshipMemory, *, expected_revision: int,
                  interpretation: str, sources: tuple[SourceRef, ...],
                  observed_at: datetime, scope: ScopeRef, actor: SubjectRef | None = None) -> RelationshipMemory:
    if type(expected_revision) is not int or memory.revision != expected_revision:
        raise ReferenceValidationError("relationship memory revision conflict")
    if memory.state is RelationshipMemoryState.RETRACTED:
        raise ReferenceValidationError("retracted relationship memory cannot be revised")
    at = normalize_utc(observed_at, field="observed_at")
    if at < memory.updated_at:
        raise ReferenceValidationError("relationship memory update cannot move backwards in time")
    return RelationshipMemory(
        memory_id=memory.memory_id,
        owner=memory.owner,
        subject=memory.subject,
        scope=scope,
        kind=memory.kind,
        interpretation=interpretation,
        sources=sources,
        created_at=memory.created_at,
        observed_at=memory.observed_at,
        revision=memory.revision + 1,
        state=RelationshipMemoryState.PROPOSED,
        emotion_subject=memory.emotion_subject,
        updated_at=at,
        reviewed_by=None,
        adopted_by=None,
        retracted_by=None,
        revised_by=actor,
    )
