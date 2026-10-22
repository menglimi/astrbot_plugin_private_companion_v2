"""Administrator-only inspection of retained work; nothing here can execute it."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3

from .archive import SCHEMA, _safe_relative_path as _safe_relative
from .sqlite_snapshot import open_readonly_sqlite_snapshot


TABLES = {
    "work": ("framework_work/work.db", ("records", "versions", "jobs", "calls", "receipts")),
    "delivery": ("framework_work/delivery.db", ("parts", "notices")),
    "world": ("framework_world/album.db", ("photos", "deletions", "inspections")),
}


def archived_work_inventory(archive_root):
    archives = []
    for path in sorted(Path(archive_root).glob("*/manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("schema") != SCHEMA or path.parent.name != manifest.get("archive_id"):
                continue
            files = {item["path"]: item for item in manifest.get("files", ())}
            areas = {}
            for area, (relative, allowed) in TABLES.items():
                if relative not in files:
                    continue
                database = _safe_relative(path.parent / "files", relative)
                with closing(open_readonly_sqlite_snapshot(database)) as connection:
                    connection.execute("PRAGMA query_only=ON")
                    actual = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    areas[area] = {table: connection.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
                                   for table in allowed if table in actual}
            if areas:
                archives.append({"archive_id": path.parent.name, "complete": manifest.get("complete", False),
                    "created_at": manifest.get("created_at"), "areas": areas,
                    "file_count": manifest.get("file_count"), "excluded_count": len(manifest.get("issues", ()))})
        except (OSError, ValueError, KeyError, sqlite3.Error):
            continue
    return {"archives": archives, "historical_only": True, "execution_restored": False}


def archived_work_rows(archive_root, archive_id, area, table, offset=0):
    if (not isinstance(archive_id, str) or len(archive_id) != 64
            or any(c not in "0123456789abcdef" for c in archive_id)
            or area not in TABLES or table not in TABLES[area][1]
            or type(offset) is not int or not 0 <= offset <= 1000000):
        raise ValueError("legacy_archive_query_invalid")
    directory = _safe_relative(Path(archive_root).resolve(), archive_id)
    manifest = json.loads(_safe_relative(directory, "manifest.json").read_text(encoding="utf-8"))
    relative = TABLES[area][0]
    if (manifest.get("schema") != SCHEMA or manifest.get("archive_id") != archive_id
            or relative not in {row["path"] for row in manifest.get("files", ())}):
        raise ValueError("legacy_archive_source_unavailable")
    database = _safe_relative(directory / "files", relative)
    with closing(open_readonly_sqlite_snapshot(database)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute('SELECT * FROM "' + table + '" LIMIT ? OFFSET ?', (11, offset)).fetchall()
    from companion_v2.sources.privacy import redact_text
    items = [{k: redact_text(v) if isinstance(v, str) else v.hex() if isinstance(v, bytes) else v
              for k, v in dict(row).items()} for row in rows[:10]]
    return {"archive_id": archive_id, "area": area, "table": table, "items": items,
            "next_offset": offset + 10 if len(rows) > 10 else None,
            "historical_only": True, "execution_restored": False}
