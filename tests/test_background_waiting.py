"""Live queue ordering, physical capacity and cancellation before task start."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import patch

from companion_v2.execution.models import Lane, TaskRegistration, TaskResult
from companion_v2.execution.runner import ExactTaskRunner
from companion_v2.execution.waiting import BackgroundTaskQueue
from tests.test_execution import ExecutionFixture


class BackgroundWaitingTests(ExecutionFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.queue = BackgroundTaskQueue(self.tasks, interval=0.005)
        self.entered, self.gates, self.invocations = [], {}, []
        self.runner = ExactTaskRunner(self.tasks, frozenset({"fixture.background"}), self.handle,
                                      waiting=self.queue, check_interval=0.005)
        self.addAsyncCleanup(self.cleanup)

    async def cleanup(self):
        for task in self.invocations:
            task.cancel()
        await asyncio.gather(*self.invocations, return_exceptions=True)
        await self.runner.close()

    async def handle(self, run):
        key = run.task.task_id
        self.entered.append(key)
        if key in self.gates:
            await self.gates[key].wait()
        return TaskResult("succeeded", result_ref="result:" + key)

    def start_job(self, key, **changes):
        self.submit(key, kind="fixture.background", **changes)
        task = asyncio.create_task(self.runner.run(self.context, key))
        self.invocations.append(task)
        return task

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(wait(), 2)

    async def occupy(self):
        self.gates["held"] = asyncio.Event()
        held = self.start_job("held")
        await self.until(lambda: "held" in self.entered)
        return held

    async def test_waiting_uses_fifo_without_consuming_attempts_or_foreground_slots(self):
        held = await self.occupy()
        jobs = []
        for name in ("second", "third", "fourth"):
            jobs.append(self.start_job(name))
            await self.until(lambda: name in self.queue._pending)
            self.assertEqual((self.read_task(name).state, self.read_task(name).attempt_no), ("created", 0))
        self.submit("foreground")
        foreground = ExactTaskRunner(self.tasks, frozenset({"fixture.read"}), self.handle)
        self.addAsyncCleanup(foreground.close)
        self.assertEqual((await foreground.run(self.context, "foreground")).unwrap().task.state, "succeeded")
        self.gates["held"].set()
        results = await asyncio.wait_for(asyncio.gather(held, *jobs), 2)
        self.assertEqual({r.unwrap().task.state for r in results}, {"succeeded"})
        self.assertEqual(self.entered, ["held", "foreground", "second", "third", "fourth"])
        self.assertEqual(self.queue._pending, {})
        self.assertEqual(self.runner.active_handles, ())

    async def test_delayed_head_does_not_block_eligible_work(self):
        delayed = self.start_job("delayed", not_before=self.clock.now() + timedelta(seconds=10))
        await self.until(lambda: "delayed" in self.queue._pending)
        ready = self.start_job("ready")
        self.assertEqual((await asyncio.wait_for(ready, 2)).unwrap().task.state, "succeeded")
        self.assertEqual(self.entered, ["ready"])
        self.clock.advance(timedelta(seconds=10))
        self.assertEqual((await asyncio.wait_for(delayed, 2)).unwrap().task.state, "succeeded")
        self.assertEqual(self.entered, ["ready", "delayed"])

    async def test_deadline_expires_while_capacity_remains_full(self):
        await self.occupy()
        short = self.start_job("short", deadline_at=self.clock.now() + timedelta(seconds=1))
        await self.until(lambda: "short" in self.queue._pending)
        self.clock.advance(timedelta(seconds=2))
        result = (await asyncio.wait_for(short, 2)).unwrap().task
        self.assertEqual((result.state, result.reason, result.attempt_no), ("expired", "deadline_before_start", 0))
        self.assertEqual(self.entered, ["held"])
        self.assertTrue(self.tasks.observe(self.context, "held").unwrap()["slot_held"])

    async def test_cancel_waiting_never_claims_or_releases_another_workers_slot(self):
        await self.occupy()
        queued = self.start_job("queued")
        await self.until(lambda: "queued" in self.queue._pending)
        queued.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await queued
        self.assertEqual((self.read_task("queued").state, self.read_task("queued").attempt_no), ("cancelled", 0))
        self.assertTrue(self.tasks.observe(self.context, "held").unwrap()["slot_held"])
        self.assertEqual(self.queue._pending, {})

    async def test_cancel_after_allocation_before_handoff_releases_only_unstarted_claim(self):
        held = await self.occupy()
        queued = self.start_job("queued")
        await self.until(lambda: "queued" in self.queue._pending)
        self.gates["held"].set()
        await held
        original = self.tasks.claim_task

        def cancel_allocated(context, task_id):
            result = original(context, task_id)
            if task_id == "queued" and result.is_success and result.unwrap().claim:
                queued.cancel()
            return result

        # A different caller can allocate the older waiter's claim first.
        with patch.object(self.tasks, "claim_task", cancel_allocated):
            following = self.start_job("following")
            with self.assertRaises(asyncio.CancelledError):
                await queued
            self.assertEqual((await asyncio.wait_for(following, 2)).unwrap().task.state, "succeeded")
        self.assertNotIn("queued", self.entered)
        self.assertFalse(self.tasks.observe(self.context, "queued").unwrap()["slot_held"])

    async def test_inputs_are_rechecked_before_dispatch_and_closing_cancels_waiters(self):
        held = await self.occupy()
        queued = self.start_job("queued")
        await self.until(lambda: "queued" in self.queue._pending)
        self.inputs_current = False
        self.gates["held"].set()
        await held
        failed = (await asyncio.wait_for(queued, 2)).unwrap().task
        self.assertEqual((failed.state, failed.reason, failed.attempt_no), ("failed", "input_expired", 0))
        self.assertNotIn("queued", self.entered)
        self.inputs_current = True
        future = self.start_job("future", not_before=self.clock.now() + timedelta(minutes=1))
        await self.until(lambda: "future" in self.queue._pending)
        self.assertEqual(await self.runner.close(), ())
        self.assertTrue(future.cancelled())
        self.assertEqual(self.read_task("future").state, "cancelled")

    async def test_duplicate_waiter_and_old_generation_cannot_execute_original_job(self):
        held = await self.occupy()
        queued = self.start_job("queued")
        await self.until(lambda: "queued" in self.queue._pending)
        duplicate = await self.runner.run(self.context, "queued")
        self.assertEqual(duplicate.failure.code, "task_already_waiting")
        self.assertEqual(self.read_task("queued").state, "created")
        new = self.supervisor()
        new.start(expected_generation=1).unwrap()
        fenced = await asyncio.wait_for(queued, 2)
        self.assertEqual(fenced.failure.code, "supervisor_fenced")
        self.assertNotIn("queued", self.entered)
        self.gates["held"].set()
        await held

    async def test_takeover_retires_only_previous_never_started_jobs_without_replaying(self):
        self.submit("orphaned", kind="fixture.background")
        self.submit("foreground")
        self.submit("started", kind="fixture.background")
        running = self.tasks.claim_task(self.context, "started").unwrap().claim
        self.assertIsNotNone(running)
        self.tasks.begin(running).unwrap()
        new = self.supervisor()
        new.start(expected_generation=1).unwrap()
        new.recover().unwrap()
        queue = BackgroundTaskQueue(new)
        queue.register({"fixture.background"})
        new.submit(self.spec("fresh", kind="fixture.background")).unwrap()
        self.assertEqual(queue.recover(), ("orphaned",))
        self.assertEqual(new.read(self.context, "orphaned").unwrap().state, "cancelled")
        self.assertEqual(new.read(self.context, "foreground").unwrap().state, "created")
        self.assertEqual(new.read(self.context, "fresh").unwrap().state, "created")
        self.assertEqual(new.read(self.context, "started").unwrap().state, "uncertain")
        self.assertTrue(new.observe(self.context, "started").unwrap()["slot_held"])
        self.assertEqual(queue.recover(), ())
        self.tasks.acknowledge_stopped(running, proof_ref="fixture-process-stopped").unwrap()


class BackgroundParallelWaitingTests(ExecutionFixture, unittest.IsolatedAsyncioTestCase):
    def supervisor(self, runtime=None, registrations=None, limits=None):
        entries = registrations or self.registrations
        other = TaskRegistration(replace(self.background, kind="fixture.other"), self.validate_inputs)
        return super().supervisor(runtime=runtime, registrations=entries + (other,),
                                  limits=replace(limits or self.limits, background_slots=2))

    async def test_scope_blocked_head_allows_other_kind_and_preserves_shared_limit(self):
        queue = BackgroundTaskQueue(self.tasks, interval=0.005)
        entered, release = asyncio.Queue(), asyncio.Event()

        async def handle(run):
            await entered.put(run.task.task_id)
            await release.wait()
            return TaskResult("succeeded")

        runner = ExactTaskRunner(self.tasks, frozenset({"fixture.background", "fixture.other"}), handle, waiting=queue)
        jobs = []
        try:
            for key, kind in (("held", "fixture.background"), ("blocked", "fixture.background"),
                              ("other", "fixture.other")):
                self.submit(key, kind=kind)
                jobs.append(asyncio.create_task(runner.run(self.context, key)))
            self.assertEqual(await asyncio.wait_for(entered.get(), 2), "held")
            self.assertEqual(await asyncio.wait_for(entered.get(), 2), "other")
            self.assertEqual((self.read_task("blocked").state, self.read_task("blocked").attempt_no), ("created", 0))
            self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM execution_attempts WHERE slot_held = 1", ())["n"], 2)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*jobs), 2)
            self.assertEqual(await asyncio.wait_for(entered.get(), 2), "blocked")
            self.assertEqual({r.unwrap().task.state for r in results}, {"succeeded"})
        finally:
            release.set()
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            await runner.close()


if __name__ == "__main__":
    unittest.main()
