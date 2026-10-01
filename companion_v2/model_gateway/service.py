"""A local asynchronous gateway that never retries an unknown model invocation."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from time import perf_counter
from uuid import uuid4

from companion_v2.conversation.foreground import PromptRequest
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.execution.runner import TaskRun
from companion_v2.execution.service import TaskSupervisor, outcome
from companion_v2.sources.repositories import SourceRepository

from .budget import BudgetLedger
from .failures import ModelFailure
from .models import MAX_TOOL_CATALOG, Amount, ModelCompletion, ProviderResponse, ToolSpec
from .routing import ModelRouter


class LocalModelGateway:
    def __init__(self, router: ModelRouter, ledger: BudgetLedger, tasks: TaskSupervisor):
        if router.configuration.runtime is not tasks.runtime or ledger.runtime is not tasks.runtime:
            raise ValueError("gateway components must share the original runtime")
        self.router = router
        self.ledger = ledger
        self.tasks = tasks
        self.runtime = tasks.runtime

    async def generate(self, run: TaskRun, request: PromptRequest) -> ModelCompletion:
        return await self.open_session(run, request).generate(request)

    def open_session(self, run: TaskRun, request: PromptRequest, *, tools: tuple[ToolSpec, ...] = ()):
        if run.supervisor is not self.tasks:
            raise ValueError("gateway must execute against its original supervisor")
        if len(tools) > MAX_TOOL_CATALOG or len({tool.action for tool in tools}) != len(tools):
            raise ValueError("tool registration requires a bounded unique catalog")
        with self.runtime.transaction() as connection:
            run.validate()
            if connection.execute("SELECT 1 FROM model_requests WHERE task_id = ?", (run.task.task_id,)).fetchone():
                raise TaskError("model_request_already_started", "inspect the original model calls instead of regenerating")
            plan = self.router.resolve(run, request)
            if tools:
                if any("tools" not in provider.capabilities for provider in plan.providers):
                    raise TaskError("model_capability_mismatch", "tool continuation requires tool-capable providers")
                plan = replace(plan, audit={**plan.audit, "tool_catalog_hash": digest(tools),
                                          "tool_actions": [tool.action for tool in tools]})
            self.router.adopt(run, plan)
            connection.execute("INSERT INTO model_requests VALUES (?, ?, ?, ?)",
                               (run.task.task_id, digest(request), encode(plan.audit), stamp(self.tasks.now())))
        return ModelSession(self, run, plan, tools)

    async def _generate(self, run, plan, envelope, round_no):
        def before_dispatch():
            run.validate()
            self.router.validate_plan(plan)
            # Recheck explicit original references in the cached envelope, too:
            # task input validation need not include later tool materials.
            sources = SourceRepository(self.runtime)
            references = {material.source for material in envelope.original.context.materials
                          if material.source is not None}
            reference = getattr(envelope.original.event, "source", None)
            if reference is not None:
                references.add(reference)
            for reference in references:
                require(sources.validate_reference(reference, observed_at=self.tasks.now()))

        for provider_position, provider in enumerate(plan.providers):
            provider_envelope = replace(envelope,
                model_override=envelope.model_override if provider_position == 0 else "",
                provider_capabilities=provider.capabilities)
            position = round_no * 2 + provider_position
            before_dispatch()
            try:
                amount = provider.reserve(provider_envelope)
            except Exception as error:
                raise TaskError("model_estimation_failed", "local reservation estimation failed; details omitted") from error
            if not isinstance(amount, Amount):
                raise TaskError("model_estimation_failed", "adapter did not provide a reservation ceiling")
            if amount.tokens < envelope.max_output_tokens:
                raise TaskError("model_estimation_failed", "reservation must cover the declared output ceiling")
            call_id = "model-call-" + uuid4().hex
            with self.runtime.transaction():
                self.router.validate_plan(plan)
                self.ledger.reserve(run, call_id=call_id, position=position, provider=provider.binding, amount=amount)
                self.ledger.dispatch(run, call_id)
            started = perf_counter()
            try:
                response = await asyncio.wait_for(
                    provider.generate(replace(provider_envelope, before_dispatch=before_dispatch)),
                    timeout=plan.audit["timeout_seconds"])
                if not isinstance(response, ProviderResponse):
                    raise TypeError("provider returned no trusted outcome")
            except TimeoutError as error:
                self.ledger.settle(call_id, provider.binding, ProviderResponse("unknown", failure=ModelFailure.TIMEOUT),
                                   observed_at=self.tasks.now(), latency_ms=(perf_counter() - started) * 1000)
                raise TaskError("model_timeout", "provider wait timed out; original result is unknown") from error
            except asyncio.CancelledError:
                self.ledger.settle(call_id, provider.binding, ProviderResponse("unknown", failure=ModelFailure.INTERRUPTED),
                                   observed_at=self.tasks.now(), latency_ms=(perf_counter() - started) * 1000)
                raise
            except Exception as error:
                self.ledger.settle(call_id, provider.binding, ProviderResponse("unknown", failure=ModelFailure.ADAPTER),
                                   observed_at=self.tasks.now(), latency_ms=(perf_counter() - started) * 1000)
                raise TaskError("model_transport_failed", "local provider failed; private details omitted") from error
            usage_known = self.ledger.settle(call_id, provider.binding, response, observed_at=self.tasks.now(),
                                            latency_ms=(perf_counter() - started) * 1000)
            try:
                with self.runtime.read_snapshot():
                    before_dispatch()
            except TaskError:
                self.ledger.discard(call_id, failure=ModelFailure.GATEWAY_RECHECK, observed_at=self.tasks.now())
                raise
            if response.status == "generated":
                if (response.captured_output is not None
                        and response.captured_output.finish_reason == "refusal"
                        and (envelope.original.output_format != "memory_reflection"
                             or plan.audit["fallback_on_refusal"])):
                    self.ledger.discard(call_id, failure=ModelFailure.REFUSAL, observed_at=self.tasks.now())
                    if plan.audit["fallback_on_refusal"] and provider_position + 1 < len(plan.providers):
                        continue
                    raise TaskError("model_refused", "provider explicitly refused the request")
                if response.captured_output is not None and envelope.original.output_format != "memory_reflection":
                    self.ledger.discard(call_id)
                    raise TaskError("model_capture_unavailable", "unvalidated output requires its private memory owner")
                if response.tool_calls and not envelope.tools:
                    self.ledger.discard(call_id)
                    raise TaskError("model_tools_unavailable", "no tool dispatch is allowed for this model round")
                with self.runtime.transaction() as connection:
                    connection.execute("""UPDATE model_rounds SET state = ?, call_id = ?, tool_calls_json = ?
                        WHERE task_id = ? AND round_no = ?""", (
                        "tools" if response.tool_calls else "final", call_id, encode(response.tool_calls),
                        run.task.task_id, round_no))
                return ModelCompletion(call_id, response.draft, usage_known, response.tool_calls, response.captured_output)
            if response.status != "not_started":
                raise TaskError("model_usage_unknown", "provider processing is unknown; no fallback was dispatched")
        raise TaskError("model_not_started", "configured providers confirmed they did not process the request")

    @outcome
    def observe(self, context: TaskContext, task_id: str) -> dict:
        with self.runtime.read_snapshot():
            require(self.tasks.read(context, task_id))
            plan = self.runtime.read_one("SELECT plan_json FROM model_requests WHERE task_id = ?", (task_id,))
            if plan is None:
                return {"state": "not_observed", "transport": "local_test_adapter", "calls": []}
            audit = json.loads(plan["plan_json"])
            rows = self.runtime.read_all("""SELECT c.*, f.code AS failure_code, f.observed_at AS failure_observed_at
                FROM model_calls c LEFT JOIN model_call_failures f USING(call_id)
                WHERE c.task_id = ? ORDER BY c.position""", (task_id,))
            return {"state": "observed", "transport": audit["transport"], "plan": audit,
                    "calls": [{"position": row["position"], "round": row["position"] // 2,
                               "provider_position": row["position"] % 2, "state": row["state"],
                               "provider": json.loads(row["provider_json"]),
                               "reserved_tokens": row["reserved_tokens"], "reserved_cost_microusd": row["reserved_cost"],
                               "actual_tokens": row["actual_tokens"], "actual_cost_microusd": row["actual_cost"],
                               "input_tokens": row["input_tokens"], "cached_input_tokens": row["cached_input_tokens"],
                               "cache_creation_tokens": row["cache_creation_tokens"], "output_tokens": row["output_tokens"],
                               "usage_state": "unknown" if row["actual_tokens"] is None else "settled",
                               "over_reservation": None if row["actual_tokens"] is None else (
                                   row["actual_tokens"] > row["reserved_tokens"] or row["actual_cost"] > row["reserved_cost"]),
                               "provider_latency_ms": row["latency_ms"],
                               "failure": None if row["failure_code"] is None else {
                                   **ModelFailure(row["failure_code"]).document(),
                                   "observed_at": row["failure_observed_at"]},
                               "latency_basis": "local_wait_until_receipt_or_interruption"} for row in rows]}


class ModelSession:
    """One in-memory continuation controller; a restart cannot reopen its plan."""

    def __init__(self, gateway, run, plan, tools):
        self.gateway = gateway
        self.run = run
        self.plan = plan
        self.tools = tools
        self.round_no = 0
        self.history = ()
        self.pending = ()
        self.closed = False
        self.busy = False

    async def generate(self, request, *, history=(), owner_refresh=None, media_refresh=None):
        if self.closed or self.busy or self.round_no > 8:
            raise TaskError("model_session_closed", "original model session cannot generate again")
        original = self.plan.envelope.original
        if (request.event != original.event or request.role_binding != original.role_binding or
                request.audios != original.audios or request.videos != original.videos or
                request.role_instruction != original.role_instruction or
                request.context.deferred != original.context.deferred or
                request.context.unavailable != original.context.unavailable or
                request.output_format != original.output_format or request.response_format != original.response_format or
                request.streaming != original.streaming or
                request.response_schema_json != original.response_schema_json or
                not request.instruction.startswith(original.instruction)):
            reasons = [name for name, pair in (("event", (request.event, original.event)),
                ("role_binding", (request.role_binding, original.role_binding)),
                ("audios", (request.audios, original.audios)), ("videos", (request.videos, original.videos)),
                ("role_instruction", (request.role_instruction, original.role_instruction)),
                ("deferred", (request.context.deferred, original.context.deferred)),
                ("unavailable", (request.context.unavailable, original.context.unavailable)),
                ("output_format", (request.output_format, original.output_format)),
                ("response_format", (request.response_format, original.response_format)),
                ("streaming", (request.streaming, original.streaming)),
                ("schema", (request.response_schema_json, original.response_schema_json)))
                if pair[0] != pair[1]]
            if not request.instruction.startswith(original.instruction):
                raise TaskError("model_context_mismatch", "continuation must preserve the original role and inputs")
        if (request.images != original.images or request.reply_images != original.reply_images):
            if media_refresh is None or not media_refresh(original, request):
                raise TaskError("model_context_mismatch", "new images require their original authorized provider receipt")
            if request.images and any("image" not in provider.capabilities for provider in self.plan.providers):
                raise TaskError("model_capability_mismatch", "generated images require image-capable continuation providers")
        if not isinstance(history, tuple) or len(history) < len(self.history) or tuple(item.call for item in history[len(self.history):]) != self.pending:
            raise TaskError("model_tool_results_missing", "every requested tool needs its ordered original result")
        changed = (request.context.materials[:len(original.context.materials)] != original.context.materials
                   or history[:len(self.history)] != self.history)
        if changed and (owner_refresh is None or not owner_refresh(original, request, self.history, history)):
            raise TaskError("model_context_mismatch", "changed owner material requires its original authorized receipt")
        self.busy = True
        try:
            envelope = replace(self.plan.envelope, original=request, tools=self.tools if self.round_no < 8 else (),
                               tool_history=history)
            with self.gateway.runtime.transaction() as connection:
                self.run.validate()
                self.gateway.router.validate_plan(self.plan)
                connection.execute("""INSERT INTO model_rounds
                    (task_id, round_no, attempt_id, request_hash, state) VALUES (?, ?, ?, ?, 'started')""",
                    (self.run.task.task_id, self.round_no, self.run.claim.attempt_id, digest(envelope)))
            completion = await self.gateway._generate(self.run, self.plan, envelope, self.round_no)
            self.history = history
            self.pending = completion.tool_calls
            self.round_no += 1
            self.closed = completion.draft is not None or completion.captured_output is not None
            return completion
        except BaseException:
            self.closed = True
            raise
        finally:
            self.busy = False
