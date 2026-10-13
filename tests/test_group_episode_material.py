"""Group episode settings and the bounded material folded into memory reflection.

The episode work integrates with the existing memory chain instead of adding a
parallel store: these tests cover the declared settings, the material's bounds,
and the fact that it is produced only from confirmed group deliveries.
"""

from dataclasses import replace
from datetime import timedelta
import unittest

from companion_v2.configuration.models import ApplyMode, ConfigLayer
from companion_v2.configuration.registry import FieldRegistry, ValueKind
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, stamp
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.group_audience import group_audience
from companion_v2.memory.episode_settings import (DEFAULTS, GROUP, GUIDANCE, LIMITS, MAX_SOURCE_LINES,
                                                  MAX_SUMMARY_CHARS, OWNER, configuration_fields,
                                                  episode_material, episode_namespace, episode_settings,
                                                  recent_group_lines, settings_for)
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW


class EpisodeSettingsTests(unittest.TestCase):
    def test_episode_fields_live_in_the_memory_group_with_one_owner(self):
        from companion_v2.memory.configuration import configuration_fields as memory_fields
        episode = configuration_fields()
        self.assertEqual([f.field_id for f in episode],
                         ["memory." + name for name in DEFAULTS])
        memory = {f.field_id: f for f in memory_fields()}
        for field in episode:
            # The memory extension owns these fields; the group keeps one contract.
            self.assertEqual(memory[field.field_id], field)
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id, field.core_only),
                             (GROUP, "memory", OWNER, True))
        self.assertIs(episode[0].kind, ValueKind.BOOLEAN)
        self.assertTrue(all(f.kind is ValueKind.INTEGER for f in episode[1:]))
        FieldRegistry(version="memory.v1", fields=memory_fields())

    def test_bounds_are_the_declared_ones(self):
        values = {f.field_id.removeprefix(GROUP + "."): f.default for f in configuration_fields()}
        self.assertEqual(episode_settings(values), DEFAULTS)
        declared = {f.field_id.removeprefix(GROUP + "."): (f.minimum, f.maximum) for f in configuration_fields()}
        for name, (minimum, maximum) in LIMITS.items():
            self.assertEqual(declared[name], (minimum, maximum))
            for bad in (minimum - 1, maximum + 1, "x", None, True):
                with self.assertRaises(TaskError):
                    episode_settings({**values, name: bad})
        with self.assertRaises(TaskError):
            episode_settings({**values, "group_episode_memory_enabled": "yes"})

    def test_the_material_forbids_reading_activity_as_a_member_fact(self):
        text = "".join(GUIDANCE)
        self.assertIn("不把它写成任何成员的事实", text)
        self.assertIn("不产生对成员的处理动作", text)


