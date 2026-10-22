"""Reviewable growth progress derived from original completed role receipts."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json

from companion_v2.conversation.foreground import BackgroundPromptTrigger, PromptMaterial, PromptRequest, SealedForegroundContext
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskDefinition, TaskError,
    TaskRegistration, TaskResult, TaskSpec, digest, encode, require, stamp)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, ScopeKind, SourceRef, VersionRef
from companion_v2.memory.activity_receipts import RoleReceiptReader, TABLES
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .configuration import skill_settings, skills_enabled
from .models import GrowthKind, GrowthState


KIND = "role.growth.progress"
OWNER = "role.growth.progress"
CURSOR_PREFIX = "role.growth.progress.cursor.v1:"
TERMINAL_UNAVAILABLE = frozenset({"source_revoked", "source_expired",
    "source_dependency_unavailable", "source_dependency_expired",
    "journal_unavailable", "journal_dependency_changed", "memory_evidence_forgotten"})
PROMPT = (
    "根据执行端已完成的活动或日记保存回执，判断当前已确认的成长目标是否有值得审阅的进展。只能依据提供的回执和目标，不把计划、时间经过、用户自述、日记或梦境正文当成实际完成事实；日记回执只证明保存过主观文字，不据此声称其中事件真实发生。不编造经验值、能力等级或现实世界的成绩，用贴合角色口吻的简洁、审慎定性笔触写清进展说明（如某处细节摸索出的手感、比之前顺手的地方或仍待琢磨的生疏处），避免写成生硬的行政验收报告并保留不确定性。只输出 JSON 对象，精确包含 growth_id 和 progress_note 两个字段：若无目标匹配回执则均用 null，有匹配时用原目标 ID 和非空进展说明。"
)


def growth_progress_profile(provider, *, max_output_tokens=768):
    return ModelTaskProfile(KIND, Lane.BACKGROUND, provider,
        "依据已完成回执，为已确认目标提出待审阅的成长进展。",
        max_output_tokens=max_output_tokens)


def receipt_fingerprint(experience):
    return digest([experience.title, experience.statements, experience.entities,
                   experience.occurred_at, experience.sources])


def parse_progress(raw, references):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON field")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (TypeError, ValueError, RecursionError) as error:
        raise TaskError("growth_progress_output_invalid", "growth progress needs one JSON object") from error
    if type(value) is not dict or set(value) != {"growth_id", "progress_note"}:
        raise TaskError("growth_progress_output_invalid", "growth progress fields changed")
    if value == {"growth_id": None, "progress_note": None}:
        return None
    if (type(value["growth_id"]) is not str or value["growth_id"] not in references
            or type(value["progress_note"]) is not str
            or not value["progress_note"].strip() or len(value["progress_note"]) > 8192):
        raise TaskError("growth_progress_output_invalid", "growth progress must select an original active target")
    return value["growth_id"], value["progress_note"].strip()


class GrowthProgressService:
    page_size = 16

    def __init__(self, runtime):
        self.runtime = runtime
        self.operations = OperationRepository(runtime)
        self.pending, self.committed, self.workers, self.results = {}, set(), {}, {}
        self.next_checks = {}
        self.cursor = 0
        self.closed = False
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, "role.growth.read", Lane.BACKGROUND,
            side_effect=SideEffect.LOCAL, binding=ProviderBinding(OWNER, "local", "1", "progress-1"),
            timeout_seconds=180, max_attempts=1, concurrency=1), self.validate),)

    def attach(self, app):
        self.app, self.tasks, self.gateway = app, app.tasks, app.gateway
        self.ledger = app.role_growth
        self.growth = app.role_growth_context.reader
        self.receipts = RoleReceiptReader(app.life_context)
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate,
                                      waiting=app.background_waiting)

    @staticmethod
    def identifier(context, operation_id):
        return "growth-progress:" + digest([context.scope, context.role_binding.role, operation_id])

    def _bound(self, context, instruction):
        bound = self.app.state_maintenance.bindings.get(context.key)
        if bound is None or bound[:2] != (context, instruction):
            raise TaskError("growth_progress_binding_changed", "the original private role is no longer bound")
        return bound[2]

    async def guard(self, context, instruction):
        check = self._bound(context, instruction)
        if check is not None:
            await check(context.scope, context.role_binding, instruction)

    def prepare(self, context, instruction, stream, operation_id):
        self.app.require_running()
        at = self.tasks.now()
        self._bound(context, instruction)
        self.growth._authorize(context, at)
        experience = self.receipts.read(context, stream, operation_id, at)
        if experience is None:
            return None
        for source in experience.sources:
            if not isinstance(source, SourceRef) or source.scope != context.scope:
                raise TaskError("growth_progress_source_scope", "receipt evidence belongs to another private scope")
            require(self.growth.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))
        candidates = self.growth.candidates(context, at)
        targets = []
        use_skills = skills_enabled(self.runtime, context)
        for item in candidates.items:
            record = self.ledger.record(item.reference["growth_id"], owner=self.growth.owner(context))
            if record.kind is GrowthKind.SKILL and not use_skills:
                continue
            if record.state is GrowthState.ACTIVE and record.created_at <= experience.occurred_at:
                targets.append({"growth_id": record.growth_id, "revision": record.revision,
                    "kind": record.kind.value, "title": record.title,
                    "description": record.description, "progress_note": record.progress_note})
        if not targets:
            return None
        return {"context": context, "instruction": instruction, "stream": stream,
            "operation_id": operation_id, "at": at, "receipt_hash": receipt_fingerprint(experience),
            "receipt": {"title": experience.title, "statements": experience.statements,
                "occurred_at": stamp(experience.occurred_at), "sources": experience.sources},
            "targets": tuple(targets)}

    @outcome
    def validate(self, spec, at):
        self.app.require_running()
        job = self.pending.get(spec.task_id)
        if job is None or job["context"] != spec.context or digest(job) != spec.request_ref:
            raise TaskError("growth_progress_job_unavailable", "original progress inputs are unavailable")
        self._bound(spec.context, job["instruction"])
        self.growth._authorize(spec.context, at)
        experience = self.receipts.read(spec.context, job["stream"], job["operation_id"], at)
        if experience is None or receipt_fingerprint(experience) != job["receipt_hash"]:
            raise TaskError("growth_progress_receipt_changed", "completed receipt changed or was withdrawn")
        for source in experience.sources:
            if not isinstance(source, SourceRef) or source.scope != spec.context.scope:
                raise TaskError("growth_progress_source_scope", "receipt evidence belongs to another private scope")
            require(self.growth.sources.validate_reference_for_audience(
                source, recipient=spec.context.actor.subject, observed_at=at))
        if spec.task_id not in self.committed:
            references = tuple({"growth_id": item["growth_id"], "revision": item["revision"]}
                               for item in job["targets"])
            self.growth.read(references, spec.context, at)
            for item in job["targets"]:
                record = self.ledger.record(item["growth_id"], owner=self.growth.owner(spec.context))
                if record.state is not GrowthState.ACTIVE or record.created_at > experience.occurred_at:
                    raise TaskError("growth_progress_target_changed", "confirmed growth target changed")
        return True

    async def run(self, context, instruction, stream, operation_id):
        if self.closed:
            raise TaskError("growth_progress_closed", "progress worker is stopped")
        if KIND not in self.gateway.router.profiles:
            raise TaskError("model_task_unregistered", "growth progress needs its background profile")
        await self.guard(context, instruction)
        identifier = self.identifier(context, operation_id)
        if self.operations.get(identifier).is_success:
            return {"state": "already_attempted", "task_id": identifier}
        job = self.prepare(context, instruction, stream, operation_id)
        if job is None:
            return {"state": "no_active_target", "task_id": identifier}
        with self.runtime.transaction():
            reservation = require(self.operations.reserve(OperationRef(identifier, OWNER, context.scope,
                VersionRef(identifier, 1), identifier),
                parameter_hash=digest([context.key, stream, operation_id]), observed_at=job["at"]))
            if reservation.replayed:
                return {"state": "already_attempted", "task_id": identifier}
            self.pending[identifier] = job
            try:
                require(self.tasks.submit(TaskSpec(identifier, context, KIND, digest(job), identifier,
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
        material = {"completed_receipt": job["receipt"], "active_growth_targets": job["targets"]}
        skills, _ = skill_settings(self.runtime, context)
        prompt = PROMPT
        if skills:
            prompt += ("\n角色自定义技能域：" + "、".join(skills)
                       + "。进展说明优先结合匹配的技能域表述；未匹配时保持原判。")
        request = PromptRequest(BackgroundPromptTrigger(job["operation_id"], context.actor.principal,
            context.scope, job["at"]), job["instruction"], SealedForegroundContext(
                (PromptMaterial(OWNER, "completed_receipt_and_growth", encode(material)),), (), ()),
            prompt, context.role_binding, output_format="role_growth_progress")
        completion = await self.gateway.generate(run, request)
        try:
            if completion.draft is None:
                raise TaskError("growth_progress_output_invalid", "growth progress needs a complete response")
            selected = parse_progress(completion.draft.text,
                {item["growth_id"] for item in job["targets"]})
            await self.guard(context, job["instruction"])
            with self.runtime.transaction() as connection:
                run.validate()
                run.begin_effect()
                owner = self.growth.owner(context)
                review_id = "growth-review:" + digest([owner, context.scope, job["operation_id"]])
                source_json = encode({"stream": job["stream"], "operation_id": job["operation_id"],
                    "receipt_hash": job["receipt_hash"]})
                reference = next((item for item in job["targets"] if selected and
                    item["growth_id"] == selected[0]), None)
                connection.execute("""INSERT INTO role_growth_progress_reviews VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                    (review_id, digest(owner), digest(context.scope), job["operation_id"],
                     reference["growth_id"] if reference else None,
                     reference["revision"] if reference else None, source_json,
                     selected[1] if selected else "", "pending" if selected else "skipped", stamp(self.tasks.now())))
                require(self.operations.transition(run.task.task_id, expected_state=OperationState.ACCEPTED,
                    next_state=OperationState.COMPLETED, observed_at=self.tasks.now()))
                self.committed.add(run.task.task_id)
                run.record_operation(run.task.task_id)
            self.app.notify()
            return TaskResult("succeeded", effect="committed", result_ref=review_id,
                receipt_ref=run.task.task_id, operation_id=run.task.task_id)
        except BaseException:
            if run.task.task_id not in self.committed:
                self.gateway.ledger.discard(completion.call_id)
            raise

    def _next_receipt(self, context):
        key = CURSOR_PREFIX + digest([self.growth.owner(context), context.scope])
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
            cursor = json.loads(row["value"]) if row else {stream: 0 for stream in TABLES}
            if type(cursor) is not dict or set(cursor) != set(TABLES) or any(
                    type(value) is not int or value < 0 for value in cursor.values()):
                raise TaskError("growth_progress_cursor_invalid", "progress receipt cursor is invalid")
            selected = None
            owner_key = digest(self.growth.owner(context))
            for stream, table in TABLES.items():
                rows = connection.execute(f"SELECT rowid AS scan_id, operation_id, owner_key FROM {table} "
                    "WHERE rowid > ? ORDER BY rowid LIMIT ?", (cursor[stream], self.page_size)).fetchall()
                for item in rows:
                    if item["owner_key"] != owner_key:
                        cursor[stream] = item["scan_id"]
                        continue
                    operation = require(self.operations.get(item["operation_id"]))
                    if operation.operation.scope != context.scope:
                        cursor[stream] = item["scan_id"]
                        continue
                    identifier = self.identifier(context, item["operation_id"])
                    if self.operations.get(identifier).is_success:
                        cursor[stream] = item["scan_id"]
                        continue
                    try:
                        if self.prepare(context, self.app.state_maintenance.bindings[context.key][1],
                                        stream, item["operation_id"]) is not None:
                            selected = (stream, item["operation_id"])
                            break
                    except TaskError as error:
                        if error.code not in TERMINAL_UNAVAILABLE:
                            raise
                    cursor[stream] = item["scan_id"]
                if selected:
                    break
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (key, encode(cursor)))
            return selected

    def advance(self):
        if self.closed:
            return
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                del self.workers[key]
                if not worker.cancelled():
                    error = worker.exception()
                    if error:
                        self.results[key] = {"state": "failed", "code": getattr(error, "code", "growth_progress_failed")}
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
                if not self.growth.candidates(context, at).items:
                    continue
                selected = self._next_receipt(context)
                if selected:
                    worker = asyncio.create_task(self.run(context, instruction, *selected),
                                                 name="companion:growth-progress")
                    self.workers[context.key] = worker
                    worker.add_done_callback(lambda done: self.app.notify())
                    return
            except TaskError as error:
                self.results[context.key] = {"state": "blocked", "code": error.code}

    def cancel_running(self):
        for worker in self.workers.values():
            worker.cancel()

    @property
    def active_handles(self):
        return self.runner.active_handles + tuple("growth-progress:" + key for key, worker in
            self.workers.items() if not worker.done())

    async def close(self):
        self.closed = True
        self.cancel_running()
        await self.runner.close()
        if self.workers:
            await asyncio.wait(tuple(self.workers.values()), timeout=0.25)
