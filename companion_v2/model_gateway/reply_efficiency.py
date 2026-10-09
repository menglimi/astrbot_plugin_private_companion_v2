"""Role-scoped reply latency projections from persisted conversation receipts."""

from datetime import datetime, timedelta, timezone
from math import ceil, isfinite
import json


SAMPLE_LIMIT = 48


def _parse_time(value):
    if type(value) is not str or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _elapsed_ms(start, end):
    start_time, end_time = _parse_time(start), _parse_time(end)
    if start_time is None or end_time is None or end_time < start_time:
        return None
    return round((end_time - start_time).total_seconds() * 1000)


def _percentile(values, percentile):
    ordered = sorted(value for value in values if type(value) is int and value >= 0)
    if not ordered:
        return None
    return ordered[max(0, ceil(len(ordered) * percentile) - 1)]


def _batch_metadata(runtime, origin_key, start_at, end_at):
    return runtime.read_all("""SELECT b.batch_id, b.created_at, b.generation_task_id, b.state AS batch_state,
            b.part_count, b.contributions_json, f.state AS flow_state, f.reason AS flow_reason,
            f.due_at AS flow_due_at, r.plan_json
        FROM conversation_batches b
        LEFT JOIN conversation_flows f ON f.batch_id = b.batch_id
        LEFT JOIN model_requests r ON r.task_id = b.generation_task_id
        WHERE b.origin_key = ? AND julianday(b.created_at) >= julianday(?)
            AND julianday(b.created_at) <= julianday(?)
        ORDER BY b.created_at DESC, b.rowid DESC""", (origin_key, start_at, end_at))


def _grouped_for_batches(runtime, table, identifiers):
    result = {}
    for offset in range(0, len(identifiers), 400):
        group = identifiers[offset:offset + 400]
        if table in ("calls", "task_starts", "model_details"):
            group = tuple(dict.fromkeys(value for value in group if value))
            if not group:
                continue
            placeholders = ",".join("?" for _ in group)
            if table == "calls":
                query = f"""SELECT task_id, COUNT(*) AS model_calls,
                        SUM(CASE WHEN state IN ('reserved', 'dispatched') THEN 1 ELSE 0 END) AS active_model_calls,
                        MIN(CASE WHEN started_at IS NOT NULL THEN started_at END) AS first_model_started_at,
                        CASE WHEN SUM(CASE WHEN state IN ('reserved', 'dispatched') THEN 1 ELSE 0 END) = 0
                            THEN MAX(CASE WHEN finished_at IS NOT NULL THEN finished_at END)
                            ELSE NULL END AS last_model_finished_at
                    FROM model_calls WHERE task_id IN ({placeholders}) GROUP BY task_id"""
            elif table == "task_starts":
                query = f"""SELECT task_id, MIN(observed_at) AS started_at FROM execution_events
                    WHERE task_id IN ({placeholders}) AND state = 'running' GROUP BY task_id"""
            else:
                query = f"""SELECT task_id, position, state, started_at, finished_at, latency_ms
                    FROM model_calls WHERE task_id IN ({placeholders}) ORDER BY task_id, position"""
            for row in runtime.read_all(query, group):
                if table == "model_details":
                    result.setdefault(row["task_id"], []).append(dict(row))
                else:
                    result[row["task_id"]] = dict(row)
            continue
        placeholders = ",".join("?" for _ in group)
        if table == "inputs":
            query = f"""SELECT batch_id, COUNT(*) AS input_count,
                    MIN(CASE WHEN json_valid(event_json) THEN json_extract(event_json, '$.received_at') END)
                        AS first_received_at,
                    MAX(CASE WHEN json_valid(event_json) THEN json_extract(event_json, '$.received_at') END)
                        AS last_received_at
                FROM conversation_inputs WHERE batch_id IN ({placeholders}) GROUP BY batch_id"""
        elif table == "parts":
            query = f"""SELECT batch_id, COUNT(*) AS stored_parts,
                    SUM(CASE WHEN state = 'delivered' THEN 1 ELSE 0 END) AS delivered_parts,
                    SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) AS failed_parts,
                    SUM(CASE WHEN state = 'unknown' THEN 1 ELSE 0 END) AS unknown_parts,
                    SUM(CASE WHEN state IN ('pending', 'dispatched', 'accepted') THEN 1 ELSE 0 END) AS pending_parts,
                    MIN(CASE WHEN dispatched_at IS NOT NULL THEN dispatched_at END) AS first_dispatched_at,
                    MIN(CASE WHEN state = 'delivered' AND delivered_at IS NOT NULL THEN delivered_at END) AS first_delivered_at,
                    MAX(CASE WHEN state = 'delivered' AND delivered_at IS NOT NULL THEN delivered_at END) AS last_delivered_at
                FROM conversation_parts WHERE batch_id IN ({placeholders}) GROUP BY batch_id"""
        elif table == "tools":
                query = f"""SELECT c.batch_id, c.sequence, c.action, c.state, c.created_at, c.finished_at,
                    i.invocation_id, i.state AS extension_state,
                    i.created_at AS extension_created_at, i.finished_at AS extension_finished_at
                FROM conversation_tool_calls c
                LEFT JOIN extension_tool_invocations i
                    ON i.parent_task_id = c.task_id AND i.tool_call_id = c.tool_call_id
                WHERE c.batch_id IN ({placeholders}) ORDER BY c.batch_id, c.sequence"""
        else:
            raise ValueError("unsupported reply-efficiency projection")
        for row in runtime.read_all(query, group):
            if table == "tools":
                result.setdefault(row["batch_id"], []).append(dict(row))
            else:
                result[row["batch_id"]] = dict(row)
    return result


