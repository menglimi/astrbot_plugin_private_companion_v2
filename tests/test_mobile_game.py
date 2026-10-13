"""Paired phone capabilities use the current V2 context and native receipts."""

from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from tests import test_mobile_together as together_support
# Establish the temporary SDK import root before importing the actual gateway.
from tests import test_astrbot_staging_host as host_support
from astrbot_host.mobile_game import GAME_KINDS, MobileGameBridge
from astrbot_host.native_extensions.reality.mobile_gateway import MobileGatewayMixin
from companion_v2.execution.models import TaskError


TOKEN = "valid-session-token-123456"


class MobileGameBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        together_support.MobileTogetherBridgeTests.setUp(self)
        self.allowed = {"game.tictactoe.create", "game.xiangqi.create", "game.turtle_soup.create"}
        self.declarations = []
        for kind in GAME_KINDS:
            action = "game." + kind + ".create"
            descriptor = SimpleNamespace(tool=SimpleNamespace(
                action=action, parameters_json=json.dumps({"type": "object", "properties": {}})),
                timeout_seconds=5)
            self.declarations.append(SimpleNamespace(host_tool_id="native:" + action, descriptor=descriptor))

        class Registry(type(self.registry)):
            def active_service(inner, extension_id):
                self.assertEqual(extension_id, "game")
                return self.service

            async def invoke(inner, host_tool_id, invocation):
                response = await super().invoke(host_tool_id, invocation)
                response.source.payload = json.dumps({"native": {"result": {"game": {
                    "game_id": "game-a", "provider_internal": "must-not-leak",
                }}}})
                if self.unknown_result:
                    response.state = "unknown"
                    response.effect = "none"
                    response.source = None
                return response

        self.registry = Registry()
        self.controller.native_extensions = self.registry
        self.service = SimpleNamespace(
            server_enabled=True,
            room_server=SimpleNamespace(running=False, local_base_url="http://127.0.0.1:6209"),
            _native_provider=SimpleNamespace(issue_web_ticket=Mock(return_value="ticket/a+b")),
            _ensure_mobile_room_access=AsyncMock(return_value="https://games.example"),
        )
        for kind in GAME_KINDS:
            setattr(self.service, "native_v2_" + kind + "_enabled", True)
        self.service.room_server.start = AsyncMock(side_effect=lambda: setattr(self.service.room_server, "running", True))
        self.unknown_result = False
        self.bridge = MobileGameBridge(self.controller)

    def test_status_filters_games_by_current_private_target_and_consent(self):
        result = self.bridge.status(TOKEN)
        self.assertTrue(result["ready"])
        self.assertEqual(result["games"], ["tictactoe", "xiangqi", "turtle_soup"])
        self.assertTrue(all(context is self.context for _, context in self.admissions))
        self.allowed.remove("game.tictactoe.create")
        self.assertEqual(self.bridge.status(TOKEN)["games"], ["xiangqi", "turtle_soup"])
        self.assertEqual(self.bridge.status("other-session-token-123456")["games"], [])

    def test_disabled_room_server_and_stale_application_have_no_games(self):
        self.service.server_enabled = False
        result = self.bridge.status(TOKEN)
        self.assertFalse(result["enabled"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["games"], [])
        self.service.server_enabled = True
        self.registry.application = SimpleNamespace(state="running")
        result = self.bridge.status(TOKEN)
        self.assertFalse(result["available"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["games"], [])

    async def test_retries_keep_native_invocation_identity_and_private_context(self):
        first = await self.bridge.create(TOKEN, "request-game-1", "native_v2:tictactoe", via_mobile_gateway=True)
        second = await self.bridge.create(TOKEN, "request-game-1", "tictactoe", via_mobile_gateway=True)
        self.assertEqual(self.invocations[0].invocation_id, self.invocations[1].invocation_id)
        self.assertEqual(self.invocations[0].parent_task_id, self.invocations[1].parent_task_id)
        self.assertIs(self.invocations[0].context, self.context)
        self.assertIs(self.invocations[0].descriptor, self.declarations[0].descriptor)
        self.assertEqual(json.loads(self.invocations[0].arguments_json), {"difficulty": "normal"})
        self.assertEqual(first["result"]["url"], "http://127.0.0.1:6209/native/ticket%2Fa%2Bb")
        self.assertEqual(first["result"]["room_id"], "game-a")
        self.assertEqual(first["receipt_ref"], "receipt-1")
        self.assertNotIn("provider_internal", json.dumps(first))
        self.assertNotIn("session_token", json.dumps(first))
        self.assertEqual(second["state"], "succeeded")
        self.service.room_server.start.assert_awaited_once()
        self.service._ensure_mobile_room_access.assert_not_awaited()

    async def test_game_arguments_keep_native_chess_and_turtle_contracts(self):
        await self.bridge.create(TOKEN, "request-chess", "xiangqi")
        await self.bridge.create(TOKEN, "request-turtle", "turtle_soup")
        self.assertEqual(json.loads(self.invocations[0].arguments_json), {"difficulty": "normal", "human_side": "red"})
        self.assertEqual(json.loads(self.invocations[1].arguments_json), {})
        self.service._ensure_mobile_room_access.assert_awaited()

    async def test_request_id_and_current_consent_are_required_before_creating(self):
        for request_id in ("", "new request with spaces", None):
            with self.subTest(request_id=request_id), self.assertRaises(TaskError) as raised:
                await self.bridge.create(TOKEN, request_id, "tictactoe")
            self.assertEqual(raised.exception.code, "mobile_request_id_required")
        self.allowed.remove("game.tictactoe.create")
        with self.assertRaises(TaskError) as raised:
            await self.bridge.create(TOKEN, "request-denied", "tictactoe")
        self.assertEqual(raised.exception.code, "mobile_game_not_authorized")
        self.assertEqual(self.dispatched, [])
        self.service._native_provider.issue_web_ticket.assert_not_called()

    async def test_before_dispatch_rechecks_current_authorization(self):
        self.before_dispatch = lambda: self.allowed.remove("game.tictactoe.create")
        with self.assertRaises(TaskError) as raised:
            await self.bridge.create(TOKEN, "request-preflight-revoked", "tictactoe")
        self.assertEqual(raised.exception.code, "capability_denied")
        self.assertEqual(self.dispatched, [])
        self.service._native_provider.issue_web_ticket.assert_not_called()

    async def test_context_change_during_room_access_does_not_issue_ticket(self):
        replacement = deepcopy(self.context)
        replacement.key = "context-new-persona"
        replacement.role_binding.role.subject_id = "role-b"
        self.service.room_server.start.side_effect = lambda: setattr(self.session.profile, "target", replacement)
        with self.assertRaises(TaskError) as raised:
            await self.bridge.create(TOKEN, "request-game-persona-changed", "tictactoe", via_mobile_gateway=True)
        self.assertEqual(raised.exception.code, "mobile_v2_context_changed")
        self.assertEqual(len(self.dispatched), 1)
        self.service._native_provider.issue_web_ticket.assert_not_called()

    async def test_revoked_consent_during_room_access_does_not_issue_ticket(self):
        self.service.room_server.start.side_effect = lambda: self.allowed.remove("game.tictactoe.create")
        with self.assertRaises(TaskError) as raised:
            await self.bridge.create(TOKEN, "request-game-revoked", "tictactoe", via_mobile_gateway=True)
        self.assertEqual(raised.exception.code, "capability_denied")
        self.service._native_provider.issue_web_ticket.assert_not_called()

    async def test_service_replacement_during_room_access_does_not_issue_ticket(self):
        original = self.service
        replacement = deepcopy(original)

        async def change_service():
            self.service = replacement
            return "https://games.example"

        original._ensure_mobile_room_access.side_effect = change_service
        with self.assertRaises(TaskError) as raised:
            await self.bridge.create(TOKEN, "request-game-provider-changed", "tictactoe")
        self.assertEqual(raised.exception.code, "mobile_v2_provider_changed")
        original._native_provider.issue_web_ticket.assert_not_called()
        replacement._native_provider.issue_web_ticket.assert_not_called()

    async def test_unknown_creation_result_retains_receipt_without_room_ticket(self):
        self.unknown_result = True
        result = await self.bridge.create(TOKEN, "request-game-unknown", "tictactoe", via_mobile_gateway=True)
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["operation_id"], "op-1")
        self.assertEqual(result["receipt_ref"], "receipt-1")
        self.assertNotIn("result", result)
        self.service.room_server.start.assert_not_awaited()
        self.service._native_provider.issue_web_ticket.assert_not_called()


class Gateway(MobileGatewayMixin):
    def __init__(self, api):
        self.api = api
        self._mobile_gateway_init()

    def v2_host_api(self):
        return self.api

    def native_extension(self, extension_id):
        raise AssertionError("status must not fall back to unscoped service APIs")

    def _mobile_reality_status(self):
        return {"available": True}

    def _mobile_location_snapshot(self, user_id):
        return {"user_id": user_id}

    _mobile_device_snapshot = _mobile_activity_snapshot = _mobile_telemetry_snapshot = _mobile_screen_status = _mobile_location_snapshot

    def _mobile_telemetry_enabled(self):
        return True

    _mobile_activity_enabled = _mobile_screen_upload_enabled = _mobile_telemetry_enabled


class MobileGatewayStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.game_status = {"matched": True, "available": True, "enabled": True,
                            "running": False, "ready": True, "games": ["tictactoe", "xiangqi"]}
        self.together_status = {"matched": True, "available": True, "ready": True, "running": False,
                                "capabilities": {"create": True, "invite": False, "join": True},
                                "modes": ["watch", "work"]}
        self.game_tokens = []
        self.together_tokens = []

        def game_status(token):
            self.game_tokens.append(token)
            return self.game_status

        def together_status(token, *, via_mobile_gateway=False):
            self.together_tokens.append((token, via_mobile_gateway))
            return self.together_status

        self.gateway = Gateway(SimpleNamespace(companion_v2_mobile_game_status=game_status,
            companion_v2_mobile_together_status=together_status))

    async def test_status_uses_session_token_and_only_authorized_modes_and_games(self):
        body = await self.gateway._mobile_status_response({"user_id": "12345"}, session_token=TOKEN)
        self.assertEqual(self.game_tokens, [TOKEN])
        self.assertEqual(self.together_tokens, [(TOKEN, True)])
        data = body["data"]
        self.assertEqual([game["game_type"] for game in data["games"]["games"]], ["native_v2:tictactoe", "native_v2:xiangqi"])
        self.assertTrue(data["capabilities"]["games"])
        self.assertTrue(data["capabilities"]["watch"])
        self.assertTrue(data["capabilities"]["work"])
        self.assertFalse(data["capabilities"]["call"])
        self.assertFalse(data["capabilities"]["novel"])
        self.assertFalse(data["capabilities"]["invite"])
        self.assertTrue(data["capabilities"]["join"])
        self.assertNotIn("session_token", json.dumps(body))

    async def test_unmatched_phone_cannot_fall_back_to_service_room_readiness(self):
        self.game_status = {"matched": False, "ready": True, "games": ["tictactoe"]}
        self.together_status = {"matched": False, "available": True, "ready": True,
                                "capabilities": {"create": True, "invite": True, "join": True},
                                "modes": ["call", "watch", "work", "novel"]}
        body = await self.gateway._mobile_status_response({"user_id": "99999"}, session_token=TOKEN)
        data = body["data"]
        self.assertEqual(data["games"]["games"], [])
        for capability in ("room", "call", "watch", "work", "novel", "invite", "join", "games"):
            with self.subTest(capability=capability):
                self.assertFalse(data["capabilities"][capability])

    async def test_missing_phone_token_has_no_room_or_game_capabilities(self):
        body = await self.gateway._mobile_status_response({"user_id": "12345"})
        self.assertEqual(self.game_tokens, [])
        self.assertEqual(self.together_tokens, [])
        self.assertEqual(body["data"]["games"]["games"], [])
        self.assertFalse(body["data"]["capabilities"]["room"])


if __name__ == "__main__":
    unittest.main()
