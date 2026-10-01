"""Validate the synchronous private string-fact proposal wire profile."""

import math

from .models import text
from .wire_binding import _WireIssue, _integer, _time, _token, _unique_list, _RETENTIONS


REQUIRED = {"namespace", "visibility", "purpose", "proposal_id", "operation", "target_atom_id", "expected_revision"}
FIELDS = REQUIRED | {"subject", "predicate", "object", "qualifiers", "polarity", "attribution",
    "representation", "confidence", "evidence_refs", "valid_from", "valid_to", "retention",
    "defer_until_boundary", "types", "extensions"}


def private_payload(payload, *, required, allowed):
    if type(payload) is not dict or not required.issubset(payload) or set(payload) - allowed:
        raise _WireIssue("invalid_payload")
    _token(payload["namespace"], "namespace", maximum=128)
    _token(payload["visibility"], "visibility")
    _token(payload["purpose"], "purpose", maximum=128)
    if payload["visibility"] != "private":
        raise _WireIssue("visibility_unavailable", "unavailable")
    if payload["purpose"] != "reply":
        raise _WireIssue("purpose_unavailable", "unavailable")


def subject(context, value):
    if type(value) is not dict or set(value) != {"kind", "ref"}:
        raise _WireIssue("invalid_subject")
    _token(value["kind"], "subject_kind")
    _token(value["ref"], "subject_ref")
    if value["kind"] == "companion.person" and value["ref"] == context.actor.subject.subject_id:
        return "self"
    if value["kind"] == "companion.entity" and value["ref"].startswith("entity:"):
        return value["ref"]
    raise _WireIssue("subject_mapping_unavailable", "unavailable")


def validate(context, payload):
    private_payload(payload, required=REQUIRED, allowed=FIELDS)
    _token(payload["proposal_id"], "proposal_id")
    operation = payload["operation"]
    if operation not in ("add", "correct", "retract", "no_op"):
        raise _WireIssue("invalid_operation")
    if operation in ("correct", "retract"):
        _token(payload["target_atom_id"], "target_atom_id")
        _integer(payload["expected_revision"], "expected_revision", minimum=1)
    elif payload["target_atom_id"] is not None or payload["expected_revision"] is not None:
        raise _WireIssue("invalid_target")
    deferred = payload.get("defer_until_boundary", False)
    if type(deferred) is not bool:
        raise _WireIssue("invalid_defer_until_boundary")
    if deferred and operation == "no_op":
        raise _WireIssue("invalid_defer_until_boundary")
    if deferred and not context.scope.session_id:
        raise _WireIssue("invalid_pending_scope")
    if operation in ("add", "correct") and not {"subject", "predicate", "object", "retention"}.issubset(payload):
        raise _WireIssue("invalid_assertion")
    values = {}
    if "subject" in payload:
        values["subject"] = subject(context, payload["subject"])
    for name in ("predicate", "object", "representation"):
        if name in payload:
            if name == "object" and type(payload[name]) is not str:
                raise _WireIssue("structured_object_unavailable", "unavailable")
            values[name] = text(payload[name], name, 8192)
    qualifiers = payload.get("qualifiers", {})
    if type(qualifiers) is not dict or len(qualifiers) > 32:
        raise _WireIssue("invalid_qualifiers")
    for key, value in qualifiers.items():
        text(key, "qualifier", 128)
        if type(value) is not str:
            raise _WireIssue("structured_qualifier_unavailable", "unavailable")
        text(value, "qualifier value", 1024, empty=True)
    values["qualifiers"] = qualifiers
    polarity = payload.get("polarity", "unknown")
    if polarity not in ("affirmed", "negated", "unknown"):
        raise _WireIssue("invalid_polarity")
    values["polarity"] = {"affirmed": "positive", "negated": "negative", "unknown": "uncertain"}[polarity]
    attribution = payload.get("attribution", "unknown")
    if attribution not in ("user", "third_party", "bot", "unknown"):
        raise _WireIssue("invalid_attribution")
    values["attribution"] = attribution
    # The internal profile requires a numeric confidence. Do not invent certainty.
    confidence = payload.get("confidence")
    if confidence is not None and (type(confidence) not in (int, float)
            or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        raise _WireIssue("invalid_confidence")
    values["confidence"] = confidence if confidence is not None else 0.0
    if "retention" in payload:
        if type(payload["retention"]) is not str or payload["retention"] not in _RETENTIONS:
            raise _WireIssue("invalid_retention")
        values["retention"] = payload["retention"]
    for name in ("valid_from", "valid_to"):
        values[name] = _time(payload.get(name), name, nullable=True)
    if values["valid_from"] and values["valid_to"] and values["valid_from"] >= values["valid_to"]:
        raise _WireIssue("invalid_validity")
    if payload.get("retention") == "short" and values["valid_to"] is None:
        raise _WireIssue("short_retention_requires_expiry")
    references = payload.get("evidence_refs", [])
    if type(references) is not list or len(references) > 32:
        raise _WireIssue("invalid_evidence_refs")
    if bool(references) != (operation != "no_op"):
        raise _WireIssue("invalid_evidence_refs")
    if any(type(ref) is not dict for ref in references):
        raise _WireIssue("invalid_evidence_ref")
    types = _unique_list(payload.get("types", []), "types", maximum=64,
                         item_validator=lambda item: _token(item, "type"))
    if types:
        raise _WireIssue("proposal_types_unavailable", "unavailable")
    if type(payload.get("extensions", {})) is not dict:
        raise _WireIssue("invalid_extensions")
    if payload.get("extensions"):
        raise _WireIssue("extension_unavailable", "unavailable")
    return values
