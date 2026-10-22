"""Host-side origin readers for the V2 knowledge import contract.

The core package may not touch a filesystem (the V2 isolation scan rejects
unapproved file and SQLite access inside ``companion_v2``), so the two real
origins live here:

* an AstrBot worldbook export, a JSON file with an ``entry_storage`` list, the
  same shape V1 read from ``config/plugin_upload_astrbot_plugin_worldbook_config.json``;
* an AstrBot knowledge base under ``<data root>/knowledge_base`` (``kb.db`` for the
  catalogue and ``<kb_id>/doc.db`` for the chunk rows).

Only explicitly supplied or configured origins are read.  No V1 companion data
root is touched and the AstrBot data root must be passed in by the caller; there
is no implicit global lookup in this module.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from companion_v2.storage.sqlite_path import readonly_uri

from companion_v2.knowledge.catalog import KnowledgeCatalog, SourceBinding
from companion_v2.knowledge.configuration import read_installation_settings
from companion_v2.knowledge.importer import (
    ImportPlan,
    KnowledgeFormat,
    KnowledgeImporter,
    KnowledgeSourceSpec,
)
from companion_v2.knowledge.parsing import parse_knowledge_rows
from companion_v2.knowledge.retrieval import KnowledgeCandidate


WORLDBOOK_DEFAULTS = (
    "config/plugin_upload_astrbot_plugin_worldbook_config.json",
    "config/astrbot_plugin_worldbook_config.json",
)
KNOWLEDGE_BASE_DIR = "knowledge_base"
SOURCE_PREFIXES = ("kb:", "doc:")


def worldbook_paths(data_root, settings):
    """Configured worldbook files, then the two conventional AstrBot locations."""
    data_root = Path(data_root)
    resolved = []
    configured = settings.paths()
    for part in configured:
        path = Path(part)
        candidate = path if path.is_absolute() else data_root / path
        if candidate not in resolved:
            resolved.append(candidate)
    if not configured:
        for relative in WORLDBOOK_DEFAULTS:
            candidate = data_root / relative
            if candidate not in resolved:
                resolved.append(candidate)
    return tuple(resolved)


def knowledge_base_ids(data_root, settings):
    """Configured ``kb:``/``doc:`` ids that still exist in this installation."""
    available = available_source_ids(data_root)
    return tuple(item for item in settings.knowledge_source_ids()
                 if item.startswith(SOURCE_PREFIXES) and item in available)


def available_source_ids(data_root) -> frozenset[str]:
    """Every knowledge base and document id the local AstrBot installation has."""
    root = Path(data_root) / KNOWLEDGE_BASE_DIR
    database = root / "kb.db"
    if not database.is_file():
        return frozenset()
    identifiers = set()
    connection = _connect(database)
    try:
        for row in connection.execute("select kb_id from knowledge_bases"):
            kb_id = str(row["kb_id"] or "").strip()
            if kb_id:
                identifiers.add("kb:" + kb_id)
        for row in connection.execute("select kb_id, doc_id from kb_documents"):
            kb_id, doc_id = str(row["kb_id"] or "").strip(), str(row["doc_id"] or "").strip()
            if kb_id and doc_id:
                identifiers.add(f"doc:{kb_id}:{doc_id}")
    finally:
        connection.close()
    return frozenset(identifiers)


def import_plan(data_root, binding: SourceBinding, settings) -> ImportPlan | None:
    """The configured import plan, or None when importing is switched off."""
    if not settings.import_enabled:
        return None
    specs = []
    for path in worldbook_paths(data_root, settings):
        specs.append(KnowledgeSourceSpec(f"worldbook:{path}", KnowledgeFormat.WORLD_BOOK,
                                         str(path), binding, enabled=True))
    for identifier in knowledge_base_ids(data_root, settings):
        specs.append(KnowledgeSourceSpec(identifier, KnowledgeFormat.KNOWLEDGE_ROWS, identifier,
                                         binding, enabled=True))
    return ImportPlan(tuple(specs), KnowledgeSourceReader(data_root))


class KnowledgeSourceReader:
    """Read one configured origin; None means the origin is gone."""

    def __init__(self, data_root) -> None:
        self.data_root = Path(data_root)

    def __call__(self, spec: KnowledgeSourceSpec):
        if spec.format is KnowledgeFormat.WORLD_BOOK:
            return self._worldbook(Path(spec.locator))
        return self._knowledge_rows(spec.locator)

    @staticmethod
    def _worldbook(path: Path):
        if not path.is_file():
            return None
        # A decoded failure is reported to the importer, which keeps the
        # previous good revision instead of emptying the catalogue.
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _knowledge_rows(self, identifier: str, *, limit=None):
        parts = identifier.split(":")
        kb_id = parts[1] if len(parts) > 1 else ""
        doc_id = parts[2] if len(parts) > 2 else None
        database = self.data_root / KNOWLEDGE_BASE_DIR / kb_id / "doc.db"
        if not kb_id or not database.is_file():
            return None
        rows = []
        connection = _connect(database)
        try:
            for row in connection.execute("select text, metadata from documents order by id asc"):
                metadata = row["metadata"] or "{}"
                if doc_id is not None:
                    try:
                        decoded = json.loads(metadata) if isinstance(metadata, str) else metadata
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(decoded, dict) or str(decoded.get("kb_doc_id") or "") != doc_id:
                        continue
                rows.append({"text": row["text"], "metadata": metadata})
                if limit is not None and len(rows) >= limit:
                    break
        finally:
            connection.close()
        return rows


class AstrBotKnowledgeSources:
    """Read the official AstrBot knowledge bases selected in Companion V2."""

    def __init__(self, host_context) -> None:
        self.manager = getattr(host_context, "kb_manager", None)
        database = getattr(getattr(self.manager, "kb_db", None), "db_path", None)
        self.data_root = Path(database).parent.parent if database else None

    async def list_sources(self):
        """List official knowledge bases and documents through the host manager."""
        if self.manager is None or not callable(getattr(self.manager, "list_kbs", None)):
            return []
        result = []
        for kb in await self.manager.list_kbs():
            kb_id = str(getattr(kb, "kb_id", "") or "").strip()
            if not kb_id:
                continue
            documents = []
            try:
                helper = await self.manager.get_kb(kb_id)
                if helper is not None and not getattr(helper, "init_error", None):
                    count = await helper.count_documents()
                    docs = await helper.list_documents(offset=0, limit=min(max(count, 1), 5000))
                else:
                    database = self.manager.kb_db
                    count = await database.count_documents_by_kb(kb_id)
                    docs = await database.list_documents_by_kb(kb_id, offset=0, limit=min(max(count, 1), 5000))
                documents = [
                    {"id": f"doc:{kb_id}:{doc.doc_id}", "doc_id": str(doc.doc_id),
                     "name": str(doc.doc_name or doc.doc_id), "file_type": str(doc.file_type or ""),
                     "chunk_count": int(doc.chunk_count or 0)}
                    for doc in docs if str(getattr(doc, "doc_id", "") or "").strip()
                ]
            except Exception:
                documents = []
            result.append({
                "id": f"kb:{kb_id}", "type": "knowledge_base", "kb_id": kb_id,
                "name": str(getattr(kb, "kb_name", "") or kb_id),
                "description": str(getattr(kb, "description", "") or "")[:500],
                "emoji": str(getattr(kb, "emoji", "") or "")[:8],
                "doc_count": int(getattr(kb, "doc_count", 0) or len(documents)),
                "chunk_count": int(getattr(kb, "chunk_count", 0) or 0),
                "documents": documents,
            })
        return result

    def candidates(self, source_ids, *, source_limit=16, entry_limit=500,
                   entry_char_limit=1200, char_budget=60000):
        """Return bounded chunks for the selected official sources, without importing them."""
        if self.data_root is None:
            return ()
        identifiers = []
        for value in source_ids or ():
            identifier = str(value or "").strip()
            if identifier.startswith(SOURCE_PREFIXES) and identifier not in identifiers:
                identifiers.append(identifier)
            if len(identifiers) >= max(1, int(source_limit)):
                break
        if not identifiers or entry_limit < 1 or entry_char_limit < 1 or char_budget < 1:
            return ()

        selected_kbs = {item[3:] for item in identifiers if item.startswith("kb:")}
        selected_docs = {}
        for item in identifiers:
            if item.startswith("doc:"):
                parts = item.split(":", 2)
                if len(parts) == 3 and parts[1] not in selected_kbs:
                    selected_docs.setdefault(parts[1], set()).add(parts[2])
        ordered_kbs = list(dict.fromkeys(
            [item[3:] for item in identifiers if item.startswith("kb:")]
            + [item.split(":", 2)[1] for item in identifiers if item.startswith("doc:") and len(item.split(":", 2)) == 3]
        ))

        try:
            available = available_source_ids(self.data_root)
            names = self._names(ordered_kbs)
        except (OSError, sqlite3.Error):
            return ()
        reader = KnowledgeSourceReader(self.data_root)
        candidates = []
        used_chars = 0
        remaining_entries = int(entry_limit)
        for kb_id in ordered_kbs:
            if not kb_id or f"kb:{kb_id}" not in available:
                continue
            doc_filter = None if kb_id in selected_kbs else selected_docs.get(kb_id, set())
            if doc_filter is not None and not doc_filter:
                continue
            source_ids_for_kb = [f"kb:{kb_id}"] if doc_filter is None else [
                f"doc:{kb_id}:{doc_id}" for doc_id in sorted(doc_filter)
                if f"doc:{kb_id}:{doc_id}" in available
            ]
            for source_id in source_ids_for_kb:
                try:
                    rows = reader._knowledge_rows(source_id, limit=remaining_entries)
                except (OSError, sqlite3.Error):
                    continue
                for chunk in parse_knowledge_rows(rows or (), knowledge_base_id=kb_id).items:
                    content = chunk.text[:entry_char_limit]
                    if not content:
                        continue
                    remaining = char_budget - used_chars
                    if remaining <= 0:
                        return tuple(candidates)
                    content = content[:remaining]
                    if not content:
                        return tuple(candidates)
                    document_name = chunk.document_name or self._document_names.get(
                        (kb_id, chunk.document_id), chunk.document_id or "资料")
                    candidates.append(KnowledgeCandidate(
                        f"astrbot:{kb_id}:{chunk.document_id}:{chunk.chunk_index}", content,
                        knowledge_base_id=kb_id, document_id=chunk.document_id,
                        document_name=document_name, chunk_index=chunk.chunk_index,
                        name=names.get(kb_id, kb_id),
                    ))
                    used_chars += len(content)
                    remaining_entries -= 1
                    if remaining_entries <= 0:
                        return tuple(candidates)
        return tuple(candidates)

    def _names(self, kb_ids):
        database = self.data_root / KNOWLEDGE_BASE_DIR / "kb.db"
        connection = _connect(database)
        try:
            placeholders = ",".join("?" for _ in kb_ids)
            self._document_names = {}
            if not kb_ids:
                return {}
            bases = connection.execute(
                f"select kb_id, kb_name from knowledge_bases where kb_id in ({placeholders})", kb_ids).fetchall()
            docs = connection.execute(
                f"select kb_id, doc_id, doc_name from kb_documents where kb_id in ({placeholders})", kb_ids).fetchall()
            self._document_names = {(row["kb_id"], row["doc_id"]): row["doc_name"] for row in docs}
            return {row["kb_id"]: row["kb_name"] for row in bases}
        finally:
            connection.close()


def attach_official_knowledge(application, host_context):
    """Inject the host-side reader into the core conversation collaborator."""
    sources = AstrBotKnowledgeSources(host_context)
    messages = getattr(application, "messages", None)
    knowledge = getattr(messages, "knowledge", None)
    if knowledge is not None and sources.manager is not None:
        knowledge.official_candidate_reader = sources.candidates
    return sources


def import_configured_sources(runtime, *, data_root, binding: SourceBinding, at, settings=None):
    """One start-up or on-demand refresh; returns per-source results, never raises.

    The host calls this from its own lifecycle or a management command; nothing
    here runs inside a conversation turn.
    """
    from companion_v2.knowledge.importer import ImportStatus

    if at is None:
        raise ValueError("import requires an explicit observation time")
    settings = settings if settings is not None else read_installation_settings(
        runtime, binding.installation_id)
    plan = import_plan(data_root, binding, settings)
    if plan is None:
        return ()
    importer = KnowledgeImporter(KnowledgeCatalog(runtime), entry_limit=settings.entry_limit,
                                 content_chars=settings.entry_char_limit)
    try:
        return importer.import_all(plan, at=at)
    except Exception:
        # Import is additive background work: a storage problem must not take the
        # host lifecycle down, and the previous revisions stay readable.
        from companion_v2.knowledge.importer import ImportResult
        return tuple(ImportResult(spec.source_id, ImportStatus.INVALID, code="import_unavailable")
                     for spec in plan.specs)


def _connect(path: Path):
    connection = sqlite3.connect(readonly_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    return connection


__all__ = [
    "AstrBotKnowledgeSources", "KNOWLEDGE_BASE_DIR", "KnowledgeSourceReader", "SOURCE_PREFIXES", "WORLDBOOK_DEFAULTS",
    "attach_official_knowledge",
    "available_source_ids", "import_configured_sources", "import_plan", "knowledge_base_ids",
    "worldbook_paths",
]
