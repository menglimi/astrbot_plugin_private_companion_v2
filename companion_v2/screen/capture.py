"""One requested Screen capture through an injected device port."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
from typing import Callable, Protocol

from companion_v2.foundation.outcome import Failure, Outcome
from companion_v2.foundation.refs import (
    AssetRef, AudienceRef, OperationRef, ReferenceValidationError, ScopeRef,
    SourceRef, SubjectRef, VersionRef, normalize_utc,
)
from companion_v2.identity_policy.models import ResolvedIdentity
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .models import ClockQuality, SCREEN_OWNER, ScreenCapture, ScreenCaptureRef, ScreenCoverage, ScreenMediaKind
from .originals import ScreenImage
from .repositories import ScreenRepository


CAPTURE_TTL = timedelta(minutes=30)


class _AdmissionFailure(Exception):
    def __init__(self, failure: Failure) -> None:
        self.failure = failure


@dataclass(frozen=True)
class DeviceSnapshot:
    device_id: str
    surface: str
    captured_at: datetime
    clock_quality: ClockQuality
    image: ScreenImage = field(repr=False)
    window_title: str | None = None
    gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.device_id, self.surface):
            if not isinstance(value, str) or not value.strip():
                raise ReferenceValidationError("device and surface must be identified")
        if not isinstance(self.image, ScreenImage) or not isinstance(self.clock_quality, ClockQuality):
            raise ReferenceValidationError("snapshot requires a verified image and clock quality")
        object.__setattr__(self, "captured_at", normalize_utc(self.captured_at, field="captured_at"))


class ScreenDevicePort(Protocol):
    async def capture(self, device_id: str, *, before_dispatch: Callable[[], None]) -> DeviceSnapshot:
        """Capture one selected device; call before_dispatch immediately before device I/O."""


@dataclass(frozen=True)
class ScreenCaptureReceipt:
    operation: OperationRef
    capture: ScreenCapture
    replayed: bool


class ScreenCaptureService:
    def __init__(self, *, screens: ScreenRepository, operations: OperationRepository,
                 device: ScreenDevicePort, now: Callable[[], datetime]) -> None:
        self.screens, self.operations, self.device, self.now = screens, operations, device, now

    async def capture_once(
        self, *, request_id: str, scope: ScopeRef, device_id: str, role: SubjectRef,
        resolved: ResolvedIdentity, audience: AudienceRef,
    ) -> Outcome[ScreenCaptureReceipt]:
        if (not isinstance(request_id, str) or not request_id.strip()
                or not isinstance(device_id, str) or not device_id.strip()
                or audience.scope != scope or resolved.subject not in audience.recipients):
            raise ReferenceValidationError("Screen capture requires an exact request, device and audience")
        token = hashlib.sha256(json.dumps({"request_id": request_id, "scope": scope.document()},
            sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        operation = OperationRef(f"screen-capture-{token}", "screen.capture", scope,
                                 VersionRef(f"screen-capture-{token}", 1), f"screen-capture-{token}")
        capture_id = f"screen-capture-{token}"
        parameter_hash = hashlib.sha256(json.dumps({
            "device_id": device_id, "role": asdict(role), "subject": asdict(resolved.subject),
            "principal": asdict(resolved.principal), "binding_id": resolved.binding_id,
            "binding_revision": resolved.binding_revision,
            "audience": [asdict(item) for item in audience.recipients],
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        observed_at = normalize_utc(self.now(), field="observed_at")
        placeholder = ScreenCaptureRef(capture_id,
            SourceRef(f"screen-source-{token}", SCREEN_OWNER, scope, VersionRef(f"screen-source-{token}", 1),
                      observed_at, observed_at + CAPTURE_TTL),
            AssetRef(f"screen-asset-{token}", SCREEN_OWNER, scope, VersionRef(f"screen-asset-{token}", 1), "pending"))
        initial = self.screens.admit_capture(placeholder, role=role, resolved=resolved, observed_at=observed_at)
        if not initial.is_success:
            return Outcome(failure=initial.failure)
        stamp = initial.unwrap()
        received = self.operations.reserve(operation, parameter_hash=parameter_hash, observed_at=observed_at)
        if not received.is_success:
            return Outcome(failure=received.failure)
        receipt = received.unwrap()
        if receipt.replayed:
            existing = self.screens.published_reference(capture_id, scope=scope)
            if not existing.is_success:
                return Outcome.failed("screen_capture_unresolved", "the original request has no confirmed capture")
            current = self.screens.read_image(existing.unwrap(), resolved=resolved, observed_at=self.now())
            if not current.is_success:
                return Outcome(failure=current.failure)
            captured = self.screens.read_capture(existing.unwrap(), resolved=resolved, observed_at=self.now())
            if not captured.is_success:
                return Outcome(failure=captured.failure)
            return self._complete(operation, captured.unwrap().capture, receipt.state, replayed=True)
        dispatch_checked = False

        def before_dispatch() -> None:
            nonlocal dispatch_checked
            checked = self.screens.admit_capture(placeholder, role=role, resolved=resolved, observed_at=self.now())
            if not checked.is_success:
                raise _AdmissionFailure(checked.failure)
            if checked.unwrap() != stamp:
                raise _AdmissionFailure(Failure("screen_admission_changed", "capture authority changed before device I/O"))
            dispatch_checked = True

        try:
            snapshot = await self.device.capture(device_id, before_dispatch=before_dispatch)
            if not dispatch_checked or not isinstance(snapshot, DeviceSnapshot) or snapshot.device_id != device_id:
                raise ReferenceValidationError("device response does not match the selected device")
            finished = normalize_utc(self.now(), field="received_at")
            if snapshot.clock_quality is ClockQuality.VERIFIED and snapshot.captured_at > finished:
                raise ReferenceValidationError("verified capture time is after device receipt")
            reference = ScreenCaptureRef(capture_id, placeholder.source,
                AssetRef(placeholder.asset.asset_id, SCREEN_OWNER, scope, placeholder.asset.version,
                         snapshot.image.content_hash))
            capture = ScreenCapture(reference, device_id, ScreenMediaKind.IMAGE,
                ScreenCoverage(snapshot.surface,
                               ("image.viewport", "window.title") if snapshot.window_title else ("image.viewport",),
                               snapshot.gaps, snapshot.clock_quality), snapshot.captured_at, finished, finished)
            saved = self.screens.publish_image(capture, snapshot.image, audience=audience,
                window_title=snapshot.window_title, role=role, resolved=resolved,
                observed_at=finished, expected_admission_stamp=stamp)
            if not saved.is_success:
                self._mark_unknown(operation)
                return Outcome(failure=saved.failure)
            return self._complete(operation, capture, OperationState.ACCEPTED, replayed=False)
        except _AdmissionFailure as error:
            return Outcome(failure=error.failure)
        except asyncio.CancelledError:
            self._mark_unknown(operation)
            raise
        except Exception:
            self._mark_unknown(operation)
            return Outcome.failed("screen_capture_unknown", "the original device request has no confirmed result")

    def _complete(self, operation: OperationRef, capture: ScreenCapture,
                  state: OperationState, *, replayed: bool) -> Outcome[ScreenCaptureReceipt]:
        if state is not OperationState.COMPLETED:
            completed = self.operations.transition(operation.operation_id, expected_state=state,
                                                   next_state=OperationState.COMPLETED, observed_at=self.now())
            if not completed.is_success:
                current = self.operations.get(operation.operation_id)
                if not current.is_success or current.unwrap().state is not OperationState.COMPLETED:
                    return Outcome(failure=completed.failure)
        return Outcome.success(ScreenCaptureReceipt(operation, capture, replayed))

    def _mark_unknown(self, operation: OperationRef) -> None:
        self.operations.transition(operation.operation_id, expected_state=OperationState.ACCEPTED,
                                   next_state=OperationState.UNKNOWN, observed_at=self.now())
