"""End-to-end synthetic acceptance for the multi-target AstrBot host."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import json
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskContext
from companion_v2.memory.models import owner_key
from astrbot_host.multi_api import PREFIX
from astrbot_host.multi_controller import AstrBotMultiController
from tests.multi_host_support import MultiFixture, multi_config
from tests.staging_bootstrap_support import wait_for_batch


class _Query(dict):
    def getlist(self, key):
        value = self.get(key)
        return [] if value is None else [value]


class MultiLiveAcceptanceTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def _receive(self, controller, target, identifier):
        configured = controller.settings.target(target)
        event = self.event(target, identifier)
        result = await controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(controller.session, batch)
        app = controller.session.application
        context = TaskContext.restore(json.loads(app.messages.batch(batch)["context_json"]))
        self.assertEqual(context.scope.account_id, configured.account_id)
        self.assertEqual(context.scope.bot_id, configured.bot_id)
        return context, batch

    @staticmethod
    def _routes(native):
        return {route: handler for route, handler, _, _ in native.registered_web_apis}

    async def test_configured_private_targets_deliver_and_restart_with_bound_routes(self):
        self.controller.register_routes()
        routes = self._routes(self.native)
        request = NS(username="synthetic-dashboard-admin", query=_Query())
        with patch("astrbot_host.multi_api.request", request), patch("astrbot_host.memory_api.request", request):
            self.assertEqual((await routes[PREFIX + "/probe"]())["status"], "ok")
            self.assertEqual((await routes[PREFIX + "/initialize"]())["status"], "ok")
            self.assertEqual((await routes[PREFIX + "/start"]())["status"], "ok")

            first, first_batch = await self._receive(self.controller, "first", "live-preview-first")
            second, _ = await self._receive(self.controller, "second", "live-preview-second")
            self.assertNotEqual(owner_key(first), owner_key(second))
            self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls), 1)
            self.assertEqual(len(self.native.platforms["qq-second"].client._api._wsr_api.calls), 1)

            memory_path = next(path for path in routes if path.startswith(PREFIX + "/targets/first/") and path.endswith("/memory/settings"))
            self.assertEqual((await routes[memory_path]())["status"], "ok")
            pending = self.remember(self.controller.session.application, first, first_batch, pending=True)
            self.assertTrue(pending["operation_id"])
            self.assertEqual((await routes[PREFIX + "/stop"]())["data"]["state"], "stopped")

        await self.controller.terminate()
        self.controller = self.make_controller()
        loaded = await self.controller.load_existing()
        self.assertTrue(loaded.is_success, loaded.failure)
        self.assertTrue(loaded.unwrap()["loaded"])
        self.assertEqual(self.controller.session.application.state, "new")
        self.assertTrue((await self.controller.start()).is_success)
        recovered = self.controller.authority.context("first", "role-a")
        self.assertEqual(owner_key(first), owner_key(recovered))
        self.assertEqual(self.controller.session.application.memory.writer.operation(
            recovered, pending["operation_id"]).is_success, True)

        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])

        delivery_root = TemporaryDirectory(prefix="companion-multi-live-delivery-")
        self.addCleanup(delivery_root.cleanup)
        delivery = AstrBotMultiController(self.native, multi_config(delivery_mode="onebot_private"),
            Path(delivery_root.name), native_types=self.types, now=self.clock.now)
        self.addAsyncCleanup(delivery.terminate)
        delivery.register_routes()
        routes = self._routes(self.native)
        previous_main_sends = len(self.native.platforms["qq-main"].client._api._wsr_api.calls)
        previous_second_sends = len(self.native.platforms["qq-second"].client._api._wsr_api.calls)
        request.query = _Query()
        with patch("astrbot_host.multi_api.request", request):
            self.assertEqual((await routes[PREFIX + "/probe"]())["status"], "ok")
            self.assertEqual((await routes[PREFIX + "/initialize"]())["status"], "ok")
            request.query = _Query({"target_id": "first"})
            self.assertEqual((await routes[PREFIX + "/authorize-delivery"]())["status"], "ok")
            request.query = _Query()
            self.assertEqual((await routes[PREFIX + "/start"]())["status"], "ok")

        await self._receive(delivery, "first", "live-delivery-first")
        await self._receive(delivery, "second", "live-delivery-second")
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls),
                         previous_main_sends + 1)
        self.assertEqual(len(self.native.platforms["qq-second"].client._api._wsr_api.calls),
                         previous_second_sends + 1)

        request.query = _Query({"target_id": "first"})
        with patch("astrbot_host.multi_api.request", request):
            self.assertEqual((await routes[PREFIX + "/revoke-delivery"]())["status"], "ok")
        await self._receive(delivery, "first", "live-delivery-revoked")
        self.assertEqual(len(self.native.platforms["qq-main"].client._api._wsr_api.calls),
                         previous_main_sends + 2)
        self.assertEqual(len(self.native.platforms["qq-second"].client._api._wsr_api.calls),
                         previous_second_sends + 1)
        await delivery.terminate()
        self.assertEqual(self.native.registered_web_apis, [])


if __name__ == "__main__":
    unittest.main()
