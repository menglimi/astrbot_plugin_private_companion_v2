"""Additive voice storage upgrades with exact prior data and rollback receipts."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageRuntime, StorageOpenError
from companion_v2.storage.schema import SCHEMA_VERSION, SCHEMA_VERSION_V28, SCHEMA_VERSION_V29
from tests.execution_support import remove_v29


class AudioMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="v2-audio-upgrade-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "v2"
        runtime = self.open()
        self.database = runtime.database_path
        with runtime.transaction() as db:
            db.execute("INSERT INTO runtime_metadata VALUES ('original-data', '中文旧记录')")
        runtime.close()
        with closing(sqlite3.connect(self.database)) as db, db:
            remove_v29(db)
            db.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V28,))

    def open(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="voice-upgrade")
        self.addCleanup(runtime.close)
        return runtime

    def test_v28_upgrade_and_restart_preserve_old_records_and_one_migration(self):
        runtime = self.open()
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())[0], SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'original-data'", ())[0], "中文旧记录")
        self.assertEqual(runtime.read_one("SELECT COUNT(*) FROM conversation_audio_payloads", ())[0], 0)
        receipt = tuple(runtime.read_one("SELECT * FROM schema_migrations WHERE to_version = ?", (SCHEMA_VERSION,)))
        runtime.close()
        self.assertEqual(tuple(self.open().read_one("SELECT * FROM schema_migrations WHERE to_version = ?", (SCHEMA_VERSION,))), receipt)

    def test_upgrade_failure_rolls_back_table_version_and_receipt(self):
        original = StorageRuntime._migrate_v28_to_v29
        def fail(runtime, db):
            original(runtime, db)
            raise StorageOpenError("interrupted voice upgrade")
        with patch.object(StorageRuntime, "_migrate_v28_to_v29", fail), self.assertRaises(StorageOpenError):
            self.open()
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V28)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name = 'conversation_audio_payloads'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE to_version = ?", (SCHEMA_VERSION,)).fetchone())
        self.open()

    def test_partial_table_and_untrusted_receipt_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TABLE conversation_audio_payloads (wrong TEXT)")
        with self.assertRaisesRegex(StorageOpenError, "incomplete v28-to-v29"):
            self.open()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("DROP TABLE conversation_audio_payloads")
        self.open().close()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE to_version = ?", (SCHEMA_VERSION_V29,))
        with self.assertRaisesRegex(StorageOpenError, "untrusted v29"):
            self.open()
