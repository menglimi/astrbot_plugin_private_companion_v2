"""Page discovery and target selection use the real SDK with isolated V2 data."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as support
from tests.multi_host_support import MultiFixture, multi_config
from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.dashboard.services.plugin_page_service import PluginPageService
from starlette.requests import Request
from astrbot_host.management_identity import dashboard_operator
from astrbot_host.page_api import PREFIX
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy


class PageRequests:
    def register(self):
        self.controller.register_routes()
        self.handler = next(handler for path, handler, _, _ in self.native.registered_web_apis
                            if path == PREFIX + "/page/targets")

    async def request(self, *, username="admin", query=""):
        request = Request({"type": "http", "method": "GET", "path": PREFIX + "/page/targets",
                           "headers": [], "query_string": query.encode()})
        with bind_request_context(PluginRequest(request, username=username)):
            return await self.handler()


class SinglePageTests(PageRequests, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-page-api-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                          NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(), Path(temporary.name),
                                                         native_types=types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.register()

    async def test_directory_requires_loaded_host_login_and_current_core_tier(self):
        for username in (None, "", "api_key:synthetic"):
            self.assertEqual((await self.request(username=username))["data"]["code"], "dashboard_identity_required")
        self.assertEqual((await self.request())["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        self.assertEqual((await self.request(query="subject_id=another"))["data"]["code"], "page_request_invalid")
        listed = (await self.request())["data"]
        self.assertEqual(listed["mode"], "single")
        self.assertEqual(listed["acquaintance_api"], PREFIX + "/acquaintance")
        target = listed["targets"][0]
        self.assertEqual(target["participant_id"], "200")
        self.assertEqual(target["roles"], [{"role_id":"persona-a",
            **{name + "_api": PREFIX + "/" + name for name in
               ("memory", "state", "life", "relationships", "growth", "reply", "model", "config",
                # V1 迁移写的是角色设置，所以它的地址也在角色这一层：
                # 单目标是固定路径，多目标由 target_inventory 每角色各生成一份。
                "legacy", "persona")},
            "perception_native_api": PREFIX + "/perception-native",
            "reality_access_api": PREFIX + "/reality-access",
            "screen_access_api": PREFIX + "/screen-access",
            # QQ 空间拓展与 Reality/Screen 同层：按角色安装与授权，所以地址跟角色走。
            "qzone_extension_api": PREFIX + "/qzone-extension",
            "image_material_api": PREFIX + "/image-materials"}])
        self.assertNotIn("provider", json.dumps(listed))
        operator = dashboard_operator(self.controller.runtime, "admin", at=support.NOW)
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
                        expected_revision=policy.revision, observed_at=support.NOW)
        self.assertEqual((await self.request())["data"]["code"], "core_access_required")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_page_directory_unregisters_and_retained_handler_refuses_stopped_host(self):
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.request())["data"]["code"], "staging_host_terminated")

    async def test_single_target_acquaintance_directory_uses_the_configured_role(self):
        (await self.controller.initialize_profile()).unwrap()
        routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        directory = routes[PREFIX + "/acquaintance"]
        with patch("astrbot_host.acquaintance_api.request", NS(username="admin", query={})), \
                patch("astrbot_host.acquaintance_api.PersonAcquaintanceDirectory") as service:
            service.return_value.directory.return_value = {"persons": [], "counts": {"total": 0}}
            response = await directory()
        self.assertEqual(response["status"], "ok", response)
        service.return_value.directory.assert_called_once_with([{
            "platform": self.controller.settings.platform_id,
            "bot_id": self.controller.settings.bot_id,
            "account_id": self.controller.settings.account_id,
            "role_id": self.controller.settings.role_id,
        }])
        self.assertEqual(response["data"]["groups"], [])
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_model_route_requires_dashboard_identity_and_valid_request(self):
        (await self.controller.initialize_profile()).unwrap()
        routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        status = routes[PREFIX + "/model"]
        configure = routes[PREFIX + "/model/configure"]
        with patch("astrbot_host.model_api.request", NS(username="admin", query={})):
            response = await status()
        self.assertEqual(response["status"], "ok", response)
        self.assertTrue(response["data"]["tasks"])
        self.assertEqual(len(response["data"]["tasks"][0]["edit_token"]), 64)
        with patch("astrbot_host.model_api.request", NS(username="api_key:synthetic", query={})):
            self.assertEqual((await status())["data"]["code"], "dashboard_identity_required")

        async def malformed():
            return b'{"kind":"conversation.reply","kind":"duplicate"}'

        with patch("astrbot_host.model_api.request", NS(username="admin", query={}, body=malformed)):
            self.assertEqual((await configure())["data"]["code"], "model_request_invalid")
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_setup_reads_pinned_identity_without_starting_the_host(self):
        (await self.controller.initialize_profile()).unwrap()
        before = self.controller.status()["session_state"]
        routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}
        with patch("astrbot_host.setup_api.request", NS(username="admin", query={})):
            progress = await routes[PREFIX + "/setup/status"]()
            choices = await routes[PREFIX + "/setup/targets"]()
        self.assertEqual(progress["status"], "ok", progress)
        self.assertEqual(choices["status"], "ok", choices)
        self.assertTrue(progress["data"]["binding"]["pinned"])
        self.assertEqual(progress["data"]["binding"]["role_id"], self.controller.settings.role_id)
        self.assertEqual(set(choices["data"]), {"accounts", "personas", "targets"})
        self.assertEqual(self.controller.resolved_settings().role_id, self.controller.settings.role_id)
        self.assertEqual(self.controller.status()["session_state"], before)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_sdk_discovers_same_voxel_shell_and_injects_scoped_bridge(self):
        plugin_root = Path(__file__).resolve().parents[1]
        service = PluginPageService(NS(plugin_store_path=str(plugin_root.parent)))
        plugin = NS(root_dir_name=plugin_root.name, reserved=False)
        pages = await service.discover_plugin_pages(plugin)
        self.assertEqual([page.name for page in pages], ["陪伴小屋"])
        page = next(page for page in pages if page.name == "陪伴小屋")
        entry = await service.resolve_plugin_page_file(plugin, page.name, "")
        html = service.rewrite_plugin_page_html(entry.read_text(encoding="utf-8"), plugin_root.name, page.name,
                                               "index.html", theme="light")
        self.assertIn("assets/voxel-room.js", html)
        self.assertIn("memory-page.js", html)
        self.assertIn("models-page.js", html)
        self.assertIn("perception-native-page.js", html)
        self.assertIn("/api/plugin/page/bridge-sdk.js", html)
        self.assertIn('name="companion-api-host"', html)
        # GIF 地址必须来自静态 HTML 属性，宿主才能把它改写到插件资源路由；
        # 内联脚本只负责从 template 中随机克隆，不再把裸相对路径交给浏览器。
        for asset in ("room-loading-tea-coffee.gif", "room-loading-mug.gif"):
            self.assertRegex(
                html,
                rf'src="/api/plugin/page/content/astrbot_plugin_private_companion_v2/[^" ]+/assets/{asset}\?'
            )
            self.assertNotIn(f'src="assets/{asset}', html)
        host_page = await service.resolve_plugin_page_file(plugin, "陪伴小屋", "workspaces/host/index.html")
        host_html = host_page.read_text(encoding="utf-8")
        self.assertRegex(host_html, r'<script src="app\.js(?:\?[^\"]*)?" defer></script>')
        self.assertIn('id="topology-canvas"', host_html)
        self.assertIn("embedded-bridge.js", host_html)
        content = NS(root_dir_name="astrbot_plugin_content_companion", reserved=False)
        self.assertNotIn("framework-preview-v1", [p.name for p in await service.discover_plugin_pages(content)])


class MultiPageTests(PageRequests, MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def test_same_native_user_on_different_accounts_roles_and_group_have_distinct_paths(self):
        config = multi_config(group_targets=[dict(target_id="reading", platform_id="qq-main", account_id="100",
                                                  bot_id="bot-a", group_id="300")])
        self.controller = self.make_controller(config)
        self.register()
        (await self.controller.initialize_profile()).unwrap()
        result = await self.request()
        self.assertEqual(result["status"], "ok", result)
        targets = result["data"]["targets"]
        private = [target for target in targets if target["scope_kind"] == "private"]
        self.assertEqual([target["participant_id"] for target in private], ["200", "200"])
        paths = [role["memory_api"] for target in private for role in target["roles"]]
        self.assertEqual(len(set(paths)), 4)
        routes = {path for path, *_ in self.native.registered_web_apis}
        self.assertTrue(all(path in routes and path + "/reflections/queue" in routes for path in paths))
        state_paths = [role["state_api"] for target in private for role in target["roles"]]
        self.assertEqual(len(set(state_paths)), 4)
        self.assertTrue(all(path in routes for path in state_paths))
        for name in ("life", "relationships", "growth", "model"):
            paths = [role[name + "_api"] for target in private for role in target["roles"]]
            self.assertEqual(len(set(paths)), 4)
            suffix = "/configure" if name == "model" else "/command"
            self.assertTrue(all(path in routes and path + suffix in routes for path in paths))
        paths = [role["perception_native_api"] for target in private for role in target["roles"]]
        self.assertEqual(len(set(paths)), 4)
        self.assertTrue(all(path in routes and path + "/configure" in routes for path in paths))
        persona_paths = [role["persona_api"] for target in private for role in target["roles"]]
        self.assertEqual(len(set(persona_paths)), 4)
        self.assertTrue(all(path in routes and path + "/command" in routes for path in persona_paths))
        screen_paths = [role["screen_access_api"] for target in private for role in target["roles"]]
        self.assertEqual(len(set(screen_paths)), 4)
        self.assertTrue(all(path in routes and path + "/configure" in routes for path in screen_paths))
        group = next(target for target in targets if target["scope_kind"] == "group")
        self.assertTrue(all(role["memory_api"] is None for role in group["roles"]))
        self.assertTrue(all(role["model_api"] is None for role in group["roles"]))
        self.assertTrue(all(role["perception_native_api"] is None for role in group["roles"]))
        self.assertTrue(all(role["persona_api"] is None for role in group["roles"]))
        self.assertTrue(all(role["screen_access_api"] is None for role in group["roles"]))
        # 群目标没有「角色设置」这回事，所以迁移地址同样是 None，
        # 而不是一个读不出东西的地址。
        self.assertTrue(all(role["legacy_api"] is None for role in group["roles"]))
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
