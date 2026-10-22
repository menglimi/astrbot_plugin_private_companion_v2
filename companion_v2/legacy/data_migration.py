"""Read-only converters for V1 role journals, reaction assets and summaries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from companion_v2.knowledge.parsing import parse_worldbook
from companion_v2.knowledge.member_profiles import MemberMemory, member_memories
from companion_v2.legacy.profile_source import (
    MAX_PROFILE_DB_BYTES,
    MAX_PROFILE_JSON_BYTES,
    primary_profile,
    read_json as _read_json,
    read_sqlite as _read_persona_sqlite,
)
from companion_v2.legacy.sqlite_snapshot import open_readonly_sqlite_snapshot


MAX_REACTION_ASSETS = 1000
MAX_REACTION_ASSET_BYTES = 5 * 1024 * 1024
MAX_REACTION_BATCH_BYTES = 120 * 1024 * 1024
MAX_JOURNAL_ITEMS = 10000
MAX_JOURNAL_BATCH_ITEMS = 100
MAX_JOURNAL_BATCH_BYTES = 2 * 1024 * 1024
MAX_WORLDBOOK_ITEMS = 5000
MAX_WORLDBOOK_ENTRY_BYTES = 20 * 1024
MAX_WORLDBOOK_BATCH_BYTES = 16 * 1024 * 1024
MAX_GROUP_NETWORK_MEMBERS = 512
MAX_GROUP_NETWORK_EDGES = 512
MAX_REFERENCE_IMAGE_ITEMS = 160
MAX_REFERENCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_IMAGE_BATCH_BYTES = 48 * 1024 * 1024
MAX_WARDROBE_ITEMS = 40
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
OWNED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
REFERENCE_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
REACTION_SOURCE = "private.reaction_assets"
OWNED_REACTION_SOURCE = "private.owned_reaction_assets"
REFERENCE_IMAGE_SOURCE = "private.photo_references"
WARDROBE_SOURCE = "private.wardrobe_items"


@dataclass(frozen=True)
class ReactionAsset:
    relative_path: str
    filename: str
    sha256: str
    size: int
    metadata: dict
    source_id: str = REACTION_SOURCE
    enabled: bool = True

    def document(self) -> dict:
        return {"filename": self.filename, "sha256": self.sha256, "size": self.size,
                "name": self.metadata.get("name", ""), "source_id": self.source_id,
                "enabled": self.enabled}


@dataclass(frozen=True)
class JournalItem:
    kind: str
    local_date: str
    body: str
    summary: str
    afterglow: str
    form: str
    recall: str
    source_id: str
    sha256: str
    dream_fragments: tuple[str, ...] = ()

    @property
    def key(self):
        return self.kind, self.local_date

    @property
    def size(self):
        return len(self.body.encode("utf-8")) + len(self.summary.encode("utf-8")) \
            + len(self.afterglow.encode("utf-8")) + len(self.form.encode("utf-8")) \
            + sum(len(item.encode("utf-8")) for item in self.dream_fragments)

    def document(self) -> dict:
        return {"kind": self.kind, "date": self.local_date, "size": self.size,
                "source_id": self.source_id, "dream_fragment_count": len(self.dream_fragments)}


@dataclass(frozen=True)
class LegacyWorldbookItem:
    index: int
    template: str
    name: str
    gender: str
    enabled: bool
    priority: int
    keywords: tuple[str, ...]
    aliases: tuple[str, ...]
    content: str
    member_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    sha256: str
    source_kind: str = "worldbook_entry"

    @property
    def size(self):
        return len(self.content.encode("utf-8"))

    def document(self) -> dict:
        return {"index": self.index, "template": self.template,
                "enabled": self.enabled, "content_chars": len(self.content),
                "scope_count": len(self.member_ids or self.group_ids),
                "source_id": "private.core_profiles", "source_kind": self.source_kind}


@dataclass(frozen=True)
class LegacyMemberProfile:
    profile_id: str
    name: str
    aliases: tuple[str, ...]
    account_ids: tuple[str, ...]
    gender: str
    content: str
    priority: int
    group_ids: tuple[str, ...]
    enabled: bool
    sha256: str
    identity_note: str = ""
    boundary_note: str = ""
    important_memories: tuple[MemberMemory, ...] = ()

    def document(self) -> dict:
        return {"profile_id": self.profile_id, "scope_count": len(self.group_ids),
                "content_chars": len(self.content), "enabled": self.enabled,
                "source_id": "private.core_profiles.worldbook_member_profiles"}


@dataclass(frozen=True)
class LegacyReferenceImage:
    source_key: str
    source_path: str
    filename: str
    sha256: str
    size: int
    label: str
    roles: tuple[str, ...]

    def document(self) -> dict:
        return {"filename": self.filename, "sha256": self.sha256, "size": self.size,
                "label": self.label, "roles": list(self.roles), "source_id": REFERENCE_IMAGE_SOURCE}


@dataclass(frozen=True)
class LegacyWardrobeItem:
    item_id: str
    source_key: str
    name: str
    description: str
    tags: tuple[str, ...]
    image: LegacyReferenceImage | None = None
    image_reason: str = ""

    def document(self) -> dict:
        return {"item_id": self.item_id, "name": self.name, "description": self.description,
                "tags": list(self.tags), "has_image": self.image is not None,
                "image_reason": self.image_reason, "source_id": WARDROBE_SOURCE}


@dataclass(frozen=True)
class LegacyDataPlan:
    reaction_assets: tuple[ReactionAsset, ...]
    reaction_rejected: tuple[dict, ...]
    group_networks: tuple[dict, ...]
    journals: tuple[JournalItem, ...]
    journal_rejected: tuple[dict, ...]
    worldbook_items: tuple[LegacyWorldbookItem, ...]
    worldbook_rejected: tuple[dict, ...]
    member_profiles: tuple[LegacyMemberProfile, ...]
    member_profile_rejected: tuple[dict, ...]
    persona_sources: tuple[dict, ...]
    source_persona_id: str
    profile_summary: dict
    work_delivery: dict
    world_assets: dict
    source_fingerprint: str
    warnings: tuple[str, ...]
    reference_images: tuple[LegacyReferenceImage, ...] = ()
    reference_image_rejected: tuple[dict, ...] = ()
    wardrobe_items: tuple[LegacyWardrobeItem, ...] = ()
    wardrobe_rejected: tuple[dict, ...] = ()
    expression_profiles: tuple[dict, ...] = ()

    def document(self, *, source_group_id="", existing_reaction_ids=(),
                 existing_journal_heads=None, existing_reference_hashes=(),
                 existing_wardrobe_ids=(), reference_slots_available=0,
                 wardrobe_slots_available=0, reference_bytes_available=MAX_REFERENCE_IMAGE_BYTES * 24) -> dict:
        existing = set(existing_reaction_ids)
        ready_reactions = [item for item in self.reaction_assets if item.sha256 not in existing]
        reaction_batch = next_reaction_batch(self, existing)
        heads = existing_journal_heads or {}
        journal_batch = next_journal_batch(self, heads)
        retryable_derivatives = {item.key for item in self.journals
            if item.key in heads and item.dream_fragments
            and heads[item.key].get("state") == "active"
            and heads[item.key].get("imported") is True
            and heads[item.key].get("derivatives_imported") is not True
            and heads[item.key].get("derivatives_conflict") is not True}
        journal_conflicts = [item for item in self.journals
                             if item.key in heads and item.key not in retryable_derivatives]
        ready_journals = [item for item in self.journals
                          if item.key not in heads or item.key in retryable_derivatives]
        networks = list(self.group_networks)
        selected = next((item for item in networks if item["source_group_id"] == str(source_group_id)), None)
        general_worldbook = [item for item in self.worldbook_items
                             if item.template not in ("user", "group")]
        member_worldbook = [item for item in self.worldbook_items
                            if item.member_ids and item.enabled]
        base_member_profiles = [item for item in self.member_profiles
                                if item.enabled and not item.group_ids]
        mapped_members = map_legacy_worldbook(self, confirm_member_ids=True)[1]
        selected_group_member_profiles = [item for item in self.member_profiles
                                          if item.enabled and str(source_group_id) in item.group_ids]
        disabled_member_count = sum(bool(item.member_ids) and not item.enabled
                                    for item in self.worldbook_items) + sum(
                                        not item.enabled for item in self.member_profiles)
        group_worldbook = [item for item in self.worldbook_items
                           if str(source_group_id) and str(source_group_id) in item.group_ids]
        group_member_profile_count = sum(item.enabled and bool(item.group_ids)
                                         for item in self.member_profiles)
        group_member_profile_scopes = {}
        for item in self.member_profiles:
            if not item.enabled:
                continue
            for group_id in item.group_ids:
                group_member_profile_scopes[group_id] = group_member_profile_scopes.get(group_id, 0) + 1
        worldbook_groups = {}
        for item in self.worldbook_items:
            for group_id in item.group_ids:
                worldbook_groups[group_id] = worldbook_groups.get(group_id, 0) + 1
        conflict_dates = [{"kind": item.kind, "date": item.local_date,
                           "state": heads[item.key].get("state", "unknown"),
                           "imported": bool(heads[item.key].get("imported")),
                           "content_matches": bool(heads[item.key].get("content_matches"))}
                          for item in journal_conflicts[:30]]
        reference_hashes = set(existing_reference_hashes)
        wardrobe_ids = set(existing_wardrobe_ids)
        reference_sources = {item.sha256: item for item in self.reference_images}
        for wardrobe in self.wardrobe_items:
            if wardrobe.image is not None:
                previous = reference_sources.get(wardrobe.image.sha256)
                reference_sources[wardrobe.image.sha256] = (wardrobe.image if previous is None else
                    replace(previous, roles=tuple(dict.fromkeys((*previous.roles, *wardrobe.image.roles)))))
        ready_references = [item for item in reference_sources.values()
                            if item.sha256 not in reference_hashes]
        ready_wardrobe = [item for item in self.wardrobe_items if item.item_id not in wardrobe_ids]
        wardrobe_batch = ready_wardrobe[:max(0, min(len(ready_wardrobe), int(wardrobe_slots_available)))]
        wardrobe_image_hashes = {item.image.sha256 for item in wardrobe_batch if item.image is not None}
        reference_batch = next_reference_image_batch(
            ready_references, slots_available=reference_slots_available,
            bytes_available=reference_bytes_available, priority_hashes=wardrobe_image_hashes)
        usable_image_hashes = reference_hashes | {item.sha256 for item in reference_batch}
        return {
            "source_fingerprint": self.source_fingerprint,
            "source_persona_id": self.source_persona_id,
            "persona_sources": list(self.persona_sources),
            "selected_persona": next((item for item in self.persona_sources
                                       if item["persona_id"] == self.source_persona_id), None),
            "reaction_assets": {
                "total": len(self.reaction_assets) + len(self.reaction_rejected),
                "ready": len(ready_reactions),
                "already_present": len(existing.intersection(item.sha256 for item in self.reaction_assets)),
                "batch_count": len(reaction_batch),
                "batch_bytes": sum(item.size for item in reaction_batch),
                "remaining_after_batch": max(0, len(ready_reactions) - len(reaction_batch)),
                "rejected": list(self.reaction_rejected[:100]),
                "samples": [item.document() for item in ready_reactions[:12]],
            },
            "journals": {
                "total": len(self.journals) + len(self.journal_rejected),
                "ready": len(ready_journals),
                "already_present": len(journal_conflicts),
                "identical_count": sum(bool(heads[item.key].get("content_matches"))
                                       for item in journal_conflicts),
                "batch_count": len(journal_batch),
                "batch_bytes": sum(item.size for item in journal_batch),
                "remaining_after_batch": max(0, len(ready_journals) - len(journal_batch)),
                "derivative_retry_count": len(retryable_derivatives),
                "conflicts": conflict_dates,
                "rejected": list(self.journal_rejected[:100]),
                "samples": [item.document() for item in ready_journals[:20]],
            },
            "worldbook": {
                "total": len(self.worldbook_items) + len(self.worldbook_rejected),
                "general_count": len(general_worldbook),
                "member_count": len(mapped_members),
                "member_entry_count": len(member_worldbook),
                "member_profile_count": len(base_member_profiles),
                "important_memory_count": sum(len(item.important_memories)
                    for item in (*base_member_profiles, *selected_group_member_profiles)),
                "selected_group_member_profile_count": len(selected_group_member_profiles),
                "group_profile_count": sum(item.source_kind == "group_profile" for item in self.worldbook_items),
                "group_member_profile_count": group_member_profile_count,
                "selected_group_member_count": len(selected_group_member_profiles),
                "disabled_member_count": disabled_member_count,
                "group_count": sum(worldbook_groups.values()),
                "selected_group_entry_count": len(group_worldbook),
                "available_count": len(general_worldbook) + len(mapped_members) + len(group_worldbook)
                    + len(selected_group_member_profiles),
                "selected_group_id": str(source_group_id),
                "groups": [{"source_group_id": group_id, "entry_count": count}
                           for group_id, count in sorted(worldbook_groups.items())],
                "member_profile_groups": [{"source_group_id": group_id, "member_count": count}
                    for group_id, count in sorted(group_member_profile_scopes.items())],
                "requires_id_confirmation": bool(mapped_members or group_worldbook
                                                  or selected_group_member_profiles),
                "rejected": list(self.worldbook_rejected[:100]),
                "member_profiles_rejected": list(self.member_profile_rejected[:100]),
                "samples": [item.document() for item in self.worldbook_items[:20]],
            },
            "member_profiles": {"total": len(self.member_profiles) + len(self.member_profile_rejected),
                "ready": sum(item.enabled for item in self.member_profiles),
                "base_ready": len(base_member_profiles),
                "selected_group_ready": len(selected_group_member_profiles),
                "rejected": list(self.member_profile_rejected[:100]),
                "samples": [item.document() for item in self.member_profiles[:12]]},
            "reference_images": {
                "total": len(reference_sources) + len(self.reference_image_rejected),
                "ready": len(ready_references),
                "already_present": sum(item.sha256 in reference_hashes for item in reference_sources.values()),
                "batch_count": len(reference_batch),
                "batch_bytes": sum(item.size for item in reference_batch),
                "remaining_after_batch": max(0, len(ready_references) - len(reference_batch)),
                "rejected": list(self.reference_image_rejected[:100]),
                "samples": [item.document() for item in ready_references[:12]],
            },
            "wardrobe_items": {
                "total": len(self.wardrobe_items) + len(self.wardrobe_rejected),
                "ready": len(ready_wardrobe),
                "already_present": sum(item.item_id in wardrobe_ids for item in self.wardrobe_items),
                "batch_count": len(wardrobe_batch),
                "remaining_after_batch": max(0, len(ready_wardrobe) - len(wardrobe_batch)),
                "image_count": sum(item.image is not None and item.image.sha256 in usable_image_hashes
                                    for item in wardrobe_batch),
                "image_skipped_count": sum(bool(item.image_reason)
                    or (item.image is not None and item.image.sha256 not in usable_image_hashes)
                    for item in wardrobe_batch),
                "rejected": list(self.wardrobe_rejected[:100]),
                "samples": [item.document() for item in ready_wardrobe[:12]],
            },
            "profile_data": dict(self.profile_summary),
            "work_delivery": dict(self.work_delivery),
            "world_assets": dict(self.world_assets),
            "group_networks": [{key: value for key, value in item.items() if key not in ("members", "edges")}
                                for item in networks],
            "selected_group": ({key: value for key, value in selected.items()
                                if key not in ("members", "edges")} if selected else None),
            "warnings": list(self.warnings),
        }


def next_reaction_batch(plan: LegacyDataPlan, existing_ids=()) -> tuple[ReactionAsset, ...]:
    existing = set(existing_ids)
    selected = []
    size = 0
    for item in plan.reaction_assets:
        if item.sha256 in existing:
            continue
        if len(selected) >= MAX_REACTION_ASSETS or size + item.size > MAX_REACTION_BATCH_BYTES:
            break
        selected.append(item)
        size += item.size
    return tuple(selected)


def next_journal_batch(plan: LegacyDataPlan, existing_keys=()) -> tuple[JournalItem, ...]:
    existing = existing_keys if isinstance(existing_keys, dict) else set(existing_keys)
    selected = []
    size = 0
    for item in plan.journals:
        if isinstance(existing, dict):
            head = existing.get(item.key)
            if head is not None:
                retry_derivatives = (bool(item.dream_fragments)
                    and head.get("state") == "active" and head.get("imported") is True
                    and head.get("derivatives_imported") is not True
                    and head.get("derivatives_conflict") is not True)
                if not retry_derivatives:
                    continue
        elif item.key in existing:
            continue
        if len(selected) >= MAX_JOURNAL_BATCH_ITEMS or size + item.size > MAX_JOURNAL_BATCH_BYTES:
            break
        selected.append(item)
        size += item.size
    return tuple(selected)


def next_reference_image_batch(items, *, slots_available,
                               bytes_available=MAX_REFERENCE_IMAGE_BYTES * 24,
                               priority_hashes=()):
    priorities = set(priority_hashes)
    items = sorted(items, key=lambda item: (item.sha256 not in priorities,))
    selected, size = [], 0
    for item in items:
        if len(selected) >= max(0, min(MAX_REFERENCE_IMAGE_ITEMS, int(slots_available))):
            break
        if (size + item.size > MAX_REFERENCE_IMAGE_BATCH_BYTES
                or size + item.size > max(0, int(bytes_available))):
            break
        selected.append(item)
        size += item.size
    return tuple(selected)


def map_legacy_worldbook(plan: LegacyDataPlan, *, source_group_id="", confirm_member_ids=False,
                         include_group=False):
    """Map reviewed V1 worldbook rows into V2 knowledge documents without identity inference."""
    from companion_v2.knowledge.catalog import EntryDocument, MemberEntry

    entries, members, group_entries, group_members = [], [], [], []
    for item in plan.worldbook_items:
        identifier = f"v1-worldbook-{item.index}-{item.sha256[:16]}"
        if item.member_ids:
            if confirm_member_ids and item.enabled:
                members.append(MemberEntry(identifier, name=item.name, aliases=item.aliases,
                    declared_account_ids=item.member_ids, gender=item.gender,
                    content=item.content, priority=item.priority))
            continue
        if item.group_ids:
            if include_group and confirm_member_ids and str(source_group_id) in item.group_ids:
                group_entries.append(EntryDocument(identifier, item.content, name=item.name,
                    gender=item.gender, priority=item.priority, enabled=item.enabled,
                    keywords=item.keywords, aliases=item.aliases, template=item.template))
            continue
        if item.template in ("user", "group"):
            continue
        entries.append(EntryDocument(identifier, item.content, name=item.name, gender=item.gender,
            priority=item.priority, enabled=item.enabled, keywords=item.keywords,
            aliases=item.aliases, template=item.template))
    if confirm_member_ids:
        for item in plan.member_profiles:
            if not item.enabled:
                continue
            if item.group_ids:
                if not include_group or str(source_group_id) not in item.group_ids:
                    continue
                group_members.append(MemberEntry("v1-member-profile-" + item.profile_id,
                    name=item.name, aliases=item.aliases, declared_account_ids=item.account_ids,
                    gender=item.gender, content=item.content, priority=item.priority,
                    group_ids=(str(source_group_id),), identity_note=item.identity_note,
                    boundary_note=item.boundary_note, important_memories=item.important_memories))
            else:
                members.append(MemberEntry("v1-member-profile-" + item.profile_id,
                    name=item.name, aliases=item.aliases, declared_account_ids=item.account_ids,
                    gender=item.gender, content=item.content, priority=item.priority,
                    identity_note=item.identity_note, boundary_note=item.boundary_note,
                    important_memories=item.important_memories))
    return tuple(entries), _merge_worldbook_members(members), tuple(group_entries), tuple(group_members)


def _merge_worldbook_members(members):
    """Several V1 source entries for one account are one relationship node."""
    from companion_v2.knowledge.catalog import MemberEntry

    by_account, without_account = {}, []
    for member in members:
        if not member.declared_account_ids:
            without_account.append(member)
        for account in member.declared_account_ids:
            by_account.setdefault(account, []).append(member)
    result = list(without_account)
    for account, rows in by_account.items():
        if len(rows) == 1 and len(rows[0].declared_account_ids) == 1:
            result.append(rows[0])
            continue
        rows.sort(key=lambda row: (-row.priority, row.entry_id))
        chosen = rows[0]
        result.append(MemberEntry("v1-member-account-" + hashlib.sha256(account.encode("utf-8")).hexdigest()[:24],
            name=chosen.name, aliases=tuple(dict.fromkeys(label for row in rows for label in row.labels)),
            declared_account_ids=(account,), gender=chosen.gender,
            content="\n".join(dict.fromkeys(row.content for row in rows if row.content)),
            priority=chosen.priority, identity_note=chosen.identity_note, boundary_note=chosen.boundary_note,
            important_memories=tuple(memory for row in rows for memory in row.important_memories)))
    return tuple(result)


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _safe_relative(root: Path, base: Path, relative_name, *, allow_subdirs):
    raw = str(relative_name or "").replace("\\", "/")
    parts = raw.split("/")
    if (not raw or raw.startswith("/") or ":" in raw or any(part in ("", ".", "..") for part in parts)
            or (not allow_subdirs and len(parts) != 1)):
        return None, "invalid_filename"
    base = base.resolve()
    try:
        base.relative_to(root.resolve())
    except ValueError:
        return None, "image_path_outside_library"
    candidate = base.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
        info = candidate.lstat()
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or int(getattr(info, "st_file_attributes", 0)) & reparse):
            return None, "image_unreadable"
        current = base
        for part in parts[:-1]:
            current = current / part
            directory_info = current.lstat()
            if (stat.S_ISLNK(directory_info.st_mode)
                    or int(getattr(directory_info, "st_file_attributes", 0)) & reparse):
                return None, "image_path_outside_library"
        return resolved, ""
    except FileNotFoundError:
        return None, "image_missing"
    except (OSError, ValueError):
        return None, "image_path_outside_library"


def _load_image(root: Path, base_name: str, stored_name, *, source_id, allow_subdirs=False,
                extensions=SUPPORTED_IMAGE_EXTENSIONS, max_bytes=MAX_REACTION_ASSET_BYTES):
    base = root / base_name
    path, reason = _safe_relative(root, base, stored_name, allow_subdirs=allow_subdirs)
    if reason:
        return None, reason
    if path.suffix.lower() not in extensions:
        return None, "unsupported_image_type"
    try:
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            return None, "target_image_limit"
        content = path.read_bytes()
        if len(content) != size:
            return None, "image_changed_during_read"
    except OSError:
        return None, "image_unreadable"
    return (path, content), ""


def _reaction_assets(root: Path):
    catalog_path = root / "reaction_expression_library" / "catalog.json"
    if not catalog_path.is_file():
        return (), (), ["没有找到 V1 表情素材目录。"]
    catalog = _read_json(catalog_path)
    if (not isinstance(catalog, dict) or catalog.get("version") not in (1, 2)
            or not isinstance(catalog.get("items"), list)):
        return (), ({"filename": "catalog.json", "reason": "catalog_invalid"},), ["V1 表情目录结构无法识别。"]
    accepted, rejected, seen = [], [], set()
    for index, raw in enumerate(catalog["items"][:MAX_REACTION_ASSETS + 1]):
        if index >= MAX_REACTION_ASSETS:
            rejected.append({"filename": "…", "reason": "asset_count_limit"})
            break
        if not isinstance(raw, dict):
            rejected.append({"filename": str(index + 1), "reason": "item_invalid"})
            continue
        name = raw.get("stored_name") or raw.get("filename")
        loaded, reason = _load_image(root, "reaction_expression_library/images", name,
                                     source_id=REACTION_SOURCE)
        filename = Path(str(raw.get("filename") or name or index)).name[:160]
        if reason:
            rejected.append({"filename": filename, "reason": reason})
            continue
        path, content = loaded
        digest = hashlib.sha256(content).hexdigest()
        expected = str(raw.get("sha256") or "").lower()
        if expected and expected != digest:
            rejected.append({"filename": filename, "reason": "catalog_hash_mismatch"})
            continue
        if digest in seen:
            continue
        seen.add(digest)
        metadata = {
            "name": _clean(raw.get("name") or Path(filename).stem, 100),
            "description": _clean(raw.get("description"), 1200),
            "visible_text": _clean(raw.get("visible_text"), 500),
            "tags": _clean_list(raw.get("tags"), 20),
            "emotions": _clean_list(raw.get("emotions"), 12),
            "intents": _clean_list(raw.get("intents"), 12),
        }
        accepted.append(ReactionAsset(str(path.relative_to(root)), filename, digest,
                                      len(content), metadata, REACTION_SOURCE,
                                      raw.get("enabled") is not False))
    return tuple(accepted), tuple(rejected), []


def _clean_list(value, limit):
    values = value if isinstance(value, (list, tuple)) else re.split(r"[,，;；|\n]+", str(value or ""))
    result, seen = [], set()
    for item in values:
        text = _clean(item, 80)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _persona_id_from_filename(filename):
    try:
        value = unquote(filename, encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        return ""
    value = unicodedata.normalize("NFC", value)
    value = "".join(char for char in value if unicodedata.category(char) not in {"Cc", "Cs"}).strip()
    if "/" in value or "\\" in value:
        return ""
    return value[:96]


def _persona_sources(root: Path, primary):
    result = [primary.document(root)]
    directory = root / "persona_profiles"
    try:
        directory_info = directory.lstat()
    except FileNotFoundError:
        return tuple(result), []
    except OSError:
        return tuple(result), ["V1 persona_profiles 目录无法检查。"]
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (not stat.S_ISDIR(directory_info.st_mode) or stat.S_ISLNK(directory_info.st_mode)
            or int(getattr(directory_info, "st_file_attributes", 0)) & reparse):
        return tuple(result), ["V1 persona_profiles 目录不是普通目录，已跳过。"]
    grouped = {}
    warnings = []
    try:
        children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return tuple(result), ["V1 persona_profiles 目录无法读取。"]
    for child in children:
        suffix = child.suffix.lower()
        if suffix not in (".json", ".db"):
            continue
        persona_id = _persona_id_from_filename(child.name[:-len(suffix)])
        if not persona_id:
            warnings.append("有一个次要人格档案名无法解码，已跳过。")
            continue
        grouped.setdefault(persona_id, []).append(child)
    for persona_id, paths in sorted(grouped.items(), key=lambda item: item[0].casefold()):
        formats = {path.suffix.lower() for path in paths}
        state = "ambiguous" if len(paths) != 1 or len(formats) != 1 else "ready"
        result.append({"persona_id": persona_id, "label": f"V1 人格：{persona_id}",
                       "format": next(iter(formats)) if len(formats) == 1 else "mixed",
                       "state": state})
    return tuple(result), warnings


def _selected_profile(root: Path, persona_id: str, persona_sources, primary):
    if not persona_id:
        return primary.payload, primary.error, primary.selected_path(root)
    info = next((item for item in persona_sources if item["persona_id"] == persona_id), None)
    if info is None or info["state"] == "absent":
        return None, "persona_profile_missing", ""
    if info["state"] != "ready":
        return None, "persona_profile_ambiguous", ""
    directory = root / "persona_profiles"
    candidates = [directory / (child.name) for child in directory.iterdir()
                  if child.suffix.lower() in (".json", ".db")
                  and _persona_id_from_filename(child.name[:-len(child.suffix)]) == persona_id]
    if len(candidates) != 1:
        return None, "persona_profile_ambiguous", ""
    path = candidates[0]
    if path.suffix.lower() == ".json":
        payload = _read_json(path, max_bytes=MAX_PROFILE_JSON_BYTES)
        return (payload, "", str(path.relative_to(root))) if isinstance(payload, dict) \
            else (None, "persona_profile_unreadable", "")
    payload, reason = _read_persona_sqlite(path)
    return payload, reason, str(path.relative_to(root)) if payload is not None else ""


def _profile_data(payload):
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("data")
    if isinstance(nested, dict) and not any(key in payload for key in ("bot_diaries", "daily_dream", "groups")):
        return nested
    return payload


def _date_key(value):
    if not isinstance(value, str):
        return ""
    match = re.match(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", value)
    if not match:
        return ""
    try:
        return date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:
        return ""


def _journal_items(payload, source_persona_id):
    data = _profile_data(payload)
    accepted, rejected, counts = [], [], {}
    deleted_days = data.get("daily_diary_deleted_days")
    deleted = {_date_key(value) for value in deleted_days} if isinstance(deleted_days, list) else set()
    raw_diaries = data.get("bot_diaries") if isinstance(data.get("bot_diaries"), list) else []
    fragments_by_day = {}
    fragment_bytes = 0

    def add_fragment(day, raw, *, kind):
        nonlocal fragment_bytes
        text = raw.get("text") if isinstance(raw, dict) else raw
        if not day:
            rejected.append({"kind": kind, "reason": "dream_fragment_date_invalid"})
            return
        if day in deleted:
            rejected.append({"kind": kind, "date": day, "reason": "source_day_deleted"})
            return
        if type(text) is not str or not text.strip() or len(text) > 8192:
            rejected.append({"kind": kind, "date": day, "reason": "dream_fragment_invalid"})
            return
        size = len(text.encode("utf-8"))
        if fragment_bytes + size > MAX_JOURNAL_BATCH_BYTES:
            rejected.append({"kind": kind, "date": day, "reason": "dream_fragment_batch_limit"})
            return
        fragment_bytes += size
        values = fragments_by_day.setdefault(day, [])
        if text not in values:
            values.append(text)

    for raw in raw_diaries[:MAX_JOURNAL_ITEMS]:
        if not isinstance(raw, dict):
            continue
        day = _date_key(raw.get("date"))
        values = raw.get("dream_fragments")
        if isinstance(values, list):
            for fragment in values[:64]:
                add_fragment(day, fragment, kind="diary_dream_fragment")
    raw_fragments = data.get("dream_fragments") if isinstance(data.get("dream_fragments"), list) else []
    for raw in raw_fragments[:MAX_JOURNAL_ITEMS]:
        day = _date_key(raw.get("date")) if isinstance(raw, dict) else ""
        add_fragment(day, raw, kind="dream_fragment")
    if len(raw_fragments) > MAX_JOURNAL_ITEMS:
        rejected.append({"kind": "dream_fragment", "reason": "journal_count_limit",
                         "count": len(raw_fragments) - MAX_JOURNAL_ITEMS})

    if len(raw_diaries) > MAX_JOURNAL_ITEMS:
        rejected.append({"kind": "diary", "reason": "journal_count_limit",
                         "count": len(raw_diaries) - MAX_JOURNAL_ITEMS})
    for raw in raw_diaries[:MAX_JOURNAL_ITEMS]:
        if not isinstance(raw, dict):
            rejected.append({"kind": "diary", "reason": "diary_entry_invalid"})
            continue
        day = _date_key(raw.get("date"))
        body = raw.get("body")
        if not day:
            rejected.append({"kind": "diary", "reason": "diary_date_invalid"})
            continue
        if day in deleted:
            rejected.append({"kind": "diary", "date": day, "reason": "source_day_deleted"})
            continue
        if type(body) is not str or not body.strip() or len(body) > 65536:
            rejected.append({"kind": "diary", "date": day, "reason": "diary_body_invalid"})
            continue
        summary = raw.get("summary") if type(raw.get("summary")) is str else ""
        fragments = tuple(fragments_by_day.get(day, ()))
        material = {"kind": "diary", "date": day, "body": body,
                    "summary": summary[:8192], "dream_fragments": fragments,
                    "persona_id": source_persona_id}
        accepted.append(JournalItem("diary", day, body, summary[:8192], "", "V1 导入", "",
                                    "private.core_profiles",
                                    hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode("utf-8")).hexdigest(),
                                    fragments))
        counts["diary", day] = counts.get(("diary", day), 0) + 1
    dream = data.get("daily_dream")
    if isinstance(dream, dict):
        day = _date_key(dream.get("date"))
        body = dream.get("content") if type(dream.get("content")) is str else ""
        afterglow = dream.get("afterglow") if type(dream.get("afterglow")) is str else ""
        label = _clean(dream.get("label"), 120)
        if label != "没有记住梦" and (body.strip() or afterglow.strip()):
            if not day:
                rejected.append({"kind": "dream", "reason": "dream_date_invalid"})
            elif len(body) > 65536 or len(afterglow) > 8192:
                rejected.append({"kind": "dream", "date": day, "reason": "dream_body_too_large"})
            else:
                material = {"kind": "dream", "date": day, "body": body,
                            "afterglow": afterglow, "persona_id": source_persona_id}
                accepted.append(JournalItem("dream", day, body, label, afterglow,
                    _clean(dream.get("dream_type"), 256) or "V1 导入", "full" if body.strip() else "afterglow",
                    "private.core_profiles",
                    hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode("utf-8")).hexdigest()))
                counts["dream", day] = counts.get(("dream", day), 0) + 1

    diary_days = {item.local_date for item in accepted if item.kind == "diary"}
    for day, fragments in fragments_by_day.items():
        if day in diary_days:
            continue
        existing_dream = next((index for index, item in enumerate(accepted)
                               if item.kind == "dream" and item.local_date == day), None)
        if existing_dream is not None:
            item = accepted[existing_dream]
            material = {"kind": item.kind, "date": day, "body": item.body,
                        "afterglow": item.afterglow, "dream_fragments": tuple(fragments),
                        "persona_id": source_persona_id}
            accepted[existing_dream] = replace(item, dream_fragments=tuple(fragments),
                sha256=hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest())
            continue
        body = "\n".join(fragments)
        material = {"kind": "dream", "date": day, "body": body,
                    "dream_fragments": tuple(fragments), "persona_id": source_persona_id}
        accepted.append(JournalItem("dream", day, body, "", "", "V1 梦境片段", "fragments",
            "private.core_profiles", hashlib.sha256(json.dumps(material, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()))
        counts["dream", day] = counts.get(("dream", day), 0) + 1
    duplicated = {key for key, count in counts.items() if count > 1}
    if duplicated:
        kept = []
        for item in accepted:
            if item.key in duplicated:
                rejected.append({"kind": item.kind, "date": item.local_date,
                                 "reason": "duplicate_source_day"})
            else:
                kept.append(item)
        accepted = kept
    accepted.sort(key=lambda item: (item.local_date, item.kind))
    return tuple(accepted), tuple(rejected)


def _legacy_group_id(value):
    text = _clean(value, 512)
    marker = re.search(r":groupmessage:", text, re.IGNORECASE)
    if marker:
        text = _clean(text[marker.end():], 256)
    elif ":" in text:
        return ""
    if not text or ":" in text:
        return ""
    if text.casefold() in {"default", "aiocqhttp", "qq_official", "group", "groupmessage",
                           "friendmessage", "umo", "uid", "none", "null"}:
        return ""
    return text[:256]


def _worldbook_items(payload):
    data = _profile_data(payload)
    raw_items = data.get("worldbook_entries") if isinstance(data.get("worldbook_entries"), list) else []
    profiles = data.get("worldbook_member_profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    represented = {str(value).strip() for key, raw in profiles.items() if isinstance(raw, dict)
                   for value in (key, raw.get("user_id") or key)}
    raw_deleted = data.get("worldbook_deleted_member_ids")
    deleted = {str(value).strip() for value in raw_deleted} if isinstance(raw_deleted, list) else set()
    accepted, rejected = [], []
    total_bytes = 0
    for index, raw in enumerate(raw_items[:MAX_WORLDBOOK_ITEMS]):
        parsed = parse_worldbook([raw])
        if not parsed.items:
            rejected.append({"index": index, "reason": "entry_invalid"})
            continue
        item = parsed.items[0]
        if not item.content.strip():
            rejected.append({"index": index, "reason": "entry_content_missing"})
            continue
        if len(item.content.encode("utf-8")) > MAX_WORLDBOOK_ENTRY_BYTES:
            rejected.append({"index": index, "reason": "entry_too_large"})
            continue
        member_ids, group_ids = (), ()
        if item.template == "user":
            if not item.scope:
                rejected.append({"index": index, "reason": "member_scope_missing"})
                continue
            if any(not re.fullmatch(r"[0-9]{1,64}", value) for value in item.scope):
                rejected.append({"index": index, "reason": "member_scope_unmapped"})
                continue
            member_ids = tuple(dict.fromkeys(item.scope))
            member_ids = tuple(value for value in member_ids if value not in represented and value not in deleted)
            if not member_ids:
                rejected.append({"index": index, "reason": "member_profile_preferred_or_deleted"})
                continue
        elif item.template == "group":
            if not item.scope:
                rejected.append({"index": index, "reason": "group_scope_missing"})
                continue
            normalized = tuple(_legacy_group_id(value) for value in item.scope)
            if any(not value for value in normalized):
                rejected.append({"index": index, "reason": "group_scope_invalid"})
                continue
            group_ids = tuple(dict.fromkeys(normalized))
        elif item.scope:
            rejected.append({"index": index, "reason": "unsupported_scoped_template"})
            continue
        normalized = {"template": item.template, "name": item.name, "gender": item.gender,
            "enabled": item.enabled, "priority": item.priority, "keywords": item.keywords,
            "aliases": item.aliases, "content": item.content, "member_ids": member_ids,
            "group_ids": group_ids}
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        size = len(item.content.encode("utf-8"))
        if total_bytes + size > MAX_WORLDBOOK_BATCH_BYTES:
            rejected.append({"index": index, "reason": "worldbook_batch_bytes_limit"})
            continue
        total_bytes += size
        accepted.append(LegacyWorldbookItem(index, item.template, item.name, item.gender,
            item.enabled, item.priority, tuple(item.keywords), tuple(item.aliases), item.content,
            member_ids, group_ids, hashlib.sha256(encoded).hexdigest()))
    if len(raw_items) > MAX_WORLDBOOK_ITEMS:
        rejected.append({"index": MAX_WORLDBOOK_ITEMS, "reason": "worldbook_count_limit",
                         "count": len(raw_items) - MAX_WORLDBOOK_ITEMS})
    return tuple(accepted), tuple(rejected)


def _group_profile_items(payload):
    data = _profile_data(payload)
    profiles = data.get("worldbook_group_profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    deleted = {_legacy_group_id(value) for value in data.get("worldbook_deleted_group_ids", ())
               if isinstance(data.get("worldbook_deleted_group_ids"), list)}
    accepted, rejected = [], []
    total_bytes = 0
    for index, (key, raw) in enumerate(sorted(profiles.items(), key=lambda item: str(item[0]))):
        if index >= MAX_WORLDBOOK_ITEMS:
            rejected.append({"reason": "group_profile_count_limit",
                             "count": len(profiles) - MAX_WORLDBOOK_ITEMS})
            break
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "group_profile_invalid"})
            continue
        group_id = _legacy_group_id(raw.get("group_id") or key)
        if not group_id:
            rejected.append({"index": index, "reason": "group_profile_scope_invalid"})
            continue
        if group_id in deleted:
            rejected.append({"index": index, "reason": "group_profile_deleted"})
            continue
        content = raw.get("content")
        if type(content) is not str or not content.strip():
            rejected.append({"index": index, "reason": "group_profile_content_missing"})
            continue
        size = len(content.encode("utf-8"))
        if size > MAX_WORLDBOOK_ENTRY_BYTES:
            rejected.append({"index": index, "reason": "group_profile_too_large"})
            continue
        if total_bytes + size > MAX_WORLDBOOK_BATCH_BYTES:
            rejected.append({"index": index, "reason": "worldbook_batch_bytes_limit"})
            continue
        enabled = raw.get("enabled", True)
        if type(enabled) is not bool:
            rejected.append({"index": index, "reason": "group_profile_enabled_invalid"})
            continue
        priority = raw.get("priority", 100)
        if type(priority) is not int:
            priority = 100
        normalized = {"group_id": group_id, "name": _clean(raw.get("name"), 120),
            "enabled": enabled, "priority": priority, "content": content.strip()}
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        total_bytes += size
        accepted.append(LegacyWorldbookItem(MAX_WORLDBOOK_ITEMS + index, "group",
            normalized["name"], "", enabled, priority, (), (), content.strip(), (),
            (group_id,), hashlib.sha256(encoded).hexdigest(), "group_profile"))
    return tuple(accepted), tuple(rejected)


def _member_profiles(payload):
    data = _profile_data(payload)
    profiles = data.get("worldbook_member_profiles")
    profiles = profiles if isinstance(profiles, dict) else {}
    deleted = {str(value) for value in data.get("worldbook_deleted_member_ids", ())
               if isinstance(data.get("worldbook_deleted_member_ids"), list)}
    accepted, rejected = [], []
    total_bytes = 0
    for index, (key, raw) in enumerate(sorted(profiles.items(), key=lambda item: str(item[0]))):
        if index >= MAX_WORLDBOOK_ITEMS:
            rejected.append({"reason": "member_profile_count_limit",
                             "count": len(profiles) - MAX_WORLDBOOK_ITEMS})
            break
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "member_profile_invalid"})
            continue
        user_id = _clean(raw.get("user_id") or key, 64)
        if not user_id or user_id in deleted:
            rejected.append({"index": index, "reason": "member_profile_deleted_or_unidentified"})
            continue
        if raw.get("merged_into_user_id"):
            rejected.append({"index": index, "reason": "member_profile_merged"})
            continue
        enabled = raw.get("enabled", True)
        if type(enabled) is not bool:
            rejected.append({"index": index, "reason": "member_profile_enabled_invalid"})
            continue
        raw_groups = raw.get("group_observation_scope_ids")
        raw_groups = raw_groups if isinstance(raw_groups, list) else []
        group_ids = tuple(dict.fromkeys(group for group in
            (_legacy_group_id(value) for value in raw_groups) if group))
        if raw.get("projection_kind") == "group_observation" and not group_ids:
            rejected.append({"index": index, "reason": "member_profile_group_scope_missing"})
            continue
        if len(raw_groups) != len(group_ids):
            rejected.append({"index": index, "reason": "member_profile_group_scope_partial"})
        name = _clean(raw.get("name"), 120)
        raw_aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        observed_names = raw.get("observed_names") if isinstance(raw.get("observed_names"), list) else []
        aliases = tuple(dict.fromkeys(text for text in
            (_clean(value, 120) for value in (*raw_aliases, *observed_names)) if text))[:32]
        content = raw.get("content").strip() if isinstance(raw.get("content"), str) else ""
        identity = raw.get("identity_note") or raw.get("note") or ""
        identity = identity.strip() if isinstance(identity, str) else ""
        note = raw.get("note")
        if isinstance(note, str) and note.strip() and note.strip() not in (content, identity):
            identity = "\n".join(value for value in (identity, "补充备注：" + note.strip()) if value)
        boundary = raw.get("boundary_note")
        boundary = boundary.strip() if isinstance(boundary, str) else ""
        memories = member_memories(raw.get("important_memories"))
        size = len(json.dumps([content, identity, boundary, [m.document for m in memories]],
                              ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > MAX_WORLDBOOK_ENTRY_BYTES:
            rejected.append({"index": index, "reason": "member_profile_too_large"})
            continue
        if total_bytes + size > MAX_WORLDBOOK_BATCH_BYTES:
            rejected.append({"index": index, "reason": "worldbook_batch_bytes_limit"})
            continue
        account_ids = (user_id,) if re.fullmatch(r"[0-9]{1,64}", user_id) else ()
        gender = _clean(raw.get("gender"), 40)
        priority = raw.get("priority", 100)
        if type(priority) is not int:
            priority = 100
        normalized = {"user_id": user_id, "name": name, "aliases": aliases,
            "account_ids": account_ids, "gender": gender, "content": content,
            "priority": priority, "group_ids": group_ids, "enabled": enabled,
            "identity_note": identity, "boundary_note": boundary,
            "important_memories": [memory.document for memory in memories]}
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        profile_id = hashlib.sha256(encoded).hexdigest()[:24]
        accepted.append(LegacyMemberProfile(profile_id, name, aliases, account_ids, gender,
            content, priority, group_ids, enabled, hashlib.sha256(encoded).hexdigest(),
            identity, boundary, memories))
        total_bytes += size
    return tuple(accepted), tuple(rejected)


def _setting(configuration, profile, persona_id, name, default=None):
    def configured_value(container):
        if not isinstance(container, dict):
            return None, False
        if name in container:
            return container[name], True
        for group_name in ("photo_action_config", "wardrobe_config", "config"):
            section = container.get(group_name)
            if not isinstance(section, dict):
                continue
            if name in section:
                return section[name], True
            items = section.get("items")
            if isinstance(items, dict) and name in items:
                return items[name], True
        return None, False

    candidates = []
    if isinstance(profile, dict):
        settings = profile.get("persona_settings")
        value, found = configured_value(settings)
        if found:
            candidates.append(value)
    if isinstance(configuration, dict):
        persona_settings = configuration.get("persona_settings")
        if isinstance(persona_settings, dict):
            overlay = persona_settings.get(persona_id) if persona_id else persona_settings.get("primary")
            value, found = configured_value(overlay)
            if found:
                candidates.append(value)
        value, found = configured_value(configuration)
        if found:
            candidates.append(value)
        settings = configuration.get("persona_settings")
        if isinstance(settings, dict):
            primary = settings.get("primary")
            value, found = configured_value(primary)
            if found:
                candidates.append(value)
    return candidates[0] if candidates else default


def _reference_roles(value, *, fallback=("identity",)):
    aliases = {"source": "edit_source", "background": "background"}
    allowed = {"identity", "outfit", "pose", "scene", "style", "background",
               "continuity", "edit_source", "edit_mask"}
    roles = []
    for role in _clean_list(value, 9):
        normalized = aliases.get(role.lower(), role.lower())
        if normalized in allowed and normalized not in roles:
            roles.append(normalized)
    if not roles:
        roles.extend(role for role in fallback if role in allowed)
    return tuple(roles)


def _reference_file(root: Path, source, *, expected_hash=""):
    text = str(source or "").strip()
    if not text or len(text) > 1600:
        return None, "invalid_filename"
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None, "invalid_filename"
    candidate = Path(text).expanduser()
    if not candidate.is_absolute() and parsed.scheme.lower() in ("http", "https"):
        return None, "remote_url_not_downloaded"
    if (not candidate.is_absolute() and parsed.scheme) or "\x00" in text:
        return None, "invalid_filename"

    path, reason = None, "image_missing"
    if candidate.is_absolute():
        try:
            resolved = candidate.resolve(strict=True)
            try:
                relative = candidate.absolute().relative_to(root.resolve())
            except ValueError:
                relative = None
            if relative is not None:
                path, reason = _safe_relative(root, root, relative.as_posix(), allow_subdirs=True)
            else:
                path, reason = _safe_absolute_file(candidate)
        except FileNotFoundError:
            reason = "image_missing"
        except (OSError, ValueError):
            reason = "image_path_outside_library"
    else:
        attempts = [text]
        if "/" not in text and "\\" not in text:
            attempts.extend((f"photo_reference_images/{text}", f"photo_reference_assets/{text}"))
        for relative_name in attempts:
            path, reason = _safe_relative(root, root, relative_name, allow_subdirs=True)
            if not reason:
                break
            if reason not in ("image_missing",):
                break
    if reason:
        return None, reason
    if path.suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
        return None, "unsupported_image_type"
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_REFERENCE_IMAGE_BYTES:
            return None, "target_image_limit"
        content = path.read_bytes()
        if len(content) != size:
            return None, "image_changed_during_read"
    except OSError:
        return None, "image_unreadable"
    actual_hash = hashlib.sha256(content).hexdigest()
    expected = str(expected_hash or "").strip().lower()
    if expected and (not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != actual_hash):
        return None, "catalog_hash_mismatch"
    try:
        display_path = path.relative_to(root.resolve()).as_posix()
    except ValueError:
        display_path = path.name
    return {"source_path": str(path), "filename": path.name[:160], "sha256": actual_hash,
            "size": len(content), "relative_path": display_path, "content": content}, ""


def _safe_absolute_file(candidate: Path):
    try:
        resolved = candidate.resolve(strict=True)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for current in (candidate, *candidate.parents):
            info = current.lstat()
            if (stat.S_ISLNK(info.st_mode)
                    or int(getattr(info, "st_file_attributes", 0)) & reparse):
                return None, "image_path_outside_library"
        info = resolved.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None, "image_unreadable"
        return resolved, ""
    except FileNotFoundError:
        return None, "image_missing"
    except (OSError, ValueError):
        return None, "image_path_outside_library"


def _reference_image(root, *, source, source_key, label, roles, expected_hash=""):
    loaded, reason = _reference_file(root, source, expected_hash=expected_hash)
    if reason:
        return None, reason
    return LegacyReferenceImage(source_key=str(source_key)[:160], source_path=loaded["source_path"],
        filename=loaded["filename"], sha256=loaded["sha256"], size=loaded["size"],
        label=_clean(label, 120) or loaded["filename"], roles=_reference_roles(roles)), ""


def _photo_reference_rows(configuration, profile, persona_id):
    raw_catalog = _setting(configuration, profile, persona_id, "photo_reference_catalog", None)
    cleared = _setting(configuration, profile, persona_id,
                       "photo_reference_catalog_user_cleared", False) is True
    catalog_rows = raw_catalog
    if isinstance(raw_catalog, str):
        try:
            catalog_rows = json.loads(raw_catalog)
        except (ValueError, json.JSONDecodeError):
            catalog_rows = None
    if isinstance(catalog_rows, list) and catalog_rows:
        return [(item, f"catalog:{item.get('id') or index}")
                for index, item in enumerate(catalog_rows)], []
    if raw_catalog not in (None, [], "") and catalog_rows is None:
        return [], [{"source_id": REFERENCE_IMAGE_SOURCE, "reason": "catalog_invalid"}]
    if cleared:
        return [], []
    rows = []
    persona_path = _setting(configuration, profile, persona_id, "photo_persona_reference_image_path", "")
    if persona_path:
        rows.append(({"kind": "persona", "source": persona_path, "note": "默认人设参考图",
                      "reference_roles": ["identity"]}, "legacy:persona"))
    library = _setting(configuration, profile, persona_id, "photo_reference_library", [])
    if isinstance(library, str):
        text = library.strip()
        try:
            parsed = json.loads(text) if text.startswith("[") else None
        except (ValueError, json.JSONDecodeError):
            parsed = None
        library = parsed if isinstance(parsed, list) else text.splitlines()
    if isinstance(library, dict):
        library = [library]
    if isinstance(library, (list, tuple)):
        for index, raw in enumerate(library[:MAX_REFERENCE_IMAGE_ITEMS]):
            if isinstance(raw, dict):
                item = dict(raw)
            else:
                text = str(raw or "").strip()
                parts = re.split(r"\s*(?:\|\||｜｜)\s*", text, maxsplit=2)
                item = {"source": parts[0] if parts else "",
                        "note": parts[1] if len(parts) > 1 else ""}
                if len(parts) > 2:
                    try:
                        metadata = json.loads(parts[2])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        metadata = None
                    if isinstance(metadata, dict):
                        item.update(metadata)
            rows.append((item, f"legacy:library:{index}"))
    return rows, []


def _reference_assets(root, profile, configuration, persona_id):
    accepted, rejected, seen = [], [], set()
    rows, catalog_rejected = _photo_reference_rows(configuration, profile, persona_id)
    rejected.extend(catalog_rejected)
    for index, (raw, source_key) in enumerate(rows):
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "item_invalid"})
            continue
        if raw.get("selection_eligibility") == "disabled":
            rejected.append({"source_id": source_key, "reason": "reference_disabled"})
            continue
        source = raw.get("source") or raw.get("path") or raw.get("url")
        note = raw.get("note") or raw.get("description") or ""
        category = raw.get("outfit_category") or raw.get("wardrobe_category") or ""
        label_parts = [note]
        if category:
            label_parts.append(f"服装：{category}")
        for field, title in (("scene_categories", "场景"), ("time_categories", "时间")):
            values = _clean_list(raw.get(field), 4)
            if values:
                label_parts.append(f"{title}：{'、'.join(values)}")
        if raw.get("preferred_preset"):
            label_parts.append(f"预设：{_clean(raw.get('preferred_preset'), 40)}")
        label = "；".join(part for part in label_parts if part)
        fallback = ("identity",) if raw.get("kind") == "persona" else ("identity",)
        roles = _reference_roles(raw.get("reference_roles") or raw.get("reference_role"), fallback=fallback)
        if raw.get("outfit_lock_default") is True and "outfit" not in roles:
            roles = (*roles, "outfit")
        image, reason = _reference_image(root, source=source, source_key=source_key,
            label=label or ("人设参考图" if raw.get("kind") == "persona" else "V1 参考图"),
            roles=roles, expected_hash=raw.get("sha256") or raw.get("content_hash") or "")
        if reason:
            rejected.append({"source_id": source_key, "filename": Path(str(source or "")).name[:120],
                             "reason": reason})
            continue
        if image.sha256 in seen:
            continue
        seen.add(image.sha256)
        accepted.append(image)
        if len(accepted) >= MAX_REFERENCE_IMAGE_ITEMS:
            break

    records = profile.get("photo_reference_assets") if isinstance(profile, dict) else None
    if records is not None and not isinstance(records, list):
        rejected.append({"source_id": REFERENCE_IMAGE_SOURCE, "reason": "catalog_invalid"})
    elif isinstance(records, list):
        for index, raw in enumerate(records[:MAX_REFERENCE_IMAGE_ITEMS]):
            if not isinstance(raw, dict):
                rejected.append({"index": index, "reason": "item_invalid"})
                continue
            acl = raw.get("image_access")
            scope = raw.get("scope")
            if scope not in ("relation_role", "relation_user"):
                rejected.append({"source_id": str(raw.get("id") or index)[:120],
                                 "reason": "identity_scope_unmapped"})
                continue
            if (not isinstance(acl, dict)
                    or set(acl) != {"subject_ref", "allow_generation", "readers", "audiences", "routes"}
                    or acl.get("allow_generation") is not True or acl.get("subject_ref") is not None
                    or any(not isinstance(acl.get(key), list)
                           or not acl.get(key)
                           or any(type(value) is not str or not value or value != value.strip()
                                  for value in acl.get(key, []))
                           for key in ("readers", "audiences", "routes"))
                    or "*" not in acl.get("routes", [])
                    or (scope == "relation_role"
                        and any("*" not in acl.get(key, []) for key in ("readers", "audiences")))):
                rejected.append({"source_id": str(raw.get("id") or index)[:120],
                                 "reason": "image_access_not_role_wide"})
                continue
            source_key = "asset:" + str(raw.get("id") or index)[:120]
            image, reason = _reference_image(root, source=raw.get("path"), source_key=source_key,
                label=raw.get("title") or raw.get("note") or raw.get("id") or "V1 角色参考图",
                roles=raw.get("reference_roles") or raw.get("roles") or ["identity"],
                expected_hash=raw.get("sha256") or raw.get("content_hash") or "")
            if reason:
                rejected.append({"source_id": source_key, "filename": Path(str(raw.get("path") or "")).name[:120],
                                 "reason": reason})
                continue
            if image.sha256 not in seen:
                seen.add(image.sha256)
                accepted.append(image)
    if len(rows) > MAX_REFERENCE_IMAGE_ITEMS:
        rejected.append({"source_id": REFERENCE_IMAGE_SOURCE, "reason": "asset_count_limit"})
    if isinstance(records, list) and len(records) > MAX_REFERENCE_IMAGE_ITEMS:
        rejected.append({"source_id": REFERENCE_IMAGE_SOURCE, "reason": "asset_count_limit"})
    return tuple(accepted), tuple(rejected)


def _wardrobe_items(root, profile, configuration, persona_id):
    raw_items = _setting(configuration, profile, persona_id, "wardrobe_items", [])
    if isinstance(raw_items, str):
        try:
            parsed = json.loads(raw_items)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        raw_items = parsed if isinstance(parsed, list) else []
    if not isinstance(raw_items, list):
        return (), ({"source_id": WARDROBE_SOURCE, "reason": "catalog_invalid"},)
    accepted, rejected = [], []
    for index, raw in enumerate(raw_items[:MAX_WARDROBE_ITEMS]):
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "item_invalid"})
            continue
        name = _clean(raw.get("name") or raw.get("title"), 120)
        description = _clean(raw.get("description") or raw.get("note") or raw.get("desc"), 2000)
        if not name and not description:
            rejected.append({"index": index, "reason": "entry_content_missing"})
            continue
        name = name or description[:12] or "未命名衣物"
        tags = tuple(_clean_list(raw.get("tags"), 16))
        source_id = _clean(raw.get("id"), 80) or str(index)
        source_key = f"wardrobe:{source_id}:{index}"
        item_id = "v1_wardrobe_" + hashlib.sha256(
            json.dumps([persona_id, source_key], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:32]
        source = raw.get("source") or raw.get("path") or raw.get("url")
        image, image_reason = (None, "")
        if source:
            image, image_reason = _reference_image(root, source=source, source_key=source_key,
                label=name, roles=("outfit",), expected_hash=raw.get("sha256") or "")
        accepted.append(LegacyWardrobeItem(item_id, source_key, name[:120], description[:2000],
                                            tags, image, image_reason))
    if len(raw_items) > MAX_WARDROBE_ITEMS:
        rejected.append({"source_id": WARDROBE_SOURCE, "reason": "asset_count_limit",
                         "count": len(raw_items) - MAX_WARDROBE_ITEMS})
    return tuple(accepted), tuple(rejected)


def _owned_reaction_assets(root: Path, profile, configuration, persona_id):
    raw_assets = _setting(configuration, profile, persona_id, "owned_reaction_assets", [])
    if not isinstance(raw_assets, list):
        return (), ({"filename": "owned_reaction_assets", "reason": "catalog_invalid"},)
    enabled = _setting(configuration, profile, persona_id, "enable_owned_reaction_asset_workbench", False) is True
    accepted, rejected, seen = [], [], set()
    for index, raw in enumerate(raw_assets[:96]):
        if not isinstance(raw, dict):
            rejected.append({"filename": str(index + 1), "reason": "item_invalid"})
            continue
        asset_id = _clean(raw.get("id") or raw.get("asset_id"), 80)
        tags = _clean_list(raw.get("tags"), 12)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", asset_id):
            rejected.append({"filename": asset_id or str(index + 1), "reason": "invalid_id"})
            continue
        if not tags:
            rejected.append({"filename": asset_id, "reason": "missing_tags"})
            continue
        stored_name = raw.get("file") or raw.get("relative_path")
        loaded, reason = _load_image(root, "owned_reaction_assets", stored_name,
            source_id=OWNED_REACTION_SOURCE, allow_subdirs=True, extensions=OWNED_IMAGE_EXTENSIONS)
        if reason:
            rejected.append({"filename": asset_id, "reason": reason})
            continue
        path, content = loaded
        expected = str(raw.get("sha256") or "").lower()
        digest = hashlib.sha256(content).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            rejected.append({"filename": asset_id, "reason": "invalid_hash"})
            continue
        if expected != digest:
            rejected.append({"filename": asset_id, "reason": "catalog_hash_mismatch"})
            continue
        if digest in seen:
            continue
        seen.add(digest)
        metadata = {"name": asset_id, "description": "V1 管理员登记的自有表情素材",
                    "visible_text": "", "tags": tags, "emotions": [], "intents": [],
                    "legacy_asset_id": asset_id}
        accepted.append(ReactionAsset(str(path.relative_to(root)), asset_id + path.suffix.lower(),
            digest, len(content), metadata, OWNED_REACTION_SOURCE, enabled))
    if len(raw_assets) > 96:
        rejected.append({"filename": "…", "reason": "asset_count_limit"})
    return tuple(accepted), tuple(rejected)


def _iso_time(value):
    parsed = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 10**12:
            timestamp /= 1000
        try:
            parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds") if parsed else None


def _count(value):
    if type(value) is not int:
        return 0
    return min(max(value, 0), 2**31 - 1)


def _legacy_tone(value):
    if isinstance(value, dict):
        ranked = sorted(value.items(), key=lambda item: (_count(item[1]), str(item[0])), reverse=True)
        value = ranked[0][0] if ranked and _count(ranked[0][1]) else ""
    text = str(value or "")
    if text in ("紧绷", "tension"):
        return "tension"
    if text in ("玩笑", "banter"):
        return "banter"
    return "ordinary"


def _group_networks(payload):
    if not isinstance(payload, dict):
        return (), ["所选 V1 人格档案无法解析，群互动图没有纳入预览。"]
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return (), ["所选 V1 人格档案中没有可识别的 groups 数据。"]
    result = []
    for group_id, raw in sorted(groups.items(), key=lambda pair: str(pair[0])):
        if not isinstance(raw, dict):
            continue
        members = {}
        rejected_members = 0
        raw_members = raw.get("members") if isinstance(raw.get("members"), dict) else {}
        for account_id, person in raw_members.items():
            account = _clean(account_id, 256)
            if not account or not isinstance(person, dict):
                rejected_members += 1
                continue
            members[account] = {"account_id": account,
                "name": _clean(person.get("identity_name") or person.get("name"), 64),
                "message_count": _count(person.get("count")),
                "first_seen": _iso_time(person.get("first_seen")),
                "last_seen": _iso_time(person.get("last_seen") or person.get("last_ts")),
                "evidence_basis": "v1_group_aggregate"}
        edges, rejected_edges = [], 0
        raw_edges = raw.get("relationship_edges") if isinstance(raw.get("relationship_edges"), dict) else {}
        for edge in raw_edges.values():
            if not isinstance(edge, dict):
                rejected_edges += 1
                continue
            left, right = _clean(edge.get("a"), 256), _clean(edge.get("b"), 256)
            if not left or not right or left == right:
                rejected_edges += 1
                continue
            left, right = sorted((left, right))
            for account_id, label_key in ((left, "a_name"), (right, "b_name")):
                if account_id not in members:
                    members[account_id] = {"account_id": account_id,
                        "name": _clean(edge.get(label_key), 64), "message_count": 0,
                        "first_seen": None, "last_seen": None,
                        "evidence_basis": "v1_group_aggregate"}
            tone = _legacy_tone(edge.get("tone"))
            count = _count(edge.get("count"))
            if count <= 0:
                rejected_edges += 1
                continue
            edges.append({"a": left, "b": right, "count": count,
                "last_seen": _iso_time(edge.get("last_ts")), "tone": tone,
                "summary": {"tension": "V1 历史汇总显示近期有紧绷表达",
                            "banter": "V1 历史汇总显示近期有玩笑或接梗",
                            "ordinary": "V1 历史汇总显示曾连续接话"}[tone],
                "evidence_basis": "v1_group_aggregate"})
        edges.sort(key=lambda item: (item["count"], item["last_seen"] or ""), reverse=True)
        source_member_count = len(members)
        members = dict(sorted(members.items(), key=lambda item: item[1]["message_count"], reverse=True)
                       [:MAX_GROUP_NETWORK_MEMBERS])
        omitted_member_count = source_member_count - len(members)
        keep = set(members)
        source_edge_count = len(edges)
        edges = [item for item in edges if item["a"] in keep and item["b"] in keep]
        omitted_edge_count = source_edge_count - len(edges)
        if len(edges) > MAX_GROUP_NETWORK_EDGES:
            omitted_edge_count += len(edges) - MAX_GROUP_NETWORK_EDGES
            edges = edges[:MAX_GROUP_NETWORK_EDGES]
        group_key = _clean(group_id, 256)
        if group_key:
            result.append({"source_group_id": group_key, "member_count": len(members),
                           "edge_count": len(edges), "rejected_member_count": rejected_members,
                           "rejected_edge_count": rejected_edges,
                           "omitted_member_count": omitted_member_count,
                           "omitted_edge_count": omitted_edge_count,
                           "members": members, "edges": edges})
    return tuple(result), []


def _readonly_sqlite_summary(path: Path, *, state_columns=()):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"state": "absent", "tables": {}, "states": {}}
    except OSError:
        return {"state": "unreadable", "tables": {}, "states": {}}
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or int(getattr(info, "st_file_attributes", 0)) & reparse
            or info.st_size > 1024 * 1024 * 1024):
        return {"state": "unsafe_or_too_large", "tables": {}, "states": {}}
    try:
        connection = open_readonly_sqlite_snapshot(path, timeout=2)
        try:
            connection.execute("PRAGMA query_only=ON")
            names = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            tables = {}
            states = {}
            for name in sorted(names):
                quoted = '"' + name.replace('"', '""') + '"'
                try:
                    tables[name] = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
                except sqlite3.Error:
                    tables[name] = None
            for table, column, key in state_columns:
                if table not in names:
                    continue
                columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info(\"{table}\")")}
                if column not in columns:
                    continue
                quoted_table = '"' + table.replace('"', '""') + '"'
                quoted_column = '"' + column.replace('"', '""') + '"'
                states[key] = {str(row[0] or "unknown")[:40]: int(row[1]) for row in connection.execute(
                    f"SELECT {quoted_column}, COUNT(*) FROM {quoted_table} GROUP BY {quoted_column}")}
            return {"state": "readable", "tables": tables, "states": states}
        finally:
            connection.rollback()
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return {"state": "unreadable", "tables": {}, "states": {}}


def _world_inventory(root: Path):
    album = _readonly_sqlite_summary(root / "framework_world" / "album.db",
                                     state_columns=(("photos", "state", "photos"),))
    resources = root / "framework_world" / "resources"
    file_count, image_bytes, rejected_links = 0, 0, 0
    try:
        if resources.is_dir() and not resources.is_symlink():
            pending = [resources]
            while pending and file_count < 100000:
                directory = pending.pop()
                for entry in os.scandir(directory):
                    if entry.is_symlink():
                        rejected_links += 1
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        file_count += 1
                        try:
                            if Path(entry.name).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                                image_bytes += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
    except OSError:
        rejected_links += 1
    return {"album": album, "resource_files": file_count, "image_bytes": image_bytes,
            "rejected_links": rejected_links,
            "import_state": "not_imported",
            "reason": "相册结果由 Image Companion 持有，旧图片引用和本地资源没有经过 V2 的所有权、撤销与受众校验；本次只统计，不复制或重新生成。"}


def _work_delivery_inventory(root: Path):
    work = _readonly_sqlite_summary(root / "framework_work" / "work.db",
        state_columns=(("jobs", "status", "jobs"), ("calls", "status", "calls")))
    delivery = _readonly_sqlite_summary(root / "framework_work" / "delivery.db",
        state_columns=(("parts", "state", "parts"), ("parts", "capture_state", "capture"),
                       ("parts", "direction", "direction"), ("notices", "state", "notices")))
    return {"work": work, "delivery": delivery, "import_state": "not_imported",
            "reason": "旧工作库包含待执行任务、模型调用输入/步骤和原始便笺，投递库包含消息正文与外部发送回执。V2 无法还原原作用域授权；pending、running、unknown 等结果不会复制或重放。"}


def _profile_summary(payload):
    data = _profile_data(payload)
    users = data.get("users") if isinstance(data.get("users"), dict) else {}
    groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
    member_profiles = data.get("worldbook_member_profiles") if isinstance(data.get("worldbook_member_profiles"), dict) else {}
    group_profiles = data.get("worldbook_group_profiles") if isinstance(data.get("worldbook_group_profiles"), dict) else {}
    world_entries = data.get("worldbook_entries") if isinstance(data.get("worldbook_entries"), list) else []
    diaries = data.get("bot_diaries") if isinstance(data.get("bot_diaries"), list) else []
    return {"private_user_profiles": len(users), "source_groups": len(groups),
            "worldbook_profiles": len(member_profiles), "worldbook_group_profiles": len(group_profiles),
            "worldbook_entries": len(world_entries),
            "diary_entries": len(diaries), "dream_fragments": len(data.get("dream_fragments", []))
                if isinstance(data.get("dream_fragments"), list) else 0,
            "non_equivalent_reason": "私人用户运行画像、关系分数、投递状态和定时缓存没有可验证的 V2 等价归属，不整库复制。成员线索、群资料、群互动汇总、日记及带日期的梦境碎片按各自作用域合同迁移。"}


def build_data_plan(v1_root: str | Path, *, source_persona_id="", v1_configuration=None) -> LegacyDataPlan:
    root = Path(v1_root).resolve()
    if type(source_persona_id) is not str or len(source_persona_id) > 96:
        raise ValueError("source_persona_id_invalid")
    reaction_assets, reaction_rejected, reaction_warnings = _reaction_assets(root)
    primary = primary_profile(root, v1_configuration)
    persona_sources, persona_warnings = _persona_sources(root, primary)
    profile, profile_error, selected_path = _selected_profile(
        root, source_persona_id, persona_sources, primary)
    warnings = list(reaction_warnings + persona_warnings)
    if profile_error:
        warnings.append("所选 V1 人格档案未能安全读取：" + profile_error)
        profile = {}
    legacy_owned, owned_rejected = _owned_reaction_assets(root, profile, v1_configuration, source_persona_id)
    all_reactions = []
    seen_hashes = set()
    for item in (*reaction_assets, *legacy_owned):
        if item.sha256 not in seen_hashes:
            seen_hashes.add(item.sha256)
            all_reactions.append(item)
    all_rejected = tuple((*reaction_rejected, *owned_rejected))
    group_networks, group_warnings = _group_networks(profile)
    journals, journal_rejected = _journal_items(profile, source_persona_id)
    worldbook_items, worldbook_rejected = _worldbook_items(profile)
    group_profile_items, group_profile_rejected = _group_profile_items(profile)
    worldbook_items = tuple((*worldbook_items, *group_profile_items))
    worldbook_rejected = tuple((*worldbook_rejected, *group_profile_rejected))
    member_profiles, member_profile_rejected = _member_profiles(profile)
    profile_data = _profile_data(profile)
    from .expression_data import expression_profiles
    learned_expressions = expression_profiles(profile_data, source_persona_id)
    reference_images, reference_image_rejected = _reference_assets(
        root, profile_data, v1_configuration, source_persona_id)
    wardrobe_items, wardrobe_rejected = _wardrobe_items(
        root, profile_data, v1_configuration, source_persona_id)
    work_delivery = _work_delivery_inventory(root)
    world_assets = _world_inventory(root)
    profile_summary = _profile_summary(profile)
    if profile_error:
        profile_summary = {"private_user_profiles": 0, "source_groups": 0,
            "worldbook_profiles": 0, "worldbook_group_profiles": 0,
            "worldbook_entries": 0, "diary_entries": 0,
            "dream_fragments": 0, "non_equivalent_reason": profile_error}
    material = {
        "expression_profiles": learned_expressions,
        "source_persona_id": source_persona_id,
        "selected_path": selected_path,
        "reactions": [{"sha256": item.sha256, "metadata": item.metadata, "size": item.size,
                       "source_id": item.source_id, "enabled": item.enabled} for item in all_reactions],
        "reaction_rejected": list(all_rejected),
        "journals": [{"kind": item.kind, "date": item.local_date, "sha256": item.sha256}
                     for item in journals],
        "journal_rejected": list(journal_rejected),
        "worldbook_items": [{"index": item.index, "sha256": item.sha256,
            "template": item.template, "source_kind": item.source_kind,
            "enabled": item.enabled, "member_ids": item.member_ids,
            "group_ids": item.group_ids} for item in worldbook_items],
        "worldbook_rejected": list(worldbook_rejected),
        "member_profiles": [{"profile_id": item.profile_id, "sha256": item.sha256,
            "group_ids": item.group_ids, "enabled": item.enabled} for item in member_profiles],
        "member_profile_rejected": list(member_profile_rejected),
        "reference_images": [{"source_key": item.source_key, "sha256": item.sha256,
            "size": item.size, "label": item.label, "roles": item.roles}
            for item in reference_images],
        "reference_image_rejected": list(reference_image_rejected),
        "wardrobe_items": [{"item": item.document(),
            "image_sha256": item.image.sha256 if item.image else ""}
            for item in wardrobe_items],
        "wardrobe_rejected": list(wardrobe_rejected),
        "groups": [{"source_group_id": item["source_group_id"], "members": item["members"],
                    "edges": item["edges"],
                    "rejected_member_count": item["rejected_member_count"],
                    "rejected_edge_count": item["rejected_edge_count"],
                    "omitted_member_count": item["omitted_member_count"],
                    "omitted_edge_count": item["omitted_edge_count"]}
                   for item in group_networks],
        "profile_summary": profile_summary,
        "work_delivery": work_delivery,
        "world_assets": world_assets,
        "persona_sources": list(persona_sources),
    }
    fingerprint = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return LegacyDataPlan(tuple(all_reactions), all_rejected, tuple(group_networks), journals,
        journal_rejected, worldbook_items, worldbook_rejected, member_profiles,
        member_profile_rejected, persona_sources, source_persona_id, profile_summary,
        work_delivery, world_assets, fingerprint, tuple(warnings + group_warnings),
        reference_images, reference_image_rejected, wardrobe_items, wardrobe_rejected, learned_expressions)


def load_reaction_asset(v1_root: str | Path, item: ReactionAsset) -> bytes:
    root = Path(v1_root).resolve()
    source_directory = "owned_reaction_assets" if item.source_id == OWNED_REACTION_SOURCE \
        else "reaction_expression_library/images"
    relative_path = str(item.relative_path).replace("\\", "/")
    prefix = source_directory + "/"
    if not relative_path.startswith(prefix):
        raise ValueError("image_changed_after_preview")
    stored_name = relative_path[len(prefix):]
    path, reason = _safe_relative(root, root / source_directory, stored_name,
                                  allow_subdirs=item.source_id == OWNED_REACTION_SOURCE)
    if reason:
        raise ValueError(reason)
    content = path.read_bytes()
    if len(content) != item.size or len(content) > MAX_REACTION_ASSET_BYTES:
        raise ValueError("image_changed_after_preview")
    if hashlib.sha256(content).hexdigest() != item.sha256:
        raise ValueError("image_changed_after_preview")
    return content


def load_reference_image(v1_root: str | Path, item: LegacyReferenceImage) -> bytes:
    root = Path(v1_root).resolve()
    loaded, reason = _reference_file(root, item.source_path, expected_hash=item.sha256)
    if reason:
        raise ValueError("image_changed_after_preview" if reason == "catalog_hash_mismatch" else reason)
    if loaded["size"] != item.size:
        raise ValueError("image_changed_after_preview")
    return loaded["content"]
