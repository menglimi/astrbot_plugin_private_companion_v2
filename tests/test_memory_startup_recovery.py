"""Restart recovery of local memory checkpoints, with no provider replay."""

from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskError, encode
from companion_v2.foundation.outcome import Outcome
from companion_v2.memory import reflection_recovery
from companion_v2.memory.reflection import reflection_profile
from companion_v2.model_gateway.models import ProviderResponse
from companion_v2.model_gateway.routing import configuration_fields
from tests import test_memory_recovery as support
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered


class MemoryStartupRecoveryTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    setup_reflection = support.MemoryRecoveryTests.setup_reflection
    setup_manual = support.MemoryRecoveryTests.setup_manual
    configure = support.MemoryRecoveryTests.configure
    atoms = support.MemoryRecoveryTests.atoms

    def setUp(self):
        super().setUp()
        self.profiles += (reflection_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="memory-startup-test.v1", fields=configuration_fields(self.profiles))

    def row(self, app, batch_id):
        return app.runtime.read_one("SELECT * FROM memory_reflections WHERE batch_id = ?", (batch_id,))

    async def capture(self, app, context, batch_id, *, modelled=False):
        interruption = (patch.object(app.memory_reflection, "apply", return_value=Outcome.failed("interrupted", "fixture"))
                        if modelled else patch.object(reflection_recovery, "consume", side_effect=RuntimeError("power loss")))
        with interruption:
            await app.memory_reflection.run(context, batch_id)
        self.assertEqual(self.row(app, batch_id)["state"], "modelled" if modelled else "received")

    async def restart(self, app, *, generation=1):
        await app.close()
        host = await self.start(self.host(runtime=self.open_runtime()), task_generation=generation, model_generation=generation)
        return host.application

    async def recovered(self, app):
        await self.until(lambda: app.memory_schedule.recovery.state == "complete" or app.state == "faulted")
        self.assertEqual(app.state, "running", app.failure_code)
        return app.memory_schedule.recovery.report

    async def scheduled_checkpoint(self, *, completed=False):
        host, context, _ = await self.setup_reflection(prepare=False)
        app = host.application
        app.memory_schedule.configure(context, schedule_id="restart-daily", expected_revision=0,
                                      role_instruction="原角色人格提示").unwrap()
        row = dict(app.runtime.read_one("SELECT * FROM memory_schedules WHERE schedule_id = 'restart-daily'", ()))
        interruption = (patch.object(app.memory_schedule, "_settle") if completed else
                        patch.object(reflection_recovery, "consume", side_effect=RuntimeError("power loss")))
        with interruption:
            result = await app.memory_schedule._run(row, self.clock.now())
        self.assertEqual(result["state"], "complete" if completed else "received")
        return app, context, result["batch_id"], row

    async def test_restart_consumes_saved_output_without_manual_run_or_model_call(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"])
        calls, sends = len(self.called), len(self.sent)
        self.clock.advance(timedelta(minutes=11))
        app = await self.restart(host.application)
        await self.until(lambda: self.row(app, prepared["batch_id"])["state"] == "complete")
        self.assertEqual((len(self.called), len(self.sent)), (calls, sends))
        self.assertEqual(len(self.atoms(app)), 1)

    async def test_restart_applies_previously_validated_output(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"], modelled=True)
        calls = len(self.called)
        app = await self.restart(host.application)
        await self.recovered(app)
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "complete")
        self.assertEqual(len(self.atoms(app)), 1)
        self.assertEqual(len(self.called), calls)

    async def test_restart_after_first_item_commit_keeps_receipt_and_writes_only_remaining_item(self):
        host, context, prepared = await self.setup_reflection()
        app, original = host.application, self.model_behavior
        async def two_items(envelope):
            output = json.loads((await original(envelope)).draft.text)
            proposal = output["proposals"][0]["proposal"]
            output["proposals"].append({"item_id": "second", "proposal": {**proposal, "predicate": "早餐习惯"}})
            return answered(encode(output))
        self.model_behavior = two_items
        submit = app.memory.writer.submit
        def interrupt(context, proposal, *, operation_key, **options):
            if operation_key.endswith(":second"):
                raise RuntimeError("power loss after first committed item")
            return submit(context, proposal, operation_key=operation_key, **options)
        with patch.object(app.memory.writer, "submit", side_effect=interrupt):
            await app.memory_reflection.run(context, prepared["batch_id"])
        first = json.loads(self.row(app, prepared["batch_id"])["receipts_json"])["items"]["preference"]
        self.assertEqual(len(self.atoms(app)), 1)
        calls = len(self.called)
        app = await self.restart(app)
        await self.recovered(app)
        result = app.memory_reflection.status(context, prepared["batch_id"]).unwrap()
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["receipts"]["preference"], first)
        self.assertEqual(set(result["receipts"]), {"preference", "second"})
        self.assertEqual(len(self.atoms(app)), 2)
        self.assertEqual(len(self.called), calls)

    async def test_saved_daily_result_is_recovered_before_tomorrows_due_time(self):
        app, context, batch_id, schedule = await self.scheduled_checkpoint()
        calls = len(self.called)
        self.assertGreater(schedule["next_at"], self.clock.now().isoformat())
        app = await self.restart(app)
        await self.recovered(app)
        updated = app.runtime.read_one("SELECT * FROM memory_schedules WHERE schedule_id = 'restart-daily'", ())
        self.assertIsNone(updated["pending_batch"])
        self.assertEqual(updated["next_at"], schedule["next_at"])
        self.assertEqual(updated["covered_until"], json.loads(self.row(app, batch_id)["manifest_json"])["end"])
        self.assertEqual(len(self.atoms(app)), 1)
        self.assertEqual(len(self.called), calls)

    async def test_restart_finishes_daily_bookkeeping_after_memory_was_saved(self):
        app, _, batch_id, _ = await self.scheduled_checkpoint(completed=True)
        calls = len(self.called)
        app = await self.restart(app)
        await self.recovered(app)
        updated = app.runtime.read_one("SELECT * FROM memory_schedules WHERE schedule_id = 'restart-daily'", ())
        self.assertIsNone(updated["pending_batch"])
        self.assertEqual(updated["covered_until"], json.loads(self.row(app, batch_id)["manifest_json"])["end"])
        self.assertEqual(len(self.atoms(app)), 1)
        self.assertEqual(len(self.called), calls)

    async def test_bad_saved_output_enters_repair_queue_without_automatic_model_dispatch(self):
        host, context, prepared = await self.setup_reflection()
        async def invalid(_):
            return answered("{invalid")
        self.model_behavior = invalid
        await self.capture(host.application, context, prepared["batch_id"])
        calls = len(self.called)
        app = await self.restart(host.application)
        await self.recovered(app)
        result = app.memory_reflection.status(context, prepared["batch_id"]).unwrap()
        self.assertEqual(result["state"], "failed")
        self.assertTrue(result["captured"])
        self.assertTrue(result["retryable"])
        self.assertIsNone(result["repair_batch"])
        self.assertNotIn("raw_output", result)
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_preparation_does_not_authorize_execution_on_restart(self):
        host, _, prepared = await self.setup_reflection()
        calls = len(self.called)
        app = await self.restart(host.application)
        await self.recovered(app)
        row = self.row(app, prepared["batch_id"])
        self.assertEqual(row["state"], "prepared")
        self.assertIsNone(row["task_id"])
        self.assertEqual(len(self.called), calls)

    async def test_unknown_provider_return_is_not_replayed_on_restart(self):
        host, context, prepared = await self.setup_reflection()
        async def unknown(_):
            return ProviderResponse("unknown")
        self.model_behavior = unknown
        await host.application.memory_reflection.run(context, prepared["batch_id"])
        calls = len(self.called)
        app = await self.restart(host.application)
        await self.recovered(app)
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "running")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_withdrawn_source_is_quarantined_and_cannot_be_restored_from_saved_output(self):
        host, context, prepared = await self.setup_reflection()
        app = host.application
        await self.capture(app, context, prepared["batch_id"])
        from companion_v2.memory.codec import evidence
        source = evidence(json.loads(self.row(app, prepared["batch_id"])["manifest_json"])["evidence"][0]).source
        app.memory.writer.sources.revoke(source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        calls = len(self.called)
        app = await self.restart(app)
        report = await self.recovered(app)
        self.assertEqual(report["codes"], {"source_revoked": 1})
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "failed")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_disabled_memory_keeps_checkpoint_without_writing(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"])
        self.configure(host.application, context, enabled=False)
        calls = len(self.called)
        app = await self.restart(host.application)
        report = await self.recovered(app)
        self.assertEqual(report["codes"], {"memory_disabled": 1})
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "received")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_revoked_identity_keeps_checkpoint_without_writing(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"])
        self.identity.revoke_binding(self.important.binding_id, expected_revision=self.identity.revision,
                                     revoked_at=self.clock.now())
        calls = len(self.called)
        app = await self.restart(host.application)
        report = await self.recovered(app)
        self.assertEqual(report["codes"], {"binding_revoked": 1})
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "received")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_paused_daily_schedule_cannot_resume_its_captured_output(self):
        app, context, batch_id, _ = await self.scheduled_checkpoint()
        app.memory_schedule.configure(context, schedule_id="restart-daily", expected_revision=1,
                                      role_instruction="原角色人格提示", enabled=False).unwrap()
        calls = len(self.called)
        app = await self.restart(app)
        report = await self.recovered(app)
        self.assertIn("memory_schedule_changed", report["codes"])
        self.assertEqual(self.row(app, batch_id)["state"], "failed")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_unconfirmed_old_worker_blocks_both_startup_and_manual_resume(self):
        host, context, prepared = await self.setup_reflection()
        app = host.application
        await self.capture(app, context, prepared["batch_id"])
        with app.runtime.transaction() as connection:
            connection.execute("UPDATE execution_attempts SET slot_held = 1 WHERE task_id = ?",
                               (self.row(app, prepared["batch_id"])["task_id"],))
        calls = len(self.called)
        app = await self.restart(app)
        report = await self.recovered(app)
        self.assertEqual(report["codes"], {"memory_task_worker_not_stopped": 1})
        self.assertEqual((await app.memory_reflection.run(context, prepared["batch_id"])).failure.code,
                         "memory_task_worker_not_stopped")
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "received")
        self.assertEqual(len(self.called), calls)
        self.assertEqual(self.atoms(app), ())

    async def test_completed_repair_updates_parent_receipts_after_restart(self):
        host, context, prepared = await self.setup_manual()
        app, original = host.application, self.model_behavior
        async def invalid(_):
            return answered("{invalid")
        self.model_behavior = invalid
        await app.memory_reflection.run(context, prepared["batch_id"])
        child = app.memory_reflection.retry(context, prepared["batch_id"], request_id="parent-recovery").unwrap()
        self.model_behavior = original
        with patch.object(reflection_recovery, "finish_parent"):
            await app.memory_reflection.run(context, child["batch_id"])
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "failed")
        self.assertEqual(self.row(app, child["batch_id"])["state"], "complete")
        calls = len(self.called)
        app = await self.restart(app)
        await self.recovered(app)
        parent = app.memory_reflection.status(context, prepared["batch_id"]).unwrap()
        self.assertEqual(parent["state"], "complete")
        self.assertEqual(parent["receipts"], app.memory_reflection.status(context, child["batch_id"]).unwrap()["receipts"])
        self.assertEqual(len(self.called), calls)
        self.assertEqual(len(self.atoms(app)), 1)

    async def test_blocked_first_page_does_not_starve_a_later_checkpoint_and_scan_stops(self):
        host, context, prepared = await self.setup_reflection()
        app = host.application
        await self.capture(app, context, prepared["batch_id"])
        original = dict(self.row(app, prepared["batch_id"]))
        blocked_count = app.memory_schedule.recovery.PAGE_SIZE + 1
        with app.runtime.transaction() as connection:
            connection.execute("DELETE FROM memory_reflections WHERE batch_id = ?", (prepared["batch_id"],))
            for number in range(blocked_count):
                manifest = json.loads(original["manifest_json"])
                manifest["schedule_ref"] = {"schedule_id": "missing-schedule", "revision": 1}
                clone = {**original, "batch_id": "blocked-" + str(number), "manifest_json": encode(manifest)}
                connection.execute("INSERT INTO memory_reflections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(clone.values()))
            connection.execute("INSERT INTO memory_reflections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(original.values()))
        calls = len(self.called)
        app = await self.restart(app)
        steps, recovery = [], app.memory_schedule.recovery
        advance = recovery.advance
        def inspect_page():
            before = recovery.examined
            advance()
            steps.append(recovery.examined - before)
        with patch.object(recovery, "advance", side_effect=inspect_page):
            report = await self.recovered(app)
        self.assertEqual(report["blocked"], blocked_count)
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "complete")
        self.assertGreater(len(steps), 1)
        self.assertLessEqual(max(steps), recovery.PAGE_SIZE)
        with patch.object(app.runtime, "read_all") as reads:
            for _ in range(5):
                recovery.advance()
            reads.assert_not_called()
        self.assertEqual(len(self.called), calls)
        self.assertEqual(len(self.atoms(app)), 1)

    async def test_replaced_host_generation_cannot_commit_its_pending_scan(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"])
        calls = len(self.called)
        old = await self.restart(host.application)
        replacement = await self.start(self.host(runtime=self.open_runtime()), task_generation=2, model_generation=2)
        with self.assertRaises(TaskError):
            old.memory_schedule.recovery.advance()
        await self.recovered(replacement.application)
        self.assertEqual(old.memory_schedule.recovery.report["recovered"], 0)
        self.assertEqual(self.row(replacement.application, prepared["batch_id"])["state"], "complete")
        self.assertEqual(len(self.called), calls)

    async def test_stop_before_scan_leaves_no_worker_and_next_restart_can_resume(self):
        host, context, prepared = await self.setup_reflection()
        await self.capture(host.application, context, prepared["batch_id"])
        calls = len(self.called)
        app = await self.restart(host.application)
        shutdown = await app.close(grace_seconds=0)
        self.assertEqual(shutdown.state, "stopped")
        self.assertEqual(app.active_handles, ())
        self.assertEqual(app.memory_schedule.recovery.state, "stopped")
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "received")
        app = await self.restart(app, generation=2)
        await self.recovered(app)
        self.assertEqual(self.row(app, prepared["batch_id"])["state"], "complete")
        self.assertEqual(len(self.called), calls)


if __name__ == "__main__":
    unittest.main()
