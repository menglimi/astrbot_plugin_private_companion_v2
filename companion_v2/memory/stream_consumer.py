"""Durable reference inbox and staging/activation; never replays fact commands."""

from copy import deepcopy

from companion_v2.execution.models import digest, stamp
from .models import timestamp
from .stream_store import CLIENT_PREFIX, size, token, fail, stream_outcome


class MemoryReferenceConsumer:
    def __init__(self, streams):
        self.streams, self.store = streams, streams.store

    def identifier(self, context, consumer_id):
        from .wire_binding import _token
        _token(consumer_id, "consumer_id")
        return CLIENT_PREFIX + digest([context.key, consumer_id])

    def load(self, context, consumer_id):
        self.streams.require_running()
        self.streams.memory.writer.access.check(context)
        return self.store.load(context, self.identifier(context, consumer_id), prefix=CLIENT_PREFIX, allow_expired=True)

    def save(self, context, state):
        if size(state) > 32768 + 3 * state["limits"]["max_staging_bytes"]:
            fail("consumer_storage_budget_exceeded")
        self.store.save(context, state, prefix=CLIENT_PREFIX)

    @stream_outcome
    def bind(self, context, consumer_id, bound):
        self.streams.require_running()
        self.streams.memory.writer.access.check(context)
        identifier = self.identifier(context, consumer_id)
        with self.streams.memory.runtime.transaction(require_outermost=True):
            server = self.streams.target(context, bound, allow_resync=True)
            if server["bound"] != bound:
                fail("consumer_binding_invalid")
            row = self.streams.memory.runtime.read_one("SELECT 1 FROM memory_sessions WHERE session_id = ?", (identifier,))
            state = self.store.load(context, identifier, prefix=CLIENT_PREFIX, allow_expired=True) if row else None
            preserve = state and server["state"] == "live" and state.get("checkpoint") == server.get("checkpoint")
            if server.get("checkpoint") and not preserve:
                fail("consumer_checkpoint_unavailable")
            if not row:
                self.store.reserve(prefix=CLIENT_PREFIX)
            state = dict(id=identifier, subscription_id=bound["subscription_id"], subscriber_generation=bound["subscriber_generation"],
                expires_at=bound["expires_at"], binding=bound["binding"], limits=bound["limits"],
                active=state["active"] if preserve else {}, checkpoint=state["checkpoint"] if preserve else None,
                fresh=bool(preserve) or bound["subscription_state"] == "live", staging=None,
                generation=state["generation"] if preserve else token("projection-"), inbox=[],
                active_snapshot=state.get("active_snapshot") if preserve else None,
                stream_cursor=state["stream_cursor"] if preserve else bound["cursor"],
                applied_revision=state["applied_revision"] if preserve else 0,
                last_event_id=state["last_event_id"] if preserve else None)
            self.save(context, state)
            return deepcopy(dict(checkpoint=state.get("checkpoint"), fresh=state["fresh"]))

    def checkpoint(self, state, *, phase, snapshot, page_cursor=None):
        return dict(schema_version="memory.checkpoint.v1", binding=state["binding"], projection_generation=state["generation"],
            state=phase, snapshot=snapshot, page_cursor=page_cursor, stream_cursor=state["stream_cursor"],
            last_event_id=state["last_event_id"], memory_revision=state["applied_revision"],
            inbox_ref=state["id"], stored_at=stamp(self.streams.memory.tasks.now()))

    @stream_outcome
    def stage_page(self, context, consumer_id, page):
        self.streams.require_running()
        with self.streams.memory.runtime.transaction(require_outermost=True):
            state = self.load(context, consumer_id)
            server = self.streams.target(context, state)
            snapshot = server.get("snapshot")
            if not snapshot or page not in [entry["output"] for entry in snapshot["pages"].values()]:
                fail("snapshot_page_not_issued")
            self.streams.visibility.check(context, server)
            staging = state.get("staging")
            if not staging or staging["public"] != page["snapshot"]:
                if page["page_cursor"] != "memory-page-" + digest([page["snapshot"]["snapshot_epoch"], 0]):
                    fail("consumer_snapshot_page_gap")
                staging = dict(public=page["snapshot"], items={}, next_cursor=page["page_cursor"], pages=[], completion=None)
                state.update(staging=staging, fresh=False, generation=token("projection-"),
                    stream_cursor=page["snapshot"]["tail_start_cursor"], applied_revision=page["snapshot"]["memory_revision"], last_event_id=None)
            if page["page_id"] in staging["pages"]:
                return deepcopy(state["checkpoint"])
            if staging["next_cursor"] != page["page_cursor"]:
                fail("consumer_snapshot_page_gap")
            for item in page["items"]:
                old = staging["items"].get(item["atom_id"])
                if old and old != item:
                    fail("consumer_reference_conflict")
                staging["items"][item["atom_id"]] = item
            if size(staging["items"]) > state["limits"]["max_staging_bytes"]:
                fail("consumer_staging_budget_exceeded")
            staging["pages"].append(page["page_id"])
            staging["next_cursor"], staging["completion"] = page["next_page_cursor"], page["completion"]
            state["checkpoint"] = self.checkpoint(state, phase="snapshot_pages" if page["next_page_cursor"] else "snapshot_tail",
                snapshot=page["snapshot"], page_cursor=page["next_page_cursor"])
            self.save(context, state)
            return deepcopy(state["checkpoint"])

    @stream_outcome
    def apply_batch(self, context, consumer_id, batch):
        self.streams.require_running()
        with self.streams.memory.runtime.transaction(require_outermost=True):
            state = self.load(context, consumer_id)
            server = self.streams.target(context, state)
            current = server.get("inflight")
            if current is None or current["batch"] != batch:
                fail("batch_not_issued")
            self.streams.visibility.check(context, server)
            self.streams.visibility.check(context, server, {event["payload"]["atom_id"]: event["payload"]["atom_revision"]
                for event in batch["events"] if event["payload"]["change_kind"] in ("added", "corrected")})
            semantic_hash = digest({k: v for k, v in batch.items() if k != "lease"})
            old = next((entry for entry in state["inbox"] if entry["batch_id"] == batch["batch_id"]), None)
            if old:
                if old["hash"] != semantic_hash:
                    fail("consumer_batch_conflict")
                return deepcopy(old["checkpoint"])
            if state["stream_cursor"] != batch["from_cursor"]:
                fail("consumer_stream_gap")
            tail = batch["delivery_mode"] == "snapshot_tail"
            staging = state.get("staging")
            if tail and (not staging or not staging["completion"] or staging["public"]["snapshot_id"] != batch["snapshot_id"]):
                fail("consumer_snapshot_incomplete")
            if not tail and not state["fresh"]:
                fail("consumer_projection_stale")
            items = staging["items"] if tail else state["active"]
            for event in batch["events"]:
                value = event["payload"]
                item = dict(item_kind="tombstone" if value["change_kind"] in ("retracted", "expired") else "fact_ref",
                    atom_id=value["atom_id"], atom_revision=value["atom_revision"], memory_revision=value["memory_revision"])
                item.update({"change_kind": value["change_kind"]} if item["item_kind"] == "tombstone" else {"fact_status": "active"})
                old_item = items.get(item["atom_id"])
                if old_item and old_item["atom_revision"] == item["atom_revision"] and old_item != item:
                    fail("consumer_reference_conflict")
                if old_item is None or old_item["atom_revision"] < item["atom_revision"]:
                    items[item["atom_id"]] = item
                state["applied_revision"] = max(state["applied_revision"], item["memory_revision"])
                state["last_event_id"] = value["event_id"]
            state["stream_cursor"] = batch["to_cursor"]
            if size(items) > state["limits"]["max_staging_bytes"]:
                fail("consumer_projection_budget_exceeded")
            state["checkpoint"] = self.checkpoint(state, phase="snapshot_tail" if tail else "active",
                snapshot=staging["public"] if tail else state.get("active_snapshot"))
            state["inbox"] = (state["inbox"] + [dict(batch_id=batch["batch_id"], hash=semantic_hash, checkpoint=state["checkpoint"])])[-32:]
            self.save(context, state)
            return deepcopy(state["checkpoint"])

    @stream_outcome
    def activate(self, context, consumer_id):
        self.streams.require_running()
        with self.streams.memory.runtime.transaction(require_outermost=True):
            state = self.load(context, consumer_id)
            server = self.streams.target(context, state)
            self.streams.visibility.check(context, server)
            staging = state.get("staging")
            if not staging or not staging["completion"] or state["stream_cursor"] != staging["completion"]["tail_until_cursor"]:
                fail("consumer_snapshot_incomplete")
            state.update(active=staging["items"], staging=None, fresh=True, active_snapshot=staging["public"])
            state["checkpoint"] = self.checkpoint(state, phase="active", snapshot=staging["public"])
            self.save(context, state)
            return deepcopy(state["checkpoint"])

    @stream_outcome
    def read(self, context, consumer_id):
        self.streams.require_running()
        with self.streams.memory.runtime.read_snapshot():
            state = self.load(context, consumer_id)
            if not state["fresh"] or timestamp(state["expires_at"]) <= self.streams.memory.tasks.now():
                fail("consumer_projection_stale")
            server = self.streams.target(context, state)
            if server["state"] != "live" or state["checkpoint"] != server.get("checkpoint"):
                fail("consumer_projection_unacknowledged")
            # References are a current view only after all committed change ranges
            # have been applied. A quiet poll is not proof of freshness after a write.
            if server["sequence"] != self.store.revision(context):
                fail("consumer_projection_behind")
            self.streams.visibility.check(context, server)
            # A cached reference is never evidence that a revoked fact remains usable.
            return deepcopy(dict(items=list(state["active"].values()), checkpoint=state["checkpoint"]))

    @stream_outcome
    def recovery_checkpoint(self, context, consumer_id):
        return deepcopy(dict(checkpoint=self.load(context, consumer_id).get("checkpoint")))

    @stream_outcome
    def close(self, context, consumer_id):
        self.streams.require_running()
        with self.streams.memory.runtime.transaction(require_outermost=True) as connection:
            state = self.load(context, consumer_id)
            exists = connection.execute("SELECT 1 FROM memory_sessions WHERE session_id = ?", (state["subscription_id"],)).fetchone()
            server = self.store.load(context, state["subscription_id"], allow_expired=True) if exists else None
            if server and server["subscriber_generation"] == state["subscriber_generation"]:
                server.update(state="fenced", known={}, inflight=None, snapshot=None, acks=[], checkpoint=None)
                self.streams.save(context, server)
            connection.execute("DELETE FROM memory_sessions WHERE session_id = ? AND context_key = ?", (state["id"], context.key))
        return True
