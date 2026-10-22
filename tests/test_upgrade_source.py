"""Exercise the real import-before-schema boundary without a live installation."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from astrbot_host.upgrade_source import (
    CONFIG_NAME, preserve_before_schema, preserved_configuration_path,
)
from astrbot_host.legacy_config import read_v1_host_configuration


class UpgradeSourceTests(unittest.TestCase):
    def test_schema_pruning_and_reloads_keep_exact_legacy_source(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            config = data / "config"
            config.mkdir()
            old = b'\xef\xbb\xbf{"basic_config": {}, "target_user_ids": ["123"]}\r\n'
            path = config / CONFIG_NAME
            path.write_bytes(old)
            saved = preserve_before_schema(config)
            self.assertEqual(saved.read_bytes(), old)
            path.write_text('{"multi_host": {"enabled": false}}\n', encoding="utf-8")
            self.assertEqual(preserve_before_schema(config), saved)
            self.assertEqual(saved.read_bytes(), old)
            runtime = data / "plugin_data" / "astrbot_plugin_private_companion" / "companion-7"
            loaded, found, fingerprint = read_v1_host_configuration(runtime)
            self.assertEqual(found, saved)
            self.assertEqual(loaded["target_user_ids"], ["123"])
            self.assertEqual(len(fingerprint), 64)

    def test_changed_archive_is_not_silently_treated_as_a_new_install(self):
        with TemporaryDirectory() as directory:
            config = Path(directory)
            (config / CONFIG_NAME).write_text('{"basic_config": {}}', encoding="utf-8")
            saved = preserve_before_schema(config)
            saved.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                preserved_configuration_path(config)

    def test_new_install_does_not_create_an_upgrade_archive(self):
        with TemporaryDirectory() as directory:
            config = Path(directory)
            (config / CONFIG_NAME).write_text('{"multi_host": {}}', encoding="utf-8")
            self.assertIsNone(preserve_before_schema(config))
            self.assertEqual(len(list(config.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()


class UpgradeReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_uses_the_reviewed_source_and_live_inventory(self):
        from astrbot_host.upgrade_setup import UpgradeSetup
        with TemporaryDirectory() as directory:
            data = Path(directory)
            source = data / "plugin_data" / "astrbot_plugin_private_companion"
            source.mkdir(parents=True)
            (source / "companions.json").write_text("{}", encoding="utf-8")
            config = data / "config"
            config.mkdir()
            legacy = {"basic_config": {"target_user_ids": ["123"], "plugin_specific_persona_id": "test-persona",
                      "LLM_PROVIDER_ID": "test-model"}, "operation_access": {"public_operations": []}}
            (config / CONFIG_NAME).write_text(json.dumps(legacy), encoding="utf-8")
            controller = NS(data_root=source / "companion-7", config={"multi_host": {}},
                context=NS(get_provider_by_id=lambda _: object(),
                    conversation_manager=NS(get_curr_conversation_id=AsyncMock(return_value=None)),
                    get_config=lambda **_: {"provider_settings": {"default_personality": "test-persona"}}),
                session_topology=NS(accounts=lambda: [{"platform_id": "qq", "account_id": "456", "bot_id": "test-bot"}]),
                apply_bindings=AsyncMock(return_value={"saved": True, "started": False}))
            api = UpgradeSetup(controller)
            with patch("astrbot_host.upgrade_setup.available_personas", AsyncMock(return_value=["test-persona"])):
                plan, candidate = await api.plan()
                self.assertTrue(plan["can_prepare"], plan)
                self.assertEqual(candidate["multi_host"]["targets"][0]["participant_id"], "123")
                self.assertEqual(candidate["model"]["provider_id"], "test-model")
                self.assertIn("conversation.reply", candidate["multi_host"]["capabilities"])
                self.assertIn("memory.read", candidate["multi_host"]["capabilities"])
                self.assertIn("memory.reflect", candidate["multi_host"]["capabilities"])
                from companion_v2.execution.models import TaskError
                with self.assertRaises(TaskError):
                    await api.prepare("stale-review")
                controller.apply_bindings.assert_not_awaited()
                await api.prepare(plan["plan_token"])
                controller.apply_bindings.assert_awaited_once_with(candidate)
                controller.config["multi_host"]["accounts"] = [{"account_id": "456"}]
                existing, candidate = await api.plan()
                self.assertTrue(existing["configured"])
                self.assertIsNone(candidate)

    async def test_shared_role_upgrade_confirms_the_actual_private_persona_once(self):
        from astrbot_host.binding_store import read_binding
        from astrbot_host.upgrade_setup import UpgradeSetup
        from companion_v2.execution.models import TaskError

        with TemporaryDirectory() as directory:
            data = Path(directory)
            source = data / "plugin_data" / "astrbot_plugin_private_companion"
            source.mkdir(parents=True)
            (source / "companions.json").write_text("{}\n", encoding="utf-8")
            configuration = data / "config"
            configuration.mkdir()
            legacy = {"basic_config": {"target_user_ids": ["123"],
                "plugin_specific_persona_id": "private-persona", "enable_multi_persona_mode": False,
                "LLM_PROVIDER_ID": "test-model"},
                "group_observation_config": {"enable_group_companion": True,
                    "group_access_mode": "whitelist", "group_whitelist_ids": ["789"]}}
            (configuration / CONFIG_NAME).write_text(json.dumps(legacy), encoding="utf-8")
            choices = {"qq:FriendMessage:123": "private-persona", "qq:GroupMessage:789": "group-persona"}
            controller = NS(data_root=source / "companion-7", binding_root=data / "binding",
                config={"multi_host": {}},
                context=NS(get_provider_by_id=lambda _: object(),
                    conversation_manager=NS(get_curr_conversation_id=AsyncMock(return_value="same-cid"))),
                native_types=NS(persona_snapshot_lookup=AsyncMock(side_effect=lambda _ctx, umo, _cid: choices[umo]),
                    persona_selection_lookup=lambda _ctx, _umo, selected: selected),
                session_topology=NS(accounts=lambda: [{"platform_id": "qq", "account_id": "456", "bot_id": "bot"}]),
                apply_bindings=AsyncMock(return_value={"started": True}),
                confirm_binding=lambda: {"confirmed": True})
            api = UpgradeSetup(controller)
            with patch("astrbot_host.upgrade_setup.available_personas",
                       AsyncMock(return_value=["private-persona", "group-persona"])):
                plan, candidate = await api.plan()
                self.assertTrue(plan["can_prepare"])
                self.assertEqual({row["persona_id"] for row in candidate["multi_host"]["personas"]},
                                 {"private-persona", "group-persona"})
                self.assertEqual(len({row["role_id"] for row in candidate["multi_host"]["personas"]}), 1)
                choices["qq:FriendMessage:123"] = "group-persona"
                with self.assertRaises(TaskError) as changed:
                    await api.prepare(plan["plan_token"])
                self.assertEqual(changed.exception.code, "legacy_plan_stale")
                controller.apply_bindings.assert_not_awaited()
                choices["qq:FriendMessage:123"] = "private-persona"
                result = await api.prepare(plan["plan_token"])
                self.assertTrue(result["binding_confirmed"])
                self.assertEqual(read_binding(controller.binding_root).persona_id, "private-persona")
                controller.apply_bindings.assert_awaited_once_with(candidate)
