from dataclasses import replace
from datetime import timedelta
import asyncio
import hashlib
import threading
from unittest.mock import patch

from companion_v2.execution.models import TaskError
from companion_v2.capabilities import CapabilityAuthorizationState, CapabilityRepository
from companion_v2.foundation.refs import AssetRef, AudienceRef, ReferenceValidationError, SourceRef, SubjectRef, SubjectKind, VersionRef
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.screen import (
    SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ, ClockQuality, ScreenCapture, ScreenCaptureRef,
    ScreenCoverage, ScreenFeedbackKind, ScreenInterpretation, ScreenMediaKind,
    ScreenProcessingPipeline, ScreenRepository,
)
from companion_v2.sources import AssetRecord, AssetRepository, SourceRecord, SourceRepository
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from tests.g6_support import G6Fixture, INSTALLATION, NOW


class LocalRole:
    def __init__(self, callback=None, *, kind=ScreenFeedbackKind.ATTENTION, units=None) -> None:
        self.calls = 0
        self.callback = callback
        self.kind = kind
        self.units = units
        self.requests = []

    def interpret(self, request):
        self.calls += 1
        self.requests.append(request)
        if self.callback is not None:
            self.callback()
        return ScreenInterpretation(
            "A window title is available; this does not establish what the user is doing.",
            self.units or request.input_units, self.kind,
        )


