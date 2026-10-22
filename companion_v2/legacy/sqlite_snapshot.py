"""Open legacy SQLite data without touching its WAL sidecars."""

from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
import stat
from tempfile import TemporaryDirectory

from companion_v2.storage.sqlite_path import readonly_uri


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_SIDECARS = ("-wal", "-journal")


def _file_signature(path: Path, *, optional=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if optional:
            return None
        raise sqlite3.OperationalError("sqlite_snapshot_source_missing")
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or int(getattr(info, "st_file_attributes", 0)) & _REPARSE_POINT):
        raise sqlite3.OperationalError("sqlite_snapshot_source_unsafe")
    return int(info.st_size), int(info.st_mtime_ns), int(info.st_dev), int(info.st_ino)


def _source_signature(path: Path):
    return (_file_signature(path),
            *(_file_signature(Path(str(path) + suffix), optional=True) for suffix in _SIDECARS))


class _ReadonlySnapshotConnection(sqlite3.Connection):
    def close(self):
        if getattr(self, "_snapshot_closed", False):
            return
        self._snapshot_closed = True
        close_error = None
        try:
            super().close()
        except BaseException as error:
            close_error = error

        changed = False
        try:
            source_path = getattr(self, "_snapshot_source_path", None)
            source_signature = getattr(self, "_snapshot_source_signature", None)
            if source_path is not None and source_signature is not None:
                changed = _source_signature(source_path) != source_signature
        except (OSError, sqlite3.Error):
            changed = True
        finally:
            snapshot = getattr(self, "_snapshot_directory", None)
            if snapshot is not None:
                snapshot.cleanup()

        if close_error is not None:
            raise close_error
        if changed:
            raise sqlite3.OperationalError("sqlite_snapshot_source_changed")


def open_readonly_sqlite_snapshot(path: str | Path, *, timeout=5.0):
    """Return a query-only connection backed by a stable SQLite file snapshot.

    A database without a live WAL or rollback journal can be opened as immutable.
    When sidecar data is present, the database and journal are copied to a private
    temporary directory so SQLite can rebuild its SHM index there.
    """
    candidate = Path(path).expanduser()
    before = _source_signature(candidate)
    source = candidate.resolve(strict=True)
    active_sidecar = any(signature is not None and signature[0] > 0
                         for signature in before[1:])
    snapshot_directory = None
    connect_path = source

    if active_sidecar:
        snapshot_directory = TemporaryDirectory(prefix="companion-sqlite-snapshot-")
        connect_path = Path(snapshot_directory.name) / source.name
        try:
            for suffix, signature in zip(("", *_SIDECARS), before):
                if signature is None or (suffix and signature[0] == 0):
                    continue
                source_file = Path(str(source) + suffix)
                shutil.copyfile(source_file, Path(str(connect_path) + suffix))
            if _source_signature(source) != before:
                raise sqlite3.OperationalError("sqlite_snapshot_source_changed")
        except BaseException:
            snapshot_directory.cleanup()
            raise
        uri = readonly_uri(connect_path)
    else:
        uri = readonly_uri(source) + "&immutable=1"

    try:
        connection = sqlite3.connect(uri, uri=True, timeout=timeout,
                                     factory=_ReadonlySnapshotConnection)
        connection._snapshot_source_path = source
        connection._snapshot_source_signature = before
        connection._snapshot_directory = snapshot_directory
        connection._snapshot_closed = False
        connection.execute("PRAGMA query_only=ON")
        if _source_signature(source) != before:
            connection.close()
            raise sqlite3.OperationalError("sqlite_snapshot_source_changed")
        return connection
    except BaseException:
        if "connection" in locals():
            connection.close()
        elif snapshot_directory is not None:
            snapshot_directory.cleanup()
        raise
