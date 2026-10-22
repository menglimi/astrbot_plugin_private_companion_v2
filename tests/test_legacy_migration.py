"""V1 数据迁移的发现与试算。

测的是 ``companion_v2.legacy.migration``：它只读、不写、不做无根据的转换。
「能迁 / 不能迁 / 迁了会改成什么」这三件事必须在界面点执行之前就确定下来，
所以这里的断言全部对着那个契约。

用真的临时目录而不是 mock：迁移的难点恰恰在文件系统上（路径在不在、
SQLite 能不能只读打开、JSON 坏没坏），把这一层 mock 掉就测不到真问题了。
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import tempfile
import unittest

from companion_v2.legacy.migration import (
    GROUP_OF_SCOPE,
    HANDLERS,
    LegacyMigration,
    MigrationState,
    plugin_data_path,
    read_json,
    sqlite_tables,
)


def v1_configuration(**overrides) -> dict:
    """一份最小可用的 V1 天气配置。"""
    base = {
        "weather_city": "杭州",
        "weather_lat": 30.25,
        "weather_lon": 120.16,
        "enable_weather_context": True,
        "weather_refresh_minutes": 90,
        "enable_weather_alerts": False,
    }
    base.update(overrides)
    return base


class LegacyMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)

    def write(self, name: str, payload) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (bytes, bytearray)):
            path.write_bytes(payload)
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def database(self, name: str, *, tables: tuple[str, ...] = ("facts",)) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            for table in tables:
                connection.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()

    def plan(self):
        planned = LegacyMigration(v1_root=self.root).plan()
        self.assertTrue(planned.is_success, planned.failure)
        return planned.unwrap()


class DiscoveryTests(LegacyMigrationTestCase):
    def test_missing_root_is_reported_not_created(self) -> None:
        absent = self.root / "not-here"
        result = LegacyMigration(v1_root=absent).discover()

        self.assertFalse(result.is_success)
        self.assertEqual(result.failure.code, "legacy_root_missing")
        # 发现阶段绝不能创建目录：那会把「探测」变成一次对 V1 的改动。
        self.assertFalse(absent.exists())

    def test_root_that_is_a_file_is_rejected(self) -> None:
        path = self.root / "a-file"
        path.write_text("x", encoding="utf-8")
        result = LegacyMigration(v1_root=path).discover()

        self.assertFalse(result.is_success)
        self.assertEqual(result.failure.code, "legacy_root_invalid")

    def test_absent_sources_are_reported_as_absent(self) -> None:
        findings = {item.source_id: item for item in self.plan().findings}

        # 目录里声明了九条来源，一份空目录应当让它们全部落进 absent——
        # 而不是被当成「没写转换器」。
        self.assertGreaterEqual(len(findings), 8)
        self.assertTrue(all(item.state == MigrationState.ABSENT.value
                            for item in findings.values()))

    def test_every_declared_source_appears_in_the_plan(self) -> None:
        from companion_v2.legacy.catalog import LEGACY_COMPATIBILITY_CATALOG

        reported = {item.source_id for item in self.plan().findings}
        self.assertEqual(reported,
                         {entry.source_id for entry in LEGACY_COMPATIBILITY_CATALOG.entries})

    def test_separate_memory_database_is_not_assumed_to_exist_under_v1_root(self) -> None:
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["memory.timeline_and_governance"].state,
                         MigrationState.ABSENT.value)

    def test_global_astrbot_plugin_data_wins_over_stale_embedded_copy(self) -> None:
        v1_root = self.root / "data" / "plugins" / "astrbot_plugin_private_companion"
        v1_root.mkdir(parents=True)
        global_db = self.root / "data" / "plugin_data" / "astrbot_plugin_memory_companion" / "memory_companion.db"
        global_db.parent.mkdir(parents=True)
        connection = sqlite3.connect(global_db)
        connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE timeline (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO memories VALUES ('active-source')")
        connection.commit()
        connection.close()

        embedded_db = v1_root / "data" / "plugin_data" / "astrbot_plugin_memory_companion" / "memory_companion.db"
        embedded_db.parent.mkdir(parents=True)
        embedded_db.write_bytes(b"stale copy")

        self.assertEqual(plugin_data_path(v1_root,
            "astrbot_plugin_memory_companion/memory_companion.db"), global_db)
        finding = {item.source_id: item for item in
                   LegacyMigration(v1_root=v1_root).discover().unwrap()}[
                       "memory.timeline_and_governance"]
        self.assertEqual(finding.state, MigrationState.DATA_READY.value)
        self.assertEqual(finding.byte_size, global_db.stat().st_size)

    def test_external_sources_name_their_owner(self) -> None:
        self.write("image_generation_state.json", {})
        findings = {item.source_id: item for item in self.plan().findings}

        marker = findings["image.generation_state"]
        self.assertEqual(marker.state, MigrationState.EXTERNAL.value)
        self.assertIn("image_companion", marker.owner)

    def test_unreadable_sqlite_is_not_reported_as_ready(self) -> None:
        self.write("framework_work/work.db", b"definitely not sqlite")
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["private.work_and_delivery"].state,
                         MigrationState.UNREADABLE.value)

    def test_unreadable_json_is_not_reported_as_ready(self) -> None:
        (self.root / "companions.json").write_text("{not json", encoding="utf-8")
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["private.core_profiles"].state,
                         MigrationState.UNREADABLE.value)

    def test_profile_data_source_is_reported_as_importable(self) -> None:
        self.write("companions.json", {"roles": []})
        findings = {item.source_id: item for item in self.plan().findings}

        marker = findings["private.core_profiles"]
        self.assertEqual(marker.state, MigrationState.DATA_READY.value)
        self.assertNotIn(marker.source_id, [item.source_id for item in self.plan().migratable])


class ConfigurationDiscoveryTests(LegacyMigrationTestCase):
    """宿主配置段没有文件路径，它的「在不在」靠配置转储判断。"""

    def test_configuration_dump_makes_the_source_ready(self) -> None:
        self.write("companion_config.json", v1_configuration())
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["private.host_configuration"].state,
                         MigrationState.READY.value)

    def test_configuration_source_stays_absent_without_a_dump(self) -> None:
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["private.host_configuration"].state,
                         MigrationState.ABSENT.value)

    def test_nested_weather_group_is_unwrapped(self) -> None:
        # V1 的导出有时把天气包在 weather_config 子对象里，而不是平铺一层。
        self.write("companion_config.json",
                   {"other": 1, "weather_config": v1_configuration(weather_city="上海")})
        plan = self.plan()
        location = next(intent.changes["planning_weather_location"]
                        for intent in plan.intents if "planning_weather_location" in intent.changes)

        self.assertIn("上海", location)

    def test_host_supplied_configuration_wins_over_the_dump(self) -> None:
        # 宿主侧的插件配置是权威的：它能读到时就不看数据根里的转储。
        self.write("companion_config.json", v1_configuration(weather_city="杭州"))
        planned = LegacyMigration(v1_root=self.root,
                                  v1_configuration=v1_configuration(weather_city="成都")).plan()
        self.assertTrue(planned.is_success, planned.failure)
        location = next(intent.changes["planning_weather_location"]
                        for intent in planned.unwrap().intents
                        if "planning_weather_location" in intent.changes)

        self.assertIn("成都", location)

    def test_host_supplied_configuration_alone_makes_the_source_ready(self) -> None:
        # 数据根里什么都没有，但宿主拿得到配置——这条来源依然是「可以迁移」。
        planned = LegacyMigration(v1_root=self.root,
                                  v1_configuration=v1_configuration()).plan()
        findings = {item.source_id: item for item in planned.unwrap().findings}

        self.assertEqual(findings["private.host_configuration"].state,
                         MigrationState.READY.value)


class RealityConfigurationMigrationTests(LegacyMigrationTestCase):
    def v1_reality_configuration(self):
        return {
            "camera": {
                "enabled": True,
                "index": 700,
                "min_interval_seconds": 45,
                "capture_timeout_seconds": 6,
                "analysis_timeout_seconds": 30,
                "proactive_curiosity_enabled": True,
            },
            "audio": {"default_playback_volume": 42},
            "timezone": "Asia/Shanghai",
            "vision_provider_id": "legacy-provider-private",
            "authorized_user_ids": ["legacy-user-private"],
            "home": {"access_token": "legacy-home-secret"},
        }

    def plan(self, configuration=None):
        planned = LegacyMigration(
            v1_root=self.root,
            v1_reality_configuration=configuration or self.v1_reality_configuration(),
        ).plan()
        self.assertTrue(planned.is_success, planned.failure)
        return planned.unwrap()

    def test_reality_configuration_is_a_ready_catalog_source(self):
        findings = {item.source_id: item for item in self.plan().findings}

        self.assertEqual(findings["reality.configuration"].state, MigrationState.READY.value)
        self.assertEqual(findings["reality.device_and_observations"].state,
                         MigrationState.ABSENT.value)

    def test_only_portable_runtime_settings_are_converted_and_private_values_are_redacted(self):
        plan = self.plan()
        intent = next(item for item in plan.intents if item.target_kind == "reality_config")

        self.assertEqual(intent.scope, "reality.settings")
        self.assertEqual(intent.changes, {
            "camera.enabled": True,
            "camera.min_interval_seconds": 45,
            "camera.capture_timeout_seconds": 6,
            "camera.analysis_timeout_seconds": 30,
            "audio.default_playback_volume": 42,
            "timezone": "Asia/Shanghai",
            "vision_provider_id": "legacy-provider-private",
        })
        self.assertTrue(any(item["field"] == "reality.camera.index"
                            and item["kind"] == "device_mapping_required"
                            for item in plan.differences))
        document = json.dumps(plan.document(), ensure_ascii=False)
        for secret in ("legacy-provider-private", "legacy-user-private", "legacy-home-secret"):
            self.assertNotIn(secret, document)

    def test_reality_runtime_state_is_documented_as_retained_without_import(self):
        self.write("plugin_data/astrbot_plugin_reality_companion/reality_companion.json",
                   {"version": 1, "users": {}})
        finding = {item.source_id: item for item in self.plan().findings}[
            "reality.device_and_observations"]

        self.assertEqual(finding.state, MigrationState.DOCUMENTED_SKIP.value)
        self.assertIn("授权", finding.detail)

    def test_reality_source_changes_invalidate_the_migration_context(self):
        first = LegacyMigration(v1_root=self.root,
                                v1_reality_configuration=self.v1_reality_configuration())
        changed = self.v1_reality_configuration()
        changed["camera"]["min_interval_seconds"] = 60
        second = LegacyMigration(v1_root=self.root, v1_reality_configuration=changed)

        self.assertNotEqual(first.configuration_context_fingerprint,
                            second.configuration_context_fingerprint)


class ImageCompanionConfigurationMigrationTests(LegacyMigrationTestCase):
    @staticmethod
    def image_configuration(*, route=True):
        return {
            "enabled": True,
            "comfyui": {
                "base_url": "http://127.0.0.1:8188",
                "api_key": "private-image-key",
                "workflows": [
                    {"name": "text", "workflow": {"secret-node": {"inputs": {}}},
                     "mapping": {"fields": {}, "output_node": "secret-node"}},
                ],
            },
            "preparation": {
                "chat_enabled": True,
                "default_generate_route": "text-route" if route else "missing-route",
                "routes": [{"route_id": "text-route", "backend": "comfyui",
                            "operation": "generate", "workflow_id": "text"}],
            },
        }

    def test_standalone_image_configuration_produces_one_redacted_intent(self):
        planned = LegacyMigration(
            v1_root=self.root, v1_image_configuration=self.image_configuration(),
        ).plan()
        self.assertTrue(planned.is_success, planned.failure)
        plan = planned.unwrap()
        image_intents = [item for item in plan.intents if item.target_kind == "image_output_config"]
        self.assertEqual(len(image_intents), 1)
        self.assertEqual(image_intents[0].source_id, "image.configuration")
        self.assertEqual(image_intents[0].changes["operation_routes"],
                         {"generate": ["comfyui"], "edit": []})
        self.assertTrue(image_intents[0].changes["enabled"])
        self.assertEqual(image_intents[0].changes["legacy_options"]["image_companion_selected_workflows"],
                         {"generate": "text"})
        document = json.dumps(plan.document(), ensure_ascii=False)
        self.assertNotIn("private-image-key", document)
        self.assertNotIn("secret-node", document)
        self.assertIn("workflow_operations", document)

    def test_private_preferences_and_standalone_routes_merge_without_duplicate_write(self):
        planned = LegacyMigration(
            v1_root=self.root,
            v1_configuration={"photo_action_config": {
                "photo_generation_backend": "sdgen",
                "photo_generation_style": "anime",
                "external_image_download_proxy": "http://127.0.0.1:7890",
            }},
            v1_image_configuration=self.image_configuration(),
        ).plan()
        self.assertTrue(planned.is_success, planned.failure)
        intents = planned.unwrap().intents
        image_intents = [item for item in intents if item.target_kind == "image_output_config"]
        self.assertEqual(len(image_intents), 1)
        self.assertTrue(image_intents[0].changes["enabled"])
        self.assertEqual(image_intents[0].changes["network"]["download_proxy"],
                         "http://127.0.0.1:7890")
        self.assertIn("photo_action_config.external_image_download_proxy",
                      image_intents[0].sources["network"])
        self.assertTrue(any(item.scope == "conversation.image_output"
                            and item.changes.get("style") == "anime" for item in intents))

    def test_other_configured_backend_does_not_enable_an_unrouted_default(self):
        raw = self.image_configuration(route=False)
        raw["sd_webui"] = {"base_url": "http://127.0.0.1:7860"}
        planned = LegacyMigration(v1_root=self.root, v1_image_configuration=raw).plan()
        self.assertTrue(planned.is_success, planned.failure)
        self.assertFalse(any(item.changes.get("enabled") is True
                             for item in planned.unwrap().intents
                             if item.target_kind == "image_output_config"))


class ConversionTests(LegacyMigrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("companion_config.json", v1_configuration())

    def intents_by_scope(self, plan):
        return {intent.scope: intent for intent in plan.intents}

    def test_settings_land_in_two_real_configuration_groups(self) -> None:
        plan = self.plan()
        scopes = set(self.intents_by_scope(plan))

        self.assertEqual(scopes, {"role.state", "proactive.contact"})
        # 分组名就是转换器写出的生效范围名：patch 用的键形状是 GROUP + "." + field_id，
        # 所以这里不允许出现「生效范围叫 A、分组叫 B」的映射。
        for scope in scopes:
            self.assertEqual(GROUP_OF_SCOPE[scope], scope)

    def test_weather_source_is_a_global_plugin_configuration_intent(self) -> None:
        planned = LegacyMigration(
            v1_root=self.root,
            v1_configuration={"weather_config": {"weather_source": "qweather"}},
        ).plan()
        self.assertTrue(planned.is_success, planned.failure)

        intent = next(item for item in planned.unwrap().intents
                      if item.target_kind == "plugin_config")
        self.assertEqual(intent.changes["weather.provider"], "qweather")
        self.assertEqual(intent.sources["weather.provider"], ("weather_config.weather_source",))

    def test_semantic_catalog_settings_form_a_separate_migration_intent(self) -> None:
        planned = LegacyMigration(
            v1_root=self.root,
            v1_configuration={
                "experimental_motivation_config": {
                    "reaction_expression_trigger_probability": 0.65,
                },
                "relay_bridge_config": {"group_slang_summary_minutes": 20},
            },
        ).plan()

        self.assertTrue(planned.is_success, planned.failure)
        intent = next(item for item in planned.unwrap().intents
                      if item.target_kind == "semantic_config")
        self.assertEqual(intent.scope, "semantic_catalog")
        self.assertEqual(intent.group_id, "semantic")
        self.assertEqual(intent.changes, {
            "reactions_trigger_probability": 0.65,
            "learning_interval_seconds": 1200,
        })

    def test_every_field_exists_in_the_configuration_registry(self) -> None:
        """转换器产出的每个字段都必须真的注册过。

        写错一个字段名不会在这里报错——配置服务的校验器会拒绝它，而那时用户看到的
        是一句「保存失败」。所以在试算阶段就对着注册表核一遍。
        """
        from companion_v2.proactive.configuration import configuration_fields
        from companion_v2.role_work.state.configuration import configuration_fields as state_fields

        registered = ({field.field_id for field in state_fields()}
                      | {field.field_id for field in configuration_fields()})
        plan = self.plan()

        for intent in plan.intents:
            for field in intent.changes:
                self.assertIn(f"{intent.group_id}.{field}", registered,
                              f"{intent.group_id}.{field} 不在配置注册表里")

    def test_freshness_ceiling_is_narrowed_and_explained(self) -> None:
        self.write("companion_config.json", v1_configuration(weather_refresh_minutes=400))
        plan = self.plan()
        state = self.intents_by_scope(plan)["role.state"]

        self.assertEqual(state.changes["planning_weather_max_age_minutes"], 120)
        explained = [item for item in plan.differences
                     if item["field"] == "role.state.planning_weather_max_age_minutes"]
        self.assertTrue(explained, "被改小的值必须带一条差异说明")
        self.assertEqual(explained[0]["kind"], "narrowed")
        self.assertEqual(explained[0]["before"], "400")
        self.assertEqual(explained[0]["after"], "120")

    def test_freshness_inside_the_ceiling_is_kept(self) -> None:
        self.write("companion_config.json", v1_configuration(weather_refresh_minutes=60))
        state = self.intents_by_scope(self.plan())["role.state"]

        self.assertEqual(state.changes["planning_weather_max_age_minutes"], 60)
        self.assertEqual([item for item in self.plan().differences
                          if "max_age" in item["field"]], [])

    def test_alert_severity_colour_is_translated_and_explained(self) -> None:
        self.write("companion_config.json",
                   v1_configuration(weather_alert_min_severity="orange"))
        plan = self.plan()
        contact = self.intents_by_scope(plan)["proactive.contact"]

        self.assertEqual(contact.changes["official_alert_min_severity"], "severe")
        explained = [item for item in plan.differences if "severity" in item["field"]]
        self.assertEqual(explained[0]["kind"], "renamed")

    def test_explicit_location_is_kept_as_a_document(self) -> None:
        state = self.intents_by_scope(self.plan())["role.state"]
        location = json.loads(state.changes["planning_weather_location"])

        self.assertEqual(location["name"], "杭州")
        self.assertEqual(location["latitude"], 30.25)
        self.assertEqual(location["longitude"], 120.16)

    def test_numeric_location_id_is_refused_with_an_explanation(self) -> None:
        """V1 的 LocationID 是数字串，不能当地名用。

        照抄过去会让界面显示一串数字；直接丢掉又不解释会让用户以为迁漏了。
        转换器应当两者都做：不写地名、并报一条 needs_input。
        """
        self.write("companion_config.json", {"weather_location": "101210101",
                                             "weather_lat": 0, "weather_lon": 0})
        plan = self.plan()
        state = self.intents_by_scope(plan)["role.state"]

        self.assertNotIn("planning_weather_location", state.changes)
        self.assertTrue([item for item in plan.differences
                         if item["field"] == "role.state.planning_weather_location"])
        # 没有地点就不能开观测，否则会留下一个永远无法满足的开关。
        self.assertFalse(state.changes["planning_weather_enabled"])

    def test_plan_writes_nothing(self) -> None:
        before = sorted((child.name, child.stat().st_size) for child in self.root.iterdir())
        self.plan()
        after = sorted((child.name, child.stat().st_size) for child in self.root.iterdir())

        self.assertEqual(before, after)

    def test_plan_is_repeatable_and_stable(self) -> None:
        first, second = self.plan().document(), self.plan().document()

        self.assertEqual(first["changes"] if "changes" in first else first["intents"],
                         second["changes"] if "changes" in second else second["intents"])
        self.assertEqual(first["change_count"], second["change_count"])

    def test_document_is_json_serialisable(self) -> None:
        """计划要能原样发给页面，所以里面不能有 set 或 dataclass。"""
        document = self.plan().document()
        self.assertIsInstance(json.dumps(document, ensure_ascii=False), str)
        self.assertEqual(document["migratable"], ["private.host_configuration"])


class HelperTests(LegacyMigrationTestCase):
    def test_sqlite_tables_refuses_to_create_a_missing_database(self) -> None:
        absent = self.root / "absent.db"

        self.assertIsNone(sqlite_tables(absent))
        # mode=ro 的关键作用：探测不能顺手建出一个空库来。
        self.assertFalse(absent.exists())

    def test_sqlite_tables_lists_a_real_database(self) -> None:
        self.database("real.db", tables=("alpha", "beta"))

        self.assertEqual(sorted(sqlite_tables(self.root / "real.db") or ()),
                         ["alpha", "beta"])

    def test_read_json_returns_none_instead_of_raising(self) -> None:
        broken = self.root / "broken.json"
        broken.write_text("{oops", encoding="utf-8")

        self.assertIsNone(read_json(broken))
        self.assertIsNone(read_json(self.root / "missing.json"))

    def test_read_json_accepts_utf8_bom_configuration_dumps(self) -> None:
        source = self.root / "configuration.json"
        source.write_text('\ufeff{"enabled": true}', encoding="utf-8")

        self.assertEqual(read_json(source), {"enabled": True})

    def test_handlers_only_names_written_converters(self) -> None:
        # 这份集合是「域侧已实现」的代码事实，不代表每项都写配置。
        self.assertEqual(HANDLERS, frozenset({"v2.private-config-converter",
                                              "v2.role-journal-importer",
                                              "v2.role-journal-and-worldbook-importer",
                                              "v2.group-relationship-importer",
                                              "v2.reaction-asset-importer",
                                              "v2.memory-snapshot-archive",
                                              "v2.reality-config-migrator",
                                              "v2.person-private-memory-importer",
                                              "v2.image-config-migrator",
                                              "v2.content-config-migrator",
                                              "v2.memory-config-migrator",
                                              "v2.native-extension-config-migrator"}))


if __name__ == "__main__":
    unittest.main()
