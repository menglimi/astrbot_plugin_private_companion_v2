from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.capabilities import CapabilityAuthorizationState
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry, ValueKind
from companion_v2.configuration.service import ConfigurationService
from companion_v2.diagnostics.models import CheckStatus, DiagnosticContext, DiagnosticMode, DiagnosticQuery, IncidentWindow
from companion_v2.diagnostics.service import DiagnosticService, report_document
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import AudienceRef, ScopeKind
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.screen.models import SCREEN_EXTENSION, SCREEN_READ
from companion_v2.storage.models import OperationState
from tests.test_management_access import ManagementFixture, NOW, SCOPE


class DiagnosticFixture(ManagementFixture):
    def setUp(self):
        super().setUp()
        self.clock = DeterministicClock.at(NOW)
        self.diagnostics = DiagnosticService(self.configuration, now=self.clock.now)
        self.important_context = self.context(self.important)
        self.core_context = self.context(self.core)
        self.query = DiagnosticQuery(target=self.window, group_id="output")

    def context(self, actor, *, group=False):
        scope = SCOPE if actor == self.important else replace(SCOPE, native_scope_id=actor.subject.subject_id,
                    conversation_id="conversation-" + actor.subject.subject_id, session_id="session-" + actor.subject.subject_id)
        if group:
            scope = replace(scope, kind=ScopeKind.GROUP, native_scope_id="group", conversation_id="group-conversation", session_id="group-session")
        if self.personas.route(scope) is None:
            route = ConversationRoute(scope, group_id="group") if group else ConversationRoute(scope, user=actor.subject)
            self.personas.register_route(route, observed_at=self.clock.now())
        return DiagnosticContext(actor, self.identity.resolve_role(scope, observed_at=self.clock.now()).unwrap(),
                                 AudienceRef(scope, (actor.subject, self.standard.subject) if group else (actor.subject,)))

    def check(self, query=None, context=None):
        return self.diagnostics.inspect(context or self.important_context, query or self.query)

    def counts(self):
        return tuple(self.runtime.read_one(f"SELECT COUNT(*) AS n FROM {table}", ())["n"] for table in (
            "configuration_changes", "operations", "outbox", "diagnostic_repair_proposals"))


