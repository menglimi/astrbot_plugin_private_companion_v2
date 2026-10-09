"""Unified group member profiles and the bounded interaction graph.

The group directory is the management projection shared by three existing
sources: the per-person acquaintance card, imported member clues and the
short-lived group interaction rhythm.  It deliberately keeps those evidence
levels separate.  A native account is the stable key; names and imported
accounts remain display clues; an edge means that two members spoke close
enough together to be useful for turn context, not that they have a personal
relationship.

The graph is stored in ``runtime_metadata`` so it does not need another schema
migration.  Its owner ignores the native per-member session suffix and keeps
one graph for one Bot/account/group/role.  No private relationship records are
read here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.foundation.refs import ScopeKind


VERSION = "relationships.group-network.v1"
PREFIX = VERSION + ":"
PURPOSE = "group_relationship_network"
LINK_WINDOW_SECONDS = 180
MAX_MEMBERS = 512
MAX_EDGES = 512
MAX_ALIASES = 8
MAX_RECENT = 4
MAX_RECENT_CHARS = 120
MAX_EVENT_KEYS = 512
MAX_PROMPT_EDGES = 4
MAX_PROMPT_CHARS = 2400
MAX_MEMBER_CLUES = 6
MAX_UNMATCHED_CLUES = 32

_TONE_RULES = (
    ("tension", (r"别吵", r"闭嘴", r"你什么意思", r"太过分", r"有病吧", r"生气了")),
    ("banter", (r"哈哈+", r"笑死", r"没绷住", r"玩梗", r"整活", r"你不行", r"就这")),
)


def owner_key(context) -> str:
    """Stable graph owner for one group and one role, across native sessions."""
    scope = context.scope
    if scope.kind is not ScopeKind.GROUP:
        raise ValueError("group network requires a group scope")
    return route_owner_key(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                           scope.native_scope_id, context.role_binding.role.subject_id)


def route_owner_key(installation_id, platform_id, bot_id, account_id, group_id, role_id) -> str:
    """Build the same owner key for a management route without a live turn."""
    return digest([VERSION, installation_id, platform_id, bot_id, account_id, group_id, role_id])


def metadata_key(owner: str) -> str:
    return PREFIX + str(owner)


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _iso(value):
    if isinstance(value, datetime):
        return stamp(value)
    return str(value or "")


def _when(value):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _edge_key(first: str, second: str) -> tuple[str, str, str]:
    a, b = sorted((str(first), str(second)))
    return a, b, a + ":" + b


def _tone(text: str) -> str:
    compact = _clean(text, MAX_RECENT_CHARS)
    for tone, patterns in _TONE_RULES:
        if any(re.search(pattern, compact, flags=re.IGNORECASE) for pattern in patterns):
            return tone
    return "ordinary"


def _empty_document(context, at):
    scope = context.scope
    return {
        "version": VERSION,
        "group": {"installation_id": scope.installation_id, "platform_id": scope.platform,
                   "bot_id": scope.bot_id, "account_id": scope.account_id,
                   "group_id": scope.native_scope_id,
                   "role_id": context.role_binding.role.subject_id},
        "members": {}, "edges": {}, "last": None,
        "event_keys": [], "updated_at": _iso(at),
    }


def _valid_document(value):
    return isinstance(value, dict) and value.get("version") == VERSION \
        and isinstance(value.get("members"), dict) and isinstance(value.get("edges"), dict)


def _member(document, account_id, at):
    members = document["members"]
    item = members.get(account_id)
    if not isinstance(item, dict):
        item = {"account_id": account_id, "aliases": [], "message_count": 0,
                "active_days": 0, "first_seen": _iso(at), "last_seen": _iso(at),
                "last_active_day": None, "recent": []}
        members[account_id] = item
    return item


def _alias(item, value, kind, at):
    value = _clean(value, 64)
    if not value:
        return
    aliases = [entry for entry in item.get("aliases", ())
               if isinstance(entry, dict) and entry.get("value") != value]
    aliases.insert(0, {"value": value, "kind": kind, "last_seen": _iso(at)})
    item["aliases"] = aliases[:MAX_ALIASES]


def fold_event(existing, *, context, event, text, at=None, nickname="", card=""):
    """Fold one already admitted group input into the bounded graph document."""
    at = at or event.received_at
    document = existing if _valid_document(existing) else _empty_document(context, at)
    account_id = _clean(getattr(event.principal, "native_account_id", ""), 256)
    if not account_id:
        return document
    key = str(getattr(event, "scoped_key", "") or getattr(event, "event_id", ""))
    keys = [str(item) for item in document.get("event_keys", ())]
    if key and key in keys:
        return document
    if key:
        keys.append(key)
        document["event_keys"] = keys[-MAX_EVENT_KEYS:]

    item = _member(document, account_id, at)
    item["message_count"] = max(0, int(item.get("message_count") or 0)) + 1
    day = at.date().isoformat()
    if item.get("last_active_day") != day:
        item["active_days"] = max(0, int(item.get("active_days") or 0)) + 1
        item["last_active_day"] = day
    item["first_seen"] = min(str(item.get("first_seen") or _iso(at)), _iso(at))
    item["last_seen"] = max(str(item.get("last_seen") or _iso(at)), _iso(at))
    _alias(item, nickname, "platform_nickname", at)
    _alias(item, card, "group_card", at)
    snippet = _clean(text, MAX_RECENT_CHARS)
    if snippet:
        recent = [entry for entry in item.get("recent", ())
                  if isinstance(entry, dict) and entry.get("text") != snippet]
        recent.insert(0, {"at": _iso(at), "text": snippet})
        item["recent"] = recent[:MAX_RECENT]

    previous = document.get("last") if isinstance(document.get("last"), dict) else None
    previous_id = str(previous.get("speaker_id") or "") if previous else ""
    previous_at = _when(previous.get("at")) if previous else None
    if previous_id and previous_id != account_id and previous_at is not None:
        gap = (at - previous_at).total_seconds()
        if 0 <= gap <= LINK_WINDOW_SECONDS:
            first, second, edge_id = _edge_key(previous_id, account_id)
            edge = document["edges"].get(edge_id)
            if not isinstance(edge, dict):
                edge = {"a": first, "b": second, "count": 0,
                        "last_seen": _iso(at), "tone": "ordinary", "summary": "近期连续接话"}
            edge["count"] = max(0, int(edge.get("count") or 0)) + 1
            edge["last_seen"] = max(str(edge.get("last_seen") or _iso(at)), _iso(at))
            tones = {_tone(str(previous.get("text") or "")), _tone(text)}
            edge["tone"] = "tension" if "tension" in tones else "banter" if "banter" in tones else "ordinary"
            edge["summary"] = {"tension": "近期有紧绷表达", "banter": "近期有玩笑或接梗",
                                "ordinary": "近期连续接话"}[edge["tone"]]
            document["edges"][edge_id] = edge
    document["last"] = {"speaker_id": account_id, "at": _iso(at), "text": snippet}
    document["updated_at"] = _iso(at)
    if len(document["members"]) > MAX_MEMBERS:
        ranked = sorted(document["members"].items(), key=lambda pair: str(pair[1].get("last_seen") or ""), reverse=True)
        document["members"] = dict(ranked[:MAX_MEMBERS])
        keep = set(document["members"])
        document["edges"] = {key: value for key, value in document["edges"].items()
                              if value.get("a") in keep and value.get("b") in keep}
    if len(document["edges"]) > MAX_EDGES:
        ranked = sorted(document["edges"].items(), key=lambda pair: (
            int(pair[1].get("count") or 0), str(pair[1].get("last_seen") or "")), reverse=True)
        document["edges"] = dict(ranked[:MAX_EDGES])
    return document


def project_document(document, *, people=(), group_id=""):
    """Return the management-safe projection joined with acquaintance cards."""
    valid = _valid_document(document)
    if not valid:
        document = {"version": VERSION, "members": {}, "edges": {}, "updated_at": None}
    by_account = {str(item.get("native_account_id")): item for item in people
                  if isinstance(item, dict) and item.get("native_account_id")}
    sources = dict(document["members"])
    # An acquaintance card can outlive a graph row (for example, when the
    # graph was introduced after the member was first observed). Keep that
    # account in the same group directory without inventing interaction edges.
    if group_id:
        for account_id, person in by_account.items():
            group_record = person.get("groups", {}).get(str(group_id))
            if isinstance(group_record, dict) and account_id not in sources:
                sources[account_id] = {"account_id": account_id, "aliases": [],
                                       "message_count": 0, "active_days": 0,
                                       "first_seen": group_record.get("first_seen"),
                                       "last_seen": group_record.get("last_seen"),
                                       "recent": [], "card_only": True}
    members = []
    for account_id, value in sources.items():
        if not isinstance(value, dict):
            continue
        person = by_account.get(str(account_id), {})
        group_record = person.get("groups", {}).get(str(group_id), {})
        aliases = tuple(entry.get("value") for entry in value.get("aliases", ())
                        if isinstance(entry, dict) and entry.get("value"))
        has_graph_observation = not value.get("card_only")
        observation = value if has_graph_observation else group_record
        members.append({"native_account_id": str(account_id),
                        "subject_id": person.get("subject_id"),
                        "display_name": person.get("display_name") or (aliases[0] if aliases else None),
                        "name_basis": person.get("name_basis") or ("platform" if aliases else None),
                        "aliases": list(dict.fromkeys(aliases)),
                        "acquaintance": {"message_count": int(person.get("total", {}).get("msg_count") or 0),
                                         "active_days": int(person.get("total", {}).get("active_days") or 0),
                                         "first_seen": person.get("total", {}).get("first_seen"),
                                         "last_seen": person.get("total", {}).get("last_seen"),
                                         "admin_nickname": person.get("admin_nickname"),
                                         "private_chat": bool(person.get("private_chat")),
                                         "group": {"message_count": int(group_record.get("msg_count") or 0),
                                                   "active_days": int(group_record.get("active_days") or 0),
                                                   "last_seen": group_record.get("last_seen")}},
                        "group_observation": {"basis": ("legacy_aggregate" if observation.get("evidence_basis") == "v1_group_aggregate"
                                                            else "relationship_graph") if has_graph_observation else "acquaintance_card",
                                              "message_count": int(observation.get("message_count") or observation.get("msg_count") or 0),
                                              "active_days": int(observation.get("active_days") or 0),
                                              "first_seen": observation.get("first_seen"),
                                              "last_seen": observation.get("last_seen"),
                                              "recent": list(observation.get("recent") or ())[:MAX_RECENT]}})
    members.sort(key=lambda item: (-(item["group_observation"]["message_count"]), item["native_account_id"]))
    edges = []
    for value in document["edges"].values():
        if not isinstance(value, dict) or value.get("a") not in sources or value.get("b") not in sources:
            continue
        edges.append({"a": str(value["a"]), "b": str(value["b"]), "count": int(value.get("count") or 0),
                      "last_seen": value.get("last_seen"), "tone": value.get("tone", "ordinary"),
                      "summary": value.get("summary", "近期连续接话"),
                      "evidence_basis": value.get("evidence_basis", "live_observation")})
    edges.sort(key=lambda item: (item["count"], str(item.get("last_seen") or "")), reverse=True)
    return {"version": VERSION, "group_id": group_id or document.get("group", {}).get("group_id"),
            "members": members, "edges": edges, "member_count": len(members),
            "interaction_count": sum(item["count"] for item in edges),
            "unmatched_clues": [], "updated_at": document.get("updated_at")}


def attach_member_clues(network, clues):
    """Attach clues by declared account or unique label; return other clues separately."""
    members = network.get("members", []) if isinstance(network, dict) else []
    by_account = {str(item.get("native_account_id")): item for item in members
                  if item.get("native_account_id")}
    labels = {}
    for account_id, member in by_account.items():
        values = [member.get("display_name"), *(member.get("aliases") or ())]
        for value in values:
            label = " ".join(str(value or "").split()).casefold()
            if label:
                labels.setdefault(label, set()).add(account_id)

    unmatched = []
    for clue in clues:
        declared = tuple(dict.fromkeys(str(value) for value in clue.declared_account_ids if value))
        direct = [account for account in declared if account in by_account]
        clue_labels = tuple(dict.fromkeys(str(value) for value in clue.labels if value))
        candidates = set()
        if not direct:
            for value in clue_labels:
                candidates.update(labels.get(" ".join(value.split()).casefold(), ()))
        targets = direct if direct else sorted(candidates)
        basis = "declared_account" if direct else "display_label"
        clue_row = {"entry_id": clue.entry_id, "name": clue.name,
                    "aliases": list(clue.aliases), "declared_account_ids": list(declared),
                    "gender": clue.gender, "content": clue.content[:480],
                    "priority": clue.priority, "basis": basis}
        if len(targets) == 1 or direct:
            for account in targets:
                entries = by_account[account].setdefault("clues", [])
                if (len(entries) < MAX_MEMBER_CLUES
                        and all(entry.get("entry_id") != clue.entry_id for entry in entries)):
                    entries.append(dict(clue_row))
        else:
            clue_row["basis"] = "ambiguous_display_label" if targets else "unmatched"
            clue_row["candidate_account_ids"] = targets
            unmatched.append(clue_row)
    network["unmatched_clues"] = unmatched[:MAX_UNMATCHED_CLUES]
    for member in members:
        member.setdefault("clues", [])
    return network


class GroupRelationshipStore:
    """Read and write the unified group relationship source of truth."""

    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def _load(connection, key):
        row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError):
            return None
        return value if _valid_document(value) else None

    def read(self, context):
        return self.read_owner(owner_key(context))

    def read_owner(self, owner):
        key = metadata_key(owner)
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError):
            return None
        return value if _valid_document(value) else None

    def observe(self, context, event, connection, *, text=""):
        if context.scope.kind is not ScopeKind.GROUP:
            return
        key = metadata_key(owner_key(context))
        document = fold_event(self._load(connection, key), context=context, event=event,
                              text=text, at=event.received_at)
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                           (key, encode(document)))

    def record_names(self, context, *, nickname=None, card=None, at=None):
        if context.scope.kind is not ScopeKind.GROUP:
            return
        account_id = str(context.actor.principal.native_account_id)
        at = at or datetime.now(timezone.utc)
        key = metadata_key(owner_key(context))
        with self.runtime.transaction() as connection:
            document = self._load(connection, key)
            if not document:
                return
            item = _member(document, account_id, at)
            _alias(item, nickname, "platform_nickname", at)
            _alias(item, card, "group_card", at)
            document["updated_at"] = _iso(at)
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                               (key, encode(document)))

    def import_legacy_aggregate(self, context, *, source_key, members, edges, at=None):
        """Merge a reviewed V1 aggregate without replaying it as a live event."""
        if context.scope.kind is not ScopeKind.GROUP:
            raise TaskError("group_network_group_required", "legacy interaction data requires a group target")
        if (type(source_key) is not str or not source_key or len(source_key) > 128
                or type(members) is not dict or type(edges) is not list):
            raise TaskError("group_network_legacy_payload_invalid", "legacy aggregate payload is invalid")
        at = at or datetime.now(timezone.utc)
        key = metadata_key(owner_key(context))
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
            if row is not None:
                try:
                    current = json.loads(row["value"])
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise TaskError("group_network_store_unreadable", "current relationship graph is unreadable") from error
                if not _valid_document(current):
                    raise TaskError("group_network_store_unreadable", "current relationship graph is unreadable")
                document = current
            else:
                document = _empty_document(context, at)
            imports = document.get("legacy_imports")
            if not isinstance(imports, list):
                imports = []
            if source_key in imports:
                return {"imported": False, "duplicate": True, "members_added": 0, "edges_added": 0}

            members_added = 0
            for raw_id, raw_member in members.items():
                account_id = _clean(raw_id, 256)
                if not account_id or not isinstance(raw_member, dict):
                    continue
                existing = document["members"].get(account_id)
                is_new = not isinstance(existing, dict)
                if not isinstance(existing, dict):
                    existing = {"account_id": account_id, "aliases": [], "message_count": 0,
                                "active_days": 0, "first_seen": None, "last_seen": None, "recent": []}
                    document["members"][account_id] = existing
                    members_added += 1
                existing["message_count"] = max(int(existing.get("message_count") or 0),
                                                 int(raw_member.get("message_count") or 0))
                existing["active_days"] = max(int(existing.get("active_days") or 0),
                                               int(raw_member.get("active_days") or 0))
                for field in ("first_seen", "last_seen"):
                    candidate = _when(raw_member.get(field))
                    previous = _when(existing.get(field))
                    if candidate is not None and (previous is None or (field == "first_seen" and candidate < previous)
                                                   or (field == "last_seen" and candidate > previous)):
                        existing[field] = _iso(candidate)
                label = _clean(raw_member.get("name"), 64)
                if label and not any(item.get("value") == label for item in existing.get("aliases", ())
                                     if isinstance(item, dict)):
                    aliases = list(existing.get("aliases") or ())
                    aliases.insert(0, {"value": label, "kind": "v1_legacy_label",
                                       "last_seen": raw_member.get("last_seen") or ""})
                    existing["aliases"] = aliases[:MAX_ALIASES]
                if (is_new or not int(existing.get("message_count") or 0)) \
                        and raw_member.get("evidence_basis") == "v1_group_aggregate":
                    existing["evidence_basis"] = "v1_group_aggregate"

            edges_added = 0
            for raw_edge in edges:
                if not isinstance(raw_edge, dict):
                    continue
                left, right = _clean(raw_edge.get("a"), 256), _clean(raw_edge.get("b"), 256)
                if not left or not right or left == right or left not in document["members"] or right not in document["members"]:
                    continue
                first, second, edge_id = _edge_key(left, right)
                existing = document["edges"].get(edge_id)
                if not isinstance(existing, dict):
                    existing = {"a": first, "b": second, "count": 0, "tone": "ordinary",
                                "summary": "V1 历史汇总", "last_seen": None,
                                "evidence_basis": "v1_group_aggregate"}
                    document["edges"][edge_id] = existing
                    edges_added += 1
                existing["count"] = max(int(existing.get("count") or 0), int(raw_edge.get("count") or 0))
                if existing.get("evidence_basis") == "v1_group_aggregate":
                    existing["tone"] = raw_edge.get("tone", "ordinary")
                    existing["summary"] = raw_edge.get("summary", "V1 历史汇总")
                    candidate = _when(raw_edge.get("last_seen"))
                    previous = _when(existing.get("last_seen"))
                    if candidate is not None and (previous is None or candidate > previous):
                        existing["last_seen"] = _iso(candidate)
            imports.append(source_key)
            document["legacy_imports"] = imports[-32:]
            document["updated_at"] = _iso(at)
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                               (key, encode(document)))
        return {"imported": True, "duplicate": False,
                "members_added": members_added, "edges_added": edges_added}

    def projection(self, context, *, people=()):
        return project_document(self.read(context), people=people, group_id=context.scope.native_scope_id)

    def projection_for_route(self, installation_id, platform_id, bot_id, account_id, group_id, role_id, *, people=()):
        return project_document(self.read_owner(route_owner_key(installation_id, platform_id, bot_id, account_id,
                                                                group_id, role_id)),
                                people=people, group_id=group_id)

    def capture(self, context, events, *, at):
        material = self.contribution(context, events, at=at)
        return {"version": VERSION, "context_key": context.key,
                "payload": material.payload if material is not None else None}

    @staticmethod
    def validate_snapshot(snapshot, context, *, char_limit=MAX_PROMPT_CHARS):
        if (type(snapshot) is not dict or set(snapshot) != {"version", "context_key", "payload"}
                or snapshot["version"] != VERSION or snapshot["context_key"] != context.key
                or snapshot["payload"] is not None and (type(snapshot["payload"]) is not str
                    or len(snapshot["payload"]) > char_limit)):
            raise TaskError("group_network_snapshot_invalid", "network must retain its original conversation")

    def contribution(self, context, events, *, at, char_limit=MAX_PROMPT_CHARS, snapshot=None):
        if context.scope.kind is not ScopeKind.GROUP:
            return None
        if snapshot is not None:
            self.validate_snapshot(snapshot, context, char_limit=char_limit)
            if snapshot["payload"] is None:
                return None
            return ContextContribution("group-network:" + owner_key(context), "relationships.group",
                                       PURPOSE, ContributionState.READY, snapshot["payload"], None, False)
        document = self.read(context)
        if not document:
            return None
        ids = {str(event.principal.native_account_id) for event in events}
        members = {str(item["native_account_id"]): item for item in project_document(
            document, group_id=context.scope.native_scope_id)["members"]}
        current = [members[account] for account in sorted(ids) if account in members]
        edge_values = []
        for edge in project_document(document, group_id=context.scope.native_scope_id)["edges"]:
            if edge["a"] in ids or edge["b"] in ids:
                edge_values.append(edge)
        if not edge_values:
            edge_values = project_document(document, group_id=context.scope.native_scope_id)["edges"][:MAX_PROMPT_EDGES]
        payload = {"current_members": current[:4], "nearby_interactions": edge_values[:MAX_PROMPT_EDGES],
                   "instruction": "账号是本轮认证归因；名称、熟人卡和互动边只是参考，互动边不代表现实关系。"}
        text = encode(payload)
        if len(text) > char_limit:
            payload["current_members"] = [{"native_account_id": item["native_account_id"],
                                            "display_name": item.get("display_name"),
                                            "acquaintance": item.get("acquaintance")} for item in current[:2]]
            payload["nearby_interactions"] = edge_values[:2]
            text = encode(payload)
        if not text or len(text) > char_limit:
            return None
        return ContextContribution("group-network:" + owner_key(context), "relationships.group",
                                   PURPOSE, ContributionState.READY, text, None, False)


__all__ = ["GroupRelationshipStore", "LINK_WINDOW_SECONDS", "MAX_EDGES", "MAX_MEMBERS", "PURPOSE",
           "VERSION", "attach_member_clues", "fold_event", "metadata_key", "owner_key",
           "project_document", "route_owner_key"]
