import json
import unittest

from companion_v2.configuration.service import ConfigurationService
from companion_v2.diagnostics.models import DiagnosticContext, DiagnosticQuery
from companion_v2.diagnostics.service import DiagnosticService
from companion_v2.execution.models import TaskError
from companion_v2.model_gateway.budget import BudgetLedger
from companion_v2.model_gateway.failures import ModelFailure
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.model_gateway.routing import ModelRouter
from companion_v2.model_gateway.service import LocalModelGateway
from companion_v2.model_gateway.response_diagnostics import ResponseDiagnostics, ResponseTextSummary
from tests.test_model_gateway import ModelFixture


class ModelFailureTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    async def test_unknown_result_logs_safe_provider_diagnostics(self):
        private = "private provider response text"
        summary = ResponseDiagnostics(True, "stop", "native_rejected",
            raw=ResponseTextSummary.from_text(private), failure=ModelFailure.NATIVE_PARSE)
        self.responses["primary"] = ProviderResponse(
            "unknown", failure=ModelFailure.NATIVE_PARSE, diagnostics=summary)
        run = self.model_run()
        with self.assertLogs("companion_v2.model_gateway.service", level="WARNING") as captured:
            with self.assertRaises(TaskError) as error:
                await self.gateway.generate(run, self.request())
        self.assertEqual(error.exception.code, "model_usage_unknown")
        message = "\n".join(captured.output)
        self.assertIn("native_parse", message)
        self.assertIn("native_response_parse_failed", message)
        self.assertIn("parse_state=native_rejected", message)
        self.assertIn(f"raw_chars={len(private)}", message)
        self.assertNotIn(summary.raw.sha256, message)
        self.assertNotIn(private, message)

    async def test_settled_unknown_classification_survives_reopen_and_remains_authorized(self):
        summary = ResponseDiagnostics(True, "stop", "native_rejected",
            raw=ResponseTextSummary.from_text("[]"), failure=ModelFailure.NATIVE_PARSE)
        self.responses["primary"] = ProviderResponse(
            "unknown", usage=Amount(12, 30), receipt_ref="parse-receipt", failure=ModelFailure.NATIVE_PARSE,
            diagnostics=summary,
        )
        run = self.model_run()
        with self.assertRaises(TaskError):
            await self.gateway.generate(run, self.request())
        with self.assertRaises(TaskError) as replay:
            await self.gateway.generate(run, self.request())
        self.assertEqual(replay.exception.code, "model_request_already_started")
        before = self.gateway.observe(self.context, "task-1").unwrap()
        call = before["calls"][0]
        self.assertEqual((call["state"], call["usage_state"], call["actual_tokens"]), ("unknown", "settled", 12))
        self.assertEqual(call["failure"]["phase"], "native_parse")
        self.assertEqual(call["failure"]["code"], "native_response_parse_failed")
        self.assertEqual(call["response_diagnostics"], summary.to_record())
        self.ledger.reconcile_usage(self.call_rows()[0]["call_id"], self.providers[0].binding, Amount(12, 30),
            receipt_ref="parse-receipt", observed_at=self.clock.now())
        self.assertEqual(self.gateway.observe(self.context, "task-1").unwrap(), before)
        self.assertTrue(all(row["held_tokens"] == 0 and row["spent_tokens"] == 12 for row in self.accounts()))
        wrong_owner = self.context_for(self.core)
        self.runtime.close()

        reopened = self.open_runtime()
        configuration = ConfigurationService(reopened, self.registry)
        tasks = self.supervisor(reopened)
        gateway = LocalModelGateway(ModelRouter(configuration, self.profiles, self.providers),
                                    BudgetLedger(reopened, self.budget_policy), tasks)
        self.assertEqual(gateway.observe(self.context, "task-1").unwrap(), before)
        self.assertEqual(gateway.observe(wrong_owner, "task-1").failure.code, "task_unavailable")
        diagnostics = DiagnosticService(configuration, tasks=tasks, models=gateway, now=self.clock.now)
        context = DiagnosticContext(self.context.actor, self.context.role_binding, self.context.audience)
        report = diagnostics.inspect(context, DiagnosticQuery(execution=True, execution_task_id="task-1")).unwrap()
        details = json.loads(report.results[0].details_json)
        self.assertEqual(details["model"]["calls"][0]["failure"], call["failure"])
        self.assertEqual(details["model"]["calls"][0]["response_diagnostics"], summary.to_record())
        self.assertEqual([name for name, _ in self.called], ["primary"])

    async def test_adapter_cannot_inject_private_text_as_a_failure_code(self):
        private = "private response and credential"

        async def invalid(envelope):
            return ProviderResponse("unknown", failure=private)

        self.responses["primary"] = invalid
        with self.assertRaises(TaskError):
            await self.gateway.generate(self.model_run(), self.request())
        report = self.gateway.observe(self.context, "task-1").unwrap()
        self.assertEqual(report["calls"][0]["failure"]["code"], "adapter_failed")
        self.assertNotIn(private, json.dumps(report))
        self.assertNotIn(private, str(tuple(self.runtime.read_one("SELECT * FROM model_call_failures", ()))))
        self.assertEqual([name for name, _ in self.called], ["primary"])


if __name__ == "__main__":
    unittest.main()
