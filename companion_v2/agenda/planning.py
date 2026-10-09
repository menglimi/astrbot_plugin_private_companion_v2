"""Original-role planning on the shared background supervisor and calendar owner."""

import asyncio
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from companion_v2.conversation.foreground import BackgroundPromptTrigger, PromptMaterial, PromptRequest, SealedForegroundContext
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskDefinition, TaskError,
    TaskRegistration, TaskResult, TaskSpec, digest, encode, require)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.model_gateway.models import ModelTaskProfile
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.versioned_records import owner_key
from .planning_config import SCHEDULE_MODE_ORCHESTRATED, configured_weather_location, planning_values
from .planning_inputs import capture, validate
from .planning_output import INSTRUCTION, parse_output
from .models import AgendaError
logger = logging.getLogger(__name__)


KIND = "calendar.plan"
OWNER = "calendar.planning"


def planning_profile(provider, *, max_output_tokens=2048):
    return ModelTaskProfile(KIND, Lane.BACKGROUND, provider,
        "沿原人格安排自己的生活；保留长期目标、当天小步和未完成事项，计划不是完成记录。",
        max_output_tokens=max_output_tokens)


class CalendarPlanning:
    def __init__(self, runtime, *, weather_port=None):
        self.runtime = runtime
        self.weather_port = weather_port
        self.operations = OperationRepository(runtime)
        self.pending, self.workers, self.results, self.next_checks = {}, {}, {}, {}
        self.committed = set()
        self.invocations = set()
        self.closed, self.cursor = False, 0
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, "calendar.write", Lane.BACKGROUND,
            side_effect=SideEffect.LOCAL, binding=ProviderBinding(OWNER, "local", "1", "planning-1"),
            timeout_seconds=180, max_attempts=1, concurrency=1), self.validate),)

    def attach(self, app):
        self.app, self.tasks, self.gateway = app, app.tasks, app.gateway
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate, waiting=app.background_waiting)

    @staticmethod
    def identifier(context, slot):
        return "calendar-plan-" + digest([owner_key(context), slot])

    def attempted(self, context, slot):
        return self.operations.get(self.identifier(context, slot)).is_success

    async def guard(self, context, instruction):
        binding = self.app.state_maintenance.bindings.get(context.key)
        if binding is None or binding[:2] != (context, instruction):
            raise TaskError("planning_role_changed", "original role binding is unavailable")
        if binding[2] is not None:
            await binding[2](context.scope, context.role_binding, instruction)

    @outcome
    def validate(self, spec, at):
        self.app.require_running()
        job = self.pending.get(spec.task_id)
        if self.closed or job is None or job["context"] != spec.context or digest(job) != spec.request_ref:
            raise TaskError("planning_job_unavailable", "original planning input is unavailable")
        validate(self, job, at, committed=spec.task_id in self.committed)
        return True

    async def run(self, context, instruction, *, mode, slot, occurrence=None, manual=False, refresh=False):
        invocation = asyncio.current_task()
        self.invocations.add(invocation)
        try:
            return await self._run(context, instruction, mode=mode, slot=slot, occurrence=occurrence,
                                   manual=manual, refresh=refresh)
        finally:
            self.invocations.discard(invocation)

    async def _run(self, context, instruction, *, mode, slot, occurrence=None, manual=False, refresh=False):
        if mode not in ("daily", "horizon", "refine") or mode == "refine" and occurrence is None:
            raise ValueError("select an explicit planning mode and original period")
        if self.closed:
            raise TaskError("planning_closed", "planning worker is closed")
        self.app.require_running()
        self.app.calendar.access.check(context, "calendar.write")
        identifier = self.identifier(context, slot)
        if self.attempted(context, slot):
            return {"state": "already_attempted", "mode": mode, "task_id": identifier, "replayed": True}
        if KIND not in self.gateway.router.profiles:
            raise TaskError("model_task_unregistered", "planning needs its background profile")
        await self.guard(context, instruction)
        settings = planning_values(self.app.role_state.settings(context)[0])
        location = (configured_weather_location(settings["planning_weather_location"])
                    if (manual or settings["planning_enabled"]) and settings["calendar_enabled"]
                    and settings["planning_weather_enabled"] else None)
        weather = None
        if location is not None and self.weather_port is not None:
            try:
                weather = await asyncio.wait_for(self.weather_port.fetch(location), timeout=6)
            except Exception as error:
                logger.warning("V2 planning weather fetch failed: %s", type(error).__name__)
        with self.runtime.transaction():
            job = capture(self, context, instruction, mode, slot, occurrence,
                          weather=weather, weather_location=location, manual=manual, refresh=refresh)
            reservation = require(self.operations.reserve(OperationRef(identifier, OWNER, context.scope,
                VersionRef(identifier, 1), identifier), parameter_hash=digest([owner_key(context), mode, slot]),
                observed_at=job["at"]))
            if reservation.replayed:
                return {"state": "already_attempted", "mode": mode, "task_id": identifier, "replayed": True}
            self.pending[identifier] = job
            try:
                require(self.tasks.submit(TaskSpec(identifier, context, KIND, digest(job), identifier,
                    job["at"], min(job["end"], job["at"] + timedelta(minutes=3)))))
            except BaseException:
                self.pending.pop(identifier, None)
                raise
        try:
            result = require(await self.runner.run(context, identifier))
            task = result.task
            if task.state in ("created", "retry_scheduled"):
                task = require(self.tasks.discard_queued(identifier, reason="owner_unavailable"))
            report = {"state": task.state, "mode": mode, "task_id": identifier, "code": task.reason}
            if identifier in self.committed:
                report.update(saved=self.results.get(context.key, {}).get("saved", 0),
                              rejected=self.results.get(context.key, {}).get("rejected", []),
                              replaced=self.results.get(context.key, {}).get("replaced", 0))
            self.results[context.key] = report
            return report
        finally:
            self.pending.pop(identifier, None)
            self.committed.discard(identifier)

    async def generate(self, run):
        job = self.pending[run.task.task_id]
        context, at = job["context"], self.tasks.now()
        await self.guard(context, job["instruction"])
        run.validate()
        trigger = BackgroundPromptTrigger(job["slot"], context.actor.principal, context.scope, at)
        request = PromptRequest(trigger, job["instruction"], SealedForegroundContext(
            (PromptMaterial(OWNER, "planning_material", encode(job["material"])),), (), ()),
            INSTRUCTION, context.role_binding, output_format="calendar_planning")
        completion = await self.gateway.generate(run, request)
        try:
            if completion.draft is None:
                raise TaskError("planning_output_invalid", "planning needs a complete result")
            items, rejected = parse_output(completion.draft.text, job)
            await self.guard(context, job["instruction"])
            receipts = []
            replaced = 0
            with self.runtime.transaction():
                run.validate()
                run.begin_effect()
                if job["mode"] == "refine":
                    selected = job["occurrence"]
                    receipts.append(self.app.calendar.command(context, identifier=selected["id"], action="refine",
                        expected_revision=selected["revision"], operation_key=run.task.task_id + ":detail",
                        data={"sequence": selected["sequence"], "detail": items}, sources=job["sources"]))
                else:
                    if job["refresh_plans"] and items:
                        for selected in job["refresh_plans"]:
                            receipts.append(self.app.calendar.command(context, identifier=selected["id"],
                                action="cancel", expected_revision=selected["revision"],
                                operation_key=run.task.task_id + ":replace:" + selected["id"],
                                sources=job["sources"]))
                            replaced += 1
                    for index, (event, basis) in enumerate(items):
                        identifier = "planned-" + digest([run.task.task_id, index])
                        receipts.append(self.app.calendar.command(context, identifier=identifier, action="create",
                            expected_revision=0, operation_key=run.task.task_id + ":" + str(index),
                            data=event, sources=job["sources"], planning=basis))
                require(self.operations.transition(run.task.task_id, expected_state=OperationState.ACCEPTED,
                    next_state=OperationState.COMPLETED, observed_at=self.tasks.now()))
                self.committed.add(run.task.task_id)
                run.record_operation(run.task.task_id)
            self.results[context.key] = {"state": "succeeded", "mode": job["mode"], "task_id": run.task.task_id,
                                         "saved": len(items), "replaced": replaced, "rejected": list(rejected)}
            self.app.notify()
            return TaskResult("succeeded", effect="committed", result_ref=run.task.task_id,
                              operation_id=run.task.task_id, receipt_ref=run.task.task_id)
        except BaseException:
            if run.task.task_id not in self.committed:
                self.gateway.ledger.discard(completion.call_id)
            raise

    def opportunity(self, context, settings, at):
        if settings.get("schedule_simulation_mode", SCHEDULE_MODE_ORCHESTRATED) != SCHEDULE_MODE_ORCHESTRATED:
            return None
        local = at.astimezone(ZoneInfo(settings["planning_timezone"]))
        settings_token = self.app.role_state.planning_settings_token(context)
        for mode, period in (("daily", local.date().isoformat()),
                             ("horizon", "%04d-W%02d" % local.isocalendar()[:2])):
            slot = mode + ":" + settings["planning_timezone"] + ":" + period + ":settings:" + settings_token
            if not self.attempted(context, slot):
                return mode, slot, None
        page = self.app.calendar.occurrences(context, start=at,
            end=at + timedelta(minutes=settings["planning_refine_minutes"]))
        for item in page["items"]:
            if item["kind"] == "role_plan" and item["state"] == "accepted":
                series = self.app.calendar.read(context, item["id"])
                slot = "refine:" + digest([item["id"], item["sequence"], series["schedule"]["anchor"]])
                if not self.attempted(context, slot):
                    return "refine", slot, item
        return None

    async def _automatic(self, context, instruction, opportunity):
        mode, slot, occurrence = opportunity
        try:
            return await self.run(context, instruction, mode=mode, slot=slot, occurrence=occurrence)
        except (TaskError, ValueError) as error:
            self.results[context.key] = {"state": "blocked", "mode": mode,
                "code": getattr(error, "code", "planning_input_invalid")}

    def advance(self):
        if self.closed:
            return
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.result()
                del self.workers[key]
        if self.workers or KIND not in self.gateway.router.profiles:
            return
        bindings = tuple(self.app.state_maintenance.bindings.values())
        if not bindings:
            return
        # Rotating, rate-limited reads avoid a scan of every saved calendar on every host tick.
        for _ in range(min(16, len(bindings))):
            context, instruction, _ = bindings[self.cursor % len(bindings)]
            self.cursor += 1
            at = self.tasks.now()
            if self.next_checks.get(context.key, at) > at:
                continue
            self.next_checks[context.key] = at + timedelta(seconds=30)
            try:
                settings = planning_values(self.app.role_state.settings(context)[0])
                if (settings["schedule_simulation_mode"] != SCHEDULE_MODE_ORCHESTRATED
                        or not settings["planning_enabled"] or not settings["calendar_enabled"]
                        or self.app.state_maintenance.foreground_busy(context)):
                    continue
                opportunity = self.opportunity(context, settings, at)
                if opportunity:
                    worker = asyncio.create_task(self._automatic(context, instruction, opportunity), name="companion:calendar-planning")
                    self.workers[context.key] = worker
                    worker.add_done_callback(lambda done: self.app.notify())
                    break
            except (TaskError, AgendaError, ValueError) as error:
                code = getattr(error, "code", "planning_input_invalid")
                if code in ("supervisor_fenced", "supervisor_generation_conflict"):
                    raise
                self.results[context.key] = {"state": "blocked", "code": code}

    def status(self, context):
        settings = self.app.role_state.settings(context)[0]
        return {"enabled": settings["planning_enabled"], "calendar_enabled": settings["calendar_enabled"],
            "schedule_simulation_mode": settings["schedule_simulation_mode"],
            "running": context.key in self.workers, "last_result": self.results.get(context.key),
            "next_check": self.next_checks[context.key].isoformat() if context.key in self.next_checks else None}

    @property
    def active_handles(self):
        return (self.runner.active_handles + tuple("calendar-planning:" + key for key in self.workers)
            + tuple("planning-invocation:" + str(id(t)) for t in self.invocations))

    def cancel_running(self):
        self.closed = True
        for worker in self.workers.values():
            worker.cancel()
        for invocation in tuple(self.invocations):
            invocation.cancel()

    async def close(self):
        self.cancel_running()
        await self.runner.close()
        if self.invocations:
            await asyncio.wait(tuple(self.invocations), timeout=0.25)
        if self.workers:
            await asyncio.wait(tuple(self.workers.values()), timeout=0.25)
        for key, worker in tuple(self.workers.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.exception()
                del self.workers[key]
