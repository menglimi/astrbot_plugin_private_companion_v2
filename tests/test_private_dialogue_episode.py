"""Private dialogue episodes as bounded material for the existing memory chain (T31).

The private episode is the group slice's abstract with a different scope: the
declared thresholds decide whether a window is worth summarising, a durable
cursor decides what has already been covered, and the result is offered to the
existing reflection as one more material instead of a second store.
"""

from datetime import timedelta
import json
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldRegistry, ValueKind
from companion_v2.execution.models import TaskError, stamp
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.memory.configuration import configuration_fields as memory_fields
from companion_v2.memory.episodes import (DEFAULTS, GUIDANCE, LIMITS, MAX_SOURCE_LINES, MAX_SUMMARY_CHARS,
                                          dialogue_episode_material, dialogue_settings, episode_cursor,
                                          episode_due, episode_namespace, mark_covered, recent_dialogue_lines,
                                          settings_for)
from companion_v2.memory.reflection import reflection_profile
from companion_v2.model_gateway.routing import configuration_fields
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW


def stored_fields():
    return {field.field_id: field for field in memory_fields()}


def memory_values(**overrides):
    values = {field.field_id: field.default for field in memory_fields()}
    values.update({"memory." + key: value for key, value in overrides.items()})
    return values


class FakeSettings:
    """A settings reader standing in for the memory group in pure checks."""

    def __init__(self, values=()):
        self.values = values

    def read(self, context):
        values = {field.field_id: field.default for field in memory_fields()}
        values.update({"memory." + key: value for key, value in dict(self.values).items()})
        return values, "token"


class DialogueEpisodeConfigurationTests(unittest.TestCase):
    def test_the_four_settings_live_in_the_existing_memory_group(self):
        declared = stored_fields()
        for name, default in DEFAULTS.items():
            field = declared["memory." + name]
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id, field.core_only),
                             ("memory", "memory", "configuration", True))
            self.assertEqual(field.default, default)
            self.assertIs(field.kind, ValueKind.BOOLEAN if type(default) is bool else ValueKind.INTEGER)
            self.assertEqual((field.minimum, field.maximum), LIMITS.get(name, (None, None)))
        FieldRegistry(version="memory.v1", fields=memory_fields())

    def test_bounds_are_the_declared_ones(self):
        self.assertEqual(dialogue_settings(memory_values()), DEFAULTS)
        for name, (minimum, maximum) in LIMITS.items():
            for bad in (minimum - 1, maximum + 1, "x", None, True):
                with self.assertRaises(TaskError):
                    dialogue_settings(memory_values(**{name: bad}))
        with self.assertRaises(TaskError):
            dialogue_settings(memory_values(dialogue_episode_memory_enabled="yes"))

    def test_the_guidance_keeps_the_two_speakers_apart(self):
        text = "".join(GUIDANCE)
        self.assertIn("严格区分说话人", text)
        self.assertIn("不要写成对方的事实", text)
        self.assertIn("没有新内容时不要产出条目", text)


class DialogueEpisodeMaterialTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.turns = 0
        self.profiles += (reflection_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="dialogue-episode-test.v1", fields=configuration_fields(self.profiles))

    async def say(self, app, host, text):
        self.turns += 1
        batch = host.receive(self.event("turn-%d" % self.turns, text=text, at=self.clock.now())).unwrap()
        self.advance(app)
        await self.done(app, batch, seconds=15)
        return batch

    async def talk(self, app, host, turns):
        batch = None
        for index in range(turns):
            batch = await self.say(app, host, "今天下班以后随便走走，顺便聊了聊最近身边发生的第 %d 件小事" % index)
        return batch

    def episode_window(self, *, hours=2):
        return {"start": stamp(NOW - timedelta(hours=hours)), "end": stamp(self.clock.now())}

    def material(self, app, context, window):
        return dialogue_episode_material(app.runtime, app.memory.settings, app.memory.writer.access,
                                         context, window)

    def set_field(self, app, context, field_id, value):
        field = stored_fields()[field_id]
        owner = SparseConfigurationOwner(app.runtime)
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW,
                              context.role_binding.role, context.scope)
        snapshot = owner.read(target, (field,))
        owner.write(target, (field,), changes={field_id: value}, reset=(),
                    expected_revision=snapshot.revision, observed_at=self.clock.now())

    async def test_thresholds_and_the_cycle_gate_the_material(self):
        host = await self.start()
        app = host.application
        batch = await self.talk(app, host, 4)
        context = self.context(app, batch)
        window = self.episode_window()
        lines = recent_dialogue_lines(app.runtime, app.memory.writer.access, context, window)
        self.assertEqual({line["speaker"] for line in lines}, {"user", "bot"})
        self.assertTrue(all(line["at"] for line in lines))
        # The cursor only moves forward, so the cases run oldest boundary first.
        # Only elapsed time: the minute trigger fires.
        self.set_field(app, context, "memory.dialogue_episode_refresh_messages", 64)
        mark_covered(app.runtime, context, {"end": stamp(self.clock.now() - timedelta(minutes=120))},
                     now=self.clock.now())
        material = self.material(app, context, window)
        self.assertEqual(material["trigger"], "minutes")
        self.assertEqual(material["namespace"], episode_namespace(context))
        self.assertEqual(material["max_summary_chars"], MAX_SUMMARY_CHARS)
        self.assertEqual(material["max_dialogue_episodes"], DEFAULTS["max_dialogue_episodes"])
        self.assertLessEqual(len(material["recent_dialogue"]), MAX_SOURCE_LINES)
        self.assertIn("严格区分说话人", "".join(material["guidance"]))
        # Too few new lines and too little time since the last covered boundary.
        mark_covered(app.runtime, context, {"end": stamp(NOW - timedelta(minutes=20))}, now=self.clock.now())
        self.assertIsNone(self.material(app, context, window))
        # Enough new messages inside the same span: the message trigger fires.
        self.set_field(app, context, "memory.dialogue_episode_refresh_messages", 8)
        material = self.material(app, context, window)
        self.assertEqual(material["trigger"], "messages")
        self.assertGreaterEqual(material["new_lines"], 8)
        # The window a landed batch already covered is never summarised again.
        mark_covered(app.runtime, context, {"end": window["end"]}, now=self.clock.now())
        self.assertIsNone(self.material(app, context, window))

    async def test_a_disabled_switch_or_a_wrong_scope_offers_nothing(self):
        host = await self.start()
        app = host.application
        batch = await self.talk(app, host, 3)
        context = self.context(app, batch)
        window = self.episode_window()
        self.assertIsNotNone(self.material(app, context, window))
        self.set_field(app, context, "memory.dialogue_episode_memory_enabled", False)
        self.assertIsNone(self.material(app, context, window))
        self.set_field(app, context, "memory.dialogue_episode_memory_enabled", True)
        group_scope = type(context.scope)(context.scope.installation_id, context.scope.platform, ScopeKind.GROUP,
                                          "group-episode", context.scope.bot_id, context.scope.account_id,
                                          "group-episode-conversation", "group-episode-session")
        group_context = type(context)(context.actor,
                                      type(context.role_binding)(group_scope, context.role_binding.role,
                                                                 context.role_binding.revision),
                                      group_audience(group_scope, context.actor.subject))
        with self.assertRaises(TaskError):
            settings_for(app.memory.settings, group_context)
        self.assertIsNone(self.material(app, group_context, window))
        # Another human subject shares neither the namespace nor the rows.
        other = self.other_subject_context(context)
        self.assertNotEqual(episode_namespace(context), episode_namespace(other))
        self.assertIsNone(self.material(app, other, window))

    def other_subject_context(self, context):
        """The same bot and role, but a different authenticated human subject."""
        from dataclasses import replace
        from companion_v2.execution.models import TaskContext
        from companion_v2.foundation.refs import AudienceRef
        from companion_v2.identity_policy.personas import ConversationRoute
        scope = replace(context.scope, native_scope_id="native-episode-other",
                        conversation_id="conversation-episode-other", session_id="session-episode-other")
        self.personas.register_route(ConversationRoute(scope, user=self.standard.subject), observed_at=NOW)
        return TaskContext(self.standard, self.identity.resolve_role(scope, observed_at=NOW).unwrap(),
                           AudienceRef(scope, (self.standard.subject,)))

    async def test_covered_material_is_not_gathered_again_after_a_restart(self):
        host = await self.start()
        app = host.application
        batch = await self.talk(app, host, 3)
        context = self.context(app, batch)
        window = self.episode_window()
        self.assertIsNotNone(self.material(app, context, window))
        mark_covered(app.runtime, context, window, now=self.clock.now())
        # A second handle on the same data root is what a restart sees.
        reopened = self.open_runtime()
        cursor = episode_cursor(reopened, context)
        self.assertEqual(cursor["covered_through"], window["end"])
        lines = recent_dialogue_lines(reopened, app.memory.writer.access, context, window)
        self.assertTrue(lines)
        self.assertIsNone(episode_due(cursor, lines, dialogue_settings(memory_values()), window))
        # The producer short-circuits before reading anything back.
        self.assertIsNone(dialogue_episode_material(reopened, FakeSettings(), None, context, window))

    async def test_the_episode_reaches_the_reflection_materials_and_covers_its_window(self):
        host = await self.start()
        app = host.application
        batch = await self.talk(app, host, 3)
        context = self.context(app, batch)
        prepared = app.memory_reflection.prepare(context, request_id="episode", start=NOW - timedelta(hours=2),
                                                 end=self.clock.now(), role_instruction="原角色人格提示").unwrap()
        seen = {}

        async def respond(envelope):
            from tests.test_role_tool_loop import answered
            from companion_v2.execution.models import encode
            if envelope.original.output_format != "memory_reflection":
                return answered("好的")
            seen["materials"] = envelope.original.context.materials
            return answered(encode({"summary": "本段私聊没有需要长期保留的新事实。", "proposals": [],
                                    "pending_decisions": []}))

        self.model_behavior = respond
        result = (await app.memory_reflection.run(context, prepared["batch_id"])).unwrap()
        self.assertEqual(result["state"], "complete", result)
        episodes = [item for item in seen["materials"] if item.owner == "dialogue.episode"]
        self.assertEqual(len(episodes), 1)
        payload = json.loads(episodes[0].payload)
        self.assertEqual(episodes[0].purpose, "recent_private_conversation")
        self.assertEqual({line["speaker"] for line in payload["recent_dialogue"]}, {"user", "bot"})
        self.assertEqual(payload["namespace"], episode_namespace(context))
        # Only after the batch landed does the durable cursor cover its window.
        self.assertEqual(episode_cursor(app.runtime, context)["covered_through"], payload["end"])
        self.assertIsNone(dialogue_episode_material(app.runtime, app.memory.settings, app.memory.writer.access,
                                                    context, {"start": payload["start"], "end": payload["end"]}))

    async def test_a_repaired_window_keeps_the_same_namespace(self):
        host = await self.start()
        app = host.application
        batch = await self.talk(app, host, 3)
        context = self.context(app, batch)
        window = self.episode_window()
        first = self.material(app, context, window)
        second = self.material(app, context, window)
        self.assertEqual(first["namespace"], second["namespace"])
        self.assertEqual(first["recent_dialogue"], second["recent_dialogue"])


if __name__ == "__main__":
    unittest.main()
