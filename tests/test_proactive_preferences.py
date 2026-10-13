from dataclasses import replace
from datetime import timedelta
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, fingerprint
from companion_v2.diagnostics.models import restore_target
from companion_v2.foundation.refs import OperationRef, ReferenceValidationError, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.proactive.configuration import GROUP, PURPOSES, target_for
from tests.proactive_support import ContactFixture
from tests.test_management_access import INSTALLATION, NOW, ROLE, SCOPE


class ContactPreferenceTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def test_four_layers_are_stable_and_old_window_keys_are_unchanged(self):
        context = self.contact_context()
        window = target_for(context)
        self.assertEqual(tuple(t.layer for t in window.chain()), (
            ConfigLayer.INSTALLATION, ConfigLayer.ROLE, ConfigLayer.RELATIONSHIP, ConfigLayer.WINDOW))
        self.assertEqual(restore_target(window.document()), window)
        old = ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE)
        self.assertEqual(old.key, fingerprint({"installation_id": INSTALLATION, "layer": "window",
            "role_id": ROLE.subject_id, "scope": SCOPE.document(), "bot_id": SCOPE.bot_id}))
        relation = window.chain()[2]
        self.assertEqual(relation, target_for(replace(context, audience=replace(context.audience, scope=replace(SCOPE, session_id="new")),
            role_binding=replace(context.role_binding, scope=replace(SCOPE, session_id="new")))).chain()[2])
        with self.assertRaises(ReferenceValidationError):
            ConfigTarget(INSTALLATION, ConfigLayer.RELATIONSHIP, ROLE, subject=self.important.subject)

    async def test_contact_group_rejects_targets_that_its_consumer_cannot_use(self):
        app = self.host().application
        for target in (ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE),
                       ConfigTarget(INSTALLATION, ConfigLayer.ROLE, ROLE)):
            self.assertEqual(app.configuration.read(self.core, target=target, group_id=GROUP, observed_at=NOW).failure.code,
                             "configuration_relationship_required")

    async def test_each_field_inherits_and_false_empty_reset_remain_distinct(self):
        app = self.host().application
        window = target_for(self.contact_context())
        installation, role, relationship, _ = window.chain()
        self.settings(app, {"enabled": True, "note": "安装说明"}, target=installation, actor=self.core).unwrap()
        self.settings(app, {"chat.weight": 2.0}, target=role, actor=self.core).unwrap()
        self.settings(app, {"chat.enabled": False, "note": "关系说明"}, target=relationship).unwrap()
        self.settings(app, {"note": ""}).unwrap()
        prefs = self.preferences(app)
        self.assertEqual((prefs.values["enabled"], prefs.values["chat.enabled"], prefs.values["note"], prefs.weight("chat")),
                         (True, False, "", 2.0))
        self.assertEqual(prefs.snapshot.fields[GROUP + ".chat.enabled"].source, relationship)
        self.assertTrue(prefs.snapshot.fields[GROUP + ".note"].explicit)
        self.settings(app, {}, reset=("note",)).unwrap()
        self.assertEqual(self.preferences(app).values["note"], "关系说明")
        # Includes "screen": the authorized Screen observation purpose added with T20.
        self.assertEqual(len(PURPOSES), 15)

    async def test_relation_is_separate_per_bot_and_subject_and_not_readable_by_other_important_user(self):
        app = self.host().application
        relation = target_for(self.contact_context()).chain()[2]
        self.settings(app, {"note": "只属于这段关系"}, target=relation).unwrap()
        other = self.person("other", self.policy.feature_access(self.important, scope=SCOPE,
            action="configuration.read", observed_at=NOW).unwrap().tier)
        self.assertFalse(app.configuration.read(other, target=relation, group_id=GROUP, observed_at=NOW).is_success)
        for target in (replace(relation, bot_id="bot-b"), replace(relation, subject=other.subject)):
            result = app.configuration.read(self.core, target=target, group_id=GROUP, observed_at=NOW).unwrap()
            self.assertEqual(result.values[GROUP + ".note"], "")

    async def test_window_cannot_select_someone_elses_relation_or_rebound_route(self):
        app = self.host().application
        target = target_for(self.contact_context())
        forged = replace(target, subject=self.core.subject)
        self.assertEqual(app.configuration.read(self.core, target=forged, group_id=GROUP, observed_at=NOW).failure.code,
                         "configuration_subject_mismatch")
        other_scope = replace(SCOPE, session_id="another-session")
        self.personas.register_route(ConversationRoute(other_scope, user=self.standard.subject), observed_at=NOW)
        self.assertFalse(app.configuration.read(self.core, target=replace(target, scope=other_scope), group_id=GROUP, observed_at=NOW).is_success)

    async def test_standard_relation_preferences_require_exact_read_and_write_grants(self):
        app = self.host().application
        target = ConfigTarget(INSTALLATION, ConfigLayer.RELATIONSHIP, ROLE, bot_id=SCOPE.bot_id, subject=self.standard.subject)
        self.assertFalse(app.configuration.read(self.standard, target=target, group_id=GROUP, observed_at=NOW).is_success)
        for action in ("configuration.read", "configuration.write"):
            self.grant(self.standard, target.authorization_scope, action)
        self.settings(app, {"enabled": False}, target=target, actor=self.standard).unwrap()
        self.assertFalse(app.configuration.read(self.standard, target=replace(target, bot_id="another"), group_id=GROUP, observed_at=NOW).is_success)

    async def test_ancestor_pause_cannot_be_overridden_and_expiry_restores_permanent_preferences(self):
        app = self.host().application
        window = target_for(self.contact_context())
        installation = window.chain()[0]
        until = NOW + timedelta(hours=1)
        self.settings(app, {"enabled": True, "pause_until": until.isoformat()}, target=installation, actor=self.core).unwrap()
        self.settings(app, {"enabled": True, "pause_until": "", "care.enabled": False}).unwrap()
        self.assertEqual(self.preferences(app).reason("chat"), "proactive_paused")
        self.assertEqual(self.preferences(app).snapshot.fields[GROUP + ".pause_until"].source, installation)
        future = self.preferences(app, at=until)
        self.assertIsNone(future.reason("chat"))
        self.assertEqual(future.reason("care"), "proactive_disabled")
        self.settings(app, {"pause_until": (until + timedelta(hours=1)).isoformat()}).unwrap()
        self.assertEqual(self.preferences(app, at=until).reason("chat"), "proactive_paused")
        self.settings(app, {}, reset=("pause_until",)).unwrap()
        self.assertIsNone(self.preferences(app, at=until).reason("chat"))

    async def test_purpose_pause_leaves_other_contact_purposes_available(self):
        app = self.host().application
        relation = target_for(self.contact_context()).chain()[2]
        self.settings(app, {"enabled": True, "news.pause_until": (NOW + timedelta(minutes=10)).isoformat()}, target=relation).unwrap()
        prefs = self.preferences(app)
        self.assertEqual(prefs.reason("news"), "proactive_paused")
        self.assertIsNone(prefs.reason("chat"))
        self.assertIsNone(self.preferences(app, at=NOW + timedelta(minutes=10)).reason("news"))

    async def test_public_legacy_rhythm_uses_the_last_field_save_not_an_unrelated_note_update(self):
        app = self.host().application
        first = target_for(self.contact_context())
        second = target_for(self.other_window_context())
        def old_public_save(target, changes, key):
            op_id = "proactive.contact-config:" + key
            before = app.configuration.read(self.core, target=target, group_id=GROUP,
                                            observed_at=self.clock.now()).unwrap()
            app.configuration.patch(self.core, target=target, group_id=GROUP, expected_edit_token=before.edit_token,
                changes={GROUP + "." + name: value for name, value in changes.items()}, observed_at=self.clock.now(),
                operation=OperationRef(op_id, GROUP, target.authorization_scope, VersionRef(op_id, 1), op_id)).unwrap()
        old_public_save(first, {"enabled": True}, "first-on")
        public_target = first.chain()[0]
        self.assertTrue(app.configuration.read(self.core, target=public_target, group_id=GROUP,
                                             observed_at=self.clock.now()).unwrap().values[GROUP + ".enabled"])
        self.clock.advance(timedelta(seconds=1))
        old_public_save(second, {"enabled": False}, "second-off")
        self.clock.advance(timedelta(seconds=1))
        old_public_save(first, {"note": "后来更新的私人备注"}, "first-note")
        public = app.configuration.read(self.core, target=public_target, group_id=GROUP,
                                        observed_at=self.clock.now()).unwrap()
        self.assertFalse(public.values[GROUP + ".enabled"])
        self.assertEqual(public.values[GROUP + ".note"], "")

    async def test_temporary_window_switch_cannot_override_saved_global_or_personal_rhythm(self):
        from companion_v2.proactive.management import ContactManagement

        app = await self.enabled()
        manager = ContactManagement(app, self.contact_context())
        def temporary_switch(enabled, key):
            return manager.configure(self.core, {"operation_key": key,
                "edit_token": manager.status(self.core).unwrap()["edit_token"],
                "changes": {"enabled": enabled}}).unwrap()
        temporary_switch(False, "old-setup-restoration")
        global_target, _, personal_target, _ = target_for(self.contact_context()).chain()
        self.settings(app, {"enabled": True}, target=global_target, actor=self.core).unwrap()
        self.assertTrue(self.preferences(app).values["enabled"])
        self.settings(app, {"enabled": False}, target=personal_target).unwrap()
        temporary_switch(True, "new-diagnostic-switch")
        self.assertFalse(self.preferences(app).values["enabled"])
        self.assertEqual(self.preferences(app).snapshot.fields[GROUP + ".enabled"].source, personal_target)

    async def test_quiet_hours_use_local_zone_inclusive_start_and_exclusive_end(self):
        app = self.host().application
        self.settings(app, {"enabled": True, "quiet_enabled": True, "quiet_start": "23:00", "quiet_end": "07:00"}).unwrap()
        self.assertIsNone(self.preferences(app, at=NOW.replace(hour=14, minute=59)).reason("chat"))
        self.assertEqual(self.preferences(app, at=NOW.replace(hour=15)).reason("chat"), "proactive_quiet_hours")
        self.assertEqual(self.preferences(app, at=NOW.replace(hour=22, minute=59)).reason("chat"), "proactive_quiet_hours")
        self.assertIsNone(self.preferences(app, at=NOW.replace(hour=23)).reason("chat"))
        self.settings(app, {"quiet_start": "07:00"}).unwrap()
        self.assertEqual(self.preferences(app).reason("chat"), "proactive_quiet_hours")

    async def test_invalid_timestamp_time_timezone_and_weight_are_rejected_without_receipts(self):
        app = self.host().application
        for key, value in (("pause_until", "2026-09-23T12:00:00"), ("quiet_start", "24:00"),
                           ("quiet_end", "01:01:01"), ("quiet_timezone", "No/SuchZone"), ("chat.weight", 0)):
            with self.subTest(key=key):
                self.assertFalse(self.settings(app, {key: value}).is_success)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM configuration_changes", ())[0], 0)

    async def test_parent_edits_fence_stale_patches_and_identical_operations_replay(self):
        app = self.host().application
        target = target_for(self.contact_context())
        before = self.preferences(app).snapshot
        operation = self.operation(target.authorization_scope, owner=GROUP)
        args = dict(target=target, group_id=GROUP, operation=operation, expected_edit_token=before.edit_token,
                    changes={GROUP + ".note": "新的偏好"}, observed_at=NOW)
        app.configuration.patch(self.important, **args).unwrap()
        self.assertTrue(app.configuration.patch(self.important, **args).unwrap().replayed)
        snapshot = self.preferences(app).snapshot
        self.settings(app, {"care.weight": 2.0}, target=target.chain()[2]).unwrap()
        stale = app.configuration.patch(self.important, **{**args, "operation": self.operation(target.authorization_scope, owner=GROUP),
                                                          "expected_edit_token": snapshot.edit_token})
        self.assertEqual(stale.failure.code, "configuration_revision_conflict")

    async def test_pause_preview_reports_effective_ancestor_and_survives_reopen(self):
        app = self.host().application
        target = target_for(self.contact_context())
        until = (NOW + timedelta(hours=1)).isoformat()
        self.settings(app, {"enabled": True, "pause_until": until}, target=target.chain()[0], actor=self.core).unwrap()
        preview = app.configuration.preview_changes(self.important, target=target, group_id=GROUP,
            changes={GROUP + ".pause_until": ""}, observed_at=NOW).unwrap()
        self.assertEqual(preview.after[GROUP + ".pause_until"].value, until)
        await app.close()
        reopened = self.host(runtime=self.open_runtime()).application
        self.assertEqual(self.preferences(reopened).reason("chat"), "proactive_paused")
        self.assertIsNone(self.preferences(reopened, at=NOW + timedelta(hours=1)).reason("chat"))
