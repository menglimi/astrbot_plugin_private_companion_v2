"""Inventory V2-owned files and apply a bounded snapshot retention policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4


DEFAULT_RETENTION_COUNT = 10
DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_COUNT, MAX_RETENTION_COUNT = 1, 200
MIN_RETENTION_DAYS, MAX_RETENTION_DAYS = 1, 3650
_SNAPSHOT_ID = re.compile(r"^[0-9a-f]{32}$")


def _is_link(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(junction) and junction())


def retention_policy(config: object) -> dict[str, int]:
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    if not isinstance(storage, dict):
        storage = {}
    count, days = storage.get("retention_count", DEFAULT_RETENTION_COUNT), storage.get(
        "retention_days", DEFAULT_RETENTION_DAYS)
    if type(count) is not int or not MIN_RETENTION_COUNT <= count <= MAX_RETENTION_COUNT:
        count = DEFAULT_RETENTION_COUNT
    if type(days) is not int or not MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS:
        days = DEFAULT_RETENTION_DAYS
    return {"retention_count": count, "retention_days": days}


def _snapshot_records(data_root: Path, *, backup_directory: Path | None = None,
                      installation_id: str | None = None) -> list[dict]:
    from .backup import BACKUP_FORMAT

    records = []
    root = Path(data_root)
    directories = (Path(backup_directory),) if backup_directory is not None else (
        tuple(path for path in root.rglob("backups") if path.is_dir() and not _is_link(path))
        if root.is_dir() else ()
    )
    for directory in directories:
        if not directory.is_dir() or _is_link(directory):
            continue
        for sidecar in directory.glob("companion-v2-*.json"):
            if _is_link(sidecar):
                continue
            try:
                document = json.loads(sidecar.read_text(encoding="utf-8"))
                snapshot_id = document.get("snapshot_id")
                if (document.get("format") != BACKUP_FORMAT or type(snapshot_id) is not str
                        or not _SNAPSHOT_ID.fullmatch(snapshot_id)
                        or (installation_id is not None and document.get("installation_id") != installation_id)):
                    continue
                database = sidecar.with_name(f"companion-v2-{snapshot_id}.sqlite3")
                if not database.is_file() or _is_link(database):
                    continue
                created_at = datetime.fromisoformat(str(document.get("created_at", "")).replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    continue
                records.append({"snapshot_id": snapshot_id, "created_at": created_at.astimezone(timezone.utc),
                                "database": database, "sidecar": sidecar,
                                "byte_size": database.stat().st_size + sidecar.stat().st_size})
            except (OSError, ValueError, TypeError, AttributeError):
                continue
    records.sort(key=lambda item: item["created_at"], reverse=True)
    return records


def cleanup_plan(data_root: Path, *, retention_count: int, retention_days: int,
                 now: datetime | None = None, backup_directory: Path | None = None,
                 installation_id: str | None = None) -> dict:
    """Return complete snapshots outside policy, always keeping the newest one."""
    records = _snapshot_records(Path(data_root), backup_directory=backup_directory,
                                installation_id=installation_id)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("cleanup time must include a timezone")
    cutoff = current.astimezone(timezone.utc) - timedelta(days=retention_days)
    removed = [item for index, item in enumerate(records)
               if index > 0 and (index >= retention_count or item["created_at"] < cutoff)]
    return {"snapshot_count": len(records), "remove_count": len(removed),
            "remove_bytes": sum(item["byte_size"] for item in removed),
            "snapshot_ids": [item["snapshot_id"] for item in removed]}


def cleanup_backups(data_root: Path, *, retention_count: int, retention_days: int,
                    now: datetime | None = None, backup_directory: Path | None = None,
                    installation_id: str | None = None) -> dict:
    """Delete only complete, verified-by-manifest snapshot pairs outside policy."""
    records = _snapshot_records(Path(data_root), backup_directory=backup_directory,
                                installation_id=installation_id)
    plan = cleanup_plan(Path(data_root), retention_count=retention_count,
                        retention_days=retention_days, now=now, backup_directory=backup_directory,
                        installation_id=installation_id)
    candidates = set(plan["snapshot_ids"])
    removed_count = removed_bytes = 0
    for item in records:
        if item["snapshot_id"] not in candidates:
            continue
        size = item["byte_size"]
        item["database"].unlink()
        item["sidecar"].unlink()
        removed_count += 1
        removed_bytes += size
    return {**plan, "removed_count": removed_count, "removed_bytes": removed_bytes}


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_backup_snapshots(source: Path, destination: Path, *,
                          installation_id: str | None = None) -> tuple[tuple[Path, Path], ...]:
    """Copy complete named snapshot pairs, verifying bytes before a config switch."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        return ()
    if destination.exists() and not destination.is_dir():
        raise OSError("backup destination is not a directory")
    destination.mkdir(parents=True, exist_ok=True)
    if not source.is_dir() or _is_link(source):
        return ()

    transferred = []
    for sidecar in sorted(source.glob("companion-v2-*.json")):
        if _is_link(sidecar):
            continue
        snapshot_id = sidecar.stem.removeprefix("companion-v2-")
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            continue
        try:
            manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if installation_id is not None and manifest.get("installation_id") != installation_id:
            continue
        database = sidecar.with_name(f"companion-v2-{snapshot_id}.sqlite3")
        if not database.is_file() or _is_link(database):
            continue
        pair = []
        for current in (database, sidecar):
            target = destination / current.name
            if target.exists():
                if not target.is_file() or _is_link(target) or _file_digest(current) != _file_digest(target):
                    raise FileExistsError(f"backup snapshot conflicts at {target.name}")
            else:
                temporary = destination / ("." + current.name + "." + uuid4().hex + ".tmp")
                try:
                    shutil.copy2(current, temporary)
                    if current.stat().st_size != temporary.stat().st_size or _file_digest(current) != _file_digest(temporary):
                        raise OSError("backup snapshot copy verification failed")
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            pair.append(current)
        transferred.append((pair[0], pair[1]))
    return tuple(transferred)


