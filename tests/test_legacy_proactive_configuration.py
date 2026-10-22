"""Upgrade enabled people without turning the global default on for everyone."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.configuration.models import ConfigLayer
from companion_v2.legacy.migration import ConfigIntent, LegacyMigration
from companion_v2.legacy.proactive_configuration import (
    PRIVATE_RELATIONSHIP, PRIVATE_WINDOW, private_contact_configuration,
)
from companion_v2.proactive.configuration import GROUP, target_for
from companion_v2.proactive.management import ContactManagement, GRANT_PREFIX
from tests.proactive_support import ContactFixture


def write_profile(root, *, enabled=True, quota=12, idle=-1, interval=-1, account="100", platform="qq-main"):
    payload = {"primary_store_ownership": {"owner_persona_id": "original", "status": "bound"},
        "users": {"200": {"identity_subject_id": "200", "identity_adapter_instance_id": platform,
            "identity_bot_id": account, "identity_platform_kind": "onebot",
            "proactive_private_enabled": enabled,
            "unified_profile_capabilities": {"proactive_private_enabled": enabled},
            "proactive_daily_limit": quota, "proactive_idle_minutes": idle,
            "proactive_min_interval_minutes": interval,
            "pending_proactive_send_retry": {"text": "旧计划不得恢复"}}}}
    path = Path(root) / "companions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


class PrivateContactConversionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="legacy-proactive-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = write_profile(self.root)

    def convert(self, **changes):
        target = dict(persona_id="original", platform_id="qq-main", account_id="100", participant_id="200")
        target.update(changes)
        return private_contact_configuration(self.root, {}, **target)

    def test_enabled_person_inherits_intervals_and_keeps_its_send_quota_without_restoring_jobs(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        result = self.convert()
        self.assertEqual(result.changes, {"enabled": True, "automatic_enabled": True, "max_contacts_24h": 12})
        self.assertFalse(result.differences)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_explicit_false_zero_and_duration_overrides_are_preserved(self):
        write_profile(self.root, enabled=False, quota=0, idle=0, interval=5)
        self.assertEqual(self.convert().changes, {"enabled": False, "automatic_enabled": False,
            "max_contacts_24h": 0, "idle_seconds": 0, "interval_seconds": 300})
        write_profile(self.root, quota=-1)
        self.assertNotIn("max_contacts_24h", self.convert().changes)

    def test_mismatched_persona_account_adapter_or_person_cannot_enable_contacts(self):
        for target in ({"persona_id": "another"}, {"account_id": "101"},
                       {"platform_id": "qq-second"}, {"participant_id": "201"}):
            with self.subTest(target=target):
                self.assertFalse(self.convert(**target).changes)

    def test_namespaced_duplicate_without_verified_identity_never_overrides_the_original_user(self):
        profile = json.loads(self.path.read_text(encoding="utf-8"))
        profile["users"]["onebot:200:other"] = {"proactive_private_enabled": False, "proactive_daily_limit": 0}
        self.path.write_text(json.dumps(profile) + "\n", encoding="utf-8", newline="\n")
        self.assertTrue(self.convert().changes["enabled"])

    def test_conflicting_legacy_capability_or_matching_records_require_review(self):
        profile = json.loads(self.path.read_text(encoding="utf-8"))
        profile["users"]["200"]["proactive_private_enabled"] = False
        self.path.write_text(json.dumps(profile) + "\n", encoding="utf-8", newline="\n")
        self.assertFalse(self.convert().changes)
        self.assertTrue(self.convert().differences)


class PrivateContactMigrationHostTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def ready(self):
        from astrbot_host.legacy_api import LegacyMigrationWebAPI
        from astrbot_host.legacy_contact_configuration import append_private_contact_plan
        self.append_plan = append_private_contact_plan
        self.app = self.host().application
        self.context = self.contact_context()
        self.session = SimpleNamespace(application=self.app, profile=SimpleNamespace(target=self.context))
        self.api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
        self.api.controller = SimpleNamespace(runtime=self.runtime, now=self.clock.now,
            settings=SimpleNamespace(personas=(SimpleNamespace(persona_id="original",
                bot_id=self.context.scope.bot_id, role_id=self.context.role_binding.role.subject_id),)))
        self.api._operator = lambda: self.core
        temporary = TemporaryDirectory(prefix="legacy-contact-host-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = write_profile(self.root, account=self.context.scope.account_id,
            platform=self.context.scope.platform)
        payload = json.loads(self.profile.read_text(encoding="utf-8"))
        user = payload["users"].pop("200")
        user["identity_subject_id"] = self.context.actor.principal.native_account_id
        payload["users"][self.context.actor.principal.native_account_id] = user
        self.profile.write_text(json.dumps(payload) + "\n", encoding="utf-8", newline="\n")
        self.migration = LegacyMigration(v1_root=self.root,
            v1_configuration={"basic_config": {"default_proactive_enabled": False,
                "default_proactive_daily_limit": 0}, "proactive_reach_config": {"max_daily_messages": 8}},
            configuration_registry=self.app.configuration.registry, configuration_scope_kind="private")

    def plan(self):
        original = self.migration.plan().unwrap()
        return self.append_plan(self.api.controller, self.session, self.migration, original, "plugin")

    def migrate(self):
        intents, differences, _, _ = self.api._prepare_intents(self.session, self.plan())
        baseline = {self.api._intent_key(intent): self.app.configuration._snapshot(
            self.core, self.api._scope_target(self.session, intent), intent.group_id, self.clock.now(),
            "configuration.read") for intent in intents if intent.group_id == GROUP}
        for intent in intents:
            if intent.group_id == GROUP:
                self.api._apply_intent(intent, self.session, baseline[self.api._intent_key(intent)])
        return intents, differences

    async def test_global_off_personal_on_effective_authority_quota_and_idempotency(self):
        await self.ready()
        self.migrate()
        window = target_for(self.context)
        global_settings = self.app.configuration.read(self.core, target=window.chain()[0],
            group_id=GROUP, observed_at=self.clock.now()).unwrap()
        self.assertFalse(global_settings.values[GROUP + ".enabled"])
        self.assertFalse(global_settings.values[GROUP + ".automatic_enabled"])
        personal = self.app.configuration.read(self.core, target=window,
            group_id=GROUP, observed_at=self.clock.now()).unwrap()
        self.assertTrue(personal.values[GROUP + ".enabled"])
        self.assertTrue(personal.values[GROUP + ".automatic_enabled"])
        self.assertEqual(personal.values[GROUP + ".max_contacts_24h"], 12)
        self.app.tasks.check_context_access(self.context, action=GROUP, observed_at=self.clock.now()).unwrap()
        managed = [grant for grant in self.identity.snapshot().grants if grant.grant_id.startswith(GRANT_PREFIX)]
        self.assertEqual(len(managed), 1)
        self.assertEqual((managed[0].subject, managed[0].scope), (self.context.actor.subject, self.context.scope))
        self.migrate()
        self.assertEqual(len([grant for grant in self.identity.snapshot().grants
                              if grant.grant_id.startswith(GRANT_PREFIX)]), 1)
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_existing_personal_disable_is_not_overwritten_by_legacy_enable(self):
        await self.ready()
        target = target_for(self.context).chain()[2]
        self.settings(self.app, {"enabled": False, "automatic_enabled": False},
                      target=target, actor=self.core).unwrap()
        intents, differences = self.migrate()
        private = [intent for intent in intents if intent.target_kind == PRIVATE_RELATIONSHIP]
        self.assertFalse(private)
        self.assertTrue(any(item["kind"] == "preserved_v2" for item in differences))
        self.assertFalse(self.app.configuration.read(self.core, target=target_for(self.context),
            group_id=GROUP, observed_at=self.clock.now()).unwrap().values[GROUP + ".enabled"])

    async def test_failed_grant_rolls_back_personal_switch(self):
        await self.ready()
        intent = next(intent for intent in self.plan().intents if intent.target_kind == PRIVATE_RELATIONSHIP)
        target = self.api._scope_target(self.session, intent)
        before = self.app.configuration._snapshot(self.core, target, GROUP, self.clock.now(), "configuration.read")
        with patch.object(ContactManagement, "sync_configuration_grant", side_effect=RuntimeError("grant failed")):
            with self.assertRaisesRegex(RuntimeError, "grant failed"):
                self.api._apply_intent(intent, self.session, before)
        after = self.app.configuration._snapshot(self.core, target, GROUP, self.clock.now(), "configuration.read")
        self.assertEqual(before.fields, after.fields)

    async def test_source_changes_invalidate_review_even_if_file_metadata_is_preserved(self):
        await self.ready()
        first = self.api._prepare_intents(self.session, self.plan())[3]["private_contact_preferences"]
        payload = json.loads(self.profile.read_text(encoding="utf-8"))
        next(iter(payload["users"].values()))["proactive_daily_limit"] = 11
        self.profile.write_text(json.dumps(payload) + "\n", encoding="utf-8", newline="\n")
        second = self.api._prepare_intents(self.session, self.plan())[3]["private_contact_preferences"]
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
