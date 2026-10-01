"""Run separately: real SDK plugin entry and isolated multi-target life routes."""

import asyncio
from functools import partial
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import sys
from unittest.mock import patch

# This fixture establishes a temporary AstrBot import root before SDK imports.
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.foundation.clock import DeterministicClock
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request


async def run():
    root = Path(__file__).resolve().parents[1]
    package = ModuleType("companion_life_entry_fixture")
    package.__path__ = [str(root)]
    sys.modules[package.__name__] = package
    entry = importlib.import_module(package.__name__ + ".main")
    native = MultiNativeContext()
    clock = DeterministicClock.at(NOW)
    types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace, SimpleNamespace, FakeReverseApi)
    factory = partial(entry.AstrBotMultiController, native_types=types, now=clock.now)
    with TemporaryDirectory(prefix="companion-life-entry-") as temporary:
        with patch.object(entry.StarTools, "get_data_dir", return_value=Path(temporary)), \
                patch.object(entry, "AstrBotMultiController", factory):
            plugin = entry.PrivateCompanionV2StagingPlugin(native, multi_config())
        controller = plugin.staging
        try:
            await plugin.initialize()
            assert controller.runtime is None
            (await controller.initialize_profile()).unwrap()
            routes = {path: handler for path, handler, _, _ in native.registered_web_apis}
            paths = [role["life_api"] for target in controller.web_api.target_inventory() for role in target["roles"]]
            assert len(paths) == 4 and all(path in routes and path + "/command" in routes for path in paths)

            async def request(path, data=None):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else b""
                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}
                req = Request({"type": "http", "method": "POST" if data else "GET", "path": path,
                    "headers": [(b"content-type", b"application/json")], "query_string": b""}, receive=receive)
                with bind_request_context(PluginRequest(req, username="admin")):
                    result = await routes[path]()
                assert result["status"] == "ok", result
                return result["data"]

            for path in paths:
                status = await request(path)
                await request(path + "/command", dict(action="configure", operation_key="enable",
                    view_token=status["view_token"], edit_token=status["edit_token"],
                    changes={"enabled": True, "diary_enabled": False, "derive_enabled": False}))
            (await controller.start()).unwrap()
            app = controller.session.application
            assert len([r for r in app.life_runtime.routines.values() if r.instruction is not None]) == 2
            await request(paths[0] + "/command", dict(action="sleep", operation_key="sleep", minutes=1,
                view_token=(await request(paths[0]))["view_token"]))
            report = (await controller.stop()).unwrap()
            assert report.state == "stopped" and report.pending_handles == ()
            assert (await request(paths[0]))["activities"][0]["state"] == "active"
            assert app.life_runtime.active_handles == () and app.journal_schedule.active_handles == ()
            assert native.provider.client.state.calls == []
            assert all(not p.client._api._wsr_api.calls for p in native.platforms.values())
        finally:
            await plugin.terminate()
        assert controller.runtime is None and native.registered_web_apis == []
        print(json.dumps({"life_routes": len(paths), "state": report.state, "route_cleanup": True,
                          "model_calls": 0, "platform_calls": 0}))


if __name__ == "__main__":
    asyncio.run(run())
