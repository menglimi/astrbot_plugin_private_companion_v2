"""Whole-installation backup and restore for the V2 data root.

Two rules shape this module.

First, a snapshot is taken with ``VACUUM INTO``, never by copying the database
file. The runtime opens SQLite in WAL mode, so committed frames can still live in
the ``-wal`` sidecar; copying only ``companion-v2.sqlite3`` would silently drop
recent commits. ``VACUUM INTO`` runs inside one read transaction and emits a
compact single-file snapshot with no sidecar to forget.

Second, restore does not rebuild the live connection. ``StorageRuntime`` holds one
shared connection opened at plugin load, and every repository, service and task in
the tree borrows it. Swapping the file under a running process would leave all of
them pointing at a closed database. A restore therefore stages the verified
candidate, records a pending request, refuses further writes, and reports that the
host must restart to reopen the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.outcome import Outcome
from .management import cleanup_backups


BACKUP_FORMAT = "companion-v2.installation-backup.v1"
BACKUP_DIRECTORY = "backups"
PENDING_FILENAME = "restore-pending.json"
MAX_SNAPSHOT_BYTES = 1024 * 1024 * 1024

# A preview reports how much data a restore would replace. These are the tables a
# reader can compare by row count without interpreting any domain meaning.
COUNTED_TABLES = ("memory_atoms", "operations", "configuration_values")

# A snapshot is refused when it claims another installation or another schema
# revision: both mean it cannot faithfully replace this data root.
_REQUIRED_METADATA = ("installation_id", "schema_version")


class BackupError(TaskError):
    """A snapshot or restore request cannot be trusted or completed."""


@dataclass(frozen=True)
class SnapshotManifest:
    """The provenance of one snapshot, as recorded beside it."""

    snapshot_id: str
    created_at: str
    installation_id: str
    schema_version: str
    byte_size: int
    content_hash: str
    note: str

    def document(self) -> dict:
        return {
            "format": BACKUP_FORMAT,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "installation_id": self.installation_id,
            "schema_version": self.schema_version,
            "byte_size": self.byte_size,
            "content_hash": self.content_hash,
            "note": self.note,
        }


def _sha256(path: Path) -> str:
    accumulator = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            accumulator.update(block)
    return accumulator.hexdigest()


def _stamp(at: datetime) -> str:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise BackupError("backup_clock_invalid", "a backup needs a timezone-aware clock")
    return at.astimezone(timezone.utc).isoformat()


def _read_metadata(connection: sqlite3.Connection) -> dict:
    """Read the identity rows a snapshot must carry to be restorable here."""
    try:
        rows = connection.execute(
            "SELECT key, value FROM runtime_metadata WHERE key IN (?, ?)", _REQUIRED_METADATA,
        ).fetchall()
    except sqlite3.Error as error:
        raise BackupError("backup_snapshot_unreadable", "the snapshot is not a V2 data root") from error
    found = {row["key"]: row["value"] for row in rows}
    if set(found) != set(_REQUIRED_METADATA):
        raise BackupError("backup_snapshot_incomplete", "the snapshot is missing its installation identity")
    return found


def _inspect(path: Path, *, installation_id: str, schema_version: str) -> dict:
    """Open a candidate read-only and prove it can replace this data root."""
    if not path.is_file():
        raise BackupError("backup_snapshot_missing", "the named snapshot does not exist")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise BackupError("backup_snapshot_unreadable", "the snapshot cannot be read") from error
    if size <= 0 or size > MAX_SNAPSHOT_BYTES:
        raise BackupError("backup_snapshot_size_invalid", "the snapshot size is outside the accepted range")
    # A read-only URI keeps inspection from creating or migrating anything, and a
    # wall clock bounds a hang instead of relying on a busy timeout.
    try:
        from .sqlite_path import readonly_uri
        connection = sqlite3.connect(readonly_uri(path), uri=True, timeout=10.0)
    except sqlite3.Error as error:
        raise BackupError("backup_snapshot_unreadable", "the snapshot is not a readable SQLite database") from error
    try:
        connection.row_factory = sqlite3.Row
        if [tuple(row) for row in connection.execute("PRAGMA quick_check")] != [("ok",)]:
            raise BackupError("backup_snapshot_corrupt", "the snapshot failed its integrity check")
        metadata = _read_metadata(connection)
        if metadata["installation_id"] != installation_id:
            raise BackupError("backup_snapshot_foreign", "the snapshot belongs to another installation")
        if metadata["schema_version"] != schema_version:
            raise BackupError("backup_snapshot_schema_mismatch", "the snapshot schema revision differs from this data root")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("backup_snapshot_broken_references", "the snapshot contains broken references")
        table_count = connection.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
        ).fetchone()["n"]
    except sqlite3.Error as error:
        raise BackupError("backup_snapshot_unreadable", "the snapshot could not be verified") from error
    finally:
        connection.close()
    return {"byte_size": size, "table_count": table_count,
            "installation_id": metadata["installation_id"], "schema_version": metadata["schema_version"]}


class InstallationBackup:
    """Snapshot and restore one V2 installation's complete database."""

    def __init__(self, runtime, *, now=None, retention_count=10, retention_days=90,
                 directory: Path | None = None):
        self.runtime = runtime
        self.now = now
        self.retention_count = retention_count
        self.retention_days = retention_days
        self._directory = Path(directory) if directory is not None else None

    # -- paths -----------------------------------------------------------

    @property
    def directory(self) -> Path:
        return self._directory or Path(getattr(self.runtime, "backup_directory", None)
                                       or self.runtime.data_root / BACKUP_DIRECTORY)

    @property
    def pending_path(self) -> Path:
        return self.runtime.data_root / PENDING_FILENAME

    def _snapshot_path(self, snapshot_id: str) -> Path:
        if not snapshot_id or any(character not in "0123456789abcdef" for character in snapshot_id):
            raise BackupError("backup_snapshot_id_invalid", "a snapshot id is a lowercase hex digest")
        return self.directory / f"companion-v2-{snapshot_id}.sqlite3"

    def _at(self) -> datetime:
        value = self.now() if self.now is not None else datetime.now(timezone.utc)
        _stamp(value)
        return value

    def _schema_version(self) -> str:
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", ("schema_version",))
        if row is None:
            raise BackupError("backup_metadata_missing", "this data root has no schema version")
        return row["value"]

    # -- snapshot --------------------------------------------------------

    def create(self, *, note: str = "") -> Outcome:
        """Write one verified snapshot and return its manifest."""
        try:
            manifest = self._create(note=note)
            try:
                cleanup = cleanup_backups(self.runtime.data_root, retention_count=self.retention_count,
                                          retention_days=self.retention_days, now=self._at(),
                                          backup_directory=self.directory,
                                          installation_id=self.runtime.installation_id)
            except OSError:
                cleanup = {"removed_count": 0, "removed_bytes": 0, "failed": True}
            return Outcome.success({**manifest, "retention": cleanup})
        except BackupError as error:
            return Outcome.failed(error.code, str(error))

    def _create(self, *, note: str) -> dict:
        if type(note) is not str or len(note) > 200:
            raise BackupError("backup_note_invalid", "a backup note is at most 200 characters")
        at = self._at()
        self.directory.mkdir(parents=True, exist_ok=True)
        snapshot_id = digest([self.runtime.installation_id, _stamp(at), note])[:32]
        target = self._snapshot_path(snapshot_id)
        if target.exists():
            target.unlink()
        # The online backup API, not VACUUM INTO and not a file copy. VACUUM is a
        # write and the runtime's read snapshot forbids writes; a file copy would
        # miss committed frames still held in the WAL sidecar. The backup API reads
        # the live database under its own lock and emits a consistent single file.
        try:
            with self.runtime.read_snapshot() as source:
                destination = sqlite3.connect(str(target))
                try:
                    source.backup(destination)
                    destination.commit()
                finally:
                    destination.close()
        except (sqlite3.Error, OSError) as error:
            if target.exists():
                target.unlink()
            raise BackupError("backup_write_failed", "the snapshot could not be written") from error
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id, created_at=_stamp(at),
            installation_id=self.runtime.installation_id, schema_version=self._schema_version(),
            byte_size=target.stat().st_size, content_hash=_sha256(target), note=note,
        )
        document = json.dumps(manifest.document(), ensure_ascii=False, sort_keys=True)
        # The sidecar is written last: its presence is what marks a snapshot complete.
        target.with_suffix(".json").write_text(document, encoding="utf-8")
        return manifest.document()

    def listing(self) -> Outcome:
        """List completed snapshots, newest first."""
        try:
            if not self.directory.is_dir():
                return Outcome.success({"snapshots": ()})
            documents = []
            for sidecar in sorted(self.directory.glob("companion-v2-*.json")):
                try:
                    document = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                # A sidecar without its database is a pruned or interrupted backup.
                if document.get("format") != BACKUP_FORMAT or not _completed_snapshot(self, document):
                    continue
                documents.append(document)
            documents.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return Outcome.success({"snapshots": documents})
        except BackupError as error:
            return Outcome.failed(error.code, str(error))

    def inspect(self, *, snapshot_id: str) -> Outcome:
        """Verify one named snapshot without restoring it."""
        try:
            path = self._snapshot_path(snapshot_id)
            details = _inspect(path, installation_id=self.runtime.installation_id,
                               schema_version=self._schema_version())
            manifest = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            if manifest.get("content_hash") != _sha256(path):
                raise BackupError("backup_snapshot_changed", "the snapshot no longer matches its recorded digest")
            return Outcome.success({"manifest": manifest, "verified": details})
        except (BackupError, OSError, ValueError) as error:
            code = error.code if isinstance(error, BackupError) else "backup_snapshot_unreadable"
            return Outcome.failed(code, str(error))

    # -- restore ---------------------------------------------------------

    def preview_restore(self, *, snapshot_id: str) -> Outcome:
        """Verify a snapshot and report what a restore would replace."""
        verified = self.inspect(snapshot_id=snapshot_id)
        if not verified.is_success:
            return verified
        try:
            counts = {}
            with self.runtime.read_only_snapshot() as connection:
                for table in COUNTED_TABLES:
                    row = connection.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()
                    counts[table] = row["n"] if row is not None else 0
            return Outcome.success({"snapshot_id": snapshot_id, "current": counts,
                                    "verified": verified.unwrap()["verified"],
                                    "effect": "requires_restart"})
        except sqlite3.Error as error:
            return Outcome.failed("backup_preview_failed", str(error))

    def restore(self, *, snapshot_id: str, confirmed_hash: str) -> Outcome:
        """Stage a restore. The host must restart before it takes effect."""
        try:
            verified = self.inspect(snapshot_id=snapshot_id)
            if not verified.is_success:
                return verified
            manifest = verified.unwrap()["manifest"]
            # The operator confirms the exact bytes they were shown. A snapshot that
            # changed between preview and confirmation is refused rather than applied.
            if type(confirmed_hash) is not str or confirmed_hash != manifest["content_hash"]:
                raise BackupError("backup_confirmation_mismatch", "the confirmed digest does not match this snapshot")
            if self.pending_path.exists():
                raise BackupError("backup_restore_pending", "a restore is already waiting for a restart")
            at = _stamp(self._at())
            # Keep the data being replaced. A failed restart is otherwise unrecoverable.
            safety = self._create(note=f"pre-restore safety copy of {snapshot_id}")
            self.pending_path.write_text(json.dumps({
                "format": BACKUP_FORMAT, "snapshot_id": snapshot_id,
                "content_hash": manifest["content_hash"], "requested_at": at,
                "safety_snapshot_id": safety["snapshot_id"],
            }, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            return Outcome.success({"snapshot_id": snapshot_id, "staged_at": at,
                                    "safety_snapshot_id": safety["snapshot_id"],
                                    "effect": "restart_required",
                                    "note": "the data root is unchanged until the host restarts"})
        except BackupError as error:
            return Outcome.failed(error.code, str(error))
        except OSError as error:
            return Outcome.failed("backup_restore_failed", str(error))

    def pending(self) -> Outcome:
        """Report a staged restore, if any."""
        try:
            if not self.pending_path.is_file():
                return Outcome.success({"pending": None})
            return Outcome.success({"pending": json.loads(self.pending_path.read_text(encoding="utf-8"))})
        except (OSError, ValueError) as error:
            return Outcome.failed("backup_pending_unreadable", str(error))


def current_schema_version(data_root: Path) -> str | None:
    """Read a data root's stored schema revision without opening it for writing.

    Restore runs before ``StorageRuntime.open``, so it cannot ask a runtime. It
    also must not open the database read-write: that would create the file and run
    migrations against the very data root about to be replaced.
    """
    database = Path(data_root) / "companion-v2.sqlite3"
    if not database.is_file():
        return None
    try:
        from .sqlite_path import readonly_uri
        connection = sqlite3.connect(readonly_uri(database), uri=True, timeout=10.0)
    except sqlite3.Error:
        return None
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()
        return row["value"] if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def _completed_snapshot(backup: "InstallationBackup", document: dict) -> bool:
    """A snapshot counts only when its database is present and its digest matches."""
    snapshot_id = document.get("snapshot_id")
    if type(snapshot_id) is not str:
        return False
    try:
        path = backup._snapshot_path(snapshot_id)
    except BackupError:
        return False
    if not path.is_file():
        return False
    return document.get("content_hash") == _sha256(path)


def apply_pending(data_root: Path, *, installation_id: str, schema_version: str,
                  backup_directory: Path | None = None) -> dict:
    """Swap in a staged snapshot. Called by the host before the store is opened.

    This runs with no live connection, which is the only moment the database file
    may be replaced safely. Errors are returned rather than raised so a failed
    restore leaves the caller with the original data root and a readable reason.
    """
    try:
        return _apply_pending(data_root, installation_id=installation_id, schema_version=schema_version,
                              backup_directory=backup_directory)
    except BackupError as error:
        return {"applied": False, "reason": error.code, "detail": str(error)}
    except TaskError as error:
        # require() surfaces a malformed staged request as a TaskError. Start-up
        # must survive that: an unreadable request leaves the data root untouched.
        return {"applied": False, "reason": error.code, "detail": str(error)}
    except OSError as error:
        return {"applied": False, "reason": "backup_restore_failed", "detail": str(error)}


def _apply_pending(data_root: Path, *, installation_id: str, schema_version: str,
                   backup_directory: Path | None = None) -> dict:
    pending_path = Path(data_root) / PENDING_FILENAME
    if not pending_path.is_file():
        return {"applied": False, "reason": "no_pending_restore"}
    request = require(_load_pending(pending_path))
    directory = Path(backup_directory) if backup_directory is not None else Path(data_root) / BACKUP_DIRECTORY
    source = directory / f"companion-v2-{request['snapshot_id']}.sqlite3"
    details = _inspect(source, installation_id=installation_id, schema_version=schema_version)
    if _sha256(source) != request["content_hash"] or details["schema_version"] != schema_version:
        raise BackupError("backup_restore_unverified", "the staged snapshot no longer verifies")
    target = Path(data_root) / "companion-v2.sqlite3"
    # Rename is atomic within one filesystem, so a crash mid-swap leaves either the
    # old database or the new one, never a partially written file.
    displaced = target.with_name(target.name + ".replaced")
    if displaced.exists():
        displaced.unlink()
    if target.exists():
        target.replace(displaced)
    # WAL and shared-memory sidecars belong to the database being replaced.
    for suffix in ("-wal", "-shm"):
        stale = Path(str(target) + suffix)
        if stale.exists():
            stale.unlink()
    source.replace(target)
    pending_path.unlink()
    return {"applied": True, "snapshot_id": request["snapshot_id"],
            "replaced_kept_at": displaced.name}


def _load_pending(pending_path: Path) -> Outcome:
    try:
        document = json.loads(pending_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Outcome.failed("backup_pending_unreadable", "the staged restore request cannot be read")
    if (type(document) is not dict or document.get("format") != BACKUP_FORMAT
            or type(document.get("snapshot_id")) is not str or type(document.get("content_hash")) is not str):
        return Outcome.failed("backup_pending_invalid", "the staged restore request is malformed")
    return Outcome.success(document)
