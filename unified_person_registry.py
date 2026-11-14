"""Companion-owned Unified Person registry for the chat-side plugin.

This module is deliberately a small boundary around ``person_context_contract``:
the companion may create and link identities, while consumers only read the
contract projection.  Group overlays are scoped records and never become
profile facts.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import threading
import re
from typing import Any

try:
    from .person_context_contract import (
        build_identity_key,
        build_person_projection,
        ensure_person_store,
        person_id_for_identity,
        resolve_identity,
        validate_projection,
    )
    from .p4_affinity_confinement import validate_runtime_state
    from .identity_namespace import AssurancePolicy, NamespaceContext
except ImportError:
    from person_context_contract import (
        build_identity_key,
        build_person_projection,
        ensure_person_store,
        person_id_for_identity,
        resolve_identity,
        validate_projection,
    )
    from p4_affinity_confinement import validate_runtime_state
    from identity_namespace import AssurancePolicy, NamespaceContext


_LOCK = threading.RLock()
_FORBIDDEN = {
    "raw_prompt", "prompt", "private_object", "private_object_ref", "object",
    "chat_text", "chat_history", "conversation", "conversation_text", "content",
    "evidence_body", "evidence_text", "message_history", "message_text", "messages",
    "raw_content", "transcript", "database",
}
_CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_KEY_SEPARATOR_RE = re.compile(r"[\s\-./:]+")
_IDENTITY_FIELDS = (
    "companion_instance_id", "bot_account_id", "adapter_instance_id",
    "subject_namespace", "platform_subject_id",
)
_IDENTITY_ASSURANCE_RANK = {
    "unverified": 0,
    "observed": 1,
    "verified": 2,
    "explicit_linked": 3,
}
_P4_EFFECT_VERSION = 1
_P4_EFFECT_ALLOWED_FIELDS = frozenset({
    "event_id", "occurred_at", "kind", "source_kind", "target_kind", "authority",
    "reason_code", "safe_reference", "safe_hash", "status", "shadow_only",
})
_P4_EFFECT_FORBIDDEN_FIELDS = frozenset({
    "raw_prompt", "prompt", "text", "content", "chat_text", "messages", "transcript",
    "private_object", "private_object_ref", "database", "db", "score", "penalty",
    "confinement_state", "confinement_until", "authorized", "owner",
})
_P4_EFFECT_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
_P4_EFFECT_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
PERSON_PURGE_RETENTION_SECONDS = 7 * 24 * 60 * 60
_PROFILE_FACT_FIELDS = frozenset({
    "display_name", "preferred_address", "style", "profile_origin", "auto_profile_created",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(value: Any, depth: int = 0) -> Any:
    """Copy only bounded JSON-like values and drop context-bearing fields."""
    if depth > 2:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return " ".join(_CONTROL_CHARACTER_RE.sub(" ", value).split())[:240]
    if isinstance(value, (list, tuple)):
        result = []
        for item in list(value)[:16]:
            safe = _safe(item, depth + 1)
            if safe not in (None, "", [], {}):
                result.append(safe)
        return result
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:32]:
            if not isinstance(key, str) or _CONTROL_CHARACTER_RE.search(key):
                continue
            name = _KEY_SEPARATOR_RE.sub("_", key.strip().lower()).strip("_")
            if not name or name in _FORBIDDEN:
                continue
            safe = _safe(item, depth + 1)
            if safe is not None:
                result[name[:80]] = safe
        return result
    return None


def _text(value: Any, field: str, limit: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}_invalid")
    value = value.strip()
    if not value or _CONTROL_CHARACTER_RE.search(value) or len(value) > limit:
        raise ValueError(f"{field}_invalid")
    return value


def _operation_id(value: Any) -> str:
    if value in (None, ""):
        return ""
    return _text(value, "operation_id", 120)


def _safe_affinity_score(value: Any) -> int:
    """Normalize optional profile affinity without letting malformed input abort creation."""
    if isinstance(value, bool):
        return 0
    try:
        score = int(float(value)) if value not in (None, "") else 0
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(-1200, min(1200, score))


def _identity(identity: Any) -> dict[str, str]:
    if not isinstance(identity, dict):
        raise ValueError("identity_invalid")
    # build_identity_key is the contract authority; this explicit check also
    # prevents accidental partial identity records from being persisted.
    normalized = {field: _text(identity.get(field), field) for field in _IDENTITY_FIELDS}
    normalized["subject_namespace"] = normalized["subject_namespace"].lower()
    build_identity_key(normalized)
    return normalized


def _root(store: dict[str, Any]) -> dict[str, Any]:
    ensure_person_store(store)
    root = store["unified_person"]
    if not isinstance(root.get("profiles"), dict):
        root["profiles"] = {}
    if not isinstance(root.get("identity_links"), dict):
        root["identity_links"] = {}
    if not isinstance(root.get("group_overlays"), dict):
        root["group_overlays"] = {}
    if not isinstance(root.get("audit_events"), list):
        root["audit_events"] = []
    if not isinstance(root.get("operations"), dict):
        root["operations"] = {}
    if not isinstance(root.get("binding_checkpoints"), dict):
        root["binding_checkpoints"] = {}
    if not isinstance(root.get("detached_identity_links"), dict):
        root["detached_identity_links"] = {}
    if not isinstance(root.get("person_tombstones"), dict):
        root["person_tombstones"] = {}
    if not isinstance(root.get("identity_tombstones"), dict):
        root["identity_tombstones"] = {}
    return root


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> float:
    try:
        text = _text(value, "timestamp", 80).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return -1.0


def _contains_exact_value(value: Any, expected: str, *, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, str):
        return value == expected
    if isinstance(value, dict):
        return any(_contains_exact_value(item, expected, depth=depth + 1) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_exact_value(item, expected, depth=depth + 1) for item in value)
    return False


def _person_identity_assurance(root: dict[str, Any], person_id: str) -> str:
    """Derive profile assurance from the person's remaining active links."""
    assurances: list[str] = []
    for link in root["identity_links"].values():
        if not isinstance(link, dict) or link.get("person_id") != person_id or link.get("status") != "active":
            continue
        assurance = link.get("identity_assurance")
        assurances.append(
            assurance
            if isinstance(assurance, str) and assurance in _IDENTITY_ASSURANCE_RANK
            else "observed"
        )
    return max(assurances, key=_IDENTITY_ASSURANCE_RANK.__getitem__) if assurances else "unverified"


def _contains_forbidden_key(value: Any) -> bool:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or key.strip().lower() in _P4_EFFECT_FORBIDDEN_FIELDS:
                return True
            if _contains_forbidden_key(item):
                return True
        return False
    if type(value) in (list, tuple):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _p4_effect_container(root: dict[str, Any]) -> dict[str, Any] | None:
    """Return the separate preparation ledger, without repairing corruption."""
    existing = root.get("p4_effect")
    if existing is None:
        existing = {"version": _P4_EFFECT_VERSION, "people": {}, "operations": {}}
        root["p4_effect"] = existing
    if not isinstance(existing, dict):
        return None
    if existing.get("version") != _P4_EFFECT_VERSION:
        return None
    if not isinstance(existing.get("people"), dict) or not isinstance(existing.get("operations"), dict):
        return None
    return existing


def _normalize_p4_effect_event(event: Any) -> tuple[dict[str, Any] | None, str]:
    if type(event) is not dict or _contains_forbidden_key(event):
        return None, "invalid_p4_effect_event"
    if any(type(key) is not str or key not in _P4_EFFECT_ALLOWED_FIELDS for key in event):
        return None, "invalid_p4_effect_event"
    if type(event.get("event_id")) is not str or _P4_EFFECT_TOKEN_RE.fullmatch(event["event_id"]) is None:
        return None, "invalid_p4_effect_event"
    occurred_at = event.get("occurred_at")
    if type(occurred_at) is not str or _P4_EFFECT_TIMESTAMP_RE.fullmatch(occurred_at) is None:
        return None, "invalid_p4_effect_event"
    try:
        parsed_occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None, "invalid_p4_effect_event"
    if parsed_occurred_at.tzinfo is None or parsed_occurred_at.utcoffset() is None:
        return None, "invalid_p4_effect_event"
    if type(event.get("kind")) is not str or _P4_EFFECT_TOKEN_RE.fullmatch(event["kind"]) is None:
        return None, "invalid_p4_effect_event"
    normalized: dict[str, Any] = {
        "event_id": event["event_id"],
        "occurred_at": occurred_at,
        "kind": event["kind"],
    }
    for field in ("source_kind", "target_kind", "authority", "reason_code", "safe_reference"):
        if field not in event:
            continue
        value = event[field]
        if type(value) is type(None):
            continue
        if type(value) is not str:
            return None, "invalid_p4_effect_event"
        if value == "":
            continue
        if _P4_EFFECT_TOKEN_RE.fullmatch(value) is None:
            return None, "invalid_p4_effect_event"
        normalized[field] = value
    if "safe_hash" in event:
        safe_hash = event["safe_hash"]
        if type(safe_hash) is not type(None):
            if type(safe_hash) is not str:
                return None, "invalid_p4_effect_event"
            if safe_hash and re.fullmatch(r"sha256:[0-9a-f]{64}", safe_hash) is None:
                return None, "invalid_p4_effect_event"
            if safe_hash:
                normalized["safe_hash"] = safe_hash
    if "status" in event:
        status = event.get("status")
        if type(status) is not str or status not in {"shadow", "invalid", "degraded"}:
            return None, "invalid_p4_effect_event"
        normalized["status"] = status
    if "shadow_only" in event:
        if event.get("shadow_only") is not True:
            return None, "invalid_p4_effect_event"
        normalized["shadow_only"] = True
    return normalized, ""


def _p4_effect_fingerprint(person_id: str, event: dict[str, Any]) -> str:
    return _fingerprint({"person_id": person_id, "event": event})


def _p4_effect_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    last = events[-1] if events else {}
    return {
        "mode": "effect_preparation",
        "event_count": len(events),
        "last_event_id": str(last.get("event_id") or ""),
        "last_kind": str(last.get("kind") or ""),
    }


def _p4_effect_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "effect_preparation",
        "event_count": max(0, min(512, int(state.get("event_count") or 0))),
        "last_kind": str(state.get("last_kind") or "")[:80],
    }


def _replay_p4_effect_entry(entry: Any, person_id: str) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None, str]:
    if type(entry) is not dict or entry.get("person_id") != person_id:
        return None, None, "p4_effect_person_conflict"
    events = entry.get("events")
    if type(events) is not list or len(events) > 512:
        return None, None, "p4_effect_corrupt"
    normalized_events: list[dict[str, Any]] = []
    event_index: dict[str, dict[str, Any]] = {}
    for envelope in events:
        if type(envelope) is not dict or set(envelope) != {"event_id", "person_id", "origin_person_id", "event", "event_fingerprint", "recorded_at", "operation_id"}:
            return None, None, "p4_effect_corrupt"
        if envelope.get("person_id") != person_id or type(envelope.get("origin_person_id")) is not str or not envelope["origin_person_id"]:
            return None, None, "p4_effect_corrupt"
        event, error = _normalize_p4_effect_event(envelope.get("event"))
        if event is None or envelope.get("event_id") != event.get("event_id"):
            return None, None, error or "p4_effect_corrupt"
        event_id = event["event_id"]
        if event_id in event_index or envelope.get("event_fingerprint") != _p4_effect_fingerprint(envelope["origin_person_id"], event):
            return None, None, "p4_effect_corrupt"
        event_index[event_id] = deepcopy(envelope)
        normalized_events.append(event)
    state = _p4_effect_state(normalized_events)
    if entry.get("state") != state:
        return None, None, "p4_effect_state_mismatch"
    return state, event_index, ""


