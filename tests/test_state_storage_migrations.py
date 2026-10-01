"""Calendar/state migration retains existing V2 data and rejects partial upgrades."""

from contextlib import closing
import sqlite3
import unittest

from companion_v2.storage.runtime import StorageRuntime, StorageOpenError
from companion_v2.storage.schema import SCHEMA_VERSION, SCHEMA_VERSION_V23
from companion_v2.storage.state_schema import STATE_STATEMENTS, STATE_TABLES
from tests.execution_support import remove_v24
from tests.test_management_access import ManagementFixture


class StateMigrationTests(ManagementFixture):
    def historical(self, *, partial=False):
        counts = {table: self.runtime.read_one(f"SELECT COUNT(*) AS n FROM {table}", ())["n"]
                  for table in ("identity_bindings", "identity_grants", "role_bindings")}
        self.runtime.close()
        with closing(sqlite3.connect(self.root / StorageRuntime.DATABASE_FILENAME)) as connection:
            remove_v24(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V23,))
            if partial:
                connection.execute(STATE_STATEMENTS[0])
            connection.commit()
        return counts

    def test_nonempty_v23_upgrades_atomically_and_reopens_with_original_owners(self):
        counts = self.historical()
        migrated = self.open_runtime()
        self.assertEqual(migrated.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
        for table, expected in counts.items():
            self.assertEqual(migrated.read_one(f"SELECT COUNT(*) AS n FROM {table}", ())["n"], expected)
        for table in STATE_TABLES:
            self.assertEqual(migrated.read_one(f"SELECT COUNT(*) AS n FROM {table}", ())["n"], 0)
        migrated.close()
        reopened = self.open_runtime()
        self.assertIsNotNone(reopened.read_one("SELECT 1 FROM schema_migrations WHERE to_version = 'companion-v2.storage.v24'", ()))

    def test_partial_v24_tables_are_rejected_without_rewriting_old_version(self):
        self.historical(partial=True)
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        with closing(sqlite3.connect(self.root / StorageRuntime.DATABASE_FILENAME)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V23)

    def test_migration_receipt_fingerprint_is_checked_on_reopen(self):
        self.runtime.close()
        with closing(sqlite3.connect(self.root / StorageRuntime.DATABASE_FILENAME)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE to_version = 'companion-v2.storage.v24'")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            self.open_runtime()


if __name__ == "__main__":
    unittest.main()