class EpisodeMaterialTests(MessageFixture, unittest.TestCase):
    def group_context(self):
        scope = replace(self.context.scope, kind=ScopeKind.GROUP, native_scope_id="group-ep",
                        conversation_id="group-ep-conversation", session_id="group-ep-session")
        return TaskContext(self.context.actor, replace(self.context.role_binding, scope=scope),
                           group_audience(scope, self.context.actor.subject))

    def manifest(self, *, minutes=180):
        return {"start": stamp(NOW - timedelta(minutes=minutes)), "end": stamp(NOW)}

    def confirmed_reply(self, context, text, *, at=None, sequence=1):
        """One confirmed group reply, written through the real delivery receipts."""
        at = at or NOW - timedelta(minutes=5)
        batch_id = "batch-ep-" + digest([text, stamp(at), sequence])
        part_id = "part-ep-" + digest([batch_id, sequence])
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO conversation_batches
                (batch_id, origin_key, context_json, role_instruction, state, revision, created_at,
                 contributions_json) VALUES (?, ?, ?, '', 'ready', 1, ?, '{}')""",
                (batch_id, context.key, encode(context), stamp(at)))
            connection.execute("""INSERT INTO conversation_parts
                (part_id, batch_id, sequence, text, payload_hash, state, receipt_ref, delivered_at)
                VALUES (?, ?, ?, ?, ?, 'delivered', ?, ?)""",
                (part_id, batch_id, sequence, text, digest(text), "receipt-" + part_id, stamp(at)))
            connection.execute("""INSERT INTO conversation_delivery_receipts
                (part_id, receipt_ref, receipt_json, observed_at) VALUES (?, ?, '{}', ?)""",
                (part_id, "receipt-" + part_id, stamp(at)))
        return part_id

    def test_a_group_namespace_is_stable_and_distinct_per_group(self):
        context = self.group_context()
        other = replace(context.scope, native_scope_id="group-ep-2", session_id="group-ep-2-session")
        other_context = TaskContext(context.actor, replace(context.role_binding, scope=other),
                                    group_audience(other, context.actor.subject))
        self.assertEqual(episode_namespace(context), episode_namespace(context))
        self.assertNotEqual(episode_namespace(context), episode_namespace(other_context))

    def test_a_private_scope_has_no_group_episode_material(self):
        # Settings and material are additive: a private turn simply produces nothing.
        with self.assertRaises(TaskError):
            settings_for(self.runtime, self.context)
        with self.assertRaises(TaskError):
            recent_group_lines(self.runtime, self.context, self.manifest())
        self.assertIsNone(episode_material(self.runtime, self.context, self.manifest()))

    def test_material_appears_only_once_enough_new_replies_exist(self):
        context = self.group_context()
        for index in range(3):
            self.confirmed_reply(context, "群里的第 %d 条消息" % index, sequence=index + 1)
        self.assertIsNone(episode_material(self.runtime, context, self.manifest()))
        for index in range(3, 12):
            self.confirmed_reply(context, "群里的第 %d 条消息" % index, sequence=index + 1)
        material = episode_material(self.runtime, context, self.manifest())
        self.assertIsNotNone(material)
        self.assertEqual(material["namespace"], episode_namespace(context))
        self.assertEqual(material["max_summary_chars"], MAX_SUMMARY_CHARS)
        self.assertEqual(material["refresh_minutes"], DEFAULTS["group_episode_refresh_minutes"])
        self.assertEqual(material["max_group_episodes"], DEFAULTS["max_group_episodes"])
        self.assertLessEqual(len(material["recent_group_replies"]), MAX_SOURCE_LINES)
        self.assertIn("群里的第 11 条消息", material["recent_group_replies"])
        self.assertIn("不把它写成任何成员的事实", "".join(material["guidance"]))

    def test_replies_outside_the_window_are_not_offered(self):
        context = self.group_context()
        for index in range(12):
            self.confirmed_reply(context, "窗口外的消息 %d" % index, at=NOW - timedelta(hours=9),
                                 sequence=index + 1)
        self.assertEqual(recent_group_lines(self.runtime, context, self.manifest()), ())
        self.assertIsNone(episode_material(self.runtime, context, self.manifest()))

    def test_a_disabled_setting_offers_no_material(self):
        context = self.group_context()
        for index in range(12):
            self.confirmed_reply(context, "群里的第 %d 条消息" % index, sequence=index + 1)
        self.assertIsNotNone(episode_material(self.runtime, context, self.manifest()))
        # The switch is a declared window setting, so it is honoured before any read.
        from companion_v2.configuration.models import ConfigTarget
        from companion_v2.memory.episode_settings import EpisodeConfigurationOwner
        owner = EpisodeConfigurationOwner(self.runtime)
        target = ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW,
                              context.role_binding.role, context.scope)
        fields = configuration_fields()
        owner.write(target, fields, changes={GROUP + ".group_episode_memory_enabled": False}, reset=(),
                    expected_revision=owner.read(target, fields).revision, observed_at=NOW)
        self.assertFalse(settings_for(self.runtime, context)["group_episode_memory_enabled"])
        self.assertIsNone(episode_material(self.runtime, context, self.manifest()))


if __name__ == "__main__":
    unittest.main()
