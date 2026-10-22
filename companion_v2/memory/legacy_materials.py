"""Governed, read-only projections of the V1 memory companion snapshot.

Imported rows remain historical material. They are never converted to V2
sources, accepted facts, or executable work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
from threading import RLock

from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.legacy.sqlite_snapshot import open_readonly_sqlite_snapshot
from companion_v2.storage.sqlite_path import readonly_uri
from .legacy_policy import evaluate_legacy_memory_access


PROFILE = "memory.legacy-materials.v1"
DATABASE_FILENAME = "legacy-memory-materials.sqlite3"
MAX_MATERIAL_CHARS = 64000
MAX_QUERY_CHARS = 2000
MAX_OWNER_BINDINGS = 128
_REPARSE_POINT = 0x400
_DB_LOCK = RLock()
_ALLOWED_REVIEW = frozenset(("", "auto", "approved", "accepted"))
_ALLOWED_VISIBILITY = frozenset(("private_pair", "shareable"))
_ALLOWED_GROUP_VISIBILITY = frozenset(("group_public", "shareable"))
_ALLOWED_CAPTURE_STATES = frozenset(("current", "active"))
_ALLOWED_QUEUE_STATES = frozenset(("", "approved", "accepted", "auto", "completed"))
_UNSCOPED_BOT_ID = "legacy-unscoped"
_UNSCOPED_PERSONA_ID = "legacy"


def _bounded(value, name, maximum=512, *, empty=True):
    if type(value) is not str or len(value) > maximum or (not empty and not value.strip()) or "\x00" in value:
        raise ValueError(f"{name}_invalid")
    return value


@dataclass(frozen=True)
class LegacyOwnerSelector:
    """Exact V1 ownership dimensions; empty values match only empty source values."""

    bot_id: str
    platform: str
    persona_id: str
    scope: str
    session_id: str
    actor_id: str
    group_id: str = ""

    def __post_init__(self):
        for name in ("bot_id", "platform", "persona_id", "session_id", "actor_id", "group_id"):
            _bounded(getattr(self, name), "source_" + name, 512)
        if self.scope not in ("private", "group"):
            raise ValueError("source_scope_invalid")
        if not self.bot_id or not self.platform or not self.persona_id:
            raise ValueError("source_identity_incomplete")
        if self.scope == "private" and (not self.session_id or not self.actor_id or self.group_id):
            raise ValueError("private_source_identity_required")
        if self.scope == "group" and (not self.group_id or not self.session_id or self.actor_id != self.group_id):
            raise ValueError("group_source_identity_required")

    def key(self):
        return (self.bot_id, self.platform, self.persona_id, self.scope, self.session_id,
                self.actor_id, self.group_id)

    def document(self):
        return {"bot_id": self.bot_id, "platform": self.platform, "persona_id": self.persona_id,
                "scope": self.scope, "session_id": self.session_id,
                "actor_id": self.actor_id, "group_id": self.group_id}


@dataclass(frozen=True)
class LegacyMemoryBinding:
    """An explicit old owner to an exact V2 identity/account/scope mapping."""

    source: LegacyOwnerSelector
    target_installation_id: str
    target_bot_id: str
    target_role_id: str
    target_actor_id: str
    target_platform: str
    target_account_id: str
    target_scope_kind: str = "private"
    target_native_scope_id: str = ""

    def __post_init__(self):
        if not isinstance(self.source, LegacyOwnerSelector):
            raise ValueError("source_selector_required")
        if self.target_scope_kind not in ("private", "group"):
            raise ValueError("legacy_memory_target_scope_invalid")
        for name in ("target_installation_id", "target_bot_id", "target_role_id",
                     "target_platform", "target_account_id"):
            _bounded(getattr(self, name), name, 512, empty=False)
        _bounded(self.target_actor_id, "target_actor_id", 512,
                 empty=self.target_scope_kind == "group")
        _bounded(self.target_native_scope_id, "target_native_scope_id", 512)
        if self.target_scope_kind == "group" and (
                self.source.scope != "group" or not self.target_native_scope_id
                or self.target_actor_id):
            raise ValueError("legacy_memory_group_target_invalid")
        if self.target_scope_kind == "private" and (
                self.source.scope != "private" or not self.target_actor_id):
            raise ValueError("legacy_memory_private_target_invalid")

    def target_document(self):
        return {"installation_id": self.target_installation_id, "bot_id": self.target_bot_id,
                "role_id": self.target_role_id, "actor_id": self.target_actor_id,
                "platform": self.target_platform, "account_id": self.target_account_id,
                "scope_kind": self.target_scope_kind,
                "native_scope_id": self.target_native_scope_id}


def _binding(value):
    if isinstance(value, LegacyMemoryBinding):
        return value
    if type(value) is not dict or set(value) != {"source", "target"}:
        raise ValueError("legacy_memory_binding_invalid")
    source, target = value["source"], value["target"]
    if type(source) is not dict or set(source) != {
            "bot_id", "platform", "persona_id", "scope", "session_id", "actor_id", "group_id"}:
        raise ValueError("legacy_memory_source_selector_invalid")
    old_target_fields = {"installation_id", "bot_id", "role_id", "actor_id", "platform", "account_id"}
    target_fields = old_target_fields | {"scope_kind", "native_scope_id"}
    if type(target) is not dict or set(target) not in (old_target_fields, target_fields):
        raise ValueError("legacy_memory_target_selector_invalid")
    target = {"scope_kind": "private", "native_scope_id": "", **target}
    return LegacyMemoryBinding(LegacyOwnerSelector(**source),
                              target_installation_id=target["installation_id"],
                              target_bot_id=target["bot_id"], target_role_id=target["role_id"],
                              target_actor_id=target["actor_id"], target_platform=target["platform"],
                              target_account_id=target["account_id"],
                              target_scope_kind=target["scope_kind"],
                              target_native_scope_id=target["native_scope_id"])


def _selected_owner_ids(values):
    if not isinstance(values, (tuple, list)) or len(values) > MAX_OWNER_BINDINGS:
        raise ValueError("legacy_memory_owner_selection_invalid")
    if any(type(value) is not str or len(value) != 64
           or any(char not in "0123456789abcdef" for char in value) for value in values):
        raise ValueError("legacy_memory_owner_selection_invalid")
    if len(set(values)) != len(values):
        raise ValueError("legacy_memory_owner_selection_duplicate")
    return tuple(sorted(values))


def _target_document(value):
    required = {"installation_id", "bot_id", "role_id", "actor_id", "platform", "account_id",
                "scope_kind", "native_scope_id"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("legacy_memory_target_selector_invalid")
    for name in required - {"actor_id", "native_scope_id"}:
        _bounded(value[name], "target_" + name, 512, empty=False)
    for name in ("actor_id", "native_scope_id"):
        _bounded(value[name], "target_" + name, 512)
    if value["scope_kind"] not in ("private", "group"):
        raise ValueError("legacy_memory_target_scope_invalid")
    if value["scope_kind"] == "private" and not value["actor_id"]:
        raise ValueError("legacy_memory_private_target_invalid")
    if value["scope_kind"] == "group" and (value["actor_id"] or not value["native_scope_id"]):
        raise ValueError("legacy_memory_group_target_invalid")
    return value


def _lineage_id(value):
    if type(value) is not str or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("legacy_memory_lineage_invalid")
    return value


def _safe_database(path: str | Path):
    candidate = Path(path).expanduser()
    info = candidate.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or int(getattr(info, "st_file_attributes", 0)) & _REPARSE_POINT):
        raise ValueError("legacy_memory_snapshot_unsafe")
    return candidate.resolve(strict=True)


def _readonly(path: Path):
    connection = open_readonly_sqlite_snapshot(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _snapshot_hash(path: Path):
    digest_value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_value.update(chunk)
    return digest_value.hexdigest()


def _columns(connection, table):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
        return frozenset()
    return frozenset(row[1] for row in connection.execute(f'PRAGMA table_info("{table}")'))


def _validate_schema(connection):
    required = {
        "memories": {"id", "memory_type", "scope", "session_id", "platform", "owner_bot_id",
                     "subject_kind", "subject_id", "object_kind", "object_id", "visibility",
                     "sayability", "reality_level", "lifecycle", "content", "review_status",
                     "validity_status", "sensitivity", "metadata", "occurred_at", "created_at"},
        "timeline": {"id", "event_type", "scope", "session_id", "subject_id", "object_id",
                     "content", "metadata", "message_id", "occurred_at", "created_at"},
    }
    if any(columns - _columns(connection, table) for table, columns in required.items()):
        raise ValueError("legacy_memory_schema_unsupported")


def _rows(connection, table):
    if not _columns(connection, table):
        return ()
    return connection.execute(f'SELECT * FROM "{table}"')


def _json_dict(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return None
    return result if type(result) is dict else None


def _text(row, key):
    value = row[key] if key in row.keys() else ""
    return value if isinstance(value, str) else ""


def _owner(row, *, table):
    metadata = _json_dict(_text(row, "metadata"))
    if metadata is None:
        return None
    session_id = _text(row, "session_id")
    if not session_id:
        return None

    session_scope, session_target = _session_scope_target(session_id)
    scope = _text(row, "scope")
    if scope in ("", "unknown"):
        scope = session_scope
    elif scope not in ("private", "group") or session_scope and session_scope != scope:
        return None
    if scope not in ("private", "group"):
        return None

    platform, platform_conflict = _single_identity((
        _text(row, "platform"), metadata.get("platform")))
    if platform_conflict:
        return None
    if not platform and ":" in session_id:
        platform = session_id.split(":", 1)[0]

    bot_values = [_text(row, "owner_bot_id"), metadata.get("owner_bot_id"), metadata.get("bot_id")]
    if table == "memories":
        for kind, field in ((_text(row, "subject_kind").lower(), "subject_id"),
                            (_text(row, "object_kind").lower(), "object_id")):
            if kind in {"bot", "assistant"}:
                bot_values.append(_text(row, field))
    elif table == "timeline" and scope == "private" and _text(row, "event_type") == "user_message":
        object_id = _text(row, "object_id")
        if object_id and object_id != _text(row, "subject_id"):
            bot_values.append(object_id)
    elif _text(row, "event_type") == "bot_response":
        bot_values.append(_text(row, "subject_id"))
    bot_values = [value for value in bot_values if value not in ("", "self")]
    bot_id, bot_conflict = _single_identity(bot_values)
    if bot_conflict:
        return None
    bot_id = bot_id or _UNSCOPED_BOT_ID

    persona_values = [metadata.get("persona_id")]
    nested = metadata.get("livingmemory_metadata")
    if isinstance(nested, dict):
        persona_values.append(nested.get("persona_id"))
    persona_values = [value for value in persona_values if value not in (None, "")]
    persona_id, persona_conflict = _single_identity(persona_values)
    if persona_conflict:
        return None
    persona_id = persona_id or _UNSCOPED_PERSONA_ID

    if scope == "private":
        if table == "timeline":
            if _text(row, "event_type") == "user_message":
                actor_field = "subject_id"
            else:
                actor_field = "object_id"
            actor_values = (_text(row, actor_field), metadata.get("participant_user_id"))
        else:
            actor_values = tuple(
                _text(row, field)
                for kind, field in ((_text(row, "subject_kind").lower(), "subject_id"),
                                    (_text(row, "object_kind").lower(), "object_id"))
                if kind in {"user", "human"}
            ) + (metadata.get("participant_user_id"),)
        actor_id, actor_conflict = _single_identity(actor_values)
        if actor_conflict or (session_target and session_scope == "private"
                              and actor_id and actor_id != session_target):
            return None
        actor_id = session_target if session_scope == "private" else actor_id
        group_id = ""
        if not actor_id:
            return None
    else:
        group_values = [_text(row, "group_id"), metadata.get("group_id"), metadata.get("source_group_id")]
        if table == "memories":
            for kind, field in ((_text(row, "subject_kind").lower(), "subject_id"),
                                (_text(row, "object_kind").lower(), "object_id")):
                if kind == "group":
                    group_values.append(_text(row, field))
        group_id, group_conflict = _single_identity(group_values)
        if group_conflict or (session_target and session_scope == "group"
                              and group_id and group_id != session_target):
            return None
        group_id = session_target if session_scope == "group" else group_id
        if not group_id:
            return None
        actor_id = group_id

    if not platform:
        return None
    try:
        return LegacyOwnerSelector(bot_id, platform, persona_id, scope, session_id, actor_id, group_id)
    except ValueError:
        return None


def _single_identity(values):
    found = set()
    for value in values:
        if value in (None, ""):
            continue
        if (type(value) is not str or len(value) > 512 or "\x00" in value
                or not value.strip()):
            return "", True
        found.add(value)
    if len(found) > 1:
        return "", True
    return (next(iter(found)), False) if found else ("", False)


def _session_scope_target(session_id):
    normalized = session_id.lower()
    for marker, scope in ((":groupmessage:", "group"), (":friendmessage:", "private"),
                          (":privatemessage:", "private")):
        index = normalized.rfind(marker)
        if index >= 0:
            target = session_id[index + len(marker):]
            return (scope, target) if target else ("", "")
    for marker, scope in ((":group:", "group"), (":friend:", "private"), (":private:", "private")):
        if marker in normalized:
            target = session_id.rsplit(":", 1)[-1]
            return (scope, target) if target else ("", "")
    return "", ""


def _utc(value):
    if not value:
        return ""
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            return ""
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (AttributeError, TypeError, ValueError):
        return ""


def _references(value):
    found = set()
    if isinstance(value, dict):
        for item in value.values():
            found.update(_references(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_references(item))
    elif isinstance(value, str):
        text_value = value.strip()
        if text_value.startswith("timeline:"):
            text_value = text_value[len("timeline:"):]
        if text_value.startswith("tl_") and len(text_value) <= 512:
            found.add(text_value)
    return found


def _owner_id(selector):
    return digest([PROFILE, selector.document()])


def _capture_body(connection, source_key, manifest_value):
    manifest = _json_dict(manifest_value)
    if not manifest or type(manifest.get("chunks")) is not list:
        return None
    chunks = connection.execute("SELECT * FROM capture_chunks WHERE source_key=? ORDER BY seq", (source_key,)).fetchall()
    listed = manifest["chunks"]
    if len(chunks) != len(listed):
        return None
    bodies, char_offset, byte_offset = [], 0, 0
    for sequence, (chunk, declaration) in enumerate(zip(chunks, listed)):
        body = chunk["body"]
        blob = body.encode("utf-8") if isinstance(body, str) else b""
        actual = hashlib.sha256(blob).hexdigest()
        if (chunk["seq"] != sequence or chunk["char_offset"] != char_offset
                or chunk["byte_offset"] != byte_offset or not body
                or chunk["digest"] != actual or type(declaration) is not dict
                or declaration.get("seq") != sequence or declaration.get("char_offset") != char_offset
                or declaration.get("byte_offset") != byte_offset or declaration.get("digest") != actual
                or declaration.get("chars") != len(body) or declaration.get("bytes") != len(blob)):
            return None
        bodies.append(body)
        char_offset += len(body)
        byte_offset += len(blob)
    body = "".join(bodies)
    if (manifest.get("chars") != len(body) or manifest.get("bytes") != len(body.encode("utf-8"))
            or manifest.get("body_digest") != hashlib.sha256(body.encode("utf-8")).hexdigest()):
        return None
    return body


def _governance(connection):
    tombstone_ids, tombstone_messages, withdrawals = set(), set(), set()
    for row in _rows(connection, "message_source_tombstones"):
        source_id = _text(row, "source_id")
        message_id = _text(row, "message_id")
        if source_id:
            tombstone_ids.add(source_id)
        if message_id:
            tombstone_messages.add(message_id)
    for row in _rows(connection, "life_message_withdrawals"):
        source_id = _text(row, "source_id")
        if source_id:
            withdrawals.add(source_id)

    suppressed_keys = {_text(row, "source_key") for row in _rows(connection, "capture_suppression")
                       if _text(row, "source_key")}
    captures, captures_by_key = {}, {}
    for row in _rows(connection, "capture_sources"):
        timeline_id = _text(row, "timeline_id")
        if timeline_id:
            captures[timeline_id] = {key: row[key] for key in row.keys()}
            source_key = _text(row, "source_key")
            if source_key:
                captures_by_key[source_key] = captures[timeline_id]

    policies = [{field: row[field] for field in row.keys()}
                for row in _rows(connection, "memory_acl_policies")]

    reviews = {}
    for row in _rows(connection, "review_queue"):
        memory_id = _text(row, "memory_id")
        if memory_id:
            reviews.setdefault(memory_id, []).append(_text(row, "status").lower())

    portrait = set()
    for row in _rows(connection, "portrait_suppressions"):
        if _text(row, "status").lower() in ("active", "reconfirmation_pending"):
            portrait.add((_text(row, "person_id"), _text(row, "dimension"),
                          _text(row, "normalized_claim_hash"), _text(row, "scope")))
    return {"tombstone_ids": tombstone_ids, "tombstone_messages": tombstone_messages,
            "withdrawals": withdrawals, "suppressed_keys": suppressed_keys, "captures": captures,
            "captures_by_key": captures_by_key,
            "policies": policies, "reviews": reviews, "portrait": portrait,
            "capture_chunks_available": bool(_columns(connection, "capture_chunks"))}


def _policy_reason(selector, governance):
    window_id = selector.group_id if selector.scope == "group" else selector.actor_id
    window = (selector.scope, window_id)
    decision = evaluate_legacy_memory_access(
        window, window, policies=governance["policies"], rules=(),
        known_readers=(window,))
    if not decision.readable:
        return "legacy_policy_" + decision.reason_code
    return ""


def _memory_reason(row, selector, governance):
    if not selector.session_id:
        return "session_identity_missing"
    policy_reason = _policy_reason(selector, governance)
    if policy_reason:
        return policy_reason
    metadata = _json_dict(_text(row, "metadata"))
    if metadata is None:
        return "metadata_invalid"
    if _text(row, "validity_status").lower() not in ("", "active"):
        return "memory_inactive"
    if _text(row, "review_status").lower() not in _ALLOWED_REVIEW:
        return "memory_unreviewed"
    if _text(row, "lifecycle").lower() in {"archived", "deleted", "rejected", "superseded"}:
        return "memory_inactive"
    allowed_visibility = (_ALLOWED_GROUP_VISIBILITY if selector.scope == "group"
                          else _ALLOWED_VISIBILITY)
    if _text(row, "visibility").lower() not in allowed_visibility:
        return "visibility_unavailable"
    if _text(row, "sensitivity").lower() in {"restricted", "public"}:
        return "sensitivity_unavailable"
    if any(status not in _ALLOWED_QUEUE_STATES for status in governance["reviews"].get(_text(row, "id"), ())):
        return "review_queue_not_approved"
    message_id = _text(row, "message_id")
    if message_id and message_id in governance["tombstone_messages"]:
        return "source_withdrawn"
    source_id = _text(row, "id")
    if source_id and source_id in governance["tombstone_ids"] | governance["withdrawals"]:
        return "source_withdrawn"
    refs = _references(metadata) | _references(_text(row, "evidence"))
    source_key = _text(row, "source_key") or metadata.get("source_key", "")
    if source_key:
        refs.add(source_key)
    if refs.intersection(governance["tombstone_ids"] | governance["withdrawals"]):
        return "source_withdrawn"
    for reference in refs:
        capture = (governance["captures"].get(reference)
                   or governance["captures_by_key"].get(reference))
        if capture and (_text(capture, "source_key") in governance["suppressed_keys"]
                        or _text(capture, "state") not in _ALLOWED_CAPTURE_STATES):
            return "source_withdrawn"
    dimension, claim_hash = metadata.get("profile_dimension", ""), metadata.get("normalized_claim_hash", "")
    person_ids = {selector.actor_id, _text(row, "subject_id"), _text(row, "object_id"),
                  metadata.get("person_id", "")}
    if claim_hash and any((person_id, dimension, claim_hash, selector.scope) in governance["portrait"]
                          for person_id in person_ids if person_id):
        return "portrait_suppressed"
    content = _text(row, "content")
    if not content.strip():
        return "content_empty"
    if len(content) > MAX_MATERIAL_CHARS:
        return "content_too_large"
    return ""


def _timeline_reason(connection, row, selector, governance):
    policy_reason = _policy_reason(selector, governance)
    if policy_reason:
        return policy_reason
    identifier = _text(row, "id")
    message_id = _text(row, "message_id")
    if identifier in governance["tombstone_ids"] | governance["withdrawals"]:
        return "source_withdrawn"
    if message_id and message_id in governance["tombstone_messages"]:
        return "source_withdrawn"
    metadata = _json_dict(_text(row, "metadata"))
    if metadata is None:
        return "metadata_invalid"
    if _references(metadata).intersection(governance["tombstone_ids"] | governance["withdrawals"]):
        return "source_withdrawn"
    capture = governance["captures"].get(identifier)
    event_type = _text(row, "event_type")
    content = _text(row, "content")
    source_integrity = "legacy_timeline_projection"
    if capture:
        key, state = _text(capture, "source_key"), _text(capture, "state")
        if key in governance["suppressed_keys"] or state not in _ALLOWED_CAPTURE_STATES:
            return "capture_revoked_or_changed"
        identity = _json_dict(_text(capture, "identity"))
        if identity is None or not (
                identity.get("bot") == selector.bot_id
                and identity.get("platform") == selector.platform
                and identity.get("persona") == selector.persona_id
                and identity.get("scope") == selector.scope
                and identity.get("session") == selector.session_id
                and identity.get("audience") == selector.actor_id
                and identity.get("message", "") == message_id):
            return "capture_identity_mismatch"
        expected_direction = "incoming" if _text(row, "event_type") == "user_message" else "outgoing"
        expected_speaker = _text(row, "subject_id")
        if (identity.get("direction") != expected_direction
                or identity.get("speaker") != expected_speaker
                or (expected_direction == "outgoing" and expected_speaker != selector.bot_id)):
            return "capture_identity_mismatch"
        content = (_capture_body(connection, key, _text(capture, "manifest"))
                   if governance["capture_chunks_available"] else None)
        if content is None or content != _text(row, "content"):
            return "capture_manifest_invalid"
        source_integrity = "verified_capture_chunks"
    elif event_type in ("user_message", "bot_response"):
        return "message_capture_unavailable"
    if not content.strip():
        return "content_empty"
    if len(content) > MAX_MATERIAL_CHARS:
        return "content_too_large"
    return "", content, source_integrity


def _target_matches(binding, context):
    scope = context.scope
    role_id = context.role_binding.role.subject_id
    actor_id = context.actor.subject.subject_id
    scope_kind = getattr(scope.kind, "value", scope.kind)
    return (binding.target_scope_kind == scope_kind
            and binding.target_native_scope_id in ("", scope.native_scope_id)
            and binding.target_installation_id == scope.installation_id
            and binding.target_bot_id == scope.bot_id and binding.target_role_id == role_id
            and (not binding.target_actor_id or binding.target_actor_id == actor_id)
            and binding.target_platform == scope.platform
            and binding.target_account_id == scope.account_id)


def _database(runtime):
    path = runtime.data_root / DATABASE_FILENAME
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS legacy_memory_imports (
            source_fingerprint TEXT PRIMARY KEY, snapshot_sha256 TEXT NOT NULL,
            binding_sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, stats_json TEXT NOT NULL,
            lineage_id TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS legacy_memory_materials (
            source_fingerprint TEXT NOT NULL, material_id TEXT NOT NULL, material_kind TEXT NOT NULL,
            target_installation_id TEXT NOT NULL, target_bot_id TEXT NOT NULL, target_role_id TEXT NOT NULL,
            target_actor_id TEXT NOT NULL, target_scope_kind TEXT NOT NULL DEFAULT 'private',
            target_native_scope_id TEXT NOT NULL DEFAULT '', target_platform TEXT NOT NULL, target_account_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL, text_content TEXT NOT NULL, attributes_json TEXT NOT NULL,
            PRIMARY KEY(source_fingerprint, material_id),
            FOREIGN KEY(source_fingerprint) REFERENCES legacy_memory_imports(source_fingerprint) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS legacy_memory_owner_idx ON legacy_memory_materials(
            target_installation_id,target_bot_id,target_role_id,target_actor_id,target_platform,target_account_id,
            occurred_at DESC,material_id DESC);
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(legacy_memory_imports)")}
    if "lineage_id" not in columns:
        connection.execute("ALTER TABLE legacy_memory_imports ADD COLUMN lineage_id TEXT NOT NULL DEFAULT ''")
    connection.execute("UPDATE legacy_memory_imports SET lineage_id=source_fingerprint WHERE lineage_id='' ")
    material_columns = {row[1] for row in connection.execute("PRAGMA table_info(legacy_memory_materials)")}
    if "target_scope_kind" not in material_columns:
        connection.execute("ALTER TABLE legacy_memory_materials ADD COLUMN target_scope_kind TEXT NOT NULL DEFAULT 'private'")
    if "target_native_scope_id" not in material_columns:
        connection.execute("ALTER TABLE legacy_memory_materials ADD COLUMN target_native_scope_id TEXT NOT NULL DEFAULT ''")
    connection.execute("CREATE INDEX IF NOT EXISTS legacy_memory_lineage_idx ON legacy_memory_imports(lineage_id)")
    connection.execute("""CREATE INDEX IF NOT EXISTS legacy_memory_scope_owner_idx ON legacy_memory_materials(
        target_installation_id,target_bot_id,target_role_id,target_scope_kind,target_native_scope_id,
        target_actor_id,target_platform,target_account_id,occurred_at DESC,material_id DESC)""")
    return connection


class LegacyMemoryMaterials:
    """Archive importer and exact-owner reader for historical V1 memory material."""

    def __init__(self, writer):
        self.writer = writer
        self.runtime = writer.runtime

    @staticmethod
    def lineage_id(snapshot_path):
        path = _safe_database(snapshot_path)
        return digest(["legacy-memory-lineage.v1", str(path).casefold()])

    @staticmethod
    def inspect_snapshot(snapshot_path):
        """Return identity-only source inventory for explicit mapping review."""
        path = _safe_database(snapshot_path)
        connection = _readonly(path)
        try:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"memories", "timeline"}.issubset(tables):
                raise ValueError("legacy_memory_schema_unsupported")
            _validate_schema(connection)
            counts, invalid = {}, {"memories": 0, "timeline": 0}
            for table in ("memories", "timeline"):
                for row in _rows(connection, table):
                    selector = _owner(row, table=table)
                    if selector is None:
                        invalid[table] += 1
                        continue
                    key = selector.key()
                    entry = counts.setdefault(key, {"source": selector.document(), "memories": 0,
                                                    "timeline": 0, "queryable": selector.scope in ("private", "group"),
                                                    "owner_id": _owner_id(selector)})
                    entry[table] += 1
            governance = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                          for table in ("message_source_tombstones", "life_message_withdrawals",
                                        "capture_suppression", "memory_acl_rules", "memory_acl_policies",
                                        "review_queue", "memory_correction_receipts", "portrait_suppressions")
                          if table in tables}
            return {"profile": PROFILE, "snapshot_sha256": _snapshot_hash(path),
                    "owners": sorted(counts.values(), key=lambda item: tuple(item["source"].values())),
                    "unresolved_ownership": invalid, "governance": governance,
                    "queryable_scope": "private_and_explicitly_mapped_group",
                    "group_scope": "exact_mapping_required",
                    "hashed_scoped_namespace": "archive_only"}
        finally:
            connection.close()

    def import_snapshot(self, snapshot_path, *, source_fingerprint, bindings=(), owner_ids=(),
                        target=None, lineage_id=None, preview=False, destination_scoped=False):
        """Project governed private or group materials from an immutable snapshot.

        ``bindings`` is a tuple of ``LegacyMemoryBinding`` values or their strict
        document form. Matching is exact across every V1 ownership dimension.
        Records without one unique binding remain only in the full archive.
        """
        if type(preview) is not bool:
            raise ValueError("legacy_memory_preview_flag_invalid")
        if (type(source_fingerprint) is not str or len(source_fingerprint) != 64
                or any(char not in "0123456789abcdef" for char in source_fingerprint)):
            raise ValueError("legacy_memory_fingerprint_invalid")
        lineage_id = _lineage_id(lineage_id) if lineage_id is not None else self.lineage_id(snapshot_path)
        normalized_bindings = tuple(_binding(item) for item in bindings)
        selected_ids = _selected_owner_ids(owner_ids)
        target_binding = _target_document(target) if selected_ids else None
        source_lineage_id = lineage_id
        destinations = ([target_binding] if target_binding else []) + [b.target_document() for b in normalized_bindings]
        destinations = list({encode(d): d for d in destinations}.values())
        if destination_scoped:
            destination_key = sorted(encode(d) for d in destinations)
            source_fingerprint = digest([source_fingerprint, destination_key])
            lineage_id = digest([lineage_id, destination_key])
        if selected_ids and target_binding is None:
            raise ValueError("legacy_memory_target_selector_invalid")
        by_source = {}
        for binding in normalized_bindings:
            by_source.setdefault(binding.source.key(), set()).add(binding)
        normalized_bindings = tuple(sorted(normalized_bindings,
            key=lambda item: (item.source.key(), item.target_installation_id, item.target_bot_id,
                              item.target_role_id, item.target_actor_id, item.target_platform,
                              item.target_account_id)))
        binding_sha256 = hashlib.sha256(encode({
            "bindings": [{"source": binding.source.document(), "target": binding.target_document()}
                for binding in normalized_bindings],
            "selected_owner_ids": selected_ids, "target": target_binding,
            "lineage_id": lineage_id,
        }).encode("utf-8")).hexdigest()

        source_path = _safe_database(snapshot_path)
        snapshot_sha256 = _snapshot_hash(source_path)
        source = _readonly(source_path)
        database_target = None
        try:
            required = {"memories", "timeline"}
            if not required.issubset({row[0] for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}):
                raise ValueError("legacy_memory_schema_unsupported")
            _validate_schema(source)
            if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("legacy_memory_snapshot_integrity_failed")
            governance = _governance(source)
            material_rows, exclusions, owners, found_owner_ids = [], {}, {}, set()
            scanned = {"memories": 0, "timeline": 0}
            unresolved = {"memories": 0, "timeline": 0}

            def exclude(reason):
                exclusions[reason] = exclusions.get(reason, 0) + 1

            for table in ("memories", "timeline"):
                for row in _rows(source, table):
                    scanned[table] += 1
                    selector = _owner(row, table=table)
                    if selector is None:
                        unresolved[table] += 1
                        exclude("ownership_missing_or_invalid")
                        continue
                    owner_id = _owner_id(selector)
                    found_owner_ids.add(owner_id)
                    owner = owners.setdefault(owner_id, {"owner_id": owner_id,
                        "source": selector.document(), "memories": 0, "timeline": 0,
                        "queryable": selector.scope in ("private", "group"), "mapped": False,
                        "imported": 0})
                    owner[table] += 1
                    if owner_id in selected_ids:
                        if selector.scope != target_binding["scope_kind"]:
                            raise ValueError("legacy_memory_owner_scope_mismatch")
                        binding = LegacyMemoryBinding(selector,
                            target_installation_id=target_binding["installation_id"],
                            target_bot_id=target_binding["bot_id"], target_role_id=target_binding["role_id"],
                            target_actor_id=target_binding["actor_id"], target_platform=target_binding["platform"],
                            target_account_id=target_binding["account_id"],
                            target_scope_kind=target_binding["scope_kind"],
                            target_native_scope_id=target_binding["native_scope_id"])
                        by_source.setdefault(selector.key(), set()).add(binding)
                    matches = by_source.get(selector.key(), set())
                    if len(matches) != 1:
                        exclude("binding_missing" if not matches else "binding_conflict")
                        continue
                    binding = next(iter(matches))
                    owner["mapped"] = True
                    if table == "memories":
                        reason = _memory_reason(row, selector, governance)
                        if reason:
                            exclude(reason)
                            continue
                        content = _text(row, "content")
                        source_integrity = "legacy_memory_record"
                    else:
                        result = _timeline_reason(source, row, selector, governance)
                        if isinstance(result, tuple):
                            reason, content, source_integrity = result
                        else:
                            reason, content, source_integrity = result, "", ""
                        if reason:
                            exclude(reason)
                            continue
                    when = _utc(_text(row, "occurred_at") or _text(row, "created_at"))
                    if (_text(row, "occurred_at") or _text(row, "created_at")) and not when:
                        exclude("time_invalid")
                        continue
                    if table == "memories":
                        attributes = {
                            "memory_type": _text(row, "memory_type"),
                            "visibility": _text(row, "visibility"),
                            "sayability": _text(row, "sayability") or "indirect",
                            "reality_level": _text(row, "reality_level") or "unknown",
                            "lifecycle": _text(row, "lifecycle") or "unknown",
                            "validity_status": _text(row, "validity_status") or "active",
                            "valid_from": _utc(_text(row, "valid_from")),
                            "valid_to": _utc(_text(row, "valid_to")),
                            "confidence": float(row["confidence"]) if "confidence" in row.keys() else None,
                            "correction_ref": _text(row, "correction_ref"),
                            "supersedes_id": _text(row, "supersedes_id"),
                            "historical_only": True,
                            "source_integrity": source_integrity,
                        }
                        identifier = _text(row, "id")
                    else:
                        attributes = {"event_type": _text(row, "event_type"),
                                      "retention_class": _text(row, "retention_class") or "unknown",
                                      "source_integrity": source_integrity,
                                      "historical_only": True}
                        identifier = _text(row, "id")
                    material_id = digest([source_fingerprint, table, identifier])
                    material_rows.append((source_fingerprint, material_id, table,
                        binding.target_installation_id, binding.target_bot_id, binding.target_role_id,
                        binding.target_actor_id, binding.target_scope_kind, binding.target_native_scope_id,
                        binding.target_platform, binding.target_account_id,
                        when, content, encode(attributes)))
                    owner["imported"] += 1

            selected_binding_keys = {item.source.key() for item in normalized_bindings}
            if (not set(selected_ids).issubset(found_owner_ids)
                    or not selected_binding_keys.issubset({
                        tuple(item["source"][key] for key in (
                            "bot_id", "platform", "persona_id", "scope", "session_id", "actor_id", "group_id"))
                        for item in owners.values()})):
                raise ValueError("legacy_memory_owner_stale")

            stats = {"profile": PROFILE, "source_fingerprint": source_fingerprint,
                     "lineage_id": lineage_id,
                     "snapshot_sha256": snapshot_sha256, "binding_sha256": binding_sha256,
                     "scanned": scanned, "imported": {"memories": sum(row[2] == "memories" for row in material_rows),
                     "timeline": sum(row[2] == "timeline" for row in material_rows)},
                     "excluded": dict(sorted(exclusions.items())),
                     "excluded_count": sum(exclusions.values()), "read_model": "historical_only",
                     "source_archive_retained": True,
                     "owner_inventory": {
                         "owners": sorted(owners.values(), key=lambda item: item["owner_id"]),
                         "unresolved_ownership": unresolved,
                         "queryable_owner_count": sum(1 for item in owners.values() if item["imported"]),
                         "archive_only_owner_count": sum(1 for item in owners.values() if not item["imported"]),
                         "queryable_record_count": sum(item["imported"] for item in owners.values()),
                         "archive_only_record_count": sum(
                             item["memories"] + item["timeline"] - item["imported"]
                             for item in owners.values()),
                     },
                     "selected_owner_ids": list(selected_ids),
                     "selected_binding_owner_ids": sorted(
                         _owner_id(LegacyOwnerSelector(**item["source"]))
                         for item in owners.values() if item["mapped"] and _owner_id(
                             LegacyOwnerSelector(**item["source"])) not in selected_ids)}
            if preview:
                return {**stats, "preview": True}
            database_target = _database(self.runtime)
            with _DB_LOCK:
                database_target.execute("BEGIN IMMEDIATE")
                old = database_target.execute("SELECT snapshot_sha256,binding_sha256,stats_json,lineage_id FROM legacy_memory_imports WHERE source_fingerprint=?",
                                     (source_fingerprint,)).fetchone()
                if old and old["snapshot_sha256"] != snapshot_sha256:
                    raise ValueError("legacy_memory_snapshot_fingerprint_conflict")
                if old and old["lineage_id"] == lineage_id and old["binding_sha256"] == binding_sha256:
                    database_target.execute("ROLLBACK")
                    existing_stats = json.loads(old["stats_json"])
                    return {**existing_stats, "already_present": True}
                previous = [row[0] for row in database_target.execute(
                    "SELECT source_fingerprint FROM legacy_memory_imports WHERE lineage_id=?", (lineage_id,))]
                if old and old["lineage_id"] != lineage_id:
                    previous.append(source_fingerprint)
                if previous:
                    fingerprints = tuple(set(previous))
                    database_target.executemany("DELETE FROM legacy_memory_materials WHERE source_fingerprint=?",
                                                ((fingerprint,) for fingerprint in fingerprints))
                    database_target.executemany("DELETE FROM legacy_memory_imports WHERE source_fingerprint=?",
                                                ((fingerprint,) for fingerprint in fingerprints))
                if destination_scoped:
                    # Upgrade old shared projections without deleting another role's rows.
                    for imported in database_target.execute(
                            "SELECT source_fingerprint,lineage_id,stats_json FROM legacy_memory_imports").fetchall():
                        old_stats = json.loads(imported["stats_json"])
                        if old_stats.get("source_lineage_id", imported["lineage_id"]) != source_lineage_id:
                            continue
                        for destination in destinations:
                            columns = {"installation_id": "target_installation_id", "bot_id": "target_bot_id",
                                "role_id": "target_role_id", "actor_id": "target_actor_id",
                                "platform": "target_platform", "account_id": "target_account_id",
                                "scope_kind": "target_scope_kind"}
                            conditions = " AND ".join(column + "=?" for column in columns.values())
                            database_target.execute("DELETE FROM legacy_memory_materials WHERE source_fingerprint=? AND " + conditions,
                                (imported["source_fingerprint"], *(destination[key] for key in columns)))
                        if not database_target.execute("SELECT 1 FROM legacy_memory_materials WHERE source_fingerprint=? LIMIT 1",
                                (imported["source_fingerprint"],)).fetchone():
                            database_target.execute("DELETE FROM legacy_memory_imports WHERE source_fingerprint=?", (imported["source_fingerprint"],))
                    stats["source_lineage_id"] = source_lineage_id
                database_target.execute("INSERT INTO legacy_memory_imports(source_fingerprint,snapshot_sha256,binding_sha256,imported_at,stats_json,lineage_id) VALUES (?,?,?,?,?,?)",
                               (source_fingerprint, snapshot_sha256, binding_sha256,
                                datetime.now(timezone.utc).isoformat(), encode(stats), lineage_id))
                database_target.executemany("""INSERT INTO legacy_memory_materials(
                    source_fingerprint,material_id,material_kind,target_installation_id,target_bot_id,
                    target_role_id,target_actor_id,target_scope_kind,target_native_scope_id,target_platform,
                    target_account_id,occurred_at,text_content,attributes_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", material_rows)
                database_target.execute("COMMIT")
            return {**stats, "already_present": False}
        except BaseException:
            if database_target is not None and database_target.in_transaction:
                database_target.execute("ROLLBACK")
            raise
        finally:
            if database_target is not None:
                database_target.close()
            source.close()

    def plan_snapshot(self, snapshot_path, *, source_fingerprint, bindings=(), owner_ids=(), target=None,
                      lineage_id=None, destination_scoped=False):
        return self.import_snapshot(snapshot_path, source_fingerprint=source_fingerprint,
                                    bindings=bindings, owner_ids=owner_ids, target=target,
                                    lineage_id=lineage_id, preview=True, destination_scoped=destination_scoped)

    @outcome
    def query(self, context, *, query_intent="", material_kind="all", limit=None,
              cursor=None, time_start=None, time_end=None, group_read_authorized=False,
              lexical=False, max_result_chars=None):
        scope_kind = getattr(context.scope.kind, "value", context.scope.kind)
        if scope_kind == ScopeKind.PRIVATE.value:
            self.writer.access.check(context, "memory.read")
            policy = self.writer.access.policy_for(context)
            max_items, max_chars = min(policy.query_items, 50), policy.query_chars
        elif scope_kind == ScopeKind.GROUP.value:
            if group_read_authorized is not True:
                raise TaskError("group_memory_access_denied", "legacy group history requires group.memory.read")
            max_items, max_chars = 5, 8192
        else:
            raise TaskError("memory_conversation_context_required", "legacy memory requires a private or group conversation")
        if max_result_chars is not None:
            if type(max_result_chars) is not int or not 256 <= max_result_chars <= 48000:
                raise ValueError("legacy memory result budget invalid")
            max_chars = min(max_chars, max_result_chars)
        _bounded(query_intent, "query_intent", MAX_QUERY_CHARS)
        if material_kind not in ("all", "memories", "timeline"):
            raise ValueError("legacy material kind invalid")
        page_limit = min(max_items, 5) if limit is None and scope_kind == ScopeKind.GROUP.value else max_items if limit is None else limit
        if type(page_limit) is not int or not 1 <= page_limit <= max_items:
            raise ValueError("legacy memory page limit invalid")
        start, end = _utc(time_start), _utc(time_end)
        if time_start and not start or time_end and not end or (start and end and start >= end):
            raise ValueError("legacy memory time range invalid")
        path = self.runtime.data_root / DATABASE_FILENAME
        if not path.exists():
            return {"profile": PROFILE, "items": [], "next_cursor": None,
                    "source": "v1_historical_materials", "historical_only": True}
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            target = (context.scope.installation_id, context.scope.bot_id,
                      context.role_binding.role.subject_id, scope_kind,
                      context.scope.native_scope_id,
                      context.actor.subject.subject_id if scope_kind == ScopeKind.PRIVATE.value else "",
                      context.scope.platform, context.scope.account_id)
            native_scope_match = ("target_native_scope_id=?" if scope_kind == ScopeKind.GROUP.value
                                  else "target_native_scope_id IN ('', ?)")
            generations = connection.execute(f"""SELECT i.source_fingerprint,i.snapshot_sha256,i.binding_sha256
                FROM legacy_memory_imports i WHERE EXISTS (SELECT 1 FROM legacy_memory_materials m
                WHERE m.source_fingerprint=i.source_fingerprint AND m.target_installation_id=?
                AND m.target_bot_id=? AND m.target_role_id=? AND m.target_scope_kind=?
                AND m.{native_scope_match} AND m.target_actor_id=?
                AND m.target_platform=? AND m.target_account_id=?) ORDER BY i.source_fingerprint""",
                target).fetchall()
            query_hash = digest([context.key, query_intent, material_kind, start, end, lexical,
                                 [tuple(row) for row in generations]])
            after = None
            offset = 0
            if cursor is not None:
                _bounded(cursor, "cursor", 1024, empty=False)
                try:
                    value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
                except (ValueError, TypeError):
                    raise ValueError("legacy memory cursor invalid") from None
                if (type(value) is not dict or value.get("query") != query_hash
                        or type(value.get("material_id")) is not str
                        or type(value.get("offset", 0)) is not int or value.get("offset", 0) < 0):
                    raise ValueError("legacy memory cursor invalid")
                after = value["material_id"]
                offset = value.get("offset", 0)
            where = ["target_installation_id=?", "target_bot_id=?", "target_role_id=?",
                     "target_scope_kind=?", native_scope_match,
                     "target_actor_id=?", "target_platform=?", "target_account_id=?"]
            params = list(target)
            if material_kind != "all":
                where.append("material_kind=?")
                params.append(material_kind)
            if start:
                where.append("occurred_at!='' AND occurred_at>=?")
                params.append(start)
            if end:
                where.append("occurred_at!='' AND occurred_at<?")
                params.append(end)
            rank, rank_params = "CAST(0 AS INTEGER)", []
            if query_intent and lexical:
                from .search import terms
                words = {bytes.fromhex(t[1:]).decode("utf-8") for t in terms(query_intent)}
                words -= {"记得", "还记", "什么", "我们", "之前", "以前", "那天", "了吗", "的吗", "说过", "时候"}
                words = sorted((w for w in words if len(w) >= 2), key=lambda w: (-len(w), w))[:32]
                if not words:
                    return {"profile": PROFILE, "items": [], "next_cursor": None,
                            "source": "v1_historical_materials", "historical_only": True}
                where.append("(" + " OR ".join("instr(lower(text_content),?)>0" for _ in words) + ")")
                params.extend(words)
                rank = "(" + "+".join("(instr(lower(text_content),?)>0)" for _ in words) + ")"
                rank_params = words
            elif query_intent:
                where.append("instr(lower(text_content),lower(?))>0")
                params.append(query_intent)
            continuation = None
            if after:
                previous = connection.execute("SELECT occurred_at,text_content FROM legacy_memory_materials WHERE material_id=? AND " +
                    " AND ".join(where), [after, *params]).fetchone()
                if previous is None:
                    raise ValueError("legacy memory cursor unavailable")
                if offset:
                    if offset >= len(previous["text_content"]):
                        raise ValueError("legacy memory cursor unavailable")
                    continuation = connection.execute("SELECT material_id,material_kind,occurred_at,text_content,attributes_json "
                        "FROM legacy_memory_materials WHERE material_id=? AND " + " AND ".join(where),
                        [after, *params]).fetchone()
                prior_rank = sum(word in previous["text_content"].lower() for word in rank_params)
                where.append(f"({rank}<? OR ({rank}=? AND (occurred_at<? OR (occurred_at=? AND material_id<?))))")
                params.extend((*rank_params, prior_rank, *rank_params, prior_rank,
                               previous["occurred_at"], previous["occurred_at"], after))
            statement = ("SELECT material_id,material_kind,occurred_at,text_content,attributes_json "
                         "FROM legacy_memory_materials WHERE " + " AND ".join(where) +
                         f" ORDER BY {rank} DESC,occurred_at DESC,material_id DESC LIMIT ?")
            rows = connection.execute(statement, (*params, *rank_params, page_limit + 1)).fetchall()
        finally:
            connection.close()

        row_capacity = page_limit - (1 if continuation is not None else 0)
        more_rows = len(rows) > row_capacity
        page_rows = ([continuation] if continuation is not None else []) + rows[:row_capacity]
        items, used_chars, partial = [], 0, None
        for index, row in enumerate(page_rows):
            start_offset = offset if continuation is not None and index == 0 else 0
            attributes = json.loads(row["attributes_json"])
            material = row["text_content"]
            excerpt_size = len(material) - start_offset
            while excerpt_size > 0:
                end_offset = start_offset + excerpt_size
                item = {"id": row["material_id"], "kind": row["material_kind"],
                        "occurred_at": row["occurred_at"] or None,
                        "text": material[start_offset:end_offset], "excerpt_start": start_offset,
                        "excerpt_end": end_offset, "total_chars": len(material),
                        "next_offset": end_offset if end_offset < len(material) else None,
                        **attributes, "current_fact": False, "v2_source_ref": None}
                size = len(encode(item))
                if used_chars + size <= max_chars:
                    break
                excerpt_size //= 2
            if excerpt_size <= 0:
                if not items:
                    raise TaskError("legacy_memory_query_budget_too_small",
                                    "query budget cannot fit a historical material item")
                more_rows = True
                break
            items.append(item)
            used_chars += size
            if item["next_offset"] is not None:
                partial = {"query": query_hash, "material_id": item["id"],
                           "offset": item["next_offset"]}
                break
        next_cursor = None
        if partial is not None:
            next_cursor = base64.urlsafe_b64encode(encode(partial).encode("utf-8")).decode("ascii").rstrip("=")
        elif more_rows and items:
            next_cursor = base64.urlsafe_b64encode(encode({"query": query_hash,
                "material_id": items[-1]["id"], "offset": 0}).encode("utf-8")).decode("ascii").rstrip("=")
        return {"profile": PROFILE, "items": items, "next_cursor": next_cursor,
                "source": "v1_historical_materials", "historical_only": True,
                "read_only": True, "v2_sources_created": False}

    def verify(self, context, items, *, group_read_authorized=False):
        """Revalidate historical excerpts against the currently mapped target."""
        scope_kind = getattr(context.scope.kind, "value", context.scope.kind)
        actor_id = context.actor.subject.subject_id if scope_kind == ScopeKind.PRIVATE.value else ""
        if scope_kind == ScopeKind.PRIVATE.value:
            self.writer.access.check(context, "memory.read")
        elif scope_kind == ScopeKind.GROUP.value:
            if group_read_authorized is not True:
                raise TaskError("group_memory_access_denied", "legacy group history requires group.memory.read")
        else:
            raise TaskError("memory_conversation_context_required", "legacy memory requires a private or group conversation")
        target = (context.scope.installation_id, context.scope.bot_id,
                  context.role_binding.role.subject_id, scope_kind,
                  context.scope.native_scope_id, actor_id, context.scope.platform, context.scope.account_id)
        if type(items) is not list or len(items) > 50:
            raise TaskError("legacy_memory_result_invalid", "historical result exceeded its verification budget")
        path = self.runtime.data_root / DATABASE_FILENAME
        if not path.exists():
            raise TaskError("legacy_memory_result_changed", "historical result is no longer available")
        connection = sqlite3.connect(readonly_uri(path), uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "legacy_memory_materials" not in tables:
                raise TaskError("legacy_memory_result_changed", "historical result is no longer available")
            native_scope_match = ("target_native_scope_id=?" if scope_kind == ScopeKind.GROUP.value
                                  else "target_native_scope_id IN ('', ?)")
            for item in items:
                if type(item) is not dict or type(item.get("id")) is not str:
                    raise TaskError("legacy_memory_result_invalid", "historical result identity is invalid")
                row = connection.execute(f"""SELECT text_content,attributes_json FROM legacy_memory_materials
                    WHERE material_id=? AND target_installation_id=? AND target_bot_id=? AND target_role_id=?
                    AND target_scope_kind=? AND {native_scope_match} AND target_actor_id=?
                    AND target_platform=? AND target_account_id=?""", (item["id"], *target)).fetchone()
                if row is None:
                    raise TaskError("legacy_memory_result_changed", "historical result is no longer mapped to this target")
                start, end = item.get("excerpt_start"), item.get("excerpt_end")
                try:
                    attributes = json.loads(row["attributes_json"])
                except (TypeError, ValueError):
                    raise TaskError("legacy_memory_result_changed", "historical result metadata is unavailable") from None
                if (type(start) is not int or type(end) is not int or start < 0 or end < start
                        or row["text_content"][start:end] != item.get("text")
                        or len(row["text_content"]) != item.get("total_chars")
                        or any(item.get(key) != value for key, value in attributes.items())):
                    raise TaskError("legacy_memory_result_changed", "historical result no longer matches its snapshot")
        finally:
            connection.close()
        return True
