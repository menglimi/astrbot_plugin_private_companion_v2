"""Daily soft token ceiling: the configured bounds and the deferral they drive.

The soft ceiling is an installation/role setting with no window layer, matching
V1's `enable_daily_token_soft_limit` + `daily_token_soft_limit`. It decides only
whether optional background work starts, so it is read live and never mutates a
pinned daily account.
"""

from dataclasses import replace
import unittest

from companion_v2.agenda.planning import KIND as CALENDAR_PLANNING_KIND
from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldRegistry, ValueKind
from companion_v2.execution.models import TaskError, digest
from companion_v2.model_gateway.budget import (DEFAULT_SOFT_DEFER_KINDS, GROUP, SOFT_FIELDS, BudgetLedger,
                                              BudgetSoftPolicy, configuration_fields, effective_soft)
from companion_v2.model_gateway.models import Amount, BudgetPolicy, ProviderResponse
from companion_v2.conversation.foreground import ModelDraft
from tests.test_model_gateway import ModelFixture
from tests.test_management_access import NOW


class SoftCeilingConfigurationTests(unittest.TestCase):
    def test_the_fields_are_installation_and_role_scoped_only(self):
        fields = configuration_fields()
        self.assertEqual([f.field_id for f in fields],
                         [GROUP + ".enable_daily_token_soft_limit", GROUP + ".daily_token_soft_limit"])
        for field in fields:
            # No window layer: one conversation must not move the day's ceiling.
            self.assertEqual(field.layers, (ConfigLayer.INSTALLATION, ConfigLayer.ROLE))
            self.assertIs(field.apply_mode, ApplyMode.IMMEDIATE)
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id), (GROUP, GROUP, "configuration"))
        self.assertIs(fields[0].kind, ValueKind.BOOLEAN)
        self.assertIs(fields[1].kind, ValueKind.INTEGER)
        FieldRegistry(version="budget.v1", fields=fields)

    def test_a_daily_limit_requires_explicit_enablement(self):
        declared = {f.field_id: f for f in configuration_fields()}
        self.assertIs(declared[GROUP + ".enable_daily_token_soft_limit"].default, False)
        self.assertEqual(declared[GROUP + ".daily_token_soft_limit"].default, 800_000)
        self.assertEqual((declared[GROUP + ".daily_token_soft_limit"].minimum,
                          declared[GROUP + ".daily_token_soft_limit"].maximum), (0, 10**12))

    def test_the_policy_defers_only_optional_background_kinds(self):
        policy = BudgetSoftPolicy(enabled=True, tokens=1000)
        for kind in DEFAULT_SOFT_DEFER_KINDS:
            self.assertTrue(policy.is_deferrable(kind))
        # The kind selector is independent of the switch: the switch is applied by
        # the ledger, which reads it before asking about a kind.
        self.assertFalse(policy.is_deferrable("conversation.reply"))
        self.assertFalse(BudgetSoftPolicy(enabled=True, tokens=1000).is_deferrable("role.journal.write"))
        self.assertTrue(BudgetSoftPolicy(enabled=True, tokens=1000, kinds=("custom.kind",)).is_deferrable("custom.kind"))

    def test_the_policy_rejects_an_unbounded_declaration(self):
        for kwargs in ({"enabled": "yes", "tokens": 1}, {"enabled": True, "tokens": -1},
                       {"enabled": True, "tokens": 1, "kinds": ("x", 7)}):
            with self.assertRaises(ValueError):
                BudgetSoftPolicy(**kwargs)


