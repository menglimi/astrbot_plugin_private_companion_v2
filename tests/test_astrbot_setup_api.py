"""Exercise the persistent first-run guide against synthetic AstrBot adapters."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_astrbot_staging_host import WebContext, host_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW
from astrbot_host.binding_store import PendingBinding, write_binding
from astrbot_host.controller import AstrBotStagingController
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot_host.setup_api import SetupWebAPI
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes


class AstrBotSetupFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-setup-")
        self.root = Path(self.temporary.name)
        self.native = WebContext()
        self.types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        self.config = host_config(staging={"profile_id": "setup-flow", "delivery_mode": "onebot_private"})
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        self.native.get_all_providers = lambda: [self.native.provider]
        self.native.provider.meta = lambda: NS(id="native-model", name="Fixture model")

    def make_single_controller(self):
        return AstrBotStagingController(self.native, self.config, self.root,
                                        native_types=self.types, now=lambda: NOW)

    def attach_config_writer(self):
        def save(candidate):
            self.config.clear()
            self.config.update(candidate)
            self.controller.refresh_settings()
        self.controller.save_plugin_config = save

    async def asyncTearDown(self):
        await self.controller.terminate()
        self.temporary.cleanup()

    async def call(self, name, body=None, *, username="administrator"):
        payload = json.dumps(body if body is not None else {}, ensure_ascii=False).encode("utf-8")
        request = NS(username=username, query={}, body=AsyncMock(return_value=payload))
        with patch("astrbot_host.setup_api.request", request):
            return await getattr(self.api, name)()

    async def bind_core_window(self, persona_id="original"):
        write_binding(self.controller.binding_root,
                      PendingBinding("qq-main", "100", "200", persona_id))
        result = await self.call("confirm_binding")
        self.assertEqual(result["status"], "ok", result)

    async def enter_model_step(self):
        self.attach_config_writer()
        mode = await self.call("mode", {"accounts": "single", "personas": "single"})
        self.assertEqual(mode["status"], "ok", mode)
        self.assertFalse(mode["data"]["mode_requires_reload"])
        await self.bind_core_window()
        self.assertIsNone(self.controller.runtime)
        status = await self.call("status")
        self.assertEqual(status["data"]["step"], "model")

    async def test_binding_precedes_model_and_does_not_initialize_the_runtime(self):
        initial = await self.call("status")
        self.assertEqual(initial["data"]["step"], "mode")
        await self.enter_model_step()
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_model_selection_persists_and_prepares_before_knowledge(self):
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "native-model"})

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["model"]["provider_id"], "native-model")
        self.assertIsNotNone(self.controller.runtime)
        self.assertFalse(self.controller.status()["accepting"])
        status = await self.call("status")
        self.assertEqual(status["data"]["step"], "knowledge")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_model_selection_rejects_unloaded_provider_without_saving(self):
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "missing-model"})

        self.assertEqual(result["data"]["code"], "host_provider_unavailable")
        self.assertEqual(self.config["model"]["provider_id"], "native-model")
        self.assertIsNone(self.controller.runtime)

    async def test_multi_mode_confirmation_seeds_the_first_private_target_and_persona(self):
        await self.controller.terminate()
        self.config["staging"]["enabled"] = False
        self.config["multi_host"] = {"enabled": True, "installation_id": "setup-shared"}
        self.controller = AstrBotMultiController(self.native, self.config, self.root,
                                                 native_types=self.types, now=lambda: NOW)
        self.api = SetupWebAPI(self.controller)
        self.native.persona_manager.get_persona_v3_by_id = lambda persona_id: (
            self.native.persona if persona_id == "original" else None)
        self.attach_config_writer()

        mode = await self.call("mode", {"accounts": "multiple", "personas": "multiple"})
        self.assertEqual(mode["status"], "ok", mode)
        self.assertFalse(mode["data"]["mode_requires_reload"])
        await self.bind_core_window()

        target, persona = self.config["multi_host"]["targets"][0], self.config["multi_host"]["personas"][0]
        self.assertEqual((target["platform_id"], target["account_id"], target["participant_id"]),
                         ("qq-main", "100", "200"))
        self.assertEqual((persona["bot_id"], persona["persona_id"]), (target["bot_id"], "original"))
        self.assertIsNone(self.controller.settings_error)
        self.assertTrue(self.controller.binding_state()["configured_target"])

    async def test_active_test_is_persisted_and_never_replayed(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")

        first = await self.call("proactive_test")
        again = await self.call("proactive_test")

        self.assertEqual(first["data"]["state"], "delivered")
        self.assertTrue(again["data"]["ready"])
        calls = self.native.platform.client._api._wsr_api.calls
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "send_private_msg")
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_completed_guide_survives_plugin_restart_without_reopening_setup_steps(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("proactive_test"))["data"]["state"], "delivered")

        await self.controller.terminate()
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        status = await self.call("status")

        self.assertEqual(status["data"]["step"], "complete")
        self.assertTrue(status["data"]["ready"])
        self.assertFalse(status["data"]["host"]["accepting"])

    async def test_reconnect_route_starts_only_a_completed_setup(self):
        denied = await self.call("reconnect_host")
        self.assertEqual(denied["data"]["code"], "setup_completion_required")

        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("proactive_test"))["data"]["state"], "delivered")

        connected = await self.call("reconnect_host")

        self.assertEqual(connected["status"], "ok", connected)
        self.assertTrue(connected["data"]["status"]["host"]["accepting"])


if __name__ == "__main__":
    unittest.main()
