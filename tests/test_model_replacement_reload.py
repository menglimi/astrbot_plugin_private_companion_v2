"""An existing V2 staging profile can adopt newly configured model routes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from astrbot_host.controller import AstrBotStagingController
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_astrbot_staging_host import WebContext, host_config
from tests.test_management_access import NOW


class NativeSingleRoutingReloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_profile_accepts_new_fallback_and_rules_on_reload(self):
        temporary = TemporaryDirectory(prefix="companion-v2-routing-reload-")
        self.addCleanup(temporary.cleanup)
        root, native = Path(temporary.name), WebContext()
        types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        original = AstrBotStagingController(native, host_config(), root, native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(original.terminate)
        self.assertTrue((await original.initialize_profile()).is_success)
        self.assertTrue((await original.start()).is_success)
        await original.terminate()

        backup = FakeProvider()
        backup.provider_config["id"] = "native-backup"
        native.get_all_providers = lambda: [native.provider, backup]
        native.get_provider_by_id = lambda provider_id: {
            "native-model": native.provider, "native-backup": backup}.get(provider_id)
        config = host_config(model={"additional_providers": [{"provider_id": "native-backup",
            "max_output_tokens": 100}], "fallback_provider_id": "native-backup",
            "replacement_rules": '[{"provider_id":"native-backup","keywords":["private"]}]'})
        routed = AstrBotStagingController(native, config, root, native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(routed.terminate)
        self.assertTrue((await routed.probe()).is_success)
        self.assertTrue((await routed.initialize_profile()).is_success)
        started = await routed.start()
        self.assertTrue(started.is_success, started.failure)
        self.assertEqual([provider.provider_id for provider in routed.session.models],
                         ["native-model", "native-backup"])
        self.assertEqual(routed.session.model_profile.default_fallback, "native-backup")
