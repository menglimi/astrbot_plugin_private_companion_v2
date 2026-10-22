"""Read REQ-041 private memory without reviving its jobs or current state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .profile_source import primary_profile


SOURCE_ID = "private.authoritative_memory"
SCHEMA = "req041.person_private_memory.v1"
IDENTITY_FIELDS = ("companion_instance_id", "bot_account_id", "adapter_instance_id",
                   "subject_namespace", "platform_subject_id")
HISTORY_FIELDS = frozenset(("companion_memory", "dialogue_episodes", "open_loops",
    "behavior_habits", "action_preferences", "action_consequences", "state_continuity",
    "recent_reply_topics", "intent_profile", "birthday_profile"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def moment(value):
    try:
        if type(value) in (int, float):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return ""


def _materials(person_id, record):
    result = []
    for field, value in record["content"].items():
        if field not in HISTORY_FIELDS or value in (None, "", {}, []):
            continue
        if field == "companion_memory" and isinstance(value, dict):
            entries = [("items", item) for item in value.get("items", ())]
            entries.extend((key, item) for key, item in value.items()
                           if key not in ("items", "updated_at", "profile_updated_at"))
        elif field == "behavior_habits" and isinstance(value, dict):
            entries = [("patterns", item) for item in value.get("patterns", ())]
        else:
            entries = [(field, item) for item in value] if isinstance(value, list) else [(field, value)]
        for index, (part, item) in enumerate(entries):
            if item in (None, "", {}, []):
                continue
            attributes = item if isinstance(item, dict) else {}
            occurred = next((date for key in ("created_ts", "created_at", "date", "ts", "updated_at", "last_seen_ts")
                             if (date := moment(attributes.get(key)))), moment(record.get("updated_at")))
            text = item if isinstance(item, str) else canonical(item)
            # Preserve every character; oversized historical documents are paged, not truncated.
            for offset in range(0, len(text), 24000):
                result.append({"key": [person_id, field, part, index, offset],
                    "kind": "timeline" if field in ("dialogue_episodes", "action_consequences", "recent_reply_topics") else "memories",
                    "occurred_at": occurred, "text": text[offset:offset + 24000],
                    "attributes": {"source_id": SOURCE_ID, "source_person_id": person_id,
                        "source_field": field, "source_revision": record["revision"],
                        "historical_only": True, "execution_restored": False}})
    return result


@dataclass(frozen=True)
class PrivateMemoryPlan:
    source_fingerprint: str
    lineage_id: str
    records: tuple[dict, ...]
    rejected: tuple[dict, ...]
    source_error: str = ""

    def document(self):
        return {"source_id": SOURCE_ID, "state": "unavailable" if self.source_error else "ready",
            "reason": self.source_error, "fingerprint": self.source_fingerprint,
            "record_count": len(self.records), "material_count": sum(len(r["materials"]) for r in self.records),
            "records": [{k: r[k] for k in ("person_id", "revision", "identities")} |
                        {"material_count": len(r["materials"])} for r in self.records],
            "rejected": list(self.rejected), "historical_only": True, "execution_restored": False}

    def matching(self, *, account_id, native_actor_id):
        return tuple(r for r in self.records if any(
            i["bot_account_id"].split(":", 1)[-1] == account_id
            and i["platform_subject_id"] == native_actor_id
            and i["subject_namespace"] == "aiocqhttp:user"
            for i in r["identities"]))


def build_private_memory_plan(root: Path, configuration=None):
    source = primary_profile(Path(root), configuration)
    lineage = fingerprint([SOURCE_ID, str(source.path.resolve()) if source.path else str(Path(root).resolve())])
    if source.payload is None:
        return PrivateMemoryPlan("", lineage, (), (), source.error)
    payload = source.payload
    store = payload.get("_req041_private_memory", {"schema": SCHEMA, "records": {}})
    registry = payload.get("unified_person", {})
    if (not isinstance(store, dict) or store.get("schema") != SCHEMA
            or not isinstance(store.get("records"), dict) or not isinstance(registry, dict)):
        return PrivateMemoryPlan("", lineage, (), (), "private_memory_store_invalid")
    records, rejected = [], []
    profiles, links = registry.get("profiles", {}), registry.get("identity_links", {})
    for person_id, record in store["records"].items():
        reason, identities = "", []
        profile = profiles.get(person_id, {}) if isinstance(profiles, dict) else {}
        try:
            if (not isinstance(record, dict) or record.get("schema") != SCHEMA
                    or type(record.get("revision")) is not int or record["revision"] < 1
                    or not isinstance(record.get("content"), dict)
                    or record.get("content_hash") != fingerprint(record["content"])):
                raise ValueError("private_memory_record_invalid")
            if (not isinstance(profile, dict) or profile.get("profile_status") != "active"
                    or person_id in registry.get("person_tombstones", {})):
                raise ValueError("private_memory_person_inactive")
            for key in profile.get("identity_keys", ()):
                link = links.get(key, {}) if isinstance(links, dict) else {}
                identity = link.get("identity", {}) if isinstance(link, dict) else {}
                if (not isinstance(identity, dict) or set(identity) != set(IDENTITY_FIELDS)
                        or any(not isinstance(identity[k], str) or not identity[k] for k in IDENTITY_FIELDS)
                        or link.get("status") != "active" or link.get("person_id") != person_id
                        or key in registry.get("identity_tombstones", {})):
                    continue
                if key == "chat-origin-v1:" + fingerprint(identity):
                    identities.append(identity)
            if not identities:
                raise ValueError("private_memory_identity_unresolved")
            records.append({"person_id": person_id, "revision": record["revision"],
                "identities": identities, "materials": _materials(person_id, record)})
        except (ValueError, TypeError, OverflowError):
            reason = "private_memory_record_or_identity_invalid"
        if reason:
            rejected.append({"person_id": person_id, "reason": reason})
    return PrivateMemoryPlan(fingerprint([store, registry.get("profiles", {}), links,
        registry.get("person_tombstones", {}), registry.get("identity_tombstones", {})]),
        lineage, tuple(records), tuple(rejected))
