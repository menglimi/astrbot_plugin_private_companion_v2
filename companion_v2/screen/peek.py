"""One supervised, explicitly authorized Screen peek past the model tool loop.

V1 reached the screen companion plugin from its own scheduler. V2 keeps that
authority in the same place it was already granted — the registered native
``screen.capture`` extension — and dispatches it through the *same* provider
admission as a model-issued call, with a synthetic single-use invocation:

* the device call happens once per episode, never on a retry;
* the adopted original is interpreted by the existing interpretation chain, so a
  peek produces a proactive anchor instead of dialogue written out of thin air;
* a failed or unknown device answer is recorded as an attempt and is never
  replayed.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json

from companion_v2.conversation.external_tools import ExternalToolInvocation
from companion_v2.conversation.media.screen import ACTION as SCREEN_CAPTURE_ACTION
from companion_v2.capabilities import CapabilityRepository
from companion_v2.execution.models import (Lane, ProviderBinding, SideEffect, TaskContext, TaskDefinition,
                                           TaskError, TaskRegistration, TaskResult, TaskSpec, digest, require)
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.screen.models import SCREEN_EXTENSION

from .configuration import ScreenSettings
from .repositories import ScreenRepository


KIND = "screen.peek"
OWNER = "screen.peek"
ACTION = "extension.tool.invoke"
TIMEOUT_SECONDS = 120
DEVICE_TIMEOUT_SECONDS = 60
MAX_CONCURRENCY = 1
PEEK_ARGUMENTS = '{"all_screens":false}'
PURPOSES = ("goodnight", "followup")


class ScreenPeekService:
    """Dispatch one authorized device peek and hand the original to interpretation."""

    def __init__(self, runtime, *, notify=None):
        self.runtime = runtime
        self.notify = notify or (lambda: None)
        self.app = None
        self.tasks = None
        self.settings = None
        self.screens = None
        self.runner = None
        self.pending: dict[str, dict] = {}
        self._workers: dict[str, object] = {}
        self._closed = False
        self.registrations = (TaskRegistration(TaskDefinition(KIND, OWNER, ACTION, Lane.BACKGROUND,
            side_effect=SideEffect.EXTERNAL_DEVICE,
            binding=ProviderBinding(OWNER, "local", "1", "screen-peek-1"),
            timeout_seconds=TIMEOUT_SECONDS, max_attempts=1, concurrency=MAX_CONCURRENCY), self.validate),)

    # -- lifecycle -----------------------------------------------------

    def attach(self, app):
        self.app, self.tasks = app, app.tasks
        self.settings = app.screen_settings
        self.screens = ScreenRepository(self.runtime, authorizer=self.tasks.identity)
        self.runner = ExactTaskRunner(self.tasks, frozenset({KIND}), self.generate,
                                      waiting=app.background_waiting)
        return self

    @property
    def active_handles(self):
        return self.runner.active_handles if self.runner is not None else ()

    def cancel_running(self):
        self._closed = True
        for worker in tuple(self._workers.values()):
            worker.cancel()

    async def close(self):
        self._closed = True
        for worker in tuple(self._workers.values()):
            worker.cancel()
        if self._workers:
            await asyncio.wait(tuple(self._workers.values()), timeout=0.25)
        self._workers.clear()
        if self.runner is not None:
            await self.runner.close()

    # -- submission ----------------------------------------------------

    def request(self, context: TaskContext, decision: dict, *, request_ref: str,
                role_instruction: str = "") -> str | None:
        """Queue the decided peek; the caller has already checked every gate."""
        if (self._closed or self.app is None or not isinstance(context, TaskContext)
                or type(decision) is not dict or decision.get("purpose") not in PURPOSES):
            return None
        if self.app.external is None or SCREEN_CAPTURE_ACTION not in self.app.external.actions:
            return None
        task_id = decision.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return None
        if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)):
            return None
        at = self.tasks.now()
        self.pending[task_id] = {"context": context, "decision": decision,
                                 "request_ref": request_ref or task_id,
                                 "role_instruction": role_instruction.strip()}
        try:
            with self.runtime.transaction():
                require(self.tasks.submit(TaskSpec(task_id, context, KIND, request_ref or task_id, task_id,
                                                   at, at + timedelta(seconds=TIMEOUT_SECONDS))))
        except TaskError:
            self.pending.pop(task_id, None)
            return None
        self.notify()
        return task_id

    @outcome
    def validate(self, spec, at):
        job = self.pending.get(spec.task_id)
        if job is None or job["context"].key != spec.context.key:
            raise TaskError("screen_peek_unavailable", "the decided Screen peek is no longer held")
        context = spec.context
        if self._settings(context, at) is None:
            raise TaskError("screen_peek_disabled", "Screen peeks are no longer enabled for this window")
        return True

    def _settings(self, context, at):
        try:
            values = self.settings.read(context, at)
        except TaskError:
            return None
        return values if values["interpretation_enabled"] else None

    def ready(self, context, at) -> bool:
        """True only while a peek could actually be captured *and* interpreted."""
        if self._closed or self.app is None or self.app.external is None:
            return False
        if SCREEN_CAPTURE_ACTION not in self.app.external.actions:
            return False
        if self._settings(context, at) is None:
            return False
        projection = CapabilityRepository(self.runtime).projection(extension_id=SCREEN_EXTENSION,
                                                                   scope=context.scope)
        return (projection.is_success and projection.unwrap().settings is not None
                and projection.unwrap().settings.proactive_enabled)

    # -- planner -------------------------------------------------------

    @outcome
    def advance(self):
        if self._closed or self.app is None or self.runner is None:
            return False
        for task_id, worker in tuple(self._workers.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.exception()
                del self._workers[task_id]
        capacity = MAX_CONCURRENCY - len(self._workers)
        started = 0
        for task_id, job in tuple(self.pending.items()):
            if capacity <= 0:
                break
            if task_id in self._workers:
                continue
            if self.tasks.read(job["context"], task_id) is None:
                self.pending.pop(task_id, None)
                continue
            worker = asyncio.create_task(self.runner.run(job["context"], task_id),
                                         name="companion:screen-peek:" + task_id)
            self._workers[task_id] = worker
            worker.add_done_callback(lambda done: self.notify())
            capacity -= 1
            started += 1
        return started > 0

    # -- execution -----------------------------------------------------

    async def generate(self, run):
        job = self.pending.get(run.task.task_id)
        if job is None:
            raise TaskError("screen_peek_unavailable", "the decided Screen peek is no longer held")
        context = job["context"]
        at = self.tasks.now()
        if self._settings(context, at) is None:
            raise TaskError("screen_peek_disabled", "Screen peeks are no longer enabled for this window")
        capture = await self._dispatch(run, context)
        run.validate()
        submitted = self.app.screen_interpretation.submit(
            context, capture, purpose="glance", request_ref=job["request_ref"],
            parent_task_id=run.task.task_id, role_instruction=job["role_instruction"])
        if submitted is None:
            raise TaskError("screen_peek_interpretation_unavailable",
                            "the peek could not be handed to the interpretation chain")
        return TaskResult("succeeded", result_ref=submitted)

    async def _dispatch(self, run, context):
        provider = self.app.external.providers.get(SCREEN_CAPTURE_ACTION)
        if provider is None:
            raise TaskError("screen_peek_unavailable", "the Screen extension is not currently registered")
        descriptor = provider.descriptor
        invocation_id = "screen-peek-" + digest([run.task.task_id, context.key])
        deadline = self.tasks.now() + timedelta(seconds=DEVICE_TIMEOUT_SECONDS)

        def before_dispatch():
            run.validate()
            self.app.external.admit(descriptor, context, self.tasks.now())

        invocation = ExternalToolInvocation(invocation_id, run.task.task_id, "screen-peek", context,
                                            descriptor, PEEK_ARGUMENTS, deadline, before_dispatch)
        response = await provider.invoke(invocation)
        if response.state != "succeeded" or response.source is None:
            raise TaskError("screen_peek_not_committed", "the device did not return a confirmed screenshot")
        return self._capture(response, invocation_id, context)

    def _capture(self, response, invocation_id, context):
        try:
            data = json.loads(response.source.payload)
            capture_id = data["screen_capture"]["reference"]["capture_id"]
        except (ValueError, TypeError, KeyError) as error:
            raise TaskError("screen_peek_receipt_invalid", "the device receipt has no adopted original") from error
        reference = require(self.screens.published_reference(capture_id, scope=context.scope))
        token = digest(invocation_id)
        if (reference.source.source_id != "screen-source-" + token
                or reference.asset.asset_id != "screen-asset-" + token):
            raise TaskError("screen_peek_capture_mismatch", "the adopted original belongs to another peek")
        return reference


__all__ = ["DEVICE_TIMEOUT_SECONDS", "KIND", "OWNER", "PEEK_ARGUMENTS", "PURPOSES", "ScreenPeekService"]
