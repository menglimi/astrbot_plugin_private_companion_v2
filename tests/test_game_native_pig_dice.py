"""Scope, replay and receipt checks for V2's internal native dice game."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.capabilities.native import parse_manifest
from companion_v2.memory.game_ingestion import GAME_ACTIONS
from companion_v2.games.native import provider as game_provider
from companion_v2.product import PRODUCT_VERSION
from tests.native_internal_support import internal_registry


def request(provider, action, arguments, invocation_id, *, subject="player-a"):
    return {"schema": game_provider.SCHEMA, "invocation_id": invocation_id,
            "parent_task_id": "parent", "tool_call_id": invocation_id,
            "origin_key": "private-scope", "arguments_hash": "arguments-a",
            "action": action,
            "context": {"actor": {"principal": {"native_account_id": "bot-a"},
                                  "subject": {"subject_id": subject}}},
            "binding": {"capability": action, "provider": game_provider.PROVIDER_ID,
                        "version": provider.version, "generation": provider.generation},
            "arguments": arguments, "deadline_at": "2026-09-27T00:00:00+00:00"}


class NativePigDiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_replay_scope_and_terminal_receipt(self):
        plugin = SimpleNamespace(native_v2_tictactoe_enabled=False,
                                 native_v2_gomoku_enabled=False, native_v2_pig_dice_enabled=True)
        with tempfile.TemporaryDirectory() as root:
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            manifest = parse_manifest(provider.manifest(), plugin_id=game_provider.PLUGIN_ID,
                                      version=PRODUCT_VERSION)
            self.assertEqual(len(manifest.tools), 35)
            manifest_actions = {tool["action"] for tool in manifest.tools}
            self.assertNotIn("game.pig_dice.cheat", manifest_actions)
            roll_tool = next(tool for tool in manifest.tools if tool["action"] == game_provider.PIG_ROLL)
            self.assertIn("cup", roll_tool["parameters"]["properties"]["method"]["enum"])
            registry = internal_registry(provider)
            self.addAsyncCleanup(registry.aclose)
            self.assertEqual(registry.issues, ())
            self.assertEqual(len(registry.declarations()), 35)
            self.assertEqual(set(GAME_ACTIONS) & {game_provider.PIG_ROLL, game_provider.PIG_HOLD},
                             {game_provider.PIG_ROLL, game_provider.PIG_HOLD})

            create = request(provider, game_provider.PIG_CREATE, {"difficulty": "normal"}, "create")
            opened = await provider.execute(create, before_dispatch=lambda: True)
            game_id = opened["result"]["game"]["game_id"]
            self.assertEqual(opened["result"]["game"]["state"]["turn"], "human")

            with patch("companion_v2.games.pig_dice.secrets.randbelow",
                       side_effect=[value for _ in range(9) for value in (4, 0)] + [4]) as dice:
                for turn in range(10):
                    roll = request(provider, game_provider.PIG_ROLL, {"game_id": game_id}, f"roll-{turn}")
                    rolled = await provider.execute(roll, before_dispatch=lambda: True)
                    self.assertEqual(rolled["state"], "succeeded")
                    if turn == 0:
                        restarted = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
                        repeated = await restarted.execute(roll, before_dispatch=lambda: True)
                        self.assertEqual(repeated["operation_id"], rolled["operation_id"])
                        self.assertEqual(dice.call_count, 1)
                        provider = restarted
                    hold = request(provider, game_provider.PIG_HOLD, {"game_id": game_id}, f"hold-{turn}")
                    settled = await provider.execute(hold, before_dispatch=lambda: True)
                    self.assertEqual(settled["state"], "succeeded")
            self.assertEqual(dice.call_count, 19)
            self.assertEqual(settled["result"]["game"]["status"], "finished")
            self.assertEqual(settled["result"]["game"]["outcome"], "player")
            self.assertEqual(settled["result"]["game"]["state"]["human_score"], 50)
            self.assertLessEqual(len(settled["result"]["game"]["events"]), 24)

            restarted = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            snapshot = await restarted.execute(request(restarted, game_provider.PIG_READ, {}, "read"),
                                               before_dispatch=lambda: True)
            self.assertEqual(snapshot["result"]["game"]["state"]["human_score"], 50)
            other = await restarted.execute(request(restarted, game_provider.PIG_READ, {}, "other-read",
                                                    subject="player-b"), before_dispatch=lambda: True)
            self.assertIsNone(other["result"]["game"])
            with self.assertRaisesRegex(game_provider.NativeGameError,
                                        "game_original_invocation_mismatch"):
                await restarted.execute(request(restarted, game_provider.PIG_HOLD,
                    {"game_id": game_id}, "hold-9", subject="player-b"), before_dispatch=lambda: True)
            declared = restarted.manifest()
            plugin.native_v2_pig_dice_enabled = False
            self.assertEqual(restarted.manifest(), declared)
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_pig_dice_disabled"):
                await restarted.execute(request(restarted, game_provider.PIG_READ, {}, "disabled-read"),
                                        before_dispatch=lambda: True)

    async def test_invalid_dice_ledger_fails_closed(self):
        plugin = SimpleNamespace(native_v2_pig_dice_enabled=True)
        with tempfile.TemporaryDirectory() as root:
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            await provider.execute(request(provider, game_provider.PIG_CREATE,
                {"difficulty": "normal"}, "create"), before_dispatch=lambda: True)
            path = Path(root) / "native_v2" / "games.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            room = next(iter(next(iter(data["scopes"].values())).values()))
            room["events"] = [["bot", "cheat_roll", 6]]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_store_invalid"):
                game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)

    async def test_cup_roll_is_a_regular_action_and_replays_its_physical_result(self):
        plugin = SimpleNamespace(native_v2_pig_dice_enabled=True)
        with tempfile.TemporaryDirectory() as root:
            provider = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            opened = await provider.execute(request(provider, game_provider.PIG_CREATE,
                {"difficulty": "normal"}, "create"), before_dispatch=lambda: True)
            game_id = opened["result"]["game"]["game_id"]
            roll = request(provider, game_provider.PIG_ROLL,
                {"game_id": game_id, "method": "cup"}, "cup-roll")
            with patch("companion_v2.games.pig_dice.secrets.randbelow", side_effect=[0, 5]) as dice:
                rolled = await provider.execute(roll, before_dispatch=lambda: True)
                self.assertEqual(rolled["result"]["game"]["state"]["turn_total"], 6)
                self.assertEqual(rolled["result"]["game"]["events"][-1], ["human", "cup_roll", [1, 6]])
                self.assertEqual(await provider.execute(roll, before_dispatch=lambda: True), rolled)
                self.assertEqual(dice.call_count, 2)

            invalid = request(provider, game_provider.PIG_ROLL,
                {"game_id": game_id, "method": "fixed-six"}, "invalid-method")
            with self.assertRaisesRegex(game_provider.NativeGameError, "invalid_game_arguments"):
                await provider.execute(invalid, before_dispatch=lambda: True)

            restarted = game_provider.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            snapshot = await restarted.execute(request(restarted, game_provider.PIG_READ, {}, "read"),
                                               before_dispatch=lambda: True)
            self.assertEqual(snapshot["result"]["game"]["events"], rolled["result"]["game"]["events"])
            self.assertEqual(snapshot["result"]["game"]["state"]["turn_total"],
                             rolled["result"]["game"]["state"]["turn_total"])


if __name__ == "__main__":
    unittest.main()
