"""Bounded pending proposal pages alongside the ordinary fact wire query."""

from datetime import timedelta
import json
from uuid import uuid4

from companion_v2.execution.models import digest, encode, stamp, TaskError
from . import codec
from .models import owner_key, timestamp
from .wire_binding import _WireIssue


def pending_rows(adapter, context, namespace):
    return adapter.memory.runtime.read_all("""SELECT * FROM memory_operations
        WHERE owner_key = ? AND caller_id = ? AND namespace = ? AND state = 'pending'
        AND json_extract(context_json, '$.role_binding.scope.session_id') = ? ORDER BY operation_id LIMIT 257""",
        (owner_key(context), adapter.memory.writer.caller(context), namespace, context.scope.session_id))


def handle(adapter, context, request, call):
    # Fact pages, draft pages, evidence handles and their shared query budget
    # advance together, including when a response cannot fit its wire budget.
    with adapter.memory.runtime.transaction():
        return query(adapter, context, request, call)


def query(adapter, context, request, call):
    memory = adapter.memory
    memory.writer.access.check(context)
    memory.query.begin(context, call["session_id"], expires_at=min(call["deadline"], memory.tasks.now() + timedelta(minutes=10)))
    rows = pending_rows(adapter, context, call["namespace"])
    if len(rows) > 256:
        raise _WireIssue("pending_query_capacity_exceeded", "unavailable")
    fingerprint = digest([memory.query.memory_revision(context), adapter._policy_revision(context),
                          [(r["operation_id"], r["payload_hash"], r["updated_at"]) for r in rows]])
    session = memory.query._session(context, call["session_id"])
    state = json.loads(session["state_json"])
    pages = state.setdefault("wire_pending_pages", {})
    cursor = call["cursor"]
    page = pages.get(cursor) if cursor else dict(phase="facts", fact_cursor=None, offset=0, fingerprint=fingerprint)
    if not page or page["fingerprint"] != fingerprint:
        raise _WireIssue("cursor_invalid")
    if page["phase"] == "facts":
        result = adapter._query(context, request, {**call, "cursor": page["fact_cursor"]})
        if result["status"] not in ("succeeded", "partial"):
            return result
        next_fact = result["output"]["next_cursor"]
        next_page = dict(phase="facts" if next_fact else "pending", fact_cursor=next_fact, offset=0, fingerprint=fingerprint)
        more = bool(next_fact or rows)
    else:
        results, chars, tokens, count, truncated = [], 0, 0, 0, False
        offset = page["offset"]
        candidates = min(call["budget"].get("max_candidates", 128), 128)
        for row in rows[offset:offset + candidates]:
            offset += 1
            if json.loads(row["context_json"])["role_binding"] != json.loads(encode(context.role_binding)):
                continue
            item = codec.proposal(json.loads(row["proposal_json"]))
            if item.operation == "retract":
                continue  # A request to retract is not a draft affirmative assertion.
            now = timestamp(call["at_time"]) or memory.tasks.now()
            if ((item.valid_from and now < item.valid_from) or (item.valid_to and now >= item.valid_to)
                    or (call["subjects"] and item.subject not in call["subjects"])
                    or (call["allowed_retention"] and item.retention not in call["allowed_retention"])
                    or (call["confidence_floor"] is not None and item.confidence < call["confidence_floor"])
                    or (call["time_start"] and timestamp(row["created_at"]) < timestamp(call["time_start"]))
                    or (call["time_end"] and timestamp(row["created_at"]) >= timestamp(call["time_end"]))):
                continue
            haystack = (item.predicate + " " + item.object + " " + item.representation).casefold()
            if not all(term in haystack for term in call["query_intent"].casefold().split()):
                continue
            try:
                for evidence in item.evidence:
                    memory.writer.access.evidence(context, evidence)
            except TaskError:
                continue
            remaining = dict(items=call["evidence_budget"].max_items, chars=call["evidence_budget"].max_chars,
                             tokens=call["evidence_budget"].max_tokens)
            evidence_items = []
            for raw in json.loads(encode(item.evidence)):
                if min(remaining.values()) <= 0:
                    truncated = True
                    break
                mapped, used_chars, used_tokens, shortened = adapter._evidence_item(context, call["session_id"], raw, remaining)
                evidence_items.append(mapped)
                chars, tokens, count = chars + used_chars, tokens + used_tokens, count + 1
                truncated |= shortened
                if shortened:
                    break
            wire = json.loads(row["result_json"]).get("wire")
            results.append(dict(item_kind="proposal", proposal_id=wire["output"]["proposal_id"] if wire else row["operation_id"],
                proposal_state="pending", session_id=context.scope.session_id, owner_ref="owner-" + owner_key(context),
                assertion=dict(subject=adapter._subject_projection(context, item.subject), predicate=item.predicate,
                    object=item.object, qualifiers=item.qualifiers,
                    polarity={"positive": "affirmed", "negative": "negated", "uncertain": "unknown"}[item.polarity],
                    attribution="unknown" if item.attribution == "observed" else item.attribution),
                valid_from=stamp(item.valid_from) if item.valid_from else None, valid_to=stamp(item.valid_to) if item.valid_to else None,
                visibility="private", evidence=evidence_items, conflicts=[], missing=["evidence_budget_truncated"] if truncated else []))
            break
        more = offset < len(rows)
        next_page = dict(phase="pending", fact_cursor=None, offset=offset, fingerprint=fingerprint)
        result = adapter._envelope(request, status="partial" if truncated else "succeeded",
            reason_code="evidence_budget_truncated" if truncated else None,
            output=dict(items=results, next_cursor=None, memory_revision=memory.query.memory_revision(context),
                policy_revision=adapter._policy_revision(context), coverage=[dict(strategy_id="companion_v2.memory.pending",
                    strategy_version="1.0", status="succeeded", data_revision=memory.query.memory_revision(context), reason_code=None)],
                usage=dict(candidates=offset-page["offset"], model_calls=0, input_tokens=0, output_tokens=0,
                           evidence_items=count, evidence_chars=chars, evidence_tokens=tokens)))
    next_cursor = "memory-pending-page-" + uuid4().hex if more else None
    if next_cursor:
        pages[next_cursor] = next_page
    if len(pages) > 256:
        raise _WireIssue("pending_page_budget_exceeded")
    result["output"]["next_cursor"] = next_cursor
    from .wire_operations import check_output
    check_output(adapter, call, result)
    memory.writer.access.check(context)
    if memory.tasks.now() >= call["deadline"]:
        raise _WireIssue("deadline_expired", "timeout")
    current_rows = pending_rows(adapter, context, call["namespace"])
    current = digest([memory.query.memory_revision(context), adapter._policy_revision(context),
                     [(r["operation_id"], r["payload_hash"], r["updated_at"]) for r in current_rows]])
    if current != fingerprint:
        raise _WireIssue("memory_snapshot_changed")
    if page["phase"] == "pending":
        memory.query._charge(context, call["session_id"], result)
    # Ordinary fact queries also persist their cursor and read bookkeeping.
    # Merge our cursors into the latest state instead of replacing that state.
    state = json.loads(memory.query._session(context, call["session_id"])["state_json"])
    state["wire_pending_pages"] = pages
    with memory.runtime.transaction() as connection:
        connection.execute("UPDATE memory_sessions SET state_json = ? WHERE session_id = ?", (encode(state), call["session_id"]))
    return result