def _outcome(batch, parts):
    delivered = parts.get("delivered_parts", 0) or 0
    failed = parts.get("failed_parts", 0) or 0
    unknown = parts.get("unknown_parts", 0) or 0
    pending = parts.get("pending_parts", 0) or 0
    flow_state = batch.get("flow_state") or "not_started"
    part_count = batch.get("part_count") or 0
    if delivered and (failed or unknown or delivered < part_count):
        return "partial"
    if part_count and delivered >= part_count:
        return "completed"
    if unknown:
        return "unknown"
    if pending or flow_state in ("collecting", "generating", "delivering"):
        return "pending"
    if failed or flow_state in ("blocked", "closed") or (flow_state == "complete" and part_count == 0):
        return "no_reply"
    return "incomplete"


def _project(batch, inputs, parts, calls, task_start, model_details, tool_details):
    received_at = inputs.get("first_received_at") or batch["created_at"]
    last_input_received_at = inputs.get("last_received_at") or received_at
    first_model_started_at = calls.get("first_model_started_at")
    last_model_finished_at = calls.get("last_model_finished_at")
    first_dispatched_at = parts.get("first_dispatched_at")
    first_delivered_at = parts.get("first_delivered_at")
    last_delivered_at = parts.get("last_delivered_at")
    part_count = batch["part_count"] or 0
    delivered_parts = parts.get("delivered_parts", 0) or 0
    outcome = _outcome(batch, parts)
    completed = outcome == "completed"
    try:
        contribution_snapshot = json.loads(batch.get("contributions_json") or "{}")
    except (TypeError, ValueError):
        contribution_snapshot = {}
    raw_materials = contribution_snapshot.get("materials", []) if isinstance(contribution_snapshot, dict) else []
    materials = [{
        "owner": item.get("owner", "")[:80] if type(item.get("owner")) is str else "",
        "purpose": item.get("purpose", "")[:100] if type(item.get("purpose")) is str else "",
        "state": item.get("state") if item.get("state") in ("ready", "deferred", "unavailable") else "unknown",
    } for item in raw_materials[:32] if isinstance(item, dict)] if isinstance(raw_materials, list) else []
    try:
        request_plan = json.loads(batch.get("plan_json") or "{}")
    except (TypeError, ValueError):
        request_plan = {}
    offered_actions = request_plan.get("tool_actions") if isinstance(request_plan, dict) else None
    offered_tool_count = len(offered_actions) if isinstance(offered_actions, list) else None
    offered_tools = list(dict.fromkeys(
        action[:120] for action in offered_actions if type(action) is str and action
    ))[:32] if isinstance(offered_actions, list) else []
    model_steps = []
    for item in model_details:
        latency = item.get("latency_ms")
        elapsed = (round(latency) if type(latency) in (int, float) and isfinite(latency) and latency >= 0
                   else _elapsed_ms(item.get("started_at"), item.get("finished_at")))
        model_steps.append({
            "position": item["position"], "state": item["state"],
            "started_at": item.get("started_at"), "finished_at": item.get("finished_at"),
            "elapsed_ms": elapsed,
        })
    tool_steps = [{
        "sequence": item["sequence"], "action": item["action"],
        "kind": "extension" if item.get("invocation_id") else "builtin",
        "state": item.get("extension_state") or item["state"],
        "started_at": item.get("extension_created_at") or item.get("created_at"),
        "finished_at": item.get("extension_finished_at") or item.get("finished_at"),
        "elapsed_ms": _elapsed_ms(item.get("created_at"), item.get("finished_at")),
        "extension_started_at": item.get("extension_created_at"),
        "extension_finished_at": item.get("extension_finished_at"),
        "extension_elapsed_ms": _elapsed_ms(item.get("extension_created_at"), item.get("extension_finished_at"))
            if item.get("invocation_id") else None,
    } for item in tool_details]
    flow_due_at = batch.get("flow_due_at")
    generation_started_at = task_start.get("started_at")
    return {
        "batch_id": batch["batch_id"],
        "batch_state": batch["batch_state"],
        "received_at": received_at,
        "received_time_source": "input_event" if inputs.get("first_received_at") else "batch_created",
        "flow_state": batch.get("flow_state") or "not_started",
        "flow_reason": batch.get("flow_reason") or "",
        "outcome": outcome,
        "input_count": inputs.get("input_count", 0),
        "part_count": part_count,
        "delivered_parts": delivered_parts,
        "failed_parts": parts.get("failed_parts", 0) or 0,
        "unknown_parts": parts.get("unknown_parts", 0) or 0,
        "pending_parts": parts.get("pending_parts", 0) or 0,
        "model_calls": calls.get("model_calls", 0),
        "active_model_calls": calls.get("active_model_calls", 0) or 0,
        "timestamps": {
            "received_at": received_at,
            "last_input_received_at": last_input_received_at,
            "flow_due_at": flow_due_at,
            "generation_started_at": generation_started_at,
            "first_model_started_at": first_model_started_at,
            "last_model_finished_at": last_model_finished_at,
            "first_dispatched_at": first_dispatched_at,
            "first_delivered_at": first_delivered_at,
            "last_delivered_at": last_delivered_at,
        },
        "stages": {
            "pre_model_ms": _elapsed_ms(received_at, first_model_started_at),
            "last_input_to_model_ms": _elapsed_ms(last_input_received_at, first_model_started_at),
            "model_ms": _elapsed_ms(first_model_started_at, last_model_finished_at),
            "post_model_ms": _elapsed_ms(last_model_finished_at, first_dispatched_at),
            "first_reply_ms": _elapsed_ms(received_at, first_delivered_at),
            "delivery_ms": _elapsed_ms(first_dispatched_at, last_delivered_at),
            "end_to_end_ms": _elapsed_ms(received_at, last_delivered_at) if completed else None,
        },
        "trace": {
            "input_wait_ms": _elapsed_ms(last_input_received_at, flow_due_at),
            "queue_wait_ms": _elapsed_ms(flow_due_at, generation_started_at),
            "preparation_ms": _elapsed_ms(generation_started_at, first_model_started_at),
            "materials": materials,
            "offered_tool_count": offered_tool_count,
            "offered_tools": offered_tools,
            "model_calls": model_steps,
            "tool_calls": tool_steps,
        },
        "observed": {
            "received": bool(inputs.get("first_received_at")),
            "model_started": bool(first_model_started_at),
            "model_finished": bool(last_model_finished_at),
            "first_dispatched": bool(first_dispatched_at),
            "first_delivered": bool(first_delivered_at),
            "final_delivered": bool(part_count and delivered_parts >= part_count and last_delivered_at),
        },
    }


