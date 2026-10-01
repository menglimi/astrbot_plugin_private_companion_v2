"""Background self-review runs that propose reviewable guidance for one role.

A run inspects only the role's own observable behaviour inside one exact private
conversation -- confirmed replies and completed life/journal receipts -- and asks
the original role model what it might do differently. The output is a candidate:
it lands in `role_self_review_items` as `pending` and changes nothing until an
authenticated operator accepts an individual item. Accepted guidance always
carries a short expiry and is rechecked against its original evidence before it
may be injected into a later reply.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json

from companion_v2.conversation.foreground import (BackgroundPromptTrigger, PromptMaterial, PromptRequest,
    SealedForegroundContext)
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskDefinition, TaskError,
    TaskRegistration, TaskResult, TaskSpec, digest, encode, require, stamp)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, ScopeKind, VersionRef
from companion_v2.memory.activity_receipts import RoleReceiptReader
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from . import self_review
from .self_review_evidence import SelfReviewEvidenceCatalog, evidence_handles, window_document

KIND = "role.self_review"
OWNER = "role.self_review"
CURSOR_PREFIX = "role.self_review.cursor.v1:"
MIN_EVIDENCE = 2
TERMINAL_AVAILABLE = frozenset({"self_review_private_audience_required"})
PROMPT = (
    "复盘上一段时间里角色自己在这段私聊中的可观察行为，只依据提供的证据条目。"
    "可以检查：是否回应了对方真正提出的请求、是否在不确定时说明了不确定性、"
    "是否尊重了来源与授权、是否把提议或计划说成了已经完成的事。"
    "不要评价用户或第三方，不要给角色贴人格标签，不要把一次失误写成稳定事实，"
    "也不要因为材料里没有出现就断言某件事没有发生。"
    "证据不足时给出较少的条目，或使用 no_change。"
    "每条指导都必须引用输入中存在的 evidence_handle，next_action 要具体、简短、可立刻执行，"
    "expires_at 必须是短期的 ISO 8601 时间且带时区。"
    "这里只提出待审候选，不代表已经修改提示词、配置或记忆。"
)


def self_review_profile(provider, *, max_output_tokens=1024):
    return ModelTaskProfile(KIND, Lane.BACKGROUND, provider,
        "依据角色自己的近期行为证据，提出待审阅的自我复盘指导候选。",
        max_output_tokens=max_output_tokens)


def parse_output(raw, *, allowed_evidence, now):
    """Bridge the candidate contract onto this service's error vocabulary."""
    try:
        return self_review.parse_output(raw, allowed_evidence=allowed_evidence, now=now)
    except ValueError as error:
        raise TaskError("self_review_output_invalid", str(error) or "self-review output is invalid") from error


