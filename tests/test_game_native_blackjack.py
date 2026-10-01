"""V2 blackjack keeps the dealer hole card hidden and replays one scoped round."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from astrbot_host.native_extensions import NativeExtensionRegistry
from companion_v2.capabilities.native import parse_manifest
from companion_v2.memory.game_ingestion import GAME_ACTIONS
from astrbot_plugin_game_companion.blackjack import BlackjackCard, RANKS, SUITS
from astrbot_plugin_game_companion.native_v2 import provider as game_provider

from tests.test_game_native_pig_dice import request


def shoe_with_draws(ranks):
    shoe = [BlackjackCard(rank, suit) for _ in range(6) for suit in SUITS for rank in RANKS]
    for offset, rank in enumerate(ranks):
        target = len(shoe) - offset - 1
        source = next(index for index in range(target) if shoe[index].rank == rank)
        shoe[source], shoe[target] = shoe[target], shoe[source]
    return shoe


class NativeBlackjackTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_card_settlement_restart_and_scope(self):
        plugin = SimpleNamespace(native_v2_blackjack_enabled=True)
        with tempfile.TemporaryDirectory() as root:
            provider = game_provider.NativeGameProvider(plugin, Path(root), version="0.2.8")
            manifest = parse_manifest(provider.manifest(), plugin_id=game_provider.PLUGIN_ID,
                                      version="0.2.8")
            self.assertEqual(len(manifest.tools), 5)
            star = SimpleNamespace(root_dir_name=game_provider.PLUGIN_ID, version="0.2.8",
                activated=True, star_cls=SimpleNamespace(extension_api=SimpleNamespace(
                    companion_v2_native=lambda: provider)))
            self.assertEqual(NativeExtensionRegistry(SimpleNamespace(
                get_all_stars=lambda: [star])).issues, ())
            self.assertEqual(set(GAME_ACTIONS) & {game_provider.BLACKJACK_CREATE,
                game_provider.BLACKJACK_HIT, game_provider.BLACKJACK_STAND},
                {game_provider.BLACKJACK_CREATE, game_provider.BLACKJACK_HIT,
                 game_provider.BLACKJACK_STAND})

            with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(
                    ["10", "6", "9", "8", "4", "5"])):
                opened = await provider.execute(request(provider, game_provider.BLACKJACK_CREATE,
                    {"difficulty": "normal"}, "create"), before_dispatch=lambda: True)
            game = opened["result"]["game"]
            game_id = game["game_id"]
            self.assertEqual(game["status"], "active")
            self.assertTrue(game["state"]["dealer_hidden"])
            self.assertEqual(len(game["state"]["dealer_cards"]), 1)
            self.assertNotIn("shoe", json.dumps(game))
            self.assertNotIn("history", game["state"])
            other = await provider.execute(request(provider, game_provider.BLACKJACK_READ,
                {}, "other-read", subject="player-b"), before_dispatch=lambda: True)
            self.assertIsNone(other["result"]["game"])

            hit = request(provider, game_provider.BLACKJACK_HIT, {"game_id": game_id}, "hit")
            dealt = await provider.execute(hit, before_dispatch=lambda: True)
            self.assertEqual(dealt["result"]["game"]["state"]["hands"]["1"]["value"], 20)
            self.assertTrue(dealt["result"]["game"]["state"]["dealer_hidden"])
            restarted = game_provider.NativeGameProvider(plugin, Path(root), version="0.2.8")
            repeated = await restarted.execute(hit, before_dispatch=lambda: True)
            self.assertEqual(repeated["operation_id"], dealt["operation_id"])
            self.assertEqual(repeated["result"], dealt["result"])
            settled = await restarted.execute(request(restarted, game_provider.BLACKJACK_STAND,
                {"game_id": game_id}, "stand"), before_dispatch=lambda: True)
            self.assertEqual(settled["result"]["game"]["status"], "finished")
            self.assertEqual(settled["result"]["game"]["outcome"], "player")
            self.assertFalse(settled["result"]["game"]["state"]["dealer_hidden"])
            self.assertEqual(settled["result"]["game"]["state"]["results"]["1"], "win")
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_original_invocation_mismatch"):
                await restarted.execute(request(restarted, game_provider.BLACKJACK_HIT,
                    {"game_id": game_id}, "hit", subject="player-b"), before_dispatch=lambda: True)
            plugin.native_v2_blackjack_enabled = False
            self.assertEqual(restarted.manifest()["tools"], [])

    async def test_natural_result_and_corrupt_shoe(self):
        plugin = SimpleNamespace(native_v2_blackjack_enabled=True)
        with tempfile.TemporaryDirectory() as root:
            provider = game_provider.NativeGameProvider(plugin, Path(root), version="0.2.8")
            with patch.object(game_provider, "fresh_shoe", return_value=shoe_with_draws(
                    ["A", "K", "9", "8"])):
                opened = await provider.execute(request(provider, game_provider.BLACKJACK_CREATE,
                    {"difficulty": "normal"}, "natural"), before_dispatch=lambda: True)
            self.assertEqual(opened["result"]["game"]["status"], "finished")
            self.assertEqual(opened["result"]["game"]["state"]["results"]["1"], "blackjack_win")
            path = Path(root) / "native_v2" / "games.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            room = next(iter(next(iter(data["scopes"].values())).values()))
            room["shoe"][0] = room["shoe"][1]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_store_invalid"):
                game_provider.NativeGameProvider(plugin, Path(root), version="0.2.8")


if __name__ == "__main__":
    unittest.main()
