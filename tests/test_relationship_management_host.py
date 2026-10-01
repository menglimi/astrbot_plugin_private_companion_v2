from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

# The host fixture redirects the SDK import-time data root before SDK imports.
from tests import test_astrbot_staging_host as host_support
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.management_identity import dashboard_operator
from astrbot_host.relationships_api import MANAGEMENT_PREFIX
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.relationships.models import RelationshipMemory, RelationshipMemoryKind
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW


class RelationshipManagementHostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-relationship-api-")
        self.addCleanup(self.temporary.cleanup)
        self.native = host_support.WebContext()
        self.types = host_support.NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider,
                                                    host_support.NS, host_support.NS, FakeReverseApi)
        self.controller = host_support.AstrBotStagingController(self.native, host_support.host_config(),
            Path(self.temporary.name) / "profiles", native_types=self.types, now=lambda: NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()
        self.routes = {route: handler for route, handler, _, _ in self.native.registered_web_apis}

    async def request(self, *, username="admin", data=None, raw=None, query=""):
        raw = raw if raw is not None else json.dumps(data).encode("utf-8") if data is not None else b""
        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}
        mutation = data is not None or bool(raw)
        path = MANAGEMENT_PREFIX + ("/command" if mutation else "")
        request = Request({"type": "http", "method": "POST" if mutation else "GET", "path": path,
            "headers": [(b"content-type", b"application/json")], "query_string": query.encode("utf-8")}, receive=receive)
        with bind_request_context(PluginRequest(request, username=username)):
            return await self.routes[path]()

    async def initialize(self):
        (await self.controller.initialize_profile()).unwrap()
        session = self.controller.session
        captured = (await session.bridge.capture(FakeEvent(self.native))).unwrap()
        event = session.host.inbound.ingest(captured, capability="text").unwrap()
        target = session.profile.target
        record = RelationshipMemory("memory-a", RoleOwnerRef(target.scope.installation_id,
            target.scope.bot_id, target.role_binding.role.subject_id), target.actor.subject,
            target.scope, RelationshipMemoryKind.CONTEXT, "这是角色那时对这段关系的理解。", (event.source,), NOW, NOW)
        session.application.relationship_memories._ledger.add(record)
        return target

    def body(self, item, action="review", **changes):
        return dict(memory_id=item["memory_id"], expected_revision=item["revision"], view_token=item["view_token"],
                    operation_key="request-a", action=action) | changes

    async def test_missing_login_and_unloaded_profile_create_no_data(self):
        self.assertEqual((await self.request(username=None))["data"]["code"], "dashboard_identity_required")
        self.assertEqual((await self.request())["data"]["code"], "staging_not_initialized")
        self.assertIsNone(self.controller.runtime)

    async def test_dashboard_review_uses_admin_identity_without_granting_the_chat_participant(self):
        target = await self.initialize()
        response = await self.request()
        self.assertEqual(response["status"], "ok", response)
        self.assertEqual(response["data"]["operator_name"], "admin")
        self.assertNotEqual(response["data"]["operator_id"], target.actor.subject.subject_id)
        reviewed = await self.request(data=self.body(response["data"]["items"][0]))
        self.assertEqual(reviewed["status"], "ok", reviewed)
        self.assertEqual(reviewed["data"]["item"]["attribution"]["reviewed_by"], response["data"]["operator_id"])
        self.assertEqual(await self.request(data=self.body(response["data"]["items"][0])), reviewed)
        self.assertFalse(self.controller.session.application.relationship_memories.for_relationship(
            actor=target.actor, scope=target.scope).is_success)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_body_cannot_supply_an_operator_target_or_provenance(self):
        await self.initialize()
        item = (await self.request())["data"]["items"][0]
        for extra in ({"operator": "admin"}, {"context": {}}, {"sources": []}, {"role_id": "other"}):
            response = await self.request(data=self.body(item, **extra))
            self.assertEqual(response["data"]["code"], "relationship_command_invalid")
        self.assertEqual((await self.request())["data"]["items"][0]["revision"], 1)

    async def test_duplicate_json_fields_and_invalid_queries_are_rejected(self):
        await self.initialize()
        self.assertEqual((await self.request(raw=b'{"action":"review","action":"adopt"}'))["data"]["code"],
                         "relationship_command_invalid")
        for query in ("state=unknown", "limit=-1", "limit=true", "limit=1&limit=2", "operator=admin", "after_id=" + "x" * 513):
            self.assertEqual((await self.request(query=query))["data"]["code"], "relationship_query_invalid")

    async def test_another_admin_cannot_reuse_the_original_view_and_api_key_is_not_a_human(self):
        await self.initialize()
        item = (await self.request())["data"]["items"][0]
        self.assertEqual((await self.request(username="admin-b", data=self.body(item)))["data"]["code"],
                         "relationship_view_stale")
        self.assertEqual((await self.request(username="api_key:123"))["data"]["code"], "dashboard_identity_required")

    async def test_revoked_dashboard_binding_or_tier_is_not_reprovisioned(self):
        await self.initialize()
        operator = dashboard_operator(self.controller.runtime, "admin", at=NOW)
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.STANDARD, expected_revision=policy.revision, observed_at=NOW)
        self.assertEqual((await self.request())["status"], "error")
        policy.identity.revoke_binding(operator.binding_id, revoked_at=NOW, expected_revision=policy.identity.revision)
        self.assertEqual((await self.request())["data"]["code"], "binding_revoked")

    async def test_stopped_profile_is_manageable_and_shutdown_unregisters_both_routes(self):
        await self.initialize()
        (await self.controller.stop()).unwrap()
        self.assertEqual((await self.request())["status"], "ok")
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.request())["data"]["code"], "staging_host_terminated")
