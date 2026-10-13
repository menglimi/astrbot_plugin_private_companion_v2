"""Native registration is read-only on load and refreshed on session restart."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

# The SDK fixture sets a temporary ASTRBOT_ROOT before importing the host.
from tests import test_astrbot_staging_host as support
from tests.multi_host_support import MultiFixture
from tests.staging_bootstrap_support import database_contents
from tests.test_management_access import NOW
from tests.test_native_extensions_registry import Port, Star
from companion_v2.capabilities.repositories import CapabilityRepository


def screen_declaration(declarations):
    return next(item for item in declarations
                if item.descriptor.tool.action == "screen.capture")


class NativeSingleSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="native-single-session-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        self.star = Star(Port())
        self.native.get_all_stars = lambda: (self.star,)
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                           support.NS, support.NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(),
            Path(temporary.name), native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(self.controller.terminate)

    async def test_single_load_is_read_only_start_registers_only_stop_rebuilds_registry(self):
        c = self.controller
        (await c.initialize_profile()).unwrap()
        repository = CapabilityRepository(c.runtime)
        self.assertEqual(repository.descriptors(extension_id="image"), ())
        before = database_contents(c.runtime)
        (await c.load_existing()).unwrap()
        self.assertEqual(database_contents(c.runtime), before)
        old = c.native_extensions
        declaration = screen_declaration(old.declarations())
        image = next(item for item in old.declarations()
                     if item.descriptor.package.extension_id == "image")
        self.assertIsNotNone(old.role_guard)
        (await c.start()).unwrap()
        self.assertEqual(repository.descriptors(extension_id="image"), (image.descriptor.package,))
        self.assertFalse(repository.installation(extension_id="image").is_success)
        (await c.stop()).unwrap()
        self.assertIsNone(old.current_declaration(declaration.host_tool_id))
        self.star = Star(Port())
        (await c.start()).unwrap()
        self.assertIsNot(c.native_extensions, old)
        refreshed = c.native_extensions.current_declaration(declaration.host_tool_id)
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.descriptor.package, declaration.descriptor.package)

    async def test_no_optional_provider_starts_with_all_seven_bundled_providers(self):
        self.native.get_all_stars = lambda: ()
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.start()).unwrap()
        declarations = self.controller.native_extensions.declarations()
        self.assertEqual({item.descriptor.package.extension_id for item in declarations},
                         {"content", "image", "companion.screen.native", "reality", "together", "game", "live"})
        self.assertTrue(all(CapabilityRepository(self.controller.runtime).installation(
            extension_id=extension_id).failure is not None for extension_id in
            ("content", "image", "companion.screen.native", "reality", "together", "game", "live")))
        self.assertIsNotNone(self.controller.session.application.external)

    async def test_optional_provider_cannot_replace_a_managed_image_provider(self):
        c = self.controller
        (await c.initialize_profile()).unwrap()
        (await c.start()).unwrap()
        original = {item.host_tool_id: item for item in c.native_extensions.declarations()}
        declaration = screen_declaration(original.values())
        repository = CapabilityRepository(c.runtime)
        retained = repository.descriptors(extension_id="image")
        (await c.stop()).unwrap()
        changed = Port()
        changed.document["package"]["artifact_hash"] = "changed-content-same-version"
        self.star = Star(changed)
        started = (await c.start()).unwrap()
        self.assertTrue(started["started"])
        self.assertTrue(c.status()["accepting"])
        refreshed = {item.host_tool_id: item for item in c.native_extensions.declarations()}
        self.assertEqual(set(refreshed), set(original))
        current = c.native_extensions.current_declaration(declaration.host_tool_id)
        self.assertIsNotNone(current)
        self.assertEqual(current.descriptor.package, declaration.descriptor.package)
        self.assertNotIn((self.star.root_dir_name, "capability_descriptor_conflict"),
                         c.native_extensions.issues)
        self.assertEqual(repository.descriptors(extension_id="image"), retained)
        self.assertFalse(repository.installation(extension_id="image").is_success)
        self.assertEqual(changed.before, 0)


class NativeMultiSessionTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def test_shared_host_uses_v2_window_persona_binding_for_private_and_group_bridges(self):
        calls = []

        async def lookup(umo):
            calls.append(umo)
            return self.window_personas.get(umo)

        self.types = replace(self.types, session_persona_override_lookup=lookup)
        self.controller = self.make_controller()
        await self.start_host()

        self.assertEqual(set(calls), {"qq-main:FriendMessage:200", "qq-second:FriendMessage:200"})
        self.assertIs(self.controller.session.bridge.session_persona_override_lookup, lookup)
        self.assertIs(self.controller.session.bridge.groups.session_persona_override_lookup, lookup)

    async def test_optional_provider_cannot_replace_a_managed_image_provider_in_shared_host(self):
        stars = [Star(Port())]
        self.native.get_all_stars = lambda: stars
        c = self.controller
        (await c.initialize_profile()).unwrap()
        (await c.start()).unwrap()
        original = {item.host_tool_id: item for item in c.native_extensions.declarations()}
        declaration = screen_declaration(original.values())
        retained = CapabilityRepository(c.runtime).descriptors(extension_id="image")
        (await c.stop()).unwrap()
        changed = Port()
        changed.document["package"]["artifact_hash"] = "changed-content-same-version"
        stars[:] = [Star(changed)]
        (await c.start()).unwrap()
        self.assertEqual(c.session.application.state, "running")
        refreshed = {item.host_tool_id: item for item in c.native_extensions.declarations()}
        self.assertEqual(set(refreshed), set(original))
        self.assertIsNotNone(c.native_extensions.current_declaration(declaration.host_tool_id))
        self.assertEqual(CapabilityRepository(c.runtime).descriptors(extension_id="image"), retained)
        self.assertEqual(changed.before, 0)

    async def test_multi_load_is_read_only_start_registers_only_stop_rebuilds_registry(self):
        stars = [Star(Port())]
        self.native.get_all_stars = lambda: stars
        c = self.controller
        (await c.initialize_profile()).unwrap()
        repository = CapabilityRepository(c.runtime)
        self.assertEqual(repository.descriptors(extension_id="image"), ())
        before = database_contents(c.runtime)
        (await c.load_existing()).unwrap()
        self.assertEqual(database_contents(c.runtime), before)
        old = c.native_extensions
        declaration = screen_declaration(old.declarations())
        image = next(item for item in old.declarations()
                     if item.descriptor.package.extension_id == "image")
        self.assertIsNotNone(old.role_guard)
        (await c.start()).unwrap()
        self.assertEqual(repository.descriptors(extension_id="image"), (image.descriptor.package,))
        self.assertFalse(repository.installation(extension_id="image").is_success)
        (await c.stop()).unwrap()
        self.assertIsNone(old.current_declaration(declaration.host_tool_id))
        stars[:] = [Star(Port())]
        (await c.start()).unwrap()
        self.assertIsNot(c.native_extensions, old)
        refreshed = c.native_extensions.current_declaration(declaration.host_tool_id)
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.descriptor.package, declaration.descriptor.package)

    async def test_no_optional_provider_starts_with_all_seven_bundled_providers(self):
        self.native.get_all_stars = lambda: ()
        app = await self.start_host()
        declarations = self.controller.native_extensions.declarations()
        self.assertEqual({item.descriptor.package.extension_id for item in declarations},
                         {"content", "image", "companion.screen.native", "reality", "together", "game", "live"})
        self.assertTrue(all(CapabilityRepository(self.controller.runtime).installation(
            extension_id=extension_id).failure is not None for extension_id in
            ("content", "image", "companion.screen.native", "reality", "together", "game", "live")))
        self.assertIsNotNone(app.external)


if __name__ == "__main__":
    unittest.main()