class DiagnosticTests(DiagnosticFixture):
    def test_explain_is_static_and_never_claims_runtime_checks(self):
        before = self.counts()
        result = self.diagnostics.explain(self.context(self.important, group=True), "configuration").unwrap()
        self.assertEqual((result.mode, result.results, result.findings), (DiagnosticMode.EXPLAIN, (), ()))
        self.assertIn("未检查", result.uncertainties[0])
        self.assertEqual(self.counts(), before)

    def test_config_adoption_failed_pending_applied_and_restart_are_distinct(self):
        initial = self.check().unwrap().results[0]
        self.assertEqual((initial.status, initial.code), (CheckStatus.UNKNOWN, "consumer_not_started"))
        generation = self.configuration.start_consumer("output", expected_generation=0)
        snapshot = self.read(self.important).unwrap()
        self.configuration.report_application(self.important, snapshot=snapshot, generation=generation,
                                             succeeded=False, observed_at=NOW).unwrap()
        self.assertEqual(self.check().unwrap().results[0].status, CheckStatus.FAIL)
        self.configuration.report_application(self.important, snapshot=snapshot, generation=generation,
                                             succeeded=True, observed_at=NOW).unwrap()
        self.assertEqual(self.check().unwrap().results[0].status, CheckStatus.PASS)
        self.write(self.important, snapshot).unwrap()
        pending = self.check().unwrap().results[0]
        self.assertEqual((pending.status, pending.code), (CheckStatus.WARN, "next_task"))
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.diagnostics = DiagnosticService(ConfigurationService(self.runtime, self.registry), now=self.clock.now)
        self.assertEqual(self.check().unwrap().results[0].code, "consumer_not_started")

    def test_report_redacts_values_records_sources_time_and_no_side_effects(self):
        self.registry = FieldRegistry(version="secret.v1", fields=(
            FieldDefinition("prompt.text", "prompt", "prompt", ValueKind.TEXT, "private-prompt-body"),))
        configuration = ConfigurationService(self.runtime, self.registry)
        diagnostics = DiagnosticService(configuration, now=self.clock.now)
        before = self.counts()
        report = diagnostics.inspect(self.important_context, DiagnosticQuery(target=self.window, group_id="prompt")).unwrap()
        self.assertNotIn("private-prompt-body", json.dumps(report_document(report)))
        result = report.results[0]
        self.assertEqual((result.started_at, result.finished_at), (NOW, NOW))
        self.assertGreaterEqual(result.elapsed_ms, 0)
        self.assertEqual(json.loads(result.details_json)["fields"]["prompt.text"]["source"], "default")
        self.assertEqual(result.check.side_effects, "none")
        self.assertTrue(result.evidence[0].revision_token)
        self.assertEqual(self.counts(), before)

    def test_sensitive_checks_use_existing_permissions_and_private_audience(self):
        self.assertEqual(self.check(DiagnosticQuery(target=self.window, group_id="security")).failure.code, "core_access_required")
        self.assertFalse(self.check(DiagnosticQuery(target=self.global_target, group_id="output")).is_success)
        group = self.context(self.core, group=True)
        self.assertEqual(self.check(context=group).failure.code, "private_result_required")
        self.assertEqual(self.check(DiagnosticQuery(storage=True)).failure.code, "core_access_required")
        storage = self.check(DiagnosticQuery(storage=True, execution=True), self.core_context).unwrap()
        self.assertEqual([r.status for r in storage.results], [CheckStatus.PASS, CheckStatus.UNKNOWN])
        self.assertEqual(json.loads(storage.results[0].details_json)["integrity_scan"], "not_run")

    def test_capability_acquisition_and_consent_do_not_prove_readiness(self):
        query = DiagnosticQuery(extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ)
        self.assertEqual(self.check(query).unwrap().results[0].status, CheckStatus.NOT_APPLICABLE)
        self.acquire().unwrap()
        self.management.set_consent(self.important, extension_id=SCREEN_EXTENSION, capability_id=SCREEN_READ,
            subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.ACTIVE, expected_revision=0,
            operation=self.operation(SCOPE, owner=self.management.OWNER), observed_at=NOW).unwrap()
        result = self.check(query).unwrap().results[0]
        details = json.loads(result.details_json)
        self.assertEqual((result.status, details["desired_state"], details["consent"], details["runtime_ready"]),
                         (CheckStatus.UNKNOWN, "active", "active", "unknown"))
        other = self.context(self.standard)
        self.grant(self.standard, other.scope, "capability.view")
        other_result = self.check(query, other).unwrap().results[0]
        self.assertEqual(json.loads(other_result.details_json)["consent"], "capability_consent_missing")

    def test_incident_is_exact_bounded_and_unknown_is_not_reconstructed_as_success(self):
        operation = self.operation(SCOPE, owner="conversation")
        self.diagnostics.operations.reserve(operation, parameter_hash="sensitive-hash", observed_at=NOW,
                                            outbox_part_id="part", outbox_payload_hash="secret-payload").unwrap()
        self.diagnostics.operations.transition(operation.operation_id, expected_state=OperationState.ACCEPTED,
                                              next_state=OperationState.UNKNOWN, observed_at=NOW).unwrap()
        query = DiagnosticQuery(DiagnosticMode.INCIDENT, operation_id=operation.operation_id, operation_scope=SCOPE,
                                window=IncidentWindow(NOW - timedelta(minutes=5), NOW))
        result = self.check(query, self.core_context).unwrap().results[0]
        details = json.loads(result.details_json)
        self.assertEqual((result.status, details["local_operation_state"], details["external_effect"]),
                         (CheckStatus.UNKNOWN, "unknown", "unknown"))
        self.assertEqual(details["outbox"], {"pending": 1})
        self.assertNotIn("sensitive-hash", result.details_json)
        self.assertNotIn("secret-payload", result.details_json)
        self.assertEqual(self.check(query).failure.code, "core_access_required")
        other = replace(SCOPE, bot_id="other-bot")
        self.assertEqual(self.check(replace(query, operation_scope=other), self.core_context).unwrap().results[0].code,
                         "operation_not_observed")
        self.assertEqual(self.check(replace(query, window=IncidentWindow(NOW - timedelta(hours=1), NOW - timedelta(minutes=1))),
                                    self.core_context).unwrap().results[0].code, "operation_outside_window")
        self.assertEqual(self.check(replace(query, window=IncidentWindow(NOW, NOW + timedelta(seconds=1))),
                                    self.core_context).failure.code, "incident_window_in_future")

    def test_missing_operation_is_unknown_and_completed_local_operation_is_not_delivery(self):
        query = DiagnosticQuery(DiagnosticMode.INCIDENT, operation_id="missing", operation_scope=SCOPE,
                                window=IncidentWindow(NOW - timedelta(minutes=1), NOW))
        self.assertEqual(self.check(query, self.core_context).unwrap().results[0].status, CheckStatus.UNKNOWN)
        operation = self.operation(SCOPE)
        self.diagnostics.operations.reserve(operation, parameter_hash="hash", observed_at=NOW).unwrap()
        self.diagnostics.operations.transition(operation.operation_id, expected_state=OperationState.ACCEPTED,
                                              next_state=OperationState.COMPLETED, observed_at=NOW).unwrap()
        result = self.check(replace(query, operation_id=operation.operation_id), self.core_context).unwrap().results[0]
        self.assertEqual((result.status, result.code), (CheckStatus.WARN, "local_operation_completed"))
        self.assertEqual(json.loads(result.details_json)["recipient_received"], "unknown")
        self.clock.advance(timedelta(seconds=5))
        self.diagnostics.operations.transition(operation.operation_id, expected_state=OperationState.COMPLETED,
                                              next_state=OperationState.UNKNOWN, observed_at=self.clock.now()).unwrap()
        later = self.check(replace(query, operation_id=operation.operation_id), self.core_context).unwrap().results[0]
        self.assertEqual((later.status, later.code), (CheckStatus.UNKNOWN, "operation_changed_after_window"))

    def test_report_cannot_cross_actor_bot_role_expiry_or_changed_evidence(self):
        report = self.check().unwrap()
        self.assertEqual(self.diagnostics.validated(self.core_context, report.report_id).failure.code, "diagnostic_report_unavailable")
        self.clock.advance(timedelta(seconds=60))
        self.assertEqual(self.diagnostics.validated(self.important_context, report.report_id).failure.code, "diagnostic_report_expired")
        fresh = self.check().unwrap()
        self.write(self.important, self.read(self.important, now=self.clock.now()).unwrap()).unwrap()
        self.assertEqual(self.diagnostics.validated(self.important_context, fresh.report_id).failure.code, "diagnostic_evidence_changed")

    def test_revoked_and_rebound_identity_cannot_reuse_report(self):
        report = self.check().unwrap()
        self.identity.revoke_binding(self.important.binding_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.diagnostics.validated(self.important_context, report.report_id).failure.code, "binding_revoked")

    def test_collection_is_bounded_and_slow_local_result_is_unknown(self):
        ticks = iter((0.0, 1.0))
        diagnostics = DiagnosticService(self.configuration, now=self.clock.now, monotonic=lambda: next(ticks))
        result = diagnostics.inspect(self.important_context, self.query).unwrap().results[0]
        self.assertEqual((result.status, result.code, result.elapsed_ms), (CheckStatus.UNKNOWN, "local_check_budget_exceeded", 1000))
        with self.assertRaises(ValueError):
            IncidentWindow(NOW - timedelta(days=2), NOW)
        with self.assertRaises(ValueError):
            DiagnosticQuery(operation_id="unbounded")
        first = self.check().unwrap()
        for _ in range(33):
            self.check().unwrap()
        self.assertEqual(len(self.diagnostics._reports), 32)
        self.assertEqual(self.diagnostics.validated(self.important_context, first.report_id).failure.code, "diagnostic_report_unavailable")


if __name__ == "__main__":
    unittest.main()
