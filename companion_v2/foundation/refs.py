"""Immutable, scoped references shared by V2 domains."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json


class ReferenceValidationError(ValueError):
    """Raised when an opaque reference is incomplete or crosses a hard boundary."""


class ScopeKind(str, Enum):
    PRIVATE = "private"
    GROUP = "group"
    THREAD = "thread"
    DEVICE = "device"
    SYSTEM = "system"


class SubjectKind(str, Enum):
    HUMAN = "human"
    BOT = "bot"
    SERVICE = "service"
    GROUP = "group"


def normalize_utc(value: datetime, *, field: str) -> datetime:
    """Normalize an aware timestamp while rejecting naive local-time values."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ReferenceValidationError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    if len(value) > 512:
        raise ReferenceValidationError(f"{field} exceeds 512 characters")
    return value


def _positive(value: int, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReferenceValidationError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class ScopeRef:
    """A host-independent conversation, device, or system scope."""

    installation_id: str
    platform: str
    kind: ScopeKind
    native_scope_id: str
    bot_id: str | None = None
    account_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.installation_id, field="installation_id")
        _opaque(self.platform, field="platform")
        _opaque(self.native_scope_id, field="native_scope_id")
        if not isinstance(self.kind, ScopeKind):
            raise ReferenceValidationError("scope kind must be explicit")
        for name in ("bot_id", "account_id", "conversation_id", "session_id"):
            value = getattr(self, name)
            if value is not None:
                _opaque(value, field=name)
        routing = (self.bot_id, self.account_id, self.conversation_id, self.session_id)
        if self.kind in (ScopeKind.PRIVATE, ScopeKind.GROUP, ScopeKind.THREAD) and any(routing) and not all(routing):
            raise ReferenceValidationError("conversation scope requires bot, account, conversation and session together")

    @property
    def is_resolved(self) -> bool:
        return all((self.bot_id, self.account_id, self.conversation_id, self.session_id))

    def document(self) -> dict:
        """Preserve the v1 shape for unresolved historical references."""
        result = {"installation_id": self.installation_id, "platform": self.platform,
                  "kind": self.kind.value, "native_scope_id": self.native_scope_id}
        for name in ("bot_id", "account_id", "conversation_id", "session_id"):
            if getattr(self, name) is not None:
                result[name] = getattr(self, name)
        return result

    @classmethod
    def restore(cls, value: dict) -> ScopeRef:
        return cls(**{**value, "kind": ScopeKind(value["kind"])})

    @property
    def key(self) -> str:
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RoleOwnerRef:
    """Stable role ownership, independent of account, window, session and binding revision."""

    installation_id: str
    bot_id: str
    persona_id: str

    def __post_init__(self) -> None:
        for name in ("installation_id", "bot_id", "persona_id"):
            _opaque(getattr(self, name), field=name)


@dataclass(frozen=True)
class SubjectRef:
    """A stable subject distinct from a native platform account or display name."""

    installation_id: str
    kind: SubjectKind
    subject_id: str

    def __post_init__(self) -> None:
        _opaque(self.installation_id, field="installation_id")
        _opaque(self.subject_id, field="subject_id")


@dataclass(frozen=True)
class AudienceRef:
    """The explicitly allowed recipients in one exact scope."""

    scope: ScopeRef
    recipients: tuple[SubjectRef, ...]

    def __post_init__(self) -> None:
        if not self.recipients:
            raise ReferenceValidationError("audience must include at least one recipient")
        seen: set[SubjectRef] = set()
        for recipient in self.recipients:
            if recipient.installation_id != self.scope.installation_id:
                raise ReferenceValidationError("audience recipient crosses installation")
            if recipient in seen:
                raise ReferenceValidationError("audience recipients must be unique")
            seen.add(recipient)


@dataclass(frozen=True)
class VersionRef:
    """A monotonic version of a source, asset, record, or operation lineage."""

    lineage_id: str
    revision: int

    def __post_init__(self) -> None:
        _opaque(self.lineage_id, field="lineage_id")
        _positive(self.revision, field="revision")


def _validate_owned_scope(owner: str, scope: ScopeRef, version: VersionRef) -> None:
    _opaque(owner, field="owner")
    if not isinstance(scope, ScopeRef):
        raise ReferenceValidationError("scope must be a ScopeRef")
    if not isinstance(version, VersionRef):
        raise ReferenceValidationError("version must be a VersionRef")


@dataclass(frozen=True)
class SourceRef:
    """A versioned factual source with a scope and optional expiry boundary."""

    source_id: str
    owner: str
    scope: ScopeRef
    version: VersionRef
    issued_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _opaque(self.source_id, field="source_id")
        _validate_owned_scope(self.owner, self.scope, self.version)
        issued_at = normalize_utc(self.issued_at, field="issued_at")
        object.__setattr__(self, "issued_at", issued_at)
        if self.expires_at is not None:
            expires_at = normalize_utc(self.expires_at, field="expires_at")
            if expires_at <= issued_at:
                raise ReferenceValidationError("expires_at must be after issued_at")
            object.__setattr__(self, "expires_at", expires_at)

    def is_expired_at(self, observed_at: datetime) -> bool:
        return self.expires_at is not None and normalize_utc(
            observed_at, field="observed_at"
        ) >= self.expires_at


@dataclass(frozen=True)
class AssetRef:
    """A versioned asset reference; it exposes no filesystem path."""

    asset_id: str
    owner: str
    scope: ScopeRef
    version: VersionRef
    content_hash: str

    def __post_init__(self) -> None:
        _opaque(self.asset_id, field="asset_id")
        _validate_owned_scope(self.owner, self.scope, self.version)
        _opaque(self.content_hash, field="content_hash")


@dataclass(frozen=True)
class OperationRef:
    """A scoped operation identity and its stable idempotency key."""

    operation_id: str
    owner: str
    scope: ScopeRef
    version: VersionRef
    idempotency_key: str

    def __post_init__(self) -> None:
        _opaque(self.operation_id, field="operation_id")
        _validate_owned_scope(self.owner, self.scope, self.version)
        _opaque(self.idempotency_key, field="idempotency_key")


@dataclass(frozen=True)
class TaskRef:
    """A versioned task belonging to a single owner and exact scope."""

    task_id: str
    owner: str
    scope: ScopeRef
    version: VersionRef

    def __post_init__(self) -> None:
        _opaque(self.task_id, field="task_id")
        _validate_owned_scope(self.owner, self.scope, self.version)


@dataclass(frozen=True)
class AttemptRef:
    """One delivery or tool attempt for a stable local operation."""

    attempt_id: str
    operation: OperationRef
    ordinal: int

    def __post_init__(self) -> None:
        _opaque(self.attempt_id, field="attempt_id")
        if not isinstance(self.operation, OperationRef):
            raise ReferenceValidationError("operation must be an OperationRef")
        _positive(self.ordinal, field="ordinal")


@dataclass(frozen=True)
class PartRef:
    """An immutable, ordered part of an operation's delivery manifest."""

    part_id: str
    operation: OperationRef
    sequence: int

    def __post_init__(self) -> None:
        _opaque(self.part_id, field="part_id")
        if not isinstance(self.operation, OperationRef):
            raise ReferenceValidationError("operation must be an OperationRef")
        _positive(self.sequence, field="sequence")
