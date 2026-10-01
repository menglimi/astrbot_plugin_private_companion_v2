"""Background style-learning runs over the role's own confirmed writing.

A run reads the role's confirmed-delivered replies in one exact conversation --
a private window or one group -- and asks the original role model what *form*
patterns it notices. The result is a candidate set: nothing changes until an
operator adopts an individual signal. Adopted signals are reversible and are
never treated as conclusions about identity, personality or stable preference.

The window, batch size, minimum sample count, per-sample length and scan
interval come from the registered ``expression.learning`` settings, so a
distribution that starved one conversation no longer needs a code change.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json

from companion_v2.conversation.foreground import (BackgroundPromptTrigger, PromptMaterial, PromptRequest,
    SealedForegroundContext)
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskContext, TaskDefinition,
    TaskError, TaskRegistration, TaskResult, TaskSpec, digest, encode, require, stamp)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, ScopeKind, VersionRef
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from . import learning
from .configuration import read_settings
from .style_evidence import MAX_WINDOW_HOURS, sample_document, sample_handles

KIND = "role.expression.learn"
OWNER = "role.expression.learn"
CURSOR_PREFIX = "role.expression.learn.cursor.v1:"
PROMPT = learning.INSTRUCTION + (
    " 输入是本角色自己已确认送达的回复样本。只描述可从这些样本直接观察到的形式特征，"
    "样本不足或某个维度没有稳定迹象时就不要为它输出条目。"
)


def expression_learning_profile(provider, *, max_output_tokens=1024):
    return ModelTaskProfile(KIND, Lane.BACKGROUND, provider,
        "依据角色自己已确认送达的表达样本，提出待审阅的表达形式观察候选。",
        max_output_tokens=max_output_tokens)


def parse_output(raw, *, allowed_evidence):
    """Bridge the candidate contract onto this service's error vocabulary."""
    try:
        return learning.parse_output(raw, allowed_evidence=allowed_evidence)
    except ValueError as error:
        raise TaskError("expression_output_invalid", str(error) or "expression output is invalid") from error


