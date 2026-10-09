"""Dashboard routes for the image, reaction and budget groups the cottage edits.

These groups already had owners and consumers; the route is what turns them into
operator-editable settings. The tests pin the two scope shapes (role ceiling vs
conversation window), the per-section edit token, replay safety and the
authorization gate.

主动联系偏好（proactive.contact）是其中最特殊的一个：它是唯一一个四层组
（安装 → 角色 → 关系 → 窗口），两个关系级额度按窗口写入会被所有者拒绝，
所以它的字段契约里没有窗口层。
"""

import json
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as support
from tests.multi_host_support import MultiFixture, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from astrbot_host.controller import AstrBotStagingController
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.role_profile.configuration import FIELD_LIMITS
from types import SimpleNamespace as NS


class Query(dict):
    """Minimal stand-in for the host query object (keys/get/getlist)."""

    def getlist(self, key):
        return [self[key]] if key in self else []


async def call(handler, body=None, *, username="config-admin", query=None):
    """Invoke one configuration handler with the host request patched in."""
    async def read():
        return json.dumps(body, ensure_ascii=False).encode("utf-8")
    with patch("astrbot_host.configuration_api.request",
               NS(username=username, query=Query(query or {}), body=read)):
        return await handler()


class ConfigurationWebAPITests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def routes(self):
        self.controller = self.make_controller(multi_config(delivery_mode="onebot_private"))
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        self.controller.register_routes()
        handlers = {route: handler for route, handler, _, _ in self.native.registered_web_apis}
        def editor(target_id):
            # The editor route lives on the role path; /model/image/config also
            # ends with /config, so the target comes from the route itself.
            return [route for route in handlers
                    if route.split("/")[-1] == "config" and "/model/" not in route
                    and "/targets/" + target_id + "/" in route][0]
        return handlers, editor("first"), editor("second")

    async def test_official_catalogue_and_saved_missing_sources_are_visible(self):
        handlers, first, _ = await self.routes()
        official = NS(list_sources=AsyncMock(return_value=[{
            "id": "kb:kb-1", "type": "knowledge_base", "kb_id": "kb-1", "name": "星河设定",
            "documents": [{"id": "doc:kb-1:doc-1", "name": "角色资料.md"}],
        }]))
        self.native.kb_manager = NS()
        try:
            with patch("astrbot_host.configuration_api.AstrBotKnowledgeSources", return_value=official):
                status = (await call(handlers[first], query={"sections": "knowledge"}))["data"]["sections"]["knowledge"]
                saved = await call(handlers[first + "/configure"], {
                    "section": "knowledge", "operation_key": "official-kb-selection",
                    "edit_token": status["edit_token"],
                    "changes": {"source_ids": "doc:kb-1:doc-1\nkb:missing"},
                }, query={"sections": "knowledge"})
                reread = (await call(handlers[first], query={"sections": "knowledge"}))[
                    "data"]["sections"]["knowledge"]
            self.assertEqual(saved["status"], "ok", saved)
            self.assertNotIn("status", saved["data"])
            status = reread
            self.assertTrue(status["knowledge_sources_available"])
            self.assertEqual(status["knowledge_sources"][0]["documents"][0]["id"], "doc:kb-1:doc-1")
            self.assertEqual(status["knowledge_sources"][-1]["type"], "missing")
            self.assertEqual(status["knowledge_sources"][-1]["id"], "kb:missing")
            official.list_sources.side_effect = RuntimeError("catalogue unavailable")
            with patch("astrbot_host.configuration_api.AstrBotKnowledgeSources", return_value=official):
                unavailable = (await call(handlers[first], query={"sections": "knowledge"}))["data"]["sections"]["knowledge"]
            self.assertFalse(unavailable["knowledge_sources_available"])
            self.assertEqual([item["id"] for item in unavailable["knowledge_sources"]],
                             ["doc:kb-1:doc-1", "kb:missing"])
        finally:
            self.controller.unregister_routes()

    async def test_every_section_reads_with_its_own_scope_and_token(self):
        handlers, first, _ = await self.routes()
        try:
            status = (await call(handlers[first]))["data"]["sections"]
            expected_sections = {"budget", "busy_gate", "group_participation", "image_review",
                                 "knowledge", "library", "life", "person", "photo.reference",
                                 "private_access", "proactive.contact", "quota", "reaction", "recall",
                                 "content.authoring",
                                 # qzone 是真实配置分区（companion_v2/qzone/configuration.py:18
                                 # 的 GROUP = "qzone"）。它加入注册表时这份硬编码清单没跟上，
                                 # 于是 assertEqual 把"多了一个真分区"报成失败——这正是本会话
                                 # 反复出现的模式：新增能力却不更新按字面枚举的名单。
                                 "qzone",
                                 "relationship_profile", "role.growth.skills", "role_growth",
                                 "role_profile", "screen", "wardrobe"}
            expected_sections.add("image.output")
            self.assertTrue(expected_sections.issubset(status))
            self.assertEqual(set(status), expected_sections)
            self.assertEqual(status["quota"]["scope"], "role")
            self.assertEqual(status["budget"]["scope"], "role")
            self.assertEqual(status["library"]["scope"], "role")
            self.assertEqual(status["role_profile"]["scope"], "role")
            self.assertEqual(status["role_profile"]["layers"], ["installation", "role"])
            self.assertEqual(status["role_profile"]["fields"]["world"]["maximum_chars"], 4200)
            self.assertEqual(status["role_profile"]["settings"]["world_adaptation_mode"], "auto")
            self.assertEqual(status["role_profile"]["fields"]["world_adaptation_mode"]["maximum_chars"], 20)
            self.assertEqual(status["role_profile"]["fields"]["world_adaptation"]["maximum_chars"], 1200)
            self.assertEqual(set(status["role_profile"]["settings"]), set(FIELD_LIMITS))
            self.assertEqual(status["relationship_profile"]["scope"], "relationship")
            self.assertEqual(status["relationship_profile"]["layers"],
                             ["installation", "role", "relationship"])
            self.assertEqual(status["relationship_profile"]["fields"]["role_relation"]["editable_layers"],
                             ["relationship"])
            # 参考图与衣柜同样按角色生效：单个会话不能收窄整个角色的设置。
            self.assertEqual(status["wardrobe"]["scope"], "role")
            self.assertEqual(status["photo.reference"]["scope"], "role")
            self.assertEqual(status["image_review"]["scope"], "window")
            self.assertEqual(status["busy_gate"]["scope"], "window")
            self.assertEqual(status["reaction"]["scope"], "window")
            # 2026-09-28 新增的各组都是窗口级；主动联系偏好同样是窗口级，
            # 但它的继承链上多了关系层（安装 → 角色 → 关系 → 窗口）。
            for name in ("recall", "screen", "person", "role_growth", "knowledge", "life",
                         "group_participation", "proactive.contact"):
                self.assertEqual(status[name]["scope"], "window", name)
            self.assertEqual(status["proactive.contact"]["layers"],
                             ["installation", "role", "relationship", "window"])
            self.assertEqual(status["quota"]["settings"]["private_owner_max_daily"], -1)
            self.assertEqual(status["reaction"]["settings"]["candidate_limit"], 6)
            self.assertTrue(status["budget"]["settings"]["enable_daily_token_soft_limit"])
            self.assertFalse(status["recall"]["settings"]["transcribe_enabled"])
            self.assertFalse(status["screen"]["settings"]["interpretation_enabled"])
            self.assertTrue(status["person"]["settings"]["acquaintance_enabled"])
            # 技能领域已独立成组：权限留在 role_growth，内容落在 role.growth.skills。
            self.assertNotIn("custom_skills", status["role_growth"]["settings"])
            self.assertEqual(status["role.growth.skills"]["settings"]["custom_skills"], "[]")
            self.assertEqual(status["role.growth.skills"]["settings"]["schedule_influence_strength"], 0)
            # 技能组是双层：默认落窗口，但可写到角色级，因此链上必须出现 role。
            self.assertIn("role", status["role.growth.skills"]["layers"])
            # 群聊参与：V1 的默认行为——跟读默认开、主动插话默认关。
            self.assertTrue(status["group_participation"]["settings"]["enable_group_repeat_follow"])
            self.assertFalse(status["group_participation"]["settings"]["enable_group_interjection"])
            # 参考图与衣柜的两个总闸默认关闭；轮换天数沿用 14 天。
            self.assertFalse(status["wardrobe"]["settings"]["enabled"])
            self.assertFalse(status["photo.reference"]["settings"]["enabled"])
            self.assertFalse(status["photo.reference"]["settings"]["group_enabled"])
            self.assertFalse(status["photo.reference"]["settings"]["daily_outfit_enabled"])
            self.assertEqual(status["photo.reference"]["settings"]["daily_outfit_rotation_days"], 14)
            for name, section in status.items():
                self.assertEqual(len(section["edit_token"]), 64, name)
                # 组名以各自域开头：既有组用 conversation./expression./model.，
                # 新增组分别是 conversation.recall / screen / person / role.growth /
                # conversation.group_participation / photo.reference 等；
                # private_access（私聊用户权限的默认值与拒绝文案）本身就是一个小域，
                # 不带厂商前缀，字段是按人权限的默认值而不是某个能力的实现细节。
                # qzone（QQ 空间拓展的角色级开关与节流）同样是自己的一个小域。
                # 这份白名单是**按字面枚举**的，所以每加一个不带前缀的域都要跟上——
                # 今天 qzone 就因此判红过一次，而失败信息只说"qzone"，看不出是
                # "多了一个真域"还是"组名写错了"。加域时两处都要改：
                # 这里的前缀白名单，以及下面 expected_sections 的组清单。
                self.assertTrue(section["group_id"].split(".")[0] in
                                ("conversation", "expression", "model", "screen", "person",
                                 "role", "knowledge", "library", "photo", "wardrobe",
                                 "proactive", "private_access", "relationship", "content",
                                 "qzone"), name)
            # The workbench renders its layer rail from these, so every section
            # must publish the chain and a per-field source, not just its values.
            for name, section in status.items():
                self.assertIn(section["scope"], ("role", "relationship", "window"), name)
                self.assertTrue(section["layers"], name)
                self.assertEqual(section["layers"][-1], section["scope"], name)
                self.assertTrue(section["provenance"], name)
                self.assertTrue(section["fields"], name)
                self.assertIn("kind", section["fields"][next(iter(section["settings"]))], name)
            # Window groups and the role ceiling are different targets, so their
            # tokens must not be interchangeable.
            self.assertNotEqual(status["quota"]["edit_token"], status["image_review"]["edit_token"])
            restricted = await call(handlers[first], query={"sections": "quota"})
            self.assertEqual(sorted(restricted["data"]["sections"]), ["quota"])
            self.assertEqual((await call(handlers[first], query={"sections": "nope"}))["data"]["code"],
                             "configuration_request_invalid")
        finally:
            self.controller.unregister_routes()

    async def test_role_and_window_sections_save_independently_and_replay(self):
        handlers, first, second = await self.routes()
        try:
            status = (await call(handlers[first]))["data"]["sections"]
            quota = {"section": "quota", "operation_key": "quota-1",
                     "edit_token": status["quota"]["edit_token"],
                     "changes": {"group_max_daily": 5, "proactive_max_daily": 0}}
            saved = await call(handlers[first + "/configure"], quota)
            self.assertEqual(saved["status"], "ok", saved)
            self.assertTrue((await call(handlers[first + "/configure"], quota))["data"]["result"]["replayed"])
            after = (await call(handlers[first], query={"sections": "quota"}))["data"]["sections"]["quota"]["settings"]
            self.assertEqual((after["group_max_daily"], after["proactive_max_daily"]), (5, 0))
            # Another target keeps its own ceiling.
            other = (await call(handlers[second]))["data"]["sections"]["quota"]["settings"]
            self.assertEqual(other["group_max_daily"], -1)
            # A window section saves with its own token and leaves the role
            # ceiling untouched.
            review_status = (await call(handlers[first], query={"sections": "image_review"}))
            review = {"section": "image_review", "operation_key": "review-1",
                      "edit_token": review_status["data"]["sections"]["image_review"]["edit_token"],
                      "changes": {"enable_group_nsfw_private_fallback": True,
                                  "group_nsfw_image_review_mode": "dual"}}
            reviewed = await call(handlers[first + "/configure"], review)
            self.assertEqual(reviewed["status"], "ok", reviewed)
            sections = (await call(handlers[first], query={"sections": "image_review"}))["data"]["sections"]
            self.assertTrue(sections["image_review"]["settings"]["enable_group_nsfw_private_fallback"])
            self.assertEqual(sections["image_review"]["settings"]["group_nsfw_image_review_mode"], "dual")
            quota_after = (await call(handlers[first], query={"sections": "quota"}))
            self.assertEqual(quota_after["data"]["sections"]["quota"]["settings"]["group_max_daily"], 5)
            # Using one section's token for another section's target is rejected.
            quota_token = quota_after["data"]["sections"]["quota"]["edit_token"]
            crossed = await call(handlers[first + "/configure"],
                                    {"section": "reaction", "operation_key": "cross",
                                     "edit_token": quota_token, "changes": {"candidate_limit": 3}})
            self.assertIn(crossed["data"]["code"], ("configuration_revision_conflict", "invalid_configuration_value"))
        finally:
            self.controller.unregister_routes()

    async def test_role_profile_is_saved_for_one_role_and_not_another(self):
        handlers, first, second = await self.routes()
        try:
            profile = (await call(handlers[first]))["data"]["sections"]["role_profile"]
            response = await call(handlers[first + "/configure"], {
                "section": "role_profile", "operation_key": "profile-first",
                "edit_token": profile["edit_token"],
                "changes": {"identity": "住在旧城边的电台编辑", "world": "信件总会晚一个雨季才抵达。"},
            })
            self.assertEqual(response["status"], "ok", response)
            first_saved = (await call(handlers[first], query={"sections": "role_profile"}))[
                "data"]["sections"]["role_profile"]["settings"]
            self.assertEqual(first_saved["identity"], "住在旧城边的电台编辑")
            self.assertEqual(first_saved["world"], "信件总会晚一个雨季才抵达。")
            other = (await call(handlers[second]))["data"]["sections"]["role_profile"]["settings"]
            self.assertEqual(other["identity"], "")
            self.assertEqual(other["world"], "")
        finally:
            self.controller.unregister_routes()

    async def test_relationship_profile_is_saved_per_person_for_the_same_role(self):
        config = multi_config(delivery_mode="onebot_private")
        config["multi_host"]["targets"].append({
            "target_id": "third", "platform_id": "qq-main", "account_id": "100",
            "bot_id": "bot-a", "participant_id": "201",
        })
        self.controller = self.make_controller(config)
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        self.controller.register_routes()
        handlers = {route: handler for route, handler, _, _ in self.native.registered_web_apis}
        first = next(route for route in handlers if route.endswith("/config") and "/model/" not in route
                     and "/targets/first/" in route)
        third = next(route for route in handlers if route.endswith("/config") and "/model/" not in route
                     and "/targets/third/" in route)
        try:
            relationship = (await call(handlers[first]))["data"]["sections"]["relationship_profile"]
            response = await call(handlers[first + "/configure"], {
                "section": "relationship_profile", "operation_key": "relationship-first",
                "edit_token": relationship["edit_token"],
                "changes": {"default_nickname": "小舟", "role_relation": "经确认的搭档"},
            })
            self.assertEqual(response["status"], "ok", response)
            first_saved = (await call(handlers[first], query={"sections": "relationship_profile"}))[
                "data"]["sections"]["relationship_profile"]["settings"]
            self.assertEqual(first_saved["default_nickname"], "小舟")
            self.assertEqual(first_saved["role_relation"], "经确认的搭档")
            other = (await call(handlers[third]))["data"]["sections"]["relationship_profile"]["settings"]
            self.assertEqual(other["default_nickname"], "")
            self.assertEqual(other["role_relation"], "")
        finally:
            self.controller.unregister_routes()

    async def test_the_contact_section_publishes_four_layers_and_locks_the_relationship_budget(self):
        """主动联系偏好是唯一一个四层组，也是最长的一个分区（160 项）。

        两个「同一关系」的额度按窗口写入会被所有者拒绝，所以字段契约里不能出现
        窗口层——否则页面会渲染一个存不下去的控件。其余字段仍然四层可写。
        """
        handlers, first, _ = await self.routes()
        try:
            status = (await call(handlers[first]))["data"]["sections"]
            contact = status["proactive.contact"]
            self.assertEqual(contact["group_id"], "proactive.contact")
            self.assertEqual(contact["scope"], "window")
            self.assertEqual(contact["layers"], ["installation", "role", "relationship", "window"])
            self.assertEqual(len(contact["settings"]), 164)
            self.assertEqual(len(contact["provenance"]), 164)
            self.assertFalse(contact["settings"]["enabled"])
            self.assertEqual(contact["settings"]["interval_seconds"], 3600)
            self.assertEqual(contact["settings"]["quiet_timezone"], "Asia/Shanghai")
            for name in ("max_relationship_contacts_24h", "max_relationship_attempts_24h"):
                with self.subTest(field=name):
                    editable = contact["fields"][name]["editable_layers"]
                    self.assertIn("relationship", editable)
                    self.assertNotIn("window", editable)
            self.assertIn("window", contact["fields"]["interval_seconds"]["editable_layers"])
            refused = await call(handlers[first + "/configure"],
                {"section": "proactive.contact", "operation_key": "contact-budget",
                 "edit_token": contact["edit_token"],
                 "changes": {"max_relationship_contacts_24h": 12}})
            self.assertEqual(refused["data"]["code"], "contact_relationship_budget_scope")
            saved = await call(handlers[first + "/configure"],
                {"section": "proactive.contact", "operation_key": "contact-rhythm",
                 "edit_token": contact["edit_token"],
                 "changes": {"interval_seconds": 900, "quiet_enabled": True}})
            self.assertEqual(saved["status"], "ok", saved)
            after = (await call(handlers[first], query={"sections": "proactive.contact"}))[
                "data"]["sections"]["proactive.contact"]
            self.assertEqual(after["settings"]["interval_seconds"], 900)
            self.assertTrue(after["settings"]["quiet_enabled"])
            # 保存后编辑令牌必然更新，否则两次保存会互相覆盖。
            self.assertNotEqual(after["edit_token"], contact["edit_token"])
        finally:
            self.controller.unregister_routes()

    async def test_contact_save_returns_receipt_without_reading_status(self):
        from astrbot_host.configuration_api import ConfigurationWebAPI

        handlers, first, _ = await self.routes()
        try:
            initial = (await call(handlers[first], query={"sections": "proactive.contact"}))
            contact = initial["data"]["sections"]["proactive.contact"]
            body = {"section": "proactive.contact", "operation_key": "contact-save-isolated",
                    "edit_token": contact["edit_token"], "changes": {"interval_seconds": 1200}}
            with patch.object(ConfigurationWebAPI, "_status", new_callable=AsyncMock) as api_status, \
                    patch("companion_v2.configuration.management.GroupEditor.status",
                          side_effect=AssertionError("a write must not read its post-save status")) as editor_status:
                saved = await call(handlers[first + "/configure"], body)
                replayed = await call(handlers[first + "/configure"], body)

            api_status.assert_not_awaited()
            editor_status.assert_not_called()
            self.assertEqual(saved["status"], "ok", saved)
            self.assertEqual(set(saved["data"]), {"result"})
            self.assertFalse(saved["data"]["result"]["replayed"])
            self.assertTrue(replayed["data"]["result"]["replayed"])
            self.assertEqual(saved["data"]["result"]["operation_id"],
                             replayed["data"]["result"]["operation_id"])
            refreshed = (await call(handlers[first], query={"sections": "proactive.contact"}))[
                "data"]["sections"]["proactive.contact"]
            self.assertEqual(refreshed["settings"]["interval_seconds"], 1200)
        finally:
            self.controller.unregister_routes()

    async def test_the_busy_gate_section_round_trips_its_keyword_lists(self):
        handlers, first, _ = await self.routes()
        try:
            gate = (await call(handlers[first]))["data"]["sections"]["busy_gate"]
            self.assertFalse(gate["settings"]["busy_reply_gate_enabled"])
            self.assertEqual(gate["fields"]["busy_reply_min_delay_seconds"]["maximum"], 900)
            answer = await call(handlers[first + "/configure"],
                {"section": "busy_gate", "operation_key": "gate-1", "edit_token": gate["edit_token"],
                 "changes": {"busy_reply_gate_enabled": True, "busy_reply_min_delay_seconds": 45,
                             "busy_activity_keywords": "开会, 赶稿、写代码"}})
            self.assertEqual(answer["status"], "ok", answer)
            after = (await call(handlers[first], query={"sections": "busy_gate"}))["data"]["sections"]["busy_gate"]
            settings = after["settings"]
            self.assertTrue(settings["busy_reply_gate_enabled"])
            self.assertEqual(settings["busy_reply_min_delay_seconds"], 45)
            # The stored form keeps the separators the operator typed; the parsed
            # keyword list is what the gate reads.
            self.assertEqual(settings["busy_activity_keywords"], "开会, 赶稿、写代码")
            # A keyword list the gate would reject never reaches storage.
            refused = await call(handlers[first + "/configure"],
                {"section": "busy_gate", "operation_key": "gate-2",
                 "edit_token": after["edit_token"],
                 "changes": {"busy_activity_keywords": "x" * 25}})
            self.assertEqual(refused["data"]["code"], "busy_gate_settings_invalid")
        finally:
            self.controller.unregister_routes()

    async def test_content_authoring_settings_round_trip_at_role_scope(self):
        handlers, first, _ = await self.routes()
        try:
            initial = (await call(handlers[first]))["data"]["sections"]["content.authoring"]
            self.assertEqual(initial["scope"], "role")
            self.assertEqual(initial["layers"], ["installation", "role"])
            answer = await call(handlers[first + "/configure"],
                {"section": "content.authoring", "operation_key": "authoring-1",
                 "edit_token": initial["edit_token"],
                 "changes": {"enabled": True, "direction_prompt": "保持清晰、克制的叙事风格。"}})
            self.assertEqual(answer["status"], "ok", answer)
            settings = (await call(handlers[first], query={"sections": "content.authoring"}))[
                "data"]["sections"]["content.authoring"]["settings"]
            self.assertTrue(settings["enabled"])
            self.assertEqual(settings["direction_prompt"], "保持清晰、克制的叙事风格。")
        finally:
            self.controller.unregister_routes()

    async def test_invalid_requests_and_unknown_fields_are_refused(self):
        handlers, first, _ = await self.routes()
        try:
            status = (await call(handlers[first]))["data"]["sections"]
            token = status["reaction"]["edit_token"]
            for changes in ({"nope": 1}, {"candidate_limit": 0}, {"candidate_limit": 99},
                            {"embedding_score_threshold": 2}, {"vision_verify_mode": "sometimes"}):
                answer = await call(handlers[first + "/configure"],
                                       {"section": "reaction", "operation_key": "bad-" + str(len(changes)),
                                        "edit_token": token, "changes": changes})
                self.assertEqual(answer["status"], "error", changes)
                self.assertNotEqual(answer["data"]["code"], "staging_host_terminated", changes)
            self.assertEqual((await call(handlers[first + "/configure"],
                                            {"section": "unknown", "operation_key": "k", "edit_token": token,
                                             "changes": {"candidate_limit": 3}}))["data"]["code"],
                             "configuration_request_invalid")
            self.assertEqual((await call(handlers[first + "/configure"],
                                            {"section": "reaction", "operation_key": "k", "edit_token": token,
                                             "changes": {"candidate_limit": 3}, "extra": 1}))["data"]["code"],
                             "configuration_request_invalid")
            self.assertEqual((await call(handlers[first], username="api_key:x"))["data"]["code"],
                             "dashboard_identity_required")
        finally:
            self.controller.unregister_routes()


class SingleHostConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_host_registers_the_route(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from tests.test_management_access import NOW

        temporary = TemporaryDirectory(prefix="companion-config-api-")
        self.addCleanup(temporary.cleanup)
        native = support.WebContext()
        config = support.host_config(staging={"profile_id": "config-api", "delivery_mode": "onebot_private"})
        types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        controller = AstrBotStagingController(native, config, Path(temporary.name), native_types=types, now=lambda: NOW)
        self.addAsyncCleanup(controller.terminate)
        (await controller.initialize_profile()).unwrap()
        (await controller.authorize_delivery()).unwrap()
        controller.register_routes()
        routes = {route for route, _, _, _ in native.registered_web_apis}
        self.assertIn("/astrbot_plugin_private_companion_v2/config", routes)
        self.assertIn("/astrbot_plugin_private_companion_v2/config/configure", routes)
        controller.unregister_routes()
        self.assertEqual(native.registered_web_apis, [])


if __name__ == "__main__":
    unittest.main()
