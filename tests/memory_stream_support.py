from datetime import timedelta
from contextlib import contextmanager
import sqlite3
from unittest.mock import patch

from companion_v2.execution.models import require, stamp
from companion_v2.foundation.outcome import Outcome
from companion_v2.memory.service import MemoryService
from companion_v2.memory.subscriptions import MemorySubscriptions
from companion_v2.memory.stream_consumer import MemoryReferenceConsumer
from companion_v2.memory.stream_store import LIMITS
from tests.memory_support import MemoryFixture
from tests.test_memory_wire import runtime_scope


@contextmanager
def commit_fault(runtime, *, after):
    connection = runtime._require_connection()

    class FaultyConnection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, statement, *args):
            if statement == "COMMIT" and runtime._write_depth:
                if after:
                    connection.execute(statement, *args)
                raise sqlite3.OperationalError("simulated commit acknowledgement failure")
            return connection.execute(statement, *args)

    with patch.object(runtime, "_require_connection", return_value=FaultyConnection()):
        yield


class StreamFixture(MemoryFixture):
    def setUp(self):
        super().setUp()
        self.service = MemoryService(self.tasks)
        self.streams = MemorySubscriptions(self.service, provider_id="companion_v2.memory", provider_generation="stream-1",
            scope_for_context=runtime_scope, require_running=lambda: require(self.tasks.check_generation()))
        self.consumer = MemoryReferenceConsumer(self.streams)

    def request(self, capability, payload, *, key=None, streams=None, context=None):
        streams, context = streams or self.streams, context or self.context
        request = dict(schema_version={"subscribe": "memory.subscribe.v1", "resync": "memory.resync.v1", "ack": "memory.ack.v1"}[capability],
            capability_id="memory.changed." + capability, capability_version="1.0", provider_id=streams.provider_id,
            provider_generation=streams.provider_generation, request_id="request", trace_id="trace",
            scope=streams.scope_for_context(context), deadline_at=stamp(self.clock.now() + timedelta(minutes=2)),
            budget=dict(max_input_bytes=65536, max_output_bytes=65536, max_model_calls=0), payload=payload)
        if key is not None:
            request["idempotency_key"] = key
        return request

    def control(self, capability, payload, *, key=None, streams=None, context=None):
        streams, context = streams or self.streams, context or self.context
        result = streams.handle(context, self.request(capability, payload, key=key, streams=streams, context=context))
        self.assertEqual(result["status"], "succeeded", result)
        return result["output"]

    def subscribe(self, *, key="subscribe", generation="consumer-1", mode="snapshot", checkpoint=None,
                  view="current_projection", kinds=None, limits=None, streams=None, context=None):
        payload = dict(namespace="personal", visibility="private", purpose="reply", subscriber_generation=generation,
            projection_kind="references", view_kind=view, change_kinds=kinds or ["added", "corrected", "retracted", "expired"],
            limits={**LIMITS, "max_batch_items": 1, "recovery_deadline_at": stamp(self.clock.now() + timedelta(hours=1)), **(limits or {})},
            start={"mode": mode, **({"checkpoint": checkpoint} if checkpoint else {})})
        return self.control("subscribe", payload, key=key, streams=streams, context=context)

    def target(self, bound):
        return {key: bound[key] for key in ("subscription_id", "subscriber_generation")}

    def start(self, bound, key="snapshot", *, context=None):
        return self.control("resync", self.target(bound) | {"action": "start"}, key=key, context=context)

    def next_page(self, bound, previous, *, context=None):
        return self.control("resync", self.target(bound) | dict(action="page", snapshot_id=previous["snapshot"]["snapshot_id"],
            snapshot_epoch=previous["snapshot"]["snapshot_epoch"], page_cursor=previous["next_page_cursor"]), context=context)

    def poll(self, bound, *, streams=None, context=None):
        result = (streams or self.streams).poll(context or self.context, **self.target(bound),
            deadline_at=stamp(self.clock.now() + timedelta(minutes=2)))
        return Outcome.success(result.unwrap()["batch"] or {}) if result.is_success else result

    def ack_batch(self, bound, batch, checkpoint, *, context=None):
        return self.control("ack", self.target(bound) | dict(lease_id=batch["lease"]["lease_id"],
            target=dict(kind="batch", batch_id=batch["batch_id"]), checkpoint=checkpoint), context=context)

    def ack_snapshot(self, bound, page, checkpoint, *, context=None):
        return self.control("ack", self.target(bound) | dict(lease_id=page["activation_lease"]["lease_id"],
            target=dict(kind="snapshot", snapshot_id=page["snapshot"]["snapshot_id"],
                        completion_token=page["completion"]["completion_token"]), checkpoint=checkpoint), context=context)

    def synchronized(self, *, bound=None, consumer_id="test-view", context=None):
        context = context or self.context
        bound = bound or self.subscribe(context=context)
        self.consumer.bind(context, consumer_id, bound).unwrap()
        page = self.start(bound, context=context)
        while True:
            self.consumer.stage_page(context, consumer_id, page).unwrap()
            if page["next_page_cursor"] is None:
                break
            page = self.next_page(bound, page, context=context)
        while True:
            batch = self.poll(bound, context=context).unwrap()
            if not batch:
                break
            checkpoint = self.consumer.apply_batch(context, consumer_id, batch).unwrap()
            self.ack_batch(bound, batch, checkpoint, context=context)
        checkpoint = self.consumer.activate(context, consumer_id).unwrap()
        self.ack_snapshot(bound, page, checkpoint, context=context)
        return bound, checkpoint
