"""Temporary SQLite support for isolated tests.

The helper owns its directory and never accepts a caller-provided path, which keeps G0
tests away from V1 and host data roots.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@dataclass
class TemporarySQLiteDatabase:
    """An automatically cleaned SQLite database located under the system temp root."""

    _directory: TemporaryDirectory[str]
    path: Path
    connection: sqlite3.Connection

    @classmethod
    def create(cls) -> "TemporarySQLiteDatabase":
        directory = TemporaryDirectory(prefix="companion-v2-g0-")
        path = Path(directory.name) / "state.sqlite3"
        connection = sqlite3.connect(str(path))
        connection.execute("PRAGMA foreign_keys = ON")
        return cls(_directory=directory, path=path, connection=connection)

    def close(self) -> None:
        self.connection.close()
        self._directory.cleanup()

    def __enter__(self) -> "TemporarySQLiteDatabase":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


def temporary_sqlite_database() -> TemporarySQLiteDatabase:
    """Create a new isolated database for a test or deterministic fixture builder."""

    return TemporarySQLiteDatabase.create()
