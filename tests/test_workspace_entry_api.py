"""Refresh the companion page asset token through an authenticated plugin API request."""

import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.page_api import PageWebAPI, PREFIX


PLUGIN_NAME = "astrbot_plugin_private_companion"


class WorkspaceEntryApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.page_service = NS(get_plugin_page_entry_config=AsyncMock(return_value={
            "content_path": "/api/plugin/page/content/astrbot_plugin_private_companion/%E9%99%AA%E4%BC%B4%E5%B0%8F%E5%B1%8B/?asset_token=fresh",
        }))
        self.app = NS(state=NS(services=NS(plugin_pages=self.page_service)))
        self.handler = next(
            handler for path, handler, _, _ in PageWebAPI(NS()).routes()
            if path == PREFIX + "/page/workspace-entry"
        )

    async def request(self, *, username="admin", query=b"", plugin_name=PLUGIN_NAME, language="zh-CN"):
        request = Request({
            "type": "http",
            "method": "GET",
            "path": PREFIX + "/page/workspace-entry",
            "headers": [(b"accept-language", language.encode("ascii"))],
            "query_string": query,
            "app": self.app,
        })
        plugin_request = PluginRequest(request, plugin_name=plugin_name, username=username)
        with bind_request_context(plugin_request):
            return await self.handler()

    async def test_uses_current_dashboard_identity_to_issue_entry(self):
        response = await self.request(language="en-US,en;q=0.8")

        self.assertEqual(response["status"], "ok")
        self.assertIn("asset_token=fresh", response["data"]["content_path"])
        self.page_service.get_plugin_page_entry_config.assert_awaited_once_with(
            plugin_name=PLUGIN_NAME,
            page_name="陪伴小屋",
            username="admin",
            locale="en-US",
        )

    async def test_rejects_api_keys_and_query_overrides(self):
        for username, query in (("api_key:synthetic", b""), ("admin", b"page=other")):
            response = await self.request(username=username, query=query)
            self.assertEqual(response["status"], "error")
        self.page_service.get_plugin_page_entry_config.assert_not_awaited()

    async def test_rejects_calls_routed_under_another_plugin_name(self):
        response = await self.request(plugin_name="another_plugin")

        self.assertEqual(response["data"]["code"], "page_request_invalid")
        self.page_service.get_plugin_page_entry_config.assert_not_awaited()

    async def test_service_failures_return_a_safe_error_code(self):
        self.page_service.get_plugin_page_entry_config.side_effect = RuntimeError("private service detail")

        response = await self.request()

        self.assertEqual(response["data"]["code"], "page_entry_unavailable")
        self.assertNotIn("private service detail", response["reason"])

    async def test_rejects_entries_without_a_fresh_asset_token(self):
        self.page_service.get_plugin_page_entry_config.return_value = {
            "content_path": "/api/plugin/page/content/astrbot_plugin_private_companion/%E9%99%AA%E4%BC%B4%E5%B0%8F%E5%B1%8B/",
        }

        response = await self.request()

        self.assertEqual(response["data"]["code"], "page_entry_unavailable")


if __name__ == "__main__":
    unittest.main()
