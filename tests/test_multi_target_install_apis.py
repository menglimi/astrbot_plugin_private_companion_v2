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
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as support
from tests import multi_host_support as multi_support
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request


BACKUP_PREFIX = "/astrbot_plugin_private_companion_v2/backup"
LEGACY_PREFIX = "/astrbot_plugin_private_companion_v2/legacy"


class QueryArgs(dict):
    def getlist(self, key):
        value = self.get(key)
        if value is None:
            return []
        return value if isinstance(value, list) else [value]


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
        query_values = QueryArgs(query or {})
        fake = NS(username=username, query=query_values,
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

    async def test_account_migration_appends_new_routes_and_preserves_v2_persona_roles(self):
        import astrbot_host.legacy_api as legacy_api
        from companion_v2.legacy.migration import ConfigIntent

        self.controller.save_plugin_config = lambda candidate: (
            self.controller.config.clear(), self.controller.config.update(candidate))
        async def apply_bindings(candidate):
            self.controller.config.clear()
            self.controller.config.update(candidate)
            return {"saved": True, "started": True}
        self.controller.apply_bindings = AsyncMock(side_effect=apply_bindings)
        api = legacy_api.LegacyMigrationWebAPI(self.controller)
        duplicate_route = {"target_id": "v1-copy", "platform_id": "qq-main", "account_id": "100",
                           "bot_id": "bot-a", "participant_id": "200"}
        new_route = {"target_id": "v1-extra", "platform_id": "qq-main", "account_id": "100",
                     "bot_id": "bot-a", "participant_id": "201"}
        intent = ConfigIntent(
            scope="plugin_config", group_id="plugin", source_id="test",
            target_kind="plugin_config",
            changes={
                "multi_host.targets": [duplicate_route, new_route],
                "multi_host.personas": [
                    {"bot_id": "bot-a", "persona_id": "original", "role_id": "legacy-role"},
                    {"bot_id": "bot-a", "persona_id": "third", "role_id": "role-third"},
                ],
            },
            confidence={"multi_host.targets": "high", "multi_host.personas": "high"},
            sources={"multi_host.targets": ("basic_config.target_user_ids",),
                     "multi_host.personas": ("basic_config.plugin_specific_persona_id",)},
        )
        differences, scope_status, edit_tokens = [], [], {}

        prepared = api._prepare_plugin_intent(intent, differences, scope_status, edit_tokens)
        self.assertIsNotNone(prepared, differences)
        written, apply_result = await api._apply_plugin_intent(
            prepared, edit_tokens["plugin_config_state"])

        self.assertIn("multi_host.targets", written)
        self.assertEqual(apply_result, {"saved": True, "started": True})
        self.controller.apply_bindings.assert_awaited_once()
        self.assertEqual(len(self.controller.config["multi_host"]["targets"]), 3)
        self.assertEqual(next(item for item in self.controller.config["multi_host"]["targets"]
                              if item["target_id"] == "first")["participant_id"], "200")
        self.assertEqual(next(item for item in self.controller.config["multi_host"]["personas"]
                              if item["bot_id"] == "bot-a" and item["persona_id"] == "original")["role_id"],
                         "role-a")
        self.assertIn("role-third", {item["role_id"] for item in self.controller.config["multi_host"]["personas"]})
        self.assertIn("preserved_v2", {item["kind"] for item in differences})

    async def test_invalid_runtime_setting_does_not_split_identity_migration_bundle(self):
        import astrbot_host.legacy_api as legacy_api
        from companion_v2.legacy.migration import ConfigIntent

        self.controller.save_plugin_config = lambda candidate: (
            self.controller.config.clear(), self.controller.config.update(candidate))
        api = legacy_api.LegacyMigrationWebAPI(self.controller)
        intent = ConfigIntent(
            scope="plugin_config", group_id="plugin", source_id="test",
            target_kind="plugin_config",
            changes={
                "multi_host.targets": [{"target_id": "v1-private", "platform_id": "qq-main",
                    "account_id": "100", "bot_id": "bot-a", "participant_id": "201"}],
                "multi_host.group_targets": [{"target_id": "v1-group", "platform_id": "qq-main",
                    "account_id": "100", "bot_id": "bot-a", "group_id": "300"}],
                "multi_host.personas": [{"bot_id": "bot-a", "persona_id": "third",
                    "role_id": "role-third"}],
                "runtime.quiet_seconds": -1,
            },
            confidence={"multi_host.targets": "high", "multi_host.group_targets": "high",
                        "multi_host.personas": "high", "runtime.quiet_seconds": "high"},
            sources={"multi_host.targets": ("basic_config.target_user_ids",),
                     "multi_host.group_targets": ("legacy_compat_config.target_group_ids",),
                     "multi_host.personas": ("basic_config.multi_persona_ids",),
                     "runtime.quiet_seconds": ("basic_config.runtime_quiet_seconds",)},
        )
        differences, scope_status, edit_tokens = [], [], {}

        prepared = api._prepare_plugin_intent(intent, differences, scope_status, edit_tokens)

        self.assertIsNotNone(prepared, differences)
        self.assertEqual(prepared.changes["multi_host.targets"][-1]["target_id"], "v1-private")
        self.assertEqual(prepared.changes["multi_host.group_targets"][-1]["target_id"], "v1-group")
        self.assertIn("role-third", {item["role_id"] for item in prepared.changes["multi_host.personas"]})
        self.assertNotIn("runtime.quiet_seconds", prepared.changes)
        self.assertIn(("runtime.quiet_seconds", "invalid_combination"),
                      {(item["field"], item["kind"]) for item in differences})

    async def test_staged_restore_is_applied_before_the_store_opens(self):
        """多目标下必须补上这一步：否则还原永远不生效。"""
        import astrbot_host.multi_controller as multi_controller

        calls = []
        applied = {"applied": True, "reason": "test-restore"}

        def recorder(root, *, installation_id, backup_directory):
            # 记录当时运行实例还没有打开——那正是唯一能安全换文件的时刻。
            calls.append((root, installation_id, backup_directory, self.controller.runtime))
            return dict(applied)

        with patch.object(multi_controller, "apply_staged_restore", recorder):
            initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)

        self.assertEqual(len(calls), 1, "开库路径必须调用一次 apply_staged_restore")
        root, installation_id, backup_directory, runtime_at_call = calls[0]
        self.assertEqual(Path(root), self.controller.profile_root / "runtime")
        self.assertEqual(installation_id, self.controller.settings.installation_id)
        self.assertEqual(Path(backup_directory), Path(root) / "backups")
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
        self.assertNotIn("mode", data)
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
            self.assertEqual(target.installation_id, session.profile.target.scope.installation_id)

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


class HostConfigDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    """V1 的插件配置在宿主配置目录里，不在 V1 数据根里。

    真实安装中 V1 从不导出配置转储，迁移必须直接读宿主按
    ``<插件目录名>_config.json`` 保存的那份（star_manager 的命名约定，位于 AstrBot
    数据目录的 config 子目录）。没有这条读取，「天气」这条唯一的自动转换在任何
    真实机器上都会报「未发现」。沙盒里按 AstrBot 的标准布局搭一层：
    ``<tmp>/astrbot/{config,plugin_data/<v2 数据根>}``。
    """

    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-legacy-hostcfg-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name) / "astrbot"
        self.data_root = base / "plugin_data" / "astrbot_plugin_private_companion_v2"
        self.data_root.mkdir(parents=True)
        # V1 数据根留空：证明来源的就绪只靠宿主配置文件，不靠任何转储。
        (base / "plugin_data" / "astrbot_plugin_private_companion").mkdir()
        config_dir = base / "config"
        config_dir.mkdir()
        self.host_config_path = config_dir / "astrbot_plugin_private_companion_config.json"
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider, NS, NS,
                                           support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(
            self.native, support.host_config(), self.data_root,
            native_types=types, now=lambda: support.NOW)
        self.native.persona_manager.get_personas = lambda: [self.native.persona]
        self.controller.save_plugin_config = self._save_plugin_config
        self.addAsyncCleanup(self.controller.terminate)

    def _save_plugin_config(self, candidate):
        self.controller.config.clear()
        self.controller.config.update(candidate)

    def _write_host_config(self, **overrides):
        config = v1_weather_config()
        config["basic_config"] = {"reply_style_prompt": "V1 的回复表达配置"}
        config["reactive_poke_config"] = {
            "enable_reactive_poke": True,
            "reactive_poke_trigger_probability": 0.25,
            "reactive_poke_back_probability": 0.4,
            "reactive_poke_normal_replies": ["V1 戳一戳回复"],
        }
        config.update(overrides)
        self.host_config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    async def _plan(self, *, configuration_scope=None):
        self.controller.register_routes()
        (await self.controller.initialize_profile()).unwrap()
        caller = RouteCaller(self.native, __import__("astrbot_host.legacy_api", fromlist=["request"]))
        query = ({"configuration_scope": configuration_scope}
                 if configuration_scope is not None else None)
        planned = await caller.call(LEGACY_PREFIX + "/plan", query=query)
        self.assertEqual(planned["status"], "ok", planned)
        return planned["data"], caller

    async def test_absent_without_the_host_config_file(self):
        plan, _ = await self._plan()
        ready = [item["source_id"] for item in plan["findings"] if item["state"] == "ready"]
        self.assertEqual(ready, [], "没有宿主配置文件也没有转储时，host-config 来源必须报未发现")

    async def test_host_config_file_makes_the_source_ready_and_applies(self):
        self._write_host_config()
        plan, caller = await self._plan()
        ready = [item["source_id"] for item in plan["findings"] if item["state"] == "ready"]
        self.assertIn("private.host_configuration", ready)
        self.assertGreater(plan["change_count"], 0, "试算要产出可写入的天气设置")
        presentation = next(item for item in plan["intents"]
                            if item["group_id"] == "conversation.presentation")
        self.assertEqual(presentation["values"]["style_prompt"], "V1 的回复表达配置")
        self.assertEqual(presentation["confidence"]["style_prompt"], "high")

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertGreater(applied["data"]["written_count"], 0)
        self.assertEqual(applied["data"]["errors"], [])
        self.assertTrue(applied["data"]["restart_required"])
        self.assertEqual(self.controller.config["poke"], {
            "enabled": True,
            "trigger_probability": 0.25,
            "back_probability": 0.4,
            "replies": ["V1 戳一戳回复"],
        })

    def test_plugin_config_candidate_falls_back_for_noncopyable_runtime_mapping(self):
        import astrbot_host.legacy_api as legacy_api

        class RuntimeConfig(dict):
            def __deepcopy__(self, memo):
                raise TypeError("runtime mapping cannot be copied")

        weather = {"provider": "auto", "api_host": ""}
        untouched = object()
        config = RuntimeConfig(weather=weather, untouched=untouched)
        candidate = legacy_api.LegacyMigrationWebAPI._plugin_config_candidate(
            config, {"weather.provider": "qweather", "weather.api_host": "api.qweatherapi.com"},
        )

        self.assertEqual(candidate["weather"], {
            "provider": "qweather", "api_host": "api.qweatherapi.com",
        })
        self.assertEqual(weather, {"provider": "auto", "api_host": ""})
        self.assertIs(candidate["untouched"], untouched)

    async def test_qweather_credentials_apply_through_redacted_host_settings(self):
        host = "api.qweatherapi.com"
        credential = "a" * 32
        self._write_host_config(
            reactive_poke_config={},
            weather_config={
                "weather_source": "qweather",
                "weather_api_host": host,
                "weather_token": credential,
                "weather_city": "杭州",
                "weather_lat": 30.25,
                "weather_lon": 120.16,
                "enable_weather_context": True,
                "enable_weather_alerts": False,
            },
        )

        plan, caller = await self._plan()
        weather_intent = next(item for item in plan["intents"]
                              if item["target_kind"] == "weather_host_settings")
        self.assertEqual(set(weather_intent["fields"]), {"api_host", "credential", "provider"})
        self.assertEqual(weather_intent["values"]["api_host"], "（已配置，值不在此显示）")
        self.assertEqual(weather_intent["values"]["credential"], "（已配置，值不在此显示）")
        serialized_plan = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn(host, serialized_plan)
        self.assertNotIn(credential, serialized_plan)
        self.assertNotIn("weather_api_host", {
            item.get("field") for item in plan["differences"]
        })

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertIn("weather.api_host", applied["data"]["written"])
        self.assertIn("weather.credential", applied["data"]["written"])
        self.assertNotIn(host, json.dumps(applied, ensure_ascii=False))
        self.assertNotIn(credential, json.dumps(applied, ensure_ascii=False))
        weather = self.controller.config["weather"]
        self.assertEqual(weather["provider"], "qweather")
        self.assertEqual(weather["api_host"], host)
        self.assertEqual(weather["credential"], credential)
        self.assertEqual(self.controller.session.application.calendar_planning.weather_port.provider,
                         "qweather")

    async def test_weather_bundle_isolated_from_an_unrelated_invalid_plugin_setting(self):
        import astrbot_host.legacy_api as legacy_api
        from companion_v2.legacy.migration import ConfigIntent, MigrationPlan

        (await self.controller.initialize_profile()).unwrap()
        api = legacy_api.LegacyMigrationWebAPI(self.controller)
        host = "api.qweatherapi.com"
        credential = "b" * 32
        intent = ConfigIntent(
            scope="plugin_config", group_id="plugin", source_id="test", target_kind="plugin_config",
            changes={"weather.provider": "qweather", "weather.api_host": host,
                     "weather.credential": credential, "runtime.quiet_seconds": -1},
        )

        request = Request({"type": "http", "method": "GET", "path": LEGACY_PREFIX + "/plan",
                           "headers": [], "query_string": b""})
        with bind_request_context(PluginRequest(request, username="admin")):
            intents, differences, scope_status, edit_tokens = api._prepare_intents(
                self.controller.session, MigrationPlan(v1_root="test", intents=(intent,)),
            )

        self.assertEqual([item.target_kind for item in intents], ["weather_host_settings"])
        documents = api._intent_documents(intents)
        encoded = json.dumps(documents, ensure_ascii=False)
        self.assertNotIn(host, encoded)
        self.assertNotIn(credential, encoded)
        self.assertIn(("runtime.quiet_seconds", "invalid_combination"),
                      {(item["field"], item["kind"]) for item in differences})
        self.assertIn("weather_host_settings", edit_tokens)

    async def test_proactive_scope_only_plans_and_applies_message_and_weather_settings(self):
        self._write_host_config(private_followup_config={
            "idle_minutes": 12,
            "min_interval_minutes": 45,
        })

        plan, caller = await self._plan(configuration_scope="proactive")

        self.assertEqual(plan["configuration_scope"], "proactive")
        fields = {
            f"{intent['scope']}.{field}"
            for intent in plan["intents"]
            for field in intent["fields"]
        }
        allowed = {
            "proactive.contact.*",
            "role.state.planning_weather_enabled",
            "role.state.planning_weather_location",
            "role.state.planning_weather_max_age_minutes",
        }
        self.assertTrue(any(field.startswith("proactive.contact.") for field in fields))
        self.assertTrue({
            "role.state.planning_weather_enabled",
            "role.state.planning_weather_location",
            "role.state.planning_weather_max_age_minutes",
        }.issubset(fields))
        self.assertTrue(all(field.startswith("proactive.contact.") or field in allowed for field in fields))
        self.assertTrue(all(intent["target_kind"] == "configuration_registry" for intent in plan["intents"]))
        self.assertNotIn("conversation.presentation", {intent["scope"] for intent in plan["intents"]})
        self.assertNotIn("plugin_config", {intent["target_kind"] for intent in plan["intents"]})
        self.assertNotIn("semantic_config", {intent["target_kind"] for intent in plan["intents"]})

        wrong_scope = await caller.call(LEGACY_PREFIX + "/apply", payload={
            "plan_token": plan["plan_token"],
        })
        self.assertEqual(wrong_scope["status"], "error")
        self.assertEqual(wrong_scope["data"]["code"], "legacy_plan_stale")

        applied = await caller.call(LEGACY_PREFIX + "/apply", payload={
            "plan_token": plan["plan_token"],
            "configuration_scope": "proactive",
        })
        self.assertEqual(applied["status"], "ok", applied)
        self.assertEqual(applied["data"]["configuration_scope"], "proactive")
        self.assertGreater(applied["data"]["written_count"], 0)
        self.assertEqual(applied["data"]["errors"], [])
        self.assertFalse(applied["data"]["restart_required"])
        self.assertNotIn("poke", self.controller.config)

    async def test_account_targets_and_persona_are_previewed_and_applied_without_mode_switch(self):
        self._write_host_config(
            basic_config={
                "bot_scope_mode": "all",
                "bot_scope_ids": [],
                "target_user_ids": ["200"],
                "plugin_specific_persona_id": "original",
                "enable_multi_persona_mode": False,
                "multi_persona_ids": [],
            },
            group_observation_config={
                "enable_group_companion": False,
                "group_access_mode": "whitelist",
                "group_whitelist_ids": [],
            },
        )

        plan, caller = await self._plan()
        plugin = next(item for item in plan["intents"] if item["target_kind"] == "plugin_config")
        targets = plugin["values"]["multi_host.targets"]
        personas = plugin["values"]["multi_host.personas"]
        self.assertEqual({item["account_id"] for item in targets}, {"100", "101"})
        self.assertEqual({item["participant_id"] for item in targets}, {"200"})
        self.assertEqual({item["persona_id"] for item in personas}, {"original"})
        self.assertNotIn("multi_host.enabled", plugin["values"])
        self.assertIn("mode_preserved", {item["kind"] for item in plan["differences"]})

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertEqual(self.controller.config.get("multi_host", {}).get("enabled", False), False)
        self.assertEqual(len(self.controller.config["multi_host"]["targets"]), 2)
        self.assertEqual(len(self.controller.config["multi_host"]["personas"]), 2)

    async def test_account_inventory_change_expires_the_migration_plan(self):
        self._write_host_config(
            basic_config={"bot_scope_mode": "all", "bot_scope_ids": [], "target_user_ids": ["200"],
                          "plugin_specific_persona_id": "original"},
        )
        plan, caller = await self._plan()
        self.native.platform.client._wsr_api_clients["102"] = object()

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "error")
        self.assertEqual(applied["data"]["code"], "legacy_plan_stale", applied)

    async def test_semantic_settings_are_previewed_and_applied(self):
        self._write_host_config(
            experimental_motivation_config={
                "reaction_expression_trigger_probability": 0.73,
                "reaction_expression_cooldown_seconds": 240,
            },
            relay_bridge_config={"group_slang_summary_minutes": 20},
        )
        plan, caller = await self._plan()

        semantic = next(item for item in plan["intents"]
                        if item["target_kind"] == "semantic_config")
        self.assertEqual(semantic["values"], {
            "reactions_trigger_probability": 0.73,
            "reactions_cooldown_seconds": 240,
            "learning_interval_seconds": 1200,
        })
        self.assertTrue(next(item for item in plan["scope_status"]
                             if item["scope"] == "semantic_catalog")["available"])

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertIn("semantic.reactions_trigger_probability", applied["data"]["written"])
        snapshot = self.controller.session.application.semantics.store.configuration_snapshot()
        self.assertEqual(snapshot["values"]["reactions_trigger_probability"], 0.73)
        self.assertEqual(snapshot["values"]["reactions_cooldown_seconds"], 240)
        self.assertEqual(snapshot["values"]["learning_interval_seconds"], 1200)
        self.assertTrue({"reactions_trigger_probability", "reactions_cooldown_seconds",
                         "learning_interval_seconds"}.issubset(snapshot["explicit"]))

    async def test_semantic_revision_change_expires_the_preview(self):
        self._write_host_config(experimental_motivation_config={
            "reaction_expression_trigger_probability": 0.73,
        })
        plan, caller = await self._plan()
        semantics = self.controller.session.application.semantics
        snapshot = semantics.store.configuration_snapshot()
        semantics.store.configure({"slang_enabled": False}, snapshot["revision"])

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "error", applied)
        self.assertEqual(applied["data"]["code"], "legacy_plan_stale", applied)

    async def test_semantic_preview_preserves_an_existing_v2_value(self):
        self._write_host_config(experimental_motivation_config={
            "reaction_expression_trigger_probability": 0.73,
        })
        _, caller = await self._plan()
        semantics = self.controller.session.application.semantics
        snapshot = semantics.store.configuration_snapshot()
        semantics.store.configure({"reactions_trigger_probability": 0.25}, snapshot["revision"])

        plan = await caller.call(LEGACY_PREFIX + "/plan")

        self.assertEqual(plan["status"], "ok", plan)
        self.assertFalse(any(item["target_kind"] == "semantic_config"
                             for item in plan["data"]["intents"]))
        difference = next(item for item in plan["data"]["differences"]
                          if item["field"] == "semantic.reactions_trigger_probability")
        self.assertEqual(difference["kind"], "preserved_v2")
        self.assertEqual(difference["after"], "0.25")

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["data"]["plan_token"]})

        self.assertEqual(applied["status"], "ok", applied)
        self.assertNotIn("semantic.reactions_trigger_probability", applied["data"]["written"])
        self.assertEqual(semantics.store.settings()["reactions_trigger_probability"], 0.25)

    async def test_plan_token_expires_when_the_host_config_changes(self):
        """指纹必须覆盖宿主配置文件：它在试算与执行之间变了，执行就要被拒。"""
        self._write_host_config()
        plan, caller = await self._plan()
        self._write_host_config(weather_refresh_minutes=119)

        applied = await caller.call(LEGACY_PREFIX + "/apply",
                                    payload={"plan_token": plan["plan_token"]})

        self.assertEqual(applied["status"], "error", applied)
        self.assertEqual(applied["data"]["code"], "legacy_plan_stale", applied)

    async def test_plan_token_expires_when_config_dump_changes_without_stat_change(self):
        self.controller.register_routes()
        (await self.controller.initialize_profile()).unwrap()
        caller = RouteCaller(self.native, __import__("astrbot_host.legacy_api", fromlist=["request"]))
        selected_root = v1_root(self.data_root.parent / "alternate-dump")
        planned = await caller.call(LEGACY_PREFIX + "/plan", query={"v1_root": str(selected_root)})
        self.assertEqual(planned["status"], "ok", planned)

        config_path = selected_root / "companion_config.json"
        original = config_path.read_text(encoding="utf-8")
        original_stat = config_path.stat()
        updated = original.replace("杭州", "合肥", 1)
        self.assertEqual(len(updated.encode("utf-8")), original_stat.st_size)
        config_path.write_text(updated, encoding="utf-8")
        os.utime(config_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertEqual(config_path.stat().st_mtime_ns, original_stat.st_mtime_ns)

        applied = await caller.call(LEGACY_PREFIX + "/apply", payload={
            "plan_token": planned["data"]["plan_token"], "v1_root": str(selected_root)})

        self.assertEqual(applied["status"], "error")
        self.assertEqual(applied["data"]["code"], "legacy_plan_stale", applied)

    async def test_explicit_v1_directory_is_bound_to_the_plan_and_apply(self):
        self._write_host_config()
        self.controller.register_routes()
        (await self.controller.initialize_profile()).unwrap()
        caller = RouteCaller(self.native, __import__("astrbot_host.legacy_api", fromlist=["request"]))
        selected_root = v1_root(self.data_root.parent / "alternate")

        discovered = await caller.call(LEGACY_PREFIX, query={"v1_root": str(selected_root)})
        planned = await caller.call(LEGACY_PREFIX + "/plan", query={"v1_root": str(selected_root)})

        self.assertEqual(discovered["status"], "ok", discovered)
        self.assertEqual(discovered["data"]["v1_root"], str(selected_root))
        self.assertEqual(planned["status"], "ok", planned)
        self.assertEqual(planned["data"]["v1_root"], str(selected_root))
        applied = await caller.call(LEGACY_PREFIX + "/apply", payload={
            "plan_token": planned["data"]["plan_token"], "v1_root": str(selected_root)})
        self.assertEqual(applied["status"], "ok", applied)
        self.assertEqual(applied["data"]["v1_root"], str(selected_root))
