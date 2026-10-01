from datetime import timedelta
import json
import unittest

from companion_v2.execution.models import TaskContext, stamp
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.memory import codec
from companion_v2.memory.management import MemoryManagement
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE


class MemoryCommandsHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def target_context(self):
        return TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap(),
                           AudienceRef(SCOPE, (self.important.subject,)))

    def request(self, app, context, *, evidence=None):
        commands = app.memory_commands
        payload = dict(namespace="personal", visibility="private", purpose="reply", proposal_id="host-proposal",
                       operation="no_op", target_atom_id=None, expected_revision=None)
        if evidence:
            payload.update(operation="add", subject=dict(kind="companion.person", ref=context.actor.subject.subject_id),
                predicate="饮用偏好", object="不喝咖啡", representation="用户不喝咖啡。", retention="durable",
                attribution="user", polarity="affirmed", evidence_refs=[evidence])
        return dict(schema_version="memory.proposal.v1", capability_id="memory.proposal.submit", capability_version="1.0",
            provider_id=commands.provider_id, provider_generation=commands.provider_generation,
            request_id="host-request", trace_id="host-trace", idempotency_key="host-save",
            deadline_at=stamp(self.clock.now() + timedelta(minutes=2)), scope=commands.scope_for_context(context),
            budget=dict(max_input_bytes=65536, max_output_bytes=65536, max_model_calls=0), payload=payload)

    def actual_request(self, host):
        app = host.application
        batch = host.receive(self.event("source", text="我不喝咖啡")).unwrap()
        context = self.context(app, batch)
        row = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (batch,))
        source = codec.source(json.loads(row["event_json"])["source"])
        reference = app.memory_commands.offer_source(context, source)
        return context, self.request(app, context, evidence=reference)

    def lookup(self, app, context, key="host-save"):
        bound = app.provider_registry.bind(context, capability_id="memory.operation.get", capability_version="1.0",
                                           provider_id="companion_v2.memory").unwrap()
        request = dict(schema_version="memory.operation-query.v1", capability_id="memory.operation.get",
            capability_version="1.0", provider_id=bound.provider.provider, provider_generation=bound.provider.generation,
            request_id="lookup", trace_id="lookup-trace", deadline_at=stamp(self.clock.now() + timedelta(minutes=2)),
            scope=bound.scope, budget=dict(max_input_bytes=65536, max_model_calls=0),
            payload=dict(namespace="personal", visibility="private", purpose="reply",
                         capability_id="memory.proposal.submit", idempotency_key=key))
        return app.provider_registry.invoke(context, bound.binding_ref, request).unwrap()

    async def test_host_submits_and_discovers_receipt_reads_without_model_or_sender_calls(self):
        host = self.host()
        app, context = host.application, self.target_context()
        result = app.memory_commands.handle(context, self.request(app, context))
        self.assertEqual(result["reason_code"], "host_not_running")
        await self.start(host)
        context, request = self.actual_request(host)
        result = app.memory_commands.handle(context, request)
        self.assertEqual(result["status"], "succeeded", result)
        found = self.lookup(app, context)
        self.assertEqual(found["output"], result["output"])
        for capability in ("memory.query", "memory.operation.get"):
            catalog = app.provider_registry.discover(context, capability_id=capability).unwrap()
            self.assertEqual([item["capability"]["capability_id"] for item in catalog], [capability])
        self.assertEqual(app.provider_registry.discover(context, capability_id="memory.proposal.submit").unwrap(), ())
        self.assertEqual((self.called, self.sent), ([], []))
        await app.close()
        self.assertEqual(app.memory_commands.handle(context, request)["reason_code"], "host_not_running")
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_restarted_host_looks_up_original_generation_and_replays_original_receipt(self):
        first = await self.start()
        context, request = self.actual_request(first)
        saved = first.application.memory_commands.handle(context, request)
        self.assertEqual(saved["status"], "succeeded")
        await first.application.close()
        second = self.host(runtime_identity=RuntimeIdentity("companion", "runtime-2", "astrbot", "host"))
        await self.start(second, task_generation=1, model_generation=1)
        app = second.application
        self.assertEqual(self.lookup(app, context)["output"], saved["output"])
        self.assertNotEqual(app.memory_commands.provider_generation, request["provider_generation"])
        request.update(provider_generation=app.memory_commands.provider_generation,
                       scope=app.memory_commands.scope_for_context(context))
        replay = app.memory_commands.handle(context, request)
        self.assertEqual(replay["output"], saved["output"])
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_supervisor_takeover_fences_old_command_before_writing(self):
        first = await self.start()
        context, request = self.actual_request(first)
        second = self.host()
        await self.start(second, task_generation=1, model_generation=1)
        result = first.application.memory_commands.handle(context, request)
        self.assertEqual((result["status"], result["reason_code"]), ("unavailable", "supervisor_fenced"))
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_operations", ())["n"], 0)

    async def test_memory_disable_blocks_commands_and_receipt_discovery(self):
        host = await self.start()
        app = host.application
        context, request = self.actual_request(host)
        manager = MemoryManagement(app.memory, self.core)
        snapshot = manager.settings(context).unwrap()
        manager.patch_settings(context, operation_key="disable-memory", expected_edit_token=snapshot["edit_token"],
                               changes={"memory.enabled": False}).unwrap()
        result = app.memory_commands.handle(context, request)
        self.assertEqual((result["status"], result["reason_code"]), ("permission_denied", "memory_disabled"))
        self.assertEqual(app.provider_registry.discover(context, capability_id="memory.operation.get").unwrap(), ())
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_atoms", ())["n"], 0)


if __name__ == "__main__":
    unittest.main()
