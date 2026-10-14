"""Role-owned activity records and the small in-memory ledger used by fixtures."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import AssetRef, ReferenceValidationError, RoleOwnerRef, ScopeRef, SourceRef, normalize_utc
from .work_models import RoleWorkSpec


class RoleActivityState(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RoleArtifactKind(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    AUDIO = "audio"


class RoleArtifactJournalMeaning(str, Enum):
    """Content semantics set by the trusted producer, independently of media.

    READING describes collected material, not evidence of reading or finishing it.
    Neither label records publication or makes events in the content factual.
    """

    UNCLASSIFIED = "unclassified"
    CREATIVE_TEXT = "creative_text"
    READING = "reading"


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 512:
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


@dataclass(frozen=True)
class RoleReadingReceipt:
    """A completed [start, end) span using Python Unicode character offsets."""

    source: SourceRef
    content_hash: str
    text_length: int
    start_offset: int
    end_offset: int
    completed_at: datetime
    reflection: str = ""

    def __post_init__(self):
        if not isinstance(self.source, SourceRef):
            raise ReferenceValidationError("reading requires its exact original source")
        if not isinstance(self.reflection, str) or len(self.reflection) > 8192:
            raise ReferenceValidationError("reading reflection must be bounded text")
        _opaque(self.content_hash, field="reading content hash")
        if (any(type(value) is not int for value in (self.text_length, self.start_offset, self.end_offset))
                or not 0 <= self.start_offset < self.end_offset <= self.text_length):
            raise ReferenceValidationError("reading span must be nonempty and within the supplied original")
        object.__setattr__(self, "completed_at", normalize_utc(self.completed_at, field="reading completion"))
        if self.completed_at < self.source.issued_at:
            raise ReferenceValidationError("reading cannot precede its original source")

    @property
    def covers_source(self):
        return self.start_offset == 0 and self.end_offset == self.text_length


@dataclass(frozen=True)
class RoleSleepReceipt:
    """Physiological facts accumulated across one role-owned sleep episode."""

    kind: str
    base_need_minutes: int
    target_minutes: int
    slept_seconds: int = 0
    interruptions: int = 0
    early_interruptions: int = 0
    workload_score: int = 0
    quality_min: int = 70
    quality_max: int = 92
    wake_until: datetime | None = None
    oversleep_minutes: int = 0

    def __post_init__(self):
        if self.kind not in ("night", "nap", "manual"):
            raise ReferenceValidationError("sleep kind must be explicit")
        for name in ("base_need_minutes", "target_minutes"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 1440:
                raise ReferenceValidationError(f"{name} must be from 1 to 1440")
        for name, maximum in (("slept_seconds", 172800), ("interruptions", 1000),
                              ("early_interruptions", 1000), ("workload_score", 100),
                              ("quality_min", 100), ("quality_max", 100), ("oversleep_minutes", 60)):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ReferenceValidationError(f"{name} is out of range")
        if self.quality_min > self.quality_max:
            raise ReferenceValidationError("sleep quality range is reversed")
        if self.wake_until is not None:
            object.__setattr__(self, "wake_until", normalize_utc(self.wake_until, field="sleep wake grace"))


@dataclass(frozen=True)
class RoleActivity:
    activity_id: str
    role_id: str
    scope: ScopeRef
    started_at: datetime
    state: RoleActivityState
    revision: int = 1
    description: str = ""
    checkpoint: str = ""
    updated_at: datetime | None = None
    reading: RoleReadingReceipt | None = None
    work: RoleWorkSpec | None = None
    sleep: RoleSleepReceipt | None = None

    def __post_init__(self) -> None:
        _opaque(self.activity_id, field="activity_id")
        _opaque(self.role_id, field="role_id")
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("activity revision must be positive")
        if not isinstance(self.state, RoleActivityState):
            raise ReferenceValidationError("activity state must be explicit")
        if any(not isinstance(value, str) or len(value) > 16384 for value in (self.description, self.checkpoint)):
            raise ReferenceValidationError("activity description and checkpoint must be bounded text")
        object.__setattr__(self, "started_at", normalize_utc(self.started_at, field="started_at"))
        object.__setattr__(self, "updated_at", normalize_utc(
            self.started_at if self.updated_at is None else self.updated_at, field="updated_at"))
        if self.updated_at < self.started_at:
            raise ReferenceValidationError("activity update cannot precede its recorded start")
        if self.reading is not None:
            if (not isinstance(self.reading, RoleReadingReceipt) or self.state is not RoleActivityState.COMPLETED
                    or self.reading.source.scope != self.scope or self.reading.completed_at != self.updated_at):
                raise ReferenceValidationError("reading receipt must match the completed activity's scope and time")
        if self.work is not None:
            if not isinstance(self.work, RoleWorkSpec) or (self.work.source is not None and self.work.source.scope != self.scope):
                raise ReferenceValidationError("role execution must retain the original scope")
        if self.sleep is not None and (not isinstance(self.sleep, RoleSleepReceipt)
                                       or self.work is None or self.work.kind != "sleep"):
            raise ReferenceValidationError("sleep receipt must belong to a sleep activity")

    @property
    def owner(self) -> RoleOwnerRef:
        if self.scope.bot_id is None:
            raise ReferenceValidationError("role activity requires a resolved bot owner")
        return RoleOwnerRef(self.scope.installation_id, self.scope.bot_id, self.role_id)


@dataclass(frozen=True)
class RoleArtifact:
    """A completed role-owned material, never a claim that an image was generated."""

    artifact_id: str
    activity_id: str
    kind: RoleArtifactKind
    source: SourceRef
    created_at: datetime
    asset: AssetRef | None = None
    owner: RoleOwnerRef | None = None
    journal_meaning: RoleArtifactJournalMeaning = RoleArtifactJournalMeaning.UNCLASSIFIED

    def __post_init__(self) -> None:
        _opaque(self.artifact_id, field="artifact_id")
        _opaque(self.activity_id, field="activity_id")
        if not isinstance(self.kind, RoleArtifactKind):
            raise ReferenceValidationError("artifact kind must be explicit")
        if not isinstance(self.journal_meaning, RoleArtifactJournalMeaning):
            raise ReferenceValidationError("artifact journal meaning must be explicit")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))
        if self.kind is RoleArtifactKind.IMAGE and self.asset is None:
            raise ReferenceValidationError("image artifact requires an actual asset reference")
        if self.asset is not None and self.asset.scope != self.source.scope:
            raise ReferenceValidationError("artifact asset and source must share a scope")


def advance_activity(activity, *, expected_revision, state, observed_at, checkpoint=None, reading=None, work=None,
                     sleep=None):
    """Apply an explicit owner decision; elapsed wall time never advances an activity."""
    if type(expected_revision) is not int or activity.revision != expected_revision:
        raise ReferenceValidationError("activity revision conflict")
    if not isinstance(state, RoleActivityState):
        raise ReferenceValidationError("activity state must be explicit")
    transitions = {
        RoleActivityState.PLANNED: {RoleActivityState.PLANNED, RoleActivityState.ACTIVE, RoleActivityState.CANCELLED},
        RoleActivityState.ACTIVE: {RoleActivityState.ACTIVE, RoleActivityState.PAUSED,
                                  RoleActivityState.COMPLETED, RoleActivityState.CANCELLED},
        RoleActivityState.PAUSED: {RoleActivityState.PAUSED, RoleActivityState.ACTIVE,
                                  RoleActivityState.COMPLETED, RoleActivityState.CANCELLED},
        RoleActivityState.COMPLETED: set(),
        RoleActivityState.CANCELLED: set(),
    }
    if state not in transitions[activity.state]:
        raise ReferenceValidationError("activity transition is not valid for its current lifecycle state")
    at = normalize_utc(observed_at, field="observed_at")
    if at < activity.updated_at:
        raise ReferenceValidationError("activity update cannot move backwards in time")
    return replace(activity, state=state, revision=activity.revision + 1, updated_at=at,
                   checkpoint=activity.checkpoint if checkpoint is None else checkpoint, reading=reading,
                   work=activity.work if work is None else work,
                   sleep=activity.sleep if sleep is None else sleep)


class RoleLifeLedger:
    """G5 local role state. It stores only role activities and real artifact references."""

    def __init__(self) -> None:
        self._activities: dict[str, RoleActivity] = {}
        self._artifacts: dict[str, RoleArtifact] = {}

    def add_activity(self, activity: RoleActivity) -> RoleActivity:
        activity.owner
        existing = self._activities.get(activity.activity_id)
        if existing is None:
            self._activities[activity.activity_id] = activity
            return activity
        if existing != activity:
            raise ReferenceValidationError("activity_id is already bound to another activity")
        return existing

    def transition_activity(
        self,
        activity_id: str,
        *,
        expected_revision: int,
        state: RoleActivityState,
        owner: RoleOwnerRef,
        observed_at: datetime | None = None,
        checkpoint: str | None = None,
        reading: RoleReadingReceipt | None = None,
        work: RoleWorkSpec | None = None,
        sleep: RoleSleepReceipt | None = None,
    ) -> RoleActivity:
        activity = self._activities.get(activity_id)
        if activity is None or activity.owner != owner:
            raise KeyError(activity_id)
        updated = advance_activity(activity, expected_revision=expected_revision, state=state,
                                   observed_at=activity.updated_at if observed_at is None else observed_at,
                                   checkpoint=checkpoint, reading=reading, work=work, sleep=sleep)
        self._activities[activity_id] = updated
        return updated

    def add_artifact(self, artifact: RoleArtifact) -> RoleArtifact:
        activity = self._activities.get(artifact.activity_id)
        if activity is None:
            raise ReferenceValidationError("artifact activity does not exist")
        if activity.scope != artifact.source.scope:
            raise ReferenceValidationError("artifact source does not match activity scope")
        if artifact.owner is not None and artifact.owner != activity.owner:
            raise ReferenceValidationError("artifact cannot change the activity's role owner")
        artifact = replace(artifact, owner=activity.owner)
        existing = self._artifacts.get(artifact.artifact_id)
        if existing is None:
            self._artifacts[artifact.artifact_id] = artifact
            return artifact
        if existing != artifact:
            raise ReferenceValidationError("artifact_id is already bound to another artifact")
        return existing

    def artifact(self, artifact_id: str, *, owner: RoleOwnerRef) -> RoleArtifact:
        artifact = self._artifacts[artifact_id]
        if artifact.owner != owner:
            raise KeyError(artifact_id)
        return artifact

    def artifacts_for_scope(self, scope: ScopeRef, *, owner: RoleOwnerRef) -> tuple[RoleArtifact, ...]:
        return tuple(item for item in self._artifacts.values() if item.source.scope == scope and item.owner == owner)

    def artifacts_for_role(self, owner: RoleOwnerRef) -> tuple[RoleArtifact, ...]:
        """Trusted owner inventory only; source ACL still governs any audience projection."""
        return tuple(item for item in self._artifacts.values() if item.owner == owner)
