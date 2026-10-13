"""A separately named V2 database, opened only by explicit construction."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from .models import ContentError
from .governance import append_retraction

_APPLICATION_ID = 0x43563243
_SCHEMA = (
    """CREATE TABLE content_v2_works (
        owner_key TEXT NOT NULL, work_id TEXT NOT NULL, owner_json TEXT NOT NULL,
        title TEXT NOT NULL, work_type TEXT NOT NULL, author_json TEXT NOT NULL,
        audience_json TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
        head_version TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','retracted')),
        origin_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, work_id))""",
    """CREATE TABLE content_v2_versions (
        owner_key TEXT NOT NULL, work_id TEXT NOT NULL, version_id TEXT NOT NULL,
        base_revision INTEGER NOT NULL, base_version TEXT,
        manuscript_json TEXT NOT NULL, content_hash TEXT NOT NULL,
        origin_json TEXT NOT NULL, contributor_json TEXT NOT NULL,
        sources_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, work_id, version_id),
        FOREIGN KEY(owner_key, work_id) REFERENCES content_v2_works(owner_key, work_id))""",
    """CREATE TABLE content_v2_heads (
        owner_key TEXT NOT NULL, work_id TEXT NOT NULL, revision INTEGER NOT NULL,
        version_id TEXT NOT NULL,
        PRIMARY KEY(owner_key, work_id, revision),
        FOREIGN KEY(owner_key, work_id, version_id)
            REFERENCES content_v2_versions(owner_key, work_id, version_id))""",
    """CREATE TABLE content_v2_operations (
        owner_key TEXT NOT NULL, operation_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, work_id TEXT NOT NULL,
        origin_json TEXT NOT NULL, receipt_json TEXT NOT NULL,
        PRIMARY KEY(owner_key, operation_key),
        FOREIGN KEY(owner_key, work_id) REFERENCES content_v2_works(owner_key, work_id))""",
    "CREATE INDEX content_v2_catalogue ON content_v2_works(owner_key, state, work_id)",
)

_GOVERNANCE_SCHEMA = (
    """CREATE TABLE content_v2_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
        installation_id TEXT NOT NULL, owner_key TEXT NOT NULL, work_id TEXT NOT NULL,
        revision INTEGER NOT NULL, operation_id TEXT NOT NULL UNIQUE,
        event_json TEXT NOT NULL,
        FOREIGN KEY(operation_id) REFERENCES content_v2_operations(operation_id))""",
    "CREATE INDEX content_v2_event_installation ON content_v2_events(installation_id, seq)",
)


class ContentRepository:
    def __init__(self, data_root: Path) -> None:
        self.path = Path(data_root) / "content_v2" / "works.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(self.path, timeout=5, isolation_level=None,
                                           check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys=ON")
            with self.transaction(write=True) as connection:
                application = connection.execute("PRAGMA application_id").fetchone()[0]
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if application == _APPLICATION_ID and version in (1, 2):
                    pass
                elif application == 0 and version == 0 and not connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                    for statement in _SCHEMA:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                    connection.execute("PRAGMA user_version=1")
                    version = 1
                else:
                    raise ContentError("incompatible_database")
                if version == 1:
                    for statement in _GOVERNANCE_SCHEMA:
                        connection.execute(statement)
                    # A pre-event V2 retraction must also remain discoverable.
                    # Its original operation is authoritative, never a V1 input.
                    rows = connection.execute(
                        """SELECT o.receipt_json, w.owner_json FROM content_v2_operations o
                           JOIN content_v2_works w USING(owner_key, work_id)
                           WHERE json_extract(o.receipt_json, '$.action')='retract'
                           ORDER BY o.rowid""",
                    ).fetchall()
                    for row in rows:
                        append_retraction(connection, json.loads(row["owner_json"]),
                                          json.loads(row["receipt_json"]))
                    connection.execute("PRAGMA user_version=2")
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self._connection.close()
            self._closed = True
            raise

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._closed:
                raise ContentError("repository_closed")
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._connection.close()
