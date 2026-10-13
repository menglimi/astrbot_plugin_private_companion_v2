"""Optional phase variation stays reproducible across boundaries, sources and host restarts."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import unittest

from companion_v2.conversation.state_context import ConversationStateContext
from companion_v2.execution.models import TaskError, encode
from companion_v2.role_work.state import cycle
from companion_v2.role_work.state.cycle_prompts import VARIATION
from tests.test_management_access import NOW
from tests.test_role_cycle import assertion
from tests.test_role_cycle_optimization import CycleOptimizationFixture, SETTINGS
from tests.test_role_state import state_data
from tests.test_role_tool_loop import answered


VARIED = SETTINGS | {"cycle_variation_enabled": True}


def view(clock, days=0):
    return cycle.project(clock, NOW + timedelta(days=days), discomfort_enabled=False)


class CycleVariationClockTests(unittest.TestCase):
    def test_version_one_plans_survive_serialization_repeated_maintenance_and_long_offline_read(self):
        clock = cycle.evolve(None, assertion(), VARIED, NOW, seed="stable-role")
        original = encode(clock)
        # Fixed fixtures pin the saved algorithm version across subsequent code changes.
        expected = ([5, 7, 2, 2, 9, 3], [5, 7, 2, 2, 9, 3], [5, 7, 3, 2, 9, 2],
                    [4, 7, 2, 2, 9, 4], [5, 7, 2, 1, 9, 4])
        for index, lengths in enumerate(expected):
            observed = view(clock, 28 * index)
            self.assertEqual([p["days"] for p in observed["phase_plan"]], lengths)
            self.assertEqual((observed["cycle_number"], observed["cycle_day"]), (index + 1, 1))
            restored = json.loads(encode(clock))
            saved = cycle.evolve(restored, assertion(), VARIED, NOW + timedelta(days=28 * index), seed="rebound")
            self.assertEqual(saved["variation_plan"]["phases"], observed["phase_plan"])
            self.assertEqual(saved["variation_plan"]["cycle_number"], index + 1)
            self.assertEqual(view(saved, 28 * index), observed)
            self.assertEqual(cycle.evolve(saved, None, VARIED, NOW + timedelta(days=28 * index)), saved)
        self.assertEqual(encode(clock), original)  # Projection cannot alter the saved authority.
        self.assertEqual(view(json.loads(original), 28 * 10000 + 3)["cycle_number"], 10001)
        self.assertEqual(view(json.loads(original), 28 * 10000 + 3)["cycle_day"], 4)

    def test_variation_respects_phase_bounds_calendar_total_and_has_optional_unchanged_rounds(self):
        for mode in ("basic", "six_phase"):
            for days in (1, None, 30):
                settings = VARIED | {"cycle_mode": mode}
                if days is not None:
                    settings.update({"cycle_" + phase + "_days": days for phase in cycle.PHASES})
                clock = cycle.evolve(None, assertion(), settings, NOW, seed="stable-role")
                base = cycle.phase_plan(settings)
                total = sum(p["days"] for p in base)
                plans = set()
                for number in range(24):
                    projected = view(clock, number * total)
                    plan = projected["phase_plan"]
                    plans.add(tuple(p["days"] for p in plan))
                    self.assertEqual(sum(p["days"] for p in plan), total)
                    self.assertEqual((projected["cycle_day"], projected["cycle_number"]), (1, number + 1))
                    offsets = [p["days"] - b["days"] for p, b in zip(plan, base)]
                    self.assertLessEqual(sum(abs(offset) for offset in offsets), 2)
                    for item, offset in zip(plan, offsets):
                        self.assertLessEqual(abs(offset), 1)
                        minimum, maximum = (4, 120) if item["phase"] == "recovery" else (1, 30)
                        self.assertTrue(minimum <= item["days"] <= maximum)
                    elapsed = 0
                    for item in plan:
                        phase = view(clock, number * total + elapsed)
                        self.assertEqual((phase["phase"], phase["phase_day"], phase["phase_days"]),
                                         (item["phase"], 1, item["days"]))
                        elapsed += item["days"]
                        self.assertEqual(phase["next_phase_date"], (NOW + timedelta(days=number * total + elapsed)).date().isoformat())
                if days is None:
                    self.assertGreater(len(plans), 1)
                    self.assertIn(tuple(p["days"] for p in base), plans)
                else:
                    self.assertEqual(plans, {tuple(p["days"] for p in base)})

    def test_enabling_is_deferred_and_can_be_cancelled_without_changing_this_round(self):
        fixed = cycle.evolve(None, assertion(), SETTINGS, NOW, seed="stable-role")
        pending = cycle.evolve(fixed, None, VARIED, NOW + timedelta(days=58), seed="stable-role")
        before, after = view(fixed, 58), view(pending, 58)
        self.assertEqual({k: v for k, v in after.items() if k != "pending_plan"}, before)
        self.assertTrue(after["pending_plan"]["variation_enabled"])
        self.assertEqual(after["pending_plan"]["effective_date"], "2026-12-14")
        self.assertNotIn("phase_plan", view(pending, 83))
        self.assertTrue(view(pending, 84)["variation_enabled"])
        cancelled = cycle.evolve(pending, None, SETTINGS, NOW + timedelta(days=70))
        self.assertIsNone(cancelled["pending_plan"])
        self.assertEqual(view(cancelled, 84), view(fixed, 84))

    def test_disabling_and_reenabling_keep_current_plan_and_reuse_persisted_seed(self):
        clock = cycle.evolve(None, assertion(), VARIED, NOW, seed="stable-role")
        pending = cycle.evolve(clock, None, SETTINGS, NOW + timedelta(days=5))
        self.assertEqual(view(pending, 5)["phase_plan"], view(clock, 5)["phase_plan"])
        self.assertFalse(pending["pending_plan"]["variation_enabled"])
        self.assertNotIn("phase_plan", view(pending, 28))
        restored = cycle.evolve(pending, None, VARIED, NOW + timedelta(days=29), seed="new-binding")
        self.assertNotIn("phase_plan", view(restored, 29))
        self.assertEqual(restored["pending_plan"]["effective_date"], "2026-11-16")
        self.assertEqual(view(restored, 56)["phase_plan"], view(clock, 56)["phase_plan"])
        self.assertEqual(restored["variation_seed"], clock["variation_seed"])

    def test_length_mode_and_variation_changes_share_one_boundary_without_cycle_number_regression(self):
        clock = cycle.evolve(None, assertion(), VARIED, NOW, seed="stable-role")
        changed_settings = VARIED | {"cycle_follicular_days": 9, "cycle_mode": "basic"}
        pending = cycle.evolve(clock, None, changed_settings, NOW + timedelta(days=58))
        current = view(pending, 58)
        self.assertEqual((current["cycle_number"], current["cycle_day"], current["mode"]), (3, 3, "six_phase"))
        self.assertEqual(current["phase_plan"], view(clock, 58)["phase_plan"])
        later = view(pending, 149)
        self.assertEqual((later["cycle_number"], later["cycle_day"], later["cycle_days"], later["mode"]), (6, 6, 30, "basic"))
        adopted = cycle.evolve(pending, None, changed_settings, NOW + timedelta(days=149))
        self.assertEqual(view(adopted, 149), later)
        self.assertIsNone(adopted["pending_plan"])

    def test_existing_clock_with_pending_plan_and_missing_variation_fields_stays_fixed(self):
        legacy = {"schema": 2, "applicability": "applicable", "decision_origin": "model", "initialization": "first_day",
                  "anchor_date": NOW.date().isoformat(), "timezone": "Asia/Shanghai", "phases": cycle.phase_plan(SETTINGS),
                  "segment_start_date": NOW.date().isoformat(), "segment_start_number": 1,
                  "expression_prompt": "", "discomfort_enabled": False,
                  "pending_plan": {"effective_date": "2026-10-19", "cycle_number": 2,
                                   "phases": cycle.phase_plan(SETTINGS | {"cycle_follicular_days": 9})}}
        snapshot = encode(legacy)
        observed = view(legacy, 33)
        self.assertEqual((observed["cycle_day"], observed["cycle_number"], observed["cycle_days"]), (6, 2, 30))
        self.assertNotIn("variation_enabled", observed)
        self.assertNotIn("phase_plan", observed)
        updated = cycle.evolve(legacy, None, VARIED, NOW + timedelta(days=33))
        self.assertEqual({k: v for k, v in view(updated, 33).items() if k not in ("pending_plan", "phase_expression")}, observed)
        self.assertEqual(encode(legacy), snapshot)

    def test_unknown_and_manual_inapplicability_do_not_invent_a_phase_plan(self):
        for applicability in ("unknown", "not_applicable", "applicable"):
            clock = cycle.evolve(None, assertion(applicability), VARIED | {"cycle_initialization": "unknown"}, NOW)
            self.assertNotIn("variation_plan", clock)
            self.assertNotIn("phase_plan", view(clock, 30))
            self.assertNotIn("cycle_day", view(clock, 30))
        manual = cycle.evolve(None, None, VARIED, NOW, alignment={"applicability": "not_applicable", "day": None})
        automatic = cycle.evolve(manual, assertion(), VARIED, NOW)
        self.assertEqual(view(automatic)["applicability"], "not_applicable")
        self.assertNotIn("phase_plan", view(automatic))
        aligned = cycle.evolve(manual, None, VARIED, NOW, alignment={"applicability": "applicable", "day": 28})
        self.assertEqual(view(aligned)["cycle_day"], 28)
        self.assertTrue(view(aligned)["variation_enabled"])

    def test_dst_and_natural_initialization_follow_local_dates_with_varied_phases(self):
        at = datetime(2026, 3, 8, 5, tzinfo=timezone.utc)
        settings = VARIED | {"cycle_timezone": "America/New_York"}
        clock = cycle.evolve(None, assertion(), settings, at, seed="role")
        today = cycle.project(clock, at, discomfort_enabled=False)
        tomorrow = cycle.project(clock, at + timedelta(hours=23), discomfort_enabled=False)
        self.assertEqual(tomorrow["cycle_day"], 2)
        self.assertEqual(today["phase_plan"], tomorrow["phase_plan"])
        positions, plans = set(), set()
        for owner in range(20):
            natural = cycle.evolve(None, assertion(), VARIED | {"cycle_initialization": "natural"}, NOW, seed=owner)
            initial = view(natural)
            positions.add(initial["cycle_day"])
            plans.add(tuple(p["days"] for p in initial["phase_plan"]))
            self.assertTrue(1 <= initial["cycle_day"] <= initial["cycle_days"])
            self.assertEqual(view(json.loads(encode(natural))), initial)
        self.assertGreater(len(positions), 1)
        self.assertGreater(len(plans), 1)


class VariationHostFixture(CycleOptimizationFixture):
    async def ready_varied(self):
        self.setup_cycle()
        self.configure(self.manager, cycle_variation_enabled=True)
        self.app.state_maintenance.bind(self.ctx, "原角色人格提示")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE role_state_schedules SET next_at = ?", ((self.clock.now() + timedelta(days=1000)).isoformat(),))
        await self.start(self.host1)


class CycleVariationHostTests(VariationHostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_maintenance_preview_matches_saved_plan_when_unknown_dates_become_natural(self):
        await self.ready_varied()
        self.configure(self.manager, cycle_initialization="unknown")
        self.write("unknown-date", cycle=assertion())
        self.configure(self.manager, cycle_initialization="natural")
        job = self.app.state_maintenance.prepare(self.ctx, "原角色人格提示", "initial-preview")
        self.assertIn("phase_plan", job["cycle_timeline"])
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(cycle=assertion()))))
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "natural")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(self.view()["cycle_timeline"], job["cycle_timeline"])
        self.assertIn(VARIATION, self.called[-1].original.instruction)
        basis = next(m for m in self.called[-1].original.context.materials if m.purpose == "maintenance_basis")
        self.assertEqual(json.loads(basis.payload)["cycle_timeline"], job["cycle_timeline"])

    async def test_restarted_host_projects_saved_seed_without_replaying_model_or_writing_state(self):
        await self.ready_varied()
        self.write("initial", cycle=assertion())
        record = self.app.role_state.records.get(self.ctx, "current")
        self.clock.advance(timedelta(days=89))
        expected = self.view()["cycle_timeline"]
        await self.app.close()
        restarted = self.host()
        other = restarted.application
        await self.start(restarted, task_generation=1, model_generation=1)
        self.assertEqual(other.role_state.read(self.ctx)["cycle_timeline"], expected)
        self.assertEqual(other.role_state.records.get(self.ctx, "current"), record)
        self.assertEqual(self.called, [])
        self.assertEqual(self.sent, [])

    async def test_unrelated_mood_withdrawal_keeps_the_current_round_plan_and_seed(self):
        await self.ready_varied()
        self.align("applicable", 10)
        original = self.app.role_state.records.get(self.ctx, "current")["cycle_clock"]
        self.clock.advance(timedelta(days=30))
        expected = self.view()["cycle_timeline"]
        joke = self.source(self.app, self.ctx, "joke")
        self.write("new-round-mood", mood="听到笑话", sources=(joke,))
        self.revoke_source(self.app, joke)
        self.assertEqual(self.manager.status(self.core).unwrap()["state"]["state"], "unavailable")
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(cycle=assertion()))))
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "restore-plan")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(self.view()["cycle_timeline"], expected)
        saved = self.app.role_state.records.get(self.ctx, "current")["cycle_clock"]
        self.assertEqual(saved["variation_seed"], original["variation_seed"])
        self.assertEqual(saved["variation_plan"]["phases"], expected["phase_plan"])
        self.assertIsNone(self.view()["values"]["mood"])

    async def test_cycle_source_revocation_still_invalidates_newly_materialized_plans(self):
        await self.ready_varied()
        source = self.source(self.app, self.ctx, "body-setting")
        self.write("initialize", sources=(source,), cycle=assertion())
        self.clock.advance(timedelta(days=57))
        self.write("later-plan", cycle=assertion())
        self.assertEqual(self.view()["cycle_timeline"]["cycle_number"], 3)
        self.revoke_source(self.app, source)
        with self.assertRaises(TaskError):
            self.view()
        job = self.app.state_maintenance.prepare(self.ctx, "原角色人格提示", "withdrawn")
        self.assertIsNone(job["cycle_timeline"])

    async def test_generation_across_new_cycle_keeps_original_plan_and_history(self):
        self.clock.advance(timedelta(hours=15, minutes=59, seconds=57))
        await self.ready_varied()
        self.align("applicable", 28)
        original = self.view()["cycle_timeline"]
        async def respond(envelope):
            self.clock.advance(timedelta(seconds=5))
            return answered("代码可以这样写。")
        self.model_behavior = respond
        batch = self.host1.receive(self.event()).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual(len(self.sent), 1)
        reply = self.called[-1].original
        state = json.loads(next(m.payload for m in reply.context.materials if m.purpose == "role_state"))
        self.assertEqual(state["simulation"]["cycle_timeline"], original)
        self.assertIn(VARIATION, reply.instruction)
        self.assertEqual((self.view()["cycle_timeline"]["cycle_number"], self.view()["cycle_timeline"]["cycle_day"]), (2, 1))
        self.assertTrue(all(item["body_available"] for item in self.app.messages.history(self.ctx).unwrap()["items"]))

    async def test_failed_maintenance_and_forged_plan_fields_cannot_change_the_clock(self):
        await self.ready_varied()
        self.write("original", cycle=assertion())
        before = self.app.role_state.records.get(self.ctx, "current")
        self.configure(self.manager, cycle_variation_enabled=False)
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered("not json"))
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "failed")
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current"), before)
        for extra in ({"variation_seed": "model-chosen"}, {"phase_plan": []}, {"variation_enabled": True}):
            with self.assertRaises(TaskError):
                self.write("forged", cycle=assertion() | extra)
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current"), before)
        self.assertTrue(self.view()["cycle_timeline"]["variation_enabled"])

    async def test_historical_snapshot_and_operation_retry_keep_their_original_varied_plan(self):
        await self.ready_varied()
        payload = state_data(cycle=assertion())
        receipt = self.app.role_state.write(self.ctx, data=payload, expected_revision=0, operation_key="original")
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        historical = consumer.contributions(snapshot, self.ctx, self.clock.now())
        first_plan = self.view()["cycle_timeline"]["phase_plan"]
        self.clock.advance(timedelta(days=58))
        self.write("third-round", cycle=assertion())
        record = self.app.role_state.records.get(self.ctx, "current")
        replay = self.app.role_state.write(self.ctx, data=payload, expected_revision=0, operation_key="original")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation_id"], receipt["operation_id"])
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current"), record)
        self.assertEqual(consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True), historical)
        self.assertEqual(json.loads(historical[0].payload)["simulation"]["cycle_timeline"]["phase_plan"], first_plan)


if __name__ == "__main__":
    unittest.main()
