from __future__ import annotations

from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.storage.models import OperationState
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V6_TO_V7_ID, MIGRATION_V7_TO_V8_FINGERPRINT, MIGRATION_V7_TO_V8_ID,
    SCHEMA_VERSION, SCHEMA_VERSION_V7, V7_REQUIRED_TABLES,
)
from tests.test_diagnostics import DiagnosticFixture
from tests.execution_support import remove_v9
from tests.test_management_access import INSTALLATION, NOW, SCOPE


class DiagnosticStorageTests(DiagnosticFixture):
    def setUp(self):
        super().setUp()
        self.write(self.important, self.read(self.important).unwrap()).unwrap()
        self.original_operation = self.operation(SCOPE, owner="conversation")
        self.diagnostics.operations.reserve(self.original_operation, parameter_hash="original", observed_at=NOW).unwrap()
        self.diagnostics.operations.transition(self.original_operation.operation_id, expected_state=OperationState.ACCEPTED,
                                              next_state=OperationState.UNKNOWN, observed_at=NOW).unwrap()
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V7_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v9(connection)
            connection.execute("DROP TABLE diagnostic_repair_proposals")
            connection.execute("DELETE FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V7_TO_V8_ID,))
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V7,))
            connection.commit()

    def metadata(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0],
                    connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'diagnostic_repair_proposals'").fetchall())

    def test_nonempty_v7_upgrade_preserves_all_domain_records_and_unknown_operations(self):
        runtime = self.open_runtime()
        after = {table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}
        self.assertEqual(after, self.before)
        self.assertEqual(runtime.read_one("SELECT state FROM operations WHERE operation_id = ?", (self.original_operation.operation_id,))["state"], "unknown")
        self.assertEqual(runtime.read_one("SELECT to_version FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V6_TO_V7_ID,))["to_version"], SCHEMA_VERSION_V7)
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V7_TO_V8_ID,))["fingerprint"], MIGRATION_V7_TO_V8_FINGERPRINT)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION)
        runtime.close()
        self.open_runtime().close()

    def test_failed_v8_upgrade_rolls_back_without_touching_v7_records_and_can_retry(self):
        with patch("companion_v2.storage.runtime.V8_MIGRATION_STATEMENTS",
                   ("CREATE TABLE diagnostic_repair_proposals(proposal_id TEXT)", "INVALID DIAGNOSTIC MIGRATION")):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V7, []))
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                          for table in self.before}, self.before)

    def test_partial_upgrade_and_changed_fingerprint_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE diagnostic_repair_proposals(proposal_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION_V7)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE diagnostic_repair_proposals")
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V7_TO_V8_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
