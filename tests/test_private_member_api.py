"""Private-member settings affect live consumers and preserve exact routes."""

import json
from dataclasses import replace
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from tests.multi_host_support import MultiFixture
from tests.test_person_authorization import _Query, _body
from astrbot_host.acquaintance_api import AcquaintanceWebAPI, _group_target_access, _persona_metadata
from astrbot_host.management_identity import dashboard_operator
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.memory.person.access import owner_key
from companion_v2.proactive.management import ContactManagement


class AcquaintancePersonaMetadataTests(unittest.TestCase):
    def test_persona_label_is_resolved_from_bot_and_role(self):
        settings = NS(all_targets=(), personas=(
            NS(bot_id="bot-a", role_id="role-a", persona_id="星缘-私聊"),
            NS(bot_id="bot-a", role_id="role-b", persona_id="星缘-私聊"),
            NS(bot_id="bot-a", role_id="role-default", persona_id=None),
            NS(bot_id="bot-b", role_id="role-a", persona_id="另一人格"),
        ))
        self.assertEqual(_persona_metadata(settings, "bot-a", "role-a"),
                         {"persona_ids": ["星缘-私聊"], "role_name": "星缘-私聊"})
        self.assertEqual(_persona_metadata(settings, "bot-a", "role-b"),
                         {"persona_ids": ["星缘-私聊"], "role_name": "星缘-私聊"})
        self.assertEqual(_persona_metadata(settings, "bot-a", "role-default"),
                         {"persona_ids": [""], "role_name": "默认人格"})
        self.assertEqual(_persona_metadata(settings, "bot-c", "role-a"), {})


class GroupTargetAccessTests(unittest.TestCase):
    def test_single_mode_never_advertises_group_target_editing(self):
        controller = NS(_multi_host=False, _accepting=False, _terminated=False, session=None)
        access = _group_target_access(controller, NS())
        self.assertFalse(access["editable"])
        self.assertEqual(access["accounts"], [])
        self.assertEqual(access["persona_bots"], [])

    def test_shared_mode_requires_a_stopped_host_and_reports_bound_routes(self):
        settings = NS(all_targets=(NS(platform_id="qq", account_id="100", bot_id="bot-a"),),
                      personas=(NS(bot_id="bot-a"),))
        stopped = NS(_multi_host=True, _accepting=False, _terminated=False,
                     session=NS(application=NS(state="stopped")))
        access = _group_target_access(stopped, settings)
        self.assertTrue(access["editable"])
        self.assertEqual(access["accounts"], [{"platform_id": "qq", "account_id": "100", "bot_id": "bot-a"}])
        self.assertEqual(access["persona_bots"], ["bot-a"])

        stopped.session.application.state = "running"
        access = _group_target_access(stopped, settings)
        self.assertTrue(access["running"])
        self.assertFalse(access["editable"])


class PrivateMemberTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def ready(self):
        app = await self.start_host()
        await self.controller.receive_claimed(self.event("first", "first-input"))
        await self.controller.receive_claimed(self.event("second", "second-input"))
        self.api = AcquaintanceWebAPI(self.controller)
        return app

    def person(self, target="first"):
        context = self.controller.authority.context(target, "role-a")
        return {"subject_id": context.actor.subject.subject_id,
                "route": {"platform": context.scope.platform, "bot_id": context.scope.bot_id,
                          "account_id": context.scope.account_id, "role_id": context.role_binding.role.subject_id}}

    async def send(self, action, *, person=None, command=None, username="member-admin"):
        person = person or self.person()
        query = "&".join(key + "=" + value for key, value in
                         {"subject_id": person["subject_id"], **person["route"]}.items()) if command is None else ""
        payload = json.dumps(command or {}, ensure_ascii=False).encode("utf-8")
        with patch("astrbot_host.acquaintance_api.request",
                   NS(username=username, query=_Query(query), body=_body(payload))):
            return await getattr(self.api, action)()

    async def settings(self, person=None):
        result = await self.send("member_settings", person=person)
        self.assertEqual(result["status"], "ok", result)
        return result["data"]["sections"]

    async def configure(self, changes, *, person=None, key="member-save", snapshots=None):
        person = person or self.person()
        sections = snapshots or await self.settings(person)
        return await self.send("configure_member", command={**person, "operation_key": key,
            "sections": {section: {"edit_token": sections[section]["edit_token"], "changes": values}
                         for section, values in changes.items()}})

    async def test_profile_is_the_prompt_source_and_accounts_are_isolated(self):
        app = await self.ready()
        written = await self.configure({"profile": {"default_nickname": "小舟", "role_relation": "搭档",
                                                    "interaction": "简洁自然，称呼小舟"}})
        self.assertEqual(written["status"], "ok", written)
        first = self.controller.authority.context("first", "role-a")
        second = self.controller.authority.context("second", "role-a")
        reader = app.messages.relationship_profile_context
        snapshot = reader.capture(first, self.clock.now())
        self.assertIn("对用户的称呼：小舟", reader.instruction(snapshot, first))
        self.assertIsNone(reader.capture(second, self.clock.now()))
        self.assertEqual((await self.settings(self.person("second")))["profile"]["settings"]["default_nickname"], "")

    async def test_contact_and_card_settings_use_existing_consumers(self):
        app = await self.ready()
        result = await self.configure({"contact": {"enabled": True, "max_contacts_24h": 5, "quiet_enabled": True},
                                       "person": {"acquaintance_learning_enabled": False}})
        self.assertEqual(result["status"], "ok", result)
        context = self.controller.authority.context("first", "role-a")
        self.assertIsNone(app.messages.acquaintance.intake_observer(context))
        self.assertIsNotNone(app.messages.acquaintance.card_contribution(context, self.clock.now()))
        self.assertEqual((await self.settings())["contact"]["settings"]["max_contacts_24h"], 5)
        count = json.loads(app.messages.acquaintance.row(owner_key(context))["document_json"])["contexts"]
        await self.controller.receive_claimed(self.event("first", "without-learning"))
        self.assertEqual(json.loads(app.messages.acquaintance.row(owner_key(context))["document_json"])["contexts"], count)
        self.assertEqual((await self.configure({"person": {"acquaintance_enabled": False}}, key="disable-card"))["status"], "ok")
        self.assertIsNone(app.messages.acquaintance.card_contribution(context, self.clock.now()))
        self.assertEqual(app.messages.acquaintance.recall(context)["state"], "disabled")

    async def test_shared_owner_groups_save_and_replay_as_one_operation(self):
        await self.ready()
        original = await self.settings()
        changes = {"contact": {"max_contacts_24h": 5}, "person": {"acquaintance_learning_enabled": False},
                   "profile": {"default_nickname": "一起保存"}}
        first = await self.configure(changes, snapshots=original)
        self.assertEqual(first["status"], "ok", first)
        replay = await self.configure(changes, snapshots=original)
        self.assertEqual(replay["status"], "ok", replay)
        for name, result in first["data"]["results"].items():
            self.assertTrue(replay["data"]["results"][name]["replayed"])
            self.assertEqual(replay["data"]["results"][name]["operation_id"], result["operation_id"])
        different = await self.configure({**changes, "person": {"acquaintance_learning_enabled": True}}, snapshots=original)
        self.assertEqual(different["data"]["code"], "idempotency_key_conflict")

    async def test_invalid_last_group_rolls_back_saved_groups_and_the_receipt(self):
        app = await self.ready()
        original = (await self.settings())["contact"]["settings"]["max_contacts_24h"]
        result = await self.configure({"contact": {"max_contacts_24h": 5},
                                       "person": {"acquaintance_card_chars": 1}})
        self.assertEqual(result["status"], "error", result)
        self.assertEqual((await self.settings())["contact"]["settings"]["max_contacts_24h"], original)
        self.assertIsNone(app.runtime.read_one("SELECT 1 FROM operations WHERE operation_id LIKE 'private-member-settings:%'", ()))

    async def test_configured_members_are_selectable_before_cards_exist(self):
        await self.start_host()
        self.api = AcquaintanceWebAPI(self.controller)
        with patch("astrbot_host.acquaintance_api.request", NS(username="member-admin", query=_Query(), body=_body(b""))):
            result = await self.api.directory()
        self.assertEqual(result["status"], "ok", result)
        persons = result["data"]["persons"]
        self.assertEqual(len(persons), 4)
        self.assertTrue(all(person["private_target"] and not person["private_chat"] for person in persons))
        self.assertTrue(all(person["revision"] == 0 for person in persons))
        self.assertTrue(all(person["settings_available"] for person in persons), persons)
        for person in persons:
            sections = await self.settings({"subject_id": person["subject_id"],
                "route": {key: person[key] for key in ("platform", "bot_id", "account_id", "role_id")}})
            self.assertEqual(sections["profile"]["settings"]["default_nickname"], "")

    async def test_automatic_private_routes_expose_registered_people_and_their_settings(self):
        await self.start_host()
        self.api = AcquaintanceWebAPI(self.controller)
        self.controller.settings = replace(self.controller.settings, targets=tuple(
            replace(target, participant_id="*") for target in self.controller.settings.targets))
        self.controller.authority.settings = self.controller.settings
        with patch("astrbot_host.acquaintance_api.request", NS(username="member-admin", query=_Query(), body=_body(b""))):
            result = await self.api.directory()
        self.assertEqual(result["status"], "ok", result)
        persons = result["data"]["persons"]
        self.assertEqual(len(persons), 4)
        self.assertTrue(all(person["native_account_id"] == "200" and person["settings_available"] for person in persons))
        self.assertEqual((await self.settings())["profile"]["settings"]["default_nickname"], "")

    async def test_contact_configuration_cannot_restore_a_page_revocation(self):
        app = await self.ready()
        person = self.person()
        auth = (await self.send("authorization"))["data"]
        result = await self.send("authorize", command={**person, "operation_key": "contact-off",
            "capability": "proactive.contact", "enabled": False, "expected_revision": auth["policy_revision"]})
        self.assertEqual(result["status"], "ok", result)
        context = self.controller.authority.context("first", "role-a")
        manager = ContactManagement(app, context)
        operator = dashboard_operator(app.runtime, "member-admin", at=self.clock.now())
        before = manager.status(operator).unwrap()
        saved = manager.configure(operator, {"operation_key": "plan-on", "edit_token": before["edit_token"],
                                            "changes": {"enabled": True}})
        self.assertTrue(saved.is_success, saved.failure)
        current = (await self.send("authorization"))["data"]
        self.assertEqual(next(row for row in current["items"] if row["capability"] == "proactive.contact")["state"], "revoked")

    async def test_multisection_conflict_rolls_every_section_back(self):
        await self.ready()
        stale = await self.settings()
        self.assertEqual((await self.configure({"contact": {"max_contacts_24h": 7}}, key="other-edit"))["status"], "ok")
        result = await self.configure({"profile": {"default_nickname": "不能写入"},
                                       "contact": {"max_contacts_24h": 9}}, snapshots=stale)
        self.assertEqual(result["data"]["code"], "configuration_revision_conflict")
        current = await self.settings()
        self.assertEqual(current["profile"]["settings"]["default_nickname"], "")
        self.assertEqual(current["contact"]["settings"]["max_contacts_24h"], 7)

    async def test_settings_replay_returns_the_same_receipt(self):
        await self.ready()
        original = await self.settings()
        first = await self.configure({"profile": {"default_nickname": "小舟"}}, snapshots=original)
        replay = await self.configure({"profile": {"default_nickname": "小舟"}}, snapshots=original)
        self.assertEqual(first["status"], "ok", first)
        self.assertTrue(replay["data"]["results"]["profile"]["replayed"])
        changed = await self.configure({"profile": {"default_nickname": "不同称呼"}}, snapshots=original)
        self.assertEqual(changed["data"]["code"], "idempotency_key_conflict")

    async def test_identity_is_live_audited_and_overrides_are_explicit(self):
        app = await self.ready()
        auth = (await self.send("authorization"))["data"]
        result = await self.send("set_identity", command={**self.person(), "operation_key": "member-identity",
            "tier": "important", "expected_revision": auth["identity_revision"]})
        self.assertEqual(result["status"], "ok", result)
        state = result["data"]["status"]
        self.assertEqual(state["identity_tier"], "important")
        self.assertTrue(all(row["identity_override"] for row in state["items"]
                            if row["capability"] in {"proactive.contact", "conversation.reply"}))
        context = self.controller.authority.context("first", "role-a")
        decision = ObjectAccessPolicy(app.runtime).feature_access(context.actor, scope=context.scope,
            action="proactive.contact", observed_at=self.clock.now()).unwrap()
        self.assertEqual(decision.tier, AuthorizationTier.IMPORTANT)
        self.assertTrue(app.runtime.read_one("SELECT 1 FROM operations WHERE operation_id LIKE 'person-identity:%'", ()))
        stale = await self.send("set_identity", command={**self.person(), "operation_key": "stale-identity",
            "tier": "standard", "expected_revision": auth["identity_revision"]})
        self.assertEqual(stale["data"]["code"], "identity_revision_conflict")

    async def test_forged_or_ambiguous_routes_do_not_write(self):
        await self.ready()
        result = await self.send("configure_member", command={**self.person(), "operation_key": "bad-route",
            "route": {**self.person()["route"], "bot_id": "unconfigured"}, "sections": {}})
        self.assertEqual(result["data"]["code"], "acquaintance_route_unknown")
        with patch("astrbot_host.acquaintance_api.request", NS(username="member-admin",
                query=_Query("subject_id=" + self.person()["subject_id"]), body=_body(b""))):
            self.assertEqual((await self.api.authorization())["data"]["code"], "acquaintance_route_required")

    async def test_admin_gate_refuses_api_keys_and_noncore_operators(self):
        app = await self.ready()
        denied = await self.send("member_settings", username="api_key:synthetic")
        self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        operator = dashboard_operator(app.runtime, "limited", at=self.clock.now())
        policy = ObjectAccessPolicy(app.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
                        expected_revision=policy.revision, observed_at=self.clock.now())
        denied = await self.send("set_identity", username="limited", command={})
        self.assertEqual(denied["data"]["code"], "core_access_required")

    async def test_dialogue_off_on_and_settings_survive_host_reopen(self):
        await self.ready()
        person = self.person()
        for enabled in (False, True, False):
            auth = (await self.send("authorization"))["data"]
            result = await self.send("authorize", command={**person, "operation_key": "switch-" + str(auth["policy_revision"]),
                "capability": "conversation.reply", "enabled": enabled, "expected_revision": auth["policy_revision"]})
            self.assertEqual(result["status"], "ok", result)
            self.controller.authority.context("first", "role-a")
        await self.configure({"profile": {"default_nickname": "重载后的称呼"}}, key="before-reopen")
        await self.controller.terminate()
        self.controller = self.make_controller()
        (await self.controller.load_existing()).unwrap()
        self.api = AcquaintanceWebAPI(self.controller)
        auth = (await self.send("authorization", person=person))["data"]
        self.assertEqual(next(row for row in auth["items"] if row["capability"] == "conversation.reply")["state"], "revoked")
        self.assertEqual((await self.settings(person))["profile"]["settings"]["default_nickname"], "重载后的称呼")

    async def test_reenabled_permission_and_identity_survive_reopen(self):
        await self.ready()
        person = self.person()
        for enabled in (False, True):
            auth = (await self.send("authorization"))["data"]
            result = await self.send("authorize", command={**person, "operation_key": "reopen-" + str(enabled),
                "capability": "conversation.reply", "enabled": enabled, "expected_revision": auth["policy_revision"]})
            self.assertEqual(result["status"], "ok", result)
        await self.controller.terminate()
        self.controller = self.make_controller()
        (await self.controller.load_existing()).unwrap()
        self.api = AcquaintanceWebAPI(self.controller)
        auth = (await self.send("authorization", person=person))["data"]
        self.assertEqual(next(row for row in auth["items"] if row["capability"] == "conversation.reply")["state"], "active")
        result = await self.send("set_identity", command={**person, "operation_key": "important-reopen",
            "tier": "important", "expected_revision": auth["identity_revision"]})
        self.assertEqual(result["status"], "ok", result)
        await self.controller.terminate()
        self.controller = self.make_controller()
        (await self.controller.load_existing()).unwrap()
        self.api = AcquaintanceWebAPI(self.controller)
        self.assertEqual((await self.send("authorization", person=person))["data"]["identity_tier"], "important")


if __name__ == "__main__":
    unittest.main()
