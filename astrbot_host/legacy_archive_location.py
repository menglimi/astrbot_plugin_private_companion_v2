"""Choose a V1 archive directory that cannot become part of the V1 source."""

from __future__ import annotations

from pathlib import Path

from .storage_location import selected_backup_root


def migration_archive_root(controller, source_root: str | Path | None = None) -> Path:
    """Return the external archive location for one migration.

    A configured backup path is preferred. During an in-place 6.7.0 -> 7.0.0
    update the V2 runtime lives below the old plugin directory, so the fallback
    is a sibling of that source directory rather than a child of it.
    """
    runtime = Path(controller.data_root).resolve()
    config = getattr(controller, "config", {})
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    selected = storage.get("backup_path", "") if isinstance(storage, dict) else ""
    external = selected_backup_root(runtime, selected)
    if external is not None:
        return external / "legacy-v1-archives"
    if source_root is not None:
        source = Path(source_root).expanduser().resolve()
        if runtime != source and runtime.is_relative_to(source):
            return source.parent / (f".{source.name}-legacy-v1-archives")
    return runtime / "legacy-v1-archives"


__all__ = ["migration_archive_root"]
