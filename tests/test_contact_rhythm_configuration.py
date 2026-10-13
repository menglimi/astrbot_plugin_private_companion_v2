"""Global rhythm and personal overrides survive chats without copying private data."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.proactive.configuration import GROUP, ContactConfigurationOwner, configuration_fields
from companion_v2.storage.runtime import StorageRuntime


class ContactRhythmConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-contact-rhythm-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "runtime"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id="rhythm-test")
        self.addCleanup(lambda: self.runtime.close())
        self.fields = configuration_fields()
        self.role = SubjectRef("rhythm-test", SubjectKind.BOT, "star")
        self.person = SubjectRef("rhythm-test", SubjectKind.HUMAN, "person-1")
        scope = ScopeRef("rhythm-test", "onebot", ScopeKind.PRIVATE, "private-1", bot_id="bot-1",
            account_id="account-1", conversation_id="conversation-1", session_id="session-1")
        self.window = ConfigTarget("rhythm-test", ConfigLayer.WINDOW, self.role, scope, subject=self.person)
        self.role_target = self.window.chain()[1]
        self.global_target = self.window.chain()[0]
        self.at = datetime(2026, 10, 10, tzinfo=timezone.utc)

    def write(self, target, values):
        self.at += timedelta(seconds=1)
        owner = SparseConfigurationOwner(self.runtime)
        snapshot = owner.read(target, self.fields)
        owner.write(target, self.fields, changes={GROUP + "." + key: value for key, value in values.items()},
            reset=(), expected_revision=snapshot.revision, observed_at=self.at)

    def read(self, target):
        return ContactConfigurationOwner(self.runtime).read(target, self.fields)

    def test_old_saved_rhythm_recovers_after_a_new_chat_or_participant_without_writes(self):
        self.write(self.window, {"enabled": True, "automatic_enabled": True, "quiet_enabled": True,
            "quiet_start": "22:30", "proactive_hour_activity_enabled": True,
            "note": "这是一位对象的私人备注", "important_dates": '[{"calendar":"solar","month":1,"day":1,"label":"私人日期"}]'})
        before = tuple(tuple(row) for row in self.runtime.read_all("SELECT * FROM configuration_values", ()))
        new_scope = replace(self.window.scope, conversation_id="new-conversation", session_id="new-session")
        other_scope = replace(new_scope, native_scope_id="private-2")
        other_person = replace(self.person, subject_id="person-2")
        for target in (self.global_target, self.role_target, replace(self.window, scope=new_scope),
                       replace(self.window, scope=other_scope, subject=other_person)):
            snapshot = self.read(target)
            self.assertTrue(snapshot.fields[GROUP + ".enabled"].value)
            self.assertTrue(snapshot.fields[GROUP + ".automatic_enabled"].value)
            self.assertTrue(snapshot.fields[GROUP + ".proactive_hour_activity_enabled"].value)
            self.assertEqual(snapshot.fields[GROUP + ".quiet_start"].value, "22:30")
            self.assertEqual(snapshot.fields[GROUP + ".note"].value, "")
            self.assertEqual(snapshot.fields[GROUP + ".important_dates"].value, "[]")
        after = tuple(tuple(row) for row in self.runtime.read_all("SELECT * FROM configuration_values", ()))
        self.assertEqual(before, after)

    def test_explicit_global_save_wins_over_old_public_window_values_and_survives_restart(self):
        self.write(self.window, {"enabled": True, "automatic_enabled": True, "quiet_start": "22:30"})
        self.write(self.global_target, {"enabled": False, "automatic_enabled": False, "quiet_start": "21:15"})
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id="rhythm-test")
        for target in (self.global_target, self.role_target, self.window,
                       replace(self.window, scope=replace(self.window.scope, conversation_id="fresh-conversation"))):
            snapshot = self.read(target)
            self.assertFalse(snapshot.fields[GROUP + ".enabled"].value)
            self.assertFalse(snapshot.fields[GROUP + ".automatic_enabled"].value)
            self.assertEqual(snapshot.fields[GROUP + ".quiet_start"].value, "21:15")
            self.assertEqual(snapshot.fields[GROUP + ".enabled"].source, self.global_target)
            self.assertEqual(snapshot.fields[GROUP + ".enabled"].explicit, target == self.global_target)

    def test_personal_preferences_override_global_defaults_without_changing_other_users(self):
        self.write(self.window, {"enabled": True})
        relationship = self.window.chain()[2]
        self.write(relationship, {"enabled": False, "note": "私人备注"})
        self.assertFalse(self.read(self.window).fields[GROUP + ".enabled"].value)
        self.write(self.global_target, {"enabled": True})
        self.assertFalse(self.read(self.window).fields[GROUP + ".enabled"].value)
        other = replace(self.window, subject=replace(self.person, subject_id="person-2"),
            scope=replace(self.window.scope, native_scope_id="private-2", conversation_id="new-conversation"))
        self.assertTrue(self.read(other).fields[GROUP + ".enabled"].value)
        self.assertEqual(self.read(other).fields[GROUP + ".note"].value, "")
        changed_chat = replace(self.window, scope=replace(self.window.scope, conversation_id="fresh-conversation"))
        self.assertFalse(self.read(changed_chat).fields[GROUP + ".enabled"].value)
        self.assertEqual(self.read(self.window).fields[GROUP + ".note"].value, "私人备注")

    def test_global_legacy_recovery_is_shared_across_bots_and_roles_and_preserves_saved_false(self):
        self.write(self.window, {"enabled": True})
        newest = replace(self.window, scope=replace(self.window.scope, conversation_id="newer"))
        self.write(newest, {"enabled": False})
        self.assertFalse(self.read(self.role_target).fields[GROUP + ".enabled"].value)
        for target in (replace(self.role_target, bot_id="another-bot"),
                       replace(self.role_target, role=replace(self.role, subject_id="another-role"))):
            value = self.read(target).fields[GROUP + ".enabled"]
            self.assertFalse(value.value)
            self.assertEqual(value.source, self.global_target)
        self.write(newest, {"enabled": True})
        self.assertTrue(self.read(replace(self.role_target, bot_id="another-bot")).fields[GROUP + ".enabled"].value)
        foreign = ConfigTarget("foreign-installation", ConfigLayer.INSTALLATION)
        self.assertIsNone(self.read(foreign).fields[GROUP + ".enabled"].source)

    def test_global_save_replaces_legacy_role_defaults_while_personal_overrides_still_win(self):
        self.write(self.role_target, {"enabled": True, "max_contacts_24h": 9, "chat.weight": 2.0})
        self.assertTrue(self.read(self.window).fields[GROUP + ".enabled"].value)
        self.write(self.global_target, {"enabled": False, "max_contacts_24h": 3, "chat.weight": 1.2})
        for target in (self.role_target, self.window, self.window.chain()[2]):
            snapshot = self.read(target)
            self.assertFalse(snapshot.fields[GROUP + ".enabled"].value)
            self.assertEqual(snapshot.fields[GROUP + ".max_contacts_24h"].value, 3)
            self.assertEqual(snapshot.fields[GROUP + ".chat.weight"].value, 1.2)
        self.write(self.window.chain()[2], {"enabled": True, "max_contacts_24h": 4})
        personal = self.read(self.window)
        self.assertTrue(personal.fields[GROUP + ".enabled"].value)
        self.assertEqual(personal.fields[GROUP + ".max_contacts_24h"].value, 4)
        self.assertEqual(personal.fields[GROUP + ".chat.weight"].value, 1.2)
