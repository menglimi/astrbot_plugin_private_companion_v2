"""Mood axes, bounded updates, decay regression and tone injection contracts."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import AudienceRef, TaskContext, TaskError, encode
from companion_v2.foundation.refs import ScopeRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.identity_policy.private_domain import source_ref
from companion_v2.role_work.state import mood
from companion_v2.role_work.state.configuration import DEFAULTS, validate_mood_settings
from companion_v2.role_work.state.maintenance import state_profile
from tests.test_management_access import NOW, SCOPE
from tests.test_role_state import StateFixture, state_data
from tests.test_role_tool_loop import answered


def axes(**changes):
    return {"joy": 6, "anger": 1, "sorrow": 1, "fear": 1} | changes


def mood_data(**changes):
    return {"baseline": 6, **axes(), "intensity": "mild", "description": "平常"} | changes


class MoodModelTests(unittest.TestCase):
    def test_contract_accepts_text_null_and_complete_objects(self):
        self.assertIsNone(mood.validate(None))
        self.assertEqual(mood.validate("平静"), "平静")
        for payload in ({"baseline": 6, **axes(), "intensity": "strong"},
                        mood_data(intensity=None),
                        {**mood_data(), "description": None}):
            self.assertEqual(mood.validate(payload)["joy"], 6)
        for payload in ({"baseline": 6, **axes()}, mood_data(joy=0), mood_data(fear=11), mood_data(joy=6.0),
                        mood_data(intensity="none"), mood_data(description=" "), mood_data(extra=1), ""):
            with self.assertRaises(TaskError, msg=payload):
                mood.validate(payload)

    def test_neutral_band_ignores_a_plain_text_mood(self):
        quiet = mood_data(joy=2, anger=1, sorrow=1, fear=1)
        self.assertTrue(mood.neutral(quiet, 3))
        self.assertTrue(mood.neutral("平静", 3))
        self.assertFalse(mood.neutral(mood_data(joy=2, fear=4), 3))
        self.assertFalse(mood.neutral(mood_data(joy=2, fear=5), 4))

    def test_decay_moves_toward_the_baseline_by_a_half_life(self):
        previous = {"updated_at": NOW, "baseline": 6, "joy": 10, "anger": 7, "sorrow": 3, "fear": 1}
        one = mood.decayed(previous, 6, NOW + timedelta(minutes=90), 90)
        self.assertAlmostEqual(one["joy"], 8.0, places=3)
        self.assertAlmostEqual(one["anger"], 4.0, places=3)
        self.assertAlmostEqual(one["sorrow"], 2.0, places=3)
        self.assertAlmostEqual(one["fear"], 1.0, places=3)
        two = mood.decayed(previous, 6, NOW + timedelta(minutes=180), 90)
        self.assertAlmostEqual(two["joy"], 7.0, places=3)
        self.assertAlmostEqual(two["anger"], 2.5, places=3)
        self.assertEqual(mood.decayed(None, 6, NOW, 90),
                         {"joy": 6.0, "anger": 1.0, "sorrow": 1.0, "fear": 1.0})

    def test_acceleration_is_bounded_while_relaxation_is_not(self):
        previous = {"updated_at": NOW, "baseline": 6, "joy": 9, "anger": 1, "sorrow": 2, "fear": 1}
        later = NOW + timedelta(minutes=30)
        allowed = mood.bounds(previous, at=later, half_life_minutes=90, max_delta=2)["allowed"]
        # Relaxing toward the baseline by one bounded step stays available...
        self.assertAlmostEqual(allowed["joy"][0], 6.381, places=3)
        self.assertEqual(allowed["joy"][1], 10)
        # ...while a swing to the opposite extreme is refused.
        for joy in (10, 9, 8, 7):
            mood.validate_update(previous, mood_data(joy=joy), at=later, half_life_minutes=90, max_delta=2)
        for joy in (6, 4, 1):
            with self.assertRaises(TaskError):
                mood.validate_update(previous, mood_data(joy=joy), at=later, half_life_minutes=90, max_delta=2)
        with self.assertRaises(TaskError):
            mood.validate_update(previous, mood_data(anger=6), at=later, half_life_minutes=90, max_delta=2)
        # The first structured round may establish any value in range.
        mood.validate_update(None, mood_data(joy=2, fear=9), at=later, half_life_minutes=90, max_delta=2)

    def test_first_axes_are_accepted_only_once_a_record_carries_them(self):
        plain = mood.validate("平静")
        self.assertIsNone(mood.previous_axes(plain, None))
        document = mood.document(mood_data(joy=8), None, at=NOW, half_life_minutes=90, interest_level=2,
                                 cross_window=True)
        self.assertEqual(document["previous_axes"], None)
        self.assertEqual(document["interest_level"], 2)
        self.assertTrue(document["cross_window"])
        previous = mood.previous_axes(mood_data(joy=8), document)
        self.assertEqual(previous["joy"], 8)
        self.assertEqual(previous["updated_at"], NOW)
        projected = mood.project(mood_data(joy=8), document, at=NOW + timedelta(minutes=90),
                                 half_life_minutes=90, band=3, cross_window=False)
        self.assertEqual(projected["axes"]["joy"], 8)
        self.assertAlmostEqual(projected["reference"]["joy"], 7.0, places=3)
        self.assertFalse(projected["neutral"])

    def test_reply_tone_block_surfaces_decay_reference_and_mixed_emotions(self):
        mixed = mood_data(joy=8, sorrow=5, intensity="moderate", description="开心但又有点舍不得")
        dynamics = {"reference": {"joy": 6.5, "anger": 1.0, "sorrow": 2.8, "fear": 1.0}, "cross_window": False}
        text = mood.prompts.reply(mixed, dynamics, neutral=False)
        self.assertIn("随时间缓和后的当前参考：joy→6.5、sorrow→2.8", text)
        self.assertIn("当前喜悦与顾虑/低落并存", text)
        self.assertIn("开心但又有点舍不得", text)

    def test_mood_settings_are_closed_ranges(self):
        values = {name: DEFAULTS[name] for name in DEFAULTS}
        validate_mood_settings(values)
        for name, value in (("mood_interest_window_minutes", 4), ("mood_update_max_delta", 5),
                            ("mood_decay_half_life_minutes", 0), ("mood_neutral_band", 5),
                            ("mood_update_probability", 2)):
            with self.assertRaises(ConfigurationError, msg=name):
                validate_mood_settings(values | {name: value})


class MoodStateTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def ready(self, **changes):
        host, app, context, manager = self.setup_state()
        self.configure(manager, enabled=True, **changes)
        return host, app, context, manager

    async def test_structured_mood_is_stored_projected_and_bounded(self):
        _, app, context, _ = await self.ready(mood_enabled=True)
        app.role_state.write(context, data=state_data(mood=mood_data(joy=9, anger=5, description="被夸了但刚才有点急")),
                             expected_revision=0, operation_key="first")
        first = app.role_state.read(context)
        self.assertEqual(first["values"]["mood"]["joy"], 9)
        self.assertEqual(first["mood_dynamics"]["axes"]["joy"], 9)
        self.assertFalse(first["mood_dynamics"]["neutral"])
        self.assertIsNone(first["mood_dynamics"]["interest_level"])
        self.clock.advance(timedelta(minutes=45))
        drifted = app.role_state.read(context)
        self.assertLess(drifted["mood_dynamics"]["reference"]["joy"], 8.2)
        self.assertLess(drifted["mood_dynamics"]["reference"]["anger"], 5)
        self.assertGreater(drifted["mood_dynamics"]["reference"]["anger"], 1)
        # Numbers move by one bounded step, and an extreme swing is refused.
        app.role_state.write(context, data=state_data(mood=mood_data(joy=8, anger=3, description="余韵")),
                             expected_revision=1, operation_key="second")
        with self.assertRaises(TaskError):
            app.role_state.write(context, data=state_data(mood=mood_data(joy=2)), expected_revision=2,
                                 operation_key="swing")
        self.assertEqual(app.role_state.records.get(context, "current")["revision"], 2)

    async def test_legacy_text_and_operator_writes_stay_readable(self):
        _, app, context, _ = await self.ready(mood_enabled=True)
        app.role_state.write(context, data=state_data(mood="被这段话触动"), expected_revision=0,
                             operation_key="text")
        read = app.role_state.read(context)
        self.assertEqual(read["values"]["mood"], "被这段话触动")
        self.assertNotIn("mood_dynamics", read)
        # An explicit operator calibration is not a model step and may set any value.
        app.role_state.write(context, data=state_data(mood=mood_data(joy=10, fear=9, intensity="strong")),
                             expected_revision=1, operation_key="operator", operator=self.core)
        calibrated = app.role_state.read(context)
        self.assertEqual(calibrated["values"]["mood"]["fear"], 9)
        self.assertEqual(calibrated["mood_dynamics"]["axes"], axes(joy=10, fear=9))

    async def test_role_mood_follows_persona_even_when_its_input_was_window_scoped(self):
        host, app, context, _ = await self.ready(mood_enabled=True, mood_cross_window=False)
        source = self.source(app, context)
        app.role_state.write(context, data=state_data(mood=mood_data(joy=9, description="心情明朗")),
                             expected_revision=0, operation_key="one", sources=(source,))
        other = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b", session_id="session-b")
        self.personas.register_route(ConversationRoute(other, user=self.standard.subject), observed_at=NOW)
        # The simulation follows the persona, while the read capability remains
        # an explicit grant for each private window.
        self.grant(self.standard, other, "role.state.read")
        record = app.role_state.records.get(context, "current")
        roots = tuple(source_ref(item) for item in record["sources"])
        # The second window gets the role simulation, while the raw source remains private.
        self.assertEqual(app.role_state.records.storage(context), "role")
        self.assertNotEqual(roots[0].scope, other)
        self.assertFalse(app.role_state.evidence.shared(context, (source,)))
        second = TaskContext(self.standard, app.tasks.identity.resolve_role(other, observed_at=NOW).unwrap(),
                             AudienceRef(other, (self.standard.subject,)))
        self.assertFalse(app.role_state.evidence.visible(second, (source,), at=NOW))
        local = app.role_state.read(context)
        self.assertEqual(local["values"]["mood"]["joy"], 9)
        self.assertEqual(local["values"]["mood"]["description"], "心情明朗")
        self.assertTrue(local["mood_dynamics"]["axes"])
        shared = app.role_state.read(second)
        self.assertEqual(shared["values"]["mood"], local["values"]["mood"])
        self.assertEqual(shared["mood_dynamics"]["axes"], local["mood_dynamics"]["axes"])
        self.assertTrue(shared["mood_dynamics"]["cross_window"])

    async def test_disabled_mood_setting_hides_numbers_without_deleting_them(self):
        _, app, context, manager = await self.ready(mood_enabled=True)
        app.role_state.write(context, data=state_data(mood=mood_data(joy=7)), expected_revision=0,
                             operation_key="one")
        self.configure(manager, mood_enabled=False)
        read = app.role_state.read(context)
        self.assertIsNone(read["values"]["mood"])
        self.assertEqual(app.role_state.records.get(context, "current")["values"]["mood"]["joy"], 7)
        self.assertNotIn("mood_dynamics", read)


class MoodMaintenanceTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def ready(self, **changes):
        host, app, context, manager = self.setup_state()
        self.configure(manager, enabled=True, mood_enabled=True, **changes)
        app.state_maintenance.bind(context, "原角色人格提示")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE role_state_schedules SET next_at = ?", ((NOW + timedelta(days=1)).isoformat(),))
        await self.start(host)
        return host, app, context, manager

    def seed(self, app, context, payload):
        return app.role_state.write(context, data=state_data(mood=payload), expected_revision=0, operation_key="seed")

    async def test_probability_gate_holds_numbers_while_decay_still_appears(self):
        _, app, context, _ = await self.ready(mood_update_probability=0.0)
        self.seed(app, context, mood_data(joy=9))
        self.clock.advance(timedelta(minutes=30))
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(
            state_data(mood={**mood_data(joy=9), "description": "仍开心"}))))
        result = await app.state_maintenance.run(context, "原角色人格提示", "held")
        self.assertEqual(result["state"], "succeeded", result)
        instruction = self.called[0].original.instruction
        self.assertIn("本轮不做情绪数值更新", instruction)
        stored = app.role_state.read(context)["values"]["mood"]
        self.assertEqual((stored["joy"], stored["description"]), (9, "仍开心"))
        basis = json.loads([m for m in self.called[0].original.context.materials
                            if m.purpose == "maintenance_basis"][0].payload)
        self.assertEqual(basis["mood_settlement"]["numbers_may_move"], False)
        self.assertLess(basis["mood_settlement"]["reference"]["joy"], 9)

    async def test_open_round_receives_the_reference_and_may_move_one_step(self):
        _, app, context, _ = await self.ready(mood_update_probability=1.0)
        self.seed(app, context, mood_data(joy=9))
        self.clock.advance(timedelta(minutes=30))
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(
            state_data(mood={**mood_data(joy=10, intensity="moderate"), "description": "还在高兴"}))))
        result = await app.state_maintenance.run(context, "原角色人格提示", "open")
        self.assertEqual(result["state"], "succeeded", result)
        instruction = self.called[0].original.instruction
        self.assertIn("回落参考", instruction)
        self.assertIn("JSON 整数，禁止小数", instruction)
        self.assertIn("区间内选择整数", instruction)
        self.assertIn("超出会被拒绝", instruction)
        stored = app.role_state.read(context)["values"]["mood"]
        self.assertEqual(stored["joy"], 10)
        self.assertEqual(app.role_state.read(context)["mood_dynamics"]["axes"]["joy"], 10)

    async def test_first_structured_round_opens_and_unbounded_values_are_refused(self):
        _, app, context, manager = await self.ready(mood_update_probability=0.0)
        self.seed(app, context, "平静")
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(
            state_data(mood=mood_data(joy=2, fear=8, intensity="moderate", description="有点不安")))))
        result = await app.state_maintenance.run(context, "原角色人格提示", "first")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertIn("首次给出结构对象", self.called[0].original.instruction)
        self.assertEqual(app.role_state.read(context)["values"]["mood"]["fear"], 8)
        # A later round cannot jump past the bounded window even though the gate is open.
        self.clock.advance(timedelta(minutes=10))
        before = app.role_state.read(context)
        self.model_behavior = lambda env: asyncio.sleep(0, result=answered(encode(
            state_data(mood=mood_data(joy=2, fear=1, anger=6, sorrow=6, intensity="strong"),
                       energy=63, location="小屋里"))))
        result = await app.state_maintenance.run(context, "原角色人格提示", "jump")
        self.assertEqual(result["state"], "succeeded", result)
        # The invalid mood is isolated, while the rest of this maintenance round is saved.
        stored = app.role_state.read(context)
        self.assertEqual((stored["values"]["mood"]["joy"], stored["values"]["mood"]["fear"]), (2, 8))
        self.assertEqual(stored["values"]["mood"]["description"], "有点不安")
        self.assertEqual(stored["mood_dynamics"]["updated_at"], before["mood_dynamics"]["updated_at"])
        self.assertEqual((stored["values"]["energy"], stored["values"]["location"]), (63, "小屋里"))
        self.assertEqual(stored["revision"], 3)

    async def test_reply_gets_the_tone_block_only_for_structured_mood(self):
        host, app, context, _ = await self.ready(mood_update_probability=0.0)
        self.seed(app, context, mood_data(joy=9, fear=2, intensity="moderate", description="被夸得有点慌"))
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        instruction = self.called[0].original.instruction
        self.assertIn("情绪数值只影响角色的用词、节奏与情绪浓度", instruction)
        self.assertIn("joy=9", instruction)
        self.assertIn("被夸得有点慌", instruction)
        self.assertIn("四轴允许并存", instruction)
        self.assertNotIn("当前情绪处于中性带", instruction)
        materials = [m for m in self.called[0].original.context.materials if m.purpose == "role_state"]
        self.assertTrue(json.loads(materials[0].payload)["simulation"]["mood_dynamics"])
        self.assertEqual(self.called[0].original.role_instruction, "原角色人格提示")

    async def test_neutral_mood_keeps_tone_flat_and_plain_text_adds_nothing(self):
        host, app, context, _ = await self.ready(mood_update_probability=0.0)
        self.seed(app, context, mood_data(joy=2, anger=1, sorrow=1, fear=1, intensity="mild", description="很平静"))
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        instruction = self.called[0].original.instruction
        self.assertIn("当前情绪处于中性带", instruction)
        self.assertNotIn("语气滤镜", instruction)
        # A trusted operator can drop back to a plain text mood; no tone block is added at all.
        app.role_state.write(context, data=state_data(mood="平常"), expected_revision=1,
                             operation_key="plain", operator=self.core)
        batch2 = host.receive(self.event("event-2")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch2))["state"], "complete")
        self.assertNotIn("语气滤镜", self.called[-1].original.instruction)
        self.assertNotIn("中性带", self.called[-1].original.instruction)


if __name__ == "__main__":
    unittest.main()
