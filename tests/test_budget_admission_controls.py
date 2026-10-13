"""Opting out of local admission preserves accounting and original-call identity."""

from dataclasses import replace
import unittest

from astrbot_host.settings import HostSettings
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.conversation.foreground import ModelDraft
from companion_v2.execution.models import TaskError, TaskResult
from companion_v2.model_gateway.budget import BudgetLedger, BudgetSoftPolicy, GROUP, SOFT_FIELDS
from companion_v2.model_gateway.models import Amount, BudgetPolicy, ProviderResponse
from companion_v2.model_gateway.service import LocalModelGateway
from tests.test_model_gateway import ModelFixture


class HostBudgetSettingsTests(unittest.TestCase):
    def test_an_existing_numeric_ceiling_does_not_implicitly_enable_a_limit(self):
        settings = HostSettings.parse({"runtime": {"budget_tokens": 3_000_000}})
        self.assertFalse(settings.budget.enabled)
        self.assertFalse(settings.budget_soft.enabled)
        self.assertEqual(settings.budget.installation.tokens, 3_000_000)

    def test_hard_admission_requires_the_explicit_host_switch(self):
        settings = HostSettings.parse({"runtime": {"enable_daily_model_hard_limit": True}})
        self.assertTrue(settings.budget.enabled)
        self.assertFalse(HostSettings.parse({}).budget.enabled)


class BudgetAdmissionControlsTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    async def test_disabled_hard_admission_records_usage_above_both_configured_limits(self):
        policy = BudgetPolicy(*(Amount(1, 1) for _ in range(5)), enabled=False)
        ledger = BudgetLedger(self.runtime, policy)
        gateway = LocalModelGateway(self.router, ledger, self.tasks)
        await gateway.generate(self.model_run("disabled-budget", kind="fixture.background"), self.request())
        self.assertEqual(len(self.called), 1)
        self.assertTrue(all((a["held_tokens"], a["spent_tokens"], a["spent_cost"]) == (0, 15, 40)
                            for a in self.accounts()))
        self.assertEqual(self.call_rows()[0]["actual_tokens"], 15)

    async def test_disabling_a_saved_budget_wait_keeps_unknown_calls_and_allows_new_work(self):
        self.responses["primary"] = ProviderResponse("generated", ModelDraft("usage unreported", ()))
        first = self.model_run("original-held-call", kind="fixture.background")
        completion = await self.gateway.generate(first, self.request())
        self.tasks.finish(first.claim, TaskResult("succeeded")).unwrap()
        waiting = self.model_run("unstarted-deferred-call", kind="fixture.background")
        with self.assertRaises(TaskError) as error:
            await self.gateway.generate(waiting, self.request())
        self.assertEqual(error.exception.code, "model_budget_exhausted")
        self.tasks.stop(waiting.claim, reason="worker_error").unwrap()

        disabled = BudgetLedger(self.runtime, replace(self.budget_policy, enabled=False))
        self.assertEqual(disabled.policy_hash, self.ledger.policy_hash)
        self.assertIsNone(disabled.background_deferral(self.context, "fixture.background", at=self.clock.now()))
        original = self.runtime.read_one("SELECT * FROM model_calls WHERE call_id=?", (completion.call_id,))
        self.assertIsNone(original["actual_tokens"])
        self.assertEqual(original["reserved_tokens"], 30)
        self.assertEqual(len(self.called), 1)

        gateway = LocalModelGateway(self.router, disabled, self.tasks)
        await gateway.generate(self.model_run("new-work-after-disable", kind="fixture.background"), self.request())
        self.assertEqual(len(self.called), 2)
        self.assertEqual(len(self.call_rows()), 2)
        self.assertTrue(all(a["held_tokens"] == 60 for a in self.accounts()))
        with self.assertRaises(TaskError):
            await gateway.generate(first, self.request())
        self.assertEqual(len(self.called), 2)

    async def test_global_soft_disable_prevents_a_legacy_role_flag_from_deferring_new_work(self):
        owner = SparseConfigurationOwner(self.runtime)
        installation = ConfigTarget(self.context.scope.installation_id, ConfigLayer.INSTALLATION)
        role = ConfigTarget(self.context.scope.installation_id, ConfigLayer.ROLE,
                            self.context.role_binding.role, bot_id=self.context.scope.bot_id)
        for target, enabled in ((installation, False), (role, True)):
            owner.write(target, SOFT_FIELDS,
                changes={GROUP + ".enable_daily_token_soft_limit": enabled,
                         GROUP + ".daily_token_soft_limit": 1}, reset=(),
                expected_revision=owner.read(target, SOFT_FIELDS).revision, observed_at=self.clock.now())
        ledger = BudgetLedger(self.runtime, replace(self.budget_policy, enabled=False),
                             BudgetSoftPolicy(enabled=True, tokens=1, kinds=("fixture.background",)))
        gateway = LocalModelGateway(self.router, ledger, self.tasks)
        await gateway.generate(self.model_run("global-budget-disabled", kind="fixture.background"), self.request())
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.call_rows()[0]["actual_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
