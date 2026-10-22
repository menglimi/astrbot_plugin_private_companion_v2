"""Only the exact predecessor may become an internal V2 capability owner."""

from dataclasses import replace

from companion_v2.capabilities import CapabilityDesiredState
from companion_v2.capabilities.native_catalog import register_native_replacement
from tests.g6_support import G6Fixture, NOW, descriptor


class NativeCatalogUpgradeTests(G6Fixture):
    def replacement(self):
        return replace(descriptor(), package_id="astrbot_plugin_private_companion.screen",
                       package_version="2.1.0", artifact_hash="new-native-artifact")

    def upgrade(self, new=None):
        return register_native_replacement(self.runtime, new or self.replacement(),
            previous_package_id=descriptor().package_id, observed_at=NOW)

    def test_active_upgrade_keeps_authorizations_choices_and_immutable_history(self):
        self.enable_screen()
        before = tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_authorizations", ()))
        choices = tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_role_selections", ()))
        self.assertTrue(self.upgrade().unwrap())
        installation = self.capabilities.installation(extension_id=descriptor().extension_id).unwrap()
        self.assertEqual(installation.package_id, self.replacement().package_id)
        self.assertIs(installation.desired_state, CapabilityDesiredState.ACTIVE)
        self.assertEqual(installation.revision, 2)
        self.assertEqual(before, tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_authorizations", ())))
        self.assertEqual(choices, tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_role_selections", ())))
        self.assertEqual(len(self.capabilities.descriptors(extension_id=descriptor().extension_id)), 2)
        self.assertEqual(self.runtime.read_all("PRAGMA foreign_key_check", ()), ())
        self.capabilities.register_descriptor(self.replacement(), registered_at=NOW).unwrap()
        self.upgrade().unwrap()
        self.assertEqual(self.capabilities.installation(extension_id=descriptor().extension_id).unwrap(), installation)

    def test_paused_upgrade_does_not_resume_or_grant_added_capabilities(self):
        self.enable_screen()
        self.capabilities.pause(extension_id=descriptor().extension_id, expected_revision=1, observed_at=NOW).unwrap()
        native = replace(self.replacement(), capabilities=(*descriptor().capabilities, "screen.new.action"))
        self.upgrade(native).unwrap()
        installed = self.capabilities.installation(extension_id=descriptor().extension_id).unwrap()
        self.assertIs(installed.desired_state, CapabilityDesiredState.PAUSED)
        self.assertEqual(self.runtime.read_all("SELECT * FROM capability_authorizations WHERE capability_id = ?",
                                               ("screen.new.action",)), ())

    def test_loaded_native_update_keeps_authority_and_repeated_registration_is_idle(self):
        self.enable_screen()
        self.upgrade().unwrap()
        before = tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_authorizations", ()))
        new = replace(self.replacement(), package_version="2.1.1")
        for _ in range(2):
            register_native_replacement(self.runtime, new, previous_package_id=new.package_id,
                                        observed_at=NOW).unwrap()
            installed = self.capabilities.installation(extension_id=new.extension_id).unwrap()
            self.assertEqual((installed.package_version, installed.revision), ("2.1.1", 3))
            self.assertEqual(before, tuple(dict(row) for row in self.runtime.read_all(
                "SELECT * FROM capability_authorizations", ())))

    def test_unknown_publisher_or_data_owner_fails_without_modifying_installation(self):
        self.enable_screen()
        before = self.capabilities.installation(extension_id=descriptor().extension_id).unwrap()
        for changed in (replace(self.replacement(), publisher_id="unknown"),
                        replace(self.replacement(), dataset_owners=("other-data",))):
            result = self.upgrade(changed)
            self.assertEqual(result.failure.code, "capability_identity_conflict")
            self.assertEqual(self.capabilities.installation(extension_id=descriptor().extension_id).unwrap(), before)
        self.assertEqual(len(self.capabilities.descriptors(extension_id=descriptor().extension_id)), 1)
