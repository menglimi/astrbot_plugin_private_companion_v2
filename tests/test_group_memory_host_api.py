"""Real Dashboard requests, fixed collective targets and lifecycle cleanup."""

import asyncio
import json
from urllib.parse import urlencode
import unittest

from tests.group_memory_management_support import GroupMemoryManagementFixture
from astrbot.api.web import PluginRequest, bind_request_context
from astrbot_host.management_identity import dashboard_operator
from starlette.requests import Request
from companion_v2.execution.models import digest
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy


PREFIX = "/astrbot_plugin_private_companion"


class GroupMemoryHostAPITests(GroupMemoryManagementFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler for path, handler, methods, _ in self.native.registered_web_apis}

    async def request(self, suffix="", *, target="group-a", role="role-a", username="admin",
                      data=None, raw=None, query="", path=None, hold=None):
        path = path or PREFIX + "/host/targets/" + target + "/roles/" + digest(role) + "/group-memory" + suffix
        body = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else b""
        method = "POST" if body else "GET"

        async def receive():
            if hold:
                hold[0].set()
                await hold[1].wait()
            return {"type": "http.request", "body": body, "more_body": False}

        req = Request({"type": "http", "method": method, "path": path, "headers": [],
                       "query_string": query.encode("utf-8")}, receive=receive)
        with bind_request_context(PluginRequest(req, username=username)):
            return await self.routes[(path, method)]()

    async def seed(self, **options):
        context, batch, receipt = await self.conversation(remember=True, **options)
        return context, batch, receipt

    async def test_directory_registers_group_archive_separately_from_private_memory(self):
        await self.start_host()
        directory = (await self.request(path=PREFIX + "/page/targets"))["data"]
        routes = {path for path, _ in self.routes}
        for target in directory["targets"]:
            for role in target["roles"]:
                if target["scope_kind"] == "group":
                    self.assertIsNone(role["memory_api"])
                    self.assertIn(role["group_memory_api"], routes)
                    self.assertIn(role["group_memory_api"] + "/retract", routes)
                else:
                    self.assertIsNotNone(role["memory_api"])
                    self.assertNotIn("group_memory_api", role)
        empty = await self.request()
        self.assertEqual(empty["status"], "ok", empty)
        self.assertEqual(empty["data"]["items"], [])
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_inputs", ())[0], 0)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_login_host_and_current_core_tier_are_required(self):
        for username in (None, "", "api_key:synthetic"):
            self.assertEqual((await self.request(username=username))["data"]["code"], "dashboard_identity_required")
        self.assertEqual((await self.request())["data"]["code"], "staging_not_initialized")
        await self.start_host()
        operator = dashboard_operator(self.app.runtime, "admin", at=self.clock.now())
        policy = ObjectAccessPolicy(self.app.runtime)
        for tier in (AuthorizationTier.IMPORTANT, AuthorizationTier.STANDARD):
            policy.set_tier(operator.subject, tier, expected_revision=policy.revision, observed_at=self.clock.now())
            self.assertEqual((await self.request())["data"]["code"], "core_access_required")

    async def test_review_retract_and_receipt_use_original_pinned_group_and_operator(self):
        await self.start_host()
        _, _, saved = await self.seed()
        _, _, another = await self.seed(target="group-b", wording="另一群的原话")
        platform_calls_before_management = list(self.native.platform.client._api._wsr_api.calls)
        listed = await self.request()
        item = listed["data"]["items"][0]
        detail = await self.request("/detail", data={"memory_id": saved["memory_id"], "revision": 1, "chars": 4})
        self.assertEqual(detail["data"]["evidence"]["text"], "周六去公")
        self.assertEqual(detail["data"]["evidence"]["speaker_id"], "201")
        calls = len(self.native.provider.client.state.calls)
        args = self.command(item, reason="管理员撤回测试")
        retired = await self.request("/retract", data=args)
        self.assertEqual(retired["status"], "ok", retired)
        self.assertEqual(retired["data"]["attribution"], "administrator_action")
        self.assertEqual(await self.request("/retract", data=args), retired)
        self.assertEqual(await self.request("/operation", query=urlencode({"operation_id": retired["data"]["operation_id"]})), retired)
        self.assertEqual((await self.request(target="group-b"))["data"]["items"][0]["memory_id"], another["memory_id"])
        self.assertEqual((await self.request("/detail", target="group-b",
            data={"memory_id": saved["memory_id"], "revision": 1}))["data"]["code"], "group_memory_unavailable")
        self.assertEqual(len(self.native.provider.client.state.calls), calls)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, platform_calls_before_management)

    async def test_group_role_and_independent_native_sessions_keep_separate_archives(self):
        await self.start_host()
        _, _, saved = await self.seed(unique=True)
        self.assertEqual((await self.request())["data"]["items"], [])
        selected = await self.request(query="session_id=201_300")
        self.assertEqual(selected["data"]["items"][0]["memory_id"], saved["memory_id"])
        for options in ({"role": "role-b", "query": "session_id=201_300"},
                        {"target": "group-c", "query": "session_id=201_300"}, {"query": "session_id=202_300"}):
            with self.subTest(options=options):
                self.assertEqual((await self.request(**options))["data"]["items"], [])
        denied = await self.request(query="session_id=201_301")
        self.assertEqual(denied["data"]["code"], "group_memory_session_invalid")

    async def test_invalid_identity_fields_duplicate_keys_and_oversized_bodies_have_no_effect(self):
        await self.start_host()
        await self.seed()
        item = (await self.request())["data"]["items"][0]
        args = self.command(item)
        for extra in ({"scope": {}}, {"speaker_id": "999"}, {"operator": "admin"}, {"target_id": "group-b"},
                      {"role_id": "role-b"}, {"source": {}}):
            result = await self.request("/retract", data=args | extra)
            self.assertEqual(result["data"]["code"], "group_memory_request_invalid")
        for raw in (b'{"memory_id":"first","memory_id":"second"}', b'[' * 5000, b'"' + b'x' * 8192 + b'"'):
            self.assertEqual((await self.request("/retract", raw=raw))["data"]["code"], "group_memory_request_invalid")
        for query in ("limit=1&limit=2", "operator=admin", "state=all", "limit=0"):
            self.assertEqual((await self.request(query=query))["data"]["code"], "group_memory_request_invalid")
        self.assertEqual((await self.request("/retract", data=args, query="scope=other"))["data"]["code"],
                         "group_memory_request_invalid")
        self.assertEqual((await self.request())["data"]["items"][0]["revision"], 1)

    async def test_slow_request_keeps_target_and_rechecks_authority_after_body_read(self):
        await self.start_host()
        context, _, _ = await self.seed()
        await self.seed(target="group-b", wording="另一个群")
        first = (await self.request())["data"]["items"][0]
        ready, release = asyncio.Event(), asyncio.Event()
        pending = asyncio.create_task(self.request("/retract", data=self.command(first), hold=(ready, release)))
        try:
            await asyncio.wait_for(ready.wait(), 3)
            second = (await self.request(target="group-b"))["data"]["items"][0]
            result = await self.request("/retract", target="group-b", data=self.command(second))
            self.assertEqual(result["status"], "ok", result)
            operator = dashboard_operator(self.app.runtime, "admin", at=self.clock.now())
            policy = ObjectAccessPolicy(self.app.runtime)
            policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
                            expected_revision=policy.revision, observed_at=self.clock.now())
        finally:
            release.set()
        self.assertEqual((await pending)["data"]["code"], "core_access_required")
        manager = self.manager("fresh-admin")
        self.assertEqual(manager.list(self.target(context)).unwrap()["items"][0]["revision"], 1)

    async def test_shutdown_removes_routes_and_retained_handler_cannot_admit_late_command(self):
        await self.start_host()
        await self.seed()
        item = (await self.request())["data"]["items"][0]
        ready, release = asyncio.Event(), asyncio.Event()
        pending = asyncio.create_task(self.request("/retract", data=self.command(item), hold=(ready, release)))
        try:
            await asyncio.wait_for(ready.wait(), 3)
            await self.controller.terminate()
        finally:
            release.set()
        self.assertEqual((await pending)["data"]["code"], "staging_host_terminated")
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.request())["data"]["code"], "staging_host_terminated")


if __name__ == "__main__":
    unittest.main()
