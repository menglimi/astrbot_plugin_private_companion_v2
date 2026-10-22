from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch

from astrbot_host.legacy_config import V1_HOST_CONFIG_NAME
from astrbot_host.persona_workshop_api import PREFIX
from companion_v2.role_profile.configuration import (
    GROUP as ROLE_PROFILE_GROUP,
    RoleProfileConfigurationOwner,
    configuration_fields as role_profile_fields,
    target_for as role_profile_target_for,
)
from tests import test_astrbot_staging_host as support
from companion_v2.role_profile.migration import (
    RoleProfileMigrationError,
    map_persona_role_profile,
    map_v1_world_knowledge_role_profile,
)


class RoleProfileMigrationTests(unittest.TestCase):
    def test_maps_only_explicit_role_sections_and_excludes_user_relationship(self):
        source = """人格前置文字不参与迁移。
<Role_Profile>
**姓名**：澄溪
**基本信息**：年龄：二十岁
性别：女
**外貌特征**：深色长发。
**特殊设定**：会修复旧式航海仪器。
**性格特质**：慢热。
**底色与气质**：安静而有耐心。
**内在驱动**：希望保护灯塔。
**外显表现**：遇事会先确认安全。
**亲疏变化**：熟悉后会开玩笑。
**压力与冲突**：压力大时先沉默。
**矛盾感**：谨慎又向往冒险。
**兴趣爱好**：收集旧海图。
**厌恶事物**：损坏航海记录。
**口头禅**：潮声会记得。
**社会关系**：与灯塔守望者保持联系。
用户（仅供关系设定）：绝不迁移这段私人内容。
</Role_Profile>
人格后置文字也不参与迁移。"""

        result = map_persona_role_profile(source)

        self.assertEqual(result["fields"]["name"], "澄溪")
        self.assertIn("年龄：二十岁", result["fields"]["identity"])
        self.assertEqual(result["fields"]["appearance"], "深色长发。")
        self.assertIn("底色与气质：安静而有耐心。", result["fields"]["personality"])
        self.assertEqual(result["fields"]["motivations"], "希望保护灯塔。")
        self.assertEqual(result["fields"]["reaction_patterns"], "外显表现：遇事会先确认安全。\n压力与冲突：压力大时先沉默。")
        self.assertEqual(result["fields"]["social_distance"], "熟悉后会开玩笑。")
        self.assertEqual(result["fields"]["hobbies"], "收集旧海图。")
        self.assertIn("厌恶事物：损坏航海记录。", result["fields"]["character_extra"])
        self.assertEqual(result["fields"]["signature_phrases"], "潮声会记得。")
        self.assertEqual(result["fields"]["network"], "与灯塔守望者保持联系。")
        self.assertEqual(result["excluded_relationship_sections"], 1)
        self.assertNotIn("仅供关系设定", repr(result))
        self.assertNotIn("人格前置文字", repr(result))

    def test_rejects_missing_ambiguous_and_unsupported_role_blocks(self):
        with self.assertRaisesRegex(RoleProfileMigrationError, "missing_or_ambiguous"):
            map_persona_role_profile("没有档案区块")
        with self.assertRaisesRegex(RoleProfileMigrationError, "missing_or_ambiguous"):
            map_persona_role_profile("<Role_Profile>一</Role_Profile><Role_Profile>二</Role_Profile>")
        with self.assertRaisesRegex(RoleProfileMigrationError, "no_supported_fields"):
            map_persona_role_profile("<Role_Profile>用户：只属于关系的资料</Role_Profile>")

    def test_over_limit_values_are_reported_and_never_truncated(self):
        result = map_persona_role_profile(
            "<Role_Profile>**姓名**：" + "名" * 81 + "</Role_Profile>")

        self.assertEqual(result["fields"], {})
        self.assertEqual(result["rejected_fields"], ["name"])

    def test_maps_v1_world_knowledge_labels_to_individual_role_fields(self):
        source = """姓名：澄溪
种族：海岛人
生日：每年冬至
年龄：20
性别：女
识别点：常戴星星发饰。
发型发色：蓝紫色短发。
瞳色：紫金色眼睛。
服饰风格：蓝紫色日常服饰。
职业/身份：高一学生。
性格描述：安静认真，熟悉后会俏皮。
核心欲望/目标：过好校园日常。
爱好：星星和小猫。
禁忌：不要把日程写成任务清单。
关键设定：拥有名为星律的能力。
其他补充信息：工作日需要上学。
用户资料：这段不能迁入。
所处世界：现代校园世界。
"""

        result = map_v1_world_knowledge_role_profile(source, "图像线索")

        self.assertEqual(result["fields"]["name"], "澄溪")
        self.assertEqual(result["fields"]["species"], "海岛人")
        self.assertEqual(result["fields"]["birthday"], "每年冬至")
        self.assertEqual(result["fields"]["age"], "20")
        self.assertEqual(result["fields"]["appearance_points"], "常戴星星发饰。")
        self.assertEqual(result["fields"]["hair"], "蓝紫色短发。")
        self.assertEqual(result["fields"]["eyes"], "紫金色眼睛。")
        self.assertEqual(result["fields"]["occupation"], "高一学生。")
        self.assertEqual(result["fields"]["taboos"], "不要把日程写成任务清单。")
        self.assertEqual(result["fields"]["key_lore"], "拥有名为星律的能力。")
        self.assertEqual(result["fields"]["image_identity_hint"], "图像线索")
        self.assertEqual(result["excluded_relationship_sections"], 2)
        self.assertNotIn("这段不能迁入", repr(result))
        self.assertNotIn("现代校园世界", repr(result))

    def test_v1_over_limit_values_are_rejected_without_truncation(self):
        result = map_v1_world_knowledge_role_profile("姓名：" + "名" * 81)

        self.assertEqual(result["fields"], {})
        self.assertEqual(result["rejected_fields"], ["name"])

    def test_schedule_in_other_information_maps_to_daily_habits(self):
        source = "其他补充信息：周一到周五需要上学，早上九点起床，下午五点放学，晚上十二点睡觉。"

        result = map_v1_world_knowledge_role_profile(source)

        self.assertEqual(result["fields"]["daily_habits"], source.split("：", 1)[1])
        self.assertNotIn("character_extra", result["fields"])