def reply_efficiency_report(runtime, origin_key, now):
    """Return a seven-calendar-day, body-free response timing report for one role."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    batches = _batch_metadata(runtime, origin_key, window_start.isoformat(), now.isoformat())
    batch_ids = [row["batch_id"] for row in batches]
    task_ids = [row["generation_task_id"] for row in batches]
    inputs_by_batch = _grouped_for_batches(runtime, "inputs", batch_ids)
    parts_by_batch = _grouped_for_batches(runtime, "parts", batch_ids)
    calls_by_task = _grouped_for_batches(runtime, "calls", task_ids)
    task_starts = _grouped_for_batches(runtime, "task_starts", task_ids)
    model_details = _grouped_for_batches(runtime, "model_details", task_ids)
    tools_by_batch = _grouped_for_batches(runtime, "tools", batch_ids)

    samples = [_project(dict(batch), inputs_by_batch.get(batch["batch_id"], {}),
                        parts_by_batch.get(batch["batch_id"], {}),
                        calls_by_task.get(batch["generation_task_id"], {}),
                        task_starts.get(batch["generation_task_id"], {}),
                        model_details.get(batch["generation_task_id"], ()),
                        tools_by_batch.get(batch["batch_id"], ())) for batch in batches]
    stage_keys = ("end_to_end_ms", "first_reply_ms", "pre_model_ms", "last_input_to_model_ms", "model_ms",
                  "post_model_ms", "delivery_ms")
    stage_values = {key: [sample["stages"][key] for sample in samples] for key in stage_keys}
    summary = {
        "samples": len(samples),
        "completed": sum(sample["outcome"] == "completed" for sample in samples),
        "partial": sum(sample["outcome"] == "partial" for sample in samples),
        "unknown": sum(sample["outcome"] == "unknown" for sample in samples),
        "pending": sum(sample["outcome"] == "pending" for sample in samples),
        "no_reply": sum(sample["outcome"] == "no_reply" for sample in samples),
        "incomplete": sum(sample["outcome"] == "incomplete" for sample in samples),
        "median_end_to_end_ms": _percentile(stage_values["end_to_end_ms"], 0.5),
        "p95_end_to_end_ms": _percentile(stage_values["end_to_end_ms"], 0.95),
        "median_first_reply_ms": _percentile(stage_values["first_reply_ms"], 0.5),
        "p95_first_reply_ms": _percentile(stage_values["first_reply_ms"], 0.95),
        "median_pre_model_ms": _percentile(stage_values["pre_model_ms"], 0.5),
        "median_last_input_to_model_ms": _percentile(stage_values["last_input_to_model_ms"], 0.5),
        "median_model_ms": _percentile(stage_values["model_ms"], 0.5),
        "median_post_model_ms": _percentile(stage_values["post_model_ms"], 0.5),
        "median_delivery_ms": _percentile(stage_values["delivery_ms"], 0.5),
    }
    coverage_keys = ("received", "model_started", "model_finished", "first_dispatched", "first_delivered", "final_delivered")
    coverage = {key: sum(sample["observed"][key] for sample in samples) for key in coverage_keys}
    by_day = {}
    cursor = window_start.date()
    while cursor <= now.date():
        by_day[cursor.isoformat()] = []
        cursor += timedelta(days=1)
    for sample in samples:
        by_day.setdefault(sample["received_at"][:10], []).append(sample)
    daily = []
    for day, entries in sorted(by_day.items()):
        values = [entry["stages"]["end_to_end_ms"] for entry in entries]
        daily.append({"day": day, "samples": len(entries),
                      "completed": sum(entry["outcome"] == "completed" for entry in entries),
                      "median_end_to_end_ms": _percentile(values, 0.5),
                      "p95_end_to_end_ms": _percentile(values, 0.95)})
    return {
        "generated_at": now.isoformat(),
        "window_days": 7,
        "window_start": window_start.isoformat(),
        "sample_limit": SAMPLE_LIMIT,
        "summary": summary,
        "coverage": coverage,
        "recent": samples[:SAMPLE_LIMIT],
        "daily": daily,
    }
