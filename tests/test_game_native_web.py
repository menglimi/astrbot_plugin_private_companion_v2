"""Browser and mobile tickets operate on the V2 native game ledger."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from companion_v2.games.native import provider as game_provider
from companion_v2.product import PRODUCT_VERSION
from astrbot_host.native_extensions.game.rooms_methods import GameRoomsMethods


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

    async def test_role_black_starts_real_game_and_returned_room_continues_it(self):
        async def access_base():
            return "http://127.0.0.1:6331"

        runtime = GameRoomsMethods()
        runtime.server_enabled = True
        runtime._native_provider = self.provider
        runtime._ensure_mobile_room_access = access_base
        self.plugin.native_game_room_access = runtime.native_game_room_access
        created = await self.provider.execute(request(self.provider, game_provider.GOMOKU_CREATE,
            {"difficulty": "normal", "human_side": "white"}, "role-black-create"), before_dispatch=lambda: True)
        result = created["result"]
        self.assertEqual(result["game"]["state"]["human_color"], 2)
        self.assertEqual(result["game"]["moves"], [[7, 7, 1]])
        self.assertTrue(result["room_url"].startswith("http://127.0.0.1:6331/native/"))
        ticket = result["room_url"].rsplit("/", 1)[1]
        state = await self.provider.web_state(ticket)
        self.assertEqual(state["game"]["game_id"], result["game"]["game_id"])
        self.assertEqual(state["game"]["state"]["turn"], 2)
        moved = await self.provider.web_action(ticket, {"action": "move", "row": 7, "column": 8})
        self.assertEqual(moved["game"]["state"]["move_count"], 3)
        replay = game_provider.NativeGameProvider(self.plugin, self.root, version=PRODUCT_VERSION)
        saved = await replay.execute(request(replay, game_provider.GOMOKU_READ, {}, "read-reloaded"),
            before_dispatch=lambda: True)
        self.assertEqual(saved["result"]["game"]["state"]["human_color"], 2)
        self.assertEqual(saved["result"]["game"]["state"]["move_count"], 3)

    async def test_room_access_failure_keeps_confirmed_game_instead_of_recreating(self):
        async def unavailable(*args, **kwargs):
            raise RuntimeError("synthetic access failure")

        self.plugin.native_game_room_access = unavailable
        original = request(self.provider, game_provider.GOMOKU_CREATE, {"difficulty": "normal"}, "access-fails")
        created = await self.provider.execute(original, before_dispatch=lambda: True)
        repeated = await self.provider.execute(original, before_dispatch=lambda: True)
        self.assertEqual(created["state"], "succeeded")
        self.assertNotIn("room_url", created["result"])
        self.assertEqual(created["result"]["room_access"]["state"], "unavailable")
        self.assertEqual(created["result"]["game"]["game_id"], repeated["result"]["game"]["game_id"])
        self.assertEqual(len(self.provider.list_web_games()), 1)

        async def restored(game_id, *, before_dispatch):
            before_dispatch()
            ticket = self.provider.issue_web_ticket(game_id)
            return {"state": "ready", "url": f"http://127.0.0.1:6331/native/{ticket}"}

        self.plugin.native_game_room_access = restored
        recovered = await self.provider.lookup(original, before_dispatch=lambda: True)
        self.assertEqual(recovered["result"]["game"]["game_id"], created["result"]["game"]["game_id"])
        ticket = recovered["result"]["room_url"].rsplit("/", 1)[1]
        self.assertEqual((await self.provider.web_state(ticket))["game"]["game_id"],
                         created["result"]["game"]["game_id"])
        self.assertEqual(len(self.provider.list_web_games()), 1)

    async def test_public_failure_keeps_explicit_local_entry_for_same_game(self):
        runtime = GameRoomsMethods()
        runtime.server_enabled = True
        runtime._native_provider = self.provider
        runtime._ensure_mobile_room_access = AsyncMock(side_effect=RuntimeError("public health unavailable"))
        runtime.room_server = SimpleNamespace(running=False, local_base_url="http://127.0.0.1:6331",
                                             start=AsyncMock())
        self.plugin.native_game_room_access = runtime.native_game_room_access
        original = request(self.provider, game_provider.GOMOKU_CREATE,
                           {"difficulty": "normal", "human_side": "white"}, "public-fails")
        created = await self.provider.execute(original, before_dispatch=lambda: True)
        access = created["result"]["room_access"]
        self.assertEqual(access["access_scope"], "same_device")
        self.assertEqual(access["public_access"], "unavailable")
        runtime.room_server.start.assert_awaited_once()
        ticket = created["result"]["room_url"].rsplit("/", 1)[1]
        state = await self.provider.web_state(ticket)
        self.assertEqual(state["game"]["moves"], [[7, 7, 1]])
        self.assertEqual(state["game"]["game_id"], created["result"]["game"]["game_id"])
        moved = await self.provider.web_action(ticket, {"action": "move", "row": 7, "column": 8})
        self.assertEqual(moved["game"]["state"]["move_count"], 3)
        self.assertEqual(len(self.provider.list_web_games()), 1)

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

    async def test_bot_reply_resumes_free_placement_without_adding_a_human_move(self):
        for kind in ("gomoku", "tictactoe"):
            created = await self.provider.create_mobile_game(f"resume-{kind}", kind)
            ticket = created["ticket"]
            row = column = 7 if kind == "gomoku" else 1
            await self.provider.web_action(ticket, {"action": "interact", "source": {"kind": "tray", "color": 1},
                "target": {"row": row, "column": column, "x": .5, "y": .5}, "interaction": "click"})
            result = await self.provider.web_action(ticket, {"action": "reply"})
            self.assertEqual(len(result["game"]["moves"]), 2)
            self.assertEqual(result["game"]["moves"][0], [row, column, 1])
            self.assertEqual(result["game"]["moves"][1][2], 2)
            state = result["game"]["state"]
            self.assertEqual(state["turn"], 1)
            self.assertEqual(state["pieces"][1]["x"], .5)
            with self.assertRaisesRegex(game_provider.NativeGameError, "game_illegal_move"):
                await self.provider.web_action(ticket, {"action": "reply"})
            self.assertEqual(len((await self.provider.web_state(ticket))["game"]["moves"]), 2)

    async def test_reply_uses_actual_bot_color_and_rejects_finished_or_nonboard_games(self):
        created = await self.provider.execute(request(self.provider, game_provider.GOMOKU_CREATE,
            {"difficulty": "normal", "human_side": "white"}, "resume-white"), before_dispatch=lambda: True)
        ticket = self.provider.issue_web_ticket(created["result"]["game"]["game_id"])
        await self.provider.web_action(ticket, {"action": "interact", "source": {"kind": "tray", "color": 2},
            "target": {"row": 7, "column": 8, "x": .5, "y": .5}, "interaction": "click"})
        result = await self.provider.web_action(ticket, {"action": "reply"})
        self.assertEqual(result["game"]["moves"][-1][2], 1)
        self.assertEqual(result["game"]["state"]["turn"], 2)
        await self.provider.web_action(ticket, {"action": "close"})
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_not_active"):
            await self.provider.web_action(ticket, {"action": "reply"})
        dice = await self.provider.create_mobile_game("resume-dice", "pig_dice")
        with self.assertRaisesRegex(game_provider.NativeGameError, "invalid_game_arguments"):
            await self.provider.web_action(dice["ticket"], {"action": "reply"})


if __name__ == "__main__":
    unittest.main()
