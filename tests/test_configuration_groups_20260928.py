"""The four configuration groups the cottage gained on 2026-09-28.

Each one already had an owner, a registered field contract and a live consumer;
what was missing was an authorized dashboard editor. These tests pin the two
things that are easy to get wrong when adding a ``GroupEditor`` subclass — the
owner constant (a mismatched one fails only at write time) and the error prefix
the scope/target refusals are built from — plus the group validators the editor
relies on to reject bad values before they reach storage.
"""

import unittest

from companion_v2.configuration.management import (AcquaintanceManagement, DiaryAndRestManagement,
                                                   KnowledgeManagement, RecallManagement,
                                                   RoleGrowthManagement, ScreenManagement)
from companion_v2.conversation.recall_settings import DEFAULTS as RECALL_DEFAULTS
from companion_v2.conversation.recall_settings import GROUP as RECALL_GROUP, validate as recall_validate
from companion_v2.knowledge.configuration import KnowledgeSettings
from companion_v2.memory.person.configuration import GROUP as PERSON_GROUP
from companion_v2.role_work.growth.configuration import (GROUP as GROWTH_GROUP, custom_skills)
from companion_v2.screen.configuration import DEFAULTS as SCREEN_DEFAULTS
from companion_v2.screen.configuration import GROUP as SCREEN_GROUP, validate as screen_validate
from companion_v2.configuration.models import ConfigLayer, ConfigurationError


class NewEditorDeclarationTests(unittest.TestCase):
    """Declarations only: no runtime, so these fail loudly on a copy-paste slip."""

    def test_each_editor_binds_its_own_group_owner_and_layers(self):
        expected = {
            RecallManagement: (RECALL_GROUP, RECALL_GROUP, (ConfigLayer.WINDOW,), "recall"),
            ScreenManagement: (SCREEN_GROUP, SCREEN_GROUP, (ConfigLayer.WINDOW,), "screen"),
            # person registers no owner of its own: its fields carry the default
            # ``configuration`` owner that ConfigurationService always installs.
            AcquaintanceManagement: (PERSON_GROUP, "configuration",
                                     (ConfigLayer.INSTALLATION, ConfigLayer.ROLE, ConfigLayer.WINDOW), "person"),
            RoleGrowthManagement: (GROWTH_GROUP, "role.growth.access", (ConfigLayer.WINDOW,), "role_growth"),
        }
        for editor, (group, owner, layers, prefix) in expected.items():
            with self.subTest(editor=editor.__name__):
                self.assertEqual(editor.group, group)
                self.assertEqual(editor.owner, owner)
                self.assertEqual(tuple(editor.layers), layers)
                self.assertEqual(editor.error_prefix, prefix)

    def test_the_scope_and_target_codes_are_prefixed_per_group(self):
        """The page maps these exact strings; a rename would surface raw codes."""
        for editor, code in ((RecallManagement, "recall_scope_invalid"),
                             (ScreenManagement, "screen_scope_invalid"),
                             (AcquaintanceManagement, "person_scope_invalid"),
                             (RoleGrowthManagement, "role_growth_scope_invalid")):
            with self.subTest(editor=editor.__name__):
                self.assertEqual(editor._code(editor.__new__(editor), "scope_invalid"), code)

    def test_a_window_editor_never_claims_a_role_scope(self):
        """Window groups must go through the private-participant branch of
        ``_authorize``; a group that quietly gained a role layer would skip it."""
        for editor in (RecallManagement, ScreenManagement, RoleGrowthManagement):
            with self.subTest(editor=editor.__name__):
                self.assertIn(ConfigLayer.WINDOW, editor.layers)


