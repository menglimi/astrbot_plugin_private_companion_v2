"""Import contract for worldbook files and knowledge-base rows.

One import is: *read* the named origin, *parse* it with the existing format
parsers, *normalize* it into background entries and member entries, then save a
versioned revision in the catalogue.  Nothing here selects, ranks or injects;
that stays with :mod:`~companion_v2.knowledge.retrieval` and the conversation
injection point.

The contract is deliberately host-free: reading a file, an AstrBot knowledge
base or a test dictionary is the caller's job, so no data-root policy, no SDK
and no filesystem access live in the core package.

Failure handling follows V1 but is honest about it:

* a source that is no longer present is *retired* (its entries stop being used);
* a source that is present but unreadable or unparsable keeps its previous good
  revision and reports ``invalid`` -- a broken file must never empty working
  material, and it must never raise into a conversation turn;
* unchanged parsed content writes no new revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from companion_v2.execution.models import digest

from .catalog import EntryDocument, MemberEntry, SourceBinding, SourceVersion
from .parsing import ParseBatch, parse_knowledge_rows, parse_worldbook


MEMBER_TEMPLATE = "user"
GROUP_TEMPLATE = "group"


class KnowledgeFormat(str, Enum):
    """The two import shapes V2 accepts; both reuse the existing parsers."""

    WORLD_BOOK = "worldbook"
    KNOWLEDGE_ROWS = "knowledge_rows"


class ImportStatus(str, Enum):
    IMPORTED = "imported"
    UNCHANGED = "unchanged"
    MISSING = "missing"
    INVALID = "invalid"
    DISABLED = "disabled"


@dataclass(frozen=True)
class KnowledgeSourceSpec:
    """One importable origin and the boundary its material may serve."""

    source_id: str
    format: KnowledgeFormat
    locator: str
    binding: SourceBinding
    enabled: bool = True

    def __post_init__(self) -> None:
        if type(self.source_id) is not str or not self.source_id.strip() or len(self.source_id) > 512:
            raise ValueError("source_id must be a bounded non-blank string")
        if not isinstance(self.format, KnowledgeFormat):
            raise ValueError("source format must be declared")
        if type(self.locator) is not str or not self.locator.strip():
            raise ValueError("source locator must be non-blank")
        if not isinstance(self.binding, SourceBinding):
            raise ValueError("source binding must be explicit")
        if type(self.enabled) is not bool:
            raise ValueError("source enabled must be boolean")


@dataclass(frozen=True)
class ImportResult:
    """What one import attempt did, without exposing imported content."""

    source_id: str
    status: ImportStatus
    revision: int = 0
    entries: int = 0
    member_entries: int = 0
    issues: tuple[tuple[int, str], ...] = ()
    code: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (ImportStatus.IMPORTED, ImportStatus.UNCHANGED)


class KnowledgeSourceReader(Protocol):
    """Host-supplied reader: returns the decoded payload or None when absent."""

    def __call__(self, spec: KnowledgeSourceSpec) -> object | None: ...


@dataclass(frozen=True)
class ImportPlan:
    """A configured source set plus the reader that can fetch each origin."""

    specs: tuple[KnowledgeSourceSpec, ...]
    read: KnowledgeSourceReader
    retire_absent: bool = True


def _bounded(value, limit):
    text = " ".join(str(value or "").split())
    return text[:limit]


def _knowledge_base_id(locator) -> str:
    """``kb:<id>`` and ``doc:<kb>:<doc>`` both name one knowledge base."""
    parts = str(locator or "").split(":")
    if len(parts) > 1 and parts[0] in ("kb", "doc") and parts[1].strip():
        return parts[1].strip()
    return str(locator or "").strip()


def _native_id(value) -> str:
    """Accept one native account or window id from an imported ``scope`` list.

    The runtime treats native ids as opaque host strings, so this keeps the token
    as written instead of assuming V1's all-digit QQ numbers.  A ``platform:id``
    prefix is dropped because the runtime window already carries the platform.
    A value that matches nothing simply never authorizes a hit.
    """
    text = str(value or "").strip()
    if not text or len(text) > 64 or any(character.isspace() for character in text):
        return ""
    return text.rsplit(":", 1)[-1].strip() if ":" in text else text


class KnowledgeImporter:
    """Parse, normalize and version one or more configured knowledge sources."""

    def __init__(self, catalog, *, entry_limit=500, content_chars=1200) -> None:
        if type(entry_limit) is not int or not 1 <= entry_limit <= 5000:
            raise ValueError("entry limit must be inside the registered range")
        if type(content_chars) is not int or not 64 <= content_chars <= 4000:
            raise ValueError("entry character limit must be inside the registered range")
        self.catalog = catalog
        self.entry_limit = entry_limit
        self.content_chars = content_chars

    # -- normalization -------------------------------------------------------

    def _entries(self, batch: ParseBatch) -> tuple[tuple[EntryDocument, ...], tuple[MemberEntry, ...]]:
        entries: list[EntryDocument] = []
        members: list[MemberEntry] = []
        for item in batch.items:
            if len(entries) + len(members) >= self.entry_limit:
                break
            member_ids = tuple(dict.fromkeys(
                _native_id(value) for value in item.scope if _native_id(value)))
            if item.template == MEMBER_TEMPLATE and member_ids:
                members.append(MemberEntry(
                    item.entry_id or item.name or digest(item.content), name=item.name,
                    aliases=item.aliases, declared_account_ids=member_ids, gender=item.gender,
                    content=item.content[:self.content_chars], priority=item.priority))
                continue
            group_ids = ()
            if item.template == GROUP_TEMPLATE:
                group_ids = tuple(dict.fromkeys(
                    _native_id(value) for value in item.scope if _native_id(value)))
            entries.append(EntryDocument(
                item.entry_id or item.name or digest(item.content),
                item.content[:self.content_chars], name=item.name, gender=item.gender,
                priority=item.priority, enabled=item.enabled, keywords=item.keywords,
                aliases=item.aliases, template=item.template, native_scope_ids=group_ids))
        return tuple(entries), tuple(members)

    def _chunks(self, batch: ParseBatch) -> tuple[EntryDocument, ...]:
        entries = []
        for chunk in batch.items:
            if len(entries) >= self.entry_limit:
                break
            entries.append(EntryDocument(
                f"{chunk.knowledge_base_id}:{chunk.document_id}:{chunk.chunk_index}",
                chunk.text[:self.content_chars], document_name=chunk.document_name,
                knowledge_base_id=chunk.knowledge_base_id, document_id=chunk.document_id,
                chunk_index=chunk.chunk_index))
        return tuple(entries)

    def _parse(self, spec: KnowledgeSourceSpec, payload):
        if spec.format is KnowledgeFormat.WORLD_BOOK:
            return parse_worldbook(payload)
        return parse_knowledge_rows(payload, knowledge_base_id=_knowledge_base_id(spec.locator))

    # -- import --------------------------------------------------------------

    def import_source(self, spec: KnowledgeSourceSpec, read: KnowledgeSourceReader, *, at) -> ImportResult:
        """Import one source; every outcome is a result, never an exception."""
        if not spec.enabled:
            return ImportResult(spec.source_id, ImportStatus.DISABLED)
        current = self.catalog.get(spec.binding, spec.source_id)
        try:
            payload = read(spec)
        except Exception:
            # An unreadable origin keeps the previous good revision so a
            # temporary I/O problem cannot silently remove working material.
            return ImportResult(spec.source_id, ImportStatus.INVALID,
                                revision=current.revision if current else 0,
                                code="source_unreadable")
        if payload is None:
            retired = self.catalog.retire(spec.binding, spec.source_id, at=at)
            return ImportResult(spec.source_id, ImportStatus.MISSING, code="source_absent"
                                if retired else "source_unknown")
        try:
            batch = self._parse(spec, payload)
            if spec.format is KnowledgeFormat.WORLD_BOOK:
                entries, members = self._entries(batch)
            else:
                entries, members = self._chunks(batch), ()
        except Exception:
            return ImportResult(spec.source_id, ImportStatus.INVALID,
                                revision=current.revision if current else 0,
                                code="source_unparsable")
        issues = tuple((item.index, item.code) for item in batch.issues)
        if not entries and not members:
            return ImportResult(spec.source_id, ImportStatus.INVALID, issues=issues,
                                revision=current.revision if current else 0,
                                code="source_empty")
        content_digest = digest([item.document for item in entries] + [item.document for item in members])
        if current is not None and current.active and current.digest == content_digest:
            return ImportResult(spec.source_id, ImportStatus.UNCHANGED, revision=current.revision,
                                entries=len(current.entries), member_entries=len(current.members),
                                issues=issues)
        version = self.catalog.save(spec.binding, source_id=spec.source_id, locator=spec.locator,
                                    format=spec.format.value, content_digest=content_digest,
                                    entries=entries, members=members, issues=issues, at=at,
                                    code="imported")
        return ImportResult(spec.source_id, ImportStatus.IMPORTED, revision=version.revision,
                            entries=len(entries), member_entries=len(members), issues=issues)

    def import_all(self, plan: ImportPlan, *, at) -> tuple[ImportResult, ...]:
        """Import every configured source; one bad source never stops the rest."""
        results = []
        for spec in plan.specs:
            results.append(self.import_source(spec, plan.read, at=at))
        if plan.retire_absent and plan.specs:
            # Only rows of a binding that this plan actually configures may be
            # retired, so one role's plan can never invalidate another's sources.
            bindings = {spec.binding.key: spec.binding for spec in plan.specs}
            for binding in bindings.values():
                configured = {spec.source_id for spec in plan.specs if spec.binding == binding}
                for version in self.catalog.active(binding.installation_id,
                                                   limit=max(1, len(plan.specs) * 8)):
                    if version.binding != binding or version.source_id in configured:
                        continue
                    if version.code == "legacy_v1_imported":
                        continue
                    if self.catalog.retire(version.binding, version.source_id, at=at,
                                           reason="source_removed"):
                        results.append(ImportResult(version.source_id, ImportStatus.MISSING,
                                                    code="source_removed"))
        return tuple(results)

    def status(self, binding: SourceBinding) -> tuple[SourceVersion, ...]:
        """Current stored revisions for one binding, for an operator view."""
        return tuple(version for version in self.catalog.list(binding.installation_id, limit=64)
                     if version.binding == binding)


__all__ = [
    "GROUP_TEMPLATE", "ImportPlan", "ImportResult", "ImportStatus", "KnowledgeFormat",
    "KnowledgeImporter", "KnowledgeSourceReader", "KnowledgeSourceSpec", "MEMBER_TEMPLATE",
]
