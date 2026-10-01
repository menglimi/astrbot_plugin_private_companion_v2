from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import unittest

from companion_v2.execution.models import require, stamp
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.memory.models import AtomRef
from companion_v2.memory.service import MemoryService
from companion_v2.memory.subscriptions import MemorySubscriptions
from companion_v2.memory.stream_consumer import MemoryReferenceConsumer
from tests.test_memory_wire import runtime_scope
from tests.memory_stream_support import StreamFixture


class MemorySubscriptionTests(StreamFixture, unittest.TestCase):
    def test_snapshot_and_live_add_correct_retract_are_reference_only(self):
        original = self.proposed()
        atom = self.remember(original)
        bound, _ = self.synchronized()
        self.assertEqual(self.consumer.read(self.context, "test-view").unwrap()["items"][0]["atom_id"], atom.atom_id)
        for number, operation in enumerate(("correct", "retract"), 2):
            item = replace(original, operation=operation, target=AtomRef(atom.atom_id, number-1),
                object="喝茶", representation="改为喝茶", evidence=(self.evidence("新声明" + str(number)),))
            self.memory.submit(self.context, item, operation_key=str(number)).unwrap()
            batch = self.poll(bound).unwrap()
            self.assertNotIn("喝茶", str(batch))
            checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
            self.ack_batch(bound, batch, checkpoint)
        current = self.consumer.read(self.context, "test-view").unwrap()
        self.assertEqual(current["items"][0]["item_kind"], "tombstone")
        self.assertEqual(current["items"][0]["atom_revision"], 3)

    def test_snapshot_pages_plus_concurrent_changes_catch_up_before_activation(self):
        first = self.remember()
        second = self.remember(replace(self.proposed(), predicate="其他"), "other")
        bound = self.subscribe()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        page = self.start(bound)
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        self.assertIsNotNone(page["next_page_cursor"])
        self.memory.submit(self.context, replace(self.proposed(), operation="correct", target=first,
            evidence=(self.evidence("改变了"),), object="喝茶", representation="现在喝茶"), operation_key="correct").unwrap()
        final = self.next_page(bound, page)
        self.consumer.stage_page(self.context, "test-view", final).unwrap()
        self.assertFalse(self.consumer.activate(self.context, "test-view").is_success)
        tail = self.poll(bound).unwrap()
        self.assertEqual(tail["delivery_mode"], "snapshot_tail")
        checkpoint = self.consumer.apply_batch(self.context, "test-view", tail).unwrap()
        self.assertEqual(self.ack_batch(bound, tail, checkpoint)["subscription_state"], "resyncing")
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        self.ack_snapshot(bound, final, checkpoint)
        items = {i["atom_id"]: i["atom_revision"] for i in self.consumer.read(self.context, "test-view").unwrap()["items"]}
        self.assertEqual(items, {first.atom_id: 2, second.atom_id: 1})

    def test_batch_apply_and_ack_duplicates_are_durable_and_idempotent(self):
        bound, _ = self.synchronized()
        self.remember()
        batch = self.poll(bound).unwrap()
        self.assertEqual(self.poll(bound).unwrap(), batch)
        checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        self.assertEqual(self.consumer.apply_batch(self.context, "test-view", batch).unwrap(), checkpoint)
        self.assertEqual(self.ack_batch(bound, batch, checkpoint)["ack_state"], "accepted")
        self.assertEqual(self.ack_batch(bound, batch, checkpoint)["ack_state"], "already_accepted")
        self.assertEqual(self.poll(bound).unwrap(), {})
        self.assertEqual(len(self.consumer.read(self.context, "test-view").unwrap()["items"]), 1)

    def test_restart_recovers_after_apply_before_ack_and_fences_old_generation(self):
        bound, _ = self.synchronized()
        self.remember()
        batch = self.poll(bound).unwrap()
        checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        tasks, _, _ = self.components(self.open_runtime())
        streams = MemorySubscriptions(MemoryService(tasks), provider_id=self.streams.provider_id, provider_generation="stream-2",
            scope_for_context=runtime_scope, require_running=lambda: require(tasks.check_generation()))
        resumed = self.subscribe(key="restart", generation="consumer-2", mode="resume", checkpoint=checkpoint, streams=streams)
        self.assertEqual(resumed["subscription_state"], "live")
        consumer = MemoryReferenceConsumer(streams)
        consumer.bind(self.context, "test-view", resumed).unwrap()
        self.assertEqual(len(consumer.read(self.context, "test-view").unwrap()["items"]), 1)
        self.assertEqual(self.poll(resumed, streams=streams).unwrap(), {})
        self.assertFalse(self.poll(bound, streams=streams).is_success)

    def test_resume_after_projection_activation_before_ack(self):
        self.remember()
        bound = self.subscribe()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        page = self.start(bound)
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        resumed = self.subscribe(key="resume", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual(resumed["subscription_state"], "live")
        self.consumer.bind(self.context, "test-view", resumed).unwrap()
        self.assertEqual(len(self.consumer.read(self.context, "test-view").unwrap()["items"]), 1)

    def test_forged_checkpoint_cannot_skip_a_batch_or_activate_partial_pages(self):
        bound, checkpoint = self.synchronized()
        self.remember()
        batch = self.poll(bound).unwrap()
        forged = deepcopy(checkpoint)
        forged["stream_cursor"] = batch["to_cursor"]
        payload = self.target(bound) | dict(lease_id=batch["lease"]["lease_id"], target=dict(kind="batch", batch_id=batch["batch_id"]), checkpoint=forged)
        rejected = self.streams.handle(self.context, self.request("ack", payload))
        self.assertEqual(rejected["reason_code"], "checkpoint_mismatch")
        self.assertEqual(self.poll(bound).unwrap(), batch)

    def test_expired_lease_reissues_same_batch_and_refuses_old_ack(self):
        bound, _ = self.synchronized(bound=self.subscribe(limits={"lease_ms": 1000}))
        self.remember()
        first = self.poll(bound).unwrap()
        checkpoint = self.consumer.apply_batch(self.context, "test-view", first).unwrap()
        self.clock.advance(timedelta(seconds=2))
        second = self.poll(bound).unwrap()
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertNotEqual(first["lease"], second["lease"])
        self.assertEqual(first["events"], second["events"])
        payload = self.target(bound) | dict(lease_id=first["lease"]["lease_id"], target=dict(kind="batch", batch_id=first["batch_id"]), checkpoint=checkpoint)
        self.assertEqual(self.streams.handle(self.context, self.request("ack", payload))["reason_code"], "ack_lease_expired")
        self.assertEqual(self.consumer.apply_batch(self.context, "test-view", second).unwrap(), checkpoint)
        self.ack_batch(bound, second, checkpoint)

    def test_revoked_or_expired_known_source_requires_replacement_before_cached_read(self):
        original = self.proposed()
        self.remember(original)
        bound, checkpoint = self.synchronized()
        self.memory.sources.revoke(original.evidence[0].source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        result = self.poll(bound)
        self.assertEqual(result.failure.code, "resync_required")
        page = self.start(bound, "replace")
        self.assertEqual(page["items"], [])
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        self.ack_snapshot(bound, page, checkpoint)
        self.assertEqual(self.consumer.read(self.context, "test-view").unwrap()["items"], [])

    def test_permission_change_invalidates_resume_and_denies_old_reads(self):
        self.remember()
        bound, checkpoint = self.synchronized()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        self.assertFalse(self.poll(bound).is_success)
        self.policy.set_tier(self.important.subject, AuthorizationTier.IMPORTANT,
            expected_revision=self.policy.revision, observed_at=self.clock.now())
        resumed = self.subscribe(key="new-auth", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual(resumed["subscription_state"], "resync_required")

    def test_filtered_notifications_advance_empty_authoritative_boundaries(self):
        bound = self.subscribe(mode="live", view="notifications", kinds=["corrected"])
        self.consumer.bind(self.context, "notifications", bound).unwrap()
        self.remember()
        batch = self.poll(bound).unwrap()
        self.assertEqual(batch["events"], [])
        self.assertNotEqual(batch["from_cursor"], batch["to_cursor"])
        checkpoint = self.consumer.apply_batch(self.context, "notifications", batch).unwrap()
        self.ack_batch(bound, batch, checkpoint)
        self.assertEqual(self.poll(bound).unwrap(), {})

    def test_snapshot_budget_is_explicit_and_cannot_activate_partial_data(self):
        self.remember()
        bound = self.subscribe(limits={"max_snapshot_bytes": 1})
        result = self.streams.handle(self.context, self.request("resync", self.target(bound) | {"action": "start"}, key="tiny"))
        self.assertEqual(result["reason_code"], "snapshot_capacity_exceeded")
        self.assertIsNone(result["output"])

    def test_retry_and_backlog_budgets_require_resync(self):
        bound, _ = self.synchronized(bound=self.subscribe(limits={"lease_ms": 1, "max_retry_attempts": 0}))
        self.remember()
        self.poll(bound).unwrap()
        self.clock.advance(timedelta(seconds=1))
        self.assertEqual(self.poll(bound).failure.code, "resync_required")

    def test_other_context_scope_and_unknown_generation_cannot_poll(self):
        bound, _ = self.synchronized()
        self.assertFalse(self.streams.poll(self.context, bound["subscription_id"], "fake",
            deadline_at=stamp(self.clock.now() + timedelta(seconds=20))).is_success)
        other = self.context_for(self.core)
        self.assertFalse(self.streams.poll(other, **self.target(bound), deadline_at=stamp(self.clock.now() + timedelta(seconds=20))).is_success)


if __name__ == "__main__":
    unittest.main()
