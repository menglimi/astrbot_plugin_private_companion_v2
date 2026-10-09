"""Optional runtime settings must not require the participant to be an administrator."""

import unittest

from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.role_work.state.configuration import (DEFAULTS, EXPRESSION_PROMPTS, GROUP, OWNER,
    configuration_fields, target_for, validate_expression_prompts)
from tests.test_host_application import HostFixture


class RoleStateConfigurationTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def test_state_expression_prompts_are_registered_and_bounded(self):
        fields = {field.field_id: field for field in configuration_fields()}
        for name in EXPRESSION_PROMPTS:
            self.assertEqual(DEFAULTS[name], "")
            self.assertIn(GROUP + "." + name, fields)
        validate_expression_prompts({**DEFAULTS, "energy_expression_prompt": "随活动自然变化"})
        for value in (None, 7, "x" * 513):
            with self.assertRaises(Exception):
                validate_expression_prompts({**DEFAULTS, "health_expression_prompt": value})

    async def test_standard_participant_consumes_core_settings_without_management_access(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event()).unwrap()
        context = self.context(app, batch)
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.grant(self.important, context.scope, "configuration.read")
        self.grant(self.important, context.scope, "configuration.write")
        values, token = app.role_state.settings(context)
        self.assertFalse(values["enabled"])
        self.assertFalse(values["typing_enabled"])
        self.assertEqual(values["typing_refresh_seconds"], 4)
        self.assertEqual(app.configuration.read(context.actor, target=target_for(context), group_id=GROUP,
            observed_at=self.clock.now()).failure.code, "core_access_required")
        snapshot = app.configuration.read(self.core, target=target_for(context), group_id=GROUP,
            observed_at=self.clock.now()).unwrap()
        changes = {"role.state.maintenance_minutes": 45}
        denied = app.configuration.patch(context.actor, target=target_for(context), group_id=GROUP,
            operation=self.operation(context.scope, owner=OWNER), expected_edit_token=snapshot.edit_token,
            changes=changes, observed_at=self.clock.now())
        self.assertEqual(denied.failure.code, "core_access_required")
        app.configuration.patch(self.core, target=target_for(context), group_id=GROUP,
            operation=self.operation(context.scope, owner=OWNER), expected_edit_token=snapshot.edit_token,
            changes=changes, observed_at=self.clock.now()).unwrap()
        changed, updated = app.role_state.settings(context)
        self.assertEqual(changed["maintenance_minutes"], 45)
        self.assertNotEqual(token, updated)
        self.assertEqual(self.called, [])
        self.assertEqual(self.sent, [])

    async def test_runtime_settings_reject_an_obsolete_account_binding(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event()).unwrap()
        context = self.context(app, batch)
        self.identity.bind(binding_id="rebound", principal=context.actor.principal,
            subject=context.actor.subject, valid_from=self.clock.now(), expected_revision=self.identity.revision)
        with self.assertRaises(TaskError) as caught:
            app.role_state.settings(context)
        self.assertEqual(caught.exception.code, "binding_rebound")


if __name__ == "__main__":
    unittest.main()