class ExpressionStyleService:
    page_size = 16

    def __init__(self, runtime, *, window_hours=168):
        self.runtime = runtime
        self.operations = OperationRepository(runtime)
        self.window_hours = window_hours
        self.pending, self.committed, self.workers, self.results = {}, set(), {}, {}
        self.next_checks = {}
        self.cursor = 0
        self.closed = False
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, "role.expression.read",
            Lane.BACKGROUND, side_effect=SideEffect.LOCAL, binding=ProviderBinding(OWNER, "local", "1", "style-1"),
            timeout_seconds=180, max_attempts=1, concurrency=1), self.validate),)

    def attach(self, app):
        self.app, self.tasks, self.gateway = app, app.tasks, app.gateway
        if app.expression_samples is None:
            raise TaskError("expression_owner_unavailable", "the conversation owner is not attached")
        self.samples = app.expression_samples
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate,
                                      waiting=app.background_waiting)

    @staticmethod
    def identifier(context, operation_id):
        return "expression-learn:" + digest([context.scope, context.role_binding.role, operation_id])

    def _policy(self, context, at):
        """The effective bounds for this exact window, defaulted when unreadable."""
        return read_settings(self.runtime, context)

    def _bound(self, context, instruction):
        """Accept a live private binding or re-derive the same group turn."""
        bound = self.app.state_maintenance.bindings.get(context.key)
        if bound is not None:
            if bound[:2] != (context, instruction):
                raise TaskError("expression_binding_changed", "the original role is no longer bound")
            return bound[2]
        row = self.runtime.read_one("SELECT context_json FROM conversation_batches WHERE origin_key = ?",
                                    (context.key,))
        if row is None or TaskContext.restore(json.loads(row["context_json"])) != context:
            raise TaskError("expression_binding_changed", "the original conversation is no longer current")
        current = self.tasks.identity.resolve_role(context.scope, observed_at=self.tasks.now())
        if not current.is_success or current.unwrap() != context.role_binding:
            raise TaskError("expression_binding_changed", "the original role is no longer bound")
        return None

    async def guard(self, context, instruction):
        check = self._bound(context, instruction)
        if check is not None:
            await check(context.scope, context.role_binding, instruction)

    def prepare(self, context, instruction, at):
        self.app.require_running()
        self._bound(context, instruction)
        policy = self._policy(context, at)
        samples = self.samples.collect(context, at, window_hours=min(policy.window_hours, MAX_WINDOW_HOURS),
                                       sample_limit=policy.sample_limit, sample_chars=policy.sample_chars)
        if len(samples.samples) < policy.min_samples:
            return None
        return {"context": context, "instruction": instruction, "at": at, "policy": policy,
                "samples": samples, "material_hash": samples.material_hash,
                "catalogue": self.samples.catalogue(samples),
                "sample_document": sample_document(samples)}

    @outcome
    def validate(self, spec, at):
        self.app.require_running()
        job = self.pending.get(spec.task_id)
        if job is None or job["context"] != spec.context or job["request_key"] != spec.request_ref:
            raise TaskError("expression_job_unavailable", "original style inputs are unavailable")
        self._bound(spec.context, job["instruction"])
        policy = job["policy"]
        samples = self.samples.collect(spec.context, at, window_hours=min(policy.window_hours, MAX_WINDOW_HOURS),
                                       sample_limit=policy.sample_limit, sample_chars=policy.sample_chars)
        if samples.material_hash != job["material_hash"]:
            raise TaskError("expression_sample_changed", "sampled writing changed or was withdrawn")
        return True

    async def run(self, context, instruction):
        if self.closed:
            raise TaskError("expression_closed", "style worker is stopped")
        if KIND not in self.gateway.router.profiles:
            raise TaskError("model_task_unregistered", "style learning needs its background profile")
        await self.guard(context, instruction)
        identifier = self.identifier(context, context.key)
        if self.operations.get(identifier).is_success:
            return {"state": "already_attempted", "task_id": identifier}
        job = self.prepare(context, instruction, self.tasks.now())
        if job is None:
            return {"state": "insufficient_samples", "task_id": identifier}
        request_key = digest([job["material_hash"], job["sample_document"]])
        with self.runtime.transaction():
            reservation = require(self.operations.reserve(OperationRef(identifier, OWNER, context.scope,
                VersionRef(identifier, 1), identifier),
                parameter_hash=digest([context.key, request_key]), observed_at=job["at"]))
            if reservation.replayed:
                return {"state": "already_attempted", "task_id": identifier}
            self.pending[identifier] = {**job, "request_key": request_key}
            try:
                require(self.tasks.submit(TaskSpec(identifier, context, KIND, request_key, identifier,
                    job["at"], job["at"] + timedelta(minutes=3))))
            except BaseException:
                self.pending.pop(identifier, None)
                raise
        try:
            result = require(await self.runner.run(context, identifier))
            if result.task.state in ("created", "retry_scheduled"):
                require(self.tasks.discard_queued(identifier, reason="owner_unavailable"))
            report = {"state": result.task.state, "task_id": identifier, "code": result.task.reason}
            self.results[context.key] = report
            return report
        finally:
            self.pending.pop(identifier, None)
            self.committed.discard(identifier)

    async def generate(self, run):
        job = self.pending[run.task.task_id]
        context = job["context"]
        await self.guard(context, job["instruction"])
        run.validate()
        material = {"sample_window": job["sample_document"], "samples": job["catalogue"]}
        request = PromptRequest(BackgroundPromptTrigger(job["request_key"], context.actor.principal,
            context.scope, job["at"]), job["instruction"], SealedForegroundContext(
                (PromptMaterial(OWNER, "role_expression_samples", encode(material)),), (), ()),
            PROMPT, context.role_binding, output_format="role_expression_learning")
        completion = await self.gateway.generate(run, request)
        try:
            if completion.draft is None:
                raise TaskError("expression_output_invalid", "style learning needs a complete response")
            output = parse_output(completion.draft.text,
                allowed_evidence=sample_handles(job["samples"]))
            await self.guard(context, job["instruction"])
            with self.runtime.transaction() as connection:
                run.validate()
                run.begin_effect()
                owner_key = digest(self.samples.role_owner(context))
                run_id = "expression-run:" + digest([context.key, job["request_key"]])
                at = stamp(self.tasks.now())
                connection.execute("""INSERT INTO expression_style_runs VALUES
                    (?, ?, ?, ?, ?, ?, 'pending', ?, NULL)""",
                    (run_id, owner_key, digest(context.scope), encode(job["sample_document"]),
                     job["material_hash"], output.summary, at))
                for ordinal, item in enumerate(output.signals):
                    connection.execute("""INSERT INTO expression_style_signals VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL, ?)""",
                        (run_id + ":signal:" + str(ordinal), run_id, owner_key, digest(context.scope),
                         item.dimension, item.observation, item.proposal, item.confidence,
                         encode(sorted(item.evidence_handles)), at, ordinal))
                require(self.operations.transition(run.task.task_id, expected_state=OperationState.ACCEPTED,
                    next_state=OperationState.COMPLETED, observed_at=self.tasks.now()))
                self.committed.add(run.task.task_id)
                run.record_operation(run.task.task_id)
            self.app.notify()
            return TaskResult("succeeded", effect="committed", result_ref=run_id,
                receipt_ref=run.task.task_id, operation_id=run.task.task_id)
        except BaseException:
            if run.task.task_id not in self.committed:
                self.gateway.ledger.discard(completion.call_id)
            raise

    def _cursor(self, context):
        key = CURSOR_PREFIX + digest([self.samples.role_owner(context), context.scope])
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
        if row is None:
            return key, None
        value = json.loads(row["value"])
        if type(value) is not dict or set(value) != {"closed_at"} or type(value["closed_at"]) is not str:
            raise TaskError("expression_cursor_invalid", "style-learning cursor is invalid")
        try:
            closed_at = datetime.fromisoformat(value["closed_at"])
        except ValueError:
            raise TaskError("expression_cursor_invalid", "style-learning cursor is invalid") from None
        return key, closed_at

    def due(self, context, at, *, scan_minutes=None):
        _, closed_at = self._cursor(context)
        if closed_at is None:
            return True
        minutes = scan_minutes if type(scan_minutes) is int and scan_minutes >= 1 else 1440
        return at - closed_at >= timedelta(minutes=minutes)

    def _advance_cursor(self, key, closed_at):
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, encode({"closed_at": stamp(closed_at)})))

    def _group_candidates(self, at, limit=8):
        """Reconstruct one context per group that wrote inside the widest window.

        Group turns are not part of the state bindings, so the batch ledger is the
        only honest source: the newest batch of each group origin carries the exact
        collective context and role binding that produced those replies.
        """
        rows = self.runtime.read_all("""SELECT b.origin_key, b.context_json, MAX(b.rowid) AS newest
            FROM conversation_batches b
            WHERE json_extract(b.context_json, '$.scope.kind') = ?
            GROUP BY b.origin_key ORDER BY newest DESC LIMIT ?""", (ScopeKind.GROUP.value, limit))
        candidates = []
        for row in rows:
            try:
                context = TaskContext.restore(json.loads(row["context_json"]))
            except (TypeError, ValueError, KeyError):
                continue
            if context.scope.kind is ScopeKind.GROUP and context.key == row["origin_key"]:
                candidates.append(context)
        return tuple(candidates)

    def _scan(self, context, instruction, at):
        """Prepare one due window; returns True when a worker was started."""
        if self.next_checks.get(context.key, at) > at:
            return False
        self.next_checks[context.key] = at + timedelta(seconds=60)
        policy = self._policy(context, at)
        if not self.due(context, at, scan_minutes=policy.scan_interval_minutes):
            return False
        if self.prepare(context, instruction, at) is None:
            return False
        key, _ = self._cursor(context)
        self._advance_cursor(key, at)
        self.workers[context.key] = asyncio.create_task(
            self.run(context, instruction), name="companion:expression-learn")
        self.workers[context.key].add_done_callback(lambda done: self.app.notify())
        return True

    def advance(self):
        if self.closed:
            return
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                del self.workers[key]
                if not worker.cancelled():
                    error = worker.exception()
                    if error:
                        self.results[key] = {"state": "failed",
                                             "code": getattr(error, "code", "expression_learn_failed")}
        if self.workers or KIND not in self.gateway.router.profiles:
            return
        bindings = tuple(self.app.state_maintenance.bindings.values())
        at = self.tasks.now()
        group_contexts = self._group_candidates(at)
        if not bindings and not group_contexts:
            self.next_checks.clear()
            return
        for _ in range(min(16, len(bindings) + len(group_contexts))):
            if bindings:
                context, instruction, _ = bindings[self.cursor % len(bindings)]
            else:
                context, instruction = group_contexts[self.cursor % len(group_contexts)]
            self.cursor += 1
            at = self.tasks.now()
            if context.scope.kind is not ScopeKind.PRIVATE:
                continue
            try:
                if self._scan(context, instruction, at):
                    return
            except TaskError as error:
                self.results[context.key] = {"state": "blocked", "code": error.code}
        # Group learning is opt-in per group and runs after the private queue.
        for context in group_contexts:
            at = self.tasks.now()
            try:
                instruction = self._group_instruction(context, at)
                if instruction is None:
                    continue
                if self._scan(context, instruction, at):
                    return
            except TaskError as error:
                self.results[context.key] = {"state": "blocked", "code": error.code}

    def _group_instruction(self, context, at):
        """A group run needs its own switch and the exact current role prompt."""
        policy = self._policy(context, at)
        if not policy.group_learning_enabled:
            return None
        row = self.runtime.read_one("""SELECT b.role_instruction FROM conversation_batches b
            WHERE b.origin_key = ? ORDER BY b.rowid DESC LIMIT 1""", (context.key,))
        if row is None or not row["role_instruction"].strip():
            return None
        current = self.tasks.identity.resolve_role(context.scope, observed_at=at)
        if not current.is_success or current.unwrap() != context.role_binding:
            return None
        return row["role_instruction"]

    def cancel_running(self):
        for worker in self.workers.values():
            worker.cancel()

    @property
    def active_handles(self):
        return self.runner.active_handles + tuple("expression-learn:" + key for key, worker in
            self.workers.items() if not worker.done())

    async def close(self):
        self.closed = True
        self.cancel_running()
        await self.runner.close()
        if self.workers:
            await asyncio.wait(tuple(self.workers.values()), timeout=0.25)
