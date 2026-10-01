"""Trusted host subscription controls and durable reference-only recovery."""

from copy import deepcopy
from datetime import timedelta
import sqlite3

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.foundation.outcome import Outcome
from companion_v2.storage.runtime import StorageTransactionNestingError
from .models import timestamp
from .stream_store import StreamStore, PREFIX, token, fail, size, stream_outcome
from .stream_delivery import StreamDelivery
from .stream_visibility import StreamVisibility, ResyncRequired
from . import stream_validation as validation
from .wire_binding import MemoryWireBinding, _WireIssue, _time, _token
from .wire_operations import check_output, task_issue


class SubscriptionControl(MemoryWireBinding):
    def __init__(self, streams, capability, schema):
        super().__init__(streams.memory, provider_id=streams.provider_id, provider_generation=streams.provider_generation,
                         scope_for_context=streams.scope_for_context)
        self.streams, self.capability_id, self.schema_version = streams, capability, schema

    def _envelope(self, *args, **kwargs):
        result = super()._envelope(*args, **kwargs)
        result["schema_version"] = "memory.subscription-result.v1"
        return result

    def handle(self, context, request):
        streams = self.streams
        try:
            streams.require_running()
            needs_key = self.capability_id.endswith("subscribe") or (
                self.capability_id.endswith("resync") and type(request) is dict
                and type(request.get("payload")) is dict and request["payload"].get("action") == "start")
            # Per-call validator avoids mutating a shared provider during concurrent calls.
            binding = control_binding(self, needs_key)
            call = binding._validate_envelope(context, request)
            if call["budget"]["max_model_calls"] != 0:
                raise _WireIssue("invalid_model_budget")
            if needs_key:
                _token(request["idempotency_key"], "idempotency_key")
            with streams.memory.runtime.transaction(require_outermost=True):
                streams.fence(context, call["deadline"])
                try:
                    if self.capability_id == "memory.changed.subscribe":
                        output = streams.subscribe(context, request)
                    else:
                        validation.control(request["payload"], self.capability_id)
                        state = streams.target(context, request["payload"],
                            allow_resync=self.capability_id.endswith("resync") and request["payload"].get("action") == "start")
                        output = (streams.delivery.ack(context, state, request["payload"])
                            if self.capability_id.endswith("ack") else streams.resync(context, state, request))
                        streams.visibility.check(context, state)
                        streams.save(context, state)
                    result = self._envelope(request, status="succeeded", output=output)
                    check_output(self, call, result)
                except ResyncRequired as changed:
                    streams.invalidate(context, changed.state, changed.reason)
                    result = self._envelope(request, status="unavailable", reason_code=changed.reason)
                streams.fence(context, call["deadline"])
            return result
        except _WireIssue as issue:
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except TaskError as error:
            issue = task_issue(error)
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except StorageTransactionNestingError:
            return self._envelope(request, status="rejected", reason_code="outer_transaction_required")
        except sqlite3.Error:
            return self._envelope(request, status="uncertain", reason_code="subscription_control_uncertain")
        except (TypeError, ValueError, KeyError, RecursionError):
            return self._envelope(request, status="rejected", reason_code="invalid_request")


def control_binding(adapter, needs_key):
    binding = MemoryWireBinding(adapter.memory, provider_id=adapter.provider_id,
        provider_generation=adapter.provider_generation, scope_for_context=adapter.scope_for_context)
    binding.schema_version, binding.capability_id = adapter.schema_version, adapter.capability_id
    binding.extra_request_fields = frozenset({"idempotency_key"}) if needs_key else frozenset()
    return binding


