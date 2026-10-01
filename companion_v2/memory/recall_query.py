"""Finite candidate pages with current original-object and source checks."""

import json
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, stamp

from .fact_index import FactIndex
from .models import timestamp
from . import recall_vectors
from .mmr import rank as mmr_rank


class RecallQuery:
    def __init__(self, query, index, objects):
        self.query, self.index, self.objects = query, index, objects

    def run(self, context, session_id, session, *, intent, namespace, kind, limit, cursor,
            start, end, at, subjects, retention, confidence, vector, model, candidate_limit):
        query, policy = self.query, self.query.access.policy_for(context)
        expression = FactIndex.expression(intent)
        if vector is not None:
            recall_vectors.validate(vector, model)
        key = digest(["incremental-recall.v1", intent, namespace, kind, start, end, at,
                      subjects, retention, confidence, vector, model])
        state = json.loads(session["state_json"])
        previous = state["pages"].get(cursor) if cursor else None
        if cursor and (previous is None or previous["query"] != key):
            raise TaskError("memory_cursor_stale", "cursor belongs to a different memory query")
        snapshot = self.index.advance(context, namespace, kind)
        offset, unavailable, ranking_at = 0, snapshot.get("unavailable", False), at or query.tasks.now()
        if previous and previous["phase"] in ("results", "vectors"):
            if not snapshot["ready"] or snapshot["fingerprint"] != previous["fingerprint"]:
                raise TaskError("memory_cursor_stale", "query results changed; start a fresh query in the same turn budget")
            offset, unavailable = previous["offset"], previous["unavailable"] or unavailable
            ranking_at = timestamp(previous["ranking_at"])
        filters = self.index.filters(snapshot, context=context, start=start, end=end, at=ranking_at,
                                     subjects=subjects, retention=retention, confidence=confidence)
        phase, coverage, job = "index", None, None
        if snapshot["ready"]:
            phase = "results"
            if vector is not None:
                job, progress = recall_vectors.advance(self.index, snapshot, session=session,
                    filters=filters, vector=vector, model=model)
                phase = "results" if progress["ready"] else "vectors"
                coverage = {"embedded": progress["embedded"], "eligible": progress.get("eligible"),
                            "model": model, "complete": progress["ready"], "basis": "projected_candidates"}
        items, consumed, examined, used, scan_limited = [], 0, 0, 0, False
        pending_ids, pending_more = (), False
        more = phase != "results"
        if phase == "results":
            use_mmr = vector is not None
            if use_mmr and previous and previous.get("pending"):
                pending_ids = tuple(previous["pending"])
                candidates = self.index.candidates_for_ids(snapshot, pending_ids)
                pending_more = bool(previous.get("pending_more", False))
                more = pending_more
                next_offset = previous["offset"]
            else:
                candidates, more = self.index.candidates(snapshot, expression, filters=filters,
                    offset=offset, limit=candidate_limit, vector_job=job)
                pending_more = more
                next_offset = offset + len(candidates)

            if not use_mmr:
                for candidate in candidates:
                    if len(items) >= limit:
                        break
                    examined += 1
                    try:
                        value = self.objects.read(context, candidate, at=at)
                        date = timestamp(value["observed_at"])
                        if ((start and date < start) or (end and date >= end)
                                or (subjects and value.get("subject") not in subjects
                                    and not set(subjects).intersection(value.get("entities", ())))
                                or (candidate["producer"] == "fact" and (
                                    value["namespace"] != namespace
                                    or (retention and value["retention"] not in retention)
                                    or (confidence is not None and value["confidence"] < confidence)))):
                            raise TaskError("memory_candidate_changed", "current original does not satisfy query filters")
                        visible = self.objects.visible(context, session_id, candidate, value)
                    except TaskError:
                        unavailable = True
                        consumed += 1
                        continue
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
            else:
                # Read the whole bounded candidate window before ranking. This
                # keeps authorization and current-source checks ahead of MMR;
                # the derived vector cache never decides visibility.
                authorized = {}
                ordered = []
                for candidate in candidates:
                    examined += 1
                    try:
                        value = self.objects.read(context, candidate, at=at)
                        date = timestamp(value["observed_at"])
                        if ((start and date < start) or (end and date >= end)
                                or (subjects and value.get("subject") not in subjects
                                    and not set(subjects).intersection(value.get("entities", ())))
                                or (candidate["producer"] == "fact" and (
                                    value["namespace"] != namespace
                                    or (retention and value["retention"] not in retention)
                                    or (confidence is not None and value["confidence"] < confidence)))):
                            raise TaskError("memory_candidate_changed", "current original does not satisfy query filters")
                    except TaskError:
                        unavailable = True
                        consumed += 1
                        continue
                    authorized[candidate["id"]] = (candidate, value)

                if pending_ids:
                    ordered = [authorized[identifier] for identifier in pending_ids if identifier in authorized]
                elif authorized:
                    authorized_candidates = [record[0] for record in authorized.values()]
                    vectors = recall_vectors.document_vectors(
                        self.index, snapshot, authorized_candidates,
                        model=model, dimensions=len(vector),
                    )
                    ranked_ids = mmr_rank(
                        [candidate["id"] for candidate in authorized_candidates],
                        [candidate["recall_score"] for candidate in authorized_candidates],
                        vectors=vectors, lambda_mult=0.7,
                    )
                    ordered = [authorized[identifier] for identifier in ranked_ids]

                remaining = []
                for position, (candidate, value) in enumerate(ordered):
                    if len(items) >= limit:
                        remaining.extend(record[0]["id"] for record in ordered[position:])
                        break
                    try:
                        visible = self.objects.visible(context, session_id, candidate, value)
                        size = len(encode(visible))
                        if size > policy.query_chars:
                            raise TaskError("memory_item_budget_exceeded", "one result exceeds the configured result budget")
                        if items and used + size > policy.query_chars:
                            remaining.extend(record[0]["id"] for record in ordered[position:])
                            break
                    except TaskError:
                        unavailable = True
                        consumed += 1
                        continue
                    items.append(visible)
                    used += size
                    consumed += 1
                pending_ids = tuple(remaining)
                more = bool(pending_ids) or pending_more
                scan_limited = bool(more and not items and examined == len(candidates))
        next_cursor = None
        if more:
            next_cursor = "memory-page-" + uuid4().hex
            page = {"query": key, "phase": phase, "fingerprint": snapshot["fingerprint"],
                    "offset": next_offset if vector is not None and phase == "results" else offset + consumed,
                    "ranking_at": stamp(ranking_at), "unavailable": unavailable}
            if vector is not None and phase == "results":
                page.update({"pending": list(pending_ids), "pending_more": pending_more})
            state["pages"][next_cursor] = page
            if len(state["pages"]) > policy.turn_calls:
                raise TaskError("memory_query_budget_exhausted", "query page budget is exhausted")
            with query.runtime.transaction() as db:
                db.execute("UPDATE memory_sessions SET state_json = ? WHERE session_id = ?", (encode(state), session_id))
        return query._charge(context, session_id, {"items": items, "next_cursor": next_cursor,
            "mode": "hybrid" if vector is not None else "lexical", "vector_coverage": coverage,
            "index_state": "catching_up" if phase == "index" else "ranking" if phase == "vectors" else "ready",
            "candidates_examined": examined, "scan_limited": scan_limited,
            "scope_coverage": "captured_authorized_sources_only", "unavailable_sources": unavailable,
            "complete": not more and not unavailable, "temporal_coverage": "current_revisions_only",
            "meaning": "no_match_is_not_proof_of_no_event"})
