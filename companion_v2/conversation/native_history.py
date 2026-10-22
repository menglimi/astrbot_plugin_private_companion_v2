"""Reference-based native dialogue for background work, without fake receipts."""

import json

from companion_v2.execution.models import TaskContext, TaskError, stamp

from .messages import source_from_document
from .native_observations import REALITY_ASSISTANT_OWNER, TOGETHER_OWNERS, observations_available, validate_observation
from .reset import source_current


def reference(row):
    return {"kind": "native_input" if row["kind"] == "input" else "native_reply",
            "observation_id": row["observation_id"], "content_hash": row["content_hash"],
            "observed_at": row["observed_at"]}


def reference_key(ref):
    if (type(ref) is not dict or set(ref) != {"kind", "observation_id", "content_hash", "observed_at"}
            or ref["kind"] not in ("native_input", "native_reply")
            or any(type(value) is not str or not value or len(value) > 1024 for value in ref.values())):
        raise TaskError("native_history_invalid", "native history must retain its original source reference")
    return ref["kind"], ref["observation_id"]


def rows(runtime, context, *, start=None, end=None, kind=None, limit=32):
    if not observations_available(runtime):
        return ()
    has_sends = runtime.read_one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_native_sends'", ()) is not None
    timestamp = "COALESCE(s.sent_at, n.observed_at)" if has_sends else "n.observed_at"
    where = ["n.context_key = ?", "n.delivery_state IN ('input_observed', 'send_returned')"]
    values = [context.key]
    if start is not None:
        where.append(timestamp + " >= ?")
        values.append(start)
    if end is not None:
        where.append(timestamp + " <= ?")
        values.append(end)
    if kind is not None:
        where.append("n.kind = ?")
        values.append(kind)
    query = ("SELECT n.*, s.sent_at FROM conversation_native_observations n LEFT JOIN conversation_native_sends s USING(observation_id) "
             if has_sends else "SELECT n.*, NULL AS sent_at FROM conversation_native_observations n ")
    query += "WHERE " + " AND ".join(where) + " ORDER BY " + timestamp + " DESC, n.rowid DESC LIMIT ?"
    return runtime.read_all(query, (*values, limit))


def body(messages, ref, context, at, *, historical=False):
    reference_key(ref)
    if not observations_available(messages.runtime):
        raise TaskError("native_history_unavailable", "native history is unavailable")
    row = messages.runtime.read_one("SELECT * FROM conversation_native_observations WHERE observation_id=?",
                                    (ref["observation_id"],))
    if (row is None or reference(row) != ref or row["context_key"] != context.key
            or row["delivery_state"] not in ("input_observed", "send_returned") or row["observed_at"] > stamp(at)):
        raise TaskError("native_history_changed", "the native history changed or was not sent")
    original = TaskContext.restore(json.loads(row["context_json"]))
    if original.key != context.key or original.scope != context.scope:
        raise TaskError("native_history_context", "native history belongs to another authenticated context")
    source = source_from_document(json.loads(row["source_json"]))
    validate_observation(messages.runtime, row, context, source)
    if not historical and not source_current(messages.runtime, source):
        raise TaskError("conversation_context_reset", "native history precedes this window's reset")
    record = messages._read_source(source, context, "text", at)
    if record.content_hash != row["content_hash"]:
        raise TaskError("native_history_changed", "the original native source changed")
    origin = ({"owner": source.owner, "execution_path": "together_room", "source_label": "一起房间文字转写"}
              if source.owner in TOGETHER_OWNERS else {})
    if source.owner == REALITY_ASSISTANT_OWNER:
        local = row["event_id"].startswith("reality-local:")
        origin = {"execution_path": "reality_local_audio" if local else "reality_chat",
                  "source_label": "现实设备已播放的话" if local else "现实提醒聊天副本"}
    if row["kind"] == "input":
        return {"role": "user", "received_at": row["observed_at"], "text": record.payload,
                "owner": source.owner, **origin}
    sent = (messages.runtime.read_one("SELECT sent_at FROM conversation_native_sends WHERE observation_id=?",
                                     (row["observation_id"],))
            if messages.runtime.read_one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_native_sends'", ()) else None)
    sent_at = sent["sent_at"] if sent else row["observed_at"]
    if sent_at > stamp(at):
        raise TaskError("native_history_changed", "the native send is later than this observation")
    return {"role": "assistant", "delivered_at": sent_at, "text": record.payload, "owner": source.owner,
            "recipient_read": "unknown", "delivery_state": "send_returned", "platform_confirmed": False,
            "send_time_basis": "reality_output_return" if source.owner == REALITY_ASSISTANT_OWNER else
                "together_room_send_return" if source.owner in TOGETHER_OWNERS
                else "native_send_return" if sent else "source_observation", **origin}


def dialogue(messages, context, at, *, start=None, end=None, limit=32, max_chars=8000,
             include_turns=False):
    """Read a bounded, validated private native dialogue in chronological order.

    Only input observations and actual assistant send returns are exposed.  The
    returned rows intentionally contain no mutable source object so callers can
    safely place the material in an asynchronous model request.
    """
    if max_chars <= 0:
        return ()
    result = []
    remaining = max_chars
    # Apply the text budget from the latest messages backwards. Reading in
    # chronological order first could spend the whole budget on older inputs
    # and silently omit the assistant's latest care/recovery feedback.
    for row in rows(messages.runtime, context, start=start, end=end, limit=limit):
        if remaining <= 0:
            break
        try:
            item = body(messages, reference(row), context, at)
        except (TaskError, ValueError, KeyError, TypeError):
            continue
        text = str(item.get("text", "")).strip()
        if not text or remaining <= 0:
            continue
        text = text[:min(1600, remaining)]
        if not text:
            continue
        entry = {
            "speaker": item["role"],
            "text": text,
            "at": item.get("received_at") or item.get("delivered_at") or row["observed_at"],
            "observation_id": row["observation_id"],
            "content_hash": row["content_hash"],
        }
        if include_turns:
            entry.update(turn_id=row["turn_id"], event_id=row["event_id"])
        result.append(entry)
        remaining -= len(text)
    return tuple(reversed(result))


def latest_input(messages, context, at):
    for row in rows(messages.runtime, context, end=stamp(at), kind="input", limit=32):
        try:
            item = body(messages, reference(row), context, at)
        except (TaskError, ValueError, KeyError, TypeError):
            continue
        return row, item
    return None
