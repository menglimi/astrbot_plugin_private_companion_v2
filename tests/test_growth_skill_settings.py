"""Growth skill configuration: parsing, installation-wide storage, and contract."""

import json
from dataclasses import replace
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.role_work.growth.configuration import (INFLUENCE_NOTES, SKILL_FIELDS, SKILLS_GROUP,
                                                         SkillConfigurationOwner, configuration_fields,
                                                         custom_skills, skill_configuration_fields,
                                                         migrate_legacy_skill_values, skill_settings)
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

    def target(self, scope=SCOPE, role=ROLE, layer=ConfigLayer.ROLE):
        if layer is ConfigLayer.INSTALLATION:
            return ConfigTarget(INSTALLATION, layer)
        if layer is ConfigLayer.ROLE:
            return ConfigTarget(INSTALLATION, layer, role, bot_id=scope.bot_id)
        return ConfigTarget(INSTALLATION, layer, role, scope)

    def set_skills(self, value, strength=0, *, scope=SCOPE, role=ROLE, layer=ConfigLayer.ROLE):
        fields = tuple(f for f in SKILL_FIELDS)
        target = self.target(scope, role, layer)
        snapshot = self.owner.read(target, fields)
        return self.owner.write(target, fields,
            changes={SKILLS_GROUP + ".enabled": True,
                     SKILLS_GROUP + ".custom_skills": value,
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
                         {SKILLS_GROUP + ".enabled", SKILLS_GROUP + ".custom_skills",
                          SKILLS_GROUP + ".schedule_influence_strength"})
        # Permissions stay window-only: a grant is issued per participant.
        self.assertTrue(all(f.layers == (ConfigLayer.WINDOW,) for f in permissions))
        # Skills have role defaults with an installation fallback; per-person
        # permissions remain window-scoped.
        self.assertTrue(all(f.layers == (ConfigLayer.INSTALLATION, ConfigLayer.ROLE) for f in skills))
        FieldRegistry(version="growth.v2", fields=(*permissions, *skills))

    def test_settings_roundtrip(self):
        self.assertEqual(skill_settings(self.runtime, self.context()), ((), 0))
        self.set_skills("写作、吉他", strength=2)
        self.assertEqual(skill_settings(self.runtime, self.context()), (("写作", "吉他"), 2))

    def test_disabling_skills_suppresses_automatic_settings_without_deleting_them(self):
        self.set_skills("写作、吉他", strength=2)
        target = self.target()
        snapshot = self.owner.read(target, SKILL_FIELDS)
        self.owner.write(target, SKILL_FIELDS, changes={SKILLS_GROUP + ".enabled": False},
                         reset=(), expected_revision=snapshot.revision, observed_at=NOW)
        self.assertEqual(skill_settings(self.runtime, self.context()), ((), 0))
        stored = self.owner.read(target, SKILL_FIELDS).fields[SKILLS_GROUP + ".custom_skills"].value
        self.assertEqual(custom_skills(stored), ("写作", "吉他"))

    def test_role_skill_policy_is_shared_by_its_windows_but_not_other_roles(self):
        self.set_skills("水彩、吉他", strength=2, scope=SCOPE)
        self.assertEqual(skill_settings(self.runtime, self.context(scope=OTHER_SCOPE)),
                         (("水彩", "吉他"), 2))
        self.assertEqual(skill_settings(self.runtime, self.context(scope=OTHER_SCOPE, role=OTHER_ROLE)),
                         ((), 0))

    def test_installation_skill_values_remain_a_fallback(self):
        self.set_skills("全局技能", strength=1, role=OTHER_ROLE, layer=ConfigLayer.INSTALLATION)
        self.assertEqual(skill_settings(self.runtime, self.context(role=OTHER_ROLE)), (("全局技能",), 1))
        self.set_skills("角色技能", strength=3, role=OTHER_ROLE)
        self.assertEqual(skill_settings(self.runtime, self.context(role=OTHER_ROLE)), (("角色技能",), 3))
        self.assertEqual(skill_settings(self.runtime, self.context(role=ROLE)), ((), 0))

    def test_roles_can_save_different_skill_defaults(self):
        self.set_skills("摄影", strength=3, scope=SCOPE, role=ROLE)
        self.set_skills("写作", strength=1, scope=OTHER_SCOPE, role=OTHER_ROLE)
        self.assertEqual(skill_settings(self.runtime, self.context(scope=OTHER_SCOPE, role=ROLE)), (("摄影",), 3))
        self.assertEqual(skill_settings(self.runtime, self.context(scope=SCOPE, role=OTHER_ROLE)), (("写作",), 1))

    def test_global_target_has_no_role_or_window_address(self):
        target = self.target()
        self.assertIsNone(target.scope)
        self.assertIsNone(target.role)
        self.assertIsNone(target.bot_id)

    def test_legacy_window_values_promote_once_without_globalizing_role_values(self):
        legacy_fields = tuple(replace(field, layers=(ConfigLayer.ROLE,)) for field in SKILL_FIELDS)
        legacy_owner = SparseConfigurationOwner(self.runtime)
        for role, scope, value, at in ((ROLE, SCOPE, '["写作"]', NOW),
                                       (OTHER_ROLE, OTHER_SCOPE, '["摄影"]', NOW.replace(minute=1))):
            target = self.target(scope=scope, role=role, layer=ConfigLayer.ROLE)
            snapshot = legacy_owner.read(target, legacy_fields)
            legacy_owner.write(target, legacy_fields,
                changes={SKILLS_GROUP + ".enabled": True, SKILLS_GROUP + ".custom_skills": value,
                         SKILLS_GROUP + ".schedule_influence_strength": 2},
                reset=(), expected_revision=snapshot.revision, observed_at=at)
        legacy_window_fields = tuple(replace(field, layers=(ConfigLayer.WINDOW,)) for field in SKILL_FIELDS)
        target = self.target(scope=SCOPE, role=ROLE, layer=ConfigLayer.WINDOW)
        snapshot = legacy_owner.read(target, legacy_window_fields)
        legacy_owner.write(target, legacy_window_fields,
            changes={SKILLS_GROUP + ".custom_skills": '["油画"]'}, reset=(),
            expected_revision=snapshot.revision, observed_at=NOW.replace(minute=2))
        expected = {SKILLS_GROUP + ".custom_skills"}
        self.assertEqual(set(migrate_legacy_skill_values(self.runtime)), expected)
        self.assertEqual(skill_settings(self.runtime, self.context(role=ROLE)), (("写作",), 2))
        self.assertEqual(skill_settings(self.runtime, self.context(role=OTHER_ROLE)), (("摄影",), 2))
        self.assertEqual(migrate_legacy_skill_values(self.runtime), ())

        target = self.target(role=ROLE)
        snapshot = self.owner.read(target, SKILL_FIELDS)
        self.owner.write(target, SKILL_FIELDS,
            changes={SKILLS_GROUP + ".custom_skills": '["角色设置"]'}, reset=(),
            expected_revision=snapshot.revision, observed_at=NOW)
        self.assertEqual(migrate_legacy_skill_values(self.runtime), ())
        self.assertEqual(skill_settings(self.runtime, self.context()), (("角色设置",), 2))
        self.assertEqual(skill_settings(self.runtime, self.context(role=OTHER_ROLE)), (("摄影",), 2))

    def test_influence_notes_bounds(self):
        self.assertEqual(sorted(INFLUENCE_NOTES), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
