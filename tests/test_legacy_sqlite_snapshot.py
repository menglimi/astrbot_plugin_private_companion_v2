from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from companion_v2.legacy.sqlite_snapshot import open_readonly_sqlite_snapshot


def _file_state(path: Path):
    if not path.exists():
        return None
    info = path.stat()
    return (info.st_size, info.st_mtime_ns, info.st_ino,
            hashlib.sha256(path.read_bytes()).hexdigest())


class LegacySQLiteSnapshotTests(unittest.TestCase):
    def test_reads_committed_wal_without_changing_source_or_sidecars(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "legacy.db"
            writer = sqlite3.connect(database)
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute("CREATE TABLE entries (value TEXT)")
                writer.execute("INSERT INTO entries VALUES ('committed in wal')")
                writer.commit()
                wal = Path(str(database) + "-wal")
                shm = Path(str(database) + "-shm")
                self.assertGreater(wal.stat().st_size, 0)
                before = {path: _file_state(path)
                          for path in (database, wal, shm)}

                reader = open_readonly_sqlite_snapshot(database)
                try:
                    reader.execute("BEGIN")
                    values = reader.execute("SELECT value FROM entries").fetchall()
                    reader.rollback()
                finally:
                    reader.close()

                self.assertEqual(values, [("committed in wal",)])
                self.assertEqual({path: _file_state(path)
                                  for path in (database, wal, shm)}, before)
            finally:
                writer.close()


if __name__ == "__main__":
    unittest.main()