class RecallValidatorTests(unittest.TestCase):
    def test_accepts_the_declared_defaults(self):
        self.assertEqual(recall_validate(dict(RECALL_DEFAULTS)), RECALL_DEFAULTS)

    def test_refuses_a_partial_payload_and_out_of_range_counts(self):
        for values in ({}, {**RECALL_DEFAULTS, "transcribe_max_items": 21},
                       {**RECALL_DEFAULTS, "transcribe_text_chars": 79},
                       {**RECALL_DEFAULTS, "transcribe_window_minutes": 0}):
            with self.subTest(values=values):
                with self.assertRaises(ConfigurationError) as caught:
                    recall_validate(values)
                self.assertEqual(caught.exception.code, "recall_configuration_invalid")

    def test_switches_must_be_real_booleans(self):
        with self.assertRaises(ConfigurationError):
            recall_validate({**RECALL_DEFAULTS, "transcribe_enabled": 1})


class ScreenValidatorTests(unittest.TestCase):
    def test_accepts_the_declared_defaults(self):
        self.assertEqual(screen_validate(dict(SCREEN_DEFAULTS)), SCREEN_DEFAULTS)

    def test_the_material_limit_is_bounded_on_both_sides(self):
        for value in (199, 1601):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as caught:
                    screen_validate({**SCREEN_DEFAULTS, "journal_material_max_chars": value})
                self.assertEqual(caught.exception.code, "screen_configuration_invalid")


class GrowthSkillParserTests(unittest.TestCase):
    """``custom_skills`` is TEXT so the page edits it as a textarea; the parser —
    not a validator — decides what counts, which is why the page must not
    reject non-JSON input itself."""

    def test_reads_a_json_array_a_comma_list_and_a_blank(self):
        self.assertEqual(custom_skills('["写作", "植物学"]'), ("写作", "植物学"))
        self.assertEqual(custom_skills("写作, 植物学"), ("写作", "植物学"))
        self.assertEqual(custom_skills(""), ())
        self.assertEqual(custom_skills("   "), ())

    def test_truncates_instead_of_refusing_so_the_page_need_not_prevalidate(self):
        self.assertEqual(len(custom_skills(",".join(str(index) for index in range(20)))), 8)
        self.assertEqual(custom_skills("x" * 50), ("x" * 24,))

    def test_a_non_string_or_non_list_payload_yields_nothing(self):
        self.assertEqual(custom_skills("42"), ())
        self.assertEqual(custom_skills(None), ())


if __name__ == "__main__":
    unittest.main()


class KnowledgeAndLifeEditorDeclarationTests(unittest.TestCase):
    """The second batch: world-book/knowledge import, and diary/dream/rest."""

    def test_each_editor_binds_its_own_group_owner_and_layers(self):
        from companion_v2.configuration.management import DiaryAndRestManagement, KnowledgeManagement
        from companion_v2.knowledge.configuration import GROUP as KG, OWNER as KO
        from companion_v2.role_work.life.configuration import GROUP as LG, OWNER as LO
        expected = {
            KnowledgeManagement: (KG, KO, (ConfigLayer.INSTALLATION, ConfigLayer.ROLE,
                                           ConfigLayer.WINDOW), "knowledge"),
            # role.life is window-first, unlike every other group here.
            DiaryAndRestManagement: (LG, LO, (ConfigLayer.WINDOW, ConfigLayer.ROLE), "role_life"),
        }
        for editor, (group, owner, layers, prefix) in expected.items():
            with self.subTest(editor=editor.__name__):
                self.assertEqual(editor.group, group)
                self.assertEqual(editor.owner, owner)
                self.assertEqual(tuple(editor.layers), layers)
                self.assertEqual(editor.error_prefix, prefix)

    def test_the_life_editor_is_not_named_after_the_access_checker(self):
        """``role_work.life.management`` already exports a ``RoleLifeManagement``
        used as an access checker by four modules; a same-named editor would be
        easy to reach for by mistake."""
        from companion_v2.configuration import management as editors
        from companion_v2.role_work.life.management import RoleLifeManagement as AccessChecker
        self.assertIsNot(editors.DiaryAndRestManagement, AccessChecker)
        self.assertFalse(hasattr(editors, "RoleLifeManagement"),
                         "the editor must not shadow the access checker's name")


