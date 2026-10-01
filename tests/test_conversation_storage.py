from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import TaskResult
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V9_TO_V10_ID, MIGRATION_V9_TO_V10_FINGERPRINT,
    MIGRATION_V10_TO_V11_ID, MIGRATION_V10_TO_V11_FINGERPRINT,
    MIGRATION_V11_TO_V12_ID, MIGRATION_V11_TO_V12_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V10, SCHEMA_VERSION_V11, SCHEMA_VERSION_V12, V10_REQUIRED_TABLES,
    V11_MIGRATION_STATEMENTS, V12_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v11
from tests.test_management_access import INSTALLATION, NOW
from tests.test_model_gateway import ModelFixture


class ConversationStorageTests(ModelFixture):
    def setUp(self):
        super().setUp()
        run = self.model_run()
        self.stage_plan(run)
        self.ledger.reserve(run, call_id="pending-call", position=0, provider=self.providers[0].binding, amount=Amount(30, 100))
        self.ledger.dispatch(run, "pending-call")
        self.ledger.settle("pending-call", self.providers[0].binding, ProviderResponse("unknown"), observed_at=NOW, latency_ms=1)
        self.tasks.finish(run.claim, TaskResult("failed")).unwrap()
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V10_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v11(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V10,))
            connection.commit()

    def metadata(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0],
                    connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'conversation_batches'").fetchall())

    def stage_v11(self):
        """Turn the historical fixture into a complete, non-empty v11 root."""
        with closing(sqlite3.connect(self.database)) as connection:
            for statement in V11_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                """INSERT INTO schema_migrations(migration_id, from_version, to_version, fingerprint, applied_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("companion-v2.storage.v10-to-v11", SCHEMA_VERSION_V10, SCHEMA_VERSION_V11,
                 MIGRATION_V10_TO_V11_FINGERPRINT,
                 NOW.isoformat()),
            )
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V11,))
            connection.commit()

    def test_nonempty_upgrade_preserves_pending_usage_and_historical_fingerprint(self):
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V9_TO_V10_ID,))
        self.assertEqual((row["to_version"], row["fingerprint"]), (SCHEMA_VERSION_V10, MIGRATION_V9_TO_V10_FINGERPRINT))
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V10_TO_V11_ID,))
        self.assertEqual((row["to_version"], row["fingerprint"]), (SCHEMA_VERSION_V11, MIGRATION_V10_TO_V11_FINGERPRINT))
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION)
        self.open_runtime().close()

    def test_failed_upgrade_rolls_back_original_tables_and_version(self):
        with patch("companion_v2.storage.runtime.V11_MIGRATION_STATEMENTS",
                   ("CREATE TABLE conversation_batches(batch_id TEXT)", "INVALID CONVERSATION MIGRATION")):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V10, []))
        runtime = self.open_runtime()
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())) for table in self.before}, self.before)

    def test_partial_upgrade_and_changed_fingerprint_are_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE conversation_batches(batch_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION_V10)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DROP TABLE conversation_batches")
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V10_TO_V11_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)

    def test_changed_original_v10_fingerprint_cannot_be_upgraded(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V9_TO_V10_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata(), (SCHEMA_VERSION_V10, []))

    def test_v11_to_v12_preserves_nonempty_ledger_and_widens_round_positions(self):
        with closing(sqlite3.connect(self.database)) as connection:
            original_calls = tuple(tuple(row) for row in connection.execute(
                "SELECT call_id, position, state FROM model_calls"))
        self.stage_v11()
        runtime = self.open_runtime()
        self.assertEqual(
            tuple(tuple(row) for row in runtime.read_all("SELECT call_id, position, state FROM model_calls", ())),
            original_calls,
        )
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
        migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V11_TO_V12_ID,))
        self.assertEqual((migration["from_version"], migration["to_version"], migration["fingerprint"]),
                         (SCHEMA_VERSION_V11, SCHEMA_VERSION_V12, MIGRATION_V11_TO_V12_FINGERPRINT))
        source = runtime.read_one("SELECT task_id, attempt_id FROM model_calls LIMIT 1", ())
        with runtime.transaction() as connection:
            connection.execute(
                """INSERT INTO model_calls(call_id, task_id, attempt_id, position, state, provider_json,
                   reserved_tokens, reserved_cost) VALUES (?, ?, ?, ?, 'reserved', ?, 1, 1)""",
                ("round-four", source["task_id"], source["attempt_id"], 4, "{}"),
            )
        self.assertEqual(runtime.read_one("SELECT position FROM model_calls WHERE call_id = 'round-four'", ())["position"], 4)

    def test_v11_to_v12_failure_rolls_back_rebuild_and_new_tables(self):
        self.stage_v11()
        self.runtime.close()
        with patch("companion_v2.storage.runtime.V12_MIGRATION_STATEMENTS",
                   V12_MIGRATION_STATEMENTS + ("INVALID V12 MIGRATION",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V11)
            self.assertIsNotNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_calls'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_rounds'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'model_calls_saved'").fetchone())

    def test_future_v12_table_on_an_older_version_is_rejected_before_upgrade(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE model_rounds(task_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.metadata()[0], SCHEMA_VERSION_V10)


if __name__ == "__main__":
    unittest.main()
