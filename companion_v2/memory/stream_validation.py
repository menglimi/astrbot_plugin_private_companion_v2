"""Validate subscription controls before touching durable stream state."""

from datetime import timedelta

from companion_v2.execution.models import digest, stamp
from .proposal_input import private_payload
from .stream_store import LIMITS, CONTRACT_FINGERPRINT
from .models import owner_key
from .wire_binding import _WireIssue, _token, _integer, _time


KINDS = {"added", "corrected", "retracted", "expired"}


def fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        raise _WireIssue("invalid_payload")


def subscribe(adapter, context, payload):
    required = set("namespace visibility purpose subscriber_generation projection_kind view_kind change_kinds start limits".split())
    private_payload(payload, required=required, allowed=required)
    _token(payload["subscriber_generation"], "subscriber_generation")
    if payload["projection_kind"] != "references" or payload["view_kind"] not in ("current_projection", "notifications"):
        raise _WireIssue("view_unavailable", "unavailable")
    kinds = payload["change_kinds"]
    if (type(kinds) is not list or not 1 <= len(kinds) <= 4 or any(type(k) is not str or k not in KINDS for k in kinds)
            or len(set(kinds)) != len(kinds)):
        raise _WireIssue("invalid_change_kinds")
    start = payload["start"]
    if type(start) is not dict or start.get("mode") not in ("snapshot", "live", "resume"):
        raise _WireIssue("invalid_subscription_start")
    fields(start, "mode checkpoint" if start["mode"] == "resume" else "mode")
    if payload["view_kind"] == "current_projection" and (set(kinds) != KINDS or start["mode"] == "live"):
        raise _WireIssue("incomplete_projection_view")
    if payload["view_kind"] == "notifications" and start["mode"] == "snapshot":
        raise _WireIssue("notification_snapshot_unavailable")
    limits = payload["limits"]
    if type(limits) is not dict or set(limits) != set(LIMITS) | {"recovery_deadline_at"}:
        raise _WireIssue("invalid_limits")
    checked = {name: min(_integer(limits[name], name, minimum=0 if name == "max_retry_attempts" else 1), cap)
               for name, cap in LIMITS.items()}
    expiry = _time(limits["recovery_deadline_at"], "recovery_deadline_at")
    if expiry <= adapter.memory.tasks.now():
        raise _WireIssue("recovery_deadline_expired", "timeout")
    checked["recovery_deadline_at"] = stamp(min(expiry, adapter.memory.tasks.now() + timedelta(days=1)))
    checked["max_batch_bytes"] = min(checked["max_batch_bytes"], checked["max_inflight_bytes"])
    binding = dict(subscriber_ref="subscriber-" + digest([context.key, adapter.memory.writer.caller(context)]),
        owner_ref="owner-" + owner_key(context), namespace=payload["namespace"], purpose=payload["purpose"],
        projection_kind="references", view_kind=payload["view_kind"], change_kinds=sorted(kinds),
        view_fingerprint=digest([context.key, payload["namespace"], payload["purpose"], payload["view_kind"], sorted(kinds)]),
        authorization_revision=adapter.authorization_revision(), policy_revision=adapter._policy_revision(context),
        lineage_id=adapter.store.keys()["lineage"], retention_epoch="memory-unpruned-v1",
        contract_fingerprint=CONTRACT_FINGERPRINT)
    if start["mode"] == "resume":
        checkpoint(start["checkpoint"])
    return checked, binding


def checkpoint(value):
    fields(value, "schema_version binding projection_generation state snapshot page_cursor stream_cursor last_event_id memory_revision inbox_ref stored_at")
    if value["schema_version"] != "memory.checkpoint.v1" or value["state"] not in ("snapshot_pages", "snapshot_tail", "active"):
        raise _WireIssue("invalid_checkpoint")
    for name in ("projection_generation", "stream_cursor", "inbox_ref"):
        _token(value[name], name)
    if value["last_event_id"] is not None:
        _token(value["last_event_id"], "last_event_id")
    _integer(value["memory_revision"], "memory_revision")
    _time(value["stored_at"], "stored_at")
    if value["state"] == "snapshot_pages":
        _token(value["page_cursor"], "page_cursor")
    elif value["page_cursor"] is not None:
        raise _WireIssue("invalid_checkpoint_page")
    if value["state"] != "active" and type(value["snapshot"]) is not dict:
        raise _WireIssue("invalid_checkpoint_snapshot")


def control(payload, capability):
    if capability == "memory.changed.ack":
        fields(payload, "subscription_id subscriber_generation lease_id target checkpoint")
        _token(payload["lease_id"], "lease_id")
        target = payload["target"]
        if type(target) is not dict or target.get("kind") not in ("snapshot", "batch"):
            raise _WireIssue("invalid_ack_target")
        fields(target, "kind batch_id" if target["kind"] == "batch" else "kind snapshot_id completion_token")
        for key, value in target.items():
            _token(value, key)
        checkpoint(payload["checkpoint"])
    else:
        if type(payload) is not dict or payload.get("action") not in ("start", "page"):
            raise _WireIssue("invalid_resync_action")
        fields(payload, "subscription_id subscriber_generation action" +
               (" snapshot_id snapshot_epoch page_cursor" if payload["action"] == "page" else ""))
        for key, value in payload.items():
            _token(value, key)
    _token(payload["subscription_id"], "subscription_id")
    _token(payload["subscriber_generation"], "subscriber_generation")
