from datetime import timedelta
from dataclasses import replace
import json
import unittest

from companion_v2.execution.models import stamp
from companion_v2.memory import codec
from companion_v2.identity_policy.personas import RuntimeIdentity
from tests.test_host_application import HostFixture
from tests import test_memory_commands_host as commands_support
from tests.memory_stream_support import StreamFixture


class MemoryStreamHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    request = StreamFixture.request
    control = StreamFixture.control
    subscribe = StreamFixture.subscribe
    target = StreamFixture.target
    start_snapshot = StreamFixture.start
    next_page = StreamFixture.next_page
    poll = StreamFixture.poll
    ack_batch = StreamFixture.ack_batch
    ack_snapshot = StreamFixture.ack_snapshot

    async def prepared(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event("source", text="我不喝咖啡")).unwrap()
        context = HostFixture.context(self, app, batch)
        row = app.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (batch,))
        source = codec.source(json.loads(row["event_json"])["source"])
        reference = app.memory_commands.offer_source(context, source)
        request = commands_support.MemoryCommandsHostTests.request(self, app, context, evidence=reference)
        self.context = context
        self.streams, self.consumer = app.memory_subscriptions, app.memory_reference_views
        return host, request

    async def test_pending_lookup_boundary_subscription_and_restart_share_the_same_host(self):
        host, request = await self.prepared()
        app = host.application
        request["payload"]["defer_until_boundary"] = True
        pending = app.memory_commands.handle(self.context, request)
        self.assertEqual(pending["status"], "pending")
        lookup = commands_support.MemoryCommandsHostTests.lookup(self, app, self.context)
        self.assertEqual(lookup["status"], "pending")
        resolved = app.memory_commands.resolve_pending(self.context, pending["output"]["operation_id"], decision="accept",
            deadline_at=stamp(self.clock.now() + timedelta(seconds=30)))
        self.assertEqual(resolved["status"], "succeeded")
        bound = self.subscribe()
        self.consumer.bind(self.context, "host-view", bound).unwrap()
        page = self.start_snapshot(bound)
        self.consumer.stage_page(self.context, "host-view", page).unwrap()
        checkpoint = self.consumer.activate(self.context, "host-view").unwrap()
        self.ack_snapshot(bound, page, checkpoint)
        view = self.consumer.read(self.context, "host-view").unwrap()
        self.assertEqual(view["items"][0]["atom_id"], resolved["output"]["atom_id"])
        self.assertEqual((self.called, self.sent), ([], []))
        await app.close()
        self.assertEqual(self.poll(bound).failure.code, "host_not_running")
        second = self.host(runtime_identity=RuntimeIdentity("companion", "runtime-2", "astrbot", "host"))
        await self.start(second, task_generation=1, model_generation=1)
        self.streams, self.consumer = second.application.memory_subscriptions, second.application.memory_reference_views
        resumed = self.subscribe(key="restarted", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual(resumed["subscription_state"], "live")
        self.consumer.bind(self.context, "host-view", resumed).unwrap()
        self.assertEqual(self.consumer.read(self.context, "host-view").unwrap()["items"], view["items"])
        record = second.application.runtime.read_one("SELECT record_json FROM memory_atoms WHERE atom_id = ?",
                                                      (resolved["output"]["atom_id"],))
        proposal = codec.proposal(json.loads(record["record_json"])["proposal"])
        second.application.memory.writer.submit(self.context, replace(proposal, predicate="其他口味", defer_until_boundary=False),
                                                operation_key="after-restart").unwrap()
        batch = self.poll(resumed).unwrap()
        applied = self.consumer.apply_batch(self.context, "host-view", batch).unwrap()
        self.ack_batch(resumed, batch, applied)
        self.assertEqual(len(self.consumer.read(self.context, "host-view").unwrap()["items"]), 2)
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_takeover_refuses_old_stream_and_consumer_without_fact_side_effects(self):
        host, _ = await self.prepared()
        bound = self.subscribe()
        self.consumer.bind(self.context, "host-view", bound).unwrap()
        second = self.host()
        await self.start(second, task_generation=1, model_generation=1)
        self.assertEqual(self.poll(bound).failure.code, "supervisor_fenced")
        self.assertEqual(self.consumer.read(self.context, "host-view").failure.code, "supervisor_fenced")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_operations", ())["n"], 0)
        self.assertEqual((self.called, self.sent), ([], []))


if __name__ == "__main__":
    unittest.main()
