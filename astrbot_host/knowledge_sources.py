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

from companion_v2.knowledge.catalog import KnowledgeCatalog, SourceBinding
from companion_v2.knowledge.configuration import read_installation_settings
from companion_v2.knowledge.importer import (
    ImportPlan,
    KnowledgeFormat,
    KnowledgeImporter,
    KnowledgeSourceSpec,
)


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

    def _knowledge_rows(self, identifier: str):
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
                decoded = json.loads(metadata) if isinstance(metadata, str) else metadata
                if doc_id is not None and str((decoded or {}).get("kb_doc_id") or "") != doc_id:
                    continue
                rows.append({"text": row["text"], "metadata": decoded})
        finally:
            connection.close()
        return rows


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
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


__all__ = [
    "KNOWLEDGE_BASE_DIR", "KnowledgeSourceReader", "SOURCE_PREFIXES", "WORLDBOOK_DEFAULTS",
    "available_source_ids", "import_configured_sources", "import_plan", "knowledge_base_ids",
    "worldbook_paths",
]
