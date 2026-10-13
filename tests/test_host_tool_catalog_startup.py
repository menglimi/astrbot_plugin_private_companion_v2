"""Cold-start saved host profiles with all seven modules and QQ Zone installed."""

import unittest
from unittest.mock import patch

# Import the fixture before the SDK to keep AstrBot's database in a temporary root.
from tests.multi_host_support import MultiFixture
from tests.test_qzone_extension import FakeTransport
from companion_v2.model_gateway.models import MAX_TOOL_CATALOG
from companion_v2.qzone.capability import tool_descriptors


class HostToolCatalogStartupTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def test_saved_profile_survives_repeated_cold_starts_with_the_complete_catalog(self):
        transport = FakeTransport()
        with patch("astrbot_host.multi_controller.build_qzone_transport", return_value=transport):
            initialized = await self.controller.initialize_profile()
            self.assertTrue(initialized.is_success, initialized.failure)
            saved_root = self.controller.runtime.data_root
            saved_manifest = self.controller.authority.require_manifest()
            native_actions = {item.descriptor.tool.action for item in self.controller.native_extensions.declarations()}
            qzone_actions = {item.tool.action for item in tool_descriptors()}
            expected_actions = native_actions | qzone_actions
            self.assertEqual(len(self.controller.native_extensions._bundled_extensions), 7)
            self.assertGreater(len(expected_actions), MAX_TOOL_CATALOG)
            self.assertEqual(set(self.controller.session.application.external.providers), expected_actions)
            await self.controller.terminate()

            for restart in range(2):
                with self.subTest(restart=restart):
                    restored = self.make_controller()
                    restored.register_routes()
                    loaded = await restored.load_existing()
                    self.assertTrue(loaded.is_success, loaded.failure)
                    self.assertEqual(loaded.unwrap(), {"loaded": True, "started": False})
                    self.assertEqual(restored.runtime.data_root, saved_root)
                    self.assertEqual(restored.authority.require_manifest(), saved_manifest)
                    self.assertEqual(set(restored.session.application.external.providers), expected_actions)
                    started = await restored.start()
                    self.assertTrue(started.is_success, started.failure)
                    self.assertEqual(restored.session.application.state, "running")
                    self.assertTrue(restored._accepting)
                    self.assertIsNone(restored.last_failure)
                    await restored.terminate()
                    self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual(transport.acquired, 0)
        self.assertEqual(transport.sent, [])


if __name__ == "__main__":
    unittest.main()
