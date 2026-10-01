from dataclasses import replace
import json
import unittest

from companion_v2.diagnostics.models import CheckStatus, DiagnosticContext, DiagnosticQuery
from companion_v2.diagnostics.service import DiagnosticService
from companion_v2.execution.models import TaskResult
from tests.test_execution import ExecutionFixture


class ExecutionDiagnosticTests(ExecutionFixture):
    def setUp(self):
        super().setUp()
        self.diagnostics = DiagnosticService(self.configuration, tasks=self.tasks, now=self.clock.now)
        self.diagnostic_context = DiagnosticContext(self.context.actor, self.context.role_binding, self.context.audience)
        self.query = DiagnosticQuery(execution=True, execution_task_id="task-1")

    def test_exact_task_projection_redacts_contents_and_unknown_stays_unknown(self):
        claim = self.running(kind="fixture.effect")
        self.tasks.begin_effect(claim).unwrap()
        self.tasks.finish(claim, TaskResult("uncertain", "unknown", result_ref="private-original")).unwrap()
        result = self.diagnostics.inspect(self.diagnostic_context, self.query).unwrap().results[0]
        details = json.loads(result.details_json)
        self.assertEqual((result.status, result.code, details["task"]["state"]), (CheckStatus.UNKNOWN, "local_task_observed", "uncertain"))
        self.assertEqual((details["provider"], details["sender"]), ("not_connected", "not_connected"))
        self.assertNotIn("private-original", result.details_json)
        self.assertNotIn("fixture:original-input", result.details_json)
        self.assertIsNone(details["task"]["provider_latency_ms"])

    def test_original_report_is_invalidated_by_task_transition_and_cannot_cross_context(self):
        self.submit()
        report = self.diagnostics.inspect(self.diagnostic_context, self.query).unwrap()
        self.claim()
        self.assertEqual(self.diagnostics.validated(self.diagnostic_context, report.report_id).failure.code, "diagnostic_evidence_changed")
        other = self.context_for(self.core)
        other_diagnostic = DiagnosticContext(other.actor, other.role_binding, other.audience)
        self.assertEqual(self.diagnostics.inspect(other_diagnostic, self.query).failure.code, "task_unavailable")

    def test_missing_task_and_unattached_runner_cannot_be_reported_as_executed(self):
        self.assertEqual(self.diagnostics.inspect(self.diagnostic_context, self.query).failure.code, "task_unavailable")
        result = self.diagnostics.inspect(self.diagnostic_context, replace(self.query, execution_task_id=None)).unwrap().results[0]
        self.assertEqual((result.status, result.code), (CheckStatus.UNKNOWN, "execution_partially_connected"))
        disconnected = DiagnosticService(self.configuration, now=self.clock.now)
        result = disconnected.inspect(self.diagnostic_context, self.query).unwrap().results[0]
        self.assertEqual((result.status, result.code), (CheckStatus.UNKNOWN, "execution_unobserved"))


if __name__ == "__main__":
    unittest.main()
