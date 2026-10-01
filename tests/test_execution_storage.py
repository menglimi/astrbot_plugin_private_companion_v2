from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V7_TO_V8_ID, MIGRATION_V8_TO_V9_ID, MIGRATION_V8_TO_V9_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V8, V8_REQUIRED_TABLES,
)
from tests.execution_support import remove_v9
from tests.test_diagnostics import DiagnosticFixture
from companion_v2.diagnostics.repairs import RepairProposalService
from tests.test_management_access import INSTALLATION


class ExecutionStorageTests(DiagnosticFixture):
    def setUp(self):
        super().setUp()
        report = self.check().unwrap()
        repairs = RepairProposalService(self.diagnostics)
        self.proposal = repairs.propose(self.important_context, proposal_id="pending-repair", report_id=report.report_id,
                                       changes={"output.enabled": False}, rationale="fixture repair").unwrap()
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V8_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v9(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V8,))
            connection.commit()

    def metadata(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0],
                    connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'execution_tasks'").fetchall())

    def test_nonempty_v8_upgrade_preserves_pending_repairs_and_prior_fingerprint(self):
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)
        self.assertEqual(runtime.read_one("SELECT to_version FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V7_TO_V8_ID,))["to_version"], SCHEMA_VERSION_V8)
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V8_TO_V9_ID,))["fingerprint"], MIGRATION_V8_TO_V9_FINGERPRINT)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION)
        runtime.close()
        self.open_runtime().close()

    def test_failed_upgrade_rolls_back_v8_records_and_version_then_retries(self):
        with patch("companion_v2.storage.runtime.V9_MIGRATION_STATEMENTS",
                   ("CREATE TABLE execution_tasks(task_id TEXT)", "INVALID EXECUTION MIGRATION")):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V8, []))
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)

    def test_partial_upgrade_and_changed_fingerprint_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE execution_tasks(task_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION_V8)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE execution_tasks")
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V8_TO_V9_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
