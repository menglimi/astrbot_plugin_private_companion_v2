"""Regression coverage for cycle observations, plan boundaries and independent provenance."""

import asyncio
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.state_context import ConversationStateContext
from companion_v2.execution.models import TaskError, encode
from companion_v2.role_work.state import cycle
from companion_v2.role_work.state.configuration import DEFAULTS
from companion_v2.role_work.state.cycle_prompts import INSTRUCTION, MAINTENANCE, PHASE_HINTS
from companion_v2.role_work.state.service import RoleStateService
from tests.test_management_access import NOW
from tests.test_role_cycle import assertion
from tests.test_role_state import StateFixture, state_data
from tests.test_role_tool_loop import answered


SETTINGS = DEFAULTS | {"enabled": True, "cycle_enabled": True, "cycle_mode": "six_phase",
                      "cycle_initialization": "first_day"}


class CyclePlanTests(unittest.TestCase):
    def view(self, clock, days):
        return cycle.project(clock, NOW + timedelta(days=days), discomfort_enabled=False)

    def test_length_change_after_many_cycles_starts_at_next_boundary_and_survives_offline(self):
        original = cycle.evolve(None, assertion(), SETTINGS, NOW)
        changed = cycle.evolve(original, assertion(), SETTINGS | {"cycle_follicular_days": 9}, NOW + timedelta(days=58))
        current = self.view(changed, 58)
        self.assertEqual((current["cycle_number"], current["cycle_day"], current["phase"]), (3, 3, "menstrual"))
        self.assertEqual(current["cycle_days"], 28)
        self.assertEqual(current["pending_plan"]["effective_date"], (NOW + timedelta(days=84)).date().isoformat())
        self.assertEqual(self.view(changed, 83)["cycle_day"], 28)
        boundary = self.view(changed, 84)
        self.assertEqual((boundary["cycle_number"], boundary["cycle_day"], boundary["cycle_days"]), (4, 1, 30))
        self.assertNotIn("pending_plan", boundary)
        restored = json.loads(encode(changed))
        later = self.view(restored, 149)
        self.assertEqual((later["cycle_number"], later["cycle_day"], later["phase"]), (6, 6, "follicular"))
        adopted = cycle.evolve(restored, None, SETTINGS | {"cycle_follicular_days": 9}, NOW + timedelta(days=149))
        self.assertEqual(self.view(adopted, 149), later)
        self.assertEqual(self.view(original, 58)["cycle_days"], 28)

    def test_pending_plan_can_be_revised_cancelled_and_replaced_after_it_takes_effect(self):
        original = cycle.evolve(None, assertion(), SETTINGS, NOW)
        pending = cycle.evolve(original, None, SETTINGS | {"cycle_follicular_days": 9}, NOW + timedelta(days=58))
        changed = cycle.evolve(pending, None, SETTINGS | {"cycle_pms_days": 4}, NOW + timedelta(days=70))
        self.assertEqual(self.view(changed, 84)["cycle_days"], 29)
        self.assertEqual(changed["pending_plan"]["effective_date"], pending["pending_plan"]["effective_date"])
        cancelled = cycle.evolve(changed, None, SETTINGS, NOW + timedelta(days=75))
        self.assertNotIn("pending_plan", self.view(cancelled, 75))
        self.assertEqual(self.view(cancelled, 85)["cycle_days"], 28)
        after = cycle.evolve(pending, None, SETTINGS | {"cycle_pms_days": 4}, NOW + timedelta(days=100))
        self.assertEqual((self.view(after, 100)["cycle_day"], self.view(after, 100)["cycle_days"]), (17, 30))
        self.assertEqual((self.view(after, 114)["cycle_number"], self.view(after, 114)["cycle_days"]), (5, 29))

    def test_legacy_clock_adopts_next_plan_without_rewriting_old_projection(self):
        legacy = {"schema": 1, "applicability": "applicable", "anchor_date": NOW.date().isoformat(),
                  "timezone": "Asia/Shanghai", "phases": cycle.phase_plan(SETTINGS),
                  "expression_prompt": "旧表达", "discomfort_enabled": False}
        before = self.view(legacy, 58)
        self.assertNotIn("decision_origin", before)
        current = cycle.evolve(legacy, None, SETTINGS | {"cycle_mode": "basic"}, NOW + timedelta(days=58))
        self.assertEqual(self.view(current, 58)["mode"], "six_phase")
        self.assertEqual(self.view(current, 84)["mode"], "basic")
        self.assertEqual(self.view(legacy, 58), before)

    def test_natural_start_is_persisted_once_and_has_varied_positions(self):
        settings = SETTINGS | {"cycle_initialization": "natural"}
        positions = set()
        for owner in range(32):
            clock = cycle.evolve(None, assertion(), settings, NOW, seed=str(owner))
            first = self.view(clock, 0)
            positions.add(first["cycle_day"])
            self.assertEqual(first["initialization"], "natural")
            self.assertTrue(1 <= first["cycle_day"] <= 28)
            restored = json.loads(encode(clock))
            updated = cycle.evolve(restored, assertion(), settings, NOW + timedelta(days=60), seed="changed binding")
            self.assertEqual(updated["anchor_date"], clock["anchor_date"])
            self.assertEqual(self.view(updated, 60)["cycle_day"], (first["cycle_day"] + 59) % 28 + 1)
        self.assertGreater(len(positions), 10)

    def test_unknown_initialization_has_no_invented_date_and_can_be_changed_before_anchoring(self):
        clock = cycle.evolve(None, assertion(), SETTINGS | {"cycle_initialization": "unknown"}, NOW)
        self.assertEqual(self.view(clock, 50)["applicability"], "applicable")
        self.assertNotIn("cycle_day", self.view(clock, 50))
        adopted = cycle.evolve(clock, None, SETTINGS, NOW + timedelta(days=50))
        self.assertEqual(self.view(adopted, 50)["cycle_day"], 1)
        manual = cycle.evolve(clock, None, SETTINGS, NOW, alignment={"applicability": "applicable", "day": 12})
        self.assertEqual(self.view(manual, 0)["cycle_day"], 12)


