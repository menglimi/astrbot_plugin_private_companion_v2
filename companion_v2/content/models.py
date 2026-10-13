"""Local domain values, not a second public provider or identity protocol."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

MAX_MANUSCRIPT_BYTES = 1_048_576
MAX_CHAPTERS = 512
MAX_SOURCES = 64
MAX_READ_CHARS = 4096


class ContentError(ValueError):
    """A stable local failure code without another owner's private details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def identifier(value: str) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 512 or "\x00" in value):
        raise ContentError("invalid_identifier")
    return value


def integer(value: int, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContentError("invalid_range")
    return value


def canonical(value: Any) -> str:
    try:
        # Reject Python-only values before JSON can silently coerce keys/tuples.
        def validate(item: Any) -> None:
            if item is None or type(item) in (str, bool, int, float):
                return
            if type(item) is list:
                for child in item:
                    validate(child)
                return
            if type(item) is dict and all(type(key) is str for key in item):
                for child in item.values():
                    validate(child)
                return
            raise ContentError("invalid_json")

        validate(value)
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
        return result
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ContentError("invalid_json") from exc


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JsonObject:
    """An immutable copy of a host-owned JSON reference or audit snapshot."""

    encoded: str

    def __post_init__(self) -> None:
        try:
            value = json.loads(self.encoded)
        except (TypeError, ValueError) as exc:
            raise ContentError("invalid_json") from exc
        if not isinstance(value, dict) or not value:
            raise ContentError("object_required")
        encoded = canonical(value)
        if len(encoded.encode("utf-8")) > 65_536:
            raise ContentError("metadata_too_large")
        object.__setattr__(self, "encoded", encoded)

    @classmethod
    def capture(cls, value: dict[str, Any]) -> JsonObject:
        return cls(canonical(value))

    def value(self) -> dict[str, Any]:
        return json.loads(self.encoded)


@dataclass(frozen=True)
class WorkOwner:
    """Resolved by the host; sessions and runtime generations are not owners."""

    installation_id: str
    bot_id: str
    role_id: str
    owner_key: str

    def __post_init__(self) -> None:
        for value in (self.installation_id, self.bot_id, self.role_id, self.owner_key):
            identifier(value)

    def value(self) -> dict[str, str]:
        return dict(installation_id=self.installation_id, bot_id=self.bot_id,
                    role_id=self.role_id, owner_key=self.owner_key)

    @property
    def key(self) -> str:
        return digest(canonical(self.value()))


@dataclass(frozen=True)
class Origin:
    """Keep the original envelope, caller, role and audience independently."""

    request_id: str
    request: JsonObject
    actor: JsonObject
    role: JsonObject
    audience: JsonObject
    request_identity: JsonObject | None = None

    def __post_init__(self) -> None:
        identifier(self.request_id)
        if not all(isinstance(value, JsonObject) for value in (
                self.request, self.actor, self.role, self.audience)):
            raise ContentError("object_required")
        if self.request_identity is not None and not isinstance(self.request_identity, JsonObject):
            raise ContentError("object_required")

    def summary(self) -> dict[str, Any]:
        # The envelope may contain manuscript text. It is stored for audit but
        # never echoed through lists, pagination metadata or operation receipts.
        value = dict(request_id=self.request_id, actor=self.actor.value(),
                     role=self.role.value(), audience=self.audience.value())
        if self.request_identity is not None:
            value["request_identity"] = self.request_identity.value()
        return value

    def value(self) -> dict[str, Any]:
        return {**self.summary(), "request": self.request.value()}

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> Origin:
        return cls(value["request_id"], *(JsonObject.capture(value[key]) for key
                   in ("request", "actor", "role", "audience")),
                   JsonObject.capture(value["request_identity"]) if value.get("request_identity") else None)


@dataclass(frozen=True)
class Call:
    origin: Origin
    before_dispatch: Callable[[], None]

    def __post_init__(self) -> None:
        if not isinstance(self.origin, Origin) or not callable(self.before_dispatch):
            raise ContentError("invalid_call")


@dataclass(frozen=True)
class Chapter:
    chapter_id: str
    text: str
    title: str = ""

    def __post_init__(self) -> None:
        identifier(self.chapter_id)
        if not isinstance(self.text, str) or not isinstance(self.title, str):
            raise ContentError("invalid_manuscript")
        if len(self.title) > 200:
            raise ContentError("title_too_large")

    def value(self) -> dict[str, str]:
        return dict(chapter_id=self.chapter_id, text=self.text, title=self.title)


def manuscript(chapters: tuple[Chapter, ...]) -> str:
    if (not isinstance(chapters, tuple) or not 1 <= len(chapters) <= MAX_CHAPTERS
            or not all(isinstance(item, Chapter) for item in chapters)):
        raise ContentError("invalid_manuscript")
    if len({item.chapter_id for item in chapters}) != len(chapters):
        raise ContentError("duplicate_chapter")
    encoded = canonical([item.value() for item in chapters])
    if len(encoded.encode("utf-8")) > MAX_MANUSCRIPT_BYTES:
        raise ContentError("manuscript_too_large")
    return encoded


def source_union(*groups: tuple[JsonObject, ...]) -> tuple[JsonObject, ...]:
    combined: dict[str, JsonObject] = {}
    for group in groups:
        if not isinstance(group, tuple):
            raise ContentError("invalid_sources")
        for source in group:
            if not isinstance(source, JsonObject):
                raise ContentError("invalid_sources")
            value = source.value()
            required = {"source_id", "owner", "scope", "version"}
            optional = {"issued_at", "expires_at", "content_hash"}
            if (not required.issubset(value) or set(value) - required - optional
                    or not isinstance(value["scope"], dict)
                    or not value["scope"] or not isinstance(value["version"], dict)
                    or set(value["version"]) != {"lineage_id", "revision"}):
                raise ContentError("invalid_source_reference")
            identifier(value["source_id"])
            identifier(value["owner"])
            identifier(value["version"]["lineage_id"])
            integer(value["version"]["revision"], 1)
            combined[source.encoded] = source
    if len(combined) > MAX_SOURCES:
        raise ContentError("too_many_sources")
    return tuple(combined[key] for key in sorted(combined))


Action = Literal["create", "save_candidate", "adopt", "retract", "read",
                 "list", "lookup"]


@dataclass(frozen=True)
class AccessRequest:
    action: Action
    owner: WorkOwner
    origin: Origin
    work_id: str | None = None
    stored_audience: JsonObject | None = None
    sources: tuple[JsonObject, ...] = ()
    contributor: JsonObject | None = None


class AccessPort(Protocol):
    def check(self, request: AccessRequest) -> None:
        """Raise on denial; use current host authorization/source governance.

        This is a synchronous local check, never a network/model call. The host
        must resolve owner/actor/role/audience and verify source version, purpose
        and audience. Content does not interpret user tiers or UMO strings.
        """


@dataclass(frozen=True)
class WorkSummary:
    work_id: str
    title: str
    work_type: str
    revision: int
    head_version: str
    state: str
    author: JsonObject
    audience: JsonObject


@dataclass(frozen=True)
class Catalogue:
    items: tuple[WorkSummary, ...]
    next_after: str | None


@dataclass(frozen=True)
class Segment:
    chapter_id: str
    chapter_offset: int
    start: int
    end: int
    text: str
    chapter_title: str = ""


@dataclass(frozen=True)
class VersionPage:
    work_id: str
    version_id: str
    content_hash: str
    base_revision: int
    base_version: str | None
    contributor: JsonObject
    origin: JsonObject
    sources: tuple[JsonObject, ...]
    offset: int
    end_offset: int
    total_chars: int
    next_offset: int | None
    segments: tuple[Segment, ...]


@dataclass(frozen=True)
class Receipt:
    operation_id: str
    operation_key: str
    action: Action
    work_id: str
    version_id: str | None
    previous_revision: int
    revision: int
    previous_version: str | None
    origin: JsonObject
    version_origin: JsonObject | None
    sources: tuple[JsonObject, ...]
    recorded_at: str
    effect: str = "committed"

    def value(self) -> dict[str, Any]:
        return dict(operation_id=self.operation_id, operation_key=self.operation_key,
                    action=self.action, work_id=self.work_id, version_id=self.version_id,
                    previous_revision=self.previous_revision, revision=self.revision,
                    previous_version=self.previous_version, origin=self.origin.value(),
                    version_origin=self.version_origin.value() if self.version_origin else None,
                    sources=[source.value() for source in self.sources],
                    recorded_at=self.recorded_at, effect=self.effect)

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> Receipt:
        return cls(**{**value, "origin": JsonObject.capture(value["origin"]),
                      "version_origin": JsonObject.capture(value["version_origin"])
                      if value["version_origin"] else None,
                      "sources": tuple(JsonObject.capture(item) for item in value["sources"])})