class UnifiedPersonRegistry:
    """The only chat-side writer for Unified Person identity state."""

    def __init__(self, store: dict[str, Any]) -> None:
        if not isinstance(store, dict):
            raise ValueError("store_invalid")
        self._store = store

    def is_bound_to(self, store: Any) -> bool:
        """Report whether this lightweight facade targets the active persona store."""
        return self._store is store

    def status(self) -> dict[str, Any]:
        with _LOCK:
            try:
                root = _root(self._store)
            except (TypeError, ValueError):
                return {"state": "invalid", "profiles": 0, "identity_links": 0, "group_overlays": 0}
            profiles = root["profiles"]
            links = root["identity_links"]
            overlays = root["group_overlays"]
            state = "resolved" if profiles and links else "pending"
            if any(not isinstance(item, dict) for item in profiles.values()):
                state = "invalid"
            return {
                "state": state,
                "version": int(root.get("version") or 1),
                "profiles": len(profiles),
                "identity_links": len(links),
                "group_overlays": len(overlays),
                "audit_events": len(root["audit_events"]),
                "operations": len(root["operations"]),
            }

    def resolve(self, identity: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            try:
                result = resolve_identity(self._store, identity)
            except (TypeError, ValueError):
                return {"state": "invalid", "identity_key": "", "person_id": "", "errors": ["identity_invalid"]}
            if result.get("state") not in {"pending", "invalid", "resolved", "degraded"}:
                result["state"] = "invalid"
            return deepcopy(result)

    def namespace_context(
        self,
        identity: dict[str, Any],
        *,
        kind: str,
        group_id: str = "",
        policy_version: str,
        migration_epoch: str,
        purpose: str = "memory_read",
    ) -> dict[str, Any]:
        """Resolve a strict Shadow namespace without changing legacy state.

        A complete five-field identity that exactly matches an active link is
        treated as ``verified`` for the new read matrix.  The legacy v1 profile
        keeps its historical ``observed`` value, avoiding a silent contract
        change for old consumers.  Missing links are routed to ``pending`` and
        therefore fail closed for every formal purpose.
        """
        try:
            normalized = _identity(identity)
            identity_key = build_identity_key(normalized)
        except (TypeError, ValueError):
            return {"ok": False, "code": "identity_invalid", "context": None, "decision": "namespace_context_missing"}
        with _LOCK:
            root = _root(self._store)
            link = root["identity_links"].get(identity_key)
            linked = isinstance(link, dict) and link.get("status") == "active" and bool(link.get("person_id"))
            person_id = str(link.get("person_id") or "") if linked else person_id_for_identity(normalized)
            profile = root["profiles"].get(person_id) if linked else None
            status = str(profile.get("profile_status") or "active") if isinstance(profile, dict) else "active"
            stored_assurance = str(link.get("identity_assurance") or "observed") if linked else "unverified"
        assurance = "explicit_linked" if stored_assurance == "explicit_linked" else "verified" if linked else "unverified"
        effective_kind = kind if linked else "pending"
        context = NamespaceContext(
            kind=effective_kind,
            identity_id=person_id,
            group_id=group_id if effective_kind in {"group_member", "group_shared"} else "",
            assurance=assurance,
            profile_status=status,
            policy_version=policy_version,
            migration_epoch=migration_epoch,
        )
        decision = AssurancePolicy.authorize(context, purpose)
        return {
            "ok": decision.allowed,
            "code": "namespace_resolved" if decision.allowed else decision.code,
            "identity_key": identity_key,
            "person_id": person_id,
            "context": context.to_dict(),
            "decision": decision.code,
        }

    def formal_namespace_for_person(
        self,
        person_id: str,
        *,
        kind: str = "private",
        group_id: str = "",
        policy_version: str,
        migration_epoch: str,
        purpose: str = "relationship_write",
    ) -> dict[str, Any]:
        """Resolve one person's primary exact link without guessing a subject."""
        try:
            clean_person = _text(person_id, "person_id")
        except ValueError:
            return {"ok": False, "code": "identity_invalid", "context": None, "decision": "identity_invalid"}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict) or profile.get("profile_status", "active") != "active":
                return {"ok": False, "code": "profile_status_denied", "context": None, "decision": "profile_status_denied"}
            identity_key = str(profile.get("resolved_identity_key") or "")
            identity_keys = profile.get("identity_keys")
            if (
                not isinstance(identity_keys, list)
                or any(not isinstance(item, str) for item in identity_keys)
                or len(set(identity_keys)) != len(identity_keys)
                or identity_key not in identity_keys
            ):
                return {"ok": False, "code": "identity_exact_link_invalid", "context": None, "decision": "identity_exact_link_invalid"}
            active_keys = {
                str(key)
                for key, candidate in root["identity_links"].items()
                if isinstance(candidate, dict)
                and candidate.get("status") == "active"
                and candidate.get("person_id") == clean_person
            }
            if active_keys != set(identity_keys):
                return {"ok": False, "code": "identity_exact_link_invalid", "context": None, "decision": "identity_exact_link_invalid"}
            for candidate_key in identity_keys:
                candidate = root["identity_links"].get(candidate_key)
                try:
                    if not isinstance(candidate, dict) or candidate.get("identity_key") != candidate_key:
                        raise ValueError("identity_link_invalid")
                    normalized = _identity(candidate.get("identity"))
                    if build_identity_key(normalized) != candidate_key:
                        raise ValueError("identity_key_mismatch")
                except (TypeError, ValueError):
                    return {"ok": False, "code": "identity_exact_link_invalid", "context": None, "decision": "identity_exact_link_invalid"}
            link = root["identity_links"][identity_key]
            assurance = "explicit_linked" if link.get("identity_assurance") == "explicit_linked" else "verified"
        context = NamespaceContext(
            kind=kind,
            identity_id=clean_person,
            group_id=group_id if kind in {"group_member", "group_shared"} else "",
            assurance=assurance,
            profile_status="active",
            policy_version=policy_version,
            migration_epoch=migration_epoch,
        )
        decision = AssurancePolicy.authorize(context, purpose)
        return {
            "ok": decision.allowed,
            "code": "namespace_resolved" if decision.allowed else decision.code,
            "identity_key": identity_key,
            "person_id": clean_person,
            "context": context.to_dict(),
            "decision": decision.code,
        }

    def matches_person_subject(self, person_id: str, subject_id: str) -> bool:
        """Check an already-bound legacy row against exact active link subjects."""
        try:
            clean_person = _text(person_id, "person_id")
            subject = _text(subject_id, "subject_id", 160)
        except ValueError:
            return False
        with _LOCK:
            root = _root(self._store)
            for candidate in root["identity_links"].values():
                if (
                    not isinstance(candidate, dict)
                    or candidate.get("status") != "active"
                    or candidate.get("person_id") != clean_person
                ):
                    continue
                try:
                    identity = _identity(candidate.get("identity"))
                    if build_identity_key(identity) != candidate.get("identity_key"):
                        continue
                except (TypeError, ValueError):
                    continue
                platform_subject = identity["platform_subject_id"]
                if subject == platform_subject:
                    return True
                parts = subject.rsplit(":", 2)
                if (
                    len(parts) == 3
                    and len(parts[2]) == 16
                    and all(char in "0123456789abcdef" for char in parts[2].lower())
                    and parts[0].lower() == identity["subject_namespace"].split(":", 1)[0]
                    and parts[1] == platform_subject
                ):
                    return True
        return False

    def identity_for_person_subject(
        self, person_id: str, subject_id: str
    ) -> dict[str, str] | None:
        """Resolve one exact active identity for a trusted internal operation.

        The returned identity contains storage-level routing fields and must not
        be serialized to the page.  Page handlers use it only after selecting a
        concrete legacy user row, so unlink operations never accept a partial
        identity assembled by the browser.
        """
        try:
            clean_person = _text(person_id, "person_id")
            subject = _text(subject_id, "subject_id", 160)
        except ValueError:
            return None
        matches: list[dict[str, str]] = []
        with _LOCK:
            root = _root(self._store)
            for candidate in root["identity_links"].values():
                if (
                    not isinstance(candidate, dict)
                    or candidate.get("status") != "active"
                    or candidate.get("person_id") != clean_person
                ):
                    continue
                try:
                    identity = _identity(candidate.get("identity"))
                    if build_identity_key(identity) != candidate.get("identity_key"):
                        continue
                except (TypeError, ValueError):
                    continue
                platform_subject = identity["platform_subject_id"]
                parts = subject.rsplit(":", 2)
                opaque_subject_match = (
                    len(parts) == 3
                    and len(parts[2]) == 16
                    and all(char in "0123456789abcdef" for char in parts[2].lower())
                    and parts[0].lower() == identity["subject_namespace"].split(":", 1)[0]
                    and parts[1] == platform_subject
                )
                if subject == platform_subject or opaque_subject_match:
                    matches.append(identity)
        return deepcopy(matches[0]) if len(matches) == 1 else None

    def detached_identity_for_person_subject(
        self, person_id: str, subject_id: str
    ) -> dict[str, str] | None:
        """Resolve one exact detached identity for a trusted relink operation."""
        try:
            clean_person = _text(person_id, "person_id")
            subject = _text(subject_id, "subject_id", 160)
        except ValueError:
            return None
        matches: list[dict[str, str]] = []
        with _LOCK:
            root = _root(self._store)
            for candidate in root["detached_identity_links"].values():
                if (
                    not isinstance(candidate, dict)
                    or candidate.get("status") != "detached"
                    or candidate.get("person_id") != clean_person
                ):
                    continue
                try:
                    identity = _identity(candidate.get("identity"))
                    if build_identity_key(identity) != candidate.get("identity_key"):
                        continue
                except (TypeError, ValueError):
                    continue
                platform_subject = identity["platform_subject_id"]
                parts = subject.rsplit(":", 2)
                opaque_subject_match = (
                    len(parts) == 3
                    and len(parts[2]) == 16
                    and all(char in "0123456789abcdef" for char in parts[2].lower())
                    and parts[0].lower() == identity["subject_namespace"].split(":", 1)[0]
                    and parts[1] == platform_subject
                )
                if subject == platform_subject or opaque_subject_match:
                    matches.append(identity)
        return deepcopy(matches[0]) if len(matches) == 1 else None

    def safe_admin_person_summary(
        self, person_id: str, subject_id: str = ""
    ) -> dict[str, Any]:
        """Return bounded identity state without raw subjects or identity keys."""
        try:
            clean_person = _text(person_id, "person_id")
            subject = _text(subject_id, "subject_id", 160) if subject_id else ""
        except ValueError:
            return {"linked": False, "code": "identity_reference_invalid"}
        with _LOCK:
            root = _root(self._store)
            projection = build_person_projection(self._store, clean_person)
            profile = root["profiles"].get(clean_person)
            if (
                not isinstance(profile, dict)
                or projection is None
                or validate_projection(projection)
            ):
                return {"linked": False, "code": "identity_projection_invalid"}
            active = [
                link for link in root["identity_links"].values()
                if isinstance(link, dict)
                and link.get("person_id") == clean_person
                and link.get("status") == "active"
            ]
            detached_count = sum(
                1 for link in root["detached_identity_links"].values()
                if isinstance(link, dict) and link.get("person_id") == clean_person
            )
            current_linked = False
            current_detached = False
            if subject:
                current_linked = self.identity_for_person_subject(clean_person, subject) is not None
                current_detached = self.detached_identity_for_person_subject(clean_person, subject) is not None
            return {
                "linked": True,
                "code": "identity_admin_summary",
                "current_identity_linked": current_linked,
                "current_identity_detached": current_detached,
                "identity_assurance": str(projection.get("identity_assurance") or "unverified"),
                "profile_status": str(projection.get("profile_status") or "active"),
                "projection_revision": int(projection.get("projection_revision") or 0),
                "active_identity_count": len(active),
                "detached_identity_count": detached_count,
                "updated_at": str(projection.get("updated_at") or ""),
            }

    def create_or_link(
        self, identity: dict[str, Any], profile: dict[str, Any] | None = None,
        operation_id: str = "", actor_id: str = "companion", **_: Any,
    ) -> dict[str, Any]:
        """Create a person for an explicit operation, or return the existing link."""
        try:
            normalized = _identity(identity)
            op = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not op:
            return {"ok": False, "state": "pending", "code": "explicit_operation_required", "person_id": "", "identity_key": build_identity_key(normalized)}
        safe_profile = _safe(profile or {})
        if not isinstance(safe_profile, dict):
            safe_profile = {}
        display_name = safe_profile.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = "unknown_person"
        aliases = safe_profile.get("aliases")
        aliases = [item for item in aliases if isinstance(item, str) and item] if isinstance(aliases, list) else []
        relation_policy_id = safe_profile.get("relation_policy_id")
        if not isinstance(relation_policy_id, str) or not relation_policy_id:
            relation_policy_id = "default_friend"
        owner_mode = safe_profile.get("owner_mode")
        if owner_mode not in {"owner", "not_owner"}:
            owner_mode = "not_owner"
        key = build_identity_key(normalized)
        person_id = person_id_for_identity(normalized)
        with _LOCK:
            root = _root(self._store)
            identity_tombstone = root["identity_tombstones"].get(key)
            if isinstance(identity_tombstone, dict):
                return {
                    "ok": False, "state": "deleted", "code": "identity_archived",
                    "person_id": str(identity_tombstone.get("person_id") or ""),
                    "identity_key": key, "changed": False,
                }
            detached = root["detached_identity_links"].get(key)
            if isinstance(detached, dict):
                return {
                    "ok": False, "state": "detached", "code": "identity_relink_required",
                    "person_id": str(detached.get("person_id") or ""),
                    "identity_key": key, "changed": False,
                }
            existing = root["identity_links"].get(key)
            if isinstance(existing, dict) and existing.get("person_id"):
                existing_id = str(existing["person_id"])
                projection = build_person_projection(self._store, existing_id)
                state = "resolved" if projection and not validate_projection(projection) else "invalid"
                return {"ok": state == "resolved", "state": state, "code": "already_linked", "person_id": existing_id, "identity_key": key, "projection": projection, "changed": False}
            if person_id in root["profiles"]:
                return {
                    "ok": False,
                    "state": "invalid",
                    "code": "person_record_conflict",
                    "person_id": person_id,
                    "identity_key": key,
                    "changed": False,
                }
            now = _now()
            stored = {
                "person_id": person_id,
                "resolved_identity_key": key,
                "identity_keys": [key],
                "identity_assurance": "observed",
                "profile_status": "active",
                # The contract requires a non-empty display name.  Keep the
                # fallback generic; never derive it from message content.
                "display_name": display_name,
                "preferred_address": (
                    safe_profile.get("preferred_address")
                    if isinstance(safe_profile.get("preferred_address"), str) else ""
                ),
                "style": safe_profile.get("style") if isinstance(safe_profile.get("style"), str) else "",
                "profile_origin": (
                    safe_profile.get("profile_origin")
                    if isinstance(safe_profile.get("profile_origin"), str) else ""
                ),
                "auto_profile_created": bool(safe_profile.get("auto_profile_created", False)),
                "profile_fact_revision": 1,
                "aliases": aliases,
                "relation_policy_id": relation_policy_id,
                "owner_mode": owner_mode,
                "affinity_score": _safe_affinity_score(safe_profile.get("affinity_score")),
                "group_overlay_ref": "",
                "projection_revision": 1,
                "updated_at": now,
            }
            root["profiles"][person_id] = stored
            root["identity_links"][key] = {
                "identity_key": key, "identity": normalized, "person_id": person_id,
                "identity_assurance": "observed", "status": "active",
                "created_at": now, "updated_at": now, "last_operation_id": op,
            }
            projection = build_person_projection(self._store, person_id)
            if projection is None or validate_projection(projection):
                root["identity_links"].pop(key, None)
                root["profiles"].pop(person_id, None)
                return {
                    "ok": False,
                    "state": "invalid",
                    "code": "projection_invalid",
                    "person_id": person_id,
                    "identity_key": key,
                    "changed": False,
                }
            root["binding_checkpoints"][f"{person_id}:{key}"] = {
                "person_id": person_id,
                "identity_key": key,
                "origin_identity_key": key,
                "relationship_score": stored["affinity_score"],
                "created_at": now,
                "operation_id": op,
                "source_event_count": 0,
            }
            root["audit_events"].append({"event_id": op, "action": "create_or_link", "actor_id": actor, "person_id": person_id, "at": now})
            return {"ok": True, "state": "resolved", "code": "created", "person_id": person_id, "identity_key": key, "projection": projection, "changed": True}

    def identity_profile_facts(self, person_id: str) -> dict[str, Any]:
        """Read the bounded person-wide facts that may cross chat namespaces."""
        try:
            clean_person = _text(person_id, "person_id")
        except ValueError:
            return {"ok": False, "code": "identity_reference_invalid", "facts": {}}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict):
                return {"ok": False, "code": "person_not_found", "facts": {}}
            if profile.get("profile_status", "active") != "active":
                return {"ok": False, "code": "person_not_active", "facts": {}}
            facts = {
                key: deepcopy(profile.get(key))
                for key in _PROFILE_FACT_FIELDS
                if key in profile
            }
            return {
                "ok": True,
                "code": "identity_profile_facts",
                "person_id": clean_person,
                "profile_fact_revision": max(1, int(profile.get("profile_fact_revision") or 1)),
                "facts": facts,
            }

    def update_identity_profile_facts(
        self,
        person_id: str,
        changes: dict[str, Any],
        *,
        operation_id: str,
        actor_id: str = "companion",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Update person-wide facts without touching relationship or channel capabilities."""
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "changed": False}
        if not operation or not isinstance(changes, dict) or not changes:
            return {"ok": False, "state": "invalid", "code": "profile_fact_update_invalid", "changed": False}
        if set(changes) - _PROFILE_FACT_FIELDS:
            return {"ok": False, "state": "invalid", "code": "profile_fact_fields_invalid", "changed": False}
        normalized: dict[str, Any] = {}
        for key, value in changes.items():
            if key == "auto_profile_created":
                if type(value) is not bool:
                    return {"ok": False, "state": "invalid", "code": "profile_fact_value_invalid", "changed": False}
                normalized[key] = value
                continue
            if not isinstance(value, str) or _CONTROL_CHARACTER_RE.search(value):
                return {"ok": False, "state": "invalid", "code": "profile_fact_value_invalid", "changed": False}
            limit = 80 if key == "display_name" else 40 if key in {"preferred_address", "style"} else 60
            cleaned = " ".join(value.split())[:limit]
            if key == "display_name" and not cleaned:
                return {"ok": False, "state": "invalid", "code": "profile_fact_value_invalid", "changed": False}
            normalized[key] = cleaned
        if expected_revision is not None and (
            isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1
        ):
            return {"ok": False, "state": "invalid", "code": "profile_fact_revision_invalid", "changed": False}
        operation_key = f"req041.profile_fact:{operation}"
        request_fingerprint = _fingerprint({
            "person_id": clean_person,
            "changes": normalized,
            "actor_id": actor,
            "expected_revision": expected_revision,
        })
        with _LOCK:
            root = _root(self._store)
            prior = root["operations"].get(operation_key)
            if isinstance(prior, dict):
                if prior.get("request_fingerprint") != request_fingerprint:
                    return {
                        "ok": False, "state": "invalid", "code": "operation_id_conflict",
                        "person_id": clean_person, "changed": False,
                    }
                cached = prior.get("result")
                return deepcopy(cached) if isinstance(cached, dict) else {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "person_id": clean_person, "changed": False,
                }
            if operation_key in root["operations"]:
                return {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "person_id": clean_person, "changed": False,
                }
            profile = root["profiles"].get(clean_person)
            projection = build_person_projection(self._store, clean_person)
            if (
                not isinstance(profile, dict)
                or profile.get("profile_status", "active") != "active"
                or projection is None
                or validate_projection(projection)
            ):
                return {
                    "ok": False, "state": "invalid", "code": "person_record_invalid",
                    "person_id": clean_person, "changed": False,
                }
            revision = max(1, int(profile.get("profile_fact_revision") or 1))
            if expected_revision is not None and revision != expected_revision:
                return {
                    "ok": False, "state": "conflict", "code": "profile_fact_revision_conflict",
                    "person_id": clean_person, "profile_fact_revision": revision, "changed": False,
                }
            changed = any(profile.get(key) != value for key, value in normalized.items())
            if changed:
                profile.update(deepcopy(normalized))
                revision += 1
                profile["profile_fact_revision"] = revision
                profile["updated_at"] = _now()
                root["audit_events"].append({
                    "event_id": operation,
                    "action": "update_identity_profile_facts",
                    "actor_id": actor,
                    "person_id": clean_person,
                    "at": profile["updated_at"],
                    "changed_fields": sorted(normalized),
                })
            facts = {
                key: deepcopy(profile.get(key))
                for key in _PROFILE_FACT_FIELDS
                if key in profile
            }
            result = {
                "ok": True,
                "state": "resolved",
                "code": "profile_facts_updated" if changed else "profile_facts_unchanged",
                "person_id": clean_person,
                "identity_key": str(profile.get("resolved_identity_key") or ""),
                "profile_fact_revision": revision,
                "facts": facts,
                "changed": changed,
            }
            root["operations"][operation_key] = {
                "request_fingerprint": request_fingerprint,
                "result": deepcopy(result),
            }
            return result

    def link_identity(self, person_id: str, identity: dict[str, Any], operation_id: str = "", actor_id: str = "companion", **_: Any) -> dict[str, Any]:
        try:
            person_id = _text(person_id, "person_id")
            normalized = _identity(identity)
            op = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not op:
            return {"ok": False, "state": "pending", "code": "explicit_operation_required", "person_id": person_id}
        key = build_identity_key(normalized)
        operation_key = f"req036.link:{op}"
        request_fingerprint = _fingerprint({"person_id": person_id, "identity_key": key, "actor_id": actor})
        with _LOCK:
            root = _root(self._store)
            prior_operation = root["operations"].get(operation_key)
            if isinstance(prior_operation, dict):
                if prior_operation.get("request_fingerprint") != request_fingerprint:
                    return {
                        "ok": False, "state": "invalid", "code": "operation_id_conflict",
                        "operation_id": op, "person_id": person_id, "identity_key": key, "changed": False,
                    }
                cached = prior_operation.get("result")
                return deepcopy(cached) if isinstance(cached, dict) else {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "operation_id": op, "person_id": person_id, "identity_key": key, "changed": False,
                }
            if operation_key in root["operations"]:
                return {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "operation_id": op, "person_id": person_id, "identity_key": key, "changed": False,
                }
            identity_tombstone = root["identity_tombstones"].get(key)
            if isinstance(identity_tombstone, dict):
                return {
                    "ok": False, "state": "deleted", "code": "identity_archived",
                    "person_id": person_id, "identity_key": key, "changed": False,
                }
            profile = root["profiles"].get(person_id)
            if not isinstance(profile, dict):
                return {"ok": False, "state": "pending", "code": "person_not_found", "person_id": person_id}
            if profile.get("profile_status", "active") != "active":
                return {
                    "ok": False, "state": "pending", "code": "person_not_active",
                    "person_id": person_id, "identity_key": key, "changed": False,
                }
            try:
                current_projection = build_person_projection(self._store, person_id)
            except (TypeError, ValueError, OverflowError):
                current_projection = None
            identity_keys = profile.get("identity_keys")
            if (
                current_projection is None
                or validate_projection(current_projection)
                or not isinstance(identity_keys, list)
                or any(not isinstance(item, str) for item in identity_keys)
            ):
                return {
                    "ok": False,
                    "state": "invalid",
                    "code": "person_record_invalid",
                    "person_id": person_id,
                    "identity_key": key,
                    "changed": False,
                }
            prior = root["identity_links"].get(key)
            if isinstance(prior, dict) and prior.get("person_id") != person_id:
                return {"ok": False, "state": "invalid", "code": "identity_conflict", "person_id": person_id}
            if isinstance(prior, dict) and prior.get("person_id") == person_id and prior.get("status") == "active":
                projection = build_person_projection(self._store, person_id)
                result = {
                    "ok": bool(projection and not validate_projection(projection)),
                    "state": "resolved" if projection and not validate_projection(projection) else "invalid",
                    "code": "already_linked",
                    "person_id": person_id,
                    "identity_key": key,
                    "projection": projection,
                    "changed": False,
                }
                root["operations"][operation_key] = {
                    "request_fingerprint": request_fingerprint, "result": deepcopy(result),
                }
                return result
            detached = root["detached_identity_links"].get(key)
            relinking = isinstance(detached, dict)
            if relinking:
                try:
                    detached_identity = _identity(detached.get("identity"))
                    detached_valid = (
                        detached.get("person_id") == person_id
                        and detached.get("identity_key") == key
                        and detached.get("status") == "detached"
                        and build_identity_key(detached_identity) == key
                    )
                except (TypeError, ValueError):
                    detached_valid = False
                if not detached_valid:
                    return {
                        "ok": False, "state": "invalid", "code": "detached_identity_conflict",
                        "person_id": person_id, "identity_key": key, "changed": False,
                    }
            now = _now()
            root["identity_links"][key] = {
                "identity_key": key, "identity": normalized, "person_id": person_id,
                "identity_assurance": "explicit_linked", "status": "active",
                "created_at": str(detached.get("created_at") or now) if relinking else now,
                "updated_at": now, "last_operation_id": op,
            }
            if relinking:
                root["detached_identity_links"].pop(key, None)
            if key not in identity_keys:
                identity_keys.append(key)
            profile["identity_assurance"] = "explicit_linked"
            profile["projection_revision"] = int(profile.get("projection_revision") or 1) + 1
            profile["updated_at"] = now
            root["binding_checkpoints"][f"{person_id}:{key}"] = {
                "person_id": person_id,
                "identity_key": key,
                "origin_identity_key": str(profile.get("resolved_identity_key") or key),
                "relationship_score": _safe_affinity_score(profile.get("affinity_score")),
                "created_at": now,
                "operation_id": op,
                "source_event_count": 0,
            }
            action = "relink_identity" if relinking else "link_identity"
            root["audit_events"].append({"event_id": op, "action": action, "actor_id": actor, "person_id": person_id, "at": now})
            projection = build_person_projection(self._store, person_id)
            result = {
                "ok": bool(projection and not validate_projection(projection)),
                "state": "resolved" if projection and not validate_projection(projection) else "invalid",
                "code": "identity_relinked" if relinking else "identity_linked",
                "person_id": person_id, "identity_key": key, "projection": projection, "changed": True,
            }
            root["operations"][operation_key] = {
                "request_fingerprint": request_fingerprint, "result": deepcopy(result),
            }
            return result

    def unlink_identity(
        self,
        person_id: str,
        identity: dict[str, Any],
        operation_id: str = "",
        actor_id: str = "companion",
        *,
        dry_run: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        """Detach one explicit identity without inventing a profile split.

        Relationship totals, portrait facts, and suppression markers are never
        copied here.  The checkpoint tells an administrator whether a later
        source-event replay can make the split deterministic.
        """
        try:
            person_id = _text(person_id, "person_id")
            normalized = _identity(identity)
            op = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not op:
            return {"ok": False, "state": "pending", "code": "explicit_operation_required", "person_id": person_id}
        key = build_identity_key(normalized)
        operation_key = f"req036.unlink:{op}"
        request_fingerprint = _fingerprint({
            "person_id": person_id,
            "identity_key": key,
            "actor_id": actor,
        })
        with _LOCK:
            root = _root(self._store)
            prior_operation = root["operations"].get(operation_key)
            if isinstance(prior_operation, dict):
                if "request_fingerprint" in prior_operation or "result" in prior_operation:
                    if prior_operation.get("request_fingerprint") != request_fingerprint:
                        return {
                            "ok": False,
                            "state": "invalid",
                            "code": "operation_id_conflict",
                            "operation_id": op,
                            "person_id": person_id,
                            "identity_key": key,
                            "changed": False,
                        }
                    cached_result = prior_operation.get("result")
                    if not isinstance(cached_result, dict):
                        return {
                            "ok": False,
                            "state": "invalid",
                            "code": "operation_record_corrupt",
                            "operation_id": op,
                            "person_id": person_id,
                            "identity_key": key,
                            "changed": False,
                        }
                    return deepcopy(cached_result)
                # Compatibility with records written before request-bound
                # operation envelopes were introduced.
                if prior_operation.get("person_id") != person_id or prior_operation.get("identity_key") != key:
                    return {
                        "ok": False,
                        "state": "invalid",
                        "code": "operation_id_conflict",
                        "operation_id": op,
                        "person_id": person_id,
                        "identity_key": key,
                        "changed": False,
                    }
                return deepcopy(prior_operation)
            if operation_key in root["operations"]:
                return {
                    "ok": False,
                    "state": "invalid",
                    "code": "operation_record_corrupt",
                    "operation_id": op,
                    "person_id": person_id,
                    "identity_key": key,
                    "changed": False,
                }
            profile = root["profiles"].get(person_id)
            link = root["identity_links"].get(key)
            if not isinstance(profile, dict) or not isinstance(link, dict) or link.get("person_id") != person_id:
                return {"ok": False, "state": "pending", "code": "identity_not_linked", "person_id": person_id, "identity_key": key}
            identity_keys = [item for item in profile.get("identity_keys", []) if isinstance(item, str)]
            checkpoint = root["binding_checkpoints"].get(f"{person_id}:{key}")
            checkpoint = deepcopy(checkpoint) if isinstance(checkpoint, dict) else {}
            replay_count = int(checkpoint.get("source_event_count") or 0)
            ambiguity_count = 0
            if key == profile.get("resolved_identity_key") or len(identity_keys) <= 1:
                ambiguity_count = 1
            result = {
                "ok": ambiguity_count == 0,
                "state": "resolved" if ambiguity_count == 0 else "pending",
                "code": "migration_dry_run" if dry_run and ambiguity_count == 0 else (
                    "split_manual_review_required" if ambiguity_count else "identity_unlinked"
                ),
                "person_id": person_id,
                "identity_key": key,
                "source_event_count": replay_count,
                "replayable_event_count": replay_count,
                "ambiguity_count": ambiguity_count,
                "checkpoint": checkpoint,
                "changed": False,
            }
            if dry_run or ambiguity_count:
                return result
            now = _now()
            root["detached_identity_links"][key] = {
                **deepcopy(link),
                "status": "detached",
                "detached_at": now,
                "detached_by": actor,
                "detach_operation_id": op,
            }
            root["identity_links"].pop(key, None)
            profile["identity_keys"] = [item for item in identity_keys if item != key]
            profile["identity_assurance"] = _person_identity_assurance(root, person_id)
            profile["projection_revision"] = int(profile.get("projection_revision") or 1) + 1
            profile["updated_at"] = now
            root["audit_events"].append({"event_id": op, "action": "unlink_identity", "actor_id": actor, "person_id": person_id, "at": now})
            result.update({"ok": True, "state": "resolved", "code": "identity_unlinked", "changed": True})
            root["operations"][operation_key] = {
                "request_fingerprint": request_fingerprint,
                "result": deepcopy(result),
            }
            return result

    def record_identity_source_event(
        self,
        person_id: str,
        identity_key: str,
        source_scope: str,
        event_fingerprint: str,
        *,
        operation_id: str = "",
    ) -> dict[str, Any]:
        """Record a hash-only source event for a later deterministic split.

        The registry never receives message text.  A bounded fingerprint list
        gives unlink dry-runs a replay count without turning identity storage
        into a second chat archive.
        """
        try:
            person_id = _text(person_id, "person_id")
            identity_key = _text(identity_key, "identity_key", 160)
            source_scope = _text(source_scope or "private", "source_scope", 120)
            event_fingerprint = _text(event_fingerprint, "event_fingerprint", 80)
        except ValueError:
            return {"ok": False, "code": "invalid_request"}
        if re.fullmatch(r"[0-9a-f]{64}", event_fingerprint) is None:
            return {"ok": False, "code": "invalid_request"}
        with _LOCK:
            root = _root(self._store)
            link = root["identity_links"].get(identity_key)
            checkpoint_key = f"{person_id}:{identity_key}"
            checkpoint = root["binding_checkpoints"].get(checkpoint_key)
            if not isinstance(link, dict) or link.get("person_id") != person_id or not isinstance(checkpoint, dict):
                return {"ok": False, "code": "identity_not_linked"}
            seen = checkpoint.get("source_event_fingerprints")
            if not isinstance(seen, list):
                seen = []
                checkpoint["source_event_fingerprints"] = seen
            if event_fingerprint in seen:
                return {
                    "ok": True,
                    "code": "source_event_idempotent_replay",
                    "source_event_count": int(checkpoint.get("source_event_count") or len(seen)),
                }
            seen.append(event_fingerprint)
            del seen[:-512]
            checkpoint["source_event_count"] = len(seen)
            checkpoint["last_source_scope"] = source_scope
            checkpoint["last_source_event_at"] = _now()
            if operation_id:
                checkpoint["last_source_operation_id"] = _text(operation_id, "operation_id", 120)
            return {"ok": True, "code": "source_event_recorded", "source_event_count": len(seen)}

    def _merge_private_memory(self, source: str, target: str) -> int:
        """Union the source person's REQ-041 memory bucket into target.

        Identity merge used to move links but leave ``records[source]``
        untouched, so the target could never answer with facts learned under
        the source identity.  Keep all entries and delete the now-orphan
        source bucket only after the target commit succeeds.
        """
        root = self._store.get("_req041_private_memory")
        if not isinstance(root, dict) or not isinstance(root.get("records"), dict):
            return 0
        if source not in root["records"] or target == source:
            return 0
        try:
            from authoritative_private_memory import (
                AuthoritativePrivateMemoryStore,
                PRIVATE_MEMORY_FIELDS,
            )
        except ImportError:
            from .authoritative_private_memory import (
                AuthoritativePrivateMemoryStore,
                PRIVATE_MEMORY_FIELDS,
            )
        store = AuthoritativePrivateMemoryStore(self._store)
        source_read = store.read(source)
        target_read = store.read(target)
        if source_read.get("record") is None:
            return 0
        source_content = source_read["record"].get("content") or {}
        target_content = (target_read.get("record") or {}).get("content") or {}
        merged = deepcopy(target_content)

        def merge_value(old, new):
            if old in (None, "", [], {}):
                return deepcopy(new)
            if isinstance(old, list) and isinstance(new, list):
                values = list(old)
                for item in new:
                    if item not in values:
                        values.append(deepcopy(item))
                return values[-512:]
            if isinstance(old, dict) and isinstance(new, dict):
                result = deepcopy(old)
                for key, value in new.items():
                    result[key] = merge_value(result.get(key), value)
                return result
            if isinstance(old, str) and isinstance(new, str):
                if not new or new in old:
                    return old
                return (old.rstrip() + "\n" + new.strip())[:8000]
            # Numbers and timestamps: target is the surviving person.
            return deepcopy(old)

        entries = 0
        for field in PRIVATE_MEMORY_FIELDS:
            if field not in source_content:
                continue
            before = merged.get(field)
            merged[field] = merge_value(before, source_content[field])
            if merged[field] != before:
                entries += 1
        revision = (target_read.get("record") or {}).get("revision") or 0
        store.commit(
            target,
            merged,
            expected_revision=revision,
            operation_id=f"merge-person-memory:{source}:{target}",
            fields=PRIVATE_MEMORY_FIELDS,
        )
        root["records"].pop(source, None)
        return entries

    def merge_person(
        self, source_person_id: str, target_person_id: str, *, operation_id: str = "",
        actor_id: str = "companion", **_: Any,
    ) -> dict[str, Any]:
        """Merge one person into another without detaching identity links."""
        try:
            source = _text(source_person_id, "source_person_id")
            target = _text(target_person_id, "target_person_id")
            op = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request"}
        if not op:
            return {"ok": False, "state": "pending", "code": "explicit_operation_required"}
        if source == target:
            return {"ok": False, "state": "invalid", "code": "invalid_request"}
        with _LOCK:
            root = _root(self._store)
            source_profile = root["profiles"].get(source)
            target_profile = root["profiles"].get(target)
            if not isinstance(source_profile, dict) or not isinstance(target_profile, dict):
                return {"ok": False, "state": "pending", "code": "person_not_found"}
            if source_profile.get("profile_status", "active") != "active":
                return {"ok": False, "state": "invalid", "code": "person_not_active"}
            if target_profile.get("profile_status", "active") != "active":
                return {"ok": False, "state": "invalid", "code": "person_not_active"}
            now = _now()
            # Target wins conflicts; source only fills fields the target has
            # not established yet.  This is a union, not a destructive replace.
            for key, value in source_profile.items():
                if key in {"person_id", "resolved_identity_key", "identity_keys", "profile_status",
                           "merged_into", "updated_at", "projection_revision", "profile_fact_revision"}:
                    continue
                if target_profile.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    target_profile[key] = deepcopy(value)
            aliases = set(target_profile.get("aliases") or [])
            aliases.update(source_profile.get("aliases") or [])
            target_profile["aliases"] = sorted(item for item in aliases if isinstance(item, str) and item)
            target_profile["identity_keys"] = list(dict.fromkeys(
                list(target_profile.get("identity_keys") or []) + list(source_profile.get("identity_keys") or [])
            ))
            target_profile["updated_at"] = now
            target_profile["projection_revision"] = int(target_profile.get("projection_revision") or 1) + 1

            moved_links = 0
            for key, link in list(root["identity_links"].items()):
                if isinstance(link, dict) and link.get("person_id") == source:
                    link["person_id"] = target
                    link["updated_at"] = now
                    link["last_operation_id"] = op
                    moved_links += 1
            moved_overlays = 0
            for key, overlay in list(root["group_overlays"].items()):
                if not isinstance(overlay, dict) or overlay.get("person_id") != source:
                    continue
                group_scope = str(overlay.get("group_scope") or "")
                target_key = f"{target}:{_fingerprint(group_scope)[:32]}"
                if target_key not in root["group_overlays"]:
                    overlay["person_id"] = target
                    overlay["updated_at"] = now
                    root["group_overlays"][target_key] = overlay
                    moved_overlays += 1
                root["group_overlays"].pop(key, None)
            source_profile["profile_status"] = "merged"
            source_profile["merged_into"] = target
            source_profile["updated_at"] = now
            try:
                merged_memory_entries = self._merge_private_memory(source, target)
            except Exception:
                # Identity merging stays available even if one legacy memory
                # bucket is malformed; the operator can repair and re-run.
                merged_memory_entries = 0
            root["audit_events"].append({
                "event_id": op, "action": "merge_person", "actor_id": actor,
                "source_person_id": source, "target_person_id": target,
                "moved_identity_links": moved_links, "moved_group_overlays": moved_overlays,
                "merged_memory_entries": merged_memory_entries,
                "at": now,
            })
            projection = build_person_projection(self._store, target)
            if projection is None or validate_projection(projection):
                raise ValueError("person_merge_projection_invalid")
            return {
                "ok": True, "state": "resolved", "code": "merged",
                "source_person_id": source, "target_person_id": target,
                "moved_identity_links": moved_links,
                "moved_group_overlays": moved_overlays,
                "merged_memory_entries": merged_memory_entries,
                "projection": projection,
            }

    def preview_person_merge(self, source_person_id: str, target_person_id: str, operation_id: str = "", **_: Any) -> dict[str, Any]:
        """Expose conflicts without merging two existing people automatically."""
        try:
            source_person_id = _text(source_person_id, "source_person_id")
            target_person_id = _text(target_person_id, "target_person_id")
            operation_id = _operation_id(operation_id)
        except ValueError:
            return {"ok": False, "code": "invalid_request"}
        with _LOCK:
            root = _root(self._store)
            source = root["profiles"].get(source_person_id)
            target = root["profiles"].get(target_person_id)
            if not isinstance(source, dict) or not isinstance(target, dict) or source_person_id == target_person_id:
                return {"ok": False, "code": "invalid_request"}
            conflicts = [
                field for field in ("affinity_score", "owner_mode", "relation_policy_id")
                if source.get(field) != target.get(field)
            ]
            return {
                "ok": False,
                "code": "merge_manual_review_required",
                "operation_id": operation_id,
                "source_person_id": source_person_id,
                "target_person_id": target_person_id,
                "conflicts": conflicts,
                "write_count": 0,
            }

    def prepare_person_archive(
        self,
        person_id: str,
        operation_id: str = "",
        actor_id: str = "companion",
        reason_code: str = "person_archive",
    ) -> dict[str, Any]:
        """Persist a request-bound archive saga without changing identity state."""
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not operation:
            return {
                "ok": False, "state": "pending", "code": "explicit_operation_required",
                "person_id": clean_person,
            }
        operation_key = f"req041.archive:{operation}"
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
        })
        with _LOCK:
            root = _root(self._store)
            prior = root["operations"].get(operation_key)
            if isinstance(prior, dict):
                if prior.get("request_fingerprint") != request_fingerprint:
                    return {
                        "ok": False, "state": "invalid", "code": "operation_id_conflict",
                        "person_id": clean_person, "operation_id": operation,
                    }
                result = prior.get("result")
                if prior.get("stage") == "completed" and isinstance(result, dict):
                    return deepcopy(result)
                preview = prior.get("preview")
                return deepcopy(preview) if isinstance(preview, dict) else {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "person_id": clean_person, "operation_id": operation,
                }
            if operation_key in root["operations"]:
                return {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "person_id": clean_person, "operation_id": operation,
                }
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict):
                return {"ok": False, "state": "pending", "code": "person_not_found", "person_id": clean_person}
            if profile.get("profile_status", "active") != "active":
                return {"ok": False, "state": "pending", "code": "person_not_active", "person_id": clean_person}
            identity_keys = profile.get("identity_keys")
            if not isinstance(identity_keys, list) or any(not isinstance(item, str) for item in identity_keys):
                return {"ok": False, "state": "invalid", "code": "person_record_invalid", "person_id": clean_person}
            active_keys = sorted(
                str(key) for key, link in root["identity_links"].items()
                if isinstance(link, dict) and link.get("person_id") == clean_person and link.get("status") == "active"
            )
            if sorted(identity_keys) != active_keys or not active_keys:
                return {"ok": False, "state": "invalid", "code": "identity_exact_link_invalid", "person_id": clean_person}
            for key in active_keys:
                link = root["identity_links"].get(key)
                try:
                    valid = (
                        isinstance(link, dict)
                        and link.get("identity_key") == key
                        and build_identity_key(_identity(link.get("identity"))) == key
                    )
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    return {"ok": False, "state": "invalid", "code": "identity_exact_link_invalid", "person_id": clean_person}
            projection_revision = max(1, int(profile.get("projection_revision") or 1))
            token = _fingerprint({
                "request_fingerprint": request_fingerprint,
                "projection_revision": projection_revision,
                "active_identity_keys_hash": _fingerprint(active_keys),
            })
            preview = {
                "ok": True, "state": "prepared", "code": "person_archive_prepared",
                "person_id": clean_person, "operation_id": operation,
                "confirmation_token": token,
                "active_identity_count": len(active_keys),
                "detached_identity_count": sum(
                    1 for link in root["detached_identity_links"].values()
                    if isinstance(link, dict) and link.get("person_id") == clean_person
                ),
                "group_overlay_count": sum(
                    1 for overlay in root["group_overlays"].values()
                    if isinstance(overlay, dict) and overlay.get("person_id") == clean_person
                ),
                "projection_revision": projection_revision,
                "changed": False,
            }
            root["operations"][operation_key] = {
                "request_fingerprint": request_fingerprint,
                "stage": "prepared",
                "person_id": clean_person,
                "actor_id": actor,
                "reason_code": reason,
                "confirmation_token": token,
                "prepared_at": _now(),
                "preview": deepcopy(preview),
            }
            return preview

    def finalize_person_archive(
        self,
        person_id: str,
        operation_id: str,
        confirmation_token: str,
        remote_receipt: dict[str, Any],
        relationship_receipt: dict[str, Any],
        stream_receipt: dict[str, Any],
        *,
        actor_id: str = "companion",
        reason_code: str = "person_archive",
    ) -> dict[str, Any]:
        """Finalize identity state only after an atomic Memory receipt exists."""
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            token = _text(confirmation_token, "confirmation_token", 80)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        operation_key = f"req041.archive:{operation}"
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
        })
        if not isinstance(remote_receipt, dict) or not remote_receipt.get("ok"):
            return {
                "ok": False, "state": "prepared", "code": "archive_remote_not_confirmed",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        remote_code = str(remote_receipt.get("code") or "")
        if remote_code not in {"identity_scopes_tombstoned", "identity_scopes_already_empty"}:
            return {
                "ok": False, "state": "prepared", "code": "archive_remote_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        try:
            remote_count = int(remote_receipt.get("count") or 0)
            namespace_count = int(remote_receipt.get("namespace_count") or 0)
        except (TypeError, ValueError, OverflowError):
            return {
                "ok": False, "state": "prepared", "code": "archive_remote_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        if remote_count < 0 or namespace_count < 0:
            return {
                "ok": False, "state": "prepared", "code": "archive_remote_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        if not isinstance(relationship_receipt, dict):
            return {
                "ok": False, "state": "prepared", "code": "archive_relationship_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        relationship_code = str(relationship_receipt.get("code") or "")
        if relationship_code not in {
            "relationship_account_tombstoned", "relationship_account_already_empty",
        }:
            return {
                "ok": False, "state": "prepared", "code": "archive_relationship_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        if (
            not isinstance(stream_receipt, dict)
            or stream_receipt.get("code") != "outbox_streams_retired"
            or int(stream_receipt.get("stream_count") or 0) != 2
        ):
            return {
                "ok": False, "state": "prepared", "code": "archive_stream_receipt_invalid",
                "person_id": clean_person, "operation_id": operation, "changed": False,
            }
        with _LOCK:
            root = _root(self._store)
            saga = root["operations"].get(operation_key)
            if not isinstance(saga, dict) or saga.get("request_fingerprint") != request_fingerprint:
                return {
                    "ok": False, "state": "invalid", "code": "archive_operation_missing",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            if saga.get("confirmation_token") != token:
                return {
                    "ok": False, "state": "invalid", "code": "archive_confirmation_mismatch",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            if saga.get("stage") == "completed" and isinstance(saga.get("result"), dict):
                return deepcopy(saga["result"])
            if saga.get("stage") != "confirmed":
                return {
                    "ok": False, "state": "invalid", "code": "archive_operation_state_invalid",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict) or profile.get("profile_status", "active") != "active":
                return {
                    "ok": False, "state": "invalid", "code": "person_not_active",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            now = _now()
            active_keys = [
                str(key) for key, link in root["identity_links"].items()
                if isinstance(link, dict) and link.get("person_id") == clean_person and link.get("status") == "active"
            ]
            for key in active_keys:
                link = root["identity_links"].get(key)
                try:
                    valid = (
                        isinstance(link, dict)
                        and link.get("identity_key") == key
                        and build_identity_key(_identity(link.get("identity"))) == key
                    )
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    return {
                        "ok": False, "state": "invalid", "code": "identity_exact_link_invalid",
                        "person_id": clean_person, "operation_id": operation, "changed": False,
                    }
            detached_keys = [
                str(key) for key, link in root["detached_identity_links"].items()
                if isinstance(link, dict) and link.get("person_id") == clean_person
            ]
            all_identity_keys = sorted(set(active_keys + detached_keys))
            for key in all_identity_keys:
                prior_tombstone = root["identity_tombstones"].get(key)
                if isinstance(prior_tombstone, dict) and prior_tombstone.get("person_id") != clean_person:
                    return {
                        "ok": False, "state": "invalid", "code": "identity_tombstone_conflict",
                        "person_id": clean_person, "operation_id": operation, "changed": False,
                    }
            for key in active_keys:
                link = deepcopy(root["identity_links"].pop(key))
                root["detached_identity_links"][key] = {
                    **link, "status": "detached", "detached_at": now,
                    "detached_by": actor, "archive_operation_id": operation,
                }
            for key in all_identity_keys:
                root["identity_tombstones"][key] = {
                    "person_id": clean_person, "reason_code": reason,
                    "archive_operation_id": operation, "created_at": now,
                }
            root["person_tombstones"][clean_person] = {
                "reason_code": reason, "archive_operation_id": operation, "created_at": now,
                "identity_key_count": len(all_identity_keys),
            }
            overlays = [
                key for key, overlay in root["group_overlays"].items()
                if isinstance(overlay, dict) and overlay.get("person_id") == clean_person
            ]
            for key in overlays:
                root["group_overlays"].pop(key, None)
            profile["identity_keys"] = []
            profile["identity_assurance"] = "unverified"
            profile["profile_status"] = "deleted"
            profile["projection_revision"] = int(profile.get("projection_revision") or 1) + 1
            profile["updated_at"] = now
            root["audit_events"].append({
                "event_id": operation, "action": "archive_person", "actor_id": actor,
                "person_id": clean_person, "reason_code": reason, "at": now,
            })
            result = {
                "ok": True, "state": "completed", "code": "person_archived",
                "person_id": clean_person, "operation_id": operation,
                "detached_identity_count": len(active_keys),
                "removed_group_overlay_count": len(overlays),
                "scoped_record_count": remote_count,
                "scoped_namespace_count": namespace_count,
                "identity_tombstone_count": len(all_identity_keys),
                "changed": True,
            }
            saga.update({
                "stage": "completed", "completed_at": now,
                "remote_receipt_hash": _fingerprint({
                    "code": remote_code, "count": remote_count, "namespace_count": namespace_count,
                    "relationship_code": relationship_code,
                    "relationship_last_revision": int(relationship_receipt.get("last_revision") or 0),
                    "stream_code": "outbox_streams_retired",
                    "stream_revisions": stream_receipt.get("revisions") or {},
                }),
                "result": deepcopy(result),
            })
            return result

    def confirm_person_archive(
        self,
        person_id: str,
        operation_id: str,
        confirmation_token: str,
        *,
        actor_id: str = "companion",
        reason_code: str = "person_archive",
    ) -> dict[str, Any]:
        """Persist explicit destructive intent so confirmed work can resume."""
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            token = _text(confirmation_token, "confirmation_token", 80)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
        })
        operation_key = f"req041.archive:{operation}"
        with _LOCK:
            root = _root(self._store)
            saga = root["operations"].get(operation_key)
            if not isinstance(saga, dict) or saga.get("request_fingerprint") != request_fingerprint:
                return {
                    "ok": False, "state": "invalid", "code": "archive_operation_missing",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            if saga.get("confirmation_token") != token:
                return {
                    "ok": False, "state": str(saga.get("stage") or "prepared"),
                    "code": "archive_confirmation_mismatch", "person_id": clean_person,
                    "operation_id": operation, "changed": False,
                }
            if saga.get("stage") == "completed" and isinstance(saga.get("result"), dict):
                return deepcopy(saga["result"])
            if saga.get("stage") not in {"prepared", "confirmed"}:
                return {
                    "ok": False, "state": "invalid", "code": "archive_operation_state_invalid",
                    "person_id": clean_person, "operation_id": operation, "changed": False,
                }
            changed = saga.get("stage") != "confirmed"
            saga["stage"] = "confirmed"
            if changed:
                saga["confirmed_at"] = _now()
            return {
                "ok": True, "state": "confirmed", "code": "person_archive_confirmed",
                "person_id": clean_person, "operation_id": operation,
                "confirmation_token": token, "changed": changed,
            }

    def confirmed_person_archives(self, *, limit: int = 32) -> list[dict[str, str]]:
        """Return only resumable confirmed sagas, never preview-only requests."""
        safe_limit = max(1, min(128, int(limit)))
        with _LOCK:
            root = _root(self._store)
            result: list[dict[str, str]] = []
            for key, saga in sorted(root["operations"].items()):
                if not key.startswith("req041.archive:") or not isinstance(saga, dict):
                    continue
                if saga.get("stage") != "confirmed":
                    continue
                operation = key.split(":", 2)[-1]
                values = {
                    "person_id": str(saga.get("person_id") or ""),
                    "operation_id": operation,
                    "confirmation_token": str(saga.get("confirmation_token") or ""),
                    "actor_id": str(saga.get("actor_id") or ""),
                    "reason_code": str(saga.get("reason_code") or ""),
                }
                if all(values.values()):
                    result.append(values)
                if len(result) >= safe_limit:
                    break
            return result

    def prepare_person_purge(
        self,
        person_id: str,
        operation_id: str = "",
        *,
        actor_id: str = "companion",
        reason_code: str = "person_delete",
        retention_seconds: int = PERSON_PURGE_RETENTION_SECONDS,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        """Prepare legacy physical removal after the fixed archive retention."""
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
            retention = int(retention_seconds)
            current = float(now_ts) if now_ts is not None else datetime.now(timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not operation or retention < 0 or retention > 365 * 24 * 60 * 60:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": clean_person}
        operation_key = f"req041.purge:{operation}"
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
            "retention_seconds": retention,
        })
        with _LOCK:
            root = _root(self._store)
            prior = root["operations"].get(operation_key)
            if isinstance(prior, dict):
                if prior.get("request_fingerprint") != request_fingerprint:
                    return {
                        "ok": False, "state": "invalid", "code": "operation_id_conflict",
                        "person_id": clean_person, "operation_id": operation,
                    }
                if prior.get("stage") == "completed" and isinstance(prior.get("result"), dict):
                    return deepcopy(prior["result"])
                preview = prior.get("preview")
                return deepcopy(preview) if isinstance(preview, dict) else {
                    "ok": False, "state": "invalid", "code": "operation_record_corrupt",
                    "person_id": clean_person, "operation_id": operation,
                }
            profile = root["profiles"].get(clean_person)
            tombstone = root["person_tombstones"].get(clean_person)
            if (
                not isinstance(profile, dict) or profile.get("profile_status") != "deleted"
                or not isinstance(tombstone, dict)
            ):
                return {"ok": False, "state": "pending", "code": "person_not_archived", "person_id": clean_person}
            archived_at = _timestamp(tombstone.get("created_at"))
            if archived_at < 0:
                return {"ok": False, "state": "invalid", "code": "archive_tombstone_corrupt", "person_id": clean_person}
            eligible_at = archived_at + retention
            if current < eligible_at:
                return {
                    "ok": False, "state": "retention", "code": "archive_retention_active",
                    "person_id": clean_person, "eligible_at": datetime.fromtimestamp(
                        eligible_at, timezone.utc
                    ).isoformat(timespec="seconds"), "changed": False,
                }
            detached_keys = [
                str(key) for key, link in root["detached_identity_links"].items()
                if isinstance(link, dict) and link.get("person_id") == clean_person
            ]
            if any(
                isinstance(link, dict) and link.get("person_id") == clean_person
                for link in root["identity_links"].values()
            ):
                return {"ok": False, "state": "invalid", "code": "archived_person_has_active_link", "person_id": clean_person}
            token = _fingerprint({
                "request_fingerprint": request_fingerprint,
                "archive_operation_id": tombstone.get("archive_operation_id"),
                "identity_tombstone_count": len(detached_keys),
            })
            preview = {
                "ok": True, "state": "prepared", "code": "person_purge_prepared",
                "person_id": clean_person, "operation_id": operation,
                "confirmation_token": token,
                "detached_identity_count": len(detached_keys),
                "binding_checkpoint_count": sum(
                    1 for checkpoint in root["binding_checkpoints"].values()
                    if isinstance(checkpoint, dict) and checkpoint.get("person_id") == clean_person
                ),
                "changed": False,
            }
            root["operations"][operation_key] = {
                "request_fingerprint": request_fingerprint, "stage": "prepared",
                "person_id": clean_person, "actor_id": actor, "reason_code": reason,
                "retention_seconds": retention, "confirmation_token": token,
                "prepared_at": _now(), "preview": deepcopy(preview),
            }
            return preview

    def confirm_person_purge(
        self,
        person_id: str,
        operation_id: str,
        confirmation_token: str,
        *,
        actor_id: str = "companion",
        reason_code: str = "person_delete",
        retention_seconds: int = PERSON_PURGE_RETENTION_SECONDS,
    ) -> dict[str, Any]:
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            token = _text(confirmation_token, "confirmation_token", 80)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
            retention = int(retention_seconds)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
            "retention_seconds": retention,
        })
        operation_key = f"req041.purge:{operation}"
        with _LOCK:
            root = _root(self._store)
            saga = root["operations"].get(operation_key)
            if not isinstance(saga, dict) or saga.get("request_fingerprint") != request_fingerprint:
                return {"ok": False, "state": "invalid", "code": "purge_operation_missing", "person_id": clean_person}
            if saga.get("confirmation_token") != token:
                return {"ok": False, "state": str(saga.get("stage") or "prepared"), "code": "purge_confirmation_mismatch", "person_id": clean_person}
            if saga.get("stage") == "completed" and isinstance(saga.get("result"), dict):
                return deepcopy(saga["result"])
            if saga.get("stage") not in {"prepared", "confirmed"}:
                return {"ok": False, "state": "invalid", "code": "purge_operation_state_invalid", "person_id": clean_person}
            changed = saga.get("stage") != "confirmed"
            saga["stage"] = "confirmed"
            if changed:
                saga["confirmed_at"] = _now()
            return {
                "ok": True, "state": "confirmed", "code": "person_purge_confirmed",
                "person_id": clean_person, "operation_id": operation,
                "confirmation_token": token, "changed": changed,
            }

    def confirmed_person_purges(self, *, limit: int = 32) -> list[dict[str, str]]:
        safe_limit = max(1, min(128, int(limit)))
        with _LOCK:
            root = _root(self._store)
            result: list[dict[str, str]] = []
            for key, saga in sorted(root["operations"].items()):
                if not key.startswith("req041.purge:") or not isinstance(saga, dict) or saga.get("stage") != "confirmed":
                    continue
                values = {
                    "person_id": str(saga.get("person_id") or ""),
                    "operation_id": key.split(":", 2)[-1],
                    "confirmation_token": str(saga.get("confirmation_token") or ""),
                    "actor_id": str(saga.get("actor_id") or ""),
                    "reason_code": str(saga.get("reason_code") or ""),
                }
                if all(values.values()):
                    result.append(values)
                if len(result) >= safe_limit:
                    break
            return result

    def archived_identity_subjects(self, person_id: str) -> list[str]:
        """Internal purge helper; raw subjects must never be returned by page APIs."""
        try:
            clean_person = _text(person_id, "person_id")
        except ValueError:
            return []
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict) or profile.get("profile_status") != "deleted":
                return []
            subjects: list[str] = []
            for key, link in root["detached_identity_links"].items():
                if not isinstance(link, dict) or link.get("person_id") != clean_person:
                    continue
                try:
                    identity = _identity(link.get("identity"))
                    if build_identity_key(identity) != key or key not in root["identity_tombstones"]:
                        return []
                except (TypeError, ValueError):
                    return []
                subject = identity["platform_subject_id"]
                if subject not in subjects:
                    subjects.append(subject)
            return subjects

    def finalize_person_purge(
        self,
        person_id: str,
        operation_id: str,
        confirmation_token: str,
        outbox_receipt: dict[str, Any],
        *,
        actor_id: str = "companion",
        reason_code: str = "person_delete",
        retention_seconds: int = PERSON_PURGE_RETENTION_SECONDS,
    ) -> dict[str, Any]:
        try:
            clean_person = _text(person_id, "person_id")
            operation = _operation_id(operation_id)
            token = _text(confirmation_token, "confirmation_token", 80)
            actor = _text(actor_id, "actor_id", 120)
            reason = _text(reason_code, "reason_code", 80)
            retention = int(retention_seconds)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": ""}
        if not isinstance(outbox_receipt, dict) or outbox_receipt.get("code") != "outbox_retired_streams_purged":
            return {"ok": False, "state": "confirmed", "code": "purge_outbox_receipt_invalid", "person_id": clean_person}
        request_fingerprint = _fingerprint({
            "person_id": clean_person, "actor_id": actor, "reason_code": reason,
            "retention_seconds": retention,
        })
        operation_key = f"req041.purge:{operation}"
        with _LOCK:
            root = _root(self._store)
            saga = root["operations"].get(operation_key)
            if not isinstance(saga, dict) or saga.get("request_fingerprint") != request_fingerprint:
                return {"ok": False, "state": "invalid", "code": "purge_operation_missing", "person_id": clean_person}
            if saga.get("confirmation_token") != token:
                return {"ok": False, "state": "invalid", "code": "purge_confirmation_mismatch", "person_id": clean_person}
            if saga.get("stage") == "completed" and isinstance(saga.get("result"), dict):
                return deepcopy(saga["result"])
            if saga.get("stage") != "confirmed":
                return {"ok": False, "state": "invalid", "code": "purge_operation_state_invalid", "person_id": clean_person}
            profile = root["profiles"].get(clean_person)
            if not isinstance(profile, dict) or profile.get("profile_status") != "deleted":
                return {"ok": False, "state": "invalid", "code": "person_not_archived", "person_id": clean_person}
            tombstone = root["person_tombstones"].get(clean_person)
            if not isinstance(tombstone, dict):
                return {"ok": False, "state": "invalid", "code": "person_tombstone_missing", "person_id": clean_person}
            detached_keys = [
                str(key) for key, link in root["detached_identity_links"].items()
                if isinstance(link, dict) and link.get("person_id") == clean_person
            ]
            checkpoint_keys = [
                key for key, checkpoint in root["binding_checkpoints"].items()
                if isinstance(checkpoint, dict) and checkpoint.get("person_id") == clean_person
            ]
            root["profiles"].pop(clean_person, None)
            for key in detached_keys:
                root["detached_identity_links"].pop(key, None)
            for key in checkpoint_keys:
                root["binding_checkpoints"].pop(key, None)
            for container_name in ("p4_effect", "p4_live"):
                container = root.get(container_name)
                if isinstance(container, dict) and isinstance(container.get("people"), dict):
                    container["people"].pop(clean_person, None)
            root["audit_events"] = [
                event for event in root["audit_events"]
                if not (isinstance(event, dict) and event.get("person_id") == clean_person)
            ]
            preserved_saga = deepcopy(saga)
            for key, value in list(root["operations"].items()):
                if key != operation_key and _contains_exact_value(value, clean_person):
                    root["operations"].pop(key, None)
            now = _now()
            tombstone.update({"purged_at": now, "purge_operation_id": operation})
            result = {
                "ok": True, "state": "completed", "code": "person_purged",
                "person_id": clean_person, "operation_id": operation,
                "removed_detached_identity_count": len(detached_keys),
                "removed_binding_checkpoint_count": len(checkpoint_keys),
                "changed": True,
            }
            preserved_saga.update({"stage": "completed", "completed_at": now, "result": deepcopy(result)})
            root["operations"][operation_key] = preserved_saga
            root["audit_events"].append({
                "event_id": operation, "action": "purge_person", "actor_id": actor,
                "person_id": clean_person, "reason_code": reason, "at": now,
            })
            return result

    def read_projection(self, person_id: str) -> dict[str, Any] | None:
        with _LOCK:
            projection = build_person_projection(self._store, str(person_id or ""))
            return deepcopy(projection) if projection and not validate_projection(projection) else None

    def identity_link_state(self, person_id: str, identity_key: str) -> dict[str, Any]:
        """Verify one redacted link reference without exposing its raw identity."""
        try:
            clean_person = _text(person_id, "person_id")
            clean_key = _text(identity_key, "identity_key", 160)
        except ValueError:
            return {"ok": False, "code": "identity_reference_invalid"}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(clean_person)
            projection_revision = (
                int(profile.get("projection_revision") or 0) if isinstance(profile, dict) else 0
            )
            for state, container_name in (
                ("active", "identity_links"), ("detached", "detached_identity_links")
            ):
                candidate = root[container_name].get(clean_key)
                if not isinstance(candidate, dict) or candidate.get("person_id") != clean_person:
                    continue
                try:
                    normalized = _identity(candidate.get("identity"))
                    exact = (
                        candidate.get("identity_key") == clean_key
                        and build_identity_key(normalized) == clean_key
                        and candidate.get("status") == state
                    )
                except (TypeError, ValueError):
                    exact = False
                if not exact:
                    return {"ok": False, "code": "identity_link_corrupt"}
                return {
                    "ok": True,
                    "code": "identity_link_verified",
                    "state": state,
                    "identity_assurance": str(candidate.get("identity_assurance") or "observed"),
                    "profile_status": str(profile.get("profile_status") or "active") if isinstance(profile, dict) else "deleted",
                    "projection_revision": projection_revision,
                }
        return {"ok": False, "code": "identity_link_missing"}

    def identity_projection_checkpoint(self, person_id: str) -> dict[str, Any]:
        """Return a hash-only checkpoint for detecting uncaptured identity writes."""
        try:
            clean_person = _text(person_id, "person_id")
        except ValueError:
            return {"ok": False, "code": "identity_reference_invalid"}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(clean_person)
            projection = build_person_projection(self._store, clean_person)
            if not isinstance(profile, dict) or projection is None or validate_projection(projection):
                return {"ok": False, "code": "identity_projection_invalid"}
            profile_keys = profile.get("identity_keys")
            if not isinstance(profile_keys, list) or any(not isinstance(item, str) for item in profile_keys):
                return {"ok": False, "code": "identity_projection_invalid"}
            active_keys = sorted(
                str(key)
                for key, link in root["identity_links"].items()
                if isinstance(link, dict)
                and link.get("person_id") == clean_person
                and link.get("status") == "active"
            )
            if sorted(profile_keys) != active_keys:
                return {"ok": False, "code": "identity_projection_invalid"}
            state = {
                "person_id": clean_person,
                "resolved_identity_key": projection["resolved_identity_key"],
                "identity_assurance": projection["identity_assurance"],
                "profile_status": projection["profile_status"],
                "projection_revision": projection["projection_revision"],
                "active_identity_keys_hash": hashlib.sha256(
                    json.dumps(active_keys, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            }
            return {
                "ok": True,
                "code": "identity_projection_checkpoint",
                "projection_revision": state["projection_revision"],
                "checkpoint_hash": hashlib.sha256(
                    json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            }

    def identity_recovery_state(self, person_id: str) -> dict[str, Any]:
        """Return hash-only active/detached refs for durable gap recovery."""
        checkpoint = self.identity_projection_checkpoint(person_id)
        if not checkpoint.get("ok"):
            return checkpoint
        with _LOCK:
            root = _root(self._store)
            active_keys = sorted(
                str(key)
                for key, link in root["identity_links"].items()
                if isinstance(link, dict)
                and link.get("person_id") == person_id
                and link.get("status") == "active"
            )
            detached_keys: list[str] = []
            for key, link in root["detached_identity_links"].items():
                if not isinstance(link, dict) or link.get("person_id") != person_id:
                    continue
                try:
                    normalized = _identity(link.get("identity"))
                    valid = (
                        link.get("status") == "detached"
                        and link.get("identity_key") == key
                        and build_identity_key(normalized) == key
                    )
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    return {"ok": False, "code": "identity_detached_link_corrupt"}
                detached_keys.append(str(key))
            return {
                **checkpoint,
                "resolved_identity_key": active_keys[0] if active_keys else "",
                "active_identity_keys": active_keys,
                "detached_identity_keys": sorted(detached_keys),
            }

    def read_p4_effect_state(self, person_id: str) -> dict[str, Any]:
        """Read preparation state without creating a ledger or a person."""
        try:
            person_id = _text(person_id, "person_id")
        except ValueError:
            return {"ok": False, "code": "invalid_request", "person_id": ""}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(person_id)
            if not isinstance(profile, dict):
                return {"ok": False, "code": "person_not_found", "person_id": person_id}
            if profile.get("profile_status") != "active":
                return {"ok": False, "code": "person_not_active", "person_id": person_id}
            container = root.get("p4_effect")
            if container is None:
                state = _p4_effect_state([])
                return {
                    "ok": True,
                    "code": "p4_effect_empty",
                    "person_id": person_id,
                    "p4_effect_exists": False,
                    "p4_effect_state": state,
                    "p4_effect_summary": _p4_effect_summary(state),
                    "event_count": 0,
                }
            if _p4_effect_container(root) is None:
                return {"ok": False, "code": "p4_effect_corrupt", "person_id": person_id}
            entry = container["people"].get(person_id)
            if entry is None:
                state = _p4_effect_state([])
                return {
                    "ok": True,
                    "code": "p4_effect_empty",
                    "person_id": person_id,
                    "p4_effect_exists": False,
                    "p4_effect_state": state,
                    "p4_effect_summary": _p4_effect_summary(state),
                    "event_count": 0,
                }
            state, event_index, error = _replay_p4_effect_entry(entry, person_id)
            if error or state is None or event_index is None:
                return {"ok": False, "code": error or "p4_effect_corrupt", "person_id": person_id}
            return {
                "ok": True,
                "code": "p4_effect_read",
                "person_id": person_id,
                "p4_effect_exists": True,
                "p4_effect_state": state,
                "p4_effect_summary": _p4_effect_summary(state),
                "event_count": len(event_index),
            }

    def read_p4_live_state(self, person_id: str) -> dict[str, Any]:
        """Read a separately-owned live state without creating or repairing it."""
        try:
            person_id = _text(person_id, "person_id")
        except ValueError:
            return {"ok": False, "code": "invalid_request", "person_id": ""}
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(person_id)
            if not isinstance(profile, dict) or profile.get("profile_status") != "active":
                return {"ok": False, "code": "person_not_active", "person_id": person_id}
            container = root.get("p4_live")
            if container is None:
                return {"ok": True, "code": "p4_live_state_absent", "person_id": person_id, "state": None}
            if type(container) is not dict or container.get("version") != 1 or type(container.get("people")) is not dict:
                return {"ok": False, "code": "p4_live_state_corrupt", "person_id": person_id}
            state = container["people"].get(person_id)
            if state is None:
                return {"ok": True, "code": "p4_live_state_absent", "person_id": person_id, "state": None}
            if type(state) is not dict:
                return {"ok": False, "code": "p4_live_state_corrupt", "person_id": person_id}
            return {"ok": True, "code": "p4_live_state_read", "person_id": person_id, "state": deepcopy(state)}

    def record_p4_live_state(
        self,
        person_id: str,
        state: dict[str, Any],
        *,
        operation_id: str,
        actor_id: str = "companion",
    ) -> dict[str, Any]:
        """Persist only an exact Companion-owned runtime state with replay safety."""
        try:
            person_id = _text(person_id, "person_id")
            operation_id = _text(operation_id, "operation_id", 120)
            actor_id = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "code": "invalid_request"}
        if actor_id != "companion" or validate_runtime_state(state) == "invalid":
            return {"ok": False, "code": "p4_live_state_rejected", "person_id": person_id, "operation_id": operation_id}
        copied_state = deepcopy(state)
        request_fingerprint = _fingerprint({"person_id": person_id, "state": copied_state, "actor_id": actor_id})
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(person_id)
            if not isinstance(profile, dict) or profile.get("profile_status") != "active":
                return {"ok": False, "code": "person_not_active", "person_id": person_id, "operation_id": operation_id}
            container = root.get("p4_live")
            if container is None:
                container = {"version": 1, "people": {}, "operations": {}}
                root["p4_live"] = container
            if (
                type(container) is not dict
                or container.get("version") != 1
                or type(container.get("people")) is not dict
                or type(container.get("operations")) is not dict
            ):
                return {"ok": False, "code": "p4_live_state_corrupt", "person_id": person_id, "operation_id": operation_id}
            prior = container["operations"].get(operation_id)
            if isinstance(prior, dict):
                if prior.get("request_fingerprint") != request_fingerprint:
                    return {"ok": False, "code": "operation_id_conflict", "person_id": person_id, "operation_id": operation_id}
                result = deepcopy(prior.get("result"))
                if isinstance(result, dict):
                    result["idempotent"] = True
                    return result
                return {"ok": False, "code": "p4_live_state_corrupt", "person_id": person_id, "operation_id": operation_id}
            container["people"][person_id] = copied_state
            result = {"ok": True, "code": "p4_live_state_recorded", "person_id": person_id, "operation_id": operation_id, "changed": True}
            container["operations"][operation_id] = {"request_fingerprint": request_fingerprint, "result": deepcopy(result)}
            root["audit_events"].append({"event_id": operation_id, "action": "p4_live_state_recorded", "actor_id": actor_id, "person_id": person_id, "at": _now()})
            root["audit_events"] = root["audit_events"][-1000:]
            return result

    def record_p4_effect_event(
        self,
        person_id: str,
        event: dict[str, Any],
        *,
        operation_id: str,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """Append a replayable preparation event without enabling a live effect."""
        try:
            person_id = _text(person_id, "person_id")
            operation_id = _text(operation_id, "operation_id", 120)
            actor_id = _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "code": "invalid_request"}
        normalized_event, error = _normalize_p4_effect_event(event)
        if normalized_event is None:
            return {"ok": False, "code": error or "invalid_p4_effect_event", "person_id": person_id, "operation_id": operation_id}
        payload_fingerprint = _fingerprint({"person_id": person_id, "event": normalized_event, "actor_id": actor_id})
        with _LOCK:
            root = _root(self._store)
            profile = root["profiles"].get(person_id)
            if not isinstance(profile, dict):
                return {"ok": False, "code": "person_not_found", "person_id": person_id, "operation_id": operation_id}
            if profile.get("profile_status") != "active":
                return {"ok": False, "code": "person_not_active", "person_id": person_id, "operation_id": operation_id}
            container = _p4_effect_container(root)
            if container is None:
                return {"ok": False, "code": "p4_effect_corrupt", "person_id": person_id, "operation_id": operation_id}
            previous_operation = container["operations"].get(operation_id)
            if isinstance(previous_operation, dict):
                if previous_operation.get("request_fingerprint") != payload_fingerprint:
                    return {"ok": False, "code": "operation_id_conflict", "person_id": person_id, "operation_id": operation_id}
                result = deepcopy(previous_operation.get("result") or {})
                if isinstance(result, dict):
                    result["idempotent"] = True
                    return result
                return {"ok": False, "code": "p4_effect_corrupt", "person_id": person_id, "operation_id": operation_id}

            people = container["people"]
            entry = people.get(person_id)
            if entry is None:
                now = _now()
                entry = {
                    "person_id": person_id,
                    "state": _p4_effect_state([]),
                    "events": [],
                    "created_at": now,
                    "updated_at": now,
                    "last_operation_id": "",
                }
            state, event_index, replay_error = _replay_p4_effect_entry(entry, person_id) if entry else (_p4_effect_state([]), {}, "")
            if replay_error or state is None or event_index is None:
                return {"ok": False, "code": replay_error or "p4_effect_corrupt", "person_id": person_id, "operation_id": operation_id}
            event_id = normalized_event["event_id"]
            fingerprint = _p4_effect_fingerprint(person_id, normalized_event)
            known = event_index.get(event_id)
            if known is not None:
                if known.get("event_fingerprint") != fingerprint:
                    return {"ok": False, "code": "p4_effect_event_id_conflict", "person_id": person_id, "event_id": event_id, "operation_id": operation_id}
                result = {
                    "ok": True,
                    "code": "p4_effect_event_duplicate",
                    "person_id": person_id,
                    "event_id": event_id,
                    "operation_id": operation_id,
                    "event_duplicate": True,
                    "p4_effect_summary": _p4_effect_summary(state),
                    "live_effect_permitted": False,
                }
                container["operations"][operation_id] = {"request_fingerprint": payload_fingerprint, "result": deepcopy(result)}
                return result
            now = _now()
            entry["events"].append({
                "event_id": event_id,
                "person_id": person_id,
                "origin_person_id": person_id,
                "event": deepcopy(normalized_event),
                "event_fingerprint": fingerprint,
                "recorded_at": now,
                "operation_id": operation_id,
            })
            replay_state = _p4_effect_state([item["event"] for item in entry["events"]])
            entry["state"] = replay_state
            entry["updated_at"] = now
            entry["last_operation_id"] = operation_id
            people[person_id] = entry
            root["audit_events"].append({
                "event_id": operation_id,
                "action": "p4_effect_event_recorded",
                "actor_id": actor_id,
                "person_id": person_id,
                "at": now,
                "kind": normalized_event["kind"],
            })
            root["audit_events"] = root["audit_events"][-1000:]
            result = {
                "ok": True,
                "code": "p4_effect_event_recorded",
                "person_id": person_id,
                "event_id": event_id,
                "operation_id": operation_id,
                "changed": True,
                "affected_person_ids": [person_id],
                "p4_effect_summary": _p4_effect_summary(replay_state),
                "live_effect_permitted": False,
            }
            container["operations"][operation_id] = {"request_fingerprint": payload_fingerprint, "result": deepcopy(result)}
            return result

    def guard_p4_effect_person_transition(
        self,
        action: str,
        source_person_id: str,
        target_person_id: str,
        *,
        operation_id: str,
    ) -> dict[str, Any]:
        """Reject unsupported identity merge/split before it can touch the P4 ledger.

        Chat-side Unified Person deliberately has no person-lifecycle merge or
        split operation.  A future caller must implement an explicit replay
        migration rather than silently reassigning preparation entries.
        """
        try:
            action = _text(action, "action", 40)
            source_person_id = _text(source_person_id, "source_person_id")
            target_person_id = _text(target_person_id, "target_person_id")
            operation_id = _text(operation_id, "operation_id", 120)
        except ValueError:
            return {"ok": False, "code": "invalid_request"}
        if action not in {"merge", "split"} or source_person_id == target_person_id:
            return {"ok": False, "code": "p4_effect_transition_rejected", "operation_id": operation_id}
        with _LOCK:
            # Do not call the P4 container helper here: creating or repairing
            # a ledger would itself violate the no-transition guarantee.
            root = _root(self._store)
            source = root["profiles"].get(source_person_id)
            target = root["profiles"].get(target_person_id)
            if not isinstance(source, dict) or not isinstance(target, dict):
                return {"ok": False, "code": "p4_effect_transition_person_not_found", "operation_id": operation_id}
            return {
                "ok": False,
                "code": "p4_effect_transition_unsupported",
                "operation_id": operation_id,
                "action": action,
            }

    def upsert_group_overlay(self, person_id: str, group_scope: str, overlay: dict[str, Any], operation_id: str = "", actor_id: str = "companion", **_: Any) -> dict[str, Any]:
        try:
            person_id, group_scope, op = _text(person_id, "person_id"), _text(group_scope, "group_scope", 240), _operation_id(operation_id)
            _text(actor_id, "actor_id", 120)
        except ValueError:
            return {"ok": False, "state": "invalid", "code": "invalid_request", "person_id": person_id if isinstance(person_id, str) else ""}
        if not op:
            return {"ok": False, "state": "pending", "code": "explicit_operation_required", "person_id": person_id, "group_scope": group_scope}
        safe = _safe(overlay)
        if not isinstance(safe, dict):
            return {"ok": False, "state": "invalid", "code": "overlay_invalid", "person_id": person_id, "group_scope": group_scope}
        with _LOCK:
            root = _root(self._store)
            if not isinstance(root["profiles"].get(person_id), dict):
                return {"ok": False, "state": "pending", "code": "person_not_found", "person_id": person_id, "group_scope": group_scope}
            key = f"{person_id}:{_fingerprint(group_scope)[:32]}"
            previous = root["group_overlays"].get(key)
            revision = int(previous.get("revision") or 0) + 1 if isinstance(previous, dict) else 1
            root["group_overlays"][key] = {"person_id": person_id, "group_scope": group_scope, "overlay": safe, "revision": revision, "updated_at": _now(), "operation_id": op}
            return {"ok": True, "state": "resolved", "code": "group_overlay_upserted", "person_id": person_id, "group_scope": group_scope, "revision": revision, "changed": previous != root["group_overlays"][key]}

    def read_group_overlay(self, person_id: str, group_scope: str) -> dict[str, Any] | None:
        try:
            person_id, group_scope = _text(person_id, "person_id"), _text(group_scope, "group_scope", 240)
        except ValueError:
            return None
        with _LOCK:
            root = _root(self._store)
            key = f"{person_id}:{_fingerprint(group_scope)[:32]}"
            record = root["group_overlays"].get(key)
            if not isinstance(record, dict) or record.get("person_id") != person_id or record.get("group_scope") != group_scope:
                return None
            return deepcopy(record)


__all__ = ["UnifiedPersonRegistry"]