class ScreenPipelineTests(G6Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.enable_screen()
        self.screens = ScreenRepository(self.runtime, authorizer=self.identities)
        self.capture = self.create_capture()
        self.model = LocalRole()

    def create_capture(self, capture_id="capture-a", *, register=True, publish_asset=True):
        reference = ScreenCaptureRef(
            capture_id,
            SourceRef(
                f"source-{capture_id}", "screen", self.scope, VersionRef(f"source-lineage-{capture_id}", 1),
                NOW, NOW + timedelta(hours=1),
            ),
            AssetRef(f"asset-{capture_id}", "screen", self.scope, VersionRef(f"asset-lineage-{capture_id}", 1), "same-physical-image-hash"),
        )
        payload = "synthetic window title"
        SourceRepository(self.runtime).publish(
            SourceRecord(reference.source, AudienceRef(self.scope, (self.subject,)), hashlib.sha256(payload.encode()).hexdigest(), payload),
            observed_at=NOW,
        ).unwrap()
        if publish_asset:
            AssetRepository(self.runtime).publish(
                AssetRecord(reference.asset, AudienceRef(self.scope, (self.subject,))), observed_at=NOW,
            ).unwrap()
        captured = ScreenCapture(
            reference, "trusted-fixture-device", ScreenMediaKind.IMAGE,
            ScreenCoverage("window-fixture", ("window.title", "image.viewport"), ("browser body not available",)),
            NOW - timedelta(seconds=5), NOW - timedelta(seconds=1), NOW,
        )
        if register:
            self.screens.register_capture(captured, role=self.role, resolved=self.resolved, observed_at=self.clock.now()).unwrap()
        return captured

    def process(self, **changes):
        parameters = dict(
            request_id="request-a", capture=self.capture.reference, role=self.role,
            role_instruction="Continue the existing role and relationship.", purpose="Understand this window label.",
            input_units=("window.title",), processor_id="local-role-fixture-v1", resolved=self.resolved,
        )
        parameters.update(changes)
        return asyncio.run(ScreenProcessingPipeline(
            screens=self.screens, operations=OperationRepository(self.runtime), role_port=self.model, now=self.clock.now,
        ).process(**parameters))

    def process_concurrently(self, **changes):
        """A second pipeline entry from the fixture port must not need this thread's loop."""
        box = {}

        def target():
            try:
                box["result"] = self.process(**changes)
            except BaseException as error:  # surfaced to the caller below
                box["error"] = error

        worker = threading.Thread(target=target)
        worker.start()
        worker.join()
        if "error" in box:
            raise box["error"]
        return box["result"]

    def restart(self) -> None:
        snapshot = self.identities.snapshot()
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.identities = IdentityDirectory.from_snapshot(snapshot)
        self.capabilities = CapabilityRepository(self.runtime)
        self.screens = ScreenRepository(self.runtime, authorizer=self.identities)

    def follow_up(self, feedback_id, *, capture=None):
        return self.screens.read_feedback(
            feedback_id, capture=capture or self.capture.reference,
            resolved=self.resolved, observed_at=self.clock.now(),
        )

    def revoke_consent(self, capability=SCREEN_READ, revision=1):
        self.capabilities.set_authorization(
            extension_id=SCREEN_EXTENSION, capability_id=capability, subject=self.subject, scope=self.scope,
            state=CapabilityAuthorizationState.REVOKED, expected_revision=revision, observed_at=self.clock.now(),
        ).unwrap()

    def test_local_chain_preserves_coverage_and_restart_replays_without_model_or_sender(self) -> None:
        first = self.process().unwrap()
        self.assertEqual(first.result.analysis.capture, self.capture.reference)
        self.assertEqual(first.result.analysis.input_units, ("window.title",))
        self.assertEqual(first.result.material.capture.captured_at, NOW - timedelta(seconds=5))
        self.assertEqual(first.result.material.capture.received_at, NOW - timedelta(seconds=1))
        self.assertEqual(first.result.material.capture.coverage.gaps, ("browser body not available",))
        self.assertEqual(self.model.requests[0].role, self.role)
        self.assertIn("untrusted material", self.model.requests[0].instruction)
        self.assertFalse(first.replayed)
        self.assertEqual(self.runtime.read_all("SELECT * FROM evidence", ()), ())
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())
        self.assertEqual(self.model.calls, 1)
        self.restart()
        self.model = LocalRole()
        replay = self.process().unwrap()
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.result, first.result)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).unwrap(), first.result)

    def test_followup_uses_original_even_with_identical_new_image_and_blocks_expiry(self) -> None:
        first = self.process().unwrap()
        later = self.create_capture("capture-later")
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).unwrap().material.capture, self.capture)
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id, capture=later.reference).failure.code, "screen_feedback_capture_mismatch")
        self.clock.advance(timedelta(hours=1))
        self.restart()
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).failure.code, "source_expired")
        self.assertEqual(self.model.calls, 1)

    def test_revoked_source_and_asset_are_not_read_through_the_analysis(self) -> None:
        first = self.process().unwrap()
        AssetRepository(self.runtime).revoke(
            self.capture.reference.asset, expected_governance_revision=1, observed_at=NOW,
        ).unwrap()
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).failure.code, "asset_revoked")
        SourceRepository(self.runtime).revoke(
            self.capture.reference.source, expected_governance_revision=1, observed_at=NOW,
        ).unwrap()
        self.restart()
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).failure.code, "source_revoked")

    def test_discard_preserves_governed_originals_and_allows_later_revocation(self) -> None:
        first = self.process().unwrap()
        self.capabilities.request_discard(extension_id=SCREEN_EXTENSION, expected_revision=1, observed_at=NOW).unwrap()
        self.capabilities.complete_discard(extension_id=SCREEN_EXTENSION, expected_revision=2, observed_at=NOW).unwrap()
        self.restart()
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).unwrap().analysis, first.result.analysis)
        self.assertEqual(self.process(request_id="new-request").failure.code, "capability_not_admissible")
        self.revoke_consent()
        self.restart()
        self.assertEqual(self.follow_up(first.result.anchor.feedback_id).failure.code, "capability_consent_revoked")
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM screen_captures", ())["n"], 1)
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM sources", ())["n"], 1)

    def test_model_time_revoke_regrant_does_not_revive_old_permission(self) -> None:
        def callback():
            self.revoke_consent(SCREEN_PROCESS)
            self.capabilities.set_authorization(
                extension_id=SCREEN_EXTENSION, capability_id=SCREEN_PROCESS, subject=self.subject, scope=self.scope,
                state=CapabilityAuthorizationState.ACTIVE, expected_revision=2, observed_at=NOW,
            ).unwrap()
        self.model = LocalRole(callback)
        self.assertEqual(self.process().failure.code, "screen_admission_changed")
        self.assertEqual(self.runtime.read_all("SELECT * FROM screen_feedback_anchors", ()), ())
        self.assertEqual(self.process().failure.code, "screen_processing_unresolved")
        self.assertEqual(self.model.calls, 1)

    def test_model_time_pause_resume_and_role_change_fence_old_result(self) -> None:
        def callback():
            self.capabilities.pause(extension_id=SCREEN_EXTENSION, expected_revision=1, observed_at=NOW).unwrap()
            self.capabilities.resume(extension_id=SCREEN_EXTENSION, expected_revision=2, observed_at=NOW).unwrap()
        self.model = LocalRole(callback)
        self.assertEqual(self.process().failure.code, "screen_admission_changed")
        def role_change():
            self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role, enabled=False, expected_revision=1, observed_at=NOW).unwrap()
            self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=self.role, enabled=True, expected_revision=2, observed_at=NOW).unwrap()
        self.model = LocalRole(role_change)
        self.assertEqual(self.process(request_id="request-b").failure.code, "screen_admission_changed")
        self.assertEqual(self.runtime.read_all("SELECT * FROM screen_analyses", ()), ())

    def test_model_time_source_expiry_does_not_save_analysis(self) -> None:
        self.model = LocalRole(lambda: self.clock.advance(timedelta(hours=1)))
        self.assertEqual(self.process().failure.code, "source_expired")
        self.assertEqual(self.runtime.read_all("SELECT * FROM screen_analyses", ()), ())

    def test_model_time_identity_rebound_is_enforced(self) -> None:
        def callback():
            self.identities.bind(
                binding_id="binding-b", principal=self.principal,
                subject=SubjectRef(INSTALLATION, SubjectKind.HUMAN, "subject-b"), valid_from=NOW,
            )
        self.model = LocalRole(callback)
        self.assertEqual(self.process().failure.code, "binding_rebound")
        self.restart()
        self.assertEqual(self.process().failure.code, "binding_rebound")
        self.assertEqual(self.runtime.read_all("SELECT * FROM screen_analyses", ()), ())

    def test_revoked_host_grant_cannot_be_replaced_by_extension_consent(self) -> None:
        self.identities.revoke_grant(f"grant-{SCREEN_READ}", revoked_at=NOW)
        self.assertEqual(self.process().failure.code, "authorization_revoked")
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_subject_with_grants_cannot_read_another_subjects_original(self) -> None:
        other = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "subject-b")
        self.identities.bind(binding_id="binding-b", principal=self.principal, subject=other, valid_from=NOW)
        resolved = self.identities.resolve_authenticated(self.principal, observed_at=NOW).unwrap()
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.identities.issue_grant(
                grant_id=f"other-{capability}", subject=other, scope=self.scope, capability=capability,
                tier=AuthorizationTier.IMPORTANT, valid_from=NOW,
            )
            self.capabilities.set_authorization(
                extension_id=SCREEN_EXTENSION, capability_id=capability, subject=other, scope=self.scope,
                state=CapabilityAuthorizationState.ACTIVE, expected_revision=0, observed_at=NOW,
            ).unwrap()
        self.assertEqual(self.process(resolved=resolved).failure.code, "source_audience_denied")
        self.assertEqual(self.model.calls, 0)
        with self.assertRaises(ReferenceValidationError):
            ScreenCaptureRef("bad", replace(self.capture.reference.source, owner="reality"), self.capture.reference.asset)

    def test_scope_mismatch_and_reentrant_same_request_do_not_call_model_twice(self) -> None:
        ref = self.capture.reference
        foreign_scope = replace(self.scope, native_scope_id="other-private")
        changed = replace(ref, source=replace(ref.source, scope=foreign_scope), asset=replace(ref.asset, scope=foreign_scope))
        self.assertEqual(self.process(capture=changed).failure.code, "capability_consent_missing")
        self.assertEqual(self.model.calls, 0)
        seen = []
        self.model = LocalRole(lambda: seen.append(self.process_concurrently()))
        first = self.process().unwrap()
        self.assertEqual(seen[0].failure.code, "screen_processing_unresolved")
        self.assertTrue(self.process().unwrap().replayed)
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(first.result.anchor.capture, ref)

    def test_missing_asset_and_forged_source_metadata_do_not_register(self) -> None:
        incomplete = self.create_capture("incomplete", register=False, publish_asset=False)
        self.assertEqual(self.screens.register_capture(
            incomplete, role=self.role, resolved=self.resolved, observed_at=NOW,
        ).failure.code, "asset_not_found")
        forged_ref = replace(self.capture.reference, source=replace(self.capture.reference.source, expires_at=NOW + timedelta(days=2)))
        self.assertEqual(self.screens.read_capture(forged_ref, resolved=self.resolved, observed_at=NOW).failure.code, "source_reference_mismatch")
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM screen_captures", ())["n"], 1)

    def test_unknown_model_result_is_persistent_and_not_resubmitted(self) -> None:
        def fail():
            raise TimeoutError("fixture submitted but result unknown")
        self.model = LocalRole(fail)
        self.assertEqual(self.process().failure.code, "screen_processing_unknown")
        self.restart()
        self.model = LocalRole()
        self.assertEqual(self.process().failure.code, "screen_processing_unresolved")
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.runtime.read_one("SELECT state FROM operations", ())["state"], "unknown")

    def test_model_task_error_keeps_its_code_without_repeating_processing(self) -> None:
        def fail():
            raise TaskError("screen_interpretation_invalid", "the returned interpretation was invalid")
        self.model = LocalRole(fail)
        result = self.process()
        self.assertEqual(result.failure.code, "screen_interpretation_invalid")
        self.assertEqual(result.failure.reason, "the returned interpretation was invalid")
        self.assertEqual(self.process().failure.code, "screen_processing_unresolved")
        self.assertEqual(self.model.calls, 1)

    def test_result_commit_before_receipt_loss_recovers_without_reprocessing(self) -> None:
        with patch.object(OperationRepository, "transition", side_effect=RuntimeError("lost completion ACK")):
            with self.assertRaises(RuntimeError):
                self.process()
        self.assertEqual(self.runtime.read_one("SELECT count(*) AS n FROM screen_feedback_anchors", ())["n"], 1)
        self.restart()
        self.model = LocalRole()
        replay = self.process().unwrap()
        self.assertTrue(replay.replayed)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(OperationRepository(self.runtime).get(replay.operation.operation_id).unwrap().state, OperationState.COMPLETED)

    def test_reused_request_id_cannot_change_purpose_or_capture(self) -> None:
        self.process().unwrap()
        another = self.create_capture("capture-b")
        self.assertEqual(self.process(purpose="A different question").failure.code, "idempotency_key_conflict")
        self.assertEqual(self.process(capture=another.reference).failure.code, "idempotency_key_conflict")
        self.assertEqual(self.model.calls, 1)

    def test_unseen_coverage_and_proactive_permission_do_not_become_feedback(self) -> None:
        self.assertEqual(self.process(input_units=("unseen-video",)).failure.code, "screen_coverage_mismatch")
        self.assertEqual(self.model.calls, 0)
        self.model = LocalRole(units=("image.viewport",))
        self.assertEqual(self.process().failure.code, "screen_coverage_mismatch")
        self.assertEqual(self.runtime.read_all("SELECT * FROM screen_analyses", ()), ())
        self.model = LocalRole(kind=ScreenFeedbackKind.PROACTIVE)
        self.assertEqual(self.process(request_id="request-proactive").failure.code, "screen_proactive_disabled")
        self.capabilities.set_settings(
            extension_id=SCREEN_EXTENSION, scope=self.scope, proactive_enabled=True,
            thought_weight=0.01, expected_revision=0, observed_at=NOW,
        ).unwrap()
        self.assertEqual(self.process(request_id="new-proactive-intent").unwrap().result.anchor.kind, ScreenFeedbackKind.PROACTIVE)
        self.assertEqual(OperationRepository(self.runtime).pending_outbox(), ())

    def test_client_reported_time_is_preserved_and_verified_future_time_is_rejected(self) -> None:
        future = replace(self.capture, captured_at=NOW + timedelta(hours=2))
        self.assertEqual(future.coverage.clock_quality, ClockQuality.CLIENT_REPORTED)
        with self.assertRaises(ReferenceValidationError):
            replace(future, coverage=replace(future.coverage, clock_quality=ClockQuality.VERIFIED))
