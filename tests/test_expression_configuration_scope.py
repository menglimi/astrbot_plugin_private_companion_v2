"""Expression learning defaults are installation-wide with private exceptions."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.execution.models import TaskError
from companion_v2.expression.configuration import (GROUP, ExpressionConfigurationOwner,
    application_subject_allowed, configuration_fields, main_companion_subject,
    migrate_legacy_policy_values, read_role_scope_settings, read_settings,
    source_subject_allowed, target_for)
from companion_v2.expression.style_service import ExpressionStyleService
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.role_profile.configuration import (GROUP as ROLE_PROFILE_GROUP,
    RoleProfileConfigurationOwner, configuration_fields as role_profile_fields,
    target_for as role_profile_target_for)
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION


ROLE_A = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-a")
ROLE_B = SubjectRef(INSTALLATION, SubjectKind.BOT, "role-b")
SCOPE_A = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "native-a", "bot-a", "login-a",
                   "group-a", "session-a")
SCOPE_B = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "native-b", "bot-b", "login-b",
                   "group-b", "session-b")
PRIVATE_SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "person-a", "bot-a", "login-a",
                         "conversation-a", "session-a")
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


class ExpressionConfigurationScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="companion-expression-scope-")
        self.addCleanup(temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data",
                                           installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)

    @staticmethod
    def context(scope=SCOPE_A, role=ROLE_A):
        return SimpleNamespace(scope=scope, role_binding=SimpleNamespace(role=role))

    def test_policy_defaults_follow_role_and_keep_explicit_window_overrides(self):
        fields = configuration_fields()
        self.assertTrue(all(field.layers == (ConfigLayer.INSTALLATION, ConfigLayer.ROLE, ConfigLayer.WINDOW)
                            for field in fields))
        self.assertEqual(target_for(self.context()).layer, ConfigLayer.WINDOW)
        self.assertEqual(target_for(installation_id=INSTALLATION),
                         ConfigTarget(INSTALLATION, ConfigLayer.INSTALLATION))
        self.assertEqual(target_for(self.context()).role, ROLE_A)
        self.assertEqual(target_for(self.context()).scope, SCOPE_A)

        owner = ExpressionConfigurationOwner(self.runtime)
        installation = target_for(installation_id=INSTALLATION)
        snapshot = owner.read(installation, fields)
        owner.write(installation, fields, changes={GROUP + ".window_hours": 96,
                                                    GROUP + ".group_scan_interval_minutes": 240}, reset=(),
                    expected_revision=snapshot.revision, observed_at=NOW)
        role = ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE_A, bot_id=SCOPE_A.bot_id)
        snapshot = owner.read(role, fields)
        owner.write(role, fields, changes={GROUP + ".window_hours": 72}, reset=(),
                    expected_revision=snapshot.revision, observed_at=NOW)

        self.assertEqual(read_settings(self.runtime, self.context()).window_hours, 72)
        other_window = replace(SCOPE_A, conversation_id="conversation-a2", session_id="session-a2")
        self.assertEqual(read_settings(self.runtime, self.context(other_window, ROLE_A)).window_hours, 72)
        other_role = read_settings(self.runtime, self.context(SCOPE_B, ROLE_B))
        self.assertEqual(other_role.window_hours, 96)
        self.assertEqual(other_role.group_scan_interval_minutes, 240)

        window = target_for(self.context())
        snapshot = owner.read(window, fields)
        owner.write(window, fields, changes={GROUP + ".window_hours": 48}, reset=(),
                    expected_revision=snapshot.revision, observed_at=NOW)
        self.assertEqual(read_settings(self.runtime, self.context()).window_hours, 48)
        self.assertEqual(read_settings(self.runtime, self.context(other_window, ROLE_A)).window_hours, 72)

    def test_private_sampling_defaults_match_v1_observation_window(self):
        settings = read_settings(self.runtime, self.context())
        self.assertEqual(settings.scan_interval_minutes, 90)
        self.assertEqual(settings.window_hours, 720)
        self.assertEqual(settings.sample_limit, 60)
        self.assertEqual(settings.min_samples, 2)

    def test_role_profile_controls_map_owner_selected_and_all_modes(self):
        context = self.context(PRIVATE_SCOPE, ROLE_A)
        profile_owner = RoleProfileConfigurationOwner(self.runtime)
        target = role_profile_target_for(context)
        fields = role_profile_fields()
        snapshot = profile_owner.read(target, fields)
        self.assertEqual(read_role_scope_settings(self.runtime, context).private_source_mode, "owner")
        self.assertIsNone(main_companion_subject(self.runtime, context))

        profile_owner.write(target, fields, changes={
            ROLE_PROFILE_GROUP + ".main_companion_subject": "person-a",
            ROLE_PROFILE_GROUP + ".expression_private_source_mode": "selected",
            ROLE_PROFILE_GROUP + ".expression_private_source_subject_ids": '["person-b"]',
            ROLE_PROFILE_GROUP + ".expression_private_application_mode": "owner",
            ROLE_PROFILE_GROUP + ".expression_private_application_subject_ids": "[]",
        }, reset=(), expected_revision=snapshot.revision, observed_at=NOW)
        settings = read_role_scope_settings(self.runtime, context)
        self.assertEqual(main_companion_subject(self.runtime, context), "person-a")
        self.assertEqual(settings.private_source_mode, "selected")
        self.assertEqual(settings.selected_sources, ("person-b",))
        self.assertFalse(source_subject_allowed(settings, "person-a", "person-a"))
        self.assertTrue(source_subject_allowed(settings, "person-b", "person-a"))
        self.assertFalse(application_subject_allowed(settings, "person-b", "person-a"))
        self.assertTrue(application_subject_allowed(settings, "person-a", "person-a"))

        profile = profile_owner.read(target, fields)
        profile_owner.write(target, fields, changes={
            ROLE_PROFILE_GROUP + ".expression_private_source_mode": "all",
            ROLE_PROFILE_GROUP + ".expression_private_source_subject_ids": "[]",
        }, reset=(), expected_revision=profile.revision, observed_at=NOW)
        self.assertTrue(source_subject_allowed(read_role_scope_settings(self.runtime, context),
            "any-private-person", "person-a"))

    def test_group_learning_daily_budget_is_shared_across_windows(self):
        class Samples:
            @staticmethod
            def role_owner(context):
                return context.role_binding.role.subject_id

        service = ExpressionStyleService.__new__(ExpressionStyleService)
        service.runtime = self.runtime
        service.samples = Samples()
        policy = SimpleNamespace(group_daily_batch_limit=1)
        first, second = self.context(), self.context(SCOPE_B, ROLE_A)

        service._reserve_group_batch(first, policy, NOW, 1)
        with self.assertRaises(TaskError) as blocked:
            service._reserve_group_batch(second, policy, NOW, 1)
        self.assertEqual(blocked.exception.code, "expression_group_budget_exhausted")
        self.assertEqual(service._global_group_batches(service._day(NOW)), 1)

        next_day = NOW + timedelta(days=1)
        service._reserve_group_batch(second, policy, next_day, 2)
        self.assertEqual(service._global_group_batches(service._day(next_day)), 1)

    def test_existing_role_and_window_values_are_not_promoted_across_roles(self):
        fields = configuration_fields()
        owner = SparseConfigurationOwner(self.runtime)
        for role, scope, name, value, at in (
                (ROLE_A, SCOPE_A, "window_hours", 48, datetime(2026, 10, 11, tzinfo=timezone.utc)),
                (ROLE_B, SCOPE_B, "sample_limit", 32, NOW)):
            target = ConfigTarget(INSTALLATION, ConfigLayer.ROLE, role, bot_id=scope.bot_id)
            snapshot = owner.read(target, fields)
            owner.write(target, fields, changes={GROUP + "." + name: value}, reset=(),
                        expected_revision=snapshot.revision, observed_at=at)
        target = target_for(self.context())
        snapshot = owner.read(target, fields)
        owner.write(target, fields, changes={GROUP + ".window_hours": 60}, reset=(),
                    expected_revision=snapshot.revision, observed_at=NOW.replace(minute=1))

        promoted = set(migrate_legacy_policy_values(self.runtime))
        self.assertEqual(promoted, set())
        role_a = read_settings(self.runtime, self.context())
        role_a_other_window = replace(SCOPE_A, conversation_id="conversation-a2", session_id="session-a2")
        self.assertEqual(role_a.window_hours, 60)
        self.assertEqual(read_settings(self.runtime, self.context(role_a_other_window, ROLE_A)).window_hours, 48)
        role_b = read_settings(self.runtime, self.context(SCOPE_B, ROLE_B))
        self.assertEqual((role_b.window_hours, role_b.sample_limit), (720, 32))
        self.assertEqual(migrate_legacy_policy_values(self.runtime), ())

    def test_old_shared_scan_interval_is_preserved_for_group_learning(self):
        owner = ExpressionConfigurationOwner(self.runtime)
        target = ConfigTarget(INSTALLATION, ConfigLayer.INSTALLATION)
        fields = configuration_fields()
        snapshot = owner.read(target, fields)
        owner.write(target, fields, changes={GROUP + ".scan_interval_minutes": 75}, reset=(),
                    expected_revision=snapshot.revision, observed_at=NOW)

        promoted = migrate_legacy_policy_values(self.runtime)

        self.assertIn(GROUP + ".group_scan_interval_minutes", promoted)
        self.assertEqual(read_settings(self.runtime, self.context()).group_scan_interval_minutes, 75)

        current = owner.read(target, fields)
        owner.write(target, fields, changes={GROUP + ".group_scan_interval_minutes": 240}, reset=(),
                    expected_revision=current.revision, observed_at=NOW + timedelta(minutes=1))
        self.assertEqual(migrate_legacy_policy_values(self.runtime), ())
        self.assertEqual(read_settings(self.runtime, self.context()).group_scan_interval_minutes, 240)


if __name__ == "__main__":
    unittest.main()
