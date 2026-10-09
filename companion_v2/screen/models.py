"""Screen originals and interpretations, with explicit observed coverage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import (
    AssetRef, ReferenceValidationError, SourceRef, SubjectRef, VersionRef, normalize_utc,
)
from companion_v2.sources.models import AssetRecord, SourceRecord


SCREEN_EXTENSION = "companion.screen.native"
SCREEN_OWNER = "screen"
SCREEN_READ = "screen.read"
SCREEN_PROCESS = "screen.process"


class ScreenMediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class ClockQuality(str, Enum):
    VERIFIED = "verified"
    CLIENT_REPORTED = "client_reported"


class ScreenFeedbackKind(str, Enum):
    ATTENTION = "attention"
    REPLY = "reply"
    PROACTIVE = "proactive"
    JOURNAL = "journal"
    SILENCE = "silence"


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceValidationError(f"{field} must be non-blank text")


def validate_units(units: tuple[str, ...]) -> None:
    if not isinstance(units, tuple) or not units or len(set(units)) != len(units):
        raise ReferenceValidationError("coverage units must be a non-empty unique tuple")
    for unit in units:
        _text(unit, "coverage unit")


@dataclass(frozen=True)
class ScreenCoverage:
    """Units name exact adapter-supplied pieces, never implied unseen coverage."""

    surface: str
    units: tuple[str, ...]
    gaps: tuple[str, ...] = ()
    clock_quality: ClockQuality = ClockQuality.CLIENT_REPORTED

    def __post_init__(self) -> None:
        _text(self.surface, "surface")
        validate_units(self.units)
        if not isinstance(self.gaps, tuple):
            raise ReferenceValidationError("coverage gaps must be an immutable tuple")
        for gap in self.gaps:
            _text(gap, "gap")
        if not isinstance(self.clock_quality, ClockQuality):
            raise ReferenceValidationError("clock_quality must be explicit")


@dataclass(frozen=True)
class ScreenCaptureRef:
    capture_id: str
    source: SourceRef
    asset: AssetRef

    def __post_init__(self) -> None:
        _text(self.capture_id, "capture_id")
        if self.source.owner != SCREEN_OWNER or self.asset.owner != SCREEN_OWNER:
            raise ReferenceValidationError("Screen cannot adopt another domain's originals")
        if self.source.scope != self.asset.scope:
            raise ReferenceValidationError("screen source and asset must share the exact scope")


@dataclass(frozen=True)
class ScreenCapture:
    reference: ScreenCaptureRef
    device_id: str
    media_kind: ScreenMediaKind
    coverage: ScreenCoverage
    captured_at: datetime
    received_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        _text(self.device_id, "device_id")
        if not isinstance(self.media_kind, ScreenMediaKind):
            raise ReferenceValidationError("media_kind must be explicit")
        for field in ("captured_at", "received_at", "created_at"):
            object.__setattr__(self, field, normalize_utc(getattr(self, field), field=field))
        if self.received_at > self.created_at:
            raise ReferenceValidationError("a capture cannot be registered before receipt")
        if self.coverage.clock_quality is ClockQuality.VERIFIED and self.captured_at > self.received_at:
            raise ReferenceValidationError("verified capture time cannot be after receipt")


@dataclass(frozen=True)
class ScreenMaterial:
    capture: ScreenCapture
    source: SourceRecord
    asset: AssetRecord


@dataclass(frozen=True)
class ScreenAnalysis:
    analysis_id: str
    version: VersionRef
    capture: ScreenCaptureRef
    processor_id: str
    purpose: str
    input_units: tuple[str, ...]
    interpretation: str
    created_at: datetime

    def __post_init__(self) -> None:
        for field in ("analysis_id", "processor_id", "purpose", "interpretation"):
            _text(getattr(self, field), field)
        validate_units(self.input_units)
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))


@dataclass(frozen=True)
class ScreenFeedbackAnchor:
    """An intent for a shared owner; it is never a delivery or memory receipt."""

    feedback_id: str
    capture: ScreenCaptureRef
    kind: ScreenFeedbackKind
    created_at: datetime
    analysis_id: str | None = None
    analysis_version: VersionRef | None = None

    def __post_init__(self) -> None:
        _text(self.feedback_id, "feedback_id")
        if not isinstance(self.kind, ScreenFeedbackKind):
            raise ReferenceValidationError("feedback kind must be explicit")
        if (self.analysis_id is None) != (self.analysis_version is None):
            raise ReferenceValidationError("analysis id and version must be supplied together")
        if self.analysis_id is not None:
            _text(self.analysis_id, "analysis_id")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at, field="created_at"))


@dataclass(frozen=True)
class ScreenFeedbackMaterial:
    anchor: ScreenFeedbackAnchor
    material: ScreenMaterial
    analysis: ScreenAnalysis | None


@dataclass(frozen=True)
class ScreenProcessingRequest:
    material: ScreenMaterial
    role: SubjectRef
    role_instruction: str
    purpose: str
    input_units: tuple[str, ...]
    instruction: str


@dataclass(frozen=True)
class ScreenInterpretation:
    interpretation: str
    input_units: tuple[str, ...]
    feedback_kind: ScreenFeedbackKind

    def __post_init__(self) -> None:
        _text(self.interpretation, "interpretation")
        validate_units(self.input_units)
        if not isinstance(self.feedback_kind, ScreenFeedbackKind):
            raise ReferenceValidationError("feedback kind must be explicit")