def remove_transferred_backup_snapshots(pairs: tuple[tuple[Path, Path], ...], destination: Path) -> int:
    """Remove source pairs only when the verified destination still matches."""
    destination = Path(destination).resolve()
    removed = 0
    for database, sidecar in pairs:
        targets = (destination / database.name, destination / sidecar.name)
        if not all(target.is_file() and not _is_link(target) and _file_digest(source) == _file_digest(target)
                   for source, target in zip((database, sidecar), targets)):
            continue
        database.unlink()
        sidecar.unlink()
        removed += 1
    return removed


def backup_directories(data_root: Path) -> tuple[Path, ...]:
    root = Path(data_root)
    if not root.is_dir():
        return ()
    return tuple(sorted((path for path in root.rglob("backups") if path.is_dir() and not _is_link(path)),
                        key=lambda item: item.as_posix()))


def cleanup_all_backups(data_root: Path, *, retention_count: int, retention_days: int,
                        now: datetime | None = None, dry_run: bool = True) -> dict:
    summaries = []
    for directory in backup_directories(data_root):
        if dry_run:
            summary = cleanup_plan(directory.parent, retention_count=retention_count,
                                   retention_days=retention_days, now=now)
        else:
            summary = cleanup_backups(directory.parent, retention_count=retention_count,
                                      retention_days=retention_days, now=now)
        summaries.append(summary)
    remove_count = sum(item["remove_count"] for item in summaries)
    remove_bytes = sum(item["remove_bytes"] for item in summaries)
    return {"directories": len(summaries),
            "snapshot_count": sum(item["snapshot_count"] for item in summaries),
            "remove_count": remove_count, "remove_bytes": remove_bytes,
            "removed_count": sum(item.get("removed_count", 0) for item in summaries),
            "removed_bytes": sum(item.get("removed_bytes", 0) for item in summaries),
            "snapshot_ids": [snapshot_id for item in summaries for snapshot_id in item["snapshot_ids"]]}


def inventory(data_root: Path, *, backup_directory: Path | None = None) -> dict:
    """Measure V2 plugin data without following links or opening user databases."""
    root = Path(data_root)
    totals = {"database": {"files": 0, "bytes": 0},
              "backups": {"files": 0, "bytes": 0},
              "other": {"files": 0, "bytes": 0}}
    if root.is_dir():
        for path in root.rglob("*"):
            if _is_link(path) or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if path.parent.name == "backups":
                group = "backups"
            elif path.name == "companion-v2.sqlite3" or path.name.startswith("companion-v2.sqlite3-"):
                group = "database"
            else:
                group = "other"
            totals[group]["files"] += 1
            totals[group]["bytes"] += size
    extra_backup = Path(backup_directory).resolve() if backup_directory is not None else None
    if extra_backup is not None and not extra_backup.is_relative_to(root.resolve()) and extra_backup.is_dir():
        for path in extra_backup.rglob("*"):
            if _is_link(path) or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            totals["backups"]["files"] += 1
            totals["backups"]["bytes"] += size
    total_bytes = sum(value["bytes"] for value in totals.values())
    anchor = root
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    try:
        free_bytes = shutil.disk_usage(anchor).free
    except OSError:
        free_bytes = None
    backup_anchor = extra_backup if extra_backup is not None else root / "backups"
    while not backup_anchor.exists() and backup_anchor != backup_anchor.parent:
        backup_anchor = backup_anchor.parent
    try:
        backup_free_bytes = shutil.disk_usage(backup_anchor).free
    except OSError:
        backup_free_bytes = None
    return {"root": str(root), "total_bytes": total_bytes,
            "categories": totals, "free_bytes": free_bytes, "backup_free_bytes": backup_free_bytes}