class SelfReviewService:
    page_size = 16
    scan_seconds = 3600

    def __init__(self, runtime, *, window_hours=24):
        self.runtime = runtime
        self.operations = OperationRepository(runtime)
        self.window_hours = window_hours
        self.pending, self.committed, self.workers, self.results = {}, set(), {}, {}
        self.next_checks = {}
        self.cursor = 0
        self.closed = False
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, "role.self_review.read",
            Lane.BACKGROUND, side_effect=SideEffect.LOCAL, binding=ProviderBinding(OWNER, "local", "1", "review-1"),
            timeout_seconds=180, max_attempts=1, concurrency=1), self.validate),)

    def attach(self, app):
        self.app, self.tasks, self.gateway = app, app.tasks, app.gateway
        if app.role_self_review_evidence is None:
            raise TaskError("self_review_owner_unavailable", "the conversation owner is not attached")
        self.evidence = app.role_self_review_evidence
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate,
                                      waiting=app.background_waiting)

    @staticmethod
    def identifier(context, operation_id):
        return "self-review:" + digest([context.scope, context.role_binding.role, operation_id])

    def _bound(self, context, instruction):
        bound = self.app.state_maintenance.bindings.get(context.key)
        if bound is None or bound[:2] != (context, instruction):
            raise TaskError("self_review_binding_changed", "the original private role is no longer bound")
        return bound[2]

    async def guard(self, context, instruction):
        check = self._bound(context, instruction)
        if check is not None:
            await check(context.scope, context.role_binding, instruction)

    def prepare(self, context, instruction, at):
        self.app.require_running()
        self._bound(context, instruction)
        window = self.evidence.collect(context, at)
        if len(window.evidence) < MIN_EVIDENCE:
            return None
        return {"context": context, "instruction": instruction, "at": at,
                "window": window, "material_hash": window.material_hash,
                "catalogue": self.evidence.catalogue(window),
                "window_document": window_document(window)}

    @outcome
    def validate(self, spec, at):
        self.app.require_running()
        job = self.pending.get(spec.task_id)
        if job is None or job["context"] != spec.context or job["request_key"] != spec.request_ref:
            raise TaskError("self_review_job_unavailable", "original self-review inputs are unavailable")
        self._bound(spec.context, job["instruction"])
        window = self.evidence.collect(spec.context, at)
        if window.material_hash != job["material_hash"]:
            raise TaskError("self_review_material_changed", "reviewed behaviour changed or was withdrawn")
        return True

    async def run(self, context, instruction):
        if self.closed:
            raise TaskError("self_review_closed", "self-review worker is stopped")
        if KIND not in self.gateway.router.profiles:
            raise TaskError("model_task_unregistered", "self-review needs its background profile")
        await self.guard(context, instruction)
        identifier = self.identifier(context, self._slot(context))
        if self.operations.get(identifier).is_success:
            return {"state": "already_attempted", "task_id": identifier}
        job = self.prepare(context, instruction, self.tasks.now())
        if job is None:
            return {"state": "no_reviewable_window", "task_id": identifier}
        request_key = digest([job["material_hash"], job["window_document"]])
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

    @staticmethod
    def _slot(context):
        return context.key

    async def generate(self, run):
        job = self.pending[run.task.task_id]
        context = job["context"]
        await self.guard(context, job["instruction"])
        run.validate()
        material = {"review_window": job["window_document"], "evidence": job["catalogue"]}
        request = PromptRequest(BackgroundPromptTrigger(job["request_key"], context.actor.principal,
            context.scope, job["at"]), job["instruction"], SealedForegroundContext(
                (PromptMaterial(OWNER, "role_self_review_evidence", encode(material)),), (), ()),
            PROMPT, context.role_binding, output_format="role_self_review")
        completion = await self.gateway.generate(run, request)
        try:
            if completion.draft is None:
                raise TaskError("self_review_output_invalid", "self-review needs a complete response")
            output = parse_output(completion.draft.text,
                allowed_evidence=evidence_handles(job["window"]), now=self.tasks.now())
            await self.guard(context, job["instruction"])
            with self.runtime.transaction() as connection:
                run.validate()
                run.begin_effect()
                run_id = "self-review:" + digest([context.key, job["request_key"]])
                at = stamp(self.tasks.now())
                connection.execute("""INSERT INTO role_self_review_runs VALUES
                    (?, ?, ?, ?, ?, ?, 'pending', ?, NULL)""",
                    (run_id, digest(self.evidence.receipts.life.owner(context)), digest(context.scope),
                     encode(job["window_document"]), job["material_hash"], output.summary, at))
                for ordinal, item in enumerate(output.guidance):
                    connection.execute("""INSERT INTO role_self_review_items VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL, ?)""",
                        (run_id + ":item:" + str(ordinal), run_id, digest(self.evidence.receipts.life.owner(context)),
                         digest(context.scope), item.kind, item.observation, item.next_action,
                         item.confidence, encode(sorted(item.evidence_handles)), stamp(item.expires_at), at, ordinal))
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
        """Persisted review cursor: the last closed window this role was reviewed over."""
        key = CURSOR_PREFIX + digest([self.evidence.receipts.life.owner(context), context.scope])
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
        if row is None:
            return key, None
        value = json.loads(row["value"])
        if type(value) is not dict or set(value) != {"closed_at"} or type(value["closed_at"]) is not str:
            raise TaskError("self_review_cursor_invalid", "self-review cursor is invalid")
        try:
            closed_at = datetime.fromisoformat(value["closed_at"])
        except ValueError:
            raise TaskError("self_review_cursor_invalid", "self-review cursor is invalid") from None
        return key, closed_at

    def _advance_cursor(self, key, closed_at):
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, encode({"closed_at": stamp(closed_at)})))

    def due(self, context, at):
        """True when this role's window has moved on since its last review."""
        _, closed_at = self._cursor(context)
        return closed_at is None or at - closed_at >= timedelta(seconds=self.scan_seconds)

    def advance(self):
        if self.closed:
            return
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                del self.workers[key]
                if not worker.cancelled():
                    error = worker.exception()
                    if error:
                        self.results[key] = {"state": "failed", "code": getattr(error, "code", "self_review_failed")}
        if self.workers or KIND not in self.gateway.router.profiles:
            return
        bindings = tuple(self.app.state_maintenance.bindings.values())
        if not bindings:
            self.next_checks.clear()
            return
        for _ in range(min(16, len(bindings))):
            context, instruction, _ = bindings[self.cursor % len(bindings)]
            self.cursor += 1
            at = self.tasks.now()
            if context.scope.kind is not ScopeKind.PRIVATE or self.next_checks.get(context.key, at) > at:
                continue
            self.next_checks[context.key] = at + timedelta(seconds=30)
            try:
                if not self.due(context, at):
                    continue
                job = self.prepare(context, instruction, at)
                if job is None:
                    continue
                key, _ = self._cursor(context)
                self._advance_cursor(key, at)
                self.workers[context.key] = asyncio.create_task(
                    self.run(context, instruction), name="companion:self-review")
                self.workers[context.key].add_done_callback(lambda done: self.app.notify())
                return
            except TaskError as error:
                self.results[context.key] = {"state": "blocked", "code": error.code}

    def cancel_running(self):
        for worker in self.workers.values():
            worker.cancel()

    @property
    def active_handles(self):
        return self.runner.active_handles + tuple("self-review:" + key for key, worker in
            self.workers.items() if not worker.done())

    async def close(self):
        self.closed = True
        self.cancel_running()
        await self.runner.close()
        if self.workers:
            await asyncio.wait(tuple(self.workers.values()), timeout=0.25)
