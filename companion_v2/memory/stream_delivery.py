"""One bounded in-flight batch, durable leases, ACK barriers and replay cursors."""

from datetime import timedelta

from companion_v2.execution.models import digest, stamp, TaskError
from .models import owner_key, timestamp
from .stream_store import fail, token, size
from .stream_visibility import ResyncRequired


class StreamDelivery:
    def __init__(self, streams):
        self.streams = streams

    def lease(self, state):
        now = self.streams.memory.tasks.now()
        return dict(lease_id=token("memory-lease-"), expires_at=stamp(min(timestamp(state["expires_at"]),
                    now + timedelta(milliseconds=state["limits"]["lease_ms"]))))

    def apply(self, state, batch):
        for event in batch["events"]:
            item = event["payload"]
            if item["change_kind"] in ("retracted", "expired"):
                state["known"].pop(item["atom_id"], None)
            else:
                state["known"][item["atom_id"]] = item["atom_revision"]
        if size(state["known"]) > state["limits"]["max_staging_bytes"]:
            raise ResyncRequired(state, "projection_capacity_exceeded")

    def event(self, context, state, row):
        streams = self.streams
        head = streams.memory.runtime.read_one("SELECT * FROM memory_atoms WHERE atom_id = ? AND owner_key = ?",
                                               (row["atom_id"], owner_key(context)))
        if head is None:
            raise ResyncRequired(state, "stream_history_unavailable")
        kind = "retracted" if row["kind"] == "forgotten" else row["kind"]
        if kind not in state["binding"]["change_kinds"]:
            return None
        if kind in ("retracted", "expired"):
            # Hidden/inactive objects are not enumerated to a new subscriber.
            if row["atom_id"] not in state["known"]:
                return None
        else:
            try:
                streams.visibility.reference(context, row["namespace"], row["atom_id"], row["revision"])
            except TaskError:
                raise ResyncRequired(state, "stream_visibility_changed") from None
        trace = "memory-change-" + digest([state["binding"]["lineage_id"], row["sequence"]])
        return dict(schema_version="memory.changed.v1", capability_id="memory.changed", capability_version="1.0",
            provider_id=streams.provider_id, provider_generation=streams.provider_generation, trace_id=trace,
            scope=streams.scope_for_context(context), payload=dict(event_id=trace, namespace=row["namespace"],
                owner_ref=state["binding"]["owner_ref"], atom_id=row["atom_id"], atom_revision=row["revision"],
                memory_revision=row["sequence"], change_kind=kind, occurred_at=row["occurred_at"], trace_id=trace))

    def poll(self, context, state):
        streams = self.streams
        if state["state"] not in ("live", "resyncing"):
            fail("resync_required")
        snapshot = state.get("snapshot")
        if state["state"] == "resyncing" and (snapshot is None or snapshot["completion"] is None):
            fail("snapshot_pages_incomplete")
        streams.visibility.check(context, state)
        pending = state.get("inflight")
        if pending:
            batch = pending["batch"]
            streams.visibility.check(context, state, {event["payload"]["atom_id"]: event["payload"]["atom_revision"]
                for event in batch["events"] if event["payload"]["change_kind"] in ("added", "corrected")})
            if timestamp(batch["lease"]["expires_at"]) <= streams.memory.tasks.now():
                if pending["attempts"] >= state["limits"]["max_retry_attempts"]:
                    raise ResyncRequired(state, "stream_retry_exhausted")
                pending["attempts"] += 1
                batch["lease"] = self.lease(state)
            return batch
        after = state["sequence"]
        ceiling = snapshot["ceiling"] if state["state"] == "resyncing" else streams.store.revision(context)
        if after >= ceiling:
            return None
        # Retention budget limits replay backlog, not the owner's fact history.
        cap = state["limits"]["max_retained_log_bytes"]
        backlog = streams.memory.runtime.read_all("""SELECT sequence, namespace, atom_id, revision, kind, occurred_at
            FROM memory_changes WHERE owner_key = ? AND sequence > ? AND sequence <= ? ORDER BY sequence LIMIT ?""",
            (owner_key(context), after, ceiling, min(8192, cap // 64 + 1)))
        if len(backlog) == min(8192, cap // 64 + 1) or sum(size(dict(row)) for row in backlog) > cap:
            raise ResyncRequired(state, "stream_retention_budget_exceeded")
        batch = dict(schema_version="memory.change-batch.v1", capability_id="memory.changed", capability_version="1.0",
            provider_id=streams.provider_id, provider_generation=streams.provider_generation,
            trace_id=token("memory-delivery-"), scope=streams.scope_for_context(context), subscription_id=state["id"],
            subscriber_generation=state["subscriber_generation"], binding=state["binding"], batch_id=token("memory-batch-"),
            lease=self.lease(state), delivery_mode="snapshot_tail" if state["state"] == "resyncing" else "live",
            snapshot_id=snapshot["public"]["snapshot_id"] if state["state"] == "resyncing" else None,
            from_cursor=streams.store.cursor(state["binding"], after), to_cursor=streams.store.cursor(state["binding"], after), events=[])
        next_sequence = after
        projection = {**state, "known": dict(state["known"])}
        for row in backlog[:state["limits"]["max_batch_items"]]:
            event = self.event(context, projection, row) if row["namespace"] == state["binding"]["namespace"] else None
            candidate = {**batch, "events": batch["events"] + ([event] if event else []),
                         "to_cursor": streams.store.cursor(state["binding"], row["sequence"])}
            if size(candidate) > state["limits"]["max_batch_bytes"]:
                if next_sequence == after:
                    fail("stream_batch_budget_exceeded")
                break
            batch, next_sequence = candidate, row["sequence"]
            if event:
                self.apply(projection, {"events": [event]})
        if next_sequence == after:
            raise ResyncRequired(state, "stream_history_unavailable")
        state["inflight"] = dict(batch=batch, attempts=0, sequence=next_sequence)
        return batch

    def validate_checkpoint(self, context, state, checkpoint, *, cursor, expected_state, snapshot, events=()):
        from .stream_validation import checkpoint as validate
        validate(checkpoint)
        last_event = events[-1]["payload"]["event_id"] if events else state.get("last_event_id")
        revision = max([state.get("applied_revision", 0), *(event["payload"]["memory_revision"] for event in events)])
        if (checkpoint["binding"] != state["binding"] or checkpoint["stream_cursor"] != cursor
                or checkpoint["state"] != expected_state or checkpoint["snapshot"] != snapshot
                or checkpoint["last_event_id"] != last_event or checkpoint["memory_revision"] != revision
                or timestamp(checkpoint["stored_at"]) > self.streams.memory.tasks.now()):
            fail("checkpoint_mismatch")
        old = state.get("checkpoint")
        if old and old["projection_generation"] != checkpoint["projection_generation"]:
            fail("projection_generation_mismatch")

    def ack(self, context, state, payload):
        streams = self.streams
        target, checkpoint = payload["target"], payload["checkpoint"]
        streams.visibility.check(context, state)
        for old in state.get("acks", []):
            if old["target"] == target and old["lease_id"] == payload["lease_id"]:
                if old["checkpoint"] != checkpoint:
                    fail("ack_conflict")
                return {**old["output"], "ack_state": "already_accepted"}
        if target["kind"] == "batch":
            pending = state.get("inflight")
            if pending is None or pending["batch"]["batch_id"] != target["batch_id"]:
                fail("ack_target_unavailable")
            batch = pending["batch"]
            lease = batch["lease"]
            snapshot = state["snapshot"]["public"] if state["state"] == "resyncing" else state.get("active_snapshot")
            self.validate_checkpoint(context, state, checkpoint, cursor=batch["to_cursor"],
                expected_state="snapshot_tail" if state["state"] == "resyncing" else "active",
                snapshot=snapshot, events=batch["events"])
            streams.visibility.check(context, state, {event["payload"]["atom_id"]: event["payload"]["atom_revision"]
                for event in batch["events"] if event["payload"]["change_kind"] in ("added", "corrected")})
            self.apply(state, batch)
            state["sequence"], state["inflight"] = pending["sequence"], None
        else:
            snapshot = state.get("snapshot")
            if (state["state"] != "resyncing" or not snapshot or not snapshot["completion"] or state.get("inflight")
                    or target["snapshot_id"] != snapshot["public"]["snapshot_id"]
                    or target["completion_token"] != snapshot["completion"]["completion_token"]
                    or state["sequence"] != snapshot["ceiling"]):
                fail("snapshot_not_ready")
            lease = snapshot["activation_lease"]
            self.validate_checkpoint(context, state, checkpoint, cursor=snapshot["completion"]["tail_until_cursor"],
                                     expected_state="active", snapshot=snapshot["public"])
            state["active_snapshot"] = snapshot["public"]
            state["snapshot"], state["state"] = None, "live"
        if payload["lease_id"] != lease["lease_id"] or timestamp(lease["expires_at"]) <= streams.memory.tasks.now():
            fail("ack_lease_expired")
        state["checkpoint"] = checkpoint
        state["last_event_id"], state["applied_revision"] = checkpoint["last_event_id"], checkpoint["memory_revision"]
        output = dict(subscription_id=state["id"], subscriber_generation=state["subscriber_generation"], lease_id=payload["lease_id"],
            target=target, ack_state="accepted", subscription_state=state["state"], acknowledged_cursor=checkpoint["stream_cursor"],
            projection_generation=checkpoint["projection_generation"])
        state["acks"] = (state.get("acks", []) + [dict(target=target, lease_id=payload["lease_id"], checkpoint=checkpoint, output=output)])[-8:]
        return output
