"""Growth access adds a command without changing existing management routes."""

import unittest

from companion_v2.execution.models import encode
from tests import test_role_growth_api as support
from tests.test_management_access import NOW


class RoleGrowthAccessAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = support.GrowthManagementHostTests.asyncSetUp
    request = support.GrowthManagementHostTests.request
    initialize = support.GrowthManagementHostTests.initialize

    async def test_authenticated_configuration_changes_the_pinned_participant_only(self):
        session = await self.initialize()
        status = await self.request()
        access = status["data"]["access"]
        self.assertFalse(access["effective"]["read_enabled"]["allowed"])
        body = {"action": "configure", "operation_key": "read-on", "edit_token": access["edit_token"],
                "changes": {"read_enabled": True, "proposals_enabled": True}}
        changed = await self.request(data=body)
        self.assertEqual(changed["status"], "ok", changed)
        self.assertTrue(changed["data"]["access"]["effective"]["read_enabled"]["allowed"])
        for action in ("role.growth.read", "role.growth.propose"):
            self.assertTrue(session.application.tasks.check_context_access(self.target,
                action=action, observed_at=NOW).is_success)
        self.assertTrue((await self.request(data=body))["data"]["replayed"])
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_malformed_or_forged_settings_are_rejected_without_grants(self):
        await self.initialize()
        status = await self.request()
        body = {"action": "configure", "operation_key": "bad", "edit_token": status["data"]["access"]["edit_token"],
                "changes": {"read_enabled": True}}
        for changes in ({"read_enabled": 1}, {"read_enabled": "true"}, {"manage_enabled": True}, [], {}):
            denied = await self.request(data=body | {"changes": changes})
            self.assertEqual(denied["data"]["code"], "growth_configuration_invalid")
        for extra in ({"operator": "admin"}, {"context": {}}, {"role_id": "other"}):
            denied = await self.request(data=body | extra)
            self.assertEqual(denied["data"]["code"], "growth_command_invalid")
        denied = await self.request(username=None, data=body)
        self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        self.assertNotIn('"allowed":true', encode((await self.request())["data"]["access"]["effective"]))


if __name__ == "__main__":
    unittest.main()
