from __future__ import annotations

import asyncio
from dataclasses import replace
import unittest

from companion_v2.execution.models import Lane, TaskDeferred, TaskError, TaskRegistration, TaskResult
from companion_v2.execution.runner import LocalTaskRunner
from tests.test_execution import ExecutionFixture
from tests.test_management_access import NOW


class ExecutionRunnerTests(ExecutionFixture, unittest.IsolatedAsyncioTestCase):
    def runner(self, handler, *, timeout=1, kind="fixture.read", stop_grace=0.05):
        self.registrations = tuple(TaskRegistration(replace(entry.definition, timeout_seconds=timeout), entry.validate)
                                   for entry in self.registrations)
        self.tasks = self.supervisor()
        self.tasks.attach(expected_generation=1).unwrap()

        async def unused(run):
            raise AssertionError("unselected task kind ran")

        handlers = {entry.definition.kind: unused for entry in self.registrations}
        handlers[kind] = handler
        runner = LocalTaskRunner(self.tasks, handlers, check_interval=0.005, stop_grace=stop_grace)
        self.addAsyncCleanup(runner.close)
        return runner

    async def test_runner_executes_once_records_measured_time_and_does_not_poll_when_idle(self):
        calls = []

        async def handler(run):
            calls.append(run.task.task_id)
            run.validate()
            return TaskResult("succeeded", result_ref="fixture:result")

        runner = self.runner(handler)
        self.submit()
        done = (await runner.run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual((calls, done.state, runner.active_handles), (["task-1"], "succeeded", ()))
        self.assertIsNone((await runner.run_once(Lane.FOREGROUND)).unwrap().task)
        observed = self.tasks.observe(self.context, done.task_id).unwrap()
        self.assertGreaterEqual(observed["execution_ms"], 0)

    async def test_timeout_stops_cooperative_read_and_releases_capacity(self):
        cleaned = asyncio.Event()

        async def handler(run):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        runner = self.runner(handler, timeout=0.025)
        self.submit()
        result = (await runner.run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(result.state, "expired")
        self.assertTrue(cleaned.is_set())
        self.assertEqual(runner.active_handles, ())
        self.assertFalse(self.tasks.observe(self.context, result.task_id).unwrap()["slot_held"])

    async def test_timeout_after_effect_preserves_unknown_and_original_acceptance(self):
        async def handler(run):
            run.begin_effect()
            run.record_operation("original-owner-acceptance")
            await asyncio.Event().wait()

        runner = self.runner(handler, timeout=0.025, kind="fixture.effect")
        self.submit(kind="fixture.effect")
        result = (await runner.run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual((result.state, result.effect, result.operation_id), ("uncertain", "unknown", "original-owner-acceptance"))
        self.assertFalse(self.tasks.observe(self.context, result.task_id).unwrap()["slot_held"])
        self.assertIsNone((await runner.run_once(Lane.FOREGROUND)).unwrap().task)

    async def test_cancel_request_is_observed_while_handler_is_waiting(self):
        entered = asyncio.Event()

        async def handler(run):
            entered.set()
            await asyncio.Event().wait()

        runner = self.runner(handler)
        self.submit()
        running = asyncio.create_task(runner.run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        current = self.read_task()
        self.tasks.cancel(self.context, "task-1", expected_revision=current.revision).unwrap()
        result = (await asyncio.wait_for(running, 1)).unwrap().task
        self.assertEqual((result.state, runner.active_handles), ("cancelled", ()))

    async def test_revocation_during_io_disposes_draft_and_stops_worker(self):
        entered = asyncio.Event()
        exited = asyncio.Event()

        async def handler(run):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                exited.set()

        runner = self.runner(handler)
        self.submit()
        running = asyncio.create_task(runner.run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        self.identity.revoke_binding(self.important.binding_id, expected_revision=self.identity.revision, revoked_at=NOW)
        result = (await asyncio.wait_for(running, 1)).unwrap().task
        self.assertEqual((result.state, result.result_ref), ("failed", None))
        self.assertTrue(exited.is_set())
        self.assertEqual(self.tasks.observe(self.context, "task-1").failure.code, "binding_revoked")

    async def test_late_handler_return_cannot_rewrite_unknown_or_release_slot_early(self):
        cancelled = asyncio.Event()
        release = asyncio.Event()

        async def handler(run):
            run.begin_effect()
            run.record_operation("actual-operation")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            return TaskResult("succeeded", "committed", receipt_ref="late-receipt", operation_id="actual-operation")

        runner = self.runner(handler, timeout=0.025, kind="fixture.effect", stop_grace=0.005)
        self.submit(kind="fixture.effect")
        result = (await runner.run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(result.state, "uncertain")
        self.assertTrue(cancelled.is_set())
        self.assertEqual(len(runner.active_handles), 1)
        self.assertTrue(self.tasks.observe(self.context, "task-1").unwrap()["slot_held"])
        self.submit("second", kind="fixture.effect")
        self.assertIsNone(self.tasks.claim(Lane.FOREGROUND).unwrap().claim)
        worker = next(iter(runner._handles.values()))[1]
        release.set()
        await asyncio.wait_for(worker, 1)
        await asyncio.sleep(0)
        self.assertEqual(self.read_task().state, "uncertain")
        self.assertIsNone(self.read_task().result_ref)
        self.assertEqual(runner.active_handles, ())
        self.assertFalse(self.tasks.observe(self.context, "task-1").unwrap()["slot_held"])

    async def test_parent_cancellation_and_close_await_registered_workers(self):
        entered = asyncio.Event()

        async def handler(run):
            entered.set()
            await asyncio.Event().wait()

        runner = self.runner(handler)
        self.submit()
        running = asyncio.create_task(runner.run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        running.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await running
        self.assertEqual(self.read_task().state, "cancelled")
        self.assertEqual(await runner.close(), ())
        self.assertEqual((await runner.run_once(Lane.FOREGROUND)).failure.code, "task_runner_closed")

    async def test_handler_error_is_redacted_and_no_automatic_effect_retry(self):
        async def handler(run):
            run.begin_effect()
            raise RuntimeError("private exception payload")

        runner = self.runner(handler, kind="fixture.effect")
        self.submit(kind="fixture.effect")
        result = (await runner.run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual((result.state, result.reason), ("uncertain", "worker_error"))
        self.assertNotIn("private exception payload", str(self.tasks.observe(self.context, result.task_id).unwrap()))

    async def test_task_error_code_is_logged_without_private_exception_text(self):
        async def handler(_run):
            raise TaskError("model_usage_unknown", "private exception payload")

        runner = self.runner(handler)
        self.submit()
        with self.assertLogs("companion_v2.execution.runner", level="ERROR") as captured:
            run_result = (await runner.run_once(Lane.FOREGROUND)).unwrap()
            result = run_result.task
        self.assertEqual((result.state, result.reason), ("failed", "worker_error"))
        self.assertEqual(run_result.failure_code, "model_usage_unknown")
        self.assertIn("model_usage_unknown", "\n".join(captured.output))
        self.assertNotIn("private exception payload", "\n".join(captured.output))

    async def test_admission_deferral_releases_the_worker_and_logs_wait_instead_of_error(self):
        async def handler(_run):
            raise TaskDeferred("model_budget_exhausted", "private budget detail", retry_at=NOW)

        runner = self.runner(handler, kind="fixture.background")
        self.submit(kind="fixture.background")
        with self.assertLogs("companion_v2.execution.runner", level="INFO") as captured:
            result = (await runner.run_once(Lane.BACKGROUND)).unwrap()
        self.assertEqual(result.retry_at, NOW)
        self.assertEqual(result.failure_code, "model_budget_exhausted")
        self.assertTrue(all(item.levelname == "INFO" for item in captured.records))
        self.assertNotIn("private budget detail", "\n".join(captured.output))
        self.assertEqual(runner.active_handles, ())

    async def test_close_stops_active_effect_worker_without_claiming_it_was_not_committed(self):
        entered = asyncio.Event()
        exited = asyncio.Event()

        async def handler(run):
            run.begin_effect()
            run.record_operation("original-operation")
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                exited.set()

        runner = self.runner(handler, kind="fixture.effect")
        self.submit(kind="fixture.effect")
        running = asyncio.create_task(runner.run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        self.assertEqual(await runner.close(), ())
        result = (await asyncio.wait_for(running, 1)).unwrap().task
        self.assertTrue(exited.is_set())
        self.assertEqual((result.state, result.effect, result.operation_id), ("uncertain", "unknown", "original-operation"))
        self.assertFalse(self.tasks.observe(self.context, result.task_id).unwrap()["slot_held"])
        self.assertEqual((await runner.run_once(Lane.FOREGROUND)).failure.code, "task_runner_closed")


if __name__ == "__main__":
    unittest.main()
