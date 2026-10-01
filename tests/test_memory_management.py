from dataclasses import replace
import unittest

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.configuration.service import ConfigurationService
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.configuration import configuration_fields, target_for
from companion_v2.memory.management import MemoryManagement
from companion_v2.memory.models import AtomRef
from companion_v2.memory.service import MemoryService
from tests.memory_support import MemoryFixture


class MemoryManagementTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.config = ConfigurationService(self.runtime, FieldRegistry(version="memory-test", fields=configuration_fields()))
        self.service = MemoryService(self.tasks, configuration=self.config)
        self.manager = MemoryManagement(self.service, self.core)

    def command(self, item, **kwargs):
        return self.manager.command(self.context, atom_id=item["atom_id"], expected_revision=item["revision"],
            view_token=item["view_token"], operation_key="admin-command", action="correct",
            value={"object": "偶尔喝咖啡", "representation": "管理员说明对方偶尔喝咖啡。"}, **kwargs)

    def test_actual_admin_is_distinct_from_the_subject_and_retries_reuse_receipt(self):
        ref = self.remember()
        listed = self.manager.list(self.context).unwrap()
        self.assertNotEqual(listed["operator_id"], listed["subject_id"])
        item = listed["items"][0]
        result = self.command(item).unwrap()
        self.assertEqual(self.command(item).unwrap(), result)
        value = self.service.writer.read(self.context, AtomRef(ref.atom_id, 2)).unwrap()
        self.assertEqual(value["attribution"], "third_party")
        self.assertEqual(value["accepted_by"], self.core.subject.subject_id)
        self.assertEqual(value["subject"], "self")

    def test_ordinary_user_cannot_administer_and_downgrade_fences_old_view(self):
        self.remember()
        self.assertFalse(MemoryManagement(self.service, self.standard).list(self.context).is_success)
        item = self.manager.list(self.context).unwrap()["items"][0]
        self.policy.set_tier(self.core.subject, AuthorizationTier.STANDARD, expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.assertFalse(self.command(item).is_success)
        self.assertEqual(self.memory.read(self.context, AtomRef(item["atom_id"], 1)).unwrap()["revision"], 1)

    def test_different_admin_cannot_use_original_view(self):
        self.remember()
        item = self.manager.list(self.context).unwrap()["items"][0]
        other = self.person("second-admin", AuthorizationTier.CORE)
        self.manager = MemoryManagement(self.service, other)
        self.assertEqual(self.command(item).failure.code, "memory_view_stale")

    def test_unified_configuration_disable_reset_and_invalid_schedule_are_atomic(self):
        snapshot = self.manager.settings(self.context).unwrap()
        disabled = self.manager.patch_settings(self.context, operation_key="off", expected_edit_token=snapshot["edit_token"],
            changes={"memory.enabled": False}).unwrap()
        self.assertEqual(self.service.writer.read(self.context, AtomRef("any", 1)).failure.code, "memory_disabled")
        self.assertTrue(self.manager.list(self.context).is_success)
        current = self.config.read(self.core, target=target_for(self.context), group_id="memory", observed_at=self.clock.now()).unwrap()
        self.assertFalse(current.values["memory.enabled"])
        self.manager.patch_settings(self.context, operation_key="inherit", expected_edit_token=current.edit_token,
            changes={}, reset_to_inherit=["memory.enabled"]).unwrap()
        latest = self.manager.settings(self.context).unwrap()
        with self.assertRaises((KeyError, ValueError)):
            self.manager.patch_settings(self.context, operation_key="bad", expected_edit_token=latest["edit_token"],
                changes={"memory.reflection_timezone": "not/a/timezone"})
        self.assertEqual(self.manager.settings(self.context).unwrap(), latest)
        self.assertTrue(self.service.writer.access.policy_for(self.context).enabled)

    def test_forgetting_does_not_recreate_the_administrative_source_on_retry(self):
        self.remember()
        item = self.manager.list(self.context).unwrap()["items"][0]
        args = dict(atom_id=item["atom_id"], expected_revision=item["revision"], view_token=item["view_token"],
                    operation_key="forget-admin", action="forget")
        first = self.manager.command(self.context, **args).unwrap()
        self.assertEqual(self.manager.command(self.context, **args).unwrap(), first)
        self.assertEqual(first["physical_erasure"], "not_performed")
