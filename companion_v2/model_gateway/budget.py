"""Atomic daily reservations and receipt-based settlement in the original accounts.

This is a trusted owner API. Public reads go through the gateway's original-task
authorization; model tools cannot release reservations or submit usage receipts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import Lane, ProviderBinding, TaskError, digest, encode, stamp
from companion_v2.execution.runner import TaskRun
from companion_v2.execution.service import TaskSupervisor
from companion_v2.storage.runtime import StorageRuntime

from .models import Amount, BudgetPolicy, ProviderResponse
from .failures import ModelFailure


# Optional background work that may be deferred once the day's soft ceiling is reached.
# Simulated life, journal writing, reflection and state maintenance stay available: the
# first two are the product, the last two are the maintenance pass that explains how the
# interactive quota was spent.
DEFAULT_SOFT_DEFER_KINDS = frozenset({
    "role.calendar.plan",
    "role.growth.progress",
    "conversation.group.review",
})

# The daily soft ceiling is an installation/role setting, matching V1's
# `enable_daily_token_soft_limit` + `daily_token_soft_limit`. It deliberately has no
# window layer: a single conversation must not be able to raise or lower the day's
# optional-work budget for everyone.
GROUP = "model.budget"
OWNER = "configuration"
SOFT_FIELDS = (
    FieldDefinition(GROUP + ".enable_daily_token_soft_limit", GROUP, GROUP, ValueKind.BOOLEAN, True,
                    layers=(ConfigLayer.INSTALLATION, ConfigLayer.ROLE),
                    apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER),
    FieldDefinition(GROUP + ".daily_token_soft_limit", GROUP, GROUP, ValueKind.INTEGER, 800_000,
                    layers=(ConfigLayer.INSTALLATION, ConfigLayer.ROLE),
                    apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER, minimum=0, maximum=10**12),
)


def configuration_fields():
    return SOFT_FIELDS


def effective_soft(runtime, context, fallback=None):
    """The configured soft ceiling for this installation/role, or the assembly default.

    A data root that has no stored value keeps whatever the host profile supplied,
    so an existing installation is never silently re-limited by this change.
    """
    role = context.role_binding.role
    target = ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE, role,
                          bot_id=context.scope.bot_id)
    snapshot = SparseConfigurationOwner(runtime).read(target, SOFT_FIELDS)
    enabled = snapshot.fields[GROUP + ".enable_daily_token_soft_limit"]
    tokens = snapshot.fields[GROUP + ".daily_token_soft_limit"]
    if not enabled.explicit and not tokens.explicit and fallback is not None:
        return fallback
    if type(enabled.value) is not bool or type(tokens.value) is not int:
        raise TaskError("model_budget_configuration", "the daily soft ceiling settings are invalid")
    return BudgetSoftPolicy(enabled=enabled.value, tokens=tokens.value,
                            kinds=fallback.kinds if fallback is not None else ())


@dataclass(frozen=True)
class BudgetSoftPolicy:
    """One installation-wide daily soft ceiling for optional background model work."""

    enabled: bool = False
    tokens: int = 0
    kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("a soft budget policy needs an explicit switch")
        if type(self.tokens) is not int or not 0 <= self.tokens <= 10**12:
            raise ValueError("the soft ceiling must be bounded integer tokens")
        if type(self.kinds) is not tuple or any(type(kind) is not str or not kind.strip() for kind in self.kinds):
            raise ValueError("deferred task kinds must be explicit identifiers")

    def is_deferrable(self, kind: str) -> bool:
        """Background work only: the caller decides the lane, this decides the kind."""
        selected = self.kinds or tuple(sorted(DEFAULT_SOFT_DEFER_KINDS))
        return kind in selected


class BudgetLedger:
    def __init__(self, runtime: StorageRuntime, policy: BudgetPolicy, soft: BudgetSoftPolicy | None = None):
        self.runtime = runtime
        self.policy = policy
        self.policy_hash = digest(policy)
        self.soft = soft if soft is not None else BudgetSoftPolicy()

    def _accounts(self, run: TaskRun, period: str):
        context = run.task.spec.context
        scope = context.scope
        installation = [scope.installation_id]
        bot = installation + [scope.bot_id]
        role = bot + [asdict(context.role_binding.role)]
        layers = [("installation", installation), ("bot", bot), ("role", role),
                  ("window", [scope.document()])]
        if run.supervisor.registrations[run.task.spec.kind].definition.lane is Lane.BACKGROUND:
            layers.append(("background", installation))
        return tuple((digest([layer, address, period]), getattr(self.policy, layer)) for layer, address in layers)

    def _soft_refusal(self, run: TaskRun, period: str, amount: Amount):
        """The configured account that defers this call, or None.

        Only the installation and role accounts of the reservation's local day are
        read, so no window can widen the ceiling, and a deferred call writes no
        reservation at all. A ceiling below what one call would reserve defers
        immediately, which is how a mixed batch keeps its optional share bounded.

        The effective settings are read here rather than pinned, because deferral
        only decides whether optional work starts: it never mutates a pinned daily
        account, so changing it mid-day cannot invalidate an active ceiling.
        """
        settings = effective_soft(self.runtime, run.task.spec.context, self.soft)
        if settings is None or not settings.enabled or settings.tokens <= 0:
            return None
        definition = run.supervisor.registrations[run.task.spec.kind].definition
        kind = run.task.spec.kind
        if definition.lane is not Lane.BACKGROUND or not settings.is_deferrable(kind):
            return None
        context = run.task.spec.context
        scope = context.scope
        keys = (digest(["installation", [scope.installation_id], period]),
                digest(["role", [scope.installation_id, scope.bot_id, asdict(context.role_binding.role)], period]))
        used = 0
        for key in keys:
            row = self.runtime.read_one(
                "SELECT spent_tokens, held_tokens FROM model_budget_accounts WHERE account_key = ?", (key,))
            if row:
                used += row["spent_tokens"] + row["held_tokens"]
        if used >= settings.tokens or settings.tokens < amount.tokens:
            return keys[0]
        return None

    def reserve(self, run: TaskRun, *, call_id: str, position: int,
                provider: ProviderBinding, amount: Amount):
        if self.runtime is not run.supervisor.runtime or not isinstance(amount, Amount):
            raise ValueError("model reservation must share the task runtime and use explicit amounts")
        with self.runtime.transaction() as connection:
            run.validate()
            plan = connection.execute("SELECT created_at FROM model_requests WHERE task_id = ?", (run.task.task_id,)).fetchone()
            if plan is None:
                raise TaskError("model_plan_missing", "reserve only against the original adopted plan")
            if connection.execute("SELECT 1 FROM model_calls WHERE task_id = ? AND position = ?",
                                  (run.task.task_id, position)).fetchone():
                raise TaskError("model_call_already_reserved", "an original call cannot be repeated")
            period = datetime.fromisoformat(plan["created_at"]).date().isoformat()
            accounts = self._accounts(run, period)
            # Hard ceilings are checked first: software deferral decides whether optional
            # work should run, never whether the body may answer at all.
            for key, ceiling in accounts:
                connection.execute("INSERT OR IGNORE INTO model_budget_accounts VALUES (?, ?, ?, ?, 0, 0, 0, 0)",
                                   (key, self.policy_hash, ceiling.tokens, ceiling.cost_microusd))
                account = connection.execute("SELECT * FROM model_budget_accounts WHERE account_key = ?", (key,)).fetchone()
                if account["policy_hash"] != self.policy_hash:
                    raise TaskError("model_budget_policy_changed", "active daily budget policy requires an explicit migration")
                if (account["spent_tokens"] + account["held_tokens"] + amount.tokens > account["token_limit"]
                        or account["spent_cost"] + account["held_cost"] + amount.cost_microusd > account["cost_limit"]):
                    raise TaskError("model_budget_exhausted", "model reservation exceeds an original scope budget")
            if self._soft_refusal(run, period, amount) is not None:
                raise TaskError("model_budget_soft_deferred",
                                "the daily soft ceiling defers this optional background call")
            connection.execute("""INSERT INTO model_calls
                (call_id, task_id, attempt_id, position, state, provider_json, reserved_tokens, reserved_cost)
                VALUES (?, ?, ?, ?, 'reserved', ?, ?, ?)""",
                (call_id, run.task.task_id, run.claim.attempt_id, position, encode(provider), amount.tokens, amount.cost_microusd))
            for key, _ in accounts:
                connection.execute("UPDATE model_budget_accounts SET held_tokens = held_tokens + ?, held_cost = held_cost + ? WHERE account_key = ?",
                                   (amount.tokens, amount.cost_microusd, key))
                connection.execute("INSERT INTO model_call_accounts VALUES (?, ?)", (call_id, key))

    def dispatch(self, run: TaskRun, call_id: str):
        with self.runtime.transaction() as connection:
            run.validate()
            changed = connection.execute("""UPDATE model_calls SET state = 'dispatched', started_at = ?
                WHERE call_id = ? AND attempt_id = ? AND state = 'reserved'""",
                (stamp(run.supervisor.now()), call_id, run.claim.attempt_id))
            if changed.rowcount != 1:
                raise TaskError("model_dispatch_conflict", "only an unstarted original reservation may dispatch")

    def settle(self, call_id: str, provider: ProviderBinding, response: ProviderResponse, *,
               observed_at: datetime, latency_ms: float | None = None):
        if latency_ms is not None and (type(latency_ms) not in (int, float)
                                      or not math.isfinite(latency_ms) or latency_ms < 0):
            raise ValueError("provider latency must be measured and finite")
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT * FROM model_calls WHERE call_id = ?", (call_id,)).fetchone()
            if row is None or row["provider_json"] != encode(provider):
                raise TaskError("model_receipt_mismatch", "usage receipt belongs to another provider binding")
            if row["state"] == "reserved" and response.status != "not_started":
                raise TaskError("model_receipt_mismatch", "undispatched work cannot report provider execution")
            if ((row["state"] == "not_started" and response.status == "generated")
                    or (row["state"] in ("generated", "discarded") and response.status == "not_started")):
                raise TaskError("model_processing_conflict", "provider processing receipts contradict each other")
            usage = response.usage
            if row["actual_tokens"] is not None:
                if (usage is not None and (row["actual_tokens"], row["actual_cost"], row["receipt_ref"]) !=
                        (usage.tokens, usage.cost_microusd, response.receipt_ref)):
                    raise TaskError("model_usage_conflict", "settled usage is immutable")
                if usage is not None and any(
                        row[name] is not None and getattr(usage, name) is not None
                        and row[name] != getattr(usage, name)
                        for name in ("input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens")):
                    raise TaskError("model_usage_conflict", "settled usage details are immutable")
            elif usage is not None:
                accounts = connection.execute("SELECT account_key FROM model_call_accounts WHERE call_id = ?", (call_id,)).fetchall()
                for account in accounts:
                    connection.execute("""UPDATE model_budget_accounts SET held_tokens = held_tokens - ?,
                        held_cost = held_cost - ?, spent_tokens = spent_tokens + ?, spent_cost = spent_cost + ? WHERE account_key = ?""",
                        (row["reserved_tokens"], row["reserved_cost"], usage.tokens, usage.cost_microusd, account["account_key"]))
            # A late accounting receipt cannot resurrect a discarded draft or replay a call.
            state = row["state"] if row["state"] in ("generated", "discarded", "not_started") else response.status
            connection.execute("""UPDATE model_calls SET state = ?, actual_tokens = ?, actual_cost = ?,
                input_tokens = COALESCE(input_tokens, ?), cached_input_tokens = COALESCE(cached_input_tokens, ?),
                cache_creation_tokens = COALESCE(cache_creation_tokens, ?), output_tokens = COALESCE(output_tokens, ?),
                receipt_ref = ?, finished_at = COALESCE(finished_at, ?), latency_ms = COALESCE(latency_ms, ?)
                WHERE call_id = ?""", (state, usage.tokens if usage else row["actual_tokens"],
                usage.cost_microusd if usage else row["actual_cost"],
                usage.input_tokens if usage else None, usage.cached_input_tokens if usage else None,
                usage.cache_creation_tokens if usage else None, usage.output_tokens if usage else None,
                row["receipt_ref"] if row["actual_tokens"] is not None else response.receipt_ref,
                stamp(observed_at), latency_ms, call_id))
            if response.failure is not None:
                self._record_failure(connection, call_id, response.failure, observed_at)
            return row["actual_tokens"] is not None or usage is not None

    @staticmethod
    def _record_failure(connection, call_id: str, failure: ModelFailure, observed_at: datetime):
        # Keep the first observed classification, including across late accounting receipts.
        connection.execute("""INSERT INTO model_call_failures(call_id, code, observed_at) VALUES (?, ?, ?)
            ON CONFLICT(call_id) DO NOTHING""", (call_id, failure.value, stamp(observed_at)))

    def discard(self, call_id: str, *, failure: ModelFailure | None = None, observed_at: datetime | None = None):
        if failure is not None and (not isinstance(failure, ModelFailure) or observed_at is None):
            raise ValueError("discard diagnostics require a fixed classification and observation time")
        with self.runtime.transaction() as connection:
            changed = connection.execute("UPDATE model_calls SET state = 'discarded' WHERE call_id = ? AND state = 'generated'", (call_id,))
            if changed.rowcount and failure is not None:
                self._record_failure(connection, call_id, failure, observed_at)

    def reconcile_usage(self, call_id: str, provider: ProviderBinding, usage: Amount, *, receipt_ref: str, observed_at: datetime):
        """Trusted adapter accounting only, including after revocation or restart."""
        self.settle(call_id, provider, ProviderResponse("unknown", usage=usage, receipt_ref=receipt_ref), observed_at=observed_at)

    def recover(self, supervisor: TaskSupervisor) -> int:
        if supervisor.runtime is not self.runtime:
            raise ValueError("recovery requires the current task runtime")
        with self.runtime.transaction() as connection:
            controller = connection.execute("SELECT generation FROM task_supervisor WHERE singleton = 1").fetchone()
            if controller is None or controller["generation"] != supervisor.generation:
                raise TaskError("supervisor_fenced", "only the current controller can recover model reservations")
            rows = connection.execute("""SELECT c.* FROM model_calls c JOIN execution_attempts a USING(attempt_id)
                WHERE a.generation < ? AND c.state IN ('reserved', 'dispatched')""", (supervisor.generation,)).fetchall()
            for row in rows:
                response = (ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref="local:never-dispatched")
                            if row["state"] == "reserved" else ProviderResponse("unknown", failure=ModelFailure.RECOVERY))
                self.settle(row["call_id"], ProviderBinding(**json.loads(row["provider_json"])), response,
                            observed_at=supervisor.now())
            return len(rows)
