"""Account edits synchronize private targets without widening group access."""

from copy import deepcopy
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests import astrbot_data_root  # Establish isolation before the SDK import.
from astrbot_host.account_session_api import AccountSessionWebAPI
from tests.group_host_support import group_config


class AccountTargetSyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = group_config()
        self.accounts = [
            {"platform_id": "qq-main", "account_id": "100", "bot_id": "bot-a"},
            {"platform_id": "qq-second", "account_id": "101", "bot_id": "bot-b"},
        ]
        self.personas = deepcopy(self.config["multi_host"]["personas"])
        self.discovered = {"accounts": self.accounts, "personas": self.personas, "targets": []}

        async def apply(candidate):
            self.config.clear()
            self.config.update(candidate)
            return {"saved": True, "requires_reload": False, "requires_initialize": False}

        self.controller = NS(config=self.config, apply_bindings=AsyncMock(side_effect=apply))
        self.api = AccountSessionWebAPI(self.controller)
        self.api._discovered = AsyncMock(return_value=self.discovered)

    async def save(self, **body):
        request = NS(username="admin", query={},
            body=AsyncMock(return_value=json.dumps(body).encode("utf-8")))
        with patch("astrbot_host.account_session_api.request", request):
            return await self.api.save()

    async def test_new_account_gets_private_template_and_preserves_existing_ids_and_groups(self):
        section = self.config["multi_host"]
        section["targets"] = [row for row in section["targets"] if row["bot_id"] == "bot-a"]
        section["group_targets"] = [row for row in section["group_targets"] if row["bot_id"] == "bot-a"]
        section["personas"] = [row for row in section["personas"] if row["bot_id"] == "bot-a"]
        previous_private = deepcopy(section["targets"])
        previous_groups = deepcopy(section["group_targets"])

        result = await self.save(accounts=self.accounts, personas=self.personas, groups=previous_groups)

        self.assertEqual(result["status"], "ok", result)
        current = self.config["multi_host"]
        self.assertEqual(current["targets"][:1], previous_private)
        template = current["targets"][1]
        self.assertEqual((template["platform_id"], template["account_id"],
                          template["bot_id"], template["participant_id"]),
                         ("qq-second", "101", "bot-b", "*"))
        self.assertEqual(current["group_targets"], previous_groups)
        self.assertTrue(all(row["group_id"] != "*" for row in current["group_targets"]))
        self.assertEqual(result["data"]["configuration"]["sessions"], current["targets"])

    async def test_removed_account_drops_old_private_group_and_persona_references(self):
        previous = deepcopy(self.config["multi_host"])

        result = await self.save(accounts=self.accounts[:1], personas=previous["personas"],
            sessions=previous["targets"], groups=previous["group_targets"])

        self.assertEqual(result["status"], "ok", result)
        current = self.config["multi_host"]
        self.assertEqual(current["accounts"], self.accounts[:1])
        self.assertEqual(current["targets"], previous["targets"][:1])
        self.assertEqual(current["group_targets"], previous["group_targets"][:2])
        self.assertTrue(all(row["bot_id"] == "bot-a" for row in current["personas"]))

    async def test_omitted_groups_preserve_exact_groups_and_explicit_empty_groups_remove_them(self):
        groups = deepcopy(self.config["multi_host"]["group_targets"])

        result = await self.save(accounts=self.accounts, personas=self.personas)

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["multi_host"]["group_targets"], groups)
        result = await self.save(accounts=self.accounts, personas=self.personas, groups=[])
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["multi_host"]["group_targets"], [])

    async def test_existing_wildcard_targets_keep_their_ids_on_role_save(self):
        section = self.config["multi_host"]
        section["targets"][0]["participant_id"] = "*"
        section["group_targets"][0]["group_id"] = "*"
        previous = deepcopy(section)

        result = await self.save(accounts=self.accounts, personas=self.personas)

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["multi_host"]["targets"], previous["targets"])
        self.assertEqual(self.config["multi_host"]["group_targets"], previous["group_targets"])

    async def test_new_target_reference_to_unselected_account_is_rejected(self):
        before = deepcopy(self.config)
        groups = [*self.config["multi_host"]["group_targets"],
                  {**self.accounts[1], "group_id": "999"}]

        result = await self.save(accounts=self.accounts[:1], personas=self.personas, groups=groups)

        self.assertEqual(result["status"], "error", result)
        self.assertEqual(result["data"]["code"], "account_config_invalid")
        self.assertEqual(self.config, before)
        self.controller.apply_bindings.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
