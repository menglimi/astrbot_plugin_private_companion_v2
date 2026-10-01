"""The V2 perception page edits only its selected private role's owners."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from tests import test_astrbot_staging_host as support

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.native_perception_api import PREFIX


class NativePerceptionAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-native-perception-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                           NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(
            self.native, support.host_config(), Path(temporary.name), native_types=types,
            now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler
                       for path, handler, methods, _ in self.native.registered_web_apis}

    async def call(self, *, body=None, username="admin", query=b"", route=PREFIX):
        method = "POST" if body is not None else "GET"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        request_route = route if method == "GET" else route + "/configure"
        native = Request({"type": "http", "method": method, "path": request_route,
                          "headers": [], "query_string": query}, receive=receive)
        with bind_request_context(PluginRequest(native, username=username)):
            return await self.routes[(request_route, method)]()

    @staticmethod
    def command(section, token, changes, key):
        return {"section": section, "command": {"operation_key": key,
                "edit_token": token, "changes": changes}}

    async def test_model_environment_news_and_stale_token(self):
        self.assertEqual((await self.call())["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        initial = await self.call()
        self.assertEqual(initial["status"], "ok", initial)
        data = initial["data"]
        self.assertTrue(data["model"]["settings"]["calendar_enabled"])
        self.assertTrue(data["model"]["settings"]["holiday_enabled"])
        self.assertTrue(data["model"]["settings"]["automatic_solar_terms_enabled"])
        self.assertFalse(data["environment"]["settings"]["planning_weather_enabled"])
        self.assertTrue(data["environment"]["sources"]["weather_ready"])
        self.assertFalse(data["news"]["source"]["ready"])
        self.assertEqual(data["contact"]["edit_token"], data["news"]["edit_token"])
        self.assertIn("quiet_start", data["contact"]["settings"])
        self.assertIn("allowed", data["contact"]["effective"])
        self.assertIn("chat", data["contact"]["purposes"])
        for field in ("web_exploration_enabled", "web_exploration_interests",
                      "web_exploration_min_interval_hours", "web_exploration_result_count",
                      "external_event_self_link_enabled"):
            self.assertIn(field, data["news"]["settings"])

        model = await self.call(body=self.command("model", data["model"]["edit_token"],
            {"guidance": "只说有来源的观察。", "platform_enabled": False}, "model-1"))
        self.assertEqual(model["status"], "ok", model)
        self.assertEqual(model["data"]["status"]["model"]["settings"]["guidance"], "只说有来源的观察。")
        self.assertFalse(model["data"]["status"]["model"]["settings"]["platform_enabled"])

        location = json.dumps({"name":"测试区域", "latitude":12.34, "longitude":56.78,
                               "alert_city":"测试城市", "alert_area":"测试区域"}, ensure_ascii=False)
        environment_token = model["data"]["status"]["environment"]["edit_token"]
        environment = await self.call(body=self.command("environment", environment_token,
            {"planning_weather_location":location, "planning_weather_enabled":True}, "environment-1"))
        self.assertEqual(environment["status"], "ok", environment)
        self.assertEqual(environment["data"]["status"]["environment"]["settings"]["planning_weather_location"], location)
        stale = await self.call(body=self.command("environment", environment_token,
            {"planning_timezone":"UTC"}, "environment-2"))
        self.assertEqual(stale["data"]["code"], "configuration_revision_conflict")

        (await self.controller.start()).unwrap()
        latest = (await self.call())["data"]
        news = await self.call(body=self.command("news", latest["news"]["edit_token"],
            {"news_share_enabled":True, "news.enabled":True,
             "news_check_interval_minutes":60}, "news-1"))
        self.assertEqual(news["status"], "ok", news)
        self.assertTrue(news["data"]["status"]["news"]["settings"]["news_share_enabled"])
        self.assertEqual(news["data"]["status"]["news"]["settings"]["news_check_interval_minutes"], 60)
        replay = await self.call(body=self.command("news", latest["news"]["edit_token"],
            {"news_share_enabled":True, "news.enabled":True,
             "news_check_interval_minutes":60}, "news-1"))
        self.assertEqual(replay["status"], "ok", replay)
        self.assertTrue(replay["data"]["result"]["replayed"])

    async def test_authentication_payload_and_owner_boundaries(self):
        (await self.controller.initialize_profile()).unwrap()
        data = (await self.call())["data"]
        body = self.command("model", data["model"]["edit_token"], {"calendar_enabled":False}, "identity-1")
        for username in (None, "", "api_key:synthetic"):
            self.assertEqual((await self.call(body=body, username=username))["data"]["code"],
                             "dashboard_identity_required")
        self.assertEqual((await self.call(query=b"target_id=another"))["data"]["code"],
                         "perception_request_invalid")
        forbidden = self.command("environment", data["environment"]["edit_token"],
                                 {"enabled":True}, "forbidden-1")
        self.assertEqual((await self.call(body=forbidden))["data"]["code"], "perception_request_invalid")
        self.assertTrue((await self.call())["data"]["model"]["settings"]["calendar_enabled"])
        denied_runtime = await self.call(route=PREFIX + "/runtime", username=None)
        self.assertEqual(denied_runtime["data"]["code"], "dashboard_identity_required")
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.call())["data"]["code"], "staging_host_terminated")

    async def test_runtime_snapshot_uses_enabled_weather_and_returns_explicit_empty_states(self):
        class WeatherPort:
            def __init__(self):
                self.locations = []

            async def fetch(self, location):
                self.locations.append(location)
                return NS(provider="fixture-weather", location=location.name, observed_at=support.NOW,
                          condition="晴", temperature_c=22.0, humidity_pct=45.0, wind_kph=4.0, alerts=())

        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.start()).unwrap()
        app = self.controller.session.application
        weather = WeatherPort()
        app.calendar_planning.weather_port = weather

        path = PREFIX + "/runtime"
        disabled = await self.call(route=path)
        self.assertEqual(disabled["data"]["weather"]["state"], "disabled")
        self.assertEqual(weather.locations, [])
        self.assertEqual(disabled["data"]["calendar"]["status"], "available")
        self.assertEqual(disabled["data"]["screen"]["state"], "empty")
        self.assertEqual(disabled["data"]["reality"]["reason"], "reality_provider_unavailable")
        self.assertEqual(disabled["data"]["camera"]["reason"], "reality_provider_unavailable")

        settings = (await self.call())["data"]["environment"]
        location = json.dumps({"name": "测试区域", "latitude": 12.34, "longitude": 56.78}, ensure_ascii=False)
        configured = await self.call(body=self.command("environment", settings["edit_token"], {
            "planning_weather_location": location, "planning_weather_enabled": True,
        }, "runtime-weather"))
        self.assertEqual(configured["status"], "ok", configured)
        runtime = await self.call(route=path)
        self.assertEqual(runtime["status"], "ok", runtime)
        self.assertEqual(runtime["data"]["weather"]["state"], "available")
        self.assertEqual(runtime["data"]["weather"]["temperature_c"], 22.0)
        self.assertEqual(runtime["data"]["calendar"]["status"], "available")
        self.assertEqual(weather.locations[0].name, "测试区域")
