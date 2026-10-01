"""Value objects for the reading archive.

The archive is a pure provider contract: an entry carries catalog metadata and a
source reference that points at the provider-owned asset. The work's text and images
are never stored here, so adding manga later needs a new provider, not a new column.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import ReferenceValidationError, normalize_utc


class EntryKind(str, Enum):
    NOVEL = "novel"
    MANGA = "manga"
    OTHER = "other"


class EntryOrigin(str, Enum):
    """Who created this entry. A provider entry outranks a manual one."""

    PROVIDER = "provider"
    MANUAL = "manual"


class EntryState(str, Enum):
    AVAILABLE = "available"
    READING = "reading"
    FINISHED = "finished"
    WITHDRAWN = "withdrawn"


class ConsentState(str, Enum):
    GRANTED = "granted"
    REVOKED = "revoked"


MAX_TITLE = 200
MAX_AUTHOR = 120
MAX_NOTE = 2000
MAX_REVIEW = 4000
MAX_ASSET_REF = 512
MAX_METADATA_BYTES = 4096


def _text(value, *, field, maximum, required=True):
    if value is None:
        value = ""
    if not isinstance(value, str) or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a trimmed string")
    if len(value) > maximum:
        raise ReferenceValidationError(f"{field} exceeds {maximum} characters")
    if required and not value:
        raise ReferenceValidationError(f"{field} must not be blank")
    return value


def _opaque(value, *, field, maximum=MAX_ASSET_REF):
    return _text(value, field=field, maximum=maximum)


@dataclass(frozen=True)
class AssetReference:
    """Where the provider keeps this work's asset; the archive never copies it."""

    provider_id: str
    provider_version: str
    asset_ref: str

    def __post_init__(self):
        _opaque(self.provider_id, field="provider_id", maximum=128)
        _opaque(self.provider_version, field="provider_version", maximum=32)
        _opaque(self.asset_ref, field="asset_ref", maximum=MAX_ASSET_REF)


@dataclass(frozen=True)
class ArchiveEntry:
    entry_id: str
    kind: EntryKind
    title: str
    author: str
    origin: EntryOrigin
    state: EntryState
    revision: int
    created_at: datetime
    updated_at: datetime
    source: AssetReference | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        _opaque(self.entry_id, field="entry_id", maximum=128)
        _text(self.title, field="title", maximum=MAX_TITLE)
        _text(self.author, field="author", maximum=MAX_AUTHOR, required=False)
        if not isinstance(self.kind, EntryKind):
            raise ReferenceValidationError("kind must be an EntryKind")
        if not isinstance(self.origin, EntryOrigin):
            raise ReferenceValidationError("origin must be an EntryOrigin")
        if not isinstance(self.state, EntryState):
            raise ReferenceValidationError("state must be an EntryState")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ReferenceValidationError("entry revision must be a positive integer")
        # A provider entry must name its asset; a manual entry has nothing to point at.
        if self.origin is EntryOrigin.PROVIDER and self.source is None:
            raise ReferenceValidationError("a provider entry requires its source reference")
        if self.source is not None and not isinstance(self.source, AssetReference):
            raise ReferenceValidationError("source must be an AssetReference")
        keys = [key for key, _ in self.metadata]
        if len(set(keys)) != len(keys):
            raise ReferenceValidationError("metadata keys must be unique")
        for key, value in self.metadata:
            _opaque(key, field="metadata key", maximum=64)
            if not isinstance(value, str) or len(value) > 512:
                raise ReferenceValidationError("metadata values must be bounded strings")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class ReadingProgress:
    entry_id: str
    position: tuple[tuple[str, str], ...]
    percent: int
    note: str
    updated_at: datetime

    def __post_init__(self):
        _opaque(self.entry_id, field="entry_id", maximum=128)
        if type(self.percent) is not int or isinstance(self.percent, bool) or not 0 <= self.percent <= 100:
            raise ReferenceValidationError("percent must be an integer from 0 to 100")
        _text(self.note, field="note", maximum=MAX_NOTE, required=False)
        # The position is provider-defined: a page number, a chapter, a scroll offset.
        for key, value in self.position:
            _opaque(key, field="position key", maximum=64)
            if not isinstance(value, str) or len(value) > 512:
                raise ReferenceValidationError("position values must be bounded strings")
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class ArchiveReview:
    review_id: str
    entry_id: str
    body: str
    rating: int | None
    evidence: tuple[str, ...]
    revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        _opaque(self.review_id, field="review_id", maximum=128)
        _opaque(self.entry_id, field="entry_id", maximum=128)
        _text(self.body, field="review body", maximum=MAX_REVIEW)
        if self.rating is not None and (type(self.rating) is not int or isinstance(self.rating, bool)
                                        or not 1 <= self.rating <= 5):
            raise ReferenceValidationError("rating must be null or an integer from 1 to 5")
        # A review is grounded in what was actually read, never in recollection alone.
        if not self.evidence:
            raise ReferenceValidationError("a review requires at least one reading reference")
        if len(set(self.evidence)) != len(self.evidence):
            raise ReferenceValidationError("review references must be unique")
        for reference in self.evidence:
            _opaque(reference, field="review reference", maximum=512)
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ReferenceValidationError("review revision must be a positive integer")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class ArchiveConsent:
    """Per-entry consent for one subject; it never replaces identity policy."""

    entry_id: str
    subject_json: str
    state: ConsentState
    revision: int
    updated_at: datetime

    def __post_init__(self):
        _opaque(self.entry_id, field="entry_id", maximum=128)
        _opaque(self.subject_json, field="subject_json", maximum=512)
        if not isinstance(self.state, ConsentState):
            raise ReferenceValidationError("consent state must be a ConsentState")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ReferenceValidationError("consent revision must be a positive integer")
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))
