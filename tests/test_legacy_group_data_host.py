"""Exercise explicit V1 group mappings through registered host routes."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.legacy_group_data_api import LegacyGroupDataWebAPI
from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_api import PREFIX as HOST_PREFIX
from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.knowledge.catalog import KnowledgeCatalog, SourceBinding
from companion_v2.knowledge.retrieval import KnowledgeQuery, KnowledgeRetriever
from companion_v2.relationships.group_network import GroupRelationshipStore
from tests.group_host_support import GroupFixture


class LegacyGroupDataHostTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler
                       for path, handler, methods, _ in self.native.registered_web_apis}

    def _path(self, target="group-a", role="role-a"):
        return (HOST_PREFIX + "/targets/" + target + "/roles/" + digest(role)
                + "/legacy-group-data")

    async def request(self, suffix="/plan", *, target="group-a", role="role-a", username="admin",
                      data=None, query=""):
        path = self._path(target, role) + suffix
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else b""
        method = "POST" if data is not None else "GET"

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        native = Request({"type": "http", "method": method, "path": path, "headers": [],
                          "query_string": query.encode("utf-8")}, receive=receive)
        with bind_request_context(PluginRequest(native, username=username)):
            return await self.routes[(path, method)]()

    def source_root(self):
        root = self.root / "synthetic-v1"
        root.mkdir()
        payload = {
            "groups": {"789": {"members": {
                "200": {"name": "甲群成员", "count": 8},
                "201": {"name": "乙群成员", "count": 4}},
                "relationship_edges": {"200|201": {
                    "a": "200", "b": "201", "count": 2, "tone": "玩笑"}}}},
            "worldbook_entries": [{"id": "group-entry", "name": "甲群资料",
                "content": "只有明确映射到甲群后才可注入的合成资料。",
                "__template_key": "group", "scope": ["default:groupmessage:789"]}],
            "worldbook_group_profiles": {"789": {"name": "甲群补充资料",
                "content": "仅用于验证群范围的第二条合成资料。"}},
            "worldbook_member_profiles": {"200": {"user_id": "200", "name": "甲群成员",
                "content": "甲群合成成员线索。", "projection_kind": "group_observation",
                "group_observation_scope_ids": ["default:groupmessage:789"]}},
        }
        (root / "companions.json").write_text(
            json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return root

    async def plan(self, root, *, target="group-a", role="role-a"):
        # Match the setup page: empty primary-persona values are not sent.
        query = urlencode({"v1_root": str(root), "source_group_id": "789"})
        response = await self.request("/plan", target=target, role=role, query=query)
        self.assertEqual(response["status"], "ok", response)
        return response["data"]

    async def apply(self, plan, root, *, target="group-a", role="role-a"):
        return await self.request("/apply", target=target, role=role, data={
            "plan_token": plan["plan_token"], "source_persona_id": "", "source_group_id": "789",
            "import_group_network": True, "import_group_worldbook": True,
            "confirm_member_ids": True, "confirm_group_mapping": True, "v1_root": str(root),
        })

    def scope(self, *, platform, bot, account):
        return ScopeRef(self.controller.runtime.installation_id, platform, ScopeKind.GROUP,
            "300", bot, account, "300", "300")

    def group_binding(self, *, platform, bot, account):
        return SourceBinding(self.controller.runtime.installation_id, role_id="role-a", persona_id="role-a",
            native_scope_ids=("300",), scope_kind=ScopeKind.GROUP,
            scope_route=(platform, bot, account))

    async def test_primary_persona_preview_accepts_omitted_id_but_apply_requires_it(self):
        root = self.source_root()
        await self.start_host()
        plan = await self.plan(root)
        explicit = await self.request("/plan", query=urlencode({
            "v1_root": str(root), "source_persona_id": "", "source_group_id": "789"}))
        self.assertEqual(explicit["status"], "ok", explicit)
        self.assertEqual(plan["source_persona_id"], "")
        self.assertEqual(plan["plan_token"], explicit["data"]["plan_token"])
        missing = await self.request("/apply", data={
            "plan_token": plan["plan_token"], "source_group_id": "789",
            "import_group_network": True, "import_group_worldbook": True,
            "confirm_member_ids": True, "confirm_group_mapping": True,
            "v1_root": str(root)})
        self.assertEqual(missing["status"], "error", missing)
        self.assertEqual(missing["data"]["code"], "legacy_request_invalid")

    async def test_mapping_import_is_explicit_and_isolated_across_same_id_platform_groups(self):
        root = self.source_root()
        await self.start_host()
        plan = await self.plan(root)

        self.assertEqual(plan["mapping_policy"], {
            "source_to_targets": "one_to_many_explicit", "targets_per_plan": 1,
            "automatic_fanout": False, "source_platform_id": None, "source_platform_known": False})
        self.assertEqual(plan["target"], {"target_id": "group-a", "platform_id": "qq-main",
            "account_id": "100", "bot_id": "bot-a", "group_id": "300", "role_id": "role-a"})
        result = await self.apply(plan, root)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["data"]["group_network"]["imported"])

        runtime = self.controller.runtime
        store = GroupRelationshipStore(runtime)
        selected = store.projection_for_route(runtime.installation_id, "qq-main", "bot-a", "100", "300", "role-a")
        other_platform = store.projection_for_route(runtime.installation_id, "qq-second", "bot-b", "101", "300", "role-a")
        self.assertEqual({item["native_account_id"] for item in selected["members"]}, {"200", "201"})
        self.assertEqual(other_platform["members"], [])
        self.assertEqual(len(selected["edges"]), 1)
        self.assertEqual(len(other_platform["edges"]), 0)

        catalog = KnowledgeCatalog(runtime)
        group_id = LegacyMigrationWebAPI._worldbook_source_id("", "789")
        version = catalog.get(self.group_binding(platform="qq-main", bot="bot-a", account="100"), group_id)
        self.assertIsNotNone(version)
        self.assertEqual(version.binding.scope_route, ("qq-main", "bot-a", "100"))
        self.assertEqual(version.members[0].group_ids, ("300",))
        candidates = catalog.background_candidates(installation_id=runtime.installation_id,
            source_limit=64, char_budget=4000)
        retriever = KnowledgeRetriever(candidates)
        query = "明确映射到甲群后才可注入"
        selected_result = retriever.select(KnowledgeQuery(query,
            self.scope(platform="qq-main", bot="bot-a", account="100"), role_id="role-a"))
        self.assertTrue(selected_result.hits)
        other_routes = (
            ("qq-second", "bot-a", "100"),
            ("qq-main", "bot-b", "100"),
            ("qq-main", "bot-a", "101"),
        )
        for platform, bot, account in other_routes:
            with self.subTest(platform=platform, bot=bot, account=account):
                foreign_scope = self.scope(platform=platform, bot=bot, account=account)
                foreign_result = retriever.select(KnowledgeQuery(query, foreign_scope, role_id="role-a"))
                self.assertEqual(foreign_result.hits, ())
                self.assertEqual(catalog.member_entries(installation_id=runtime.installation_id,
                    source_limit=64, role_id="role-a", scope_ids=("300",), scope_kind=ScopeKind.GROUP,
                    scope=foreign_scope), ())

        self.assertEqual(len(catalog.member_entries(installation_id=runtime.installation_id,
            source_limit=64, role_id="role-a", scope_ids=("300",), scope_kind=ScopeKind.GROUP,
            scope=self.scope(platform="qq-main", bot="bot-a", account="100"))), 1)

    async def test_worldbook_failure_rolls_back_relationship_write(self):
        root = self.source_root()
        await self.start_host()
        plan = await self.plan(root)

        def fail_save(_self, *_args, **_kwargs):
            raise TaskError("test_worldbook_write_failed", "synthetic failure")

        with patch.object(KnowledgeCatalog, "save", autospec=True, side_effect=fail_save):
            response = await self.apply(plan, root)

        self.assertEqual(response["status"], "error", response)
        self.assertEqual(response["data"]["code"], "test_worldbook_write_failed")
        runtime = self.controller.runtime
        network = GroupRelationshipStore(runtime).projection_for_route(
            runtime.installation_id, "qq-main", "bot-a", "100", "300", "role-a")
        self.assertEqual(network["members"], [])
        self.assertIsNone(KnowledgeCatalog(runtime).get(
            self.group_binding(platform="qq-main", bot="bot-a", account="100"),
            LegacyMigrationWebAPI._worldbook_source_id("", "789")))

    async def test_plan_token_is_stale_after_target_graph_changes(self):
        root = self.source_root()
        await self.start_host()
        plan = await self.plan(root)
        target = self.controller.settings.target("group-a")
        context = LegacyGroupDataWebAPI(self.controller, target.target_id, "role-a")._scope_context(target)
        self.controller.session.application.messages.group_network.import_legacy_aggregate(
            context, source_key="independent-change", members={"299": {"name": "另一位",
                "message_count": 1, "active_days": 1}}, edges=[])

        response = await self.apply(plan, root)
        self.assertEqual(response["status"], "error", response)
        self.assertEqual(response["data"]["code"], "legacy_plan_stale")
        network = GroupRelationshipStore(self.controller.runtime).projection_for_route(
            self.controller.runtime.installation_id, "qq-main", "bot-a", "100", "300", "role-a")
        self.assertEqual({item["native_account_id"] for item in network["members"]}, {"299"})


if __name__ == "__main__":
    unittest.main()
