"""Bundled services start independently and release their owned resources."""

import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock

from tests import test_astrbot_staging_host as host_support
from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.builtins import create_bundled_extensions, MANAGED_EXTENSIONS
from companion_v2.capabilities import CapabilityRepository
from companion_v2.execution.models import TaskError
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import NOW


class NativeServiceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-native-lifecycle-")
        self.root = Path(self.temporary.name)
        self.runtime = StorageRuntime.open(data_root=self.root / "v2", installation_id="native-lifecycle")
        self.context = NS(get_all_stars=lambda: ())
        self.controller = NS(context=self.context, native_extensions=None, session=None, now=lambda: NOW)
        leases, issues = create_bundled_extensions(self.root / "v2", context=self.context,
                                                  controller=self.controller)
        self.assertEqual(issues, ())
        self.registry = NativeExtensionRegistry(self.context, bundled_extensions=leases,
                                                managed_extensions=MANAGED_EXTENSIONS)
        self.controller.native_extensions = self.registry
        self.application = NS(runtime=self.runtime, state="running", external=None)
        self.registry.attach(self.application)
        self.registry.register_catalog(observed_at=NOW).unwrap()
        self.repository = CapabilityRepository(self.runtime)

    async def asyncTearDown(self):
        await self.registry.aclose()
        self.runtime.close()
        self.temporary.cleanup()

    def acquire(self, name):
        lease = self.registry._lease(name)
        package = lease.manifest.package
        self.repository.acquire(extension_id=name, package_id=package.package_id,
            package_version=package.package_version, expected_revision=0, observed_at=NOW).unwrap()
        return lease

    async def test_existing_v2_owner_advances_without_independent_predecessor(self):
        for name in ("together", "reality", "image"):
            package = self.registry._lease(name).manifest.package
            previous = replace(package, package_version="2.1.0", artifact_hash="previous-v2-" + name)
            self.repository.register_descriptor(previous, registered_at=NOW).unwrap()
            self.repository.acquire(extension_id=name, package_id=previous.package_id,
                package_version=previous.package_version, expected_revision=0, observed_at=NOW).unwrap()
        before = tuple(dict(row) for row in self.runtime.read_all("SELECT * FROM capability_authorizations", ()))
        reloaded = NativeExtensionRegistry(self.context, bundled_extensions=self.registry._bundled_extensions,
                                           managed_extensions=MANAGED_EXTENSIONS)
        self.addAsyncCleanup(reloaded.aclose)
        reloaded.attach(self.application)
        reloaded.register_catalog(observed_at=NOW).unwrap()
        for name in ("together", "reality", "image"):
            installed = self.repository.installation(extension_id=name).unwrap()
            current = self.registry._lease(name).manifest.package
            self.assertEqual((installed.package_version, installed.artifact_hash),
                             (current.package_version, current.artifact_hash))
        self.assertEqual(before, tuple(dict(row) for row in self.runtime.read_all(
            "SELECT * FROM capability_authorizations", ())))
        self.assertEqual(reloaded.issues, ())

    async def test_seven_modules_need_no_companion_stars_and_close_idempotently(self):
        self.assertEqual(len(self.registry._bundled_extensions), 7)
        for lease in self.registry._bundled_extensions:
            self.acquire(lease.manifest.package.extension_id)
        await self.registry.start()
        await asyncio.gather(*(lease.start() for lease in self.registry._bundled_extensions))
        self.assertTrue(all(lease.state == "running" for lease in self.registry._bundled_extensions))
        self.assertEqual(len(self.registry.declarations()), 63)
        await self.registry.aclose()
        await self.registry.aclose()
        self.assertTrue(all(not lease.current(self.context) for lease in self.registry._bundled_extensions))

    async def test_loaded_legacy_companions_are_never_queried_for_execution(self):
        class LegacyStar:
            activated = True
            def __init__(inner, name):
                inner.root_dir_name = 'astrbot_plugin_' + name + '_companion'
            @property
            def star_cls(inner):
                raise AssertionError('legacy companion execution must not be read')
        self.context.get_all_stars = lambda: [LegacyStar(name) for name in
            ('content', 'image', 'screen', 'reality', 'together', 'game', 'live_stream')]
        from astrbot_host.native_extensions.discovery import discover
        entries, issues = discover(self.context, excluded_extensions=MANAGED_EXTENSIONS)
        self.assertEqual(entries, {})
        self.assertEqual(issues, ())

    async def test_slow_start_never_blocks_other_modules_or_registry_start(self):
        game, live = self.acquire("game"), self.acquire("live")
        entered, finish = asyncio.Event(), asyncio.Event()
        async def initialize():
            entered.set()
            await finish.wait()
        game.instance.initialize = initialize
        await asyncio.wait_for(self.registry.start(), timeout=0.5)
        await asyncio.wait_for(entered.wait(), timeout=0.5)
        await asyncio.wait_for(live.start(), timeout=0.5)
        self.assertEqual(game.state, "starting")
        self.assertEqual(live.state, "running")
        finish.set()
        await game.start()

    async def test_pause_cancels_start_rebuilds_and_resume_uses_new_instance(self):
        lease = self.acquire("game")
        entered = asyncio.Event()
        async def initialize():
            entered.set()
            await asyncio.Event().wait()
        lease.instance.initialize = initialize
        lease.begin_start()
        await entered.wait()
        self.repository.pause(extension_id="game", expected_revision=1, observed_at=NOW).unwrap()
        await self.registry.reconcile_service("game")
        replacement = self.registry._lease("game")
        self.assertIsNot(replacement, lease)
        self.assertTrue(lease._disposed)
        self.assertTrue(lease._start_task.cancelled())
        self.assertIsNone(self.registry.active_service("game"))
        self.assertEqual(replacement.state, "inactive")
        self.repository.resume(extension_id="game", expected_revision=2, observed_at=NOW).unwrap()
        await self.registry.reconcile_service("game")
        await replacement.start()
        self.assertIs(self.registry.active_service("game"), replacement.instance)

    async def test_configure_paused_module_keeps_it_paused_and_rejects_stale_revision(self):
        lease = self.acquire("live")
        self.repository.pause(extension_id="live", expected_revision=1, observed_at=NOW).unwrap()
        revision = lease.instance.config.revision()
        result = await self.registry.configure_service("live", {"vts_port": 8002}, revision)
        self.assertTrue(result["saved"])
        self.assertEqual(result["runtime"]["state"], "inactive")
        self.assertIsNot(lease, self.registry._lease("live"))
        self.assertEqual(self.registry.service("live").config["vts_port"], 8002)
        with self.assertRaises(TaskError) as error:
            await self.registry.configure_service("live", {"vts_port": 8003}, revision)
        self.assertEqual(error.exception.code, "native_settings_conflict")

    async def test_failed_start_is_visible_and_other_services_keep_running(self):
        game, live = self.acquire("game"), self.acquire("live")
        game.instance.initialize = AsyncMock(side_effect=RuntimeError("synthetic startup failure"))
        await self.registry.start()
        await asyncio.gather(game.start(), live.start())
        self.assertEqual(self.registry.status("game")["error_code"], "native_service_start_failed")
        self.assertIsNotNone(self.registry.service("game"))
        self.assertIsNone(self.registry.active_service("game"))
        self.assertIsNotNone(self.registry.active_service("live"))
        await self.registry.reconcile_service("game")
        await self.registry._lease("game").start()
        self.assertIsNotNone(self.registry.active_service("game"))

    async def test_restart_releases_real_room_port_before_rebinding(self):
        lease = self.acquire("together")
        await lease.start()
        service = lease.instance
        service.room_server.requested_port = 0
        await service.room_server.start()
        self.assertTrue(service.room_server.running)
        result = await self.registry.configure_service("together", {"server": {"enabled": False}},
                                                        service.config.revision())
        self.assertTrue(result["saved"])
        self.assertFalse(service.room_server.running)
        await self.registry._lease("together").start()