class SoftCeilingResolutionTests(ModelFixture, unittest.TestCase):
    def target(self, layer=ConfigLayer.ROLE):
        context = self.context
        if layer is ConfigLayer.INSTALLATION:
            return ConfigTarget(context.scope.installation_id, layer)
        return ConfigTarget(context.scope.installation_id, layer, context.role_binding.role,
                            bot_id=context.scope.bot_id)

    def write(self, name, value, *, layer=ConfigLayer.ROLE):
        from companion_v2.configuration.owners import SparseConfigurationOwner
        owner = SparseConfigurationOwner(self.runtime)
        target = self.target(layer)
        return owner.write(target, SOFT_FIELDS, changes={GROUP + "." + name: value}, reset=(),
                           expected_revision=owner.read(target, SOFT_FIELDS).revision, observed_at=NOW)

    def test_a_data_root_without_a_stored_value_keeps_the_assembly_default(self):
        fallback = BudgetSoftPolicy(enabled=False, tokens=0)
        self.assertEqual(effective_soft(self.runtime, self.context, fallback), fallback)

    def test_a_stored_ceiling_overrides_the_assembly_default(self):
        self.write("enable_daily_token_soft_limit", True, layer=ConfigLayer.INSTALLATION)
        self.write("daily_token_soft_limit", 5000)
        policy = effective_soft(self.runtime, self.context, BudgetSoftPolicy(enabled=False, tokens=0))
        self.assertEqual((policy.enabled, policy.tokens), (True, 5000))
        self.assertTrue(policy.is_deferrable(CALENDAR_PLANNING_KIND))
        self.assertFalse(policy.is_deferrable("conversation.reply"))

    def test_a_global_disable_overrides_the_legacy_role_enable(self):
        self.write("enable_daily_token_soft_limit", False, layer=ConfigLayer.INSTALLATION)
        self.write("daily_token_soft_limit", 2_000_000, layer=ConfigLayer.INSTALLATION)
        self.write("enable_daily_token_soft_limit", True)
        policy = effective_soft(self.runtime, self.context, BudgetSoftPolicy(enabled=True, tokens=800_000))
        self.assertEqual((policy.enabled, policy.tokens), (False, 2_000_000))

    def test_installation_values_are_used_when_the_role_inherits(self):
        self.write("enable_daily_token_soft_limit", True, layer=ConfigLayer.INSTALLATION)
        self.write("daily_token_soft_limit", 5000, layer=ConfigLayer.INSTALLATION)
        policy = effective_soft(self.runtime, self.context, BudgetSoftPolicy(enabled=False, tokens=800_000))
        self.assertEqual((policy.enabled, policy.tokens), (True, 5000))

    def test_a_role_switch_alone_cannot_enable_a_disabled_host_default(self):
        self.write("enable_daily_token_soft_limit", True)
        policy = effective_soft(self.runtime, self.context, BudgetSoftPolicy(enabled=False, tokens=5000))
        self.assertEqual((policy.enabled, policy.tokens), (False, 5000))

    def test_partial_overrides_keep_the_host_default_for_the_other_field(self):
        fallback = BudgetSoftPolicy(enabled=True, tokens=5000)
        self.write("daily_token_soft_limit", 1234)
        policy = effective_soft(self.runtime, self.context, fallback)
        self.assertEqual((policy.enabled, policy.tokens), (True, 1234))
        self.write("enable_daily_token_soft_limit", False)
        policy = effective_soft(self.runtime, self.context, fallback)
        self.assertEqual((policy.enabled, policy.tokens), (False, 1234))

    def test_the_ceiling_is_read_per_role_without_a_window_layer(self):
        # Writing at role scope resolves for this role and leaves other scopes alone.
        self.write("enable_daily_token_soft_limit", True)
        self.write("daily_token_soft_limit", 1234)
        policy = effective_soft(self.runtime, self.context, None)
        self.assertEqual(policy.tokens, 1234)
        from companion_v2.configuration.owners import SparseConfigurationOwner
        installation = ConfigTarget(self.context.scope.installation_id, ConfigLayer.INSTALLATION)
        field = SparseConfigurationOwner(self.runtime).read(installation, SOFT_FIELDS).fields
        self.assertIsNone(field[GROUP + ".daily_token_soft_limit"].source)
        self.assertFalse(field[GROUP + ".daily_token_soft_limit"].explicit)


class SoftCeilingDeferralTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    """The ledger gate itself: what a reached ceiling starts deferring."""

    def setUp(self):
        super().setUp()
        # The configured ceiling carries only the switch and the threshold, so the
        # deferrable kinds stay the assembly profile's decision. A single roomy ledger
        # keeps the hard ceilings out of the way of the soft gate under test.
        self.estimate = Amount(20, 100)
        self.soft = BudgetSoftPolicy(enabled=True, tokens=1, kinds=("fixture.background",))
        self.ledger = BudgetLedger(self.runtime, BudgetPolicy(*(Amount(10**9, 10**12) for _ in range(5))), self.soft)

    def store(self, *, enabled=True, tokens=1):
        from companion_v2.configuration.owners import SparseConfigurationOwner
        owner = SparseConfigurationOwner(self.runtime)
        context = self.context
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE, context.role_binding.role,
                              bot_id=context.scope.bot_id)
        owner.write(target, SOFT_FIELDS,
                    changes={GROUP + ".enable_daily_token_soft_limit": enabled, GROUP + ".daily_token_soft_limit": tokens},
                    reset=(), expected_revision=owner.read(target, SOFT_FIELDS).revision, observed_at=NOW)

    def prepare(self, identifier, *, kind="fixture.background"):
        run = self.model_run(identifier, kind=kind)
        self.stage_plan(run)
        return run

    def attempt(self, run, call_id):
        return self.ledger.reserve(run, call_id=call_id, position=0,
                                   provider=self.providers[0].binding, amount=self.estimate)

    def spend(self, tokens):
        """Record a settled plugin call through the same ledger used in production."""
        identifier = "soft-spending-" + str(tokens)
        run = self.model_run(identifier, kind="fixture.read")
        self.stage_plan(run)
        call_id = "model-call-" + str(tokens)
        provider = self.providers[0].binding
        amount = Amount(tokens, 0)
        self.ledger.reserve(run, call_id=call_id, position=0, provider=provider, amount=amount)
        self.ledger.dispatch(run, call_id)
        self.ledger.settle(call_id, provider,
            ProviderResponse("generated", ModelDraft("settled plugin call", ()), amount,
                             "soft-spending-receipt-" + str(tokens)), observed_at=self.clock.now())

    async def test_a_reached_ceiling_defers_a_listed_background_kind(self):
        self.store(tokens=10**6)
        run = self.prepare("soft-deferred")
        self.spend(10**6 + 1)
        with self.assertRaises(TaskError) as error:
            self.attempt(run, "model-call-deferred")
        self.assertEqual(error.exception.code, "model_budget_soft_deferred")

    async def test_role_spending_is_not_counted_twice_in_the_installation_ceiling(self):
        self.store(tokens=1000)
        self.spend(600)
        self.attempt(self.prepare("soft-not-double-counted"), "single-charge")

    async def test_the_pending_reservation_must_fit_the_remaining_soft_ceiling(self):
        self.store(tokens=1000)
        self.spend(990)
        with self.assertRaises(TaskError) as error:
            self.attempt(self.prepare("soft-no-overrun"), "overrun-charge")
        self.assertEqual(error.exception.code, "model_budget_soft_deferred")

    async def test_a_disabled_ceiling_never_defers(self):
        self.store(enabled=False, tokens=1)
        self.attempt(self.prepare("soft-disabled"), "model-call-disabled")

    async def test_a_zero_ceiling_never_defers(self):
        self.store(enabled=True, tokens=0)
        self.attempt(self.prepare("soft-zero"), "model-call-zero")

    async def test_foreground_and_unlisted_kinds_ignore_the_ceiling(self):
        self.store(tokens=1)
        self.attempt(self.prepare("soft-foreground", kind="fixture.read"), "model-call-foreground")
        unlisted = self.prepare("soft-unlisted")
        self.ledger = BudgetLedger(self.runtime, self.ledger.policy,
                                   BudgetSoftPolicy(enabled=True, tokens=1, kinds=("role.journal.write",)))
        self.attempt(unlisted, "model-call-unlisted")

    async def test_a_deferred_call_reserves_nothing_at_all(self):
        self.store(tokens=1)
        run = self.prepare("soft-untouched")
        with self.assertRaises(TaskError):
            self.attempt(run, "model-call-untouched")
        self.assertEqual(self.call_rows(), ())
        self.assertEqual(self.accounts(), ())

    async def test_spending_from_another_day_or_scope_does_not_defer_today(self):
        self.store(tokens=10**9)
        for key in ("stale-day", "other-window"):
            with self.runtime.transaction() as connection:
                connection.execute("INSERT INTO model_budget_accounts VALUES (?, ?, 1000000, 1000000000, 0, 0, 5000, 0)",
                                   (key, self.ledger.policy_hash))
        # Only this day's installation and role accounts can trip the ceiling.
        self.attempt(self.prepare("soft-scoped"), "model-call-scoped")

    async def test_the_installation_ceiling_defers_before_any_reservation(self):
        self.store(tokens=10**6)
        run = self.prepare("soft-installation-only")
        self.spend(10**6 + 1)
        with self.assertRaises(TaskError) as error:
            self.attempt(run, "model-call-installation-only")
        self.assertEqual(error.exception.code, "model_budget_soft_deferred")

    async def test_the_hard_ceiling_still_denies_before_the_soft_ceiling(self):
        self.store(enabled=False, tokens=0)
        run = self.prepare("soft-hard-first")
        self.ledger = BudgetLedger(self.runtime, BudgetPolicy(*(Amount(0, 0) for _ in range(5))),
                                   BudgetSoftPolicy(enabled=False, tokens=0, kinds=("fixture.background",)))
        with self.assertRaises(TaskError) as error:
            self.attempt(run, "model-call-hard-first")
        self.assertEqual(error.exception.code, "model_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
