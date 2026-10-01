"""Immutable configuration addresses and snapshots, independent of a page or host."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from companion_v2.foundation.refs import ReferenceValidationError, ScopeKind, ScopeRef, SubjectKind, SubjectRef


Scalar = bool | int | float | str


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


class ConfigurationError(ValueError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code


class ConfigLayer(str, Enum):
    INSTALLATION = "installation"
    ROLE = "role"
    RELATIONSHIP = "relationship"
    WINDOW = "window"
    SCOPE = "scope"


class ApplyMode(str, Enum):
    IMMEDIATE = "immediate"
    NEXT_TASK = "next_task"
    RESTART = "restart"


@dataclass(frozen=True)
class ConfigTarget:
    installation_id: str
    layer: ConfigLayer
    role: SubjectRef | None = None
    scope: ScopeRef | None = None
    bot_id: str | None = None
    subject: SubjectRef | None = None

    def __post_init__(self) -> None:
        if self.bot_id is not None and (not self.bot_id or self.bot_id != self.bot_id.strip()):
            raise ReferenceValidationError("configuration bot must be an explicit identifier")
        if self.scope is not None and self.scope.bot_id is not None:
            if self.bot_id is not None and self.bot_id != self.scope.bot_id:
                raise ReferenceValidationError("configuration bot differs from its window")
            object.__setattr__(self, "bot_id", self.scope.bot_id)
        if not isinstance(self.layer, ConfigLayer):
            raise ReferenceValidationError("invalid configuration layer")
        if self.subject is not None:
            if (self.subject.installation_id != self.installation_id or self.subject.kind is not SubjectKind.HUMAN
                    or self.layer not in (ConfigLayer.RELATIONSHIP, ConfigLayer.WINDOW) or not self.bot_id):
                raise ReferenceValidationError("relationship preferences require a human, bot and role in one installation")
        if self.layer is ConfigLayer.RELATIONSHIP and self.subject is None:
            raise ReferenceValidationError("relationship target requires its human subject")
        if self.layer is ConfigLayer.INSTALLATION:
            if self.role is not None or self.scope is not None or self.bot_id is not None:
                raise ReferenceValidationError("installation target cannot contain a role or window")
        elif self.layer is ConfigLayer.SCOPE:
            if self.role is not None:
                raise ReferenceValidationError("scope preferences are not role-owned")
        else:
            if self.role is None or self.role.kind is not SubjectKind.BOT:
                raise ReferenceValidationError("configuration role must be a bot")
            if self.role.installation_id != self.installation_id:
                raise ReferenceValidationError("configuration role crosses installation")
        if self.layer in (ConfigLayer.WINDOW, ConfigLayer.SCOPE):
            if self.scope is None or self.scope.installation_id != self.installation_id:
                raise ReferenceValidationError("window target requires its installation scope")
        elif self.scope is not None:
            raise ReferenceValidationError("only window targets have a scope")
        self.authorization_scope

    def document(self) -> dict:
        result = {
            "installation_id": self.installation_id, "layer": self.layer.value,
            "role_id": self.role.subject_id if self.role else None,
            "scope": [self.scope.platform, self.scope.kind.value, self.scope.native_scope_id] if self.scope else None,
        }
        if self.bot_id is not None:
            result["bot_id"] = self.bot_id
        if self.scope is not None and self.scope.is_resolved:
            result["scope"] = self.scope.document()
        if self.subject is not None:
            result["subject_id"] = self.subject.subject_id
        return result

    @property
    def key(self) -> str:
        return fingerprint(self.document())

    @property
    def authorization_scope(self) -> ScopeRef:
        if self.scope is not None:
            return self.scope
        native_id = "configuration.installation" if self.role is None else "configuration.role." + fingerprint(self.role.subject_id)
        if self.layer is ConfigLayer.RELATIONSHIP:
            native_id = "configuration.relationship." + self.key
        return ScopeRef(self.installation_id, "companion", ScopeKind.SYSTEM, native_id, bot_id=self.bot_id)

    def chain(self) -> tuple[ConfigTarget, ...]:
        if self.layer is ConfigLayer.SCOPE:
            return (self,)
        result = [ConfigTarget(self.installation_id, ConfigLayer.INSTALLATION)]
        if self.role is not None:
            result.append(ConfigTarget(self.installation_id, ConfigLayer.ROLE, self.role, bot_id=self.bot_id))
        if self.subject is not None:
            result.append(ConfigTarget(self.installation_id, ConfigLayer.RELATIONSHIP, self.role,
                                      bot_id=self.bot_id, subject=self.subject))
        if self.scope is not None:
            result.append(self)
        return tuple(result)


@dataclass(frozen=True)
class EffectiveValue:
    value: Scalar
    source: ConfigTarget | None
    explicit: bool
    source_revision: int = 0


@dataclass(frozen=True)
class ConfigurationSnapshot:
    target: ConfigTarget
    group_id: str
    schema_version: str
    revision: int
    change_sequence: int
    edit_token: str
    resolution_token: str
    fields: Mapping[str, EffectiveValue]
    consumer_id: str
    apply_mode: ApplyMode

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    @property
    def values(self) -> dict[str, Scalar]:
        return {key: item.value for key, item in self.fields.items()}


@dataclass(frozen=True)
class ConfigurationReceipt:
    operation_id: str
    target_key: str
    revision: int
    changed_fields: tuple[str, ...]
    replayed: bool


@dataclass(frozen=True)
class ConfigurationPreview:
    """A read-only explicit-value patch including owner-implied field changes."""

    snapshot: ConfigurationSnapshot
    changes: Mapping[str, Scalar]
    after: Mapping[str, EffectiveValue]
    supports_reset: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes", MappingProxyType(dict(self.changes)))
        object.__setattr__(self, "after", MappingProxyType(dict(self.after)))


@dataclass(frozen=True)
class ConfigurationChanges:
    """Authorized invalidation positions, never another scope's values or operations."""

    target: ConfigTarget
    group_id: str
    sequences: tuple[int, ...]
    next_cursor: int
    has_more: bool


@dataclass(frozen=True)
class ApplicationStatus:
    state: str
    consumer_id: str
    generation: int | None
    adopted_values: Mapping[str, Scalar]

    def __post_init__(self) -> None:
        object.__setattr__(self, "adopted_values", MappingProxyType(dict(self.adopted_values)))
