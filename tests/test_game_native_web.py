"""Browser and mobile tickets operate on the V2 native game ledger."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from companion_v2.games.native import provider as game_provider
from companion_v2.product import PRODUCT_VERSION


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


class NativeGameWebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = SimpleNamespace(
            native_v2_tictactoe_enabled=True,
            native_v2_gomoku_enabled=True,
            native_v2_pig_dice_enabled=True,
            native_v2_blackjack_enabled=True,
            native_v2_xiangqi_enabled=False,
            native_v2_turtle_soup_enabled=True,
            native_v2_draw_guess_enabled=True,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provider = game_provider.NativeGameProvider(self.plugin, self.root, version=PRODUCT_VERSION)

    async def test_web_ticket_moves_the_existing_chat_game(self):
        created = await self.provider.execute(request(self.provider, game_provider.CREATE,
            {"difficulty": "normal"}, "create"), before_dispatch=lambda: True)
        game_id = created["result"]["game"]["game_id"]
        ticket = self.provider.issue_web_ticket(game_id)

        state = await self.provider.web_state(ticket)
        self.assertEqual(state["game"]["game_id"], game_id)
        self.assertEqual(state["game"]["state"]["move_count"], 0)

        moved = await self.provider.web_action(ticket, {"action": "move", "row": 1, "column": 1})
        self.assertEqual(moved["game"]["state"]["move_count"], 2)
        chat_read = await self.provider.execute(request(self.provider, game_provider.READ, {}, "read"),
                                                before_dispatch=lambda: True)
        self.assertEqual(chat_read["result"]["game"]["game_id"], game_id)
        self.assertEqual(chat_read["result"]["game"]["state"]["move_count"], 2)
        with self.assertRaisesRegex(game_provider.NativeGameError, "invalid_game_arguments"):
            await self.provider.web_action(ticket, {"action": "move", "row": 9, "column": 9})

    async def test_mobile_ticket_uses_native_rules_without_persisting_mobile_identity(self):
        result = await self.provider.create_mobile_game("mobile-owner-1", "pig_dice")
        ticket = result["ticket"]
        self.assertEqual(result["game"]["game_type"], "pig_dice")
        rolled = await self.provider.web_action(ticket, {"action": "roll", "method": "cup"})
        self.assertEqual(rolled["game"]["events"][-1][0:2], ["human", "cup_roll"])

        other = await self.provider.create_mobile_game("mobile-owner-2", "pig_dice")
        self.assertNotEqual(result["game"]["game_id"], other["game"]["game_id"])
        persisted = (self.root / "native_v2" / "games.json").read_text(encoding="utf-8")
        self.assertNotIn("mobile-owner-1", persisted)
        self.assertNotIn("mobile-owner-2", persisted)
        self.assertEqual(len(self.provider.list_web_games()), 2)


if __name__ == "__main__":
    unittest.main()
