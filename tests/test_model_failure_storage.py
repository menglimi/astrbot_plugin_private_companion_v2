from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskError, TaskResult
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V13_TO_V14_ID, MIGRATION_V13_TO_V14_FINGERPRINT,
    MIGRATION_V14_TO_V15_ID, MIGRATION_V14_TO_V15_FINGERPRINT,
    MIGRATION_V35_TO_V36_ID, MIGRATION_V35_TO_V36_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V13, SCHEMA_VERSION_V14, SCHEMA_VERSION_V15, SCHEMA_VERSION_V35,
    SCHEMA_VERSION_V36, V14_REQUIRED_TABLES, V15_MIGRATION_STATEMENTS, V36_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v14, remove_v15, remove_v36
from tests.test_management_access import INSTALLATION
from tests.test_model_gateway import ModelFixture


class ModelFailureStorageTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        first = self.model_run()
        result = await self.gateway.generate(first, self.request())
        self.tasks.finish(first.claim, TaskResult("succeeded", result_ref=result.call_id)).unwrap()
        self.responses["primary"] = ProviderResponse("unknown", usage=Amount(11, 30), receipt_ref="old-unknown")
        with self.assertRaises(TaskError):
            await self.gateway.generate(self.model_run("task-2"), self.request())
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V14_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v15(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V14,))
            connection.commit()

    def version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0]

    def assert_preserved(self, runtime):
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                          for table in self.before}, self.before)

    def populated_v35(self):
        runtime = self.open_runtime()
        calls = tuple(row["call_id"] for row in runtime.read_all("SELECT call_id FROM model_calls ORDER BY task_id", ()))
        self.assertEqual(len(calls), 2)
        with runtime.transaction() as connection:
            connection.execute("INSERT INTO model_call_failures VALUES (?, ?, ?)",
                               (calls[0], "provider_request_failed", "2026-09-26T00:00:00+00:00"))
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v36(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V35,))
            connection.commit()
        return calls

    async def test_v35_upgrade_preserves_failures_and_accepts_refusal_code(self):
        old_call, new_call = self.populated_v35()
        runtime = self.open_runtime()
        self.assertEqual(self.version(), SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT code FROM model_call_failures WHERE call_id = ?", (old_call,))["code"],
                         "provider_request_failed")
        migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V35_TO_V36_ID,))
        self.assertEqual(migration["fingerprint"], MIGRATION_V35_TO_V36_FINGERPRINT)
        with runtime.transaction() as connection:
            connection.execute("INSERT INTO model_call_failures VALUES (?, ?, ?)",
                               (new_call, "provider_refused", "2026-09-26T00:01:00+00:00"))
        runtime.close()
        reopened = self.open_runtime()
        self.assertEqual(tuple(row["code"] for row in reopened.read_all(
            "SELECT code FROM model_call_failures ORDER BY observed_at", ())),
            ("provider_request_failed", "provider_refused"))
        self.assert_preserved(reopened)

    async def test_failed_v36_upgrade_keeps_old_rows_and_retries(self):
        old_call, _ = self.populated_v35()
        with patch("companion_v2.storage.runtime.V36_MIGRATION_STATEMENTS",
                   V36_MIGRATION_STATEMENTS[:2] + ("INVALID V36 MIGRATION",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V35)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'model_call_failures_v36'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?",
                                                 (MIGRATION_V35_TO_V36_ID,)).fetchone())
            self.assertEqual(connection.execute("SELECT code FROM model_call_failures WHERE call_id = ?",
                                                (old_call,)).fetchone()[0], "provider_request_failed")
        self.assert_preserved(self.open_runtime())

    async def test_populated_v14_upgrade_preserves_calls_usage_and_absent_historical_classifications(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        self.assertEqual(runtime.read_all("SELECT * FROM model_call_failures", ()), ())
        previous = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V13_TO_V14_ID,))
        self.assertEqual((previous["to_version"], previous["fingerprint"]),
                         (SCHEMA_VERSION_V14, MIGRATION_V13_TO_V14_FINGERPRINT))
        current = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V14_TO_V15_ID,))
        self.assertEqual((current["from_version"], current["to_version"], current["fingerprint"]),
                         (SCHEMA_VERSION_V14, SCHEMA_VERSION_V15, MIGRATION_V14_TO_V15_FINGERPRINT))
        runtime.close()
        self.assert_preserved(self.open_runtime())
        self.assertEqual(len(self.called), 2)

    async def test_failed_upgrade_rolls_back_and_can_retry_without_replaying_calls(self):
        with patch("companion_v2.storage.runtime.V15_MIGRATION_STATEMENTS", V15_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V14)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'model_call_failures'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V14_TO_V15_ID,)).fetchone())
        self.assert_preserved(self.open_runtime())
        self.assertEqual(len(self.called), 2)

    async def test_partial_future_failure_table_is_rejected_for_v14_and_earlier_stores(self):
        for version in (SCHEMA_VERSION_V14, SCHEMA_VERSION_V13):
            with self.subTest(version=version):
                with closing(sqlite3.connect(self.database)) as connection:
                    if version == SCHEMA_VERSION_V13:
                        remove_v14(connection)
                    connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (version,))
                    connection.execute("CREATE TABLE model_call_failures(call_id TEXT)")
                    connection.commit()
                with self.assertRaises(StorageOpenError):
                    StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
                self.assertEqual(self.version(), version)
                with closing(sqlite3.connect(self.database)) as connection:
                    connection.execute("DROP TABLE model_call_failures")
                    connection.commit()

    async def test_changed_failure_migration_fingerprint_is_rejected(self):
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V14_TO_V15_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
