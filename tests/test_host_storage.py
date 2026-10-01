from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V12_TO_V13_ID, MIGRATION_V12_TO_V13_FINGERPRINT,
    MIGRATION_V13_TO_V14_ID, MIGRATION_V13_TO_V14_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V13, SCHEMA_VERSION_V14, V13_REQUIRED_TABLES, V14_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v14
from tests.test_host_application import HostFixture
from tests.test_management_access import INSTALLATION
from tests.test_role_tool_loop import answered, call, requested


class HostStorageTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def model(envelope):
            return requested(call()) if not envelope.tool_history else answered()
        self.model_behavior = model
        host = await self.start()
        batch = host.receive(self.event()).unwrap()
        self.advance(host.application)
        await self.done(host.application, batch)
        await host.application.close()
        self.before = {table: tuple(tuple(r) for r in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V13_REQUIRED_TABLES - {"schema_migrations", "runtime_metadata"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v14(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V13,))
            connection.commit()

    def version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0]

    def assert_preserved(self, runtime):
        self.assertEqual({table: tuple(tuple(r) for r in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                          for table in self.before}, self.before)

    async def test_populated_v13_upgrade_preserves_original_receipts_and_does_not_adopt_manual_batches(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        old = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V12_TO_V13_ID,))
        self.assertEqual((old["to_version"], old["fingerprint"]), (SCHEMA_VERSION_V13, MIGRATION_V12_TO_V13_FINGERPRINT))
        new = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V13_TO_V14_ID,))
        self.assertEqual((new["from_version"], new["to_version"], new["fingerprint"]),
                         (SCHEMA_VERSION_V13, SCHEMA_VERSION_V14, MIGRATION_V13_TO_V14_FINGERPRINT))
        host = await self.start(self.host(runtime=runtime), 1, 1)
        self.advance(host.application)
        self.assertEqual(runtime.read_one("SELECT COUNT(*) n FROM conversation_flows", ())["n"], 0)
        self.assertEqual(len(self.sent), 1)
        await host.application.close()
        runtime.close()
        reopened = self.open_runtime()
        # Starting changes the supervisor generation, so compare original domain receipts directly.
        for table in ("conversation_inputs", "conversation_parts", "conversation_tool_calls", "operations"):
            self.assertEqual(tuple(tuple(r) for r in reopened.read_all(f'SELECT * FROM "{table}"', ())), self.before[table])

    async def test_failed_v14_upgrade_rolls_back_table_and_keeps_populated_v13(self):
        with patch("companion_v2.storage.runtime.V14_MIGRATION_STATEMENTS", V14_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V13)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'conversation_flows'").fetchone())
        self.assert_preserved(self.open_runtime())

    async def test_partial_future_flow_table_is_rejected_before_upgrade(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE conversation_flows(batch_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V13)

    async def test_changed_v13_or_v14_fingerprint_is_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V12_TO_V13_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V13)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?",
                               (MIGRATION_V12_TO_V13_FINGERPRINT, MIGRATION_V12_TO_V13_ID))
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V13_TO_V14_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
