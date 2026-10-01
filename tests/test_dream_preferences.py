"""Dream writing preferences: instruction suffix, life settings validation, and registry contract."""

from types import SimpleNamespace
import unittest

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.role_work.journal.models import JournalKind
from companion_v2.role_work.journal.prompts import DREAM, dream_instruction, request_for
from companion_v2.role_work.life.configuration import (AFTERGLOW_MODES, DEFAULTS, configuration_fields, values)
from tests.test_management_access import ROLE, SCOPE


def life_settings(**changes):
    merged = {**DEFAULTS, **changes}
    return SimpleNamespace(values={f"role.life.{name}": value for name, value in merged.items()})


class DreamPreferenceTests(unittest.TestCase):
    def test_instruction_combinations(self):
        self.assertEqual(dream_instruction({}), "")
        base = dream_instruction({"dream_theme_candidates": "飞行、旧教室， 走廊"})
        self.assertIn("题材参考（可选，不必全用）：飞行、旧教室、走廊。", base)
        mixed = dream_instruction({"dream_mixed_themes_enabled": True})
        self.assertIn("轻微混搭", mixed)
        intimate = dream_instruction({"dream_intimate_theme_enabled": True})
        self.assertIn("暧昧或亲密", intimate)
        self.assertIn("不写露骨细节", intimate)
        self.assertIn("轻而短暂", dream_instruction({"dream_afterglow_mode": "轻"}))
        self.assertIn("适度、可感", dream_instruction({"dream_afterglow_mode": "标准"}))
        self.assertIn("明显一些", dream_instruction({"dream_afterglow_mode": "明显"}))
        self.assertEqual(dream_instruction({"dream_afterglow_mode": "auto"}), "")

    def test_values_rejects_unknown_afterglow_mode(self):
        with self.assertRaises(ValueError):
            values(life_settings(dream_afterglow_mode="夸张"))

    def test_registry_contract(self):
        fields = configuration_fields()
        names = {f.field_id.rsplit(".", 1)[-1] for f in fields}
        for name in ("dream_theme_candidates", "dream_mixed_themes_enabled",
                     "dream_intimate_theme_enabled", "dream_afterglow_mode"):
            self.assertIn(name, names)
        FieldRegistry(version="life.v1", fields=fields)

    def test_afterglow_modes_match_v1(self):
        self.assertEqual(AFTERGLOW_MODES, ("auto", "轻", "标准", "明显"))


class RequestForDreamTests(unittest.TestCase):
    def job(self, kind):
        return SimpleNamespace(
            target=SimpleNamespace(key=SimpleNamespace(local_date="2026-09-27", kind=kind), timezone="Asia/Shanghai"),
            materials=(), role_instruction="保持原人格",
            event=SimpleNamespace(name="trigger", scope=SCOPE, runtime_scope=None),
            context=SimpleNamespace(role_binding=SimpleNamespace(scope=SCOPE, role=ROLE)))

    def test_dream_suffix_only_applies_to_dream_kind(self):
        suffix = dream_instruction({"dream_mixed_themes_enabled": True})
        dream_request = request_for(self.job(JournalKind.DREAM), (), dream=suffix)
        self.assertTrue(dream_request.instruction.endswith(suffix))
        self.assertIn(DREAM[:20], dream_request.instruction)
        diary_request = request_for(self.job(JournalKind.DIARY), (), dream=suffix)
        self.assertFalse(diary_request.instruction.endswith(suffix))
        plain = request_for(self.job(JournalKind.DREAM), ())
        self.assertIn(DREAM[:20], plain.instruction)
        self.assertFalse(plain.instruction.endswith(suffix))


if __name__ == "__main__":
    unittest.main()
