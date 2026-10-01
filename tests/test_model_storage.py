from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskResult
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V8_TO_V9_ID, MIGRATION_V8_TO_V9_FINGERPRINT,
    MIGRATION_V9_TO_V10_ID, MIGRATION_V9_TO_V10_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V9, SCHEMA_VERSION_V10, V9_REQUIRED_TABLES,
)
from tests.execution_support import remove_v10
from tests.test_execution import ExecutionFixture
from tests.test_management_access import INSTALLATION


class ModelStorageTests(ExecutionFixture):
    def setUp(self):
        super().setUp()
        claim = self.running(kind="fixture.effect")
        self.tasks.begin_effect(claim).unwrap()
        self.tasks.record_operation(claim, "pending-original-operation").unwrap()
        self.tasks.finish(claim, TaskResult("uncertain", "unknown")).unwrap()
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V9_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v10(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V9,))
            connection.commit()

    def metadata(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0],
                    connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'model_calls'").fetchall())

    def test_nonempty_upgrade_preserves_unknown_operations_and_exact_v9_fingerprint(self):
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V8_TO_V9_ID,))
        self.assertEqual((row["to_version"], row["fingerprint"]), (SCHEMA_VERSION_V9, MIGRATION_V8_TO_V9_FINGERPRINT))
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V9_TO_V10_ID,))
        self.assertEqual((row["to_version"], row["fingerprint"]), (SCHEMA_VERSION_V10, MIGRATION_V9_TO_V10_FINGERPRINT))
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION)
        self.open_runtime().close()

    def test_failed_upgrade_rolls_back_original_records_and_can_retry(self):
        with patch("companion_v2.storage.runtime.V10_MIGRATION_STATEMENTS",
                   ("CREATE TABLE model_calls(call_id TEXT)", "INVALID MODEL MIGRATION")):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V9, []))
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)

    def test_partial_upgrade_and_changed_v10_fingerprint_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE model_calls(call_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION_V9)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE model_calls")
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V9_TO_V10_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
