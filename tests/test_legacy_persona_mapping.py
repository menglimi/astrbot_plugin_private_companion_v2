"""Upgrade native persona choices without splitting existing character data."""

from copy import deepcopy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from astrbot_host.identity_derivation import derive_role_id
from astrbot_host.legacy_persona_mapping import legacy_account_inventory
from companion_v2.legacy.configuration_migration import convert_account_configuration


class LegacyPersonaMappingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = {
            "basic_config": {"bot_scope_mode": "allowlist", "bot_scope_ids": ["100"],
                             "target_user_ids": ["200"], "plugin_specific_persona_id": "private-persona",
                             "enable_multi_persona_mode": False},
            "group_observation_config": {"enable_group_companion": True,
                "group_access_mode": "whitelist", "group_whitelist_ids": ["300"]},
        }
        self.accounts = [{"platform_id": "qq", "account_id": "100", "bot_id": "bot"},
                         {"platform_id": "qq", "account_id": "101", "bot_id": "other"}]
        self.choices = {"qq:FriendMessage:200": "private-persona",
                        "qq:GroupMessage:300": "group-persona"}
        self.controller = NS(config={"multi_host": {}},
            context=NS(persona_manager=NS(default_persona="private-persona"),
                conversation_manager=NS(get_curr_conversation_id=AsyncMock(return_value="conversation"),
                    get_conversation=AsyncMock(side_effect=AssertionError("must not read history")))),
            native_types=NS(persona_snapshot_lookup=AsyncMock(side_effect=lambda _ctx, umo, _cid: self.choices[umo]),
                persona_selection_lookup=lambda _ctx, _umo, selected: selected,
                session_persona_override_lookup=AsyncMock(return_value=None)))

    async def inventory(self):
        return await legacy_account_inventory(self.controller, self.source, self.accounts,
            ["private-persona", "group-persona", "unrelated-persona"])

    async def test_single_role_follows_authorized_private_and_group_personas_only(self):
        accounts = await self.inventory()
        plan = convert_account_configuration(self.source, accounts=accounts)
        mappings = plan.changes["multi_host.personas"]
        self.assertEqual({row["persona_id"] for row in mappings}, {"private-persona", "group-persona"})
        self.assertEqual({row["role_id"] for row in mappings}, {derive_role_id("100", "private-persona")})
        self.assertEqual(plan.changes["target.persona_id"], "private-persona")
        self.assertEqual([row["bot_id"] for row in plan.changes["multi_host.group_targets"]], ["bot"])
        self.assertEqual([call.args[1] for call in self.controller.native_types.persona_snapshot_lookup.await_args_list],
                         ["qq:FriendMessage:200", "qq:GroupMessage:300"])
        self.controller.context.conversation_manager.get_conversation.assert_not_awaited()

    async def test_supplement_keeps_the_existing_migrated_role_identifier(self):
        self.controller.config["multi_host"]["personas"] = [
            {"bot_id": "bot", "persona_id": "private-persona", "role_id": "existing-role"}]
        accounts = await self.inventory()
        plan = convert_account_configuration(self.source, accounts=accounts)
        self.assertEqual({row["role_id"] for row in plan.changes["multi_host.personas"]}, {"existing-role"})
        self.assertEqual(self.controller.config["multi_host"]["personas"], [
            {"bot_id": "bot", "persona_id": "private-persona", "role_id": "existing-role"}])

    async def test_existing_distinct_roles_are_never_silently_merged(self):
        self.controller.config["multi_host"]["personas"] = [
            {"bot_id": "bot", "persona_id": "private-persona", "role_id": "private-data"},
            {"bot_id": "bot", "persona_id": "group-persona", "role_id": "group-data"}]
        accounts = await self.inventory()
        pairs = convert_account_configuration(self.source, accounts=accounts).changes["multi_host.personas"]
        self.assertEqual({row["persona_id"]: row["role_id"] for row in pairs},
                         {"private-persona": "private-data", "group-persona": "group-data"})

    async def test_multi_persona_storage_remains_separate(self):
        self.source["basic_config"].update(enable_multi_persona_mode=True,
            multi_persona_ids=["private-persona", "group-persona"])
        accounts = await self.inventory()
        pairs = convert_account_configuration(self.source, accounts=accounts).changes["multi_host.personas"]
        self.assertEqual({row["role_id"] for row in pairs},
                         {derive_role_id("100", "private-persona"), derive_role_id("100", "group-persona")})

    async def test_multi_persona_mode_does_not_adopt_a_persona_outside_its_old_list(self):
        self.source["basic_config"].update(enable_multi_persona_mode=True,
            multi_persona_ids=["private-persona"])
        accounts = await self.inventory()
        plan = convert_account_configuration(self.source, accounts=accounts)
        self.assertNotIn("multi_host.group_targets", plan.changes)
        self.assertEqual([row["persona_id"] for row in plan.changes["multi_host.personas"]], ["private-persona"])
        self.assertIn("unavailable_persona", {item.kind for item in plan.differences})

    async def test_failed_window_lookup_does_not_fall_back_to_the_private_persona(self):
        del self.choices["qq:GroupMessage:300"]
        self.controller.native_types.persona_snapshot_lookup = AsyncMock(
            side_effect=lambda _ctx, umo, _cid: self.choices.get(umo))
        accounts = await self.inventory()
        plan = convert_account_configuration(self.source, accounts=accounts)
        self.assertIn("multi_host.targets", plan.changes)
        self.assertNotIn("multi_host.group_targets", plan.changes)

    async def test_new_window_uses_its_native_runner_default(self):
        self.controller.context.conversation_manager.get_curr_conversation_id.return_value = None
        self.controller.native_types.persona_snapshot_lookup = AsyncMock(return_value=None)
        self.controller.native_types.persona_selection_lookup = (
            lambda _ctx, umo, _selected: self.choices[umo])
        accounts = await self.inventory()
        self.assertEqual({row["persona_id"] for row in accounts[0]["native_windows"]},
                         {"private-persona", "group-persona"})

    async def test_window_override_precedes_the_native_persona(self):
        self.controller.native_types.session_persona_override_lookup = AsyncMock(return_value="group-persona")
        accounts = await self.inventory()
        self.controller.native_types.persona_snapshot_lookup.assert_not_awaited()
        self.assertEqual({row["persona_id"] for row in accounts[0]["native_windows"]}, {"group-persona"})

    async def test_changed_conversation_is_not_installed_as_a_verified_choice(self):
        self.controller.context.conversation_manager.get_curr_conversation_id.side_effect = [
            "old", "new", "group", "group"]
        accounts = await self.inventory()
        plan = convert_account_configuration(self.source, accounts=accounts)
        self.assertNotIn("multi_host.targets", plan.changes)
        self.assertIn("multi_host.group_targets", plan.changes)

    async def test_repeated_review_is_stable_and_does_not_mutate_source(self):
        original = deepcopy(self.source)
        self.assertEqual(await self.inventory(), await self.inventory())
        self.assertEqual(self.source, original)

    async def test_removed_old_persona_does_not_hide_authorized_native_windows(self):
        self.source["basic_config"]["plugin_specific_persona_id"] = "removed-persona"
        self.controller.config["multi_host"]["personas"] = [
            {"bot_id": "bot", "persona_id": "removed-persona", "role_id": "existing-role"}]
        plan = convert_account_configuration(self.source, accounts=await self.inventory())
        self.assertEqual({row["role_id"] for row in plan.changes["multi_host.personas"]}, {"existing-role"})
        self.assertIn("multi_host.targets", plan.changes)
        self.assertIn("multi_host.group_targets", plan.changes)

    async def test_all_recognized_disabled_forms_keep_single_role_ownership(self):
        for value in (False, 0, "off", " disabled ", "No", "0", ""):
            with self.subTest(value=value):
                self.source["basic_config"]["enable_multi_persona_mode"] = value
                plan = convert_account_configuration(self.source, accounts=await self.inventory())
                self.assertEqual({row["role_id"] for row in plan.changes["multi_host.personas"]},
                                 {derive_role_id("100", "private-persona")})

    async def test_invalid_switch_does_not_adopt_windows(self):
        self.source["basic_config"]["enable_multi_persona_mode"] = "unknown"
        plan = convert_account_configuration(self.source, accounts=await self.inventory())
        self.assertEqual(dict(plan.changes), {})
        self.assertIn("invalid_persona_selection", {item.kind for item in plan.differences})

    async def test_group_member_windows_only_adopt_personas_within_old_authorized_group(self):
        self.controller.context.conversation_manager.session_conversations = {
            "qq:GroupMessage:250_300": "member", "qq:GroupMessage:250_999": "unrelated"}
        self.choices["qq:GroupMessage:250_300"] = "member-persona"
        accounts = await legacy_account_inventory(self.controller, self.source, self.accounts,
            ["private-persona", "group-persona", "member-persona", "unrelated-persona"])
        plan = convert_account_configuration(self.source, accounts=accounts)
        self.assertEqual({row["persona_id"] for row in plan.changes["multi_host.personas"]},
                         {"private-persona", "group-persona", "member-persona"})
        self.assertEqual({row["role_id"] for row in plan.changes["multi_host.personas"]},
                         {derive_role_id("100", "private-persona")})
        self.assertNotIn("qq:GroupMessage:250_999",
            [call.args[1] for call in self.controller.native_types.persona_snapshot_lookup.await_args_list])

    async def test_missing_old_configuration_produces_no_authorized_mapping(self):
        accounts = await legacy_account_inventory(self.controller, None, self.accounts, ["private-persona"])
        self.assertTrue(all(not row["native_windows"] for row in accounts))
        self.controller.native_types.persona_snapshot_lookup.assert_not_awaited()
