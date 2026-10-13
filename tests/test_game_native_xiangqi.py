"""Engine replay, atomic rounds and scope checks for V2 chat Xiangqi."""

import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from companion_v2.capabilities.native import parse_manifest
from companion_v2.games.native import provider as game_provider
from companion_v2.product import PRODUCT_VERSION
from tests.native_internal_support import internal_registry
from tests.test_game_native_pig_dice import request


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.fail_bot = False
        self.entered = self.release = None

    async def legal_moves(self, moves):
        self.calls.append(("legal", tuple(moves)))
        return {(): ["a3a4", "b0c2"], ("a3a4",): ["a6a5"],
                ("a3a4", "a6a5"): ["b0c2"], ("b0c2",): [],
                ("a3a4", "a6a5", "b0c2"): []}.get(tuple(moves), [])

    async def choose_move(self, moves, difficulty):
        self.calls.append(("choose", tuple(moves), difficulty))
        if self.entered is not None:
            self.entered.set()
            await self.release.wait()
        if self.fail_bot:
            raise RuntimeError("synthetic engine failure")
        return "a3a4" if not moves else "a6a5"


class NativeXiangqiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.engine = FakeEngine()
        self.plugin = SimpleNamespace(native_v2_xiangqi_enabled=True, xiangqi_engine=self.engine)
        self.provider = self.reopen()

    def reopen(self):
        return game_provider.NativeGameProvider(self.plugin, self.root, version=PRODUCT_VERSION)

    def opening(self, invocation_id="create", **changes):
        return request(self.provider, game_provider.XIANGQI_CREATE,
                       {"difficulty": "normal", "human_side": "red", **changes}, invocation_id)

    def move(self, game_id, invocation_id="move", *, terminal=False):
        coordinates = [9, 1, 7, 2] if terminal else [6, 0, 5, 0]
        return request(self.provider, game_provider.XIANGQI_MOVE,
                       dict(zip(("from_row", "from_column", "to_row", "to_column"), coordinates))
                       | {"game_id": game_id}, invocation_id)

    async def execute(self, value, guard=lambda: True):
        return await self.provider.execute(value, before_dispatch=guard)

    async def test_manifest_restart_replay_scope_and_terminal_result(self):
        manifest = parse_manifest(self.provider.manifest(), plugin_id=game_provider.PLUGIN_ID, version=PRODUCT_VERSION)
        self.assertEqual(len(manifest.tools), 35)
        self.assertEqual({tool["action"] for tool in manifest.tools if tool["action"].startswith("game.xiangqi.")},
                         game_provider.XIANGQI_ACTIONS)
        registry = internal_registry(self.provider)
        self.addAsyncCleanup(registry.aclose)
        self.assertEqual(registry.issues, ())
        self.assertEqual(len(registry.declarations()), 35)
        opened = await self.execute(self.opening())
        game_id = opened["result"]["game"]["game_id"]
        played = await self.execute(self.move(game_id))
        self.assertEqual(played["result"]["game"]["moves"], ["a3a4", "a6a5"])
        self.provider = self.reopen()
        count = len(self.engine.calls)
        repeated = await self.execute(self.move(game_id))
        self.assertEqual(repeated, played)
        self.assertEqual(len(self.engine.calls), count)
        snapshot = await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "read"))
        self.assertEqual(snapshot["result"]["game"]["state"]["board"][5][0], "P")
        self.assertEqual(snapshot["result"]["game"]["state"]["board"][4][0], "p")
        other = await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "other", subject="player-b"))
        self.assertIsNone(other["result"]["game"])
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_original_invocation_mismatch"):
            moved = self.move(game_id)
            moved["context"]["actor"]["subject"]["subject_id"] = "player-b"
            await self.execute(moved)
        terminal = await self.execute(self.move(game_id, "terminal", terminal=True))
        self.assertEqual(terminal["result"]["game"]["status"], "finished")
        self.assertEqual(terminal["result"]["game"]["outcome"], "player")
        self.provider = self.reopen()
        self.assertEqual((await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "final-read")))
                         ["result"]["game"], terminal["result"]["game"])
        self.assertEqual(await self.provider.lookup(self.move(game_id, "terminal", terminal=True),
                                                   before_dispatch=lambda: True), terminal)

    async def test_black_opening_resume_and_close_with_disabled_flag(self):
        opened = await self.execute(self.opening(human_side="black"))
        game = opened["result"]["game"]
        self.assertEqual(game["moves"], ["a3a4"])
        self.assertEqual(game["state"]["turn"], "black")
        resumed = await self.execute(self.opening("resume", difficulty="hard"))
        self.assertEqual(resumed["result"]["game"], game)
        manifest = self.provider.manifest()
        self.plugin.native_v2_xiangqi_enabled = False
        self.assertEqual(self.provider.manifest(), manifest)
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_xiangqi_disabled"):
            await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "disabled"))
        closed = await self.execute(request(self.provider, game_provider.XIANGQI_CLOSE,
            {"game_id": game["game_id"]}, "close"))
        self.assertEqual(closed["result"]["game"]["status"], "closed")
        self.assertEqual(closed["result"]["game"]["state"]["legal_moves"], [])
        self.reopen()

    async def test_engine_failure_rolls_back_human_half_round_and_replays_failed_receipt(self):
        game_id = (await self.execute(self.opening()))["result"]["game"]["game_id"]
        self.engine.fail_bot = True
        failed = await self.execute(self.move(game_id))
        self.assertEqual((failed["state"], failed["effect"]), ("failed", "not_committed"))
        self.assertEqual(next(iter(next(iter(self.provider.store.data["scopes"].values())).values()))["moves"], [])
        self.provider = self.reopen()
        count = len(self.engine.calls)
        self.assertEqual(await self.execute(self.move(game_id)), failed)
        self.assertEqual(len(self.engine.calls), count)
        self.engine.fail_bot = False
        played = await self.execute(self.move(game_id, "retry-new"))
        self.assertEqual(played["result"]["game"]["moves"], ["a3a4", "a6a5"])

    async def test_async_round_and_other_game_do_not_overwrite_each_other(self):
        self.plugin.native_v2_tictactoe_enabled = True
        game_id = (await self.execute(self.opening()))["result"]["game"]["game_id"]
        self.engine.entered, self.engine.release = asyncio.Event(), asyncio.Event()
        chess = asyncio.create_task(self.execute(self.move(game_id)))
        await asyncio.wait_for(self.engine.entered.wait(), 1)
        tic = asyncio.create_task(self.execute(request(self.provider, game_provider.CREATE,
            {"difficulty": "normal"}, "tic-create")))
        await asyncio.sleep(0)
        self.assertFalse(tic.done())
        self.engine.release.set()
        results = await asyncio.gather(chess, tic)
        self.assertTrue(all(result["state"] == "succeeded" for result in results))
        self.assertEqual(len(self.provider.store.data["operations"]), 3)
        self.assertEqual(len(next(iter(self.provider.store.data["scopes"].values()))), 2)
        self.reopen()

    async def test_revocation_and_cancellation_before_commit_leave_original_round(self):
        game_id = (await self.execute(self.opening()))["result"]["game"]["game_id"]
        self.engine.entered, self.engine.release = asyncio.Event(), asyncio.Event()
        permitted = True
        playing = asyncio.create_task(self.execute(self.move(game_id), guard=lambda: permitted))
        await asyncio.wait_for(self.engine.entered.wait(), 1)
        permitted = False
        self.engine.release.set()
        with self.assertRaisesRegex(game_provider.NativeGameError, "host_authority_revoked"):
            await playing
        self.assertNotIn("move", self.provider.store.data["operations"])
        self.engine.release.clear()
        self.engine.entered.clear()
        playing = asyncio.create_task(self.execute(self.move(game_id, "cancelled")))
        await asyncio.wait_for(self.engine.entered.wait(), 1)
        playing.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await playing
        self.assertNotIn("cancelled", self.provider.store.data["operations"])
        room = next(iter(next(iter(self.provider.store.data["scopes"].values())).values()))
        self.assertEqual(room["moves"], [])

    async def test_disable_while_engine_waits_prevents_commit_and_late_read(self):
        game_id = (await self.execute(self.opening()))["result"]["game"]["game_id"]
        self.engine.entered, self.engine.release = asyncio.Event(), asyncio.Event()
        playing = asyncio.create_task(self.execute(self.move(game_id)))
        await asyncio.wait_for(self.engine.entered.wait(), 1)
        self.plugin.native_v2_xiangqi_enabled = False
        self.engine.release.set()
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_xiangqi_disabled"):
            await playing
        self.assertNotIn("move", self.provider.store.data["operations"])
        self.assertEqual(next(iter(next(iter(self.provider.store.data["scopes"].values())).values()))["moves"], [])
        self.plugin.native_v2_xiangqi_enabled = True
        self.provider = self.reopen()
        entered, release = asyncio.Event(), asyncio.Event()
        legal_moves = self.engine.legal_moves
        async def waiting(moves):
            entered.set()
            await release.wait()
            return await legal_moves(moves)
        self.engine.legal_moves = waiting
        reading = asyncio.create_task(self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "read")))
        await asyncio.wait_for(entered.wait(), 1)
        self.plugin.native_v2_xiangqi_enabled = False
        release.set()
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_xiangqi_disabled"):
            await reading

    async def test_empty_initial_engine_result_cannot_restore_active_game(self):
        await self.execute(self.opening())
        self.provider = self.reopen()
        async def empty(moves):
            return []
        self.engine.legal_moves = empty
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_xiangqi_engine_unavailable"):
            await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "read"))
        failed = await self.execute(self.opening("resume"))
        self.assertEqual((failed["state"], failed["effect"]), ("failed", "not_committed"))

    async def test_invalid_arguments_engine_missing_and_illegal_replay(self):
        invalid = self.opening()
        invalid["arguments"]["human_side"] = "white"
        with self.assertRaisesRegex(game_provider.NativeGameError, "invalid_game_arguments"):
            await self.execute(invalid)
        self.plugin.xiangqi_engine = None
        result = await self.execute(self.opening("no-engine"))
        self.assertEqual((result["state"], result["effect"]), ("failed", "not_committed"))
        self.plugin.xiangqi_engine = self.engine
        game_id = (await self.execute(self.opening()))["result"]["game"]["game_id"]
        invalid = self.move(game_id)
        invalid["arguments"]["from_row"] = True
        with self.assertRaisesRegex(game_provider.NativeGameError, "invalid_game_arguments"):
            await self.execute(invalid)
        path = self.root / "native_v2" / "games.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        room = next(iter(next(iter(data["scopes"].values())).values()))
        room["moves"] = ["a0a1", "a9a8"]
        path.write_text(json.dumps(data), encoding="utf-8")
        self.provider = self.reopen()
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_store_invalid"):
            await self.execute(request(self.provider, game_provider.XIANGQI_READ, {}, "invalid-replay"))
        room["moves"] = ["bad"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(game_provider.NativeGameError, "game_store_invalid"):
            self.reopen()


if __name__ == "__main__":
    unittest.main()
