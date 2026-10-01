from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskContext, stamp
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.memory import codec
from companion_v2.memory.management import MemoryManagement
from companion_v2.memory.models import Proposal
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE


class MemoryProviderHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def target_context(self):
        return TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap(),
                           AudienceRef(SCOPE, (self.important.subject,)))

    def bind(self, app, context):
        return app.provider_registry.bind(context, capability_id="memory.query", capability_version="1.0",
                                           provider_id="companion_v2.memory").unwrap()

    def request(self, bound):
        return dict(schema_version="memory.query.v1", capability_id="memory.query", capability_version="1.0",
            provider_id=bound.provider.provider, provider_generation=bound.provider.generation,
            request_id="host-request", trace_id="host-trace", deadline_at=stamp(self.clock.now() + timedelta(minutes=2)),
            scope=bound.scope, budget=dict(max_input_bytes=16384, max_output_bytes=20000, max_model_calls=0),
            payload=dict(namespace="personal", visibility="private", purpose="reply", query_intent="咖啡"))

    async def test_host_discovers_and_reads_a_real_fact_without_model_or_sender_calls(self):
        host = self.host()
        app = host.application
        context = self.target_context()
        self.assertEqual(app.provider_registry.discover(context, capability_id="memory.query").failure.code,
                         "host_not_running")
        await self.start(host)
        batch = host.receive(self.event("memory", text="我不喝咖啡")).unwrap()
        context = self.context(app, batch)
        row = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (batch,))
        source = codec.source(json.loads(row["event_json"])["source"])
        evidence = app.memory.writer.access.capture(context, source)
        saved = app.memory.writer.submit(context, Proposal("add", predicate="饮用偏好", object="不喝咖啡",
            representation="用户不喝咖啡。", evidence=(evidence,)), operation_key="host-memory").unwrap()
        entries = app.provider_registry.discover(context, capability_id="memory.query").unwrap()
        self.assertEqual(len(entries), 1)
        bound = self.bind(app, context)
        self.assertEqual((bound.scope["runtime_instance_id"], bound.scope["ecosystem_id"], bound.scope["host_kind"]),
                         ("runtime-1", "companion", "astrbot"))
        result = app.provider_registry.invoke(context, bound.binding_ref, self.request(bound)).unwrap()
        self.assertEqual(result["output"]["items"][0]["atom_id"], saved["atom_id"])
        self.assertEqual((self.called, self.sent), ([], []))
        await app.close()
        self.assertEqual(app.provider_registry.invoke(context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_registry_closed")

    async def test_configuration_changes_fence_old_bindings_and_disable_discovery(self):
        host = await self.start()
        app, context = host.application, self.target_context()
        manager = MemoryManagement(app.memory, self.core)
        bound = self.bind(app, context)
        snapshot = manager.settings(context).unwrap()
        manager.patch_settings(context, operation_key="query-budget", expected_edit_token=snapshot["edit_token"],
            changes={"memory.query_chars": 1024}).unwrap()
        self.assertEqual(app.provider_registry.invoke(context, bound.binding_ref, self.request(bound)).failure.code,
                         "provider_binding_stale")
        fresh = self.bind(app, context)
        snapshot = manager.settings(context).unwrap()
        manager.patch_settings(context, operation_key="disable", expected_edit_token=snapshot["edit_token"],
            changes={"memory.enabled": False}).unwrap()
        self.assertEqual(app.provider_registry.discover(context, capability_id="memory.query").unwrap(), ())
        self.assertEqual(app.provider_registry.invoke(context, fresh.binding_ref, self.request(fresh)).failure.code,
                         "memory_disabled")

    async def test_restart_issues_a_fresh_provider_generation_and_refuses_previous_binding(self):
        first = await self.start()
        context = self.target_context()
        original = self.bind(first.application, context)
        await first.application.close()
        second = self.host(runtime_identity=RuntimeIdentity("companion", "runtime-2", "astrbot", "host"))
        await self.start(second, task_generation=1, model_generation=1)
        fresh = self.bind(second.application, context)
        self.assertNotEqual(fresh.provider.generation, original.provider.generation)
        self.assertEqual(fresh.owner_ref, original.owner_ref)
        self.assertEqual(fresh.scope["runtime_instance_id"], "runtime-2")
        self.assertEqual(second.application.provider_registry.invoke(context, original.binding_ref,
                         self.request(original)).failure.code, "provider_binding_unavailable")
        result = second.application.provider_registry.invoke(context, fresh.binding_ref, self.request(fresh)).unwrap()
        self.assertEqual(result["status"], "succeeded")

    async def test_supervisor_takeover_fences_old_registry_before_it_touches_memory(self):
        first = await self.start()
        context = self.target_context()
        bound = self.bind(first.application, context)
        second = self.host()
        await self.start(second, task_generation=1, model_generation=1)
        self.assertEqual(first.application.provider_registry.invoke(context, bound.binding_ref,
            self.request(bound)).failure.code, "supervisor_fenced")
        fresh = self.bind(second.application, context)
        self.assertNotEqual(fresh.provider.generation, bound.provider.generation)


if __name__ == "__main__":
    unittest.main()
