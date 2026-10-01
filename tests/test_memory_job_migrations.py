"""Nonempty v27 upgrades preserve old batches without adopting them as work."""

from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION
from tests.execution_support import remove_v28
from tests.test_memory_selection import SelectionFixture


class MemoryJobMigrationTests(SelectionFixture, unittest.TestCase):
    def historical(self):
        self.evidence()
        batch = self.prepare()["batch_id"]
        saved = dict(self.row(batch))
        database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(database)) as db, db:
            remove_v28(db)
            db.execute("UPDATE runtime_metadata SET value = 'companion-v2.storage.v27' WHERE key = 'schema_version'")
        return database, batch, saved

    def open(self):
        runtime = StorageRuntime.open(data_root=self.runtime.data_root, installation_id=self.runtime.installation_id)
        self.addCleanup(runtime.close)
        return runtime

    def test_nonempty_v27_upgrades_without_adopting_prepared_reflections(self):
        _, batch, saved = self.historical()
        runtime = self.open()
        self.assertEqual(dict(runtime.read_one("SELECT * FROM memory_reflections WHERE batch_id = ?", (batch,))), saved)
        self.assertEqual(runtime.read_one("SELECT COUNT(*) n FROM memory_reflection_jobs", ())["n"], 0)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())[0], SCHEMA_VERSION)
        runtime.close()
        self.assertEqual(self.open().read_one("SELECT COUNT(*) n FROM memory_reflections", ())["n"], 1)

    def test_upgrade_failure_rolls_back_schema_and_original_batch(self):
        database, batch, saved = self.historical()
        original = StorageRuntime._migrate_v27_to_v28
        def interrupted(runtime, db):
            original(runtime, db)
            raise StorageOpenError("interrupted v28")
        with patch.object(StorageRuntime, "_migrate_v27_to_v28", interrupted), self.assertRaisesRegex(StorageOpenError, "interrupted"):
            self.open()
        with closing(sqlite3.connect(database)) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory_reflection_jobs'").fetchone())
            self.assertEqual(db.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], "companion-v2.storage.v27")
            self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v27-to-v28'").fetchone())
        self.assertEqual(dict(self.open().read_one("SELECT * FROM memory_reflections WHERE batch_id = ?", (batch,))), saved)

    def test_partial_upgrade_and_changed_receipt_are_rejected(self):
        database, _, _ = self.historical()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE memory_reflection_jobs (job_id TEXT)")
        with self.assertRaisesRegex(StorageOpenError, "incomplete v27-to-v28"):
            self.open()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TABLE memory_reflection_jobs")
        self.open().close()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE schema_migrations SET fingerprint = 'wrong' WHERE migration_id = 'companion-v2.storage.v27-to-v28'")
        with self.assertRaisesRegex(StorageOpenError, "untrusted v28"):
            self.open()
