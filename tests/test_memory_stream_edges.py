from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.configuration.service import ConfigurationService
from companion_v2.memory.configuration import configuration_fields
from companion_v2.memory.management import MemoryManagement
from companion_v2.memory.service import MemoryService
from companion_v2.memory.subscriptions import MemorySubscriptions
from companion_v2.memory.stream_consumer import MemoryReferenceConsumer
from companion_v2.memory.stream_store import CLIENT_PREFIX, PREFIX
from tests.memory_stream_support import StreamFixture, commit_fault


class MemoryStreamEdgeTests(StreamFixture, unittest.TestCase):
    def count(self, table):
        return self.runtime.read_one("SELECT COUNT(*) n FROM " + table, ())["n"]

    def test_subscription_and_persistent_view_ids_cannot_cross_bots_or_personas(self):
        others = self.other_memory_owners()
        atom = self.remember()
        bound, checkpoint = self.synchronized()
        for dimension, context in others.items():
            with self.subTest(dimension=dimension):
                results = [self.poll(bound, context=context),
                           self.consumer.read(context, "test-view"),
                           self.consumer.recovery_checkpoint(context, "test-view"),
                           self.consumer.bind(context, "test-view", bound)]
                for result in results:
                    self.assertEqual(result.failure.code, "subscription_unavailable")
                request = self.request("resync", self.target(bound) | {"action": "start"},
                                       key="foreign-start", context=context)
                result = self.streams.handle(context, request)
                self.assertEqual((result["reason_code"], result["output"]), ("subscription_unavailable", None))
        self.assertEqual(self.consumer.recovery_checkpoint(self.context, "test-view").unwrap()["checkpoint"], checkpoint)
        self.assertEqual([item["atom_id"] for item in self.consumer.read(self.context, "test-view").unwrap()["items"]],
                         [atom.atom_id])
        self.assertEqual(self.poll(bound).unwrap(), {})

    def test_checkpoint_resume_cannot_move_a_projection_to_another_bot_or_persona(self):
        others = self.other_memory_owners()
        self.remember()
        bound, checkpoint = self.synchronized()
        for dimension, context in others.items():
            with self.subTest(dimension=dimension):
                payload = dict(namespace="personal", visibility="private", purpose="reply",
                    subscriber_generation="consumer-2", projection_kind="references", view_kind="current_projection",
                    change_kinds=["added", "corrected", "retracted", "expired"], limits=bound["limits"],
                    start=dict(mode="resume", checkpoint=checkpoint))
                result = self.streams.handle(context, self.request("subscribe", payload, key="resume", context=context))
                self.assertEqual((result["reason_code"], result["output"]), ("checkpoint_binding_mismatch", None))
        resumed = self.subscribe(key="resume", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.consumer.bind(self.context, "test-view", resumed).unwrap()
        self.assertEqual(self.consumer.read(self.context, "test-view").unwrap()["checkpoint"], checkpoint)

    def test_same_subscription_keys_and_consumer_ids_keep_independent_snapshots_and_batches(self):
        contexts = {"original": self.context, **self.other_memory_owners()}
        atom = self.remember()
        bounds = {dimension: self.synchronized(context=context)[0] for dimension, context in contexts.items()}
        self.assertEqual(len({bound["subscription_id"] for bound in bounds.values()}), 3)
        self.assertEqual(len({bound["binding"]["owner_ref"] for bound in bounds.values()}), 3)
        for dimension, context in contexts.items():
            items = self.consumer.read(context, "test-view").unwrap()["items"]
            self.assertEqual([item["atom_id"] for item in items], [atom.atom_id] if dimension == "original" else [])
        added = self.remember(replace(self.proposed(), predicate="另一个偏好"), key="next")
        batch = self.poll(bounds["original"]).unwrap()
        for dimension, context in contexts.items():
            if dimension == "original":
                continue
            with self.subTest(dimension=dimension):
                self.assertEqual(self.poll(bounds[dimension], context=context).unwrap(), {})
                self.assertFalse(self.consumer.apply_batch(context, "test-view", batch).is_success)
                result = self.consumer.read(context, "test-view").unwrap()
                self.assertEqual(result["items"], [])
        checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        self.ack_batch(bounds["original"], batch, checkpoint)
        self.assertEqual({item["atom_id"] for item in self.consumer.read(self.context, "test-view").unwrap()["items"]},
                         {atom.atom_id, added.atom_id})

    def test_resumed_projection_continues_to_ack_new_batches_with_original_snapshot(self):
        self.remember()
        bound, checkpoint = self.synchronized()
        resumed = self.subscribe(key="resume", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.consumer.bind(self.context, "test-view", resumed).unwrap()
        original = self.proposed()
        atom = self.remember(replace(original, predicate="新偏好"), "next")
        self.assertEqual(self.consumer.read(self.context, "test-view").failure.code, "consumer_projection_behind")
        batch = self.poll(resumed).unwrap()
        applied = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        self.assertEqual(applied["snapshot"], checkpoint["snapshot"])
        self.ack_batch(resumed, batch, applied)
        self.assertIn(atom.atom_id, {i["atom_id"] for i in self.consumer.read(self.context, "test-view").unwrap()["items"]})
        self.assertFalse(self.poll(bound).is_success)

    def test_rebinding_same_subscription_preserves_current_cursor(self):
        bound, _ = self.synchronized()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        self.remember()
        batch = self.poll(bound).unwrap()
        checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        self.ack_batch(bound, batch, checkpoint)

    def test_missing_local_projection_cannot_claim_a_resumed_checkpoint(self):
        self.remember()
        _, checkpoint = self.synchronized()
        resumed = self.subscribe(key="resume", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        result = self.consumer.bind(self.context, "empty-view", resumed)
        self.assertEqual(result.failure.code, "consumer_checkpoint_unavailable")

    def test_duplicate_and_out_of_order_pages_never_activate_a_partial_snapshot(self):
        self.remember()
        self.remember(replace(self.proposed(), predicate="其他"), "other")
        bound = self.subscribe()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        first = self.start(bound)
        final = self.next_page(bound, first)
        self.assertEqual(self.consumer.stage_page(self.context, "test-view", final).failure.code, "consumer_snapshot_page_gap")
        checkpoint = self.consumer.stage_page(self.context, "test-view", first).unwrap()
        self.assertEqual(self.consumer.stage_page(self.context, "test-view", first).unwrap(), checkpoint)
        self.assertEqual(self.consumer.activate(self.context, "test-view").failure.code, "consumer_snapshot_incomplete")
        self.consumer.stage_page(self.context, "test-view", final).unwrap()
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        self.ack_snapshot(bound, final, checkpoint)
        self.assertEqual(len(self.consumer.read(self.context, "test-view").unwrap()["items"]), 2)

    def test_old_snapshot_epoch_and_closed_start_key_cannot_be_reused(self):
        bound = self.subscribe()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        old = self.start(bound, "old")
        self.assertEqual(self.start(bound, "old"), old)
        new = self.start(bound, "new")
        self.assertEqual(self.consumer.stage_page(self.context, "test-view", old).failure.code, "snapshot_page_not_issued")
        self.consumer.stage_page(self.context, "test-view", new).unwrap()
        self.ack_snapshot(bound, new, self.consumer.activate(self.context, "test-view").unwrap())
        for key in ("old", "new"):
            result = self.streams.handle(self.context, self.request("resync", self.target(bound) | {"action": "start"}, key=key))
            self.assertEqual(result["reason_code"], "resync_epoch_closed")
        self.assertEqual(self.poll(bound).unwrap(), {})

    def test_expired_snapshot_or_activation_lease_needs_an_explicit_new_epoch(self):
        bound = self.subscribe(limits={"lease_ms": 1})
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        page = self.start(bound)
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        self.clock.advance(timedelta(seconds=1))
        payload = self.target(bound) | dict(lease_id=page["activation_lease"]["lease_id"],
            target=dict(kind="snapshot", snapshot_id=page["snapshot"]["snapshot_id"],
                        completion_token=page["completion"]["completion_token"]), checkpoint=checkpoint)
        self.assertEqual(self.streams.handle(self.context, self.request("ack", payload))["reason_code"], "ack_lease_expired")
        self.assertFalse(self.consumer.read(self.context, "test-view").is_success)
        self.clock.advance(timedelta(minutes=11))
        request = self.request("resync", self.target(bound) | {"action": "start"}, key="snapshot")
        self.assertEqual(self.streams.handle(self.context, request)["reason_code"], "snapshot_expired")
        fresh = self.start(bound, "fresh")
        self.consumer.stage_page(self.context, "test-view", fresh).unwrap()
        self.ack_snapshot(bound, fresh, self.consumer.activate(self.context, "test-view").unwrap())

    def test_same_batch_add_then_retract_keeps_the_tombstone_and_event_order(self):
        bound, _ = self.synchronized(bound=self.subscribe(limits={"max_batch_items": 64}))
        original = self.proposed()
        atom = self.remember(original)
        self.memory.submit(self.context, replace(original, operation="retract", target=atom), operation_key="retract").unwrap()
        batch = self.poll(bound).unwrap()
        self.assertEqual([e["payload"]["change_kind"] for e in batch["events"]], ["added", "retracted"])
        checkpoint = self.consumer.apply_batch(self.context, "test-view", batch).unwrap()
        self.ack_batch(bound, batch, checkpoint)
        item = self.consumer.read(self.context, "test-view").unwrap()["items"][0]
        self.assertEqual((item["item_kind"], item["atom_revision"]), ("tombstone", 2))

    def test_natural_expiry_and_future_validity_invalidate_cached_views_without_writes(self):
        expiring = self.remember(self.proposed(retention="short", valid_to=self.clock.now() + timedelta(seconds=2)))
        future = self.remember(replace(self.proposed(), predicate="未来", valid_from=self.clock.now() + timedelta(seconds=3)), "future")
        bound, _ = self.synchronized()
        self.assertEqual([i["atom_id"] for i in self.consumer.read(self.context, "test-view").unwrap()["items"]], [expiring.atom_id])
        self.clock.advance(timedelta(seconds=2))
        self.assertFalse(self.consumer.read(self.context, "test-view").is_success)
        page = self.start(bound, "expiry")
        self.assertEqual(page["items"], [])
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        self.ack_snapshot(bound, page, self.consumer.activate(self.context, "test-view").unwrap())
        self.clock.advance(timedelta(seconds=1))
        self.assertEqual(self.poll(bound).failure.code, "resync_required")
        page = self.start(bound, "future")
        self.assertEqual([i["atom_id"] for i in page["items"]], [future.atom_id])
        self.assertEqual(self.count("memory_changes"), 2)

    def test_retention_batch_and_consumer_byte_budgets_do_not_advance_checkpoints(self):
        for limit, value, expected in (("max_retained_log_bytes", 1, "resync_required"),
                                       ("max_batch_bytes", 1, "stream_batch_budget_exceeded")):
            with self.subTest(limit=limit):
                bound = self.subscribe(key=limit, mode="live", view="notifications", limits={limit: value})
                self.remember(replace(self.proposed(), predicate=limit), limit)
                self.assertEqual(self.poll(bound).failure.code, expected)
                self.assertIsNone(self.streams.store.load(self.context, bound["subscription_id"])["inflight"])
        bound = self.subscribe(key="consumer-budget", mode="live", view="notifications", limits={"max_staging_bytes": 128})
        self.consumer.bind(self.context, "tiny", bound).unwrap()
        self.remember(replace(self.proposed(), predicate="小预算"), "tiny")
        result = self.consumer.apply_batch(self.context, "tiny", self.poll(bound).unwrap())
        self.assertEqual(result.failure.code, "consumer_projection_budget_exceeded")
        self.assertIsNone(self.consumer.recovery_checkpoint(self.context, "tiny").unwrap()["checkpoint"])

    def test_server_capacity_and_expiry_cleanup_are_bounded(self):
        for number in range(64):
            self.subscribe(key="slot-" + str(number))
        with self.assertRaises(AssertionError) as caught:
            self.subscribe(key="overflow")
        self.assertIn("subscription_capacity_exceeded", str(caught.exception))
        self.clock.advance(timedelta(hours=1, seconds=1))
        self.subscribe(key="new-slot")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_sessions WHERE session_id LIKE ?", (PREFIX + "%",))["n"], 1)

    def test_consumer_capacity_and_orphan_close_release_persistent_rows(self):
        bound = self.subscribe(mode="live", view="notifications")
        for number in range(64):
            self.consumer.bind(self.context, "view-" + str(number), bound).unwrap()
        self.assertEqual(self.consumer.bind(self.context, "overflow", bound).failure.code, "consumer_capacity_exceeded")
        self.clock.advance(timedelta(hours=1, seconds=1))
        fresh = self.subscribe(key="fresh", mode="live", view="notifications")
        self.consumer.close(self.context, "view-0").unwrap()
        self.consumer.bind(self.context, "fresh", fresh).unwrap()
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM memory_sessions WHERE session_id LIKE ?", (CLIENT_PREFIX + "%",))["n"], 1)

    def test_resync_epoch_bookkeeping_has_a_fixed_capacity(self):
        bound = self.subscribe()
        for number in range(32):
            self.start(bound, "epoch-" + str(number))
        result = self.streams.handle(self.context, self.request("resync", self.target(bound) | {"action": "start"}, key="overflow"))
        self.assertEqual(result["reason_code"], "resync_operation_capacity_exceeded")

    def test_native_invalid_requests_and_nested_transactions_return_failures(self):
        bound, _ = self.synchronized()
        self.assertEqual(self.streams.poll(self.context, **self.target(bound), deadline_at="invalid").failure.code, "invalid_deadline_at")
        self.assertFalse(self.consumer.read(self.context, "bad consumer id").is_success)
        for transaction in (self.runtime.transaction, self.runtime.read_snapshot):
            with transaction():
                self.assertEqual(self.poll(bound).failure.code, "outer_transaction_required")
                self.assertEqual(self.consumer.close(self.context, "test-view").failure.code, "outer_transaction_required")
        self.consumer.read(self.context, "test-view").unwrap()

    def test_control_budget_and_final_deadline_roll_back_snapshot_creation(self):
        bound = self.subscribe()
        request = self.request("resync", self.target(bound) | {"action": "start"}, key="budget")
        request["budget"]["max_output_bytes"] = 1
        self.assertEqual(self.streams.handle(self.context, request)["reason_code"], "output_budget_exceeded")
        self.assertIsNone(self.streams.store.load(self.context, bound["subscription_id"])["snapshot"])
        request = self.request("resync", self.target(bound) | {"action": "start"}, key="deadline")
        save = self.streams.save
        def slow_save(context, state):
            save(context, state)
            self.clock.advance(timedelta(minutes=3))
        with patch.object(self.streams, "save", side_effect=slow_save):
            self.assertEqual(self.streams.handle(self.context, request)["reason_code"], "deadline_expired")
        self.assertIsNone(self.streams.store.load(self.context, bound["subscription_id"])["snapshot"])

    def test_control_unknown_commit_can_retry_the_same_key_without_new_snapshot(self):
        bound = self.subscribe()
        for after in (False, True):
            with self.subTest(after=after):
                request = self.request("resync", self.target(bound) | {"action": "start"}, key="commit-" + str(after))
                with commit_fault(self.runtime, after=after):
                    result = self.streams.handle(self.context, request)
                self.assertEqual((result["status"], result["output"], result["retryable"]), ("uncertain", None, False))
                state = self.streams.store.load(self.context, bound["subscription_id"])
                snapshot_id = state["snapshot"]["public"]["snapshot_id"] if state["snapshot"] else None
                recovered = self.streams.handle(self.context, request)
                self.assertEqual(recovered["status"], "succeeded", recovered)
                if after:
                    self.assertEqual(recovered["output"]["snapshot"]["snapshot_id"], snapshot_id)
        self.assertEqual(self.count("memory_changes"), 0)

    def test_apply_and_ack_unknown_commits_recover_without_replaying_facts(self):
        bound, _ = self.synchronized()
        self.remember()
        batch = self.poll(bound).unwrap()
        with commit_fault(self.runtime, after=True):
            result = self.consumer.apply_batch(self.context, "test-view", batch)
        self.assertEqual(result.failure.code, "subscription_state_uncertain")
        checkpoint = self.consumer.recovery_checkpoint(self.context, "test-view").unwrap()["checkpoint"]
        self.assertEqual(self.consumer.apply_batch(self.context, "test-view", batch).unwrap(), checkpoint)
        request = self.request("ack", self.target(bound) | dict(lease_id=batch["lease"]["lease_id"],
            target=dict(kind="batch", batch_id=batch["batch_id"]), checkpoint=checkpoint))
        with commit_fault(self.runtime, after=True):
            result = self.streams.handle(self.context, request)
        self.assertEqual((result["status"], result["output"], result["retryable"]), ("uncertain", None, False))
        self.assertEqual(self.streams.handle(self.context, request)["output"]["ack_state"], "already_accepted")
        self.assertEqual(len(self.consumer.read(self.context, "test-view").unwrap()["items"]), 1)
        self.assertEqual(self.count("memory_changes"), 1)

    def test_durable_checkpoint_cannot_forge_a_skipped_range_on_resume(self):
        _, checkpoint = self.synchronized()
        checkpoint = deepcopy(checkpoint)
        self.remember()
        checkpoint["stream_cursor"] = self.streams.store.cursor(checkpoint["binding"], self.streams.store.revision(self.context))
        resumed = self.subscribe(key="forged", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual((resumed["subscription_state"], resumed["resync_reason"]), ("resync_required", "checkpoint_unavailable"))

    def test_configuration_disable_and_reenable_require_a_new_binding_and_snapshot(self):
        config = ConfigurationService(self.runtime, FieldRegistry(version="memory-stream-test", fields=configuration_fields()))
        service = MemoryService(self.tasks, configuration=config)
        self.streams = MemorySubscriptions(service, provider_id=self.streams.provider_id, provider_generation="configured",
            scope_for_context=self.streams.scope_for_context, require_running=self.streams.require_running)
        self.consumer = MemoryReferenceConsumer(self.streams)
        manager = MemoryManagement(service, self.core)
        self.remember()
        bound, checkpoint = self.synchronized()
        for index, enabled in enumerate((False, True)):
            settings = manager.settings(self.context).unwrap()
            manager.patch_settings(self.context, operation_key="enable-" + str(index), expected_edit_token=settings["edit_token"],
                                   changes={"memory.enabled": enabled}).unwrap()
            self.assertFalse(self.consumer.read(self.context, "test-view").is_success)
        resumed = self.subscribe(key="config-resume", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual((resumed["subscription_state"], resumed["resync_reason"]), ("resync_required", "stream_authority_changed"))
        self.consumer.bind(self.context, "test-view", resumed).unwrap()
        page = self.start(resumed, "config-snapshot")
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        self.ack_snapshot(resumed, page, self.consumer.activate(self.context, "test-view").unwrap())
        self.assertEqual(len(self.consumer.read(self.context, "test-view").unwrap()["items"]), 1)

    def test_resume_cannot_skip_a_future_validity_boundary_without_a_change_event(self):
        future = self.remember(self.proposed(valid_from=self.clock.now() + timedelta(seconds=3)))
        _, checkpoint = self.synchronized()
        self.clock.advance(timedelta(seconds=3))
        resumed = self.subscribe(key="later", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual((resumed["subscription_state"], resumed["resync_reason"]), ("resync_required", "stream_validity_changed"))
        self.assertEqual(self.start(resumed, "later-snapshot")["items"][0]["atom_id"], future.atom_id)

    def test_expired_unacknowledged_snapshot_cannot_be_activated_by_resume(self):
        bound = self.subscribe()
        self.consumer.bind(self.context, "test-view", bound).unwrap()
        page = self.start(bound)
        self.consumer.stage_page(self.context, "test-view", page).unwrap()
        checkpoint = self.consumer.activate(self.context, "test-view").unwrap()
        self.clock.advance(timedelta(minutes=11))
        resumed = self.subscribe(key="late", generation="consumer-2", mode="resume", checkpoint=checkpoint)
        self.assertEqual((resumed["subscription_state"], resumed["resync_reason"]), ("resync_required", "snapshot_expired"))


if __name__ == "__main__":
    unittest.main()
