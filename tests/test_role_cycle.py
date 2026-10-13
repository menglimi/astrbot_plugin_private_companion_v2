"""Cycle continuity, provenance, management and persona use through the isolated host."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import unittest

from companion_v2.conversation.state_context import ConversationStateContext
from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.role_work.state import cycle
from companion_v2.role_work.state.configuration import DEFAULTS, GROUP, target_for
from companion_v2.role_work.state.service import RoleStateService
from tests.test_management_access import NOW
from tests.test_role_state import StateFixture, state_data
from tests.test_role_tool_loop import answered


def assertion(applicability="applicable", description="今天想放慢一点节奏"):
    return {"applicability": applicability, "description": description}


class CycleClockTests(unittest.TestCase):
    def test_phase_expression_follows_actual_phase_and_preserves_legacy_projection(self):
        at = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
        settings = DEFAULTS | {"cycle_enabled": True, "cycle_mode": "six_phase", "cycle_initialization": "first_day"}
        for index, phase in enumerate(cycle.PHASES):
            settings.update({f"cycle_{phase}_energy": index - 2, f"cycle_{phase}_mood": phase + " tone",
                             f"cycle_{phase}_prompt": phase + " preference"})
        clock = cycle.evolve(None, assertion(), settings, at)
        offset = 0
        for index, phase in enumerate(cycle.PHASES):
            with self.subTest(phase=phase):
                projection = cycle.project(clock, at + timedelta(days=offset), discomfort_enabled=False)
                self.assertEqual(projection["phase_expression"], {"energy_tendency": index - 2,
                    "mood_tone": phase + " tone", "prompt": phase + " preference"})
                offset += settings[f"cycle_{phase}_days"]
        legacy = dict(clock)
        legacy.pop("phase_expression")
        self.assertNotIn("phase_expression", cycle.project(legacy, at, discomfort_enabled=False))
        basic = cycle.evolve(None, assertion(), settings | {"cycle_mode": "basic"}, at)
        self.assertNotIn("phase_expression", cycle.project(basic, at, discomfort_enabled=False))

    def test_six_phases_and_multiple_cycles_follow_local_dates(self):
        at = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
        settings = DEFAULTS | {"cycle_enabled": True, "cycle_mode": "six_phase", "cycle_initialization": "first_day"}
        clock = cycle.evolve(None, assertion(), settings, at)
        for day, phase, phase_day, number in ((1, "menstrual", 1, 1), (5, "menstrual", 5, 1),
                (6, "follicular", 1, 1), (13, "pre_ovulation", 1, 1), (15, "ovulation", 1, 1),
                (17, "luteal", 1, 1), (26, "pms", 1, 1), (29, "menstrual", 1, 2), (58, "menstrual", 2, 3)):
            with self.subTest(day=day):
                value = cycle.project(clock, at + timedelta(days=day - 1), discomfort_enabled=False)
                self.assertEqual((value["phase"], value["phase_day"], value["cycle_number"]), (phase, phase_day, number))
        self.assertEqual(cycle.project(clock, at, discomfort_enabled=False)["next_phase_date"], "2026-09-06")

    def test_basic_mode_custom_lengths_and_dst_use_calendar_days(self):
        settings = DEFAULTS | {"cycle_enabled": True, "cycle_timezone": "America/New_York", "cycle_initialization": "first_day",
                              "cycle_menstrual_days": 3, "cycle_pms_days": 2}
        at = datetime(2026, 3, 8, 5, tzinfo=timezone.utc)  # Local midnight before the spring-forward day.
        clock = cycle.evolve(None, assertion(), settings, at)
        next_day = cycle.project(clock, at + timedelta(hours=23), discomfort_enabled=False)
        self.assertEqual((next_day["cycle_day"], next_day["cycle_days"]), (2, 25))
        later = cycle.project(clock, at + timedelta(days=3), discomfort_enabled=False)
        self.assertEqual((later["mode"], later["phase"], later["phase_day"]), ("basic", "recovery", 1))

    def test_discomfort_guidance_and_linked_energy_are_projected_as_soft_preferences(self):
        at = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
        settings = DEFAULTS | {"cycle_enabled": True, "cycle_mode": "six_phase", "cycle_initialization": "first_day",
            "cycle_discomfort_enabled": True, "cycle_discomfort_chance": 35,
            "cycle_discomfort_types": "腰酸,恶心", "cycle_link_intensity": True,
            "humanized_state_intensity": 100, "cycle_menstrual_energy": -12}
        clock = cycle.evolve(None, assertion(), settings, at)
        timeline = cycle.project(clock, at, discomfort_enabled=True)
        self.assertEqual(timeline["phase_expression"]["energy_tendency"], -24)
        self.assertEqual(timeline["discomfort_guidance"], {"reference_probability": 35, "types": ["腰酸", "恶心"]})


class CycleStateTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host1, self.app, self.ctx, self.manager = self.setup_state()
        self.configure(self.manager, enabled=True, cycle_enabled=True, cycle_mode="six_phase", cycle_initialization="first_day")

    def write(self, key, revision=0, **changes):
        return self.app.role_state.write(self.ctx, data=state_data(**changes), expected_revision=revision, operation_key=key)

    def align_command(self, *, day, applicability="applicable", key="align"):
        state = self.manager.status(self.core).unwrap()["state"]
        return dict(action="cycle.align", operation_key=key, expected_revision=state["revision"],
                    view_token=state["view_token"], data={"applicability": applicability, "day": day})

    async def test_legacy_text_remains_readable_and_does_not_invent_a_clock(self):
        self.write("legacy", cycle="旧版只记录的周期感受")
        state = self.app.role_state.read(self.ctx)
        self.assertNotIn("cycle_timeline", state)
        self.assertEqual(state["values"]["cycle"], "旧版只记录的周期感受")
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        self.write("structured", 1, cycle=assertion())
        self.clock.advance(timedelta(days=8))
        historical = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        self.assertEqual(json.loads(historical[0].payload)["simulation"], state)

    async def test_anchor_survives_new_services_normal_writes_and_off_on(self):
        self.write("start", cycle=assertion(), energy=44)
        original = self.app.role_state.read(self.ctx)["cycle_timeline"]
        self.clock.advance(timedelta(days=5))
        reopened = RoleStateService(self.app.tasks, self.app.configuration, self.app.role_state.life)
        self.assertEqual(reopened.read(self.ctx)["cycle_timeline"]["phase"], "follicular")
        reopened.write(self.ctx, data=state_data(cycle=None, energy=44), expected_revision=1, operation_key="ordinary")
        self.configure(self.manager, cycle_enabled=False)
        hidden = reopened.read(self.ctx)
        self.assertNotIn("cycle_timeline", hidden)
        self.assertIsNone(hidden["values"]["cycle"])
        reopened.write(self.ctx, data=state_data(), expected_revision=2, operation_key="while-disabled")
        self.clock.advance(timedelta(days=8))
        self.configure(self.manager, cycle_enabled=True)
        resumed = reopened.read(self.ctx)["cycle_timeline"]
        self.assertEqual(resumed["anchor_date"], original["anchor_date"])
        self.assertEqual((resumed["cycle_day"], resumed["phase"]), (14, "pre_ovulation"))

    async def test_applicability_is_explicit_and_clock_is_not_inferred_from_words(self):
        for revision, kind in enumerate(("unknown", "not_applicable", "applicable", "unknown", "applicable")):
            self.write("assert-" + str(revision), revision, cycle=assertion(kind))
            read = self.app.role_state.read(self.ctx)
            self.assertEqual(read["cycle_timeline"]["applicability"], kind)
            if kind != "applicable":
                self.assertNotIn("cycle_day", read["cycle_timeline"])
                self.assertIsNone(read["values"]["cycle"])
            else:
                self.assertEqual(read["cycle_timeline"]["cycle_day"], 1)

    async def test_manual_day_is_one_shot_replayed_after_other_edits_and_cas_protected(self):
        self.write("start", energy=54, cycle=assertion())
        command = self.align_command(day=15)
        self.manager.command(self.core, command).unwrap()
        state = self.app.role_state.read(self.ctx)
        self.assertEqual((state["cycle_timeline"]["phase"], state["values"]["energy"]), ("ovulation", 54))
        self.assertIsNone(state["values"]["cycle"])
        self.clock.advance(timedelta(days=2))
        self.write("later", 2, energy=55)
        self.assertTrue(self.manager.command(self.core, command).unwrap()["replayed"])
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"]["cycle_day"], 17)
        conflict = self.manager.command(self.core, command | {"operation_key": "different"})
        self.assertEqual(conflict.failure.code, "record_revision_conflict")
        self.assertFalse(self.manager.command(self.important, self.align_command(day=2)).is_success)
        for value in (0, 29, True, "2"):
            self.assertFalse(self.manager.command(self.core, self.align_command(day=value, key=str(value))).is_success)

    async def test_invalid_model_clock_fields_cannot_reset_existing_anchor(self):
        self.write("start", cycle=assertion())
        before = self.app.role_state.records.get(self.ctx, "current")
        for value in (assertion() | {"anchor_date": "2026-01-01"}, {"phase": "menstrual"},
                      assertion("guessed"), assertion(description=[])):
            with self.assertRaises(TaskError):
                self.write("invalid", 1, cycle=value)
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current"), before)

    async def test_discomfort_opt_in_expiry_and_disabled_projection(self):
        condition = {"kind": "cycle", "text": "短暂腰酸", "expires_at": (NOW + timedelta(hours=1)).isoformat()}
        self.write("start", cycle=assertion(), conditions=[condition])
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["conditions"], [])
        self.configure(self.manager, cycle_discomfort_enabled=True)
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["conditions"], [])
        self.write("enabled-discomfort", 1, cycle=assertion(), conditions=[condition])
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["conditions"], [condition])
        self.clock.advance(timedelta(hours=2))
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["conditions"], [])
        self.assertEqual(self.app.role_state.read(self.ctx)["expired_conditions"], 1)
        self.configure(self.manager, cycle_enabled=False)
        self.assertNotIn("cycle_timeline", self.app.role_state.read(self.ctx))

    async def test_changed_durations_are_previewed_before_maintenance_and_history_keeps_original_plan(self):
        self.write("start", cycle=assertion())
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        self.clock.advance(timedelta(days=3))
        self.configure(self.manager, cycle_menstrual_days=2, cycle_mode="basic", cycle_timezone="Europe/London")
        settings, _ = self.app.role_state.settings(self.ctx)
        preview = self.app.role_state.maintenance_cycle(self.ctx, settings, self.clock.now())
        self.assertEqual((preview["phase"], preview["cycle_day"], preview["timezone"]), ("menstrual", 4, "Asia/Shanghai"))
        self.assertEqual(preview["pending_plan"]["effective_date"], "2026-10-19")
        self.write("adopt-plan", 1, cycle=assertion())
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"], preview)
        original = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        timeline = json.loads(original[0].payload)["simulation"]["cycle_timeline"]
        self.assertEqual((timeline["mode"], timeline["phase_days"]), ("six_phase", 5))
        self.manager.command(self.core, self.align_command(day=4)).unwrap()
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"]["timezone"], "Europe/London")

    async def test_enabling_discomfort_keeps_previous_replies_under_their_original_preference(self):
        self.write("no-discomfort", cycle=assertion())
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        self.configure(self.manager, cycle_discomfort_enabled=True)
        self.write("new-preference", 1, cycle=assertion())
        saved = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        self.assertFalse(json.loads(saved[0].payload)["simulation"]["cycle_timeline"]["discomfort_enabled"])
        self.assertTrue(self.app.role_state.read(self.ctx)["cycle_timeline"]["discomfort_enabled"])

    async def test_phase_preferences_adopt_on_maintenance_and_history_keeps_original(self):
        self.configure(self.manager, mood_enabled=True, cycle_menstrual_energy=-20, cycle_menstrual_mood="安静",
                       cycle_menstrual_prompt="允许慢一点回应")
        self.write("phase-original", cycle=assertion(), energy=60, mood="平常")
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        original = self.app.role_state.read(self.ctx)
        self.configure(self.manager, cycle_menstrual_energy=0, cycle_menstrual_mood="",
                       cycle_menstrual_prompt="")
        self.assertEqual(self.app.role_state.read(self.ctx), original)
        settings, _ = self.app.role_state.settings(self.ctx)
        expected = {"energy_tendency": 0, "mood_tone": "", "prompt": ""}
        preview = self.app.role_state.maintenance_cycle(self.ctx, settings, self.clock.now())
        self.assertEqual(preview["phase_expression"], expected)
        self.write("phase-new", 1, cycle=assertion(), energy=60, mood="平常")
        reopened = RoleStateService(self.app.tasks, self.app.configuration, self.app.role_state.life)
        current = reopened.read(self.ctx)
        self.assertEqual(current["cycle_timeline"]["phase_expression"], expected)
        self.assertEqual((current["values"]["energy"], current["values"]["mood"]), (60, "平常"))
        historical = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        self.assertEqual(json.loads(historical[0].payload)["simulation"], original)

    async def test_withdrawal_propagates_across_clock_carry_without_explicit_sources(self):
        source = self.source(self.app, self.ctx)
        self.app.role_state.write(self.ctx, data=state_data(cycle=assertion()), expected_revision=0,
                                  operation_key="seed", sources=(source,))
        self.write("carry-clock", 1, energy=50)
        self.revoke_source(self.app, source)
        with self.assertRaises(TaskError):
            self.app.role_state.read(self.ctx)
        self.write("fresh", 2, mood="平静")
        self.assertNotIn("cycle_timeline", self.app.role_state.read(self.ctx))

    async def test_phase_progress_preserves_observation_but_disabling_still_rechecks_unsent(self):
        self.write("start", cycle=assertion())
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.ctx, NOW)
        self.clock.advance(timedelta(days=6))
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"]["phase"], "follicular")
        saved = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        self.assertEqual(json.loads(saved[0].payload)["simulation"]["cycle_timeline"]["phase"], "menstrual")
        current = consumer.contributions(snapshot, self.ctx, self.clock.now())
        self.assertEqual(current, saved)
        self.configure(self.manager, cycle_enabled=False)
        with self.assertRaises(TaskError):
            consumer.contributions(snapshot, self.ctx, self.clock.now())
        with self.assertRaises(TaskError):
            consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)

    async def test_cycle_configuration_contract_and_noncycle_edits_preserve_it(self):
        self.configure(self.manager, cycle_expression_prompt="经前更想独处，也仍愿意倾听。", cycle_menstrual_days=4)
        self.configure(self.manager, hunger_enabled=False)
        settings, _ = self.app.role_state.settings(self.ctx)
        self.assertEqual(settings["cycle_menstrual_days"], 4)
        self.assertIn("愿意倾听", settings["cycle_expression_prompt"])
        before = self.manager.status(self.core).unwrap()
        for changes in ({"cycle_mode": "guess"}, {"cycle_timezone": "Moon/Base"},
                {"cycle_menstrual_days": 0}, {"cycle_pms_days": 31}, {"cycle_discomfort_enabled": "yes"},
                {"cycle_discomfort_chance": -1}, {"cycle_discomfort_chance": 101},
                {"cycle_discomfort_types": "胃痛"}, {"cycle_discomfort_types": "痛经,痛经"},
                {"cycle_link_intensity": "yes"},
                {"cycle_expression_prompt": "长" * 2049}, {"cycle_initialization": "random_every_time"},
                {"cycle_pms_energy": -51}, {"cycle_pms_energy": 31}, {"cycle_pms_energy": True},
                {"cycle_pms_mood": "长" * 81}, {"cycle_pms_prompt": "长" * 513}):
            preview = self.app.configuration.preview_changes(self.core, target=target_for(self.ctx),
                group_id=GROUP, changes={GROUP + "." + key: value for key, value in changes.items()},
                observed_at=self.clock.now())
            self.assertFalse(preview.is_success, changes)
            result = self.manager.command(self.core, dict(action="configure", changes=changes,
                operation_key="bad-" + digest(changes), edit_token=before["edit_token"]))
            self.assertFalse(result.is_success, changes)
        self.assertEqual(self.manager.status(self.core).unwrap()["edit_token"], before["edit_token"])


class CycleHostTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def ready(self):
        host, app, context, manager = self.setup_state()
        self.configure(manager, enabled=True, cycle_enabled=True, cycle_mode="six_phase",
                       cycle_expression_prompt="经前愿意倾听，但可以更想安静。", cycle_initialization="first_day",
                       cycle_follicular_energy=0, cycle_follicular_mood="从容", cycle_follicular_prompt="慢慢恢复自己的节奏")
        app.state_maintenance.bind(context, "原角色人格提示")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE role_state_schedules SET next_at = ?", ((NOW + timedelta(days=100)).isoformat(),))
        await self.start(host)
        return host, app, context, manager

    async def test_maintenance_and_reply_use_original_persona_and_cycle_material(self):
        host, app, context, manager = await self.ready()
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(cycle=assertion()))))
        first = await app.state_maintenance.run(context, "原角色人格提示", "initialize-cycle")
        self.assertEqual(first["state"], "succeeded", first)
        self.clock.advance(timedelta(days=6))
        second = await app.state_maintenance.run(context, "原角色人格提示", "continue-cycle")
        self.assertEqual(second["state"], "succeeded", second)
        envelope = self.called[-1].original
        basis = json.loads(next(m.payload for m in envelope.context.materials if m.purpose == "maintenance_basis"))
        self.assertEqual(basis["cycle_timeline"]["phase"], "follicular")
        expected = {"energy_tendency": 0, "mood_tone": "从容", "prompt": "慢慢恢复自己的节奏"}
        self.assertEqual(basis["cycle_timeline"]["phase_expression"], expected)
        self.assertIn("不机械调整 energy", envelope.instruction)
        self.assertIn("愿意倾听", basis["settings"]["cycle_expression_prompt"])
        self.assertEqual(envelope.role_instruction, "原角色人格提示")
        self.assertIn("用户说‘我来例假’只属于用户", envelope.instruction)
        self.assertIn("不必机械拒绝", envelope.instruction)
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered("现在轻松一些了，可以慢慢聊。"))
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        reply = self.called[-1].original
        material = next(m for m in reply.context.materials if m.purpose == "role_state")
        self.assertEqual(json.loads(material.payload)["simulation"]["cycle_timeline"]["cycle_day"], 7)
        self.assertEqual(json.loads(material.payload)["simulation"]["cycle_timeline"]["phase_expression"], expected)
        self.assertIn("不是实际精力数值或必须执行的加减", reply.instruction)
        self.assertIn("无关话题不反复播报", reply.instruction)
        self.clock.advance(timedelta(days=25))
        self.assertTrue(all(item["body_available"] for item in app.messages.history(context).unwrap()["items"]))

    async def test_user_report_is_labelled_and_does_not_directly_initialize_role_clock(self):
        host, app, context, _ = await self.ready()
        batch = host.receive(self.event(text="我来例假了，有点不舒服。")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertIsNone(app.role_state.records.get(context, "current"))
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(state_data(cycle=assertion("unknown", None)))))
        result = await app.state_maintenance.run(context, "原角色人格提示", "user-report")
        self.assertEqual(result["state"], "succeeded", result)
        inputs = [m for m in self.called[-1].original.context.materials if m.purpose == "reported_conversation"]
        self.assertEqual(inputs[0].payload, "我来例假了，有点不舒服。")
        self.assertEqual(app.role_state.read(context)["cycle_timeline"]["applicability"], "unknown")
        self.assertNotIn("cycle_day", app.role_state.read(context)["cycle_timeline"])

    async def test_bad_json_and_restart_preserve_original_anchor_without_model_replay(self):
        host, app, context, _ = await self.ready()
        app.role_state.write(context, data=state_data(cycle=assertion()), expected_revision=0, operation_key="seed")
        original = app.role_state.records.get(context, "current")
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered("not json"))
        result = await app.state_maintenance.run(context, "原角色人格提示", "broken")
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(app.role_state.records.get(context, "current"), original)
        await app.close()
        self.clock.advance(timedelta(days=14))
        reopened = self.host()
        other = reopened.application
        await self.start(reopened, task_generation=1, model_generation=1)
        other.state_maintenance.advance()
        self.assertEqual(len(self.called), 1)
        read = other.role_state.read(context)["cycle_timeline"]
        self.assertEqual((read["phase"], read["cycle_day"]), ("ovulation", 15))
        self.assertEqual(other.role_state.records.get(context, "current"), original)


if __name__ == "__main__":
    unittest.main()
