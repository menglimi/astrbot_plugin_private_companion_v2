"""Screen originals retain real bytes behind current source and asset governance."""

from datetime import timedelta
import base64
import unittest

from companion_v2.foundation.refs import ReferenceValidationError

from companion_v2.capabilities import CapabilityAuthorizationState
from companion_v2.foundation.refs import AssetRef, AudienceRef, SourceRef, VersionRef
from companion_v2.screen import (
    SCREEN_EXTENSION, SCREEN_READ, ClockQuality, ScreenCapture, ScreenCaptureRef,
    ScreenCoverage, ScreenImage, ScreenMediaKind, ScreenOriginalStore, ScreenRepository,
)
from companion_v2.sources import SourceRepository

from tests.g6_support import G6Fixture, NOW


IMAGE = ScreenImage("image/png", base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
))


class ScreenOriginalTests(G6Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.enable_screen()
        self.screens = ScreenRepository(self.runtime, authorizer=self.identities)

    def capture(self, capture_id="capture-original", image=IMAGE):
        reference = ScreenCaptureRef(
            capture_id,
            SourceRef(f"source-{capture_id}", "screen", self.scope,
                      VersionRef(f"source-lineage-{capture_id}", 1), NOW - timedelta(seconds=1),
                      NOW + timedelta(hours=1)),
            AssetRef(f"asset-{capture_id}", "screen", self.scope,
                     VersionRef(f"asset-lineage-{capture_id}", 1), image.content_hash),
        )
        return ScreenCapture(
            reference, "desktop-a", ScreenMediaKind.IMAGE,
            ScreenCoverage("desktop", ("image.viewport", "window.title"),
                           ("other displays not captured",), ClockQuality.CLIENT_REPORTED),
            NOW - timedelta(seconds=5), NOW - timedelta(seconds=1), NOW,
        )

    def publish(self, capture, *, title="Editor", stamp=None):
        if stamp is None:
            stamp = self.screens.admit_capture(
                capture.reference, role=self.role, resolved=self.resolved, observed_at=NOW,
            ).unwrap()
        return self.screens.publish_image(
            capture, IMAGE, audience=AudienceRef(self.scope, (self.subject,)),
            window_title=title, role=self.role, resolved=self.resolved,
            observed_at=NOW, expected_admission_stamp=stamp,
        )

    def test_publish_read_restart_and_idempotent_replay(self) -> None:
        capture = self.capture()
        self.publish(capture).unwrap()
        self.publish(capture).unwrap()
        self.assertEqual(self.screens.read_image(capture.reference, resolved=self.resolved,
                                                 observed_at=NOW).unwrap(), IMAGE)
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM screen_captures", ())["n"], 1)
        snapshot = self.identities.snapshot()
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.identities = type(self.identities).from_snapshot(snapshot)
        self.screens = ScreenRepository(self.runtime, authorizer=self.identities)
        self.assertEqual(self.screens.read_image(capture.reference, resolved=self.resolved,
                                                 observed_at=NOW).unwrap(), IMAGE)

    def test_retained_review_survives_evidence_expiry_but_respects_revocation(self):
        capture = self.capture()
        self.publish(capture).unwrap()
        later = NOW + timedelta(hours=2)
        self.assertEqual(self.screens.read_image(capture.reference, resolved=self.resolved,
            observed_at=later).failure.code, "source_expired")
        self.assertEqual(self.screens.read_retained_image(capture.reference, resolved=self.resolved,
            observed_at=later).unwrap(), IMAGE)
        SourceRepository(self.runtime).revoke(capture.reference.source,
            expected_governance_revision=1, observed_at=later).unwrap()
        self.assertEqual(self.screens.read_retained_image(capture.reference, resolved=self.resolved,
            observed_at=later).failure.code, "source_revoked")

    def test_revocation_and_missing_or_changed_bytes_are_not_readable(self) -> None:
        capture = self.capture()
        self.publish(capture).unwrap()
        store = ScreenOriginalStore(self.runtime.data_root)
        path = store._path(IMAGE.content_hash)
        path.write_bytes(b"changed")
        self.assertEqual(self.screens.read_image(capture.reference, resolved=self.resolved,
                                                observed_at=NOW).failure.code, "screen_original_unavailable")
        path.write_bytes(IMAGE.content)
        SourceRepository(self.runtime).revoke(capture.reference.source,
            expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.screens.read_image(capture.reference, resolved=self.resolved,
                                                observed_at=NOW).failure.code, "source_revoked")

    def test_mid_capture_authorization_change_blocks_publication(self) -> None:
        capture = self.capture()
        stamp = self.screens.admit_capture(capture.reference, role=self.role,
                                          resolved=self.resolved, observed_at=NOW).unwrap()
        self.capabilities.set_authorization(extension_id=SCREEN_EXTENSION,
            capability_id=SCREEN_READ, subject=self.subject, scope=self.scope,
            state=CapabilityAuthorizationState.REVOKED, expected_revision=1,
            observed_at=NOW).unwrap()
        self.capabilities.set_authorization(extension_id=SCREEN_EXTENSION,
            capability_id=SCREEN_READ, subject=self.subject, scope=self.scope,
            state=CapabilityAuthorizationState.ACTIVE, expected_revision=2,
            observed_at=NOW).unwrap()
        self.assertEqual(self.publish(capture, stamp=stamp).failure.code, "screen_admission_changed")
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM sources", ())["n"], 0)

    def test_conflicting_sample_rolls_back_new_source_and_asset(self) -> None:
        original = self.capture()
        self.publish(original).unwrap()
        collision = self.capture("another-capture")
        collision = ScreenCapture(
            ScreenCaptureRef(original.reference.capture_id, collision.reference.source, collision.reference.asset),
            collision.device_id, collision.media_kind, collision.coverage,
            collision.captured_at, collision.received_at, collision.created_at,
        )
        self.assertEqual(self.publish(collision).failure.code, "screen_capture_conflict")
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM sources", ())["n"], 1)
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM assets", ())["n"], 1)

    def test_coverage_claim_requires_a_window_title(self) -> None:
        capture = self.capture()
        self.assertEqual(self.publish(capture, title=None).failure.code, "screen_original_invalid")
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM screen_captures", ())["n"], 0)

    def test_signature_alone_does_not_make_a_decodable_capture(self) -> None:
        with self.assertRaises(ReferenceValidationError):
            ScreenImage("image/png", IMAGE.content[:12])


if __name__ == "__main__":
    unittest.main()
