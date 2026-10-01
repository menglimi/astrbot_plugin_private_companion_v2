"""Growth configuration and exact grants remain one persistent transaction."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.models import AuthorizationTier, GrantState
from companion_v2.role_work.growth.access_management import RoleGrowthAccessManagement
from companion_v2.role_work.growth.configuration import GROUP, OWNER, target_for
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE


class RoleGrowthAccessTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.current_host = await self.start()
        self.app = self.current_host.application
        self.target = TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                                  AudienceRef(SCOPE, (self.important.subject,)))
        self.access = RoleGrowthAccessManagement(self.app)
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                            expected_revision=self.policy.revision, observed_at=NOW)

    def status(self, operator=None):
        return self.access.read(operator=operator or self.core, context=self.target).unwrap()

    def configure(self, changes, *, key="configure", token=None, operator=None):
        return self.access.configure(operator=operator or self.core, context=self.target, operation_key=key,
                                     edit_token=token or self.status()["edit_token"], changes=changes)

    def enabled_grants(self):
        return [g for g in self.identity.snapshot().grants if g.grant_id.startswith("growth-grant:")
                and g.state is GrantState.ACTIVE]

    async def test_read_and_proposal_switches_are_independent_and_exact(self):
        self.assertFalse(self.status()["effective"]["read_enabled"]["allowed"])
        self.configure({"read_enabled": True}).unwrap()
        self.assertEqual([t.action for t in self.app.tools.growth.catalog_for(self.target)], ["role.growth.list"])
        self.configure({"proposals_enabled": True}, key="proposals").unwrap()
        self.assertEqual(len(self.app.tools.growth.catalog_for(self.target)), 3)
        self.assertEqual({g.capability for g in self.enabled_grants()}, {"role.growth.read", "role.growth.propose"})
        self.assertTrue(all(g.scope == SCOPE and g.subject == self.important.subject for g in self.enabled_grants()))
        for wrong in (replace(SCOPE, session_id="different"), replace(SCOPE, account_id="different")):
            self.assertFalse(self.identity.authorize(self.important, scope=wrong,
                capability="role.growth.read", observed_at=NOW).is_success)
        self.configure({"read_enabled": False}, key="off").unwrap()
        status = self.status()
        self.assertTrue(status["settings"]["proposals_enabled"])
        self.assertFalse(status["effective"]["proposals_enabled"]["allowed"])
        self.assertEqual(self.app.tools.growth.catalog_for(self.target), ())

    async def test_replay_after_later_disable_does_not_regrant_or_restore_settings(self):
        token = self.status()["edit_token"]
        first = self.configure({"read_enabled": True}, token=token).unwrap()
        self.configure({"read_enabled": False}, key="off").unwrap()
        replay = self.configure({"read_enabled": True}, token=token).unwrap()
        self.assertEqual(replay["operation_id"], first["operation_id"])
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["access"]["settings"]["read_enabled"])
        self.assertEqual(self.enabled_grants(), [])

    async def test_stale_edit_and_non_core_operator_cannot_issue_grants(self):
        stale = self.status()["edit_token"]
        self.configure({"read_enabled": True}).unwrap()
        denied = self.configure({"proposals_enabled": True}, key="stale", token=stale)
        self.assertEqual(denied.failure.code, "configuration_revision_conflict")
        self.assertEqual(len(self.enabled_grants()), 1)
        self.grant(self.important, SCOPE, "role.growth.manage", tier=AuthorizationTier.CORE)
        self.assertEqual(self.configure({"proposals_enabled": True}, key="noncore", operator=self.important).failure.code,
                         "core_access_required")

    async def test_configuration_failure_rolls_back_both_setting_and_grant(self):
        with patch("companion_v2.role_work.growth.configuration.PersistentIdentityDirectory.issue_grant",
                   side_effect=TaskError("simulated_grant_failure", "grant write failed")):
            result = self.configure({"read_enabled": True})
        self.assertEqual(result.failure.code, "simulated_grant_failure")
        self.assertFalse(self.status()["settings"]["read_enabled"])
        self.assertEqual(self.enabled_grants(), [])
        self.configure({"read_enabled": True}).unwrap()
        self.assertEqual(len(self.enabled_grants()), 1)

    async def test_generic_configuration_patch_uses_the_same_grant_owner_and_reset(self):
        target = target_for(self.target)
        snapshot = self.app.configuration.read(self.core, target=target, group_id=GROUP, observed_at=NOW).unwrap()
        self.app.configuration.patch(self.core, target=target, group_id=GROUP,
            operation=self.operation(SCOPE, owner=OWNER), expected_edit_token=snapshot.edit_token,
            changes={GROUP + ".read_enabled": True}, observed_at=NOW).unwrap()
        self.assertTrue(self.status()["effective"]["read_enabled"]["allowed"])
        snapshot = self.app.configuration.read(self.core, target=target, group_id=GROUP, observed_at=NOW).unwrap()
        self.app.configuration.patch(self.core, target=target, group_id=GROUP,
            operation=self.operation(SCOPE, owner=OWNER), expected_edit_token=snapshot.edit_token,
            changes={}, reset_to_inherit=(GROUP + ".read_enabled",), observed_at=NOW).unwrap()
        self.assertFalse(self.status()["effective"]["read_enabled"]["allowed"])

    async def test_disable_preserves_independent_grants_and_reports_effective_access(self):
        self.grant(self.important, SCOPE, "role.growth.read")
        self.configure({"read_enabled": True}).unwrap()
        self.configure({"read_enabled": False}, key="off").unwrap()
        status = self.status()
        self.assertFalse(status["settings"]["read_enabled"])
        self.assertTrue(status["effective"]["read_enabled"]["allowed"])
        self.assertEqual(self.enabled_grants(), [])
        self.policy.set_tier(self.important.subject, AuthorizationTier.IMPORTANT,
                             expected_revision=self.policy.revision, observed_at=NOW)
        self.assertTrue(self.status()["effective"]["proposals_enabled"]["allowed"])

    async def test_restart_retains_settings_and_receipt_without_duplicate_grants(self):
        token = self.status()["edit_token"]
        self.configure({"read_enabled": True, "proposals_enabled": True}, token=token).unwrap()
        identifiers = {g.grant_id for g in self.enabled_grants()}
        await self.app.close()
        restarted = await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)
        service = RoleGrowthAccessManagement(restarted.application)
        replay = service.configure(operator=self.core, context=self.target, operation_key="configure",
            edit_token=token, changes={"read_enabled": True, "proposals_enabled": True}).unwrap()
        self.assertTrue(replay["replayed"])
        self.assertEqual({g.grant_id for g in self.enabled_grants()}, identifiers)
        self.assertEqual(len(restarted.application.tools.growth.catalog_for(self.target)), 3)


if __name__ == "__main__":
    unittest.main()