class CycleOptimizationFixture(StateFixture):
    def setup_cycle(self):
        self.host1, self.app, self.ctx, self.manager = self.setup_state()
        self.configure(self.manager, **{k: v for k, v in SETTINGS.items() if DEFAULTS[k] != v})

    def write(self, key, *, sources=(), **changes):
        current = self.app.role_state.records.get(self.ctx, "current")
        return self.app.role_state.write(self.ctx, data=state_data(**changes), sources=sources,
            expected_revision=current["revision"] if current else 0, operation_key=key)

    def align(self, applicability, day=None, key="align"):
        state = self.manager.status(self.core).unwrap()["state"]
        command = dict(action="cycle.align", operation_key=key, expected_revision=state["revision"],
                       view_token=state["view_token"], data={"applicability": applicability, "day": day})
        return self.manager.command(self.core, command).unwrap()

    def view(self):
        return self.app.role_state.read(self.ctx)

    async def ready(self):
        self.setup_cycle()
        self.app.state_maintenance.bind(self.ctx, "原角色人格提示")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE role_state_schedules SET next_at = ?", ((self.clock.now() + timedelta(days=1000)).isoformat(),))
        await self.start(self.host1)


class CycleProvenanceTests(CycleOptimizationFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.setup_cycle()

    async def test_manual_decision_is_stable_until_auto_release(self):
        self.align("not_applicable")
        self.configure(self.manager, cycle_discomfort_enabled=True)
        self.write("model-disagrees", cycle=assertion() | {"feeling": {"episode_id": None, "trend": "continuing"}},
                   conditions=[dict(kind="cycle", text="模拟腰酸", expires_at=None)])
        current = self.view()
        self.assertEqual(current["cycle_timeline"]["applicability"], "not_applicable")
        self.assertEqual(current["cycle_timeline"]["decision_origin"], "manual")
        self.assertIsNone(current["values"]["cycle"])
        self.assertEqual(current["values"]["conditions"], [])
        self.assertNotIn("cycle_feeling", current)
        self.align("auto", key="automatic")
        self.assertEqual(self.view()["cycle_timeline"]["decision_origin"], "model")
        self.write("automatic-applicable", cycle=assertion())
        self.assertEqual(self.view()["cycle_timeline"]["cycle_day"], 1)
        self.align("unknown", key="manual-unknown")
        self.write("still-unknown", cycle=assertion())
        self.assertEqual(self.view()["cycle_timeline"]["applicability"], "unknown")

    async def test_plan_and_natural_anchor_survive_a_reopened_service(self):
        self.configure(self.manager, cycle_initialization="natural")
        self.write("start", cycle=assertion())
        initial = self.view()["cycle_timeline"]
        self.clock.advance(timedelta(days=58))
        before = self.view()["cycle_timeline"]
        self.configure(self.manager, cycle_follicular_days=9)
        self.write("next-plan", cycle=assertion())
        pending = self.view()["cycle_timeline"]
        self.assertEqual((pending["cycle_day"], pending["cycle_number"]), (before["cycle_day"], before["cycle_number"]))
        self.clock.advance(timedelta(days=90))
        reopened = RoleStateService(self.app.tasks, self.app.configuration, self.app.role_state.life)
        later = reopened.read(self.ctx)["cycle_timeline"]
        self.assertEqual(later["anchor_date"], initial["anchor_date"])
        self.assertEqual(later["cycle_days"], 30)
        self.assertGreater(later["cycle_number"], pending["cycle_number"])

    async def test_real_anchor_evidence_revocation_still_invalidates_the_clock(self):
        source = self.source(self.app, self.ctx, "body-setting")
        self.write("initialize", sources=(source,), cycle=assertion())
        self.configure(self.manager, cycle_expression_prompt="自然相处")
        self.write("carry", mood="轻松")
        self.revoke_source(self.app, source)
        settings, _ = self.app.role_state.settings(self.ctx)
        self.assertIsNone(self.app.role_state.maintenance_cycle(self.ctx, settings, self.clock.now()))
        with self.assertRaises(TaskError):
            self.view()
        self.write("fresh", mood="重新观测")
        self.assertNotIn("cycle_timeline", self.view())

    async def test_legacy_clock_without_separate_sources_remains_conservative(self):
        source = self.source(self.app, self.ctx, "legacy-source")
        self.write("legacy", sources=(source,), cycle=assertion())
        record = self.app.role_state.records.get(self.ctx, "current")
        record.pop("cycle_sources")
        record["cycle_clock"].pop("decision_origin")
        record["cycle_clock"]["schema"] = 1
        record["reason"] = "cycle_alignment"
        previous, refs = self.app.role_state.cycles.previous(self.ctx, record)
        self.assertEqual(previous["decision_origin"], "manual")
        self.assertEqual(len(refs), 1)
        self.revoke_source(self.app, source)
        self.assertEqual(self.app.role_state.cycles.previous(self.ctx, record), (None, ()))

    async def test_feeling_continues_eases_becomes_uncertain_and_ends_without_resetting_start(self):
        self.configure(self.manager, cycle_discomfort_enabled=True)
        self.write("feeling-start", cycle=assertion(description="有一点腰酸") |
                   {"feeling": {"episode_id": None, "trend": "continuing"}})
        first = self.view()["cycle_feeling"]
        for trend in ("continuing", "easing", "uncertain", "ended"):
            before = self.view()["cycle_feeling"]
            self.clock.advance(timedelta(minutes=30))
            self.write(trend, cycle=assertion(description="沿用这一次感受") |
                       {"feeling": {"episode_id": first["episode_id"], "trend": trend}})
            current = self.view()["cycle_feeling"]
            self.assertEqual((current["episode_id"], current["started_at"]), (first["episode_id"], first["started_at"]))
            self.assertEqual(current["trend"], trend)
            self.assertGreater(current["observed_at"], before["observed_at"])
            if trend == "uncertain":
                self.assertEqual(current["last_confirmed_at"], before["last_confirmed_at"])
        with self.assertRaisesRegex(TaskError, "new episode"):
            self.write("resurrect", cycle=assertion() | {"feeling": {"episode_id": first["episode_id"], "trend": "easing"}})
        self.write("new-episode", cycle=assertion() | {"feeling": {"episode_id": None, "trend": "uncertain"}})
        self.assertNotEqual(self.view()["cycle_feeling"]["episode_id"], first["episode_id"])
        self.assertIsNone(self.view()["cycle_feeling"]["last_confirmed_at"])

    async def test_feeling_reference_validates_provenance_and_bad_contract_keeps_previous_state(self):
        self.align("applicable", 10)
        self.configure(self.manager, cycle_discomfort_enabled=True)
        source = self.source(self.app, self.ctx, "feeling-evidence")
        self.write("feeling", sources=(source,), cycle=assertion() |
                   {"feeling": {"episode_id": None, "trend": "continuing"}})
        before = self.app.role_state.records.get(self.ctx, "current")
        for feeling in ({"episode_id": "missing", "trend": "easing"}, {"episode_id": None, "trend": "cured"},
                        {"episode_id": [], "trend": "easing"}, {"episode_id": None, "trend": "easing", "pain": 3}):
            with self.assertRaises(TaskError):
                self.write("bad", cycle=assertion() | {"feeling": feeling})
            self.assertEqual(self.app.role_state.records.get(self.ctx, "current"), before)
        self.revoke_source(self.app, source)
        with self.assertRaises(TaskError):
            self.write("withdrawn", cycle=assertion() |
                       {"feeling": {"episode_id": before["cycle_feeling"]["episode_id"], "trend": "easing"}})
        self.write("new-observation", cycle=assertion() | {"feeling": {"episode_id": None, "trend": "uncertain"}})
        self.assertEqual(self.view()["cycle_timeline"]["cycle_day"], 10)
        self.configure(self.manager, cycle_discomfort_enabled=False)
        self.assertNotIn("cycle_feeling", self.view())

    async def test_observation_version_keeps_old_snapshot_contract_and_current_state_checks(self):
        with patch.object(self.app.role_state.records, "change", self.app.role_state.records.legacy.change):
            self.write("start", cycle=assertion())
        consumer = ConversationStateContext(self.app.role_state)
        current = consumer.capture(self.ctx, self.clock.now())
        legacy = {k: v for k, v in current.items() if k not in ("projection_version", "storage", "sleep", "source")}
        before = consumer.contributions(legacy, self.ctx, self.clock.now())
        self.assertNotIn("observed_at", json.loads(before[0].payload))
        self.clock.advance(timedelta(days=1))
        self.assertEqual(consumer.contributions(legacy, self.ctx, self.clock.now(), historical=True), before)
        with self.assertRaises(TaskError):
            consumer.contributions(legacy, self.ctx, self.clock.now())
        self.assertEqual(json.loads(consumer.contributions(current, self.ctx, self.clock.now())[0].payload)["observed_at"], current["captured_at"])
        self.write("human-change", mood="新观测")
        with self.assertRaises(TaskError):
            consumer.contributions(current, self.ctx, self.clock.now())


class CycleReplyTests(CycleOptimizationFixture, unittest.IsolatedAsyncioTestCase):
    async def test_generation_across_midnight_delivers_the_original_observation(self):
        self.clock.advance(timedelta(hours=15, minutes=59, seconds=57))
        await self.ready()
        self.write("start", cycle=assertion())
        async def respond(envelope):
            self.clock.advance(timedelta(seconds=5))
            return answered("这是代码问题的回答。")
        self.model_behavior = respond
        batch = self.host1.receive(self.event()).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual(len(self.sent), 1)
        material = next(m for m in self.called[0].original.context.materials if m.purpose == "role_state")
        self.assertEqual(json.loads(material.payload)["simulation"]["cycle_timeline"]["cycle_day"], 1)
        self.assertIn("observed_at", json.loads(material.payload))
        self.assertEqual(self.view()["cycle_timeline"]["cycle_day"], 2)
        self.assertTrue(all(item["body_available"] for item in self.app.messages.history(self.ctx).unwrap()["items"]))

    async def test_midnight_between_reply_parts_does_not_drop_the_second_part(self):
        self.clock.advance(timedelta(hours=15, minutes=59, seconds=57))
        await self.ready()
        self.write("start", cycle=assertion())
        async def send(envelope):
            if len(self.sent) == 1:
                self.clock.advance(timedelta(seconds=5))
            return self.receipt(envelope)
        self.send_behavior = send
        batch = self.host1.receive(self.event()).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual([part.text for part in self.sent], ["第一段", "第二段"])

    async def reject_change(self, action):
        await self.ready()
        source = self.source(self.app, self.ctx)
        self.write("start", sources=(source,), cycle=assertion())
        async def respond(envelope):
            if action == "align":
                self.align("applicable", 14)
            elif action == "revoke":
                self.revoke_source(self.app, source)
            else:
                self.configure(self.manager, enabled=False)
            return answered("旧材料生成的回答")
        self.model_behavior = respond
        batch = self.host1.receive(self.event()).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "blocked")
        self.assertEqual(self.sent, [])

    async def test_manual_alignment_during_generation_still_blocks(self):
        await self.reject_change("align")

    async def test_cycle_source_revocation_during_generation_still_blocks(self):
        await self.reject_change("revoke")

    async def test_state_permission_revocation_during_generation_still_blocks(self):
        await self.reject_change("disable")

    async def test_shared_maintenance_recovers_clock_after_unrelated_mood_withdrawal(self):
        await self.ready()
        self.align("applicable", 10)
        source = self.source(self.app, self.ctx, "unrelated-joke")
        self.write("mood", sources=(source,), mood="听了笑话很开心", cycle=None)
        self.revoke_source(self.app, source)
        self.clock.advance(timedelta(days=2))
        with self.assertRaises(TaskError):
            self.view()
        job = self.app.state_maintenance.prepare(self.ctx, "原角色人格提示", "probe")
        self.assertEqual(job["previous"]["state"], "unavailable")
        self.assertEqual(job["cycle_timeline"]["cycle_day"], 12)
        self.assertTrue(job["sources"])
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(cycle=assertion()))))
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "restore")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(self.view()["cycle_timeline"]["cycle_day"], 12)
        self.assertIsNone(self.view()["values"]["mood"])

    async def test_independent_clock_revocation_during_recovery_discards_the_result(self):
        await self.ready()
        clock_source = self.source(self.app, self.ctx, "body-setting")
        self.write("start", sources=(clock_source,), cycle=assertion())
        mood_source = self.source(self.app, self.ctx, "joke")
        self.write("mood", sources=(mood_source,), mood="开心")
        self.revoke_source(self.app, mood_source)
        async def respond(envelope):
            self.revoke_source(self.app, clock_source)
            return answered(encode(state_data(cycle=assertion())))
        self.model_behavior = respond
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "withdrawn")
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current")["revision"], 2)

    async def test_disabled_cycle_adds_no_full_instructions_in_maintenance_or_reply(self):
        await self.ready()
        self.configure(self.manager, cycle_enabled=False)
        self.write("hunger-only", hunger="有点饿")
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(hunger="有点饿"))))
        result = await self.app.state_maintenance.run(self.ctx, "原角色人格提示", "no-cycle")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertNotIn(INSTRUCTION, self.called[-1].original.instruction)
        self.assertNotIn(MAINTENANCE, self.called[-1].original.instruction)
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered("可以继续聊。"))
        batch = self.host1.receive(self.event()).unwrap()
        self.advance(self.app)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertNotIn(INSTRUCTION, self.called[-1].original.instruction)

    async def test_reply_hints_follow_applicability_and_only_describe_current_phase(self):
        await self.ready()
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered("继续讨论代码。"))
        for index, applicability in enumerate(("unknown", "not_applicable", "applicable")):
            self.write("state-" + applicability, cycle=assertion(applicability))
            batch = self.host1.receive(self.event("message-" + str(index))).unwrap()
            self.advance(self.app)
            self.assertEqual((await self.done(self.app, batch))["state"], "complete")
            instruction = self.called[-1].original.instruction
            if applicability == "applicable":
                self.assertIn(INSTRUCTION, instruction)
                self.assertIn(PHASE_HINTS["menstrual"], instruction)
                self.assertNotIn(PHASE_HINTS["pms"], instruction)
                self.assertNotIn(MAINTENANCE, instruction)
            else:
                self.assertNotIn(INSTRUCTION, instruction)


if __name__ == "__main__":
    unittest.main()
