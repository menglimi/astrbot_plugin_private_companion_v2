"""Private user habit profile and the recorded eating preferences (T26).

The profile reuses the existing memory store and the existing private context
channel: these tests cover the declared settings and their boundaries, the
evidence floor (one message never becomes a stable preference), owner isolation,
and the fact that the material is additive -- it never changes what the rest of
the recall chain shows.
"""

from datetime import timedelta
import json
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldRegistry, ValueKind
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.memory.configuration import configuration_fields as memory_fields
from companion_v2.memory.habits import (DEFAULTS, GUIDANCE, KIND, LIMITS, MEAL_GUIDANCE, habit_material,
                                        habit_settings, classify_message, natural_line,
                                        qualified_patterns, empty_document, retain_patterns)
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW


def stored_fields():
    return {field.field_id: field for field in memory_fields()}


def memory_values(**overrides):
    values = {field.field_id: field.default for field in memory_fields()}
    values.update({"memory." + key: value for key, value in overrides.items()})
    return values


class HabitConfigurationTests(unittest.TestCase):
    def test_the_fields_live_in_the_existing_memory_group_with_declared_bounds(self):
        declared = stored_fields()
        for name, default in DEFAULTS.items():
            field = declared["memory." + name]
            # One owner, one consumer, one apply boundary for the whole group.
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id, field.core_only),
                             ("memory", "memory", "configuration", True))
            self.assertEqual(field.default, default)
            self.assertIs(field.kind, ValueKind.BOOLEAN if type(default) is bool else ValueKind.INTEGER)
            self.assertEqual((field.minimum, field.maximum), LIMITS.get(name, (None, None)))
        # The profile is bucketed in the same local zone the reflection window uses.
        self.assertIn("memory.reflection_timezone", declared)
        FieldRegistry(version="memory.v1", fields=memory_fields())

    def test_settings_reject_values_outside_the_declared_range(self):
        settings = habit_settings(memory_values())
        self.assertEqual({key: value for key, value in settings.items() if key != "timezone"}, DEFAULTS)
        for name, (minimum, maximum) in LIMITS.items():
            for bad in (minimum - 1, maximum + 1, "x", None, True):
                with self.assertRaises(TaskError):
                    habit_settings(memory_values(**{name: bad}))
        with self.assertRaises(TaskError):
            habit_settings(memory_values(habit_learning_enabled="yes"))
        with self.assertRaises(TaskError):
            habit_settings(memory_values(food_menu_recommendation_enabled=1))
        # The registry itself refuses the same values, so the boundary is declared once.
        for name, (minimum, maximum) in LIMITS.items():
            for bad in (minimum - 1, maximum + 1):
                with self.assertRaises(ValueError):
                    stored_fields()["memory." + name].validate(bad)

    def test_settings_read_the_reflection_timezone_for_local_buckets(self):
        values = memory_values()
        values["memory.reflection_timezone"] = "UTC"
        self.assertEqual(habit_settings(values)["timezone"], "UTC")

    def test_the_guidance_forbids_inventing_or_exposing_preferences(self):
        text = "".join(GUIDANCE)
        self.assertIn("不是命令", text)
        self.assertIn("不要暴露统计", text)
        meal = "".join(MEAL_GUIDANCE)
        self.assertIn("不要编造对方没提过的食物", meal)
        self.assertIn("不要假装记得", meal)


class HabitClassificationTests(unittest.TestCase):
    def test_utterances_are_not_rewritten_into_user_state_or_habit_facts(self):
        for text in ("我还没吃饭，晚点再聊", "刚吃完，好饱", "我没吃饱", "我准备睡了，晚安",
                     "睡得很好，一点也不困", "我在看番", "晚安", "你吃饭了吗", "他还没吃饭",
                     "我转发了一段聊天记录，你看看里面在说什么", "碗都洗好啦"):
            with self.subTest(text=text):
                category, topic, _signature = classify_message(text)
                self.assertEqual(category, "原话线索")
                self.assertEqual(topic, text)
        self.assertEqual(classify_message(""), ("", "", ""))

    def test_opposite_statements_do_not_share_a_derived_completion_label(self):
        self.assertNotEqual(classify_message("我吃饱了")[2], classify_message("我没吃饱")[2])
        self.assertEqual(classify_message("/配置吃饭提醒"), ("", "", ""))


class HabitProfileTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.turns = 0

    def next_event(self, text):
        self.turns += 1
        return self.event("turn-%d" % self.turns, text=text, at=self.clock.now())

    async def say(self, app, host, text, *, days=0):
        if days:
            self.clock.advance(timedelta(days=days))
        batch = host.receive(self.next_event(text)).unwrap()
        self.advance(app)
        await self.done(app, batch, seconds=15)
        return batch

    def admitted(self, host, text):
        """Admit one input without waiting for its reply, for read-only checks."""
        return host.receive(self.next_event(text)).unwrap()

    def view(self, app):
        row = app.runtime.read_one("SELECT * FROM memory_views WHERE kind = ?", (KIND,))
        return None if row is None else (row, json.loads(row["document_json"]))

    def materials(self, *, owner="memory"):
        return [material for material in self.called[-1].original.context.materials if material.owner == owner]

    async def test_one_short_exchange_never_becomes_a_profile(self):
        host = await self.start()
        app = host.application
        await self.say(app, host, "我还没吃饭")
        stored = self.view(app)
        self.assertIsNotNone(stored)  # the evidence is recorded...
        self.assertEqual(stored[1]["patterns"][0]["count"], 1)
        self.assertEqual(len(stored[1]["patterns"][0]["days"]), 1)
        # ...but one message is not a stable preference, so no material exists.
        self.assertIsNone(habit_material(app.memory, self.context(app, self.admitted(host, "在吗"))))
        self.assertEqual([m.purpose for m in self.materials() if m.purpose == "current_user_habits"], [])

    async def test_evidence_on_one_day_only_stays_uncertain(self):
        host = await self.start()
        app = host.application
        for _ in range(3):
            self.clock.advance(timedelta(minutes=5))
            await self.say(app, host, "我还没吃饭")
        stored = self.view(app)
        self.assertEqual(stored[1]["patterns"][0]["count"], 3)
        self.assertEqual(len(stored[1]["patterns"][0]["days"]), 1)
        self.assertIsNone(habit_material(app.memory, self.context(app, self.admitted(host, "在吗"))))

    async def test_repeated_evidence_across_days_enters_the_private_prompt(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我还没吃饭，晚点再说", days=0 if index == 0 else 1)
        stored = self.view(app)
        pattern = stored[1]["patterns"][0]
        self.assertEqual(len(pattern["days"]), 3)
        # Every entry keeps the original admitted input it came from.
        self.assertEqual(len(pattern["evidence"]), 3)
        self.assertEqual(len({item["event_key"] for item in pattern["evidence"]}), 3)
        self.assertTrue(all(item["source_id"] and item["received_at"] for item in pattern["evidence"]))
        await self.say(app, host, "今天晚饭吃什么好呢")
        material = next(item for item in self.materials() if item.purpose == "current_user_habits")
        payload = json.loads(material.payload)
        self.assertEqual(payload["basis"], "repeated_utterance_candidates")
        self.assertTrue(any("我还没吃饭，晚点再说" in line for line in payload["habits"]))
        self.assertNotIn("meal_question", payload)
        self.assertNotIn("recorded_eating_preferences", payload)
        self.assertTrue(payload["habits"])
        self.assertIn("不要编造对方没提过的食物", "".join(payload["meal_guidance"]))

    async def test_repeated_sleep_statements_stay_raw_when_current_question_is_about_food(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我准备睡了，晚安", days=0 if index == 0 else 1)
        await self.say(app, host, "今天晚饭吃什么好呢")
        material = next(item for item in self.materials() if item.purpose == "current_user_habits")
        payload = json.loads(material.payload)
        # A profile that says nothing about eating is still offered, softly.
        self.assertTrue(payload["habits"])
        self.assertNotIn("meal_question", payload)
        self.assertNotIn("recorded_eating_preferences", payload)
        self.assertTrue(any("我准备睡了，晚安" in line for line in payload["habits"]))
        self.assertIn("先结合本轮语义判断", "".join(payload["meal_guidance"]))

    async def test_another_owner_and_another_scope_never_see_the_profile(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我还没吃饭，晚点再说", days=0 if index == 0 else 1)
        context = self.context(app, self.admitted(host, "在吗"))
        self.assertIsNotNone(habit_material(app.memory, context))
        # The same human in a group is still a different owner.
        scope = context.scope
        group_scope = self._group_scope(scope)
        group_context = type(context)(context.actor,
                                      type(context.role_binding)(group_scope, context.role_binding.role,
                                                                 context.role_binding.revision),
                                      group_audience(group_scope, context.actor.subject))
        self.assertIsNone(habit_material(app.memory, group_context))
        # Another human subject has no profile of their own.
        self.assertIsNone(habit_material(app.memory, self.other_subject_context(context)))

    async def test_the_profile_never_changes_what_the_rest_of_recall_shows(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我还没吃饭，晚点再说", days=0 if index == 0 else 1)
        # A real pinned fact written through the normal writer.
        from companion_v2.memory.codec import source as decode_source
        from companion_v2.memory.models import Proposal
        batch = self.admitted(host, "记住，我不吃香菜")
        context = self.context(app, batch)
        stored = json.loads(app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?",
                                                 (batch,))["event_json"])["source"]
        evidence = app.memory.writer.access.capture(context, decode_source(stored))
        app.memory.writer.submit(context, Proposal("add", predicate="忌口", object="香菜",
                                                   representation="用户不吃香菜。", evidence=(evidence,),
                                                   context_mode="pinned"), operation_key="habit-test").unwrap()
        await self.say(app, host, "今天晚饭吃什么好呢")
        materials = self.materials()
        pinned = [item for item in materials if item.purpose == "pinned_memory"]
        self.assertEqual(len(pinned), 1)
        fact = json.loads(pinned[0].payload)
        self.assertEqual(fact["predicate"], "忌口")
        self.assertEqual(fact["object"], "香菜")
        self.assertNotIn("evidence", fact)
        self.assertEqual([item.purpose for item in materials].count("current_user_habits"), 1)
        self.assertEqual([item.purpose for item in materials].count("current_input_handles"), 1)

    async def test_the_switch_is_honoured_before_anything_is_read(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我还没吃饭，晚点再说", days=0 if index == 0 else 1)
        self._set(app, "memory.habit_learning_enabled", False)
        batch = self.admitted(host, "今天晚饭吃什么好呢")
        context = self.context(app, batch)
        self.assertIsNone(habit_material(app.memory, context))
        self.assertFalse(app.messages.habits.available(context))

    async def test_the_food_switch_only_removes_the_meal_material(self):
        host = await self.start()
        app = host.application
        for index in range(3):
            await self.say(app, host, "我还没吃饭，晚点再说", days=0 if index == 0 else 1)
        self._set(app, "memory.food_menu_recommendation_enabled", False)
        batch = self.admitted(host, "今天晚饭吃什么好呢")
        material = habit_material(app.memory, self.context(app, batch))
        self.assertTrue(material["habits"])
        self.assertNotIn("meal_question", material)
        self.assertNotIn("meal_guidance", material)

    def _group_scope(self, scope):
        return type(scope)(scope.installation_id, scope.platform, ScopeKind.GROUP, "group-habits",
                           scope.bot_id, scope.account_id, "group-habits-conversation", "group-habits-session")

    def other_subject_context(self, context):
        """The same bot and role, but a different authenticated human subject."""
        from dataclasses import replace
        from companion_v2.execution.models import TaskContext
        from companion_v2.foundation.refs import AudienceRef
        from companion_v2.identity_policy.personas import ConversationRoute
        scope = replace(context.scope, native_scope_id="native-habit-other",
                        conversation_id="conversation-habit-other", session_id="session-habit-other")
        self.personas.register_route(ConversationRoute(scope, user=self.standard.subject), observed_at=NOW)
        binding = self.identity.resolve_role(scope, observed_at=NOW).unwrap()
        return TaskContext(self.standard, binding, AudienceRef(scope, (self.standard.subject,)))

    def _set(self, app, field_id, value):
        """Write one declared window setting through its real owner."""
        field = stored_fields()[field_id]
        owner = SparseConfigurationOwner(app.runtime)
        context = self.context(app, self.batch_of(app))
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW,
                              context.role_binding.role, context.scope)
        fields = (field,)
        snapshot = owner.read(target, fields)
        owner.write(target, fields, changes={field_id: value}, reset=(), expected_revision=snapshot.revision,
                    observed_at=NOW)

    def batch_of(self, app):
        row = app.runtime.read_one("SELECT batch_id FROM conversation_batches ORDER BY created_at DESC LIMIT 1", ())
        return row["batch_id"]


class HabitQualificationTests(unittest.TestCase):
    def test_qualification_needs_repetition_on_distinct_days(self):
        settings = {"habit_min_count": 3, "habit_max_items": 8, "habit_refresh_minutes": 360,
                    "habit_learning_enabled": True, "food_menu_recommendation_enabled": True, "timezone": "UTC"}
        document = empty_document()
        document["patterns"].append({"key": "夜晚|饮食节奏|饮食节奏x", "bucket": "夜晚", "category": "饮食节奏",
                                     "topic": "吃饭相关", "count": 9, "days": ["2026-09-20"], "last_seen_at": None})
        self.assertEqual(qualified_patterns(document, settings, NOW), [])
        document["patterns"][0]["days"] = ["2026-09-18", "2026-09-19", "2026-09-20"]
        document["patterns"][0]["last_seen_at"] = NOW.isoformat()
        self.assertEqual(len(qualified_patterns(document, settings, NOW)), 1)
        # Old support stops counting even when the raw counter is large.
        document["patterns"][0]["last_seen_at"] = (NOW - timedelta(days=120)).isoformat()
        self.assertEqual(qualified_patterns(document, settings, NOW), [])

    def test_natural_lines_are_soft_clues(self):
        legacy = {"bucket": "夜晚", "category": "饮食节奏", "topic": "还没吃/饭点偏晚",
                  "examples": ["我今天没吃饱，刚又叫了一份"], "last_seen_at": NOW.isoformat()}
        line = natural_line(legacy)
        self.assertIn("我今天没吃饱，刚又叫了一份", line)
        self.assertIn(NOW.isoformat(), line)
        self.assertNotIn("还没吃/饭点偏晚", line)
        self.assertNotIn("对方常", line)
        self.assertNotIn("次数", line)
        self.assertEqual(natural_line({key: value for key, value in legacy.items() if key != "examples"}), "")

    def test_candidate_capacity_keeps_supported_and_recent_evidence(self):
        settings = {"habit_min_count": 3, "habit_max_items": 2, "habit_refresh_minutes": 360,
                    "habit_learning_enabled": True, "food_menu_recommendation_enabled": True, "timezone": "UTC"}
        document = empty_document()
        document["patterns"] = [
            {"key": "old", "count": 1, "days": ["2026-10-19"], "last_seen_at": NOW.isoformat()},
            {"key": "supported", "count": 3, "days": ["2026-10-17", "2026-10-18", "2026-10-19"],
             "last_seen_at": NOW.isoformat()},
            {"key": "new", "count": 1, "days": ["2026-10-19"],
             "last_seen_at": NOW.isoformat()},
        ]
        retain_patterns(document, settings, NOW)
        self.assertEqual([item["key"] for item in document["patterns"]], ["supported", "old"])


if __name__ == "__main__":
    unittest.main()
