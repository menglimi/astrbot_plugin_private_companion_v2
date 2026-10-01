"""Dated subjective writing and its exact inputs, independent of any model or UI."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo

from companion_v2.foundation.refs import ReferenceValidationError, RoleOwnerRef, ScopeRef, SourceRef, VersionRef, normalize_utc
from companion_v2.role_work.models import RoleActivity

from .materials import JournalMaterial, validate_materials


class JournalKind(str, Enum):
    DIARY = "diary"
    DREAM = "dream"


class JournalState(str, Enum):
    ABSENT = "absent"
    ACTIVE = "active"
    DELETED = "deleted"


class JournalOrigin(str, Enum):
    GENERATED = "generated"
    MANUAL = "manual"


class DreamRecall(str, Enum):
    FULL = "full"
    FRAGMENTS = "fragments"
    AFTERGLOW = "afterglow"


def local_day(value: str) -> str:
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ReferenceValidationError("journal date must be an ISO calendar date")
    return value


def revision(value: int, *, allow_zero=False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ReferenceValidationError("journal revision is invalid")
    return value


def _text(value: str, limit=65536) -> None:
    if not isinstance(value, str) or len(value) > limit:
        raise ReferenceValidationError("journal text exceeds its storage contract")


@dataclass(frozen=True)
class JournalKey:
    owner: RoleOwnerRef
    kind: JournalKind
    local_date: str

    def __post_init__(self):
        if not isinstance(self.owner, RoleOwnerRef) or not isinstance(self.kind, JournalKind):
            raise ReferenceValidationError("journal owner and kind must be explicit")
        local_day(self.local_date)

    @classmethod
    def at(cls, owner, kind, observed_at, *, timezone):
        at = normalize_utc(observed_at, field="journal date time")
        return cls(owner, kind, at.astimezone(ZoneInfo(timezone)).date().isoformat())


@dataclass(frozen=True)
class JournalRef:
    key: JournalKey
    revision: int

    def __post_init__(self):
        if not isinstance(self.key, JournalKey):
            raise ReferenceValidationError("journal reference needs its original key")
        revision(self.revision)


@dataclass(frozen=True)
class JournalContext:
    key: JournalKey
    scope: ScopeRef
    timezone: str

    def __post_init__(self):
        if not isinstance(self.key, JournalKey) or not isinstance(self.scope, ScopeRef):
            raise ReferenceValidationError("journal context needs its original key and scope")
        if (not self.scope.is_resolved or self.scope.installation_id != self.key.owner.installation_id
                or self.scope.bot_id != self.key.owner.bot_id):
            raise ReferenceValidationError("journal scope crosses its role owner")
        ZoneInfo(self.timezone)


@dataclass(frozen=True)
class JournalDraft:
    context: JournalContext
    body: str = ""
    summary: str = ""
    afterglow: str = ""
    form: str = ""
    recall: DreamRecall | None = None
    origin: JournalOrigin = JournalOrigin.GENERATED
    sources: tuple[SourceRef, ...] = ()
    activities: tuple[VersionRef, ...] = ()
    journals: tuple[JournalRef, ...] = ()
    materials: tuple[JournalMaterial, ...] = ()

    def __post_init__(self):
        if not isinstance(self.context, JournalContext) or not isinstance(self.origin, JournalOrigin):
            raise ReferenceValidationError("journal context and writing origin must be explicit")
        for value in (self.body, self.summary, self.afterglow):
            _text(value)
        _text(self.form, 256)
        if self.context.key.kind is JournalKind.DIARY:
            if not self.body.strip() or self.recall is not None or self.afterglow:
                raise ReferenceValidationError("diaries need a body and cannot be labeled as dreams")
        elif not isinstance(self.recall, DreamRecall) or not (self.body.strip() or self.afterglow.strip()):
            raise ReferenceValidationError("dreams need an explicit recall type and remembered material")
        for values, item_type in ((self.sources, SourceRef), (self.activities, VersionRef), (self.journals, JournalRef)):
            if not isinstance(values, tuple) or any(not isinstance(item, item_type) for item in values) or len(set(values)) != len(values):
                raise ReferenceValidationError("journal inputs must be immutable unique references")
        owner = self.context.key.owner
        if any(ref.scope.installation_id != owner.installation_id or ref.scope.bot_id != owner.bot_id for ref in self.sources):
            raise ReferenceValidationError("journal source crosses its role installation or bot")
        if any(ref.key.owner != owner or ref.key == self.context.key for ref in self.journals):
            raise ReferenceValidationError("journal input crosses its owner or refers to itself")
        validate_materials(self.materials, self.sources, self.activities)


@dataclass(frozen=True)
class JournalHead:
    key: JournalKey
    revision: int
    state: JournalState
    updated_at: datetime | None


@dataclass(frozen=True)
class JournalEntry:
    reference: JournalRef
    draft: JournalDraft
    activity_evidence: tuple[RoleActivity, ...]
    updated_at: datetime


@dataclass(frozen=True)
class JournalDerivatives:
    parent: JournalRef
    summary: str = ""
    dream_fragments: tuple[str, ...] = ()
    continuity: str = ""
    fragment_origins: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self):
        if not isinstance(self.parent, JournalRef):
            raise ReferenceValidationError("derived material needs its exact journal revision")
        for value in (self.summary, self.continuity):
            _text(value)
        if not isinstance(self.dream_fragments, tuple):
            raise ReferenceValidationError("dream fragments must be immutable")
        for value in self.dream_fragments:
            _text(value)
        if (not isinstance(self.fragment_origins, tuple)
                or (self.fragment_origins and len(self.fragment_origins) != len(self.dream_fragments))):
            raise ReferenceValidationError("fragment origins must match the remembered fragments")
        for origins in self.fragment_origins:
            if (not isinstance(origins, tuple) or any(not isinstance(item, str) or not item for item in origins)
                    or len(set(origins)) != len(origins)):
                raise ReferenceValidationError("fragment origins require immutable material identities")


@dataclass(frozen=True)
class DerivativeRecord:
    material: JournalDerivatives
    revision: int
    updated_at: datetime


@dataclass(frozen=True)
class JournalReceipt:
    """An operation result has no old body that could bypass current governance."""

    operation_id: str
    action: str
    head: JournalHead
    material_revision: int = 0
