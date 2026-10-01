"""TTS provider management and image config delegation use the real SDK with isolated data."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as support
from astrbot_host.model_api import PREFIX
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request


class FakeProviderManager:
    def __init__(self):
        self.providers_config = [{"id": "tts-a", "type": "fishaudio_tts_api", "provider": "fishaudio_tts_api",
                                  "provider_type": "text_to_speech", "enable": True,
                                  "api_key": "secret-value", "model": "s2.1-pro"}]

    async def create_provider(self, config):
        self.providers_config.append(deepcopy(config))

    async def update_provider(self, provider_id, new_config):
        for index, item in enumerate(self.providers_config):
            if item.get("id") == provider_id:
                self.providers_config[index] = deepcopy(new_config)


class FakeImageExtensionAPI:
    def __init__(self):
        self.revision = "rev-12345678"
        self.sections = {"preparation": {"routes": [{"route_id": "r1", "profile": "p", "operation": "generate"}]},
                         "sd_webui": {"base_url": "", "api_key_set": False, "timeout_seconds": 300},
                         "comfyui": {"base_url": "http://127.0.0.1:8188", "api_key_set": True, "timeout_seconds": 300}}
        self.saved = None

    def native_configuration(self):
        return {"status": "ok", "revision": self.revision, "sections": deepcopy(self.sections)}

    def save_native_configuration(self, revision, changes):
        if revision != self.revision:
            raise RuntimeError("configuration_conflict")
        for name, values in changes.items():
            self.sections[name].update(values)
        self.saved = deepcopy(changes)
        self.revision = "rev-" + ("next" * 2) + "78"
        return {"status": "ok", "revision": self.revision, "sections": deepcopy(self.sections)}


async def body(payload):
    return payload


class ProviderRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-provider-api-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider, NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(), Path(temporary.name),
                                                           native_types=types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()
        self.routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        self.manager = FakeProviderManager()
        self.native.provider_manager = self.manager
        self.native.get_all_tts_providers = lambda: []

    async def call(self, route, *, payload=None, username="admin"):
        prefix = "C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host.model_api"
        import astrbot_host.model_api as model_api
        request = Request({"type": "http", "method": "POST" if payload is not None else "GET",
                           "path": route, "headers": [], "query_string": b""})
        fake_request = NS(username=username, query={}, body=(lambda: body(payload)) if payload is not None else None)
        with patch.object(model_api, "request", fake_request):
            with bind_request_context(PluginRequest(request, username=username)):
                return await self.routes[route]()

    async def test_maintenance_diagnostics_route_is_registered_as_read_only(self):
        methods = {path: methods for path, _, methods, _ in self.native.registered_web_apis}
        self.assertEqual(methods[PREFIX + "/maintenance"], ["GET"])

    async def test_tts_provider_roundtrip_masks_secrets(self):
        (await self.controller.initialize_profile()).unwrap()
        prefix = "C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host.model_api"
        import astrbot_host.model_api as model_api
        listed = await self.call(model_api.PREFIX + "/tts/providers")
        item = listed["data"]["items"][0]
        self.assertEqual(item["id"], "tts-a")
        secret = next(field for field in item["fields"] if field["key"] == "api_key")
        self.assertTrue(secret["secret"] and secret["set"] and secret["value"] == "")
        model = next(field for field in item["fields"] if field["key"] == "model")
        self.assertEqual(model["value"], "s2.1-pro")

        created = await self.call(model_api.PREFIX + "/tts/providers/create",
                                  payload=b'{"type": "fishaudio_tts_api", "id": "tts-b"}')
        self.assertIn("tts-b", [entry["id"] for entry in created["data"]["items"]])
        new_item = next(entry for entry in created["data"]["items"] if entry["id"] == "tts-b")
        self.assertFalse(new_item["enable"])

        saved = await self.call(model_api.PREFIX + "/tts/providers/update", payload=(
            b'{"provider_id": "tts-b", "values": {"api_key": "new-key", "model": "s2.1-pro-free", "enable": true}}'))
        updated = next(entry for entry in saved["data"]["items"] if entry["id"] == "tts-b")
        self.assertTrue(updated["enable"])
        stored = next(entry for entry in self.manager.providers_config if entry["id"] == "tts-b")
        self.assertEqual(stored["api_key"], "new-key")
        self.assertEqual(stored["model"], "s2.1-pro-free")

        blank = await self.call(model_api.PREFIX + "/tts/providers/update", payload=(
            b'{"provider_id": "tts-b", "values": {"api_key": ""}}'))
        self.assertEqual(blank["status"], "ok")
        stored = next(entry for entry in self.manager.providers_config if entry["id"] == "tts-b")
        self.assertEqual(stored["api_key"], "new-key", "blank secret must keep the stored value")

        cloned = await self.call(model_api.PREFIX + "/tts/providers/clone", payload=(
            b'{"provider_id": "tts-b", "language": "ja"}'))
        clone_id = cloned["data"]["created_id"]
        self.assertTrue(clone_id.startswith("tts-b-ja"))
        clone = next(entry for entry in self.manager.providers_config if entry["id"] == clone_id)
        self.assertFalse(clone["enable"])
        self.assertEqual(clone["api_key"], "new-key")

        duplicate = await self.call(model_api.PREFIX + "/tts/providers/create",
                                    payload=b'{"type": "fishaudio_tts_api", "id": "tts-b"}')
        self.assertEqual(duplicate["data"]["code"], "tts_provider_exists")
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_image_config_delegates_to_extension_contract(self):
        (await self.controller.initialize_profile()).unwrap()
        prefix = "C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host.model_api"
        import astrbot_host.model_api as model_api
        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: NS(
                native_configuration=lambda: {"status": "ok", "revision": "rev-12345678", "sections": {}})):
            listed = await self.call(model_api.PREFIX + "/image/config")
            self.assertEqual(listed["data"]["revision"], "rev-12345678")

        class Busy:
            def native_configuration(self):
                return {"status": "ok", "revision": "rev-12345678", "sections": {}}

            def save_native_configuration(self, revision, changes):
                raise RuntimeError("configuration_busy")

        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: Busy()):
            busy = await self.call(model_api.PREFIX + "/image/config/save", payload=(
                b'{"revision": "rev-12345678", "changes": {"preparation": {"daily_limit": 5}}}'))
            self.assertEqual(busy["data"]["code"], "model_image_config_busy")

        missing = await self.call(model_api.PREFIX + "/image/config")
        self.assertEqual(missing["data"]["code"], "model_image_config_unavailable")

    async def test_image_config_save_roundtrip(self):
        (await self.controller.initialize_profile()).unwrap()
        prefix = "C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host.model_api"
        import astrbot_host.model_api as model_api
        fake = FakeImageExtensionAPI()
        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: fake):
            saved = await self.call(model_api.PREFIX + "/image/config/save", payload=(
                b'{"revision": "rev-12345678", "changes": {"sd_webui": {"base_url": "http://127.0.0.1:7860", "api_key": "k"}}}'))
            self.assertIn("rev-", saved["data"]["revision"])
            self.assertEqual(fake.saved["sd_webui"]["base_url"], "http://127.0.0.1:7860")

            conflict = await self.call(model_api.PREFIX + "/image/config/save", payload=(
                b'{"revision": "rev-stale9999", "changes": {"sd_webui": {"base_url": "x"}}}'))
            self.assertEqual(conflict["data"]["code"], "model_image_config_conflict")

    async def test_route_guidance_document_is_large_enough_for_one_save(self):
        """路线说明是可长文本：一次保存要装得下整份路线数组。

        扩展给的单键上限是 4000 字（image_config_limits.MAX_GUIDANCE_CHARS），
        而保存提交的是整份路线数组，所以请求体远大于其它配置。
        这里在旧上限（64 KB）之上发一次——闸门若比扩展允许的内容更早失败，
        用户会看到一句读不懂的 "model request is too large"。"""
        import json

        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api
        fake = FakeImageExtensionAPI()
        routes = [{"route_id": "route-%d" % index, "operation": "edit", "backend": "comfyui",
                   "guidance": {"summary": "说" * 4000, "test_notes": "记" * 4000}}
                  for index in range(8)]
        payload = json.dumps({"revision": "rev-12345678", "changes": {"preparation": {"routes": routes}}},
                             ensure_ascii=False).encode("utf-8")
        self.assertGreater(len(payload), 65536, "这个用例必须在旧上限之上，否则它测不到闸门本身")
        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: fake):
            saved = await self.call(model_api.PREFIX + "/image/config/save", payload=payload)
        self.assertIn("rev-", saved["data"]["revision"])
        self.assertEqual(len(fake.saved["preparation"]["routes"]), 8)
