"""Perception configuration uses Dashboard authority and provider-owned writes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from tests import test_astrbot_staging_host as support

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.perception_api import PREFIX


class ScreenProvider:
    def __init__(self):
        self.values = {"enabled": False, "remote_auth_token": ""}
        self.updates = []

    def companion_v2_perception_settings(self):
        return {"groups": [{"id": "runtime", "title": "运行", "fields": ["enabled"]}],
                "fields": {"enabled": {"type": "bool"}}, "values": dict(self.values)}

    def companion_v2_update_perception_settings(self, updates):
        self.updates.append(dict(updates))
        self.values.update(updates)
        return self.companion_v2_perception_settings()


class RealityProvider:
    def __init__(self):
        self.updates = []

    def companion_v2_perception_settings(self):
        return {"camera": {"camera_enabled": False}, "mobile": {"enabled": False},
                "secrets": {"pairing_token_configured": True}}

    async def companion_v2_update_perception_settings(self, section, updates):
        self.updates.append((section, dict(updates)))
        return self.companion_v2_perception_settings()


class PerceptionAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-perception-api-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                           NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(
            self.native, support.host_config(), Path(temporary.name), native_types=types,
            now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.screen = ScreenProvider()
        self.reality = RealityProvider()
        self.stars = [NS(root_dir_name=name, activated=True, star_cls=NS(extension_api=api))
                      for name, api in (("astrbot_plugin_screen_companion", self.screen),
                                        ("astrbot_plugin_reality_companion", self.reality))]
        self.native.get_all_stars = lambda: self.stars
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler for path, handler, methods, _ in self.native.registered_web_apis}

    async def call(self, *, body=None, username="admin"):
        method = "POST" if body is not None else "GET"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        native = Request({"type": "http", "method": method, "path": PREFIX,
                          "headers": [], "query_string": b""}, receive=receive)
        with bind_request_context(PluginRequest(native, username=username)):
            return await self.routes[(PREFIX, method)]()

    async def test_read_and_update_dispatch_only_to_requested_owner(self):
        self.assertEqual((await self.call())["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        data = (await self.call())["data"]["providers"]
        self.assertTrue(data["screen"]["available"])
        self.assertTrue(data["reality"]["settings"]["secrets"]["pairing_token_configured"])

        screen = await self.call(body={"provider": "screen", "section": "settings",
                                       "updates": {"enabled": True}})
        self.assertEqual(screen["status"], "ok", screen)
        self.assertEqual(self.screen.updates, [{"enabled": True}])
        reality = await self.call(body={"provider": "reality", "section": "camera",
                                        "updates": {"camera_enabled": True}})
        self.assertEqual(reality["status"], "ok", reality)
        self.assertEqual(self.reality.updates, [("camera", {"camera_enabled": True})])

        bad = await self.call(body={"provider": "reality", "section": "home", "updates": {"enabled": True}})
        self.assertEqual(bad["data"]["code"], "perception_request_invalid")
        self.assertEqual(len(self.reality.updates), 1)

    async def test_missing_owner_and_dashboard_identity_block_writes(self):
        (await self.controller.initialize_profile()).unwrap()
        body = {"provider": "screen", "section": "settings", "updates": {"enabled": True}}
        for username in (None, "", "api_key:synthetic"):
            self.assertEqual((await self.call(body=body, username=username))["data"]["code"],
                             "dashboard_identity_required")
        self.assertEqual(self.screen.updates, [])
        self.stars = self.stars[1:]
        missing = await self.call()
        self.assertFalse(missing["data"]["providers"]["screen"]["available"])
        self.assertEqual((await self.call(body=body))["data"]["code"], "perception_provider_unavailable")

    async def test_shutdown_unregisters_routes_and_retained_handler_rejects(self):
        (await self.controller.initialize_profile()).unwrap()
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.call())["data"]["code"], "staging_host_terminated")
