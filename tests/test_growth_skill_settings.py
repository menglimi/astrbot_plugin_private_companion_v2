"""Growth skill configuration: parsing, role-window sharing, and registry contract."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.role_work.growth.configuration import (INFLUENCE_NOTES, SKILL_FIELDS, SKILLS_GROUP,
                                                         SkillConfigurationOwner, configuration_fields,
                                                         custom_skills, skill_configuration_fields,
                                                         skill_settings)
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION, NOW

SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a",
                 "conversation-a", "session-a")
OTHER_SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a",
                       "conversation-b", "session-b")
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-a")
OTHER_ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")


class GrowthSkillTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="companion-v2-growth-skills-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.owner = SkillConfigurationOwner(self.runtime)

    def context(self, scope=SCOPE, role=ROLE):
        return SimpleNamespace(scope=scope, role_binding=SimpleNamespace(role=role))

    def target(self, scope=SCOPE, role=ROLE, layer=ConfigLayer.WINDOW):
        # Only window targets carry a scope; a role target is the role and the bot.
        if layer is ConfigLayer.ROLE:
            return ConfigTarget(INSTALLATION, layer, role, None)
        return ConfigTarget(INSTALLATION, layer, role, scope)

    def set_skills(self, value, strength=0, *, scope=SCOPE, role=ROLE, layer=ConfigLayer.WINDOW):
        fields = tuple(f for f in SKILL_FIELDS)
        target = self.target(scope, role, layer)
        snapshot = self.owner.read(target, fields)
        return self.owner.write(target, fields,
            changes={SKILLS_GROUP + ".custom_skills": value,
                     SKILLS_GROUP + ".schedule_influence_strength": strength},
            reset=(), expected_revision=snapshot.revision, observed_at=NOW)

    def test_custom_skills_parsing(self):
        self.assertEqual(custom_skills('["写作", "吉他"]'), ("写作", "吉他"))
        self.assertEqual(custom_skills("写作、吉他， 编曲"), ("写作", "吉他", "编曲"))
        self.assertEqual(custom_skills(""), ())
        self.assertEqual(custom_skills("[]"), ())
        self.assertEqual(custom_skills("not json {"), ("not json {",))
        self.assertEqual(custom_skills(json.dumps(["a" * 40])), ("a" * 24,))
        many = custom_skills(json.dumps([str(i) for i in range(12)]))
        self.assertEqual(many, tuple(str(i) for i in range(8)))

    def test_the_two_groups_are_registered_separately_with_their_own_layers(self):
        permissions = configuration_fields()
        skills = skill_configuration_fields()
        self.assertEqual({f.field_id for f in permissions},
                         {"role.growth.read_enabled", "role.growth.proposals_enabled"})
        self.assertEqual({f.field_id for f in skills},
                         {SKILLS_GROUP + ".custom_skills", SKILLS_GROUP + ".schedule_influence_strength"})
        # Permissions stay window-only: a grant is issued per participant.
        self.assertTrue(all(f.layers == (ConfigLayer.WINDOW,) for f in permissions))
        # Skill content may be set at either layer, like role.life.
        self.assertTrue(all(f.layers == (ConfigLayer.WINDOW, ConfigLayer.ROLE) for f in skills))
        FieldRegistry(version="growth.v2", fields=(*permissions, *skills))

    def test_settings_roundtrip(self):
        self.assertEqual(skill_settings(self.runtime, self.context()), ((), 0))
        self.set_skills("写作、吉他", strength=2)
        self.assertEqual(skill_settings(self.runtime, self.context()), (("写作", "吉他"), 2))

    def test_a_skill_set_in_one_window_is_visible_in_another_window_of_the_role(self):
        # The point of sharing: the same role talking to the same person in another
        # conversation window keeps its skill domains.
        self.set_skills("水彩、吉他", strength=2, scope=SCOPE)
        self.assertEqual(skill_settings(self.runtime, self.context(scope=OTHER_SCOPE)),
                         (("水彩", "吉他"), 2))

    def test_the_first_window_write_is_promoted_and_then_applies_to_every_window(self):
        # This is how a role-level value comes to exist: the first window to set skill
        # content promotes it onto the role, and later windows inherit it.
        self.set_skills("摄影", strength=3, scope=SCOPE)
        for scope in (SCOPE, OTHER_SCOPE):
            self.assertEqual(skill_settings(self.runtime, self.context(scope=scope)), (("摄影",), 3))

    def test_a_window_override_does_not_change_what_other_windows_see(self):
        self.set_skills("水彩", strength=1, scope=SCOPE)
        self.set_skills("油画", strength=3, scope=OTHER_SCOPE)
        third = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a",
                         "conversation-c", "session-c")
        self.assertEqual(skill_settings(self.runtime, self.context(scope=SCOPE)), (("水彩",), 1))
        self.assertEqual(skill_settings(self.runtime, self.context(scope=OTHER_SCOPE)), (("油画",), 3))
        self.assertEqual(skill_settings(self.runtime, self.context(scope=third)), (("水彩",), 1))

    def test_the_role_uses_the_key_of_the_group_it_is_stored_under(self):
        # A role-layer target carries no scope; the shared owner builds it itself.
        target = self.target(layer=ConfigLayer.ROLE)
        self.assertIsNone(target.scope)
        self.assertEqual(target.role, ROLE)

    def test_another_role_does_not_inherit_the_skills(self):
        self.set_skills("水彩", strength=2, scope=SCOPE)
        self.assertEqual(skill_settings(self.runtime, self.context(role=OTHER_ROLE)), ((), 0))

    def test_influence_notes_bounds(self):
        self.assertEqual(sorted(INFLUENCE_NOTES), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
