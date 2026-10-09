"""Legacy staging settings migrate into the one shared host configuration."""

from copy import deepcopy
import unittest

from astrbot_host.shared_host_migration import migrate_single_target_config, recover_repeated_single_target
from companion_v2.execution.models import digest


class SharedHostMigrationTests(unittest.TestCase):
    def test_enabled_single_target_becomes_a_shared_private_mapping(self):
        original = {
            "staging": {"enabled": True, "profile_id": "main"},
            "target": {"platform_id": "default", "account_id": "100", "participant_id": "200",
                       "bot_id": "staging-bot", "role_id": "staging-role", "persona_id": ""},
            "multi_host": {"enabled": False, "installation_id": "main", "targets": [], "personas": []},
        }

        migrated, changed = migrate_single_target_config(original)

        self.assertTrue(changed)
        self.assertFalse(migrated["staging"]["enabled"])
        self.assertTrue(migrated["multi_host"]["enabled"])
        self.assertEqual(len(migrated["multi_host"]["targets"]), 1)
        self.assertEqual(migrated["multi_host"]["targets"][0]["participant_id"], "200")
        self.assertEqual(migrated["multi_host"]["personas"][0]["role_id"], "staging-role")
        self.assertTrue(original["staging"]["enabled"])
        self.assertEqual(original["multi_host"]["targets"], [])

    def test_incomplete_old_target_waits_for_the_admin_binding(self):
        original = {"staging": {"enabled": False}, "target": {"account_id": "", "participant_id": ""}}

        migrated, changed = migrate_single_target_config(original)

        self.assertFalse(changed)
        self.assertEqual(migrated["multi_host"]["targets"], [])
        self.assertEqual(migrated["multi_host"]["personas"], [])

    def test_existing_shared_mappings_are_preserved(self):
        target = {"target_id": "existing", "platform_id": "default", "account_id": "101",
                  "bot_id": "bot-101", "participant_id": "201"}
        original = {"staging": {"enabled": True},
                    "target": {"platform_id": "default", "account_id": "100", "participant_id": "200"},
                    "multi_host": {"enabled": True, "targets": [target], "personas": []}}

        migrated, changed = migrate_single_target_config(original)

        self.assertTrue(changed)
        self.assertFalse(migrated["staging"]["enabled"])
        self.assertTrue(migrated["multi_host"]["enabled"])
        self.assertEqual({row["participant_id"] for row in migrated["multi_host"]["targets"]}, {"200", "201"})
        self.assertEqual(migrated["multi_host"]["targets"][0]["bot_id"], "bot-101")
        self.assertEqual(migrated["multi_host"]["targets"][1]["bot_id"], "staging-bot")

    def test_disabled_legacy_target_never_reappears_in_reviewed_wildcard_mapping(self):
        original = {
            "staging": {"enabled": False, "profile_id": "existing-data"},
            "target": {"platform_id": "default", "account_id": "100", "participant_id": "200",
                       "bot_id": "old-bot", "persona_id": "old-persona", "role_id": "old-role"},
            "multi_host": {"enabled": True,
                "targets": [{"target_id": "private-all", "platform_id": "default", "account_id": "100",
                             "bot_id": "current-bot", "participant_id": "*"}], "group_targets": [],
                "personas": [{"bot_id": "current-bot", "persona_id": "current-persona", "role_id": "current-role"}]},
        }
        for _ in range(3):
            migrated, changed = migrate_single_target_config(original)
            self.assertFalse(changed)
            self.assertEqual(migrated, original)
            original = migrated
        original["multi_host"]["enabled"] = False
        migrated, changed = migrate_single_target_config(original)
        self.assertFalse(changed)
        self.assertFalse(migrated["multi_host"]["enabled"])

    def test_registered_account_identity_and_persona_win_over_old_single_target(self):
        from astrbot_host.multi_settings import MultiHostSettings

        registered = {"platform_id": "default", "account_id": "100", "bot_id": "reviewed-bot"}
        persona = {"bot_id": "reviewed-bot", "persona_id": "original", "role_id": "reviewed-role"}
        original = {"staging": {"enabled": True},
                    "target": {"platform_id": "default", "account_id": "100", "participant_id": "200",
                               "bot_id": "old-bot", "persona_id": "original", "role_id": "old-role"},
                    "multi_host": {"enabled": True, "accounts": [registered], "targets": [],
                                   "group_targets": [], "personas": [persona]}}

        migrated, changed = migrate_single_target_config(original)

        self.assertTrue(changed)
        self.assertEqual(migrated["multi_host"]["accounts"], [registered])
        self.assertEqual(migrated["multi_host"]["targets"][0]["bot_id"], "reviewed-bot")
        self.assertEqual(migrated["multi_host"]["personas"], [persona])
        self.assertEqual(MultiHostSettings.parse(migrated).accounts[0].bot_id, "reviewed-bot")

    def test_disabled_single_target_with_no_shared_mapping_can_be_imported_once(self):
        original = {"staging": {"enabled": False},
                    "target": {"platform_id": "default", "account_id": "100", "participant_id": "200"},
                    "multi_host": {"enabled": False, "targets": [], "personas": [], "group_targets": []}}
        migrated, changed = migrate_single_target_config(original)
        self.assertTrue(changed)
        self.assertFalse(migrated["multi_host"]["enabled"])
        repeated, changed = migrate_single_target_config(migrated)
        self.assertFalse(changed)
        self.assertEqual(repeated, migrated)

    def damaged_shared_config(self):
        from astrbot_host.multi_settings import MultiHostSettings
        from tests.multi_host_support import multi_config
        reviewed = multi_config()
        reviewed["multi_host"]["targets"][0]["participant_id"] = "*"
        pinned = MultiHostSettings.parse(reviewed).binding_contract
        damaged = deepcopy(reviewed)
        damaged["multi_host"]["targets"].append({
            "target_id": "legacy-" + digest(["qq-main", "100", "200"])[:20],
            "platform_id": "qq-main", "account_id": "100", "bot_id": "bot-a", "participant_id": "200"})
        return reviewed, damaged, pinned

    def test_recovery_removes_only_the_reimported_old_target(self):
        reviewed, damaged, pinned = self.damaged_shared_config()
        before = deepcopy(damaged)
        recovered, changed = recover_repeated_single_target(damaged, pinned)
        self.assertTrue(changed)
        self.assertEqual(recovered, reviewed)
        self.assertEqual(damaged, before)
        repeated, changed = recover_repeated_single_target(recovered, pinned)
        self.assertFalse(changed)
        self.assertEqual(repeated, recovered)

    def test_recovery_never_adopts_other_account_persona_or_group_edits(self):
        _, damaged, pinned = self.damaged_shared_config()
        for kind in ("legacy_enabled", "role", "account", "group", "custom_id", "no_wildcard", "no_manifest"):
            candidate = deepcopy(damaged)
            if kind == "legacy_enabled":
                candidate["staging"]["enabled"] = True
            elif kind == "role":
                candidate["multi_host"]["personas"][0]["role_id"] = "other-role"
            elif kind == "account":
                candidate["multi_host"]["targets"][1]["account_id"] = "102"
            elif kind == "group":
                candidate["multi_host"]["group_targets"] = [{"target_id": "new-group", "platform_id": "qq-main",
                    "account_id": "100", "bot_id": "bot-a", "group_id": "300"}]
            elif kind == "custom_id":
                candidate["multi_host"]["targets"][-1]["target_id"] = "operator-target"
            elif kind == "no_wildcard":
                candidate["multi_host"]["targets"][0]["participant_id"] = "201"
            before = deepcopy(candidate)
            with self.subTest(kind=kind):
                recovered, changed = recover_repeated_single_target(candidate, None if kind == "no_manifest" else pinned)
                self.assertFalse(changed)
                self.assertEqual(recovered, before)


if __name__ == "__main__":
    unittest.main()
