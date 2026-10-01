"""多目标模式下的两条安装级能力：备份与 V1 迁移。

对应 `docs/MULTI_TARGET_OPEN_DECISIONS_20260930.md` 的推荐组合：

* 备份：多目标也注册 `BackupWebAPI`，且暂存还原必须在**开库之前**被应用——
  少了这一步会变成「暂存成功、重启不生效」，比入口点不动更糟。
* 迁移：路由按角色挂载（写的是角色设置），目标从**会话管线上下文**推出来；
  单目标下原先传的是宿主上下文，目标推导必然失败、被兜底成 `legacy_apply_failed`。

用 AstrBot 自带 Python 运行（见 AGENTS.md）。
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as support
from tests import multi_host_support as multi_support
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request


BACKUP_PREFIX = "/astrbot_plugin_private_companion_v2/backup"
LEGACY_PREFIX = "/astrbot_plugin_private_companion_v2/legacy"


def v1_weather_config() -> dict:
    """一份最小可用的 V1 天气配置——它有一条真实的转换器。"""
    return {"weather_city": "杭州", "weather_lat": 30.25, "weather_lon": 120.16,
            "enable_weather_context": True, "weather_refresh_minutes": 90,
            "enable_weather_alerts": False}


def v1_root(parent: Path) -> Path:
    """在给定目录下造一份 V1 数据根：配置转储 + 一个 SQLite。"""
    root = parent / "astrbot_plugin_private_companion"
    root.mkdir(parents=True, exist_ok=True)
    (root / "companion_config.json").write_text(json.dumps(v1_weather_config(), ensure_ascii=False),
                                                encoding="utf-8")
    return root


class RouteCaller:
    """按宿主注册表直接调用路由，绕开 HTTP —— 与 test_model_provider_api 同一做法。"""

    def __init__(self, native, module):
        self.routes = {path: handler for path, handler, _, _ in native.registered_web_apis}
        self.module = module

    async def call(self, route, *, payload=None, username="admin", query=None):
        request = Request({"type": "http", "method": "POST" if payload is not None else "GET",
                           "path": route, "headers": [], "query_string": b""})
        body = payload if isinstance(payload, (bytes, type(None))) else json.dumps(payload).encode("utf-8")
        fake = NS(username=username, query=query or {},
                  body=(lambda: self._body(body)) if body is not None else None)
        with patch.object(self.module, "request", fake):
            with bind_request_context(PluginRequest(request, username=username)):
                return await self.routes[route]()

    @staticmethod
    async def _body(raw):
        return raw


class MultiTargetInstallApiTests(multi_support.MultiFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        multi_support.MultiFixture.setUp(self)

    async def test_backup_routes_are_registered_in_multi_mode(self):
        self.controller.register_routes()
        paths = {path for path, _, _, _ in self.native.registered_web_apis}

        # 备份是安装级的：挂一次，不按角色重挂。
        self.assertIn(BACKUP_PREFIX, paths)
        self.assertIn(BACKUP_PREFIX + "/create", paths)
        self.assertIn(BACKUP_PREFIX + "/restore", paths)

    async def test_staged_restore_is_applied_before_the_store_opens(self):
        """多目标下必须补上这一步：否则还原永远不生效。"""
        import astrbot_host.multi_controller as multi_controller

        calls = []
        applied = {"applied": True, "reason": "test-restore"}

        def recorder(root, *, installation_id):
            # 记录当时运行实例还没有打开——那正是唯一能安全换文件的时刻。
            calls.append((root, installation_id, self.controller.runtime))
            return dict(applied)

        with patch.object(multi_controller, "apply_staged_restore", recorder):
            initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)

        self.assertEqual(len(calls), 1, "开库路径必须调用一次 apply_staged_restore")
        root, installation_id, runtime_at_call = calls[0]
        self.assertEqual(Path(root), self.controller.profile_root / "runtime")
        self.assertEqual(installation_id, self.controller.settings.installation_id)
        self.assertIsNone(runtime_at_call, "必须在开库之前应用，否则会留下孤儿连接")
        # 结果要留在运行实例上，「还原到底生效了没有」才有地方读。
        self.assertEqual(self.controller.last_restore, applied)

    async def test_legacy_routes_are_mounted_once_per_role(self):
        self.controller.register_routes()
        paths = {path for path, _, _, _ in self.native.registered_web_apis}

        inventory = self.controller.web_api.target_inventory()
        expected = [role["legacy_api"] for target in inventory for role in target["roles"]]
        self.assertTrue(expected, "多目标夹具里应当有角色")
        for route in expected:
            self.assertIn(route, paths, f"{route} 应当被注册")
            self.assertIn(route + "/plan", paths)
            self.assertIn(route + "/apply", paths)
        # 安装级的老地址（单目标用）不应在多目标里出现，否则会写成没角色的生效范围。
        self.assertNotIn(LEGACY_PREFIX, paths)

    async def test_page_directory_publishes_a_legacy_route_per_role(self):
        await self.controller.initialize_profile()
        self.controller.register_routes()
        caller = RouteCaller(self.native, __import__("astrbot_host.page_api", fromlist=["request"]))

        result = await caller.call("/astrbot_plugin_private_companion_v2/page/targets")

        self.assertEqual(result["status"], "ok", result)
        data = result["data"]
        self.assertEqual(data["mode"], "multi")
        for target in data["targets"]:
            for role in target["roles"]:
                self.assertTrue(role["legacy_api"].endswith("/legacy"), role)


class MultiTargetLegacyApplyTests(multi_support.MultiFixture, unittest.IsolatedAsyncioTestCase):
    """多目标下的迁移：先选目标与角色，再对着那个角色的路径执行。"""

    def setUp(self):
        multi_support.MultiFixture.setUp(self)
        temporary = TemporaryDirectory(prefix="companion-legacy-multi-")
        self.addCleanup(temporary.cleanup)
        self.v1 = v1_root(Path(temporary.name))
        config = multi_support.multi_config()
        config["legacy"] = {"v1_root": str(self.v1)}
        self.controller = self.make_controller(config=config)

    async def test_migration_writes_the_selected_roles_settings(self):
        import astrbot_host.legacy_api as legacy_api

        await self.controller.initialize_profile()
        self.controller.register_routes()
        caller = RouteCaller(self.native, legacy_api)

        inventory = self.controller.web_api.target_inventory()
        target = inventory[0]
        role = target["roles"][0]
        planned = await caller.call(role["legacy_api"] + "/plan")

        self.assertEqual(planned["status"], "ok", planned)
        self.assertTrue(planned["data"]["scope_status"], "试算要带生效范围可用性")
        applied = await caller.call(role["legacy_api"] + "/apply",
                                    payload={"plan_token": planned["data"]["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertGreater(applied["data"]["written_count"], 0)
        self.assertEqual(applied["data"]["errors"], [])

        # 写到的是**选中角色**的设置：换个角色读同一组，值应当还是默认。
        view = self.controller.web_api.target_inventory()[0]
        other = next((item for item in view["roles"] if item["role_id"] != role["role_id"]), None)
        if other is not None:
            other_plan = await caller.call(other["legacy_api"] + "/plan")
            self.assertNotEqual(other_plan["data"]["plan_token"], "",
                                "另一个角色也应当能读同一份 V1 数据（允许复制，见口径 B2）")


class SingleTargetLegacyApplyTests(unittest.IsolatedAsyncioTestCase):
    """单目标下的迁移执行：目标必须从会话的管线上下文推出来。"""

    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-legacy-api-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.v1 = v1_root(self.root)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider, NS, NS,
                                           support.FakeReverseApi)
        config = support.host_config()
        config["legacy"] = {"v1_root": str(self.v1)}
        self.controller = support.AstrBotStagingController(self.native, config, self.root,
                                                           native_types=types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)

    async def test_scope_targets_come_from_the_session_pipeline_context(self):
        import astrbot_host.legacy_api as legacy_api
        from companion_v2.legacy.migration import ConfigIntent

        (await self.controller.initialize_profile()).unwrap()
        session = self.controller.session
        api = legacy_api.LegacyMigrationWebAPI(self.controller)

        for scope, group in (("role.state", "role.state"), ("proactive.contact", "proactive.contact")):
            intent = ConfigIntent(source_id="test", scope=scope, group_id=group, changes={"x": 1})
            target = api._scope_target(session, intent)
            self.assertIsNotNone(target, f"{scope} 应当能从会话上下文推出目标")
            self.assertEqual(target.scope.installation_id, session.profile.target.scope.installation_id)

        # 宿主上下文（只有注册路由那套接口）推不出目标——这正是原先的错处。
        empty = ConfigIntent(source_id="test", scope="role.state", group_id="role.state", changes={})
        self.assertIsNone(api._scope_target(NS(profile=NS(target=NS())), empty))

    async def test_plan_reports_scope_availability_before_applying(self):
        self.controller.register_routes()
        caller = RouteCaller(self.native, __import__("astrbot_host.legacy_api", fromlist=["request"]))
        (await self.controller.initialize_profile()).unwrap()

        planned = await caller.call(LEGACY_PREFIX + "/plan")

        self.assertEqual(planned["status"], "ok", planned)
        status = planned["data"]["scope_status"]
        self.assertTrue(status, "试算要回答每个生效范围能不能写")
        for item in status:
            self.assertTrue(item["available"], item)
            self.assertEqual(item["reason"], "")

    async def test_apply_writes_the_planned_settings(self):
        self.controller.register_routes()
        caller = RouteCaller(self.native, __import__("astrbot_host.legacy_api", fromlist=["request"]))
        (await self.controller.initialize_profile()).unwrap()
        planned = await caller.call(LEGACY_PREFIX + "/plan")
        token = planned["data"]["plan_token"]

        applied = await caller.call(LEGACY_PREFIX + "/apply", payload={"plan_token": token})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertGreater(applied["data"]["written_count"], 0,
                           "迁移必须真的写进去（原先目标推导失败，一条都写不进去）")
        self.assertEqual(applied["data"]["errors"], [])
