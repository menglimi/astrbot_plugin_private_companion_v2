"""Acquaintance document contract: bounded counters and platform-observed names.

The card is bot-internal derivation, not member-authored content, so it has no
source publication of its own. Every stored name stays a display reference;
platform or administrator origin never upgrades into proven identity.
"""

from companion_v2.foundation.refs import ScopeKind


KIND = "person.acquaintance.v1"
VERSION = 1
MAX_NAME = 64
MAX_CONTEXTS = 16
MAX_GROUP_CARDS = 32


def clean_name(value):
    """Bound a platform-provided display name to printable reference text."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if len(cleaned) > MAX_NAME:
        cleaned = cleaned[:MAX_NAME].strip()
    return cleaned or None


def empty_document():
    return {"version": VERSION, "route": None, "native_account_id": None,
            "platform_nickname": None, "nickname_updated_at": None,
            "admin_nickname": None, "admin_nickname_updated_at": None,
            "group_cards": {}, "contexts": {}, "private_attempts": {"count": 0, "last_at": None}}


def bind_route(document, context):
    """Pin the owning bot/role route and the authenticated account on first
    write, so management directories can list cards without reversing digests."""
    if document.get("route") is None:
        scope = context.scope
        document["route"] = {"installation_id": scope.installation_id, "platform": scope.platform,
                             "bot_id": scope.bot_id, "account_id": scope.account_id,
                             "role_id": context.role_binding.role.subject_id,
                             "subject_id": context.actor.subject.subject_id}
    if not document.get("native_account_id"):
        document["native_account_id"] = context.actor.principal.native_account_id
    return document


def context_key(scope):
    # Per-member group sessions must not split one member's presence; the card
    # counts per group, not per session, and keeps private as a single context.
    return "group:" + scope.native_scope_id if scope.kind is ScopeKind.GROUP else "private"


def count_input(document, scope, received_at, day):
    """Fold one admitted input into the card. Distinct-day counts track the last
    active day only; re-visits to older days merge into the current streak."""
    contexts = document["contexts"]
    key = context_key(scope)
    entry = contexts.get(key)
    if entry is None:
        if len(contexts) >= MAX_CONTEXTS:
            del contexts[min(contexts, key=lambda name: contexts[name]["last_seen"])]
        entry = contexts[key] = {"msg_count": 0, "active_days": 0, "first_seen": received_at,
                                 "last_seen": received_at, "last_active_day": None}
    entry["msg_count"] += 1
    entry["last_seen"] = received_at
    if entry["last_active_day"] != day:
        entry["active_days"] += 1
        entry["last_active_day"] = day
    return entry


def aggregate(document):
    entries = tuple(document["contexts"].values())
    return {"msg_count": sum(entry["msg_count"] for entry in entries),
            "active_days": sum(entry["active_days"] for entry in entries),
            "first_seen": min((entry["first_seen"] for entry in entries), default=None),
            "last_seen": max((entry["last_seen"] for entry in entries), default=None)}


def display_name(document, scope):
    """Prefer an explicit administrator name, then the current platform card."""
    if document.get("admin_nickname"):
        return document["admin_nickname"], "administrator"
    card = document["group_cards"].get(scope.native_scope_id) if scope.kind is ScopeKind.GROUP else None
    if card is not None:
        return card["card"], "platform"
    if document["platform_nickname"]:
        return document["platform_nickname"], "platform"
    return None, None


def directory_display_name(document):
    """Account-wide fallback used by the management directory."""
    if document.get("admin_nickname"):
        return document["admin_nickname"], "administrator"
    if document.get("platform_nickname"):
        return document["platform_nickname"], "platform"
    if document.get("group_cards"):
        return next(iter(document["group_cards"].values()))["card"], "platform"
    return None, None
