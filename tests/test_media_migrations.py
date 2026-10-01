from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageRuntime, StorageOpenError
from companion_v2.storage.schema import (
    SCHEMA_VERSION, SCHEMA_VERSION_V24, MIGRATION_V23_TO_V24_FINGERPRINT,
    MIGRATION_V42_TO_V43_ID,
)
from tests.execution_support import remove_v25


class MediaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="companion-v2-media-upgrade-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "v2"
        runtime = self.runtime()
        with runtime.transaction() as connection:
            connection.execute("INSERT INTO runtime_metadata VALUES ('text-event-proof', 'unchanged')")
        runtime.close()
        self.database = self.root / StorageRuntime.DATABASE_FILENAME
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v25(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V24,))
            connection.commit()

    def runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="media-upgrade")
        self.addCleanup(runtime.close)
        return runtime

    def test_v24_upgrade_is_additive_and_restart_keeps_migration_and_existing_data(self):
        runtime = self.runtime()
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'text-event-proof'", ())["value"], "unchanged")
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE to_version = ?", (SCHEMA_VERSION_V24,))["fingerprint"], MIGRATION_V23_TO_V24_FINGERPRINT)
        self.assertEqual(runtime.read_one("SELECT COUNT(*) n FROM conversation_image_payloads", ())["n"], 0)
        migration = tuple(runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V42_TO_V43_ID,)))
        runtime.close()
        self.assertEqual(tuple(self.runtime().read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V42_TO_V43_ID,))), migration)

    def test_failed_upgrade_rolls_back_table_version_and_migration_receipt(self):
        original = StorageRuntime._migrate_v24_to_v25
        def fail(runtime, connection):
            original(runtime, connection)
            raise StorageOpenError("synthetic failure after image schema creation")
        with patch.object(StorageRuntime, "_migrate_v24_to_v25", fail):
            with self.assertRaises(StorageOpenError):
                self.runtime()
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V24)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'conversation_image_payloads'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE to_version = ?", (SCHEMA_VERSION,)).fetchone())
        self.runtime()

    def test_partial_table_or_tampered_migration_is_not_accepted(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE conversation_image_payloads (wrong TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            self.runtime()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE conversation_image_payloads")
            connection.commit()
        self.runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE migration_id = ?", (MIGRATION_V42_TO_V43_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            self.runtime()
