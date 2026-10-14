"""Scoped game permission reaches the actual AstrBot core tool adapter."""

import json
from types import SimpleNamespace as NS
import unittest

from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core.agent.message import Message, ToolCall
from astrbot.core.provider.entities import ProviderRequest
from starlette.requests import Request

from astrbot_host.core_reply import prepare_core_reply_event
from astrbot_host.core_reply_tools import inject_core_reply_tools, native_tool_name
from companion_v2.games.native.access import GROUPS
from companion_v2.games.native.provider import GOMOKU_READ
from tests.multi_host_support import MultiFixture


class GameAccessTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def api(self, *, target="first", body=None, query=b""):
        inventory = self.controller.web_api.target_inventory()
        selected = next(item for item in inventory if item["target_id"] == target)
        path = selected["roles"][0]["game_access_api"]
        method = "GET" if body is None else "POST"
        if body is not None:
            path += "/configure"

        async def receive():
            return {"type": "http.request", "body": json.dumps(body).encode("utf-8"), "more_body": False}

        req = Request({"type":"http", "method":method, "path":path,
                       "headers":[], "query_string":query}, receive=receive)
        handler = next(handler for route, handler, methods, _ in self.native.registered_web_apis
                       if route == path and method in methods)
        with bind_request_context(PluginRequest(req, username="admin")):
            return await handler()

    @staticmethod
    def command(status, enabled, key):
        return {"game_type":"gomoku", "enabled":enabled,
                "edit_token":status["edit_token"], "operation_key":key}

    async def test_permission_game_room_core_execution_revoke_and_replay(self):
        self.controller.register_routes()
        app = await self.start_host()
        initial = (await self.api())["data"]
        self.assertFalse(next(item for item in initial["games"] if item["game_type"] == "gomoku")["consented"])
        enable = self.command(initial, True, "enable-gomoku")
        result = await self.api(body=enable)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["data"]["status"]["role_enabled"])
        other = (await self.api(target="second"))["data"]
        self.assertFalse(any(item["consented"] for item in other["games"]))
        grants = app.runtime.read_all("SELECT capability_id FROM capability_authorizations WHERE extension_id='game'", ())
        self.assertEqual({row["capability_id"] for row in grants}, GROUPS["gomoku"])
        await self.controller.native_extensions._lease("game").start()
        service = self.controller.native_extensions.service("game")
        service.server_enabled = True

        async def local_entry():
            return "http://127.0.0.1:6331"

        service._ensure_mobile_room_access = local_entry
        event = self.event(text="星缘黑先吧", identifier="black-first")
        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        await prepared["native_source_future"]

        async def authorize(value):
            return await self.controller.authorize_core_reply(event, value)

        prepare_core_reply_event(event, prepared, authorize=authorize)
        request = ProviderRequest(system_prompt=self.native.persona["prompt"])
        inject_core_reply_tools(event, request, application=app)
        tool = request.func_tool.get_tool(native_tool_name("game.gomoku.create"))
        self.assertIsNotNone(tool)
        arguments = {"difficulty":"normal", "human_side":"white"}
        call = ToolCall(id="real-game-create", function=ToolCall.FunctionBody(
            name=tool.name, arguments=json.dumps(arguments)))
        wrapper = NS(context=NS(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        created = json.loads(await tool.call(wrapper, **arguments))
        self.assertEqual(created["state"], "succeeded", created)
        payload = json.loads(created["payload"])["native"]["result"]
        self.assertEqual(payload["game"]["state"]["human_color"], 2)
        ticket = payload["room_url"].rsplit("/", 1)[1]
        self.assertEqual((await service._native_provider.web_state(ticket))["game"]["moves"], [[7, 7, 1]])
        moved = await service._native_provider.web_action(ticket, {"action":"move", "row":7, "column":8})
        self.assertEqual(moved["game"]["moves"][1], [7, 8, 2])
        read_tool = request.func_tool.get_tool(native_tool_name(GOMOKU_READ))
        read_call = ToolCall(id="read-same-game", function=ToolCall.FunctionBody(name=read_tool.name, arguments="{}"))
        read_wrapper = NS(context=NS(event=event), messages=[Message(role="assistant", tool_calls=[read_call])])
        read = json.loads(await read_tool.call(read_wrapper))
        self.assertEqual(read["state"], "succeeded", read)
        same_game = json.loads(read["payload"])["native"]["result"]["game"]
        self.assertEqual(same_game["game_id"], payload["game"]["game_id"])
        self.assertEqual(same_game["moves"], moved["game"]["moves"])
        latest = (await self.api())["data"]
        revoked = await self.api(body=self.command(latest, False, "revoke-gomoku"))
        self.assertFalse(next(item for item in revoked["data"]["status"]["games"]
                              if item["game_type"] == "gomoku")["invokable"])
        replayed = await self.api(body=enable)
        self.assertTrue(replayed["data"]["replayed"])
        self.assertFalse(next(item for item in replayed["data"]["status"]["games"]
                              if item["game_type"] == "gomoku")["consented"])
        stale = await self.api(body=self.command(latest, True, "stale-gomoku"))
        self.assertEqual(stale["data"]["code"], "game_access_changed")
        denied = await self.api(query=b"target_id=second")
        self.assertEqual(denied["data"]["code"], "game_access_request_invalid")
