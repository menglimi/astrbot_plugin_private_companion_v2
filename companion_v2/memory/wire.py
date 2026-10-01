"""Read-only adapter for the review-stage memory.query.v1 wire contract.

The adapter accepts only a trusted TaskContext plus the host's authoritative
RuntimeScope projection. Request scope is checked for equality and never used
to choose an owner or grant access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import math

from companion_v2.execution.models import TaskContext, TaskError, digest, require, stamp

from . import codec
from .models import AtomRef, owner_key
from .wire_evidence import MemoryWireEvidence
from .wire_binding import (MemoryWireBinding, _WireIssue, _TOKEN, _RETENTIONS,
    _EXTENSION_NAME, _EXTENSION_VERSION, _token, _integer, _time, _unique_list,
    runtime_scope_from_task_context, RESULT_SCHEMA_VERSION, CAPABILITY_VERSION)


SCHEMA_VERSION = "memory.query.v1"
CAPABILITY_ID = "memory.query"
_PAYLOAD_FIELDS = frozenset({
    "namespace", "visibility", "purpose", "query_intent", "subjects", "types",
    "time_range", "at_time", "allowed_retention", "include_pending",
    "conflict_policy", "confidence_floor", "evidence_budget", "cursor", "extensions",
})


@dataclass(frozen=True)
class EvidenceBudget:
    max_items: int
    max_chars: int
    max_tokens: int

    def __post_init__(self):
        for name in ("max_items", "max_chars", "max_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


class MemoryQueryWireV1(MemoryWireBinding):
    """Expose the supported V2 private-fact query profile through memory.query.v1."""

    schema_version = "memory.query.v1"
    capability_id = "memory.query"

    def __init__(self, memory, *, provider_id, provider_generation, scope_for_context,
                 token_count, default_evidence_budget: EvidenceBudget,
                 max_input_bytes=65536, max_output_bytes=65536):
        super().__init__(memory, provider_id=provider_id, provider_generation=provider_generation,
                         scope_for_context=scope_for_context, max_input_bytes=max_input_bytes,
                         max_output_bytes=max_output_bytes)
        if not callable(token_count) or not isinstance(default_evidence_budget, EvidenceBudget):
            raise ValueError("a token counter and finite provider evidence budget are required")
        self.token_count = token_count
        self.default_evidence_budget = default_evidence_budget

    def _validate_request(self, context: TaskContext, request):
        call = self._validate_envelope(context, request)
        request_id, trace_id = call["request_id"], call["trace_id"]
        deadline, budget = call["deadline"], call["budget"]
        payload = request.get("payload")
        required_payload = {"namespace", "visibility", "purpose", "query_intent"}
        if type(payload) is not dict or set(payload) - _PAYLOAD_FIELDS or not required_payload.issubset(payload):
            raise _WireIssue("invalid_payload")
        namespace = _token(payload["namespace"], "namespace", maximum=128)
        visibility = _token(payload["visibility"], "visibility")
        if visibility != "private":
            raise _WireIssue("visibility_unavailable", "unavailable")
        purpose = _token(payload["purpose"], "purpose")
        if purpose != "reply":
            raise _WireIssue("purpose_unavailable", "unavailable")
        query_intent = payload["query_intent"]
        if type(query_intent) is not str or not query_intent.strip() or len(query_intent) > 2000:
            raise _WireIssue("invalid_query_intent")

        subjects = _unique_list(payload.get("subjects", []), "subjects", maximum=32,
                                 item_validator=lambda item: self._validate_subject(item))
        mapped_subjects = []
        for subject in subjects:
            if subject["kind"] == "companion.person" and subject["ref"] == context.actor.subject.subject_id:
                mapped_subjects.append("self")
            elif subject["kind"] == "companion.entity" and subject["ref"].startswith("entity:"):
                mapped_subjects.append(subject["ref"])
            else:
                raise _WireIssue("subject_mapping_unavailable", "unavailable")
        types = _unique_list(payload.get("types", []), "types", maximum=64,
                             item_validator=lambda item: _token(item, "type"))
        if types:
            raise _WireIssue("type_filter_unavailable", "unavailable")

        time_range = payload.get("time_range")
        if time_range is None:
            time_start = time_end = None
        else:
            if type(time_range) is not dict or set(time_range) != {"start", "end"}:
                raise _WireIssue("invalid_time_range")
            start = _time(time_range["start"], "time_range_start", nullable=True)
            end = _time(time_range["end"], "time_range_end", nullable=True)
            if start and end and start >= end:
                raise _WireIssue("invalid_time_range")
            time_start = stamp(start) if start else None
            time_end = stamp(end) if end else None
        at_time = payload.get("at_time")
        at_time = stamp(_time(at_time, "at_time", nullable=True)) if at_time is not None else None
        allowed_retention = _unique_list(payload.get("allowed_retention", []), "allowed_retention", maximum=4,
            item_validator=lambda item: self._validate_retention(item))
        include_pending = payload.get("include_pending", False)
        if type(include_pending) is not bool:
            raise _WireIssue("invalid_include_pending")
        if include_pending:
            if request["scope"].get("session_id") is None:
                raise _WireIssue("invalid_pending_scope")
        conflict_policy = payload.get("conflict_policy", "current_only")
        if conflict_policy not in ("current_only", "include_history"):
            raise _WireIssue("invalid_conflict_policy")
        if conflict_policy != "current_only":
            raise _WireIssue("history_query_unavailable", "unavailable")
        confidence_floor = payload.get("confidence_floor")
        if confidence_floor is not None and (type(confidence_floor) not in (int, float)
                or not math.isfinite(confidence_floor) or not 0 <= confidence_floor <= 1):
            raise _WireIssue("invalid_confidence_floor")
        cursor = payload.get("cursor")
        if cursor is not None:
            cursor = _token(cursor, "cursor")
        extensions = payload.get("extensions", {})
        if type(extensions) is not dict:
            raise _WireIssue("invalid_extensions")
        if extensions:
            for name, extension in extensions.items():
                if type(name) is not str or not _EXTENSION_NAME.fullmatch(name):
                    raise _WireIssue("invalid_extension_name")
                if (type(extension) is not dict or set(extension) != {"schema_version", "payload"}
                        or type(extension["schema_version"]) is not str
                        or not _EXTENSION_VERSION.fullmatch(extension["schema_version"])):
                    raise _WireIssue("invalid_extension")
            raise _WireIssue("extension_unavailable", "unavailable")

        evidence_budget = self._evidence_budget(context, payload.get("evidence_budget"), budget)
        if evidence_budget.max_items < 1 or evidence_budget.max_chars < 1 or evidence_budget.max_tokens < 1:
            raise _WireIssue("evidence_budget_empty")
        if budget.get("max_candidates") == 0:
            raise _WireIssue("candidate_budget_empty")

        # Trace plus immutable request semantics bind the existing bounded query session.
        # The caller's scope never contributes an owner key.
        session_payload = dict(payload)
        session_payload.pop("cursor", None)
        session_id = "memory-wire-" + digest([
            context.key, trace_id, self.provider_id, self.provider_generation,
            request["deadline_at"], request["scope"], request["budget"], session_payload,
        ])
        return {
            "request_id": request_id, "trace_id": trace_id, "deadline": deadline,
            "payload": payload, "budget": budget, "session_id": session_id,
            "namespace": namespace, "query_intent": query_intent,
            "subjects": tuple(mapped_subjects), "time_start": time_start, "time_end": time_end,
            "at_time": at_time, "allowed_retention": tuple(allowed_retention),
            "confidence_floor": confidence_floor, "cursor": cursor,
            "evidence_budget": evidence_budget,
        }

    @staticmethod
    def _validate_subject(value):
        if type(value) is not dict or set(value) != {"kind", "ref"}:
            raise _WireIssue("invalid_subject")
        _token(value["kind"], "subject_kind")
        _token(value["ref"], "subject_ref")

    @staticmethod
    def _validate_retention(value):
        if type(value) is not str or value not in _RETENTIONS:
            raise _WireIssue("invalid_allowed_retention")

    def _evidence_budget(self, context, raw, request_budget):
        if raw is None:
            requested = self.default_evidence_budget
        else:
            if type(raw) is not dict or set(raw) != {"max_items", "max_chars", "max_tokens"}:
                raise _WireIssue("invalid_evidence_budget")
            values = {name: _integer(raw[name], "evidence_" + name) for name in raw}
            if any(value < 1 for value in values.values()):
                raise _WireIssue("evidence_budget_empty")
            requested = EvidenceBudget(values["max_items"], values["max_chars"], values["max_tokens"])
        policy = self.memory.writer.access.policy_for(context)
        caps = EvidenceBudget(
            min(self.default_evidence_budget.max_items, policy.query_items),
            min(self.default_evidence_budget.max_chars, policy.query_chars),
            self.default_evidence_budget.max_tokens,
        )
        max_tokens = min(requested.max_tokens, caps.max_tokens)
        return EvidenceBudget(
            min(requested.max_items, caps.max_items),
            min(requested.max_chars, caps.max_chars),
            max_tokens,
        )

    def _token_count(self, text):
        try:
            count = self.token_count(text)
        except Exception:
            raise _WireIssue("evidence_token_accounting_unavailable", "unavailable") from None
        if type(count) is not int or count < 0:
            raise _WireIssue("evidence_token_accounting_unavailable", "unavailable")
        return count

    def _excerpt(self, text, *, max_chars, max_tokens):
        limit = min(len(text), max_chars)
        candidate = text[:limit]
        if self._token_count(candidate) <= max_tokens:
            return candidate, limit < len(text)
        low, high = 0, limit
        while low < high:
            middle = (low + high + 1) // 2
            if self._token_count(text[:middle]) <= max_tokens:
                low = middle
            else:
                high = middle - 1
        candidate = text[:low]
        if not candidate.strip():
            raise _WireIssue("evidence_budget_too_small")
        return candidate, True

    def _evidence_item(self, context, session_id, raw, remaining):
        evidence = codec.evidence(raw)
        text = self.memory.writer.access.evidence(context, evidence)
        if not text.strip():
            raise _WireIssue("evidence_excerpt_empty", "failed")
        if remaining["items"] <= 0 or remaining["chars"] <= 0 or remaining["tokens"] <= 0:
            raise _WireIssue("evidence_budget_exhausted", "failed")
        excerpt, truncated = self._excerpt(text, max_chars=remaining["chars"], max_tokens=remaining["tokens"])
        if not excerpt.strip():
            raise _WireIssue("evidence_budget_too_small")
        used_tokens = self._token_count(excerpt)
        item = {
            "ref": MemoryWireEvidence(self.memory).offer(context, session_id, evidence),
            "state": "available",
            "excerpt": excerpt,
        }
        remaining["items"] -= 1
        remaining["chars"] -= len(excerpt)
        remaining["tokens"] -= used_tokens
        return item, len(excerpt), used_tokens, truncated or len(excerpt) < len(text)

    def _subject_projection(self, context, value):
        if value == "self":
            return {"kind": "companion.person", "ref": context.actor.subject.subject_id}
        if type(value) is str and value.startswith("entity:"):
            return {"kind": "companion.entity", "ref": value}
        raise _WireIssue("subject_mapping_unavailable", "unavailable")

    def _fact(self, context, session_id, item, at_time, evidence_budget):
        current = require(self.memory.writer.read(context, AtomRef(item["atom_id"], item["revision"]), at=at_time))
        remaining = {"items": evidence_budget.max_items, "chars": evidence_budget.max_chars,
                     "tokens": evidence_budget.max_tokens}
        evidence, chars, tokens, truncated = [], 0, 0, False
        raw_evidence = current["evidence"]
        for raw in raw_evidence:
            if remaining["items"] <= 0 or remaining["chars"] <= 0 or remaining["tokens"] <= 0:
                truncated = True
                break
            try:
                entry, used_chars, used_tokens, shortened = self._evidence_item(context, session_id, raw, remaining)
            except _WireIssue as issue:
                if issue.reason_code == "evidence_budget_too_small" and evidence:
                    truncated = True
                    break
                raise
            evidence.append(entry)
            chars += used_chars
            tokens += used_tokens
            truncated = truncated or shortened
            if shortened:
                break
        if not evidence:
            raise _WireIssue("evidence_budget_too_small")
        if len(evidence) < len(raw_evidence):
            truncated = True
        return {
            "item": {
                "item_kind": "fact",
                "atom_id": current["atom_id"],
                "revision": current["revision"],
                "fact_status": "active",
                "owner_ref": "owner-" + owner_key(context),
                "assertion": {
                    "subject": self._subject_projection(context, current["subject"]),
                    "predicate": current["predicate"],
                    "object": current["object"],
                    "qualifiers": current["qualifiers"],
                    "polarity": {"positive": "affirmed", "negative": "negated", "uncertain": "unknown"}[current["polarity"]],
                    "attribution": "unknown" if current["attribution"] == "observed" else current["attribution"],
                },
                "valid_from": current["valid_from"],
                "valid_to": current["valid_to"],
                "visibility": "private",
                "evidence": evidence,
                "conflicts": [],
                "missing": ["evidence_budget_truncated"] if truncated else [],
            },
            "evidence_items": len(evidence), "evidence_chars": chars,
            "evidence_tokens": tokens, "truncated": truncated,
        }

    def handle(self, context: TaskContext, request):
        request_id = request.get("request_id") if type(request) is dict else None
        trace_id = request.get("trace_id") if type(request) is dict else None
        try:
            call = self._validate_request(context, request)
            if call["payload"].get("include_pending", False):
                from .pending_query import handle
                return handle(self, context, request, call)
            return self._query(context, request, call)
        except _WireIssue as issue:
            return self._envelope({"request_id": request_id, "trace_id": trace_id},
                status=issue.status, reason_code=issue.reason_code)
        except TaskError as error:
            if error.code == "memory_cursor_stale":
                status, reason = "rejected", "cursor_invalid"
            elif error.code in ("memory_disabled", "authorization_denied", "capability_consent_missing",
                                "capability_consent_revoked", "capability_consent_expired"):
                status, reason = "permission_denied", error.code
            elif error.code in ("memory_index_unavailable", "memory_index_busy", "memory_source_unavailable"):
                status, reason = "unavailable", error.code
            elif error.code in ("memory_query_budget_exhausted", "memory_item_budget_exceeded"):
                status, reason = "failed", error.code
            else:
                status, reason = "failed", error.code if _TOKEN.fullmatch(error.code) else "memory_query_failed"
            return self._envelope({"request_id": request_id, "trace_id": trace_id},
                status=status, reason_code=reason)
        except (TypeError, ValueError, KeyError):
            return self._envelope({"request_id": request_id, "trace_id": trace_id},
                status="rejected", reason_code="invalid_request")

    def _query(self, context, request, call):
        self.memory.writer.access.check(context, "memory.read")
        if self.memory.tasks.now() >= call["deadline"]:
            raise _WireIssue("deadline_expired", "timeout")
        policy_revision = self._policy_revision(context)
        before_revision = self.memory.query.memory_revision(context)
        policy = self.memory.writer.access.policy_for(context)
        session_expiry = min(call["deadline"], self.memory.tasks.now() + timedelta(minutes=10))
        self.memory.query.begin(context, call["session_id"], expires_at=session_expiry)
        raw = require(self.memory.query.query(
            context, call["session_id"], query_intent=call["query_intent"],
            namespace=call["namespace"], kind="facts", limit=1,
            cursor=call["cursor"], time_start=call["time_start"], time_end=call["time_end"],
            subjects=call["subjects"], at_time=call["at_time"],
            allowed_retention=call["allowed_retention"], confidence_floor=call["confidence_floor"],
            candidate_limit=min(call["budget"].get("max_candidates", self.memory.query.fact_index.candidate_items),
                                self.memory.query.fact_index.candidate_items),
        ))
        if self.memory.tasks.now() >= call["deadline"]:
            raise _WireIssue("deadline_expired", "timeout")
        after_revision = self.memory.query.memory_revision(context)
        if before_revision != after_revision or policy_revision != self._policy_revision(context):
            raise _WireIssue("memory_snapshot_changed", "rejected")
        results = []
        evidence_items = evidence_chars = evidence_tokens = 0
        truncated = False
        for result_item in raw["items"]:
            if result_item.get("kind") != "fact":
                raise _WireIssue("memory_result_shape_invalid", "failed")
            mapped = self._fact(context, call["session_id"], result_item, call["at_time"], call["evidence_budget"])
            results.append(mapped["item"])
            evidence_items += mapped["evidence_items"]
            evidence_chars += mapped["evidence_chars"]
            evidence_tokens += mapped["evidence_tokens"]
            truncated = truncated or mapped["truncated"]
        if after_revision != self.memory.query.memory_revision(context):
            raise _WireIssue("memory_snapshot_changed", "rejected")
        source_incomplete = bool(raw["unavailable_sources"])
        index_pending = raw.get("index_state") == "catching_up"
        candidates_pending = bool(raw.get("scan_limited"))
        partial_reason = ("evidence_budget_truncated" if truncated else
                          "memory_index_catching_up" if index_pending else
                          "memory_candidates_pending" if candidates_pending else
                          "memory_sources_incomplete" if source_incomplete else None)
        strategy_reason = ("memory_index_catching_up" if index_pending else
                           "memory_candidates_pending" if candidates_pending else
                           "memory_sources_incomplete" if source_incomplete else None)
        strategy_status = "partial" if strategy_reason else "succeeded"
        output = {
            "items": results,
            "next_cursor": raw["next_cursor"],
            "memory_revision": after_revision,
            "policy_revision": policy_revision,
            "coverage": [{
                "strategy_id": "companion_v2.memory." + _token(str(raw["mode"]), "strategy_id"),
                "strategy_version": "1.0",
                "status": strategy_status,
                "data_revision": after_revision,
                "reason_code": strategy_reason,
            }],
            "usage": {
                "candidates": raw.get("candidates_examined", len(raw["items"])), "model_calls": 0,
                "input_tokens": 0, "output_tokens": 0,
                "evidence_items": evidence_items, "evidence_chars": evidence_chars,
                "evidence_tokens": evidence_tokens,
            },
        }
        output_limit = min(call["budget"].get("max_output_bytes", self.max_output_bytes), self.max_output_bytes)
        if len(json.dumps(output, ensure_ascii=False, allow_nan=False,
                separators=(",", ":")).encode("utf-8")) > output_limit:
            raise _WireIssue("output_budget_exceeded")
        warnings = []
        if truncated:
            warnings.append("evidence_budget_truncated")
        if source_incomplete:
            warnings.append("some_sources_unavailable")
        if index_pending or candidates_pending:
            warnings.append(strategy_reason)
        if not results:
            warnings.append("no_match_is_not_proof_of_no_event")
        status = "partial" if partial_reason else "succeeded"
        return self._envelope(request, status=status, reason_code=partial_reason,
                              output=output, warnings=warnings)
