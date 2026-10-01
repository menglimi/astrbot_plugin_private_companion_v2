from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V17_TO_V18_FINGERPRINT, MIGRATION_V17_TO_V18_ID,
    MIGRATION_V18_TO_V19_FINGERPRINT, MIGRATION_V18_TO_V19_ID,
    SCHEMA_VERSION_V19, SCHEMA_VERSION_V18, V18_REQUIRED_TABLES, V19_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v19


class BackgroundDeliveryStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-background-schema-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        runtime = self.open_runtime()
        self.database = runtime.database_path
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("""INSERT INTO relationship_memories VALUES
                ('owner', 'remember', '{}', '{}', 1, 'context', 'proposed', '2026-09-23', '{"text":"保留原记录"}')""")
            remove_v19(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V18,))
            connection.commit()
            self.before = {table: connection.execute(f'SELECT * FROM "{table}"').fetchall()
                for table in V18_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="background-schema")
        self.addCleanup(runtime.close)
        return runtime

    def assert_preserved(self, runtime):
        self.assertEqual({table: [tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())]
            for table in self.before}, self.before)

    def test_populated_v18_upgrade_preserves_original_rows_and_migration_fingerprints(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V18_TO_V19_ID,))
        self.assertEqual((row["from_version"], row["to_version"], row["fingerprint"]),
            (SCHEMA_VERSION_V18, SCHEMA_VERSION_V19, MIGRATION_V18_TO_V19_FINGERPRINT))
        old = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V17_TO_V18_ID,))
        self.assertEqual((old["to_version"], old["fingerprint"]), (SCHEMA_VERSION_V18, MIGRATION_V17_TO_V18_FINGERPRINT))
        runtime.close()
        self.assert_preserved(self.open_runtime())

    def test_failed_upgrade_rolls_back_tables_version_and_receipt(self):
        with patch("companion_v2.storage.runtime.V19_MIGRATION_STATEMENTS", V19_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id="background-schema")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V18)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'background_deliveries'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V18_TO_V19_ID,)).fetchone())
        self.assert_preserved(self.open_runtime())

    def test_partial_future_table_is_rejected_without_mutating_v18(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE agenda_dispatches(occurrence_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id="background-schema")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V18)

    def test_tampered_upgrade_receipt_is_rejected(self):
        runtime = self.open_runtime()
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE migration_id = ?", (MIGRATION_V18_TO_V19_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id="background-schema")


if __name__ == "__main__":
    unittest.main()
