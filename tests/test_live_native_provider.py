"""Focused contract checks for V2's internal Live native read port."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest

from companion_v2.capabilities.native import parse_manifest, parse_result
from companion_v2.execution.models import SideEffect
from companion_v2.games.native import provider as GAME
from companion_v2.live import provider as LIVE
from companion_v2.product import PRODUCT_VERSION
from tests.native_internal_support import internal_registry


def request(provider, action, arguments):
    return {"schema": LIVE.SCHEMA, "invocation_id": "live-read",
            "origin_key": "private-scope", "arguments_hash": "arguments-a",
            "action": action,
            "context": {"actor": {"principal": {"native_account_id": "12345"},
                                  "subject": {"subject_id": "onebot-user:12345"}}},
            "binding": {"capability": action, "provider": LIVE.PROVIDER_ID,
                        "version": provider.version, "generation": provider.generation},
            "arguments": arguments, "deadline_at": "2026-09-27T00:00:00+00:00"}


class FakeLive:
    def __init__(self):
        self.running = True
        self.native_v2_bili_events_enabled = True
        self.native_v2_twitch_events_enabled = True
        self._bili_session_id = "session-a"
        self._bili_session_started_at = time.time() - 30
        self._bili_events = []
        self._bili_live_client = SimpleNamespace(room_id=123)
        self._twitch_session_id = ""
        self._twitch_session_started_at = 0.0
        self._twitch_events = []
        self._twitch_channel_name = ""
        self.config = {}

    def _is_bili_live_running(self):
        return self.running

    def _is_twitch_live_running(self):
        return False

    def append(self, event_id):
        self._bili_events.append(SimpleNamespace(
            event_id=event_id, event_type="danmaku", username="viewer",
            content="hello", ts=time.time()))


class LiveNativeProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = FakeLive()
        self.provider = LIVE.NativeLiveProvider(self.plugin, version=PRODUCT_VERSION)

    async def read(self, arguments):
        original = request(self.provider, LIVE.EVENTS, arguments)
        receipt = await self.provider.execute(original, before_dispatch=lambda: True)
        parse_result(receipt, request=original, side_effect=SideEffect.NONE)
        return receipt["result"]

    async def test_incremental_cursor_and_new_session(self):
        self.plugin.append("event-a")
        self.plugin.append("event-b")
        first = await self.read({"platform": "bili", "limit": 12})
        self.assertEqual(first["latest_event_id"], "event-b")
        self.assertEqual(first["session_id"], "session-a")
        self.assertFalse(first["cursor_reset"])

        self.plugin.append("event-c")
        incremental = await self.read({"platform": "bili", "limit": 12,
                                       "session_id": "session-a", "after_event_id": "event-b"})
        self.assertEqual([event["event_id"] for event in incremental["events"]], ["event-c"])
        self.assertFalse(incremental["cursor_reset"])

        self.plugin._bili_session_id = "session-b"
        self.plugin._bili_session_started_at = time.time() - 1
        self.plugin._bili_events.clear()
        self.plugin.append("event-d")
        changed = await self.read({"platform": "bili", "limit": 12,
                                   "session_id": "session-a", "after_event_id": "event-b"})
        self.assertEqual([event["event_id"] for event in changed["events"]], ["event-d"])
        self.assertTrue(changed["cursor_reset"])
        self.assertEqual(changed["session_id"], "session-b")

        evicted = await self.read({"platform": "bili", "limit": 12,
                                   "session_id": "session-b", "after_event_id": "event-b"})
        self.assertTrue(evicted["cursor_reset"])
        self.assertEqual(evicted["latest_event_id"], "event-d")

        self.plugin.running = False
        stopped = await self.read({"platform": "bili", "limit": 12,
                                   "session_id": "session-b", "after_event_id": "event-d"})
        self.assertEqual(stopped["events"], [])
        self.assertEqual(stopped["session_id"], "")
        self.assertTrue(stopped["cursor_reset"])

    async def test_manifest_registry_and_invalid_session(self):
        manifest = parse_manifest(self.provider.manifest(), plugin_id=LIVE.PLUGIN_ID,
                                  version=PRODUCT_VERSION)
        self.assertEqual(len(manifest.tools), 2)
        registry = internal_registry(self.provider)
        self.addAsyncCleanup(registry.aclose)
        self.assertEqual(registry.issues, ())
        self.assertEqual(len(registry.declarations()), 2)
        for invalid in ("", "x" * 65, 7):
            with self.assertRaisesRegex(LIVE.NativeLiveError, "invalid_live_arguments"):
                await self.read({"platform": "bili", "limit": 12, "session_id": invalid})

    async def test_platform_switches_preserve_manifest_and_block_disabled_reads(self):
        original_manifest = self.provider.manifest()
        self.plugin.native_v2_bili_events_enabled = False
        self.provider = LIVE.NativeLiveProvider(self.plugin, version=PRODUCT_VERSION)
        manifest = parse_manifest(self.provider.manifest(), plugin_id=LIVE.PLUGIN_ID,
                                  version=PRODUCT_VERSION)
        self.assertEqual(len(manifest.tools), 2)
        self.assertEqual(self.provider.manifest()["tools"][1]["parameters"]["properties"]["platform"]["enum"],
                         ["bili", "twitch"])
        self.assertEqual(self.provider.manifest(), original_manifest)
        status_request = request(self.provider, LIVE.STATUS, {})
        status = (await self.provider.execute(status_request, before_dispatch=lambda: True))["result"]
        self.assertFalse(status["bili"]["enabled"])
        self.assertFalse(status["bili"]["running"])
        self.assertEqual(status["bili"]["room_id"], "")
        with self.assertRaisesRegex(LIVE.NativeLiveError, "live_platform_not_exposed"):
            await self.read({"platform": "bili", "limit": 12})

        self.plugin.native_v2_twitch_events_enabled = False
        self.provider = LIVE.NativeLiveProvider(self.plugin, version=PRODUCT_VERSION)
        disabled_manifest = self.provider.manifest()
        self.assertEqual(disabled_manifest, original_manifest)
        self.assertEqual([tool["action"] for tool in disabled_manifest["tools"]], [LIVE.STATUS, LIVE.EVENTS])
        self.assertEqual(len(parse_manifest(disabled_manifest, plugin_id=LIVE.PLUGIN_ID,
                                            version=PRODUCT_VERSION).tools), 2)
        with self.assertRaisesRegex(LIVE.NativeLiveError, "live_platform_not_exposed"):
            await self.read({"platform": "twitch", "limit": 12})

    async def test_game_native_setting_is_independent_of_web_room_switches(self):
        plugin = SimpleNamespace(native_v2_tictactoe_enabled=True, server_enabled=False,
                                 enabled_games={"tictactoe": False})
        with tempfile.TemporaryDirectory() as root:
            game = GAME.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            current = game._apply({"scopes": {}}, "scope-a", {
                "action": GAME.CREATE, "arguments": {"difficulty": "normal"}})
            self.assertEqual(current["status"], "active")
            plugin.native_v2_tictactoe_enabled = False
            with self.assertRaisesRegex(GAME.NativeGameError, "game_tictactoe_disabled"):
                game._apply({"scopes": {}}, "scope-a", {
                    "action": GAME.CREATE, "arguments": {"difficulty": "normal"}})

    async def test_game_and_live_register_together(self):
        with tempfile.TemporaryDirectory() as root:
            game = GAME.NativeGameProvider(SimpleNamespace(
                native_v2_tictactoe_enabled=True, native_v2_gomoku_enabled=False),
                Path(root), version=PRODUCT_VERSION)
            registry = internal_registry(self.provider, game)
            self.addAsyncCleanup(registry.aclose)
            self.assertEqual(registry.issues, ())
            self.assertEqual(len(registry.declarations()), 37)
            self.assertIsNotNone(registry.current_declaration(
                "native:astrbot_plugin_private_companion.live:live.events.recent"))
            self.assertIsNotNone(registry.current_declaration(
                "native:astrbot_plugin_private_companion.game:game.tictactoe.move"))

    async def test_gomoku_and_tictactoe_are_separate_durable_scoped_games(self):
        plugin = SimpleNamespace(native_v2_tictactoe_enabled=True,
                                 native_v2_gomoku_enabled=True, server_enabled=False,
                                 enabled_games={"tictactoe": False, "gomoku": False})

        def game_request(provider, action, arguments, invocation_id, subject="player-a"):
            return {"schema": GAME.SCHEMA, "invocation_id": invocation_id,
                    "parent_task_id": "parent", "tool_call_id": invocation_id,
                    "origin_key": "private-scope", "arguments_hash": "arguments-a",
                    "action": action,
                    "context": {"actor": {"principal": {"native_account_id": "bot-a"},
                                          "subject": {"subject_id": subject}}},
                    "binding": {"capability": action, "provider": GAME.PROVIDER_ID,
                                "version": provider.version, "generation": provider.generation},
                    "arguments": arguments, "deadline_at": "2026-09-27T00:00:00+00:00"}

        with tempfile.TemporaryDirectory() as root:
            provider = GAME.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            self.assertEqual(len(parse_manifest(provider.manifest(), plugin_id=GAME.PLUGIN_ID,
                                                version=PRODUCT_VERSION).tools), 35)
            registry = internal_registry(provider)
            self.addAsyncCleanup(registry.aclose)
            self.assertEqual(registry.issues, ())
            self.assertEqual(len(registry.declarations()), 35)
            manifest = provider.manifest()
            plugin.native_v2_tictactoe_enabled = False
            self.assertEqual(provider.manifest(), manifest)
            self.assertIsNotNone(registry.current_declaration(
                "native:astrbot_plugin_private_companion.game:game.tictactoe.snapshot"))
            with self.assertRaisesRegex(GAME.NativeGameError, "game_tictactoe_disabled"):
                await provider.execute(game_request(provider, GAME.READ, {}, "disabled-read"),
                                       before_dispatch=lambda: True)
            plugin.native_v2_tictactoe_enabled = True
            ttt = await provider.execute(game_request(provider, GAME.CREATE,
                {"difficulty": "normal"}, "ttt-create"), before_dispatch=lambda: True)
            gomoku_create = game_request(provider, GAME.GOMOKU_CREATE,
                {"difficulty": "normal"}, "gomoku-create")
            gomoku = await provider.execute(gomoku_create, before_dispatch=lambda: True)
            self.assertEqual(gomoku["result"]["game"]["game_type"], "gomoku")
            self.assertNotEqual(ttt["result"]["game"]["game_id"],
                                gomoku["result"]["game"]["game_id"])
            self.assertEqual((await provider.execute(gomoku_create, before_dispatch=lambda: True))
                             ["operation_id"], gomoku["operation_id"])

            game_id = gomoku["result"]["game"]["game_id"]
            moved = await provider.execute(game_request(provider, GAME.GOMOKU_MOVE,
                {"game_id": game_id, "row": 7, "column": 7}, "gomoku-move"),
                before_dispatch=lambda: True)
            self.assertEqual(moved["state"], "succeeded")
            self.assertEqual(moved["result"]["game"]["state"]["move_count"], 2)

            restarted = GAME.NativeGameProvider(plugin, Path(root), version=PRODUCT_VERSION)
            same = await restarted.execute(game_request(restarted, GAME.GOMOKU_READ,
                {}, "gomoku-read"), before_dispatch=lambda: True)
            self.assertEqual(same["result"]["game"]["state"]["move_count"], 2)
            other = await restarted.execute(game_request(restarted, GAME.GOMOKU_READ,
                {}, "other-read", subject="player-b"), before_dispatch=lambda: True)
            self.assertIsNone(other["result"]["game"])
            other_move = await restarted.execute(game_request(restarted, GAME.GOMOKU_MOVE,
                {"game_id": game_id, "row": 8, "column": 8}, "other-move",
                subject="player-b"), before_dispatch=lambda: True)
            self.assertEqual(other_move["state"], "failed")
            wrong_kind = await restarted.execute(game_request(restarted, GAME.MOVE,
                {"game_id": game_id, "row": 0, "column": 0}, "wrong-kind"),
                before_dispatch=lambda: True)
            self.assertEqual(wrong_kind["state"], "failed")


if __name__ == "__main__":
    unittest.main()
