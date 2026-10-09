"""TTS provider management and image config delegation use the real SDK with isolated data."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
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
                                  "api_key": "secret-value", "proxy": "http://proxy-secret", "model": "s2.1-pro"}]

    async def create_provider(self, config):
        self.providers_config.append(deepcopy(config))

    async def update_provider(self, provider_id, new_config):
        for index, item in enumerate(self.providers_config):
            if item.get("id") == provider_id:
                self.providers_config[index] = deepcopy(new_config)


class FakeImageExtensionAPI:
    def __init__(self):
        self.revision = "a" * 64
        self.configuration = {"enabled": False, "backend": "auto",
            "endpoints": [], "sd_webui": {"base_url": "", "api_key_set": False, "timeout_seconds": 300},
            "comfyui": {"base_url": "", "api_key_set": False, "timeout_seconds": 300}}
        self.saved = None

    def output_configuration(self):
        return {"revision": self.revision, "settings": deepcopy(self.configuration), "live": False,
                "limits": {"max_endpoints": 24}, "supported_backends": ["auto", "online_api", "comfyui", "sd_webui"],
                "supported_platforms": ["auto", "openai", "minimax"]}

    def save_output_configuration(self, revision, changes):
        if revision != self.revision:
            error = RuntimeError("configuration_conflict")
            error.code = "configuration_conflict"
            raise error
        self.configuration.update(deepcopy(changes))
        self.saved = deepcopy(changes)
        self.revision = "b" * 64
        return self.output_configuration()


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

    def install_text_provider_catalog(self):
        primary = self.native.provider
        primary.meta = lambda: NS(id="native-model", name="Primary model")
        secondary = support.FakeProvider()
        secondary.provider_config["id"] = "secondary-model"
        secondary.model_name = "secondary-fixture"
        secondary.meta = lambda: NS(id="secondary-model", name="Secondary model")
        providers = {"native-model": primary, "secondary-model": secondary}
        self.native.get_all_providers = lambda: list(providers.values())
        self.native.get_provider_by_id = lambda provider_id: providers.get(provider_id)
        return providers

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
        self.assertEqual(methods[PREFIX + "/balance"], ["GET"])

    async def test_business_prompt_section_roundtrip_uses_the_original_model_route(self):
        (await self.controller.initialize_profile()).unwrap()
        listed = await self.call(PREFIX)
        task = next(item for item in listed["data"]["tasks"] if item["kind"] == "proactive.compose")
        section = next(item for item in task["prompt_sections"] if item["key"] == "news_sharing")
        payload = {"kind": task["kind"], "section": "news_sharing", "operation_key": "news-template-route",
                   "edit_token": section["edit_token"], "changes": {"prompt": "自然分享新鲜事，保留具体感想。"}, "reset": []}
        saved = await self.call(PREFIX + "/configure", payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(saved["status"], "ok", saved)
        changed = next(item for item in saved["data"]["task"]["prompt_sections"] if item["key"] == "news_sharing")
        self.assertEqual(changed["prompt"], payload["changes"]["prompt"])
        self.assertEqual(changed["field"]["source"], "window")

    async def test_catalog_reads_loaded_astrbot_text_providers_without_a_registration_route(self):
        self.install_text_provider_catalog()
        listed = await self.call(PREFIX + "/catalog")
        self.assertEqual(listed["status"], "ok", listed)
        self.assertEqual({item["id"] for item in listed["data"]["providers"]},
                         {"native-model", "secondary-model"})
        self.assertNotIn(PREFIX + "/pool", self.routes)
        self.assertNotIn(PREFIX + "/pool/save", self.routes)

    async def test_balance_route_returns_only_the_normalized_observation(self):
        from companion_v2.proactive.balance_events import BalanceObservation
        import astrbot_host.model_api as model_api

        class Port:
            provider = "newapi"
            provider_label = "NewAPI"
            currency_label = "USD"

            async def fetch(self):
                return BalanceObservation(Decimal("8.5"), None, datetime(2026, 10, 2, tzinfo=timezone.utc))

        (await self.controller.initialize_profile()).unwrap()
        with patch.object(model_api, "configured_balance_port", return_value=Port()):
            result = await self.call(PREFIX + "/balance")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], {
            "configured": True, "available": True, "provider": "newapi", "provider_label": "NewAPI",
            "currency_label": "USD", "observed_at": "2026-10-02T00:00:00+00:00",
            "amount": "8.50", "state": "available",
        })
        self.assertNotIn("api_key", str(result).lower())

    async def test_tts_provider_roundtrip_masks_secrets(self):
        (await self.controller.initialize_profile()).unwrap()
        prefix = "C:/Users/99505/.astrbot/data/plugins/astrbot_plugin_private_companion_v2/astrbot_host.model_api"
        import astrbot_host.model_api as model_api
        listed = await self.call(model_api.PREFIX + "/tts/providers")
        item = listed["data"]["items"][0]
        self.assertEqual(item["id"], "tts-a")
        secret = next(field for field in item["fields"] if field["key"] == "api_key")
        self.assertTrue(secret["secret"] and secret["set"] and secret["value"] == "")
        proxy = next(field for field in item["fields"] if field["key"] == "proxy")
        self.assertTrue(proxy["secret"] and proxy["set"] and proxy["value"] == "")
        model = next(field for field in item["fields"] if field["key"] == "model")
        self.assertEqual(model["value"], "s2.1-pro")
        self.assertEqual([option["value"] for option in model["options"]],
                         ["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"])
        self.assertEqual(next(field for field in item["fields"] if field["key"] == "proxy")["label"], "代理地址")
        self.assertGreaterEqual(len(listed["data"]["templates"]), 13)
        self.assertNotIn("proxy-secret", json.dumps(listed))

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

        cloned_with_draft = await self.call(model_api.PREFIX + "/tts/providers/clone", payload=(
            b'{"provider_id":"tts-b","language":"en","config":{"enable":true,"values":{"api_key":"","model":"s2-pro"}}}'))
        draft_clone_id = cloned_with_draft["data"]["created_id"]
        draft_clone = next(entry for entry in self.manager.providers_config if entry["id"] == draft_clone_id)
        self.assertTrue(draft_clone["enable"])
        self.assertEqual(draft_clone["model"], "s2-pro")
        self.assertEqual(draft_clone["api_key"], "new-key")

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

    async def test_voice_test_returns_audio_for_inline_preview(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api

        class TtsProvider:
            provider_config = {"api_key": "fixture-tts-secret"}

            def meta(self):
                return NS(id="tts-live", model="gpt-4o-mini-tts")

            async def get_audio(self, text):
                self.text = text
                return "preview.wav"

        provider = TtsProvider()
        self.native.get_all_tts_providers = lambda: [provider]
        # The generic context lookup is not the authoritative TTS lookup on all
        # AstrBot releases; the route must resolve the live TTS collection.
        self.native.get_provider_by_id = lambda provider_id: self.native.provider if provider_id == "native-model" else None
        catalog = await self.call(model_api.PREFIX + "/voice")
        self.assertEqual(catalog["status"], "ok", catalog)
        self.assertEqual(catalog["data"]["providers"], [{"id": "tts-live", "model": "gpt-4o-mini-tts"}])
        self.assertNotIn("fixture-tts-secret", json.dumps(catalog))
        with patch.object(model_api, "_read_audio", return_value=b"RIFF0000WAVE"):
            result = await self.call(model_api.PREFIX + "/voice/test", payload=(
                b'{"provider_id":"tts-live","language":"ja"}'))

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["status"], "ok")
        self.assertEqual(result["data"]["audio_base64"], "UklGRjAwMDBXQVZF")
        self.assertEqual(result["data"]["audio_mime_type"], "audio/wav")
        self.assertEqual(provider.text, "こんにちは。")

    async def test_voice_test_returns_sanitized_failure_details_and_suggestion(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api

        class TtsProvider:
            provider_config = {"api_key": "fixture-secret", "proxy": "http://proxy-secret"}

            def meta(self):
                return NS(id="tts-error", model="fishaudio")

            async def get_audio(self, text):
                raise RuntimeError("Fish Audio API request failed: status 400 api_key=fixture-secret")

        provider = TtsProvider()
        self.native.get_all_tts_providers = lambda: [provider]
        self.native.get_provider_by_id = lambda provider_id: self.native.provider if provider_id == "native-model" else None
        result = await self.call(model_api.PREFIX + "/voice/test", payload=(
            b'{"provider_id":"tts-error","language":"ja"}'))

        self.assertEqual(result["status"], "ok", result)
        data = result["data"]
        self.assertEqual(data["status"], "unknown")
        self.assertEqual(data["code"], "model_voice_probe_failed")
        self.assertEqual(data["stage"], "synthesis")
        self.assertEqual(data["exception_type"], "RuntimeError")
        self.assertIn("status 400", data["error"])
        self.assertNotIn("fixture-secret", data["error"])
        self.assertNotIn("proxy-secret", data["error"])
        self.assertTrue(data["suggestion"])
        self.assertRegex(data["request_id"], r"^[0-9a-f]{12}$")

    async def test_voice_test_reports_audio_read_failure_stage(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api

        class TtsProvider:
            def meta(self):
                return NS(id="tts-read-error", model="fishaudio")

            async def get_audio(self, text):
                return "preview.wav"

        provider = TtsProvider()
        self.native.get_all_tts_providers = lambda: [provider]
        self.native.get_provider_by_id = lambda provider_id: self.native.provider if provider_id == "native-model" else None
        with patch.object(model_api, "_read_audio", side_effect=OSError("permission denied")):
            result = await self.call(model_api.PREFIX + "/voice/test", payload=(
                b'{"provider_id":"tts-read-error","language":"ja"}'))

        data = result["data"]
        self.assertEqual(data["status"], "unknown")
        self.assertEqual(data["code"], "model_voice_audio_read_failed")
        self.assertEqual(data["stage"], "audio_read")
        self.assertIn("permission denied", data["error"])

    async def test_tts_provider_connection_test_reports_loaded_provider_result(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api

        class TtsProvider:
            async def test(self):
                return None

        self.manager.inst_map = {"tts-a": TtsProvider()}
        result = await self.call(model_api.PREFIX + "/tts/providers/test", payload=b'{"provider_id":"tts-a"}')
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["status"], "ok")
        self.assertEqual(result["data"]["steps"][-1]["status"], "ok")

        self.manager.inst_map = {}
        unloaded = await self.call(model_api.PREFIX + "/tts/providers/test", payload=b'{"provider_id":"tts-a"}')
        self.assertEqual(unloaded["data"]["code"], "tts_provider_unloaded")

    async def test_image_output_reads_the_native_configuration_contract(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api
        fake = FakeImageExtensionAPI()
        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: fake):
            listed = await self.call(model_api.PREFIX + "/image/output")
            self.assertEqual(listed["data"]["revision"], "a" * 64)
            self.assertEqual(listed["data"]["settings"]["backend"], "auto")
            self.assertTrue(listed["data"]["host_registered"])

        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: None):
            missing = await self.call(model_api.PREFIX + "/image/output")
        self.assertEqual(missing["data"]["code"], "model_image_output_unavailable")

    async def test_image_output_save_roundtrip_and_conflict(self):
        (await self.controller.initialize_profile()).unwrap()
        import astrbot_host.model_api as model_api
        fake = FakeImageExtensionAPI()
        with patch.object(model_api.ModelWebAPI, "_image_extension_api", lambda self: fake):
            payload = json.dumps({"revision": "a" * 64, "changes": {
                "enabled": True, "backend": "online_api", "endpoints": [{"id": "primary",
                    "name": "Primary", "enabled": True, "platform": "openai",
                    "base_url": "https://api.example.test/v1", "api_key": "image-key",
                    "model": "gpt-image-1", "width": 1024, "height": 1024,
                    "timeout_seconds": 60}]}}).encode("utf-8")
            saved = await self.call(model_api.PREFIX + "/image/output/save", payload=payload)
            self.assertEqual(saved["data"]["revision"], "b" * 64)
            self.assertEqual(fake.saved["backend"], "online_api")
            self.assertEqual(fake.saved["endpoints"][0]["model"], "gpt-image-1")

            conflict_payload = json.dumps({"revision": "a" * 64, "changes": {"enabled": False}}).encode("utf-8")
            conflict = await self.call(model_api.PREFIX + "/image/output/save", payload=conflict_payload)
            self.assertEqual(conflict["data"]["code"], "model_image_output_conflict")
