"""Core configuration, exact authority and durable receipt recovery for contacts."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.identity_policy.models import GrantState
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.proactive.configuration import GROUP, PURPOSES, target_for
from companion_v2.proactive.management import ContactManagement, GRANT_PREFIX
from tests.proactive_support import ContactFixture
from tests.test_management_access import INSTALLATION, SCOPE


class ContactManagementTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_manager(self, *, ordinary=False):
        self.app = (await self.start()).application
        self.target = self.contact_context()
        if ordinary:
            scope = replace(SCOPE, native_scope_id="ordinary", conversation_id="ordinary", session_id="ordinary")
            self.personas.register_route(ConversationRoute(scope, user=self.standard.subject), observed_at=self.clock.now())
            self.grant(self.standard, scope, "text")
            self.grant(self.standard, scope, "configuration.read")
            self.target = self.contact_context(scope=scope, actor=self.standard)
        self.manager = ContactManagement(self.app, self.target)

    def request(self, changes, key="change", token=None):
        if token is None:
            token = self.manager.status(self.core).unwrap()["edit_token"]
        return {"operation_key": key, "edit_token": token, "changes": changes}

    def grants(self):
        return tuple(grant for grant in self.identity.snapshot().grants if grant.grant_id.startswith(GRANT_PREFIX))

    async def test_status_is_read_only_and_identifies_effective_switches(self):
        await self.setup_manager()
        before = self.identity.revision
        status = self.manager.status(self.core).unwrap()
        self.assertEqual(status["settings"]["event_max_age_seconds"], 3600)
        self.assertFalse(status["effective"]["allowed"])
        self.assertEqual(status["effective"]["reason"], "proactive_disabled")
        self.assertEqual(status["effective"]["readonly_fields"], [])
        # 断言与注册表实际项数一致，而不是写死一个数字：purpose 会随功能增加，
        # 写死数字会让「加了一类契机」看起来像「状态接口坏了」。
        self.assertEqual(len(status["purposes"]), len(PURPOSES))
        self.assertEqual((self.identity.revision, self.grants(), self.called, self.sent), (before, (), [], []))

    async def test_non_core_is_rejected_before_configuration_is_read(self):
        await self.setup_manager()
        data = self.request({"enabled": True})
        with patch.object(self.app.configuration, "read", wraps=self.app.configuration.read) as read:
            self.assertEqual(self.manager.status(self.important).failure.code, "core_access_required")
            self.assertEqual(self.manager.configure(self.important, data).failure.code, "core_access_required")
        read.assert_not_called()
        self.assertEqual(self.grants(), ())

    async def test_enabling_grants_only_original_participant_and_exposes_current_edit_token(self):
        await self.setup_manager(ordinary=True)
        before = self.manager.status(self.core).unwrap()
        self.assertFalse(before["effective"]["allowed"])
        request = self.request({"enabled": True, "automatic_enabled": True})
        result = self.manager.configure(self.core, request).unwrap()
        grant, = self.grants()
        self.assertEqual((grant.subject, grant.scope, grant.capability), (self.standard.subject, self.target.scope, GROUP))
        self.assertNotEqual(grant.subject, self.core.subject)
        self.assertTrue(result["status"]["effective"]["automatic_allowed"])
        self.assertNotEqual(request["edit_token"], result["status"]["edit_token"])
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_disabling_revokes_only_manager_grants_and_preserves_independent_permissions(self):
        await self.setup_manager()
        independent = self.grant(self.target.actor, self.target.scope, GROUP)
        self.manager.configure(self.core, self.request({"enabled": True}, "on")).unwrap()
        result = self.manager.configure(self.core, self.request({"enabled": False}, "off")).unwrap()
        self.assertFalse(result["status"]["effective"]["allowed"])
        self.assertTrue(all(grant.state is GrantState.REVOKED for grant in self.grants()))
        stored = next(grant for grant in self.identity.snapshot().grants if grant.grant_id == independent.grant_id)
        self.assertIs(stored.state, GrantState.ACTIVE)

    async def test_lost_response_replay_keeps_original_receipt_without_regranting(self):
        await self.setup_manager(ordinary=True)
        request = self.request({"enabled": True})
        first = self.manager.configure(self.core, request).unwrap()
        grant, = self.grants()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=self.clock.now())
        revision = self.identity.revision
        replay = self.manager.configure(self.core, request).unwrap()
        self.assertEqual(replay["operation_id"], first["operation_id"])
        self.assertTrue(replay["replayed"])
        self.assertEqual((self.identity.revision, len(self.grants())), (revision, 1))
        self.assertIs(self.grants()[0].state, GrantState.REVOKED)
        self.assertFalse(replay["status"]["effective"]["allowed"])

    async def test_changed_request_cannot_reuse_an_existing_receipt(self):
        await self.setup_manager()
        request = self.request({"enabled": True})
        self.manager.configure(self.core, request).unwrap()
        changed = self.manager.configure(self.core, {**request, "changes": {"enabled": False}})
        self.assertEqual(changed.failure.code, "idempotency_key_conflict")
        self.assertTrue(self.manager.status(self.core).unwrap()["settings"]["enabled"])

    async def test_stale_edit_and_removed_relationship_limits_do_not_issue_grants(self):
        await self.setup_manager()
        stale = self.request({"enabled": True}, "stale")
        self.manager.configure(self.core, self.request({"note": "先安静一点"}, "note")).unwrap()
        self.assertEqual(self.manager.configure(self.core, stale).failure.code, "configuration_revision_conflict")
        for field in ("max_relationship_contacts_24h", "max_relationship_attempts_24h"):
            result = self.manager.configure(self.core, self.request({field: 1}, field))
            self.assertEqual(result.failure.code, "contact_configuration_invalid")
        self.assertEqual(self.grants(), ())

    async def test_invalid_patch_rolls_back_configuration_and_grant(self):
        await self.setup_manager()
        for changes in ({"enabled": "yes"}, {"event_max_age_seconds": 30}, {"quiet_timezone": "Unknown/Zone"},
                        {"made_up": True}, {"enabled": True, "creation.weight": 0}):
            self.assertFalse(self.manager.configure(self.core, self.request(changes, str(changes))).is_success)
        self.assertFalse(self.manager.status(self.core).unwrap()["settings"]["enabled"])
        self.assertEqual(self.grants(), ())

    async def test_grant_and_configuration_rollback_together_on_late_failure(self):
        await self.setup_manager()
        request = self.request({"enabled": True})
        with patch.object(self.manager, "_status", side_effect=TaskError("synthetic_failure", "late failure")):
            self.assertEqual(self.manager.configure(self.core, request).failure.code, "synthetic_failure")
        self.assertEqual(self.grants(), ())
        self.assertFalse(self.manager.status(self.core).unwrap()["settings"]["enabled"])
        self.assertFalse(self.manager.configure(self.core, request).unwrap()["replayed"])

    async def test_changing_other_setting_never_silently_grants_contact(self):
        await self.setup_manager(ordinary=True)
        result = self.manager.configure(self.core, self.request({"automatic_enabled": True, "note": "偶尔聊聊"})).unwrap()
        self.assertFalse(result["status"]["effective"]["automatic_allowed"])
        self.assertEqual(self.grants(), ())

    async def test_role_rebind_blocks_old_manager_and_old_token_for_new_role(self):
        await self.setup_manager()
        request = self.request({"enabled": True})
        old = self.target.role_binding
        self.identity.bind_role(scope=self.target.scope, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "another-persona"),
                                expected_revision=old.revision, observed_at=self.clock.now())
        self.assertEqual(self.manager.configure(self.core, request).failure.code, "role_binding_changed")
        new_context = self.contact_context()
        newer = ContactManagement(self.app, new_context)
        self.assertEqual(newer.configure(self.core, request).failure.code, "configuration_revision_conflict")
        self.assertEqual(self.grants(), ())

    async def test_operator_cannot_replace_the_real_route_participant(self):
        await self.setup_manager()
        forged = replace(self.target, actor=self.core, audience=replace(self.target.audience, recipients=(self.core.subject,)))
        manager = ContactManagement(self.app, forged)
        self.assertEqual(manager.status(self.core).failure.code, "private_task_required")
        self.assertEqual(self.grants(), ())

    async def test_restart_can_recover_original_config_receipt(self):
        await self.setup_manager()
        request = self.request({"enabled": True})
        first = self.manager.configure(self.core, request).unwrap()
        await self.app.close()
        self.app = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        manager = ContactManagement(self.app, self.target)
        result = manager.configure(self.core, request).unwrap()
        self.assertEqual(first["operation_id"], result["operation_id"])
        self.assertTrue(result["replayed"])
        self.assertEqual(len(self.grants()), 1)

    async def test_late_operator_revocation_blocks_even_exact_receipt_recovery(self):
        await self.setup_manager()
        request = self.request({"enabled": True})
        self.manager.configure(self.core, request).unwrap()
        self.identity.revoke_binding(self.core.binding_id, revoked_at=self.clock.now(), expected_revision=self.identity.revision)
        self.assertFalse(self.manager.configure(self.core, request).is_success)
