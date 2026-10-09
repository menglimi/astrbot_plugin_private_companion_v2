"""Pure access decisions for V1 memory windows and ACL rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


_SCOPES = frozenset(("private", "group"))
_DENY_EFFECTS = frozenset(("deny", "block", "blacklist"))
_BLACKLIST_MODES = frozenset(("blacklist", "deny", "block"))
_MISSING = object()


@dataclass(frozen=True)
class LegacyAccessDecision:
    readable: bool
    reason_code: str


def _window(value: object) -> tuple[str, str] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    scope, window_id = value
    if (not isinstance(scope, str) or scope not in _SCOPES
            or not isinstance(window_id, str) or not window_id.strip()
            or len(window_id) > 160 or "\x00" in window_id):
        return None
    return scope, window_id.strip()


def _field(row: object, name: str) -> object:
    if isinstance(row, Mapping):
        return row.get(name, _MISSING)
    try:
        return row[name]  # sqlite3.Row and other keyed row objects
    except (IndexError, KeyError, TypeError):
        return _MISSING


def _is_row(row: object) -> bool:
    return isinstance(row, Mapping) or callable(getattr(row, "keys", None))


def _mode(value: object) -> str | None:
    if value is _MISSING:
        return None
    if value is None:
        return "whitelist"
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _BLACKLIST_MODES:
        return "blacklist"
    if normalized in ("", "whitelist", "allow"):
        return "whitelist"
    return None


def _enabled(value: object) -> bool | None:
    if value is True or (type(value) is int and value == 1):
        return True
    if value is False or (type(value) is int and value == 0):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on", "enabled"):
            return True
        if normalized in ("0", "false", "no", "off", "disabled", ""):
            return False
    return None


def _policy_map(policies: Iterable[Mapping[str, Any]], relevant: set[tuple[str, str]]):
    found: dict[tuple[str, str], dict[str, object]] = {}
    for row in policies:
        if not _is_row(row):
            return None, "policy_ambiguous"
        scope = _field(row, "window_scope")
        window_id = _field(row, "window_id")
        if not isinstance(scope, str) or not isinstance(window_id, str):
            return None, "policy_ambiguous"
        key = (scope.strip(), window_id.strip())
        if key not in relevant:
            continue
        read_mode = _mode(_field(row, "read_mode"))
        share_mode = _mode(_field(row, "share_mode"))
        recall_value = _field(row, "recall_enabled")
        recall_enabled = None if recall_value in (_MISSING, None, "") else _enabled(recall_value)
        if read_mode is None or share_mode is None:
            return None, "policy_mode_unknown"
        if recall_value not in (_MISSING, None, "") and recall_enabled is None:
            return None, "policy_value_unknown"
        value = {"read_mode": read_mode, "share_mode": share_mode,
                 "recall_enabled": recall_enabled}
        previous = found.get(key)
        if previous is not None and previous != value:
            return None, "policy_ambiguous"
        found[key] = value
    return found, ""


def _matching_rules(rules: Iterable[Mapping[str, Any]], owner: tuple[str, str],
                    reader: tuple[str, str]) -> tuple[bool, bool, bool]:
    denied = allowed = unknown = False
    for row in rules:
        if not _is_row(row):
            unknown = True
            continue
        values = (_field(row, "owner_scope"), _field(row, "owner_id"),
                  _field(row, "reader_scope"), _field(row, "reader_id"))
        if not all(isinstance(value, str) for value in values):
            unknown = True
            continue
        pair = (values[0].strip(), values[1].strip(), values[2].strip(), values[3].strip())
        if pair != (*owner, *reader):
            continue
        enabled = _enabled(_field(row, "enabled"))
        if enabled is False:
            continue
        if enabled is not True:
            unknown = True
            continue
        effect = _field(row, "effect")
        normalized = "allow" if effect in (_MISSING, None, "") else (
            effect.strip().lower() if isinstance(effect, str) else "")
        if normalized in _DENY_EFFECTS:
            denied = True
        elif normalized == "allow":
            allowed = True
        else:
            unknown = True
    return denied, allowed, unknown


def evaluate_legacy_memory_access(
    owner: tuple[str, str],
    reader: tuple[str, str],
    *,
    policies: Iterable[Mapping[str, Any]],
    rules: Iterable[Mapping[str, Any]],
    known_readers: Iterable[tuple[str, str]],
) -> LegacyAccessDecision:
    """Evaluate one exact V1 owner-to-reader window pair.

    V1 defaults private windows to whitelist and group windows to blacklist.
    Matching deny rules override allow rules; private-to-group access always
    needs an explicit allow. A database row with unknown policy semantics fails
    closed. ``capture_enabled`` is intentionally not an access gate: it controls
    new capture, while ``recall_enabled`` controls the reader window. Record
    visibility, review state, lifecycle, and source governance remain separate
    checks for the caller.
    """
    owner_key, reader_key = _window(owner), _window(reader)
    if owner_key is None or reader_key is None:
        return LegacyAccessDecision(False, "identity_invalid")
    try:
        known = {_window(item) for item in known_readers}
    except (TypeError, ValueError):
        return LegacyAccessDecision(False, "reader_unknown")
    if None in known or owner_key not in known or reader_key not in known:
        if owner_key not in known:
            return LegacyAccessDecision(False, "owner_unknown")
        return LegacyAccessDecision(False, "reader_unknown")

    try:
        policy_rows, policy_error = _policy_map(policies, {owner_key, reader_key})
    except (TypeError, ValueError):
        return LegacyAccessDecision(False, "policy_ambiguous")
    if policy_rows is None:
        return LegacyAccessDecision(False, policy_error)
    reader_policy = policy_rows.get(reader_key)
    if reader_policy and reader_policy["recall_enabled"] is False:
        return LegacyAccessDecision(False, "reader_recall_disabled")

    if owner_key == reader_key:
        return LegacyAccessDecision(True, "same_window")

    try:
        denied, allowed, unknown = _matching_rules(rules, owner_key, reader_key)
    except (TypeError, ValueError):
        return LegacyAccessDecision(False, "acl_effect_unknown")
    if denied:
        return LegacyAccessDecision(False, "acl_deny")
    if unknown:
        return LegacyAccessDecision(False, "acl_effect_unknown")
    if allowed:
        return LegacyAccessDecision(True, "acl_allow")
    owner_default = "blacklist" if owner_key[0] == "group" else "whitelist"
    reader_default = "blacklist" if reader_key[0] == "group" else "whitelist"
    owner_policy = policy_rows.get(owner_key, {})
    reader_policy = reader_policy or {}
    owner_share = owner_policy.get("share_mode", owner_default)
    reader_mode = reader_policy.get("read_mode", reader_default)
    if owner_share not in ("whitelist", "blacklist") or reader_mode not in ("whitelist", "blacklist"):
        return LegacyAccessDecision(False, "policy_mode_unknown")
    if owner_share == "blacklist" and reader_mode == "blacklist":
        if owner_key[0] == "private" and reader_key[0] == "group":
            return LegacyAccessDecision(False, "private_group_allow_required")
        return LegacyAccessDecision(True, "blacklist_default_allowed")
    return LegacyAccessDecision(False, "policy_default_deny")
