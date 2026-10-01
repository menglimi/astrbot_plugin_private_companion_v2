"""Value objects for role reference material.

A reference asset is a *registration*: it names an asset that some owner already
stores, records the SHA-256 that owner asserted, and declares what the material
may be used for. The bytes are never copied here, so the registrant stays the
single source and the same picture can serve several declared roles without
"this picture was used" silently granting all of them.

C2-1 requires the digest to be checked when the material is *used*, not only when
it is registered: a file that changed after registration must be refused rather
than quietly influencing a generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import ReferenceValidationError, normalize_utc


class ReferenceKind(str, Enum):
    """What the material is for. Wardrobe items share the asset table."""

    REFERENCE_IMAGE = "reference_image"
    WARDROBE_ITEM = "wardrobe_item"


class ReferenceRole(str, Enum):
    """The V1 use vocabulary, kept verbatim so a planner matches a slot by name."""

    IDENTITY = "identity"
    OUTFIT = "outfit"
    POSE = "pose"
    SCENE = "scene"
    STYLE = "style"
    BACKGROUND = "background"
    CONTINUITY = "continuity"
    EDIT_SOURCE = "edit_source"
    EDIT_MASK = "edit_mask"


class ReferenceSource(str, Enum):
    OPERATOR = "operator"
    PROVIDER = "provider"


class ReferenceState(str, Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


MAX_LABEL = 120
MAX_MEDIA_REF = 512
MAX_MIME = 120
MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_ROLE_REFERENCE_BYTES = 256 * 1024 * 1024
MAX_WARDROBE_NAME = 120
MAX_WARDROBE_DESCRIPTION = 2000
MAX_WARDROBE_TAGS = 16
MAX_TAG = 40

_SHA256 = re.compile(r"[0-9a-f]{64}")


def _opaque(value, *, field, maximum):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > maximum or "\x00" in value):
        raise ReferenceValidationError(f"{field} must be a bounded opaque token")
    return value


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


@dataclass(frozen=True)
class ContentDigest:
    """The SHA-256 a registrant asserted, checked again whenever it is used."""

    sha256: str

    def __post_init__(self):
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise ReferenceValidationError("content digest must be a lowercase SHA-256 hex string")

    def matches(self, payload: bytes) -> bool:
        """Compare against real bytes; the only honest way to trust a registration."""
        import hashlib
        if not isinstance(payload, bytes):
            raise ReferenceValidationError("content must be bytes")
        return hashlib.sha256(payload).hexdigest() == self.sha256


@dataclass(frozen=True)
class ReferenceAsset:
    asset_id: str
    kind: ReferenceKind
    role: ReferenceRole
    content_hash: ContentDigest
    size_bytes: int
    mime_type: str
    media_ref: str
    source: ReferenceSource
    state: ReferenceState = ReferenceState.ACTIVE
    label: str = ""
    revision: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        _opaque(self.asset_id, field="asset_id", maximum=128)
        if not isinstance(self.kind, ReferenceKind) or not isinstance(self.role, ReferenceRole):
            raise ReferenceValidationError("a reference asset requires its kind and role")
        if not isinstance(self.content_hash, ContentDigest):
            raise ReferenceValidationError("a reference asset requires its asserted digest")
        if (type(self.size_bytes) is not int or isinstance(self.size_bytes, bool)
                or not 0 < self.size_bytes <= MAX_ASSET_BYTES):
            raise ReferenceValidationError("asset size is outside its bounded range")
        _text(self.mime_type, field="mime_type", maximum=MAX_MIME)
        _opaque(self.media_ref, field="media_ref", maximum=MAX_MEDIA_REF)
        if not isinstance(self.source, ReferenceSource) or not isinstance(self.state, ReferenceState):
            raise ReferenceValidationError("a reference asset requires its source and state")
        _text(self.label, field="label", maximum=MAX_LABEL, required=False)
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("asset revision must be a positive integer")
        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_utc(value, field=name))

    def verify(self, payload: bytes) -> bool:
        return self.content_hash.matches(payload)

    @property
    def roles(self):
        """The primary declared role; extra roles are separate rows, never implied."""
        return (self.role,)


@dataclass(frozen=True)
class WardrobeItem:
    """An entry in the role's wardrobe; the picture, if any, is a reference asset."""

    item_id: str
    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    asset_id: str | None = None
    source: ReferenceSource = ReferenceSource.OPERATOR
    state: ReferenceState = ReferenceState.ACTIVE
    revision: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        _opaque(self.item_id, field="item_id", maximum=128)
        _text(self.name, field="name", maximum=MAX_WARDROBE_NAME)
        _text(self.description, field="description", maximum=MAX_WARDROBE_DESCRIPTION, required=False)
        if not isinstance(self.tags, tuple) or len(self.tags) > MAX_WARDROBE_TAGS:
            raise ReferenceValidationError("wardrobe tags must be a bounded tuple")
        for tag in self.tags:
            _text(tag, field="tag", maximum=MAX_TAG)
        if len(set(self.tags)) != len(self.tags):
            raise ReferenceValidationError("wardrobe tags must be unique")
        if self.asset_id is not None:
            _opaque(self.asset_id, field="asset_id", maximum=128)
        if not isinstance(self.source, ReferenceSource) or not isinstance(self.state, ReferenceState):
            raise ReferenceValidationError("a wardrobe item requires its source and state")
        if type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("item revision must be a positive integer")
        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_utc(value, field=name))
