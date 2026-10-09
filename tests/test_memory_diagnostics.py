"""On-demand process memory readings stay lightweight and Dashboard-authenticated."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as support

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from astrbot_host.memory_diagnostics import process_memory_snapshot
from astrbot_host.model_api import PREFIX


class ProcessMemorySnapshotTests(unittest.TestCase):
    def test_snapshot_does_not_enable_tracemalloc(self):
        import astrbot_host.memory_diagnostics as diagnostics

        with patch.object(diagnostics, "_read_rss_bytes", return_value=(4096, "test")), \
                patch.object(diagnostics.tracemalloc, "is_tracing", return_value=False), \
                patch.object(diagnostics.tracemalloc, "get_traced_memory", side_effect=AssertionError):
            snapshot = process_memory_snapshot()

        self.assertEqual(snapshot["scope"], "astrbot_process")
        self.assertEqual(snapshot["rss_bytes"], 4096)
        self.assertEqual(snapshot["rss_source"], "test")
        self.assertFalse(snapshot["python_tracing_active"])
        self.assertIsNone(snapshot["python_heap_current_bytes"])
        self.assertIsNone(snapshot["python_heap_peak_bytes"])


class MemoryDiagnosticRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-memory-api-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes(
            "4.27.2", support.FakeEvent, support.FakeProvider, NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(
            self.native, support.host_config(), Path(temporary.name), native_types=types,
            now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()
        self.routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}

    async def call(self, *, username="admin"):
        import astrbot_host.model_api as model_api

        path = PREFIX + "/memory"
        request = Request({"type": "http", "method": "GET", "path": path,
                           "headers": [], "query_string": b""})
        fake_request = NS(username=username, query={})
        with patch.object(model_api, "request", fake_request):
            with bind_request_context(PluginRequest(request, username=username)):
                return await self.routes[path]()

    async def test_memory_route_is_read_only_and_requires_dashboard_identity(self):
        methods = {path: methods for path, _, methods, _ in self.native.registered_web_apis}
        self.assertEqual(methods[PREFIX + "/memory"], ["GET"])
        result = await self.call(username="")
        self.assertEqual(result["data"]["code"], "dashboard_identity_required")

    async def test_memory_route_returns_only_the_normalized_process_snapshot(self):
        import astrbot_host.model_api as model_api

        (await self.controller.initialize_profile()).unwrap()
        sample = {"observed_at": "2026-10-05T00:00:00+00:00", "scope": "astrbot_process",
                  "rss_bytes": 123456, "rss_source": "test", "python_tracing_active": False,
                  "python_heap_current_bytes": None, "python_heap_peak_bytes": None}
        with patch.object(model_api, "process_memory_snapshot", return_value=sample):
            result = await self.call()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], sample)


if __name__ == "__main__":
    unittest.main()
