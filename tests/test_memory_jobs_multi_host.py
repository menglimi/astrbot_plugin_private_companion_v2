"""The shared Dashboard queues work only for its fixed private target and role."""

import asyncio
from datetime import timedelta
import json
import unittest

from tests.multi_host_support import MultiFixture
from tests.native_adapter_support import completion
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.adapters.astrbot.native import persona_instruction


class MemoryJobsMultiHostTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def request(self, path, *, data=None, query=""):
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        method = "POST" if data is not None else "GET"
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        req = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": query.encode()}, receive=receive)
        with bind_request_context(PluginRequest(req, username="admin")):
            return await self.routes[path, method]()

    async def test_background_route_is_fixed_to_target_and_role_and_removed_on_shutdown(self):
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler for path, handler, methods, _ in self.native.registered_web_apis}
        app = await self.start_host()
        prepared = (await self.controller.prepare_core_reply(self.event())).unwrap()
        await prepared["native_source_future"]
        context = prepared["context"]
        for action in ("memory.reflect", "memory.read", "memory.propose", "memory.subscribe"):
            app.tasks.identity.issue_grant(grant_id="memory-jobs-" + action, subject=context.actor.subject,
                scope=context.scope, capability=action, tier=AuthorizationTier.STANDARD,
                valid_from=self.clock.now(), expected_revision=app.tasks.identity.revision)
        self.clock.advance(timedelta(seconds=1))
        batch = app.memory_reflection.prepare(context, request_id="multi-queue", start=self.clock.now() - timedelta(hours=1),
            end=self.clock.now(), role_instruction=persona_instruction(self.native.persona)).unwrap()["batch_id"]
        calls = len(self.native.provider.client.state.calls)
        async def respond(*_):
            return completion('{"summary":"已完成核对。","proposals":[],"pending_decisions":[]}')
        self.native.provider.client.state.behavior = respond
        queue_routes = [(path, handler) for (path, method), handler in self.routes.items() if path.endswith("/reflections/queue")]
        self.assertEqual(len(queue_routes), 4)
        original = None
        for path, handler in queue_routes:
            view = handler.__self__.controller
            if view.target_id == "first" and view.role_id == "role-a":
                original = path
                continue
            result = await self.request(path, data={"batch_id": batch, "operation_key": "foreign"})
            self.assertEqual(result["status"], "error", result)
        self.assertEqual(app.runtime.read_one("SELECT COUNT(*) n FROM memory_reflection_jobs", ())["n"], 0)
        result = await self.request(original, data={"batch_id": batch, "operation_key": "original"})
        self.assertEqual(result["status"], "ok", result)
        job_id = result["data"]["job_id"]
        for _ in range(10):
            self.clock.advance(timedelta(seconds=1))
            app.notify()
            await asyncio.sleep(0.03)
            row = app.runtime.read_one("SELECT state, result_code FROM memory_reflection_jobs WHERE job_id = ?", (job_id,))
            if row[0] == "complete":
                break
        self.assertEqual(row[0], "complete", {**dict(row), "reflection": app.memory_reflection.status(context, batch).unwrap()})
        self.assertEqual(len(self.native.provider.client.state.calls), calls + 1)
        for platform in self.native.platforms.values():
            self.assertEqual(platform.client._api._wsr_api.calls, [])
        (await self.controller.stop()).unwrap()
        self.controller.unregister_routes()
        self.assertEqual(self.native.registered_web_apis, [])
