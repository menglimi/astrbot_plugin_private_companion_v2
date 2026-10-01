"""Bounded lexical fact pages with per-result authoritative source checks."""

import json
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, stamp

from . import codec
from .models import AtomRef, timestamp


class FactQuery:
    def __init__(self, query, index):
        self.query, self.index = query, index

    def run(self, context, session_id, session, *, intent, namespace, limit, cursor,
            start, end, at, subjects, retention, confidence, model, candidate_limit):
        query = self.query
        policy = query.access.policy_for(context)
        expression = self.index.expression(intent)
        query_key = digest(["incremental-facts.v1", intent, namespace, start, end, at,
                            subjects, retention, confidence, model])
        state = json.loads(session["state_json"])
        previous = state["pages"].get(cursor) if cursor else None
        if cursor and (previous is None or previous["query"] != query_key):
            raise TaskError("memory_cursor_stale", "cursor belongs to a different fact query")
        snapshot = self.index.advance(context, namespace)
        offset, unavailable = 0, False
        ranking_at = at or query.tasks.now()
        if previous and previous["phase"] == "results":
            if not snapshot["ready"] or previous["fingerprint"] != snapshot["fingerprint"]:
                raise TaskError("memory_cursor_stale", "query results changed; start a fresh query in the same turn budget")
            offset, unavailable = previous["offset"], previous["unavailable"]
            # Keep SQL candidate positions stable across expiry boundaries. The
            # writer still checks today's validity and source authority below.
            ranking_at = timestamp(previous["ranking_at"])
        items, consumed, examined, used, more, scan_limited = [], 0, 0, 0, not snapshot["ready"], False
        if snapshot["ready"]:
            candidates, more = self.index.candidates(snapshot, expression, context=context,
                start=start, end=end, at=ranking_at, subjects=subjects,
                retention=retention, confidence=confidence, offset=offset, limit=candidate_limit)
            for candidate in candidates:
                if len(items) >= limit:
                    break
                examined += 1
                result = query.writer.read(context, AtomRef(candidate["id"], candidate["revision"]), at=at)
                if not result.is_success:
                    unavailable = True
                    consumed += 1
                    continue
                value = result.unwrap()
                date = timestamp(value["observed_at"])
                if (value["namespace"] != namespace or (start and date < start) or (end and date >= end)
                        or (subjects and value["subject"] not in subjects)
                        or (retention and value["retention"] not in retention)
                        or (confidence is not None and value["confidence"] < confidence)):
                    # Projection metadata can narrow a search, but only the
                    # current authoritative record can satisfy its predicates.
                    unavailable = True
                    consumed += 1
                    continue
                visible = {k: v for k, v in value.items() if k not in ("evidence", "source")}
                visible["kind"] = "fact"
                visible["sources"] = [query.offer(context, session_id, codec.evidence(e)) for e in value["evidence"]]
                size = len(encode(visible))
                if size > policy.query_chars:
                    raise TaskError("memory_item_budget_exceeded", "one result exceeds the configured result budget")
                if items and used + size > policy.query_chars:
                    break
                items.append(visible)
                used += size
                consumed += 1
            scan_limited = more and consumed == len(candidates) and len(items) < limit
            more = more or consumed < len(candidates)
        next_cursor = None
        if more:
            next_cursor = "memory-page-" + uuid4().hex
            state["pages"][next_cursor] = {"query": query_key,
                "phase": "results" if snapshot["ready"] else "index",
                "fingerprint": snapshot["fingerprint"], "offset": offset + consumed,
                "ranking_at": stamp(ranking_at), "unavailable": unavailable}
            if len(state["pages"]) > policy.turn_calls:
                raise TaskError("memory_query_budget_exhausted", "query page budget is exhausted")
            with query.runtime.transaction() as connection:
                connection.execute("UPDATE memory_sessions SET state_json = ? WHERE session_id = ?", (encode(state), session_id))
        return query._charge(context, session_id, {"items": items, "next_cursor": next_cursor,
            "mode": "lexical", "vector_coverage": None,
            "index_state": "ready" if snapshot["ready"] else "catching_up",
            "candidates_examined": examined,
            "scan_limited": scan_limited, "scope_coverage": "captured_authorized_sources_only",
            "unavailable_sources": unavailable, "complete": not more and not unavailable,
            "temporal_coverage": "current_revisions_only", "meaning": "no_match_is_not_proof_of_no_event"})
