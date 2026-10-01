"""Value objects for package lifecycle, user choices, and furniture projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math

from companion_v2.foundation.refs import ReferenceValidationError, ScopeRef, SubjectKind, SubjectRef, normalize_utc


class CapabilityDesiredState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISCARD_REQUESTED = "discard_requested"
    DISCARDED = "discarded"


class CapabilityAuthorizationState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class FurnitureAvailability(str, Enum):
    ACQUIRED = "acquired"
    PAUSED = "paused"
    REMOVING = "removing"


def _opaque(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    if len(value) > 512:
        raise ReferenceValidationError(f"{field} exceeds 512 characters")


def _positive(value: int, *, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReferenceValidationError(f"{field} must be a positive integer")


@dataclass(frozen=True)
class FurnitureDescriptor:
    """A stable room object definition; the panel identifier is registry-owned."""

    furniture_id: str
    extension_id: str
    display_name: str
    panel_id: str
    styles: tuple[str, ...] = ("default",)
    default_style: str = "default"

    def __post_init__(self) -> None:
        _opaque(self.furniture_id, field="furniture_id")
        _opaque(self.extension_id, field="extension_id")
        _opaque(self.display_name, field="display_name")
        _opaque(self.panel_id, field="panel_id")
        if not self.styles or len(set(self.styles)) != len(self.styles):
            raise ReferenceValidationError("furniture styles must be non-empty and unique")
        for style in self.styles:
            _opaque(style, field="furniture_style")
        _opaque(self.default_style, field="default_style")
        if self.default_style not in self.styles:
            raise ReferenceValidationError("default_style must be one of styles")


@dataclass(frozen=True)
class CapabilityPackageDescriptor:
    """A fixed, publisher-identified package version from a trusted catalog."""

    extension_id: str
    package_id: str
    publisher_id: str
    package_version: str
    artifact_hash: str
    capabilities: tuple[str, ...]
    dataset_owners: tuple[str, ...] = ()
    furniture: tuple[FurnitureDescriptor, ...] = ()

    def __post_init__(self) -> None:
        for value, field in (
            (self.extension_id, "extension_id"),
            (self.package_id, "package_id"),
            (self.publisher_id, "publisher_id"),
            (self.package_version, "package_version"),
            (self.artifact_hash, "artifact_hash"),
        ):
            _opaque(value, field=field)
        if not self.capabilities:
            raise ReferenceValidationError("a capability package must provide at least one capability")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ReferenceValidationError("package capabilities must be unique")
        for capability in self.capabilities:
            _opaque(capability, field="capability_id")
        if len(set(self.dataset_owners)) != len(self.dataset_owners):
            raise ReferenceValidationError("dataset owners must be unique")
        for owner in self.dataset_owners:
            _opaque(owner, field="dataset_owner")
        furniture_ids: set[str] = set()
        for item in self.furniture:
            if item.extension_id != self.extension_id:
                raise ReferenceValidationError("furniture belongs to another extension")
            if item.furniture_id in furniture_ids:
                raise ReferenceValidationError("furniture ids must be unique in a package")
            furniture_ids.add(item.furniture_id)


@dataclass(frozen=True)
class CapabilityInstallation:
    """Pinned local catalog choice; this is not evidence of host loading or readiness."""

    extension_id: str
    package_id: str
    package_version: str
    artifact_hash: str
    desired_state: CapabilityDesiredState
    revision: int
    retained_dataset_owners: tuple[str, ...]
    acquired_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.extension_id, field="extension_id")
        _opaque(self.package_id, field="package_id")
        _opaque(self.package_version, field="package_version")
        _opaque(self.artifact_hash, field="artifact_hash")
        _positive(self.revision, field="capability_revision")
        if not isinstance(self.desired_state, CapabilityDesiredState):
            raise ReferenceValidationError("desired_state must be a CapabilityDesiredState")
        if len(set(self.retained_dataset_owners)) != len(self.retained_dataset_owners):
            raise ReferenceValidationError("retained dataset owners must be unique")
        for owner in self.retained_dataset_owners:
            _opaque(owner, field="retained_dataset_owner")
        object.__setattr__(self, "acquired_at", normalize_utc(self.acquired_at, field="acquired_at"))
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class CapabilityRoleSelection:
    extension_id: str
    role: SubjectRef
    enabled: bool
    revision: int
    updated_at: datetime
    bot_id: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.extension_id, field="extension_id")
        if self.role.kind is not SubjectKind.BOT:
            raise ReferenceValidationError("capability role selection must target a bot role")
        if not isinstance(self.enabled, bool):
            raise ReferenceValidationError("enabled must be boolean")
        _positive(self.revision, field="role_selection_revision")
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class CapabilityAuthorization:
    """Extension-level consent; it never replaces identity policy authorization."""

    extension_id: str
    capability_id: str
    subject: SubjectRef
    scope: ScopeRef
    state: CapabilityAuthorizationState
    revision: int
    updated_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.extension_id, field="extension_id")
        _opaque(self.capability_id, field="capability_id")
        if not isinstance(self.state, CapabilityAuthorizationState):
            raise ReferenceValidationError("state must be a CapabilityAuthorizationState")
        if self.subject.installation_id != self.scope.installation_id:
            raise ReferenceValidationError("capability authorization crosses installation")
        _positive(self.revision, field="capability_authorization_revision")
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class CapabilitySettings:
    """Per-scope preference; weight is consumed only by multi-thought competition."""

    extension_id: str
    scope: ScopeRef
    proactive_enabled: bool
    thought_weight: float
    revision: int
    updated_at: datetime

    def __post_init__(self) -> None:
        _opaque(self.extension_id, field="extension_id")
        if not isinstance(self.proactive_enabled, bool):
            raise ReferenceValidationError("proactive_enabled must be boolean")
        if isinstance(self.thought_weight, bool) or not math.isfinite(self.thought_weight) or self.thought_weight <= 0:
            raise ReferenceValidationError("thought_weight must be a positive finite number")
        _positive(self.revision, field="capability_settings_revision")
        object.__setattr__(self, "updated_at", normalize_utc(self.updated_at, field="updated_at"))


@dataclass(frozen=True)
class FurnitureProjection:
    furniture: FurnitureDescriptor
    availability: FurnitureAvailability
    installed_revision: int


@dataclass(frozen=True)
class CapabilityProjection:
    """The management page and room use this one projection, never parallel state."""

    installation: CapabilityInstallation
    furniture: tuple[FurnitureProjection, ...]
    role_selection: CapabilityRoleSelection | None
    settings: CapabilitySettings | None