class KnowledgeCrossFieldRuleTests(unittest.TestCase):
    def test_the_turn_budget_cannot_be_smaller_than_one_entry(self):
        """Each range is enforced by its own FieldDefinition; this pair is not,
        so the owner checks it. A silently defaulted pair would look saved while
        nothing was ever injected."""
        from companion_v2.knowledge.configuration import KnowledgeSettings
        with self.assertRaises(ConfigurationError) as caught:
            KnowledgeSettings.from_values({"inject_max_chars": 500, "entry_char_limit": 4000})
        self.assertEqual(caught.exception.code, "knowledge_settings_invalid")
        # The default pair is consistent.
        self.assertEqual(KnowledgeSettings.from_values().inject_max_chars, 6000)
        self.assertEqual(KnowledgeSettings.from_values().entry_char_limit, 1200)

    def test_paths_and_source_ids_split_on_every_declared_separator(self):
        settings = KnowledgeSettings.from_values({
            "import_paths": "a.json\nb.json，c.json;d.json", "source_ids": "kb:1;doc:1:2"})
        self.assertEqual(settings.paths(), ("a.json", "b.json", "c.json", "d.json"))
        self.assertEqual(settings.knowledge_source_ids(), ("kb:1", "doc:1:2"))

    def test_the_ideographic_comma_is_not_a_separator_here(self):
        """``rest_gate`` window parsing accepts 、 but this group does not: a
        source list typed with 顿号 stays one entry and then matches nothing,
        silently importing fewer sources than the operator intended. The field
        help names the separators for exactly this reason."""
        settings = KnowledgeSettings.from_values({"source_ids": "kb:1、kb:2"})
        self.assertEqual(settings.knowledge_source_ids(), ("kb:1、kb:2",))

    def test_both_lists_are_bounded_by_the_source_limit(self):
        settings = KnowledgeSettings.from_values({
            "source_limit": 2, "import_paths": "a\nb\nc\nd"})
        self.assertEqual(len(settings.paths()), 2)


class RestGateValueTests(unittest.TestCase):
    def test_the_mode_drops_unknown_text_instead_of_failing_a_turn(self):
        from companion_v2.role_work.life.rest_gate import normalize_mode
        self.assertEqual(normalize_mode("llm"), "llm")
        self.assertEqual(normalize_mode("模型"), "llm")
        self.assertEqual(normalize_mode("LLM_JUDGE"), "llm")
        self.assertEqual(normalize_mode("nonsense"), "probability")

    def test_windows_accept_the_full_width_separators_users_actually_type(self):
        from companion_v2.role_work.life.rest_gate import parse_windows
        self.assertEqual(parse_windows("23:00-08:30"), ((1380, 1950),))
        self.assertEqual(parse_windows("23：00—08：30"), ((1380, 1950),))
        self.assertEqual(parse_windows("23:00至08:30,12:20到13:40"),
                         ((1380, 1950), (740, 820)))
        self.assertEqual(parse_windows(""), ())

    def test_a_write_of_an_unknown_mode_is_refused_rather_than_silently_coerced(self):
        """The read path coerces; the write path must not, or an operator would
        believe a typo was saved."""
        from companion_v2.role_work.life.rest_gate import validate_changes
        with self.assertRaises(ConfigurationError) as caught:
            validate_changes({"rest_reply_mode": "sometimes"})
        self.assertEqual(caught.exception.code, "rest_gate_settings_invalid")
        # A non-rest field is passed through untouched.
        self.assertEqual(validate_changes({"diary_style_prompt": "x"}), {"diary_style_prompt": "x"})


class LifeAfterglowModeTests(unittest.TestCase):
    def test_the_afterglow_mode_set_matches_the_writer_expects(self):
        from companion_v2.role_work.life.configuration import AFTERGLOW_MODES
        self.assertEqual(AFTERGLOW_MODES, ("auto", "轻", "标准", "明显"))
