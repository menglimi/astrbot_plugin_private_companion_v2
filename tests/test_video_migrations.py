"""The v29 to v30 video table upgrade preserves older data and rolls back cleanly."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageRuntime, StorageOpenError
from companion_v2.storage.schema import SCHEMA_VERSION, SCHEMA_VERSION_V29, MIGRATION_V29_TO_V30_ID
from tests.execution_support import remove_v30


class VideoMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-video-upgrade-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2"
        runtime = self.open()
        self.database = runtime.database_path
        with runtime.transaction() as db:
            db.execute("INSERT INTO runtime_metadata VALUES ('original-data', '中文旧记录')")
        runtime.close()
        with closing(sqlite3.connect(self.database)) as db, db:
            remove_v30(db)
            db.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V29,))

    def open(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="video-upgrade")
        self.addCleanup(runtime.close)
        return runtime

    def test_v29_upgrade_and_restart_preserve_old_records_and_one_migration(self):
        runtime = self.open()
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())[0], SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'original-data'", ())[0], "中文旧记录")
        self.assertEqual(runtime.read_one("SELECT COUNT(*) FROM conversation_video_payloads", ())[0], 0)
        receipt = tuple(runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V29_TO_V30_ID,)))
        runtime.close()
        reopened = self.open()
        self.assertEqual(tuple(reopened.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V29_TO_V30_ID,))), receipt)

    def test_failed_upgrade_rolls_back_table_version_and_receipt(self):
        original = StorageRuntime._migrate_v29_to_v30
        def fail(storage, db):
            original(storage, db)
            raise StorageOpenError("synthetic interrupted video upgrade")
        with patch.object(StorageRuntime, "_migrate_v29_to_v30", fail), self.assertRaises(StorageOpenError):
            self.open()
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V29)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name = 'conversation_video_payloads'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V29_TO_V30_ID,)).fetchone())
        self.open()

    def test_partial_table_and_untrusted_migration_receipt_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TABLE conversation_video_payloads (wrong TEXT)")
        with self.assertRaisesRegex(StorageOpenError, "incomplete v29-to-v30"):
            self.open()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("DROP TABLE conversation_video_payloads")
        self.open().close()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V29_TO_V30_ID,))
        with self.assertRaisesRegex(StorageOpenError, "untrusted v30"):
            self.open()

