from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from tests.execution_support import remove_v9
from companion_v2.storage.schema import (
    MIGRATION_V6_TO_V7_FINGERPRINT, MIGRATION_V6_TO_V7_ID, SCHEMA_VERSION, SCHEMA_VERSION_V6,
)


INSTALLATION = "persona-storage-installation"


class PersonaStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-persona-storage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        runtime.close()
        self.database = self.root / StorageRuntime.DATABASE_FILENAME
        self.restore_v6()

    def restore_v6(self):
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v9(connection)
            connection.execute("DROP TABLE IF EXISTS diagnostic_repair_proposals")
            connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v7-to-v8'")
            connection.execute("DELETE FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V6_TO_V7_ID,))
            for table in ("legacy_scope_mappings", "persona_binding_events", "conversation_routes"):
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V6,))
            connection.commit()

    def metadata(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0],
                    connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
                                       "('conversation_routes','persona_binding_events','legacy_scope_mappings') ORDER BY name").fetchall())

    def test_v6_upgrade_is_atomic_and_restart_validates_fingerprint(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"],
                         SCHEMA_VERSION)
        row = runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?",
                               (MIGRATION_V6_TO_V7_ID,))
        self.assertEqual(row["fingerprint"], MIGRATION_V6_TO_V7_FINGERPRINT)
        runtime.close()
        StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION).close()

    def test_failed_upgrade_rolls_back_and_can_retry(self):
        with patch("companion_v2.storage.runtime.V7_MIGRATION_STATEMENTS",
                   ("CREATE TABLE conversation_routes(scope_key TEXT)", "INVALID PERSONA MIGRATION")):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V6, []))
        StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION).close()

    def test_partial_upgrade_and_changed_fingerprint_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE conversation_routes(scope_key TEXT PRIMARY KEY, record_json TEXT NOT NULL)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.restore_v6()
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?",
                               (MIGRATION_V6_TO_V7_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