class MemorySubscriptions(MemoryWireBinding):
    def __init__(self, memory, *, require_running, **binding):
        super().__init__(memory, **binding)
        self.require_running = require_running
        self.store, self.visibility = StreamStore(memory), StreamVisibility(memory)
        self.delivery = StreamDelivery(self)
        self.controls = {cap: SubscriptionControl(self, cap, schema) for cap, schema in (
            ("memory.changed.subscribe", "memory.subscribe.v1"), ("memory.changed.ack", "memory.ack.v1"),
            ("memory.changed.resync", "memory.resync.v1"))}

    def handle(self, context, request):
        capability = request.get("capability_id") if type(request) is dict else None
        adapter = self.controls.get(capability) if type(capability) is str else None
        if adapter is None:
            adapter = self.controls["memory.changed.subscribe"]
            return adapter._envelope(request, status="rejected", reason_code="unsupported_capability")
        return adapter.handle(context, request)

    def authorization_revision(self):
        return "authorization-" + str(self.memory.writer.access.access.revision)

    def fence(self, context, deadline):
        self.require_running()
        self.memory.writer.access.check(context)
        if self.memory.tasks.now() >= deadline:
            raise _WireIssue("deadline_expired", "timeout")

    def save(self, context, state):
        cap = 32768 + 3 * state["limits"]["max_staging_bytes"] + 10 * state["limits"]["max_inflight_bytes"]
        if size(state) > cap:
            fail("subscription_storage_budget_exceeded")
        self.store.save(context, state)

    def invalidate(self, context, state, reason):
        state.update(state="resync_required", reason=reason, inflight=None, snapshot=None,
                     known={}, checkpoint=None, acks=[])
        self.save(context, state)

    def target(self, context, payload, *, allow_resync=False):
        for name in ("subscription_id", "subscriber_generation"):
            _token(payload[name], name)
        state = self.store.load(context, payload["subscription_id"])
        if state["subscriber_generation"] != payload["subscriber_generation"] or state["state"] == "fenced":
            fail("subscriber_generation_mismatch")
        if state["provider_generation"] != self.provider_generation:
            fail("stream_provider_changed")
        if (state["binding"]["authorization_revision"] != self.authorization_revision()
                or state["binding"]["policy_revision"] != self._policy_revision(context)):
            raise ResyncRequired(state, "stream_authority_changed")
        if state.get("next_activation") and timestamp(state["next_activation"]) <= self.memory.tasks.now() and not allow_resync:
            raise ResyncRequired(state, "stream_validity_changed")
        snapshot = state.get("snapshot")
        if snapshot and timestamp(snapshot["public"]["expires_at"]) <= self.memory.tasks.now() and not allow_resync:
            raise ResyncRequired(state, "snapshot_expired")
        return state

    def subscribe(self, context, request):
        payload = request["payload"]
        limits, binding = validation.subscribe(self, context, payload)
        identifier = PREFIX + digest([context.key, self.memory.writer.caller(context), payload["namespace"], request["idempotency_key"]])
        for old in self.store.sessions(context):
            if old["id"] == identifier:
                if old["request_hash"] != digest(payload):
                    fail("idempotency_conflict")
                self.target(context, dict(subscription_id=identifier, subscriber_generation=payload["subscriber_generation"]))
                return old["bound"]
        self.store.reserve()
        start = payload["start"]
        state = dict(id=identifier, request_hash=digest(payload), binding=binding, limits=limits,
            expires_at=limits["recovery_deadline_at"], subscriber_generation=payload["subscriber_generation"],
            provider_generation=self.provider_generation, state="live" if start["mode"] == "live" else "resync_required",
            reason=None if start["mode"] == "live" else "initial_snapshot_required", sequence=self.store.revision(context),
            known={}, last_event_id=None, applied_revision=0, inflight=None, snapshot=None, checkpoint=None, acks=[])
        state["next_activation"] = self.visibility.next_activation(context, state)
        if start["mode"] == "resume":
            self.resume(context, state, start["checkpoint"])
        bound = dict(subscription_id=identifier, subscriber_generation=state["subscriber_generation"], binding=binding,
            limits=limits, expires_at=state["expires_at"], subscription_state=state["state"],
            cursor=self.store.cursor(binding, state["sequence"]) if state["state"] == "live" else None, resync_reason=state["reason"])
        state["bound"] = bound
        self.save(context, state)
        return bound

    def resume(self, context, state, checkpoint):
        if checkpoint["state"] != "active":
            fail("active_checkpoint_required")
        binding = state["binding"]
        old_binding = checkpoint["binding"]
        if type(old_binding) is not dict or any(old_binding.get(k) != binding[k] for k in (
                "subscriber_ref", "owner_ref", "namespace", "view_fingerprint", "lineage_id", "contract_fingerprint")):
            fail("checkpoint_binding_mismatch")
        if old_binding != binding:
            state["reason"] = "stream_authority_changed"
            return
        for old in self.store.sessions(context):
            if old["binding"] != binding or old["state"] == "fenced":
                continue
            accepted = old.get("checkpoint") == checkpoint
            try:
                if not accepted and old.get("inflight") and old["state"] == "live":
                    pending = old["inflight"]
                    self.delivery.validate_checkpoint(context, old, checkpoint, cursor=pending["batch"]["to_cursor"],
                        expected_state="active", snapshot=old.get("active_snapshot"), events=pending["batch"]["events"])
                    self.delivery.apply(old, pending["batch"])
                    old["sequence"] = pending["sequence"]
                    accepted = True
                if not accepted and old["state"] == "resyncing" and old.get("snapshot"):
                    snapshot = old["snapshot"]
                    if snapshot["completion"] and old["sequence"] == snapshot["ceiling"] and not old.get("inflight"):
                        self.delivery.validate_checkpoint(context, old, checkpoint,
                            cursor=snapshot["completion"]["tail_until_cursor"], expected_state="active", snapshot=snapshot["public"])
                        old["active_snapshot"] = snapshot["public"]
                        accepted = True
                if not accepted:
                    continue
                if old.get("next_activation") and timestamp(old["next_activation"]) <= self.memory.tasks.now():
                    state["reason"] = "stream_validity_changed"
                    return
                if old["state"] == "resyncing" and timestamp(old["snapshot"]["public"]["expires_at"]) <= self.memory.tasks.now():
                    state["reason"] = "snapshot_expired"
                    return
                if timestamp(old["expires_at"]) <= self.memory.tasks.now():
                    state["reason"] = "recovery_deadline_expired"
                    return
                self.visibility.check(context, old)
                if size(old["known"]) > state["limits"]["max_staging_bytes"]:
                    state["reason"] = "projection_capacity_exceeded"
                    return
                state.update(state="live", reason=None, sequence=old["sequence"], known=old["known"],
                    checkpoint=checkpoint, applied_revision=checkpoint["memory_revision"], last_event_id=checkpoint["last_event_id"],
                    active_snapshot=old.get("active_snapshot"))
                old["state"] = "fenced"
                self.save(context, old)
                return
            except ResyncRequired:
                state["reason"] = "stream_visibility_changed"
                return
            except TaskError:
                continue
        state["reason"] = "checkpoint_unavailable"

    def resync(self, context, state, request):
        payload = request["payload"]
        if state["binding"]["view_kind"] != "current_projection":
            fail("notification_snapshot_unavailable")
        if payload["action"] == "start":
            key = request["idempotency_key"]
            snapshot = state.get("snapshot")
            starts = state.setdefault("resync_starts", {})
            marker = digest(key)
            if marker in starts and (snapshot is None or snapshot["key"] != key):
                # A completed/invalidated epoch must never be resurrected by retry.
                fail("resync_epoch_closed")
            if snapshot is None or snapshot["key"] != key or timestamp(snapshot["public"]["expires_at"]) <= self.memory.tasks.now():
                if marker in starts:
                    fail("snapshot_expired")
                if len(starts) >= 32:
                    fail("resync_operation_capacity_exceeded")
                starts[marker] = True
                revision = self.store.revision(context)
                public = dict(snapshot_id=token("memory-snapshot-"), snapshot_epoch=token("memory-epoch-"),
                    binding=state["binding"], memory_revision=revision, tail_start_cursor=self.store.cursor(state["binding"], revision),
                    expires_at=stamp(min(timestamp(state["expires_at"]), self.memory.tasks.now() + timedelta(minutes=10))))
                items = self.visibility.snapshot(context, state, revision)
                snapshot = dict(public=public, items=items, key=key, pages={}, next_offset=0, completion=None,
                                activation_lease=None, ceiling=None)
                state.update(state="resyncing", reason=None, snapshot=snapshot, sequence=revision,
                    known={item["atom_id"]: item["atom_revision"] for item in items}, checkpoint=None,
                    last_event_id=None, applied_revision=revision, inflight=None, acks=[], active_snapshot=None)
                state["next_activation"] = self.visibility.next_activation(context, state)
            offset = 0
        else:
            snapshot = state.get("snapshot")
            if not snapshot or state["state"] != "resyncing" or any(payload[k] != snapshot["public"][k] for k in ("snapshot_id", "snapshot_epoch")):
                fail("snapshot_unavailable")
            cursor = payload["page_cursor"]
            pages = snapshot["pages"]
            offset = next((v["next_offset"] for v in pages.values() if v["output"]["next_page_cursor"] == cursor), None)
            if offset is None:
                fail("snapshot_cursor_invalid")
        self.visibility.check(context, state)
        marker = str(offset)
        if marker in snapshot["pages"]:
            return snapshot["pages"][marker]["output"]
        if offset != snapshot["next_offset"]:
            fail("snapshot_page_gap")
        selected = []
        for item in snapshot["items"][offset:offset + state["limits"]["max_batch_items"]]:
            if size(selected + [item]) + 4096 > state["limits"]["max_batch_bytes"]:
                if not selected:
                    fail("snapshot_page_budget_exceeded")
                break
            selected.append(item)
        end = offset + len(selected)
        finished = end == len(snapshot["items"])
        if finished and snapshot["completion"] is None:
            snapshot["ceiling"] = self.store.revision(context)
            snapshot["completion"] = dict(completion_token=token("memory-complete-"),
                tail_until_cursor=self.store.cursor(state["binding"], snapshot["ceiling"]))
            snapshot["activation_lease"] = self.delivery.lease(state)
        page_cursor = "memory-page-" + digest([snapshot["public"]["snapshot_epoch"], offset])
        output = dict(subscription_id=state["id"], subscriber_generation=state["subscriber_generation"], snapshot=snapshot["public"],
            page_id="memory-page-id-" + digest([snapshot["public"]["snapshot_id"], offset]), page_cursor=page_cursor, items=selected,
            next_page_cursor=None if finished else "memory-page-" + digest([snapshot["public"]["snapshot_epoch"], end]),
            completion=snapshot["completion"] if finished else None, activation_lease=snapshot["activation_lease"] if finished else None)
        snapshot["pages"][marker] = dict(output=output, next_offset=end)
        snapshot["next_offset"] = end
        return output

    @stream_outcome
    def poll(self, context, subscription_id, subscriber_generation, *, deadline_at):
        self.require_running()
        deadline = _time(deadline_at, "deadline_at")
        try:
            with self.memory.runtime.transaction(require_outermost=True):
                self.fence(context, deadline)
                try:
                    state = self.target(context, dict(subscription_id=subscription_id, subscriber_generation=subscriber_generation))
                    batch = self.delivery.poll(context, state)
                    self.save(context, state)
                    result = deepcopy(batch)
                except ResyncRequired as changed:
                    self.invalidate(context, changed.state, changed.reason)
                    result = Outcome.failed("resync_required", changed.reason)
                self.fence(context, deadline)
            if isinstance(result, Outcome):
                # outcome() cannot flatten a nested failure.
                fail("resync_required")
            return {"batch": result}
        except _WireIssue as issue:
            fail(issue.reason_code)
        except sqlite3.Error:
            fail("subscription_delivery_uncertain")

    @stream_outcome
    def close_subscription(self, context, subscription_id, subscriber_generation):
        self.require_running()
        with self.memory.runtime.transaction(require_outermost=True):
            self.memory.writer.access.check(context)
            _token(subscription_id, "subscription_id")
            _token(subscriber_generation, "subscriber_generation")
            state = self.store.load(context, subscription_id, allow_expired=True)
            if state["subscriber_generation"] != subscriber_generation or state["provider_generation"] != self.provider_generation:
                fail("subscriber_generation_mismatch")
            state.update(state="fenced", inflight=None, snapshot=None, known={}, acks=[])
            self.save(context, state)
        return True