class RoleProfileMigrationAPITests(unittest.IsolatedAsyncioTestCase):
    PERSONA = """<Role_Profile>
**姓名**：澄溪
**基本信息**：年龄：二十岁
**外貌特征**：深色长发。
**性格特质**：慢热。
**底色与气质**：安静而有耐心。
**内在驱动**：希望保护灯塔。
**外显表现**：遇事先确认安全。
**亲疏变化**：熟悉后会开玩笑。
**兴趣爱好**：收集旧海图。
用户（仅限关系资料）：不能迁入的私密关系设定。
</Role_Profile>"""
    V1_ROLE_PROFILE = """姓名：澄溪
种族：海岛人
生日：每年冬至
年龄：20
性别：女
识别点：常戴星星发饰。
发型发色：蓝紫色短发。
瞳色：紫金色眼睛。
服饰风格：蓝紫色日常服饰。
职业/身份：学生
性格描述：安静认真。
核心欲望/目标：过好校园日常。
爱好：星星和小猫。
禁忌：不要把日程写成任务清单。
关键设定：拥有星律能力。
其他补充信息：工作日需要上学。
用户资料：关系内容不得迁入。
"""

    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-role-profile-migration-")
        self.addCleanup(self.temporary.cleanup)
        self.data_root = Path(self.temporary.name) / "data" / "plugin_data" / "companion-v2"
        self.data_root.mkdir(parents=True)
        self.v1_config_path = self.data_root.parent.parent / "config" / V1_HOST_CONFIG_NAME
        self.v1_config_path.parent.mkdir(parents=True)
        self.v1_config = {
            "enable_multi_persona_mode": False,
            "plugin_specific_persona_id": "original",
            "schedule_persona_prompt": self.V1_ROLE_PROFILE,
            "private_image_self_recognition_hint": "仅用于识别角色图像。",
        }
        self.write_v1_config()
        self.native = support.WebContext()
        self.native.persona = {"name": "original", "prompt": self.PERSONA}
        self.native.persona_manager.personas_v3 = [self.native.persona]
        self.native.persona_manager.get_persona_v3_by_id = lambda persona_id: next(
            (item for item in self.native.persona_manager.personas_v3 if item.get("name") == persona_id), None)
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                          NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(
            self.native, support.host_config(), self.data_root, native_types=types,
            now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)

    def write_v1_config(self):
        self.v1_config_path.write_text(json.dumps(self.v1_config, ensure_ascii=False), encoding="utf-8")

    async def initialize(self):
        result = await self.controller.initialize_profile()
        self.assertTrue(result.is_success, result.failure)
        started = await self.controller.start()
        self.assertTrue(started.is_success, started.failure)
        self.controller.register_routes()
        self.routes = {path: handler for path, handler, _, _ in self.native.registered_web_apis}

    async def post_route(self, route, body, *, username="admin"):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        async def reader():
            return payload

        with patch("astrbot_host.persona_workshop_api.request",
                   NS(username=username, query={}, body=reader)):
            return await self.routes[PREFIX + route]()

    async def migration_plan(self):
        return await self.post_route("/profile-migration-plan", {"persona_id": "original"})

    async def test_plan_and_apply_use_the_configuration_service_without_model_calls(self):
        await self.initialize()
        plan_response = await self.migration_plan()

        self.assertEqual(plan_response["status"], "ok", plan_response)
        plan = plan_response["data"]
        self.assertGreater(plan["counts"]["to_import"], 0)
        self.assertEqual(plan["counts"]["excluded_relationship_sections"], 1)
        self.assertEqual(plan["source"]["kind"], "v1_world_knowledge")
        self.assertEqual(plan["source"]["name"], "V1 世界知识 / 角色设定")
        self.assertNotIn("不能迁入的私密关系设定", json.dumps(plan, ensure_ascii=False))
        self.assertNotIn("关系内容不得迁入", json.dumps(plan, ensure_ascii=False))
        self.assertEqual(self.native.provider.client.state.calls, [])

        body = {"persona_id": "original", "plan_token": plan["plan_token"],
                "edit_token": plan["edit_token"], "changes": plan["changes"]}
        saved = await self.post_route("/profile-migration-apply", body)
        self.assertEqual(saved["status"], "ok", saved)
        self.assertEqual(saved["data"]["imported_count"], plan["counts"]["to_import"])

        target = role_profile_target_for(self.controller.session.profile.target)
        current = RoleProfileConfigurationOwner(self.controller.runtime).read(target, role_profile_fields())
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.name"].value, "澄溪")
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.birthday"].value, "每年冬至")
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.age"].value, "20")
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.occupation"].value, "学生")
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.personality"].value, "安静认真。")
        self.assertEqual(current.fields[f"{ROLE_PROFILE_GROUP}.image_identity_hint"].value,
                         "仅用于识别角色图像。")
        self.assertNotIn("不能迁入", current.fields[f"{ROLE_PROFILE_GROUP}.character_extra"].value)
        self.assertNotIn("关系内容不得迁入", current.fields[f"{ROLE_PROFILE_GROUP}.character_extra"].value)

        replay = await self.post_route("/profile-migration-apply", body)
        self.assertEqual(replay["status"], "ok", replay)
        self.assertTrue(replay["data"]["replayed"])

    async def test_relocated_runtime_reads_v1_settings_from_canonical_root(self):
        await self.initialize()
        relocated = Path(self.temporary.name) / "relocated-v2"
        relocated.mkdir(parents=True)
        self.controller.data_root = relocated
        self.controller.default_data_root = self.data_root

        plan = (await self.migration_plan())["data"]

        self.assertEqual(plan["source"]["kind"], "v1_world_knowledge")
        self.assertEqual(plan["source"]["name"], "V1 世界知识 / 角色设定")
        self.assertEqual(plan["changes"]["name"], "澄溪")
        self.assertEqual(plan["changes"]["personality"], "安静认真。")

    async def test_existing_fields_are_preserved_and_target_changes_invalidate_the_plan(self):
        await self.initialize()
        target = role_profile_target_for(self.controller.session.profile.target)
        owner = RoleProfileConfigurationOwner(self.controller.runtime)
        fields = role_profile_fields()
        before = owner.read(target, fields)
        owner.write(target, fields, changes={f"{ROLE_PROFILE_GROUP}.name": "手工名称"}, reset=(),
                     expected_revision=before.revision, observed_at=support.NOW)

        plan_response = await self.migration_plan()
        plan = plan_response["data"]
        self.assertEqual(plan["counts"]["preserved_existing"], 1)
        self.assertNotIn("name", plan["changes"])
        body = {"persona_id": "original", "plan_token": plan["plan_token"],
                "edit_token": plan["edit_token"], "changes": plan["changes"]}
        changed = owner.read(target, fields)
        owner.write(target, fields, changes={f"{ROLE_PROFILE_GROUP}.age": "二十一岁"}, reset=(),
                     expected_revision=changed.revision, observed_at=support.NOW)

        result = await self.post_route("/profile-migration-apply", body)
        self.assertEqual(result["data"]["code"], "configuration_revision_conflict")

    async def test_grouped_v670_configuration_preserves_world_knowledge_source(self):
        self.v1_config = {
            "basic_config": {"enable_multi_persona_mode": False,
                             "plugin_specific_persona_id": "original"},
            "life_schedule_config": {"schedule_persona_prompt": self.V1_ROLE_PROFILE},
            "message_debounce_config": {"private_image_self_recognition_hint": "角色图像线索"},
            "schedule_persona_prompt": "姓名：过时平铺副本",
        }
        self.write_v1_config()
        await self.initialize()
        plan = (await self.migration_plan())["data"]
        self.assertEqual(plan["source"]["kind"], "v1_world_knowledge")
        self.assertEqual(plan["changes"]["name"], "澄溪")
        self.assertEqual(plan["changes"]["image_identity_hint"], "角色图像线索")
        response = await self.post_route("/profile-migration-apply", {
            "persona_id": "original", "plan_token": plan["plan_token"],
            "edit_token": plan["edit_token"], "changes": plan["changes"]})
        self.assertEqual(response["status"], "ok", response)
        self.v1_config["basic_config"]["plugin_specific_persona_id"] = "other"
        self.write_v1_config()
        mismatch = await self.migration_plan()
        self.assertEqual(mismatch["data"]["code"], "role_profile_migration_source_persona_mismatch")

    async def test_dotted_v670_exports_are_supported(self):
        self.v1_config = {
            "basic_config.enable_multi_persona_mode": False,
            "basic_config.plugin_specific_persona_id": "original",
            "life_schedule_config.schedule_persona_prompt": self.V1_ROLE_PROFILE,
        }
        self.write_v1_config()
        await self.initialize()
        result = await self.migration_plan()
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["source"]["kind"], "v1_world_knowledge")
        self.assertEqual(result["data"]["changes"]["name"], "澄溪")

    async def test_source_change_after_preview_is_rejected(self):
        await self.initialize()
        plan = (await self.migration_plan())["data"]
        self.v1_config["schedule_persona_prompt"] = self.V1_ROLE_PROFILE.replace("澄溪", "澄溪二")
        self.write_v1_config()
        body = {"persona_id": "original", "plan_token": plan["plan_token"],
                "edit_token": plan["edit_token"], "changes": plan["changes"]}

        result = await self.post_route("/profile-migration-apply", body)

        self.assertEqual(result["data"]["code"], "role_profile_migration_source_changed")

    async def test_v1_profile_persona_mismatch_is_not_replaced_with_astrbot_persona(self):
        await self.initialize()
        self.v1_config["plugin_specific_persona_id"] = "another-persona"
        self.write_v1_config()

        result = await self.migration_plan()

        self.assertEqual(result["data"]["code"], "role_profile_migration_source_persona_mismatch")

    async def test_native_persona_is_a_fallback_when_v1_role_profile_is_empty(self):
        await self.initialize()
        self.v1_config["schedule_persona_prompt"] = ""
        self.v1_config["private_image_self_recognition_hint"] = ""
        self.write_v1_config()

        result = await self.migration_plan()

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["source"]["kind"], "astrbot_persona")

    async def test_migration_routes_require_dashboard_identity(self):
        await self.initialize()
        response = await self.post_route("/profile-migration-plan", {"persona_id": "original"}, username="")
        self.assertEqual(response["data"]["code"], "dashboard_identity_required")


if __name__ == "__main__":
    unittest.main()
