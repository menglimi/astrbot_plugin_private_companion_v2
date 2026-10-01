from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V11_TO_V12_ID, MIGRATION_V11_TO_V12_FINGERPRINT,
    MIGRATION_V12_TO_V13_ID, MIGRATION_V12_TO_V13_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V12, SCHEMA_VERSION_V13, V12_REQUIRED_TABLES, V13_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v13
from tests.test_management_access import INSTALLATION
from tests.test_role_tool_loop import ToolLoopFixture, answered, call, requested


class ExternalToolStorageTests(ToolLoopFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def respond(envelope):
            return requested(call()) if not envelope.tool_history else answered()
        self.responses["primary"] = respond
        await self.generate()
        self.before = {table: tuple(tuple(r) for r in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V12_REQUIRED_TABLES - {"schema_migrations", "runtime_metadata"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v13(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V12,))
            connection.commit()

    def version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0]

    def assert_preserved(self, runtime):
        self.assertEqual({table: tuple(tuple(r) for r in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                          for table in self.before}, self.before)

    async def test_populated_v12_upgrade_preserves_all_tool_receipts_and_fingerprints(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        previous = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V11_TO_V12_ID,))
        self.assertEqual((previous["to_version"], previous["fingerprint"]), (SCHEMA_VERSION_V12, MIGRATION_V11_TO_V12_FINGERPRINT))
        current = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V12_TO_V13_ID,))
        self.assertEqual((current["from_version"], current["to_version"], current["fingerprint"]),
                         (SCHEMA_VERSION_V12, SCHEMA_VERSION_V13, MIGRATION_V12_TO_V13_FINGERPRINT))
        runtime.close()
        self.assert_preserved(self.open_runtime())

    async def test_failed_v13_upgrade_rolls_back_new_table_and_preserves_nonempty_v12(self):
        with patch("companion_v2.storage.runtime.V13_MIGRATION_STATEMENTS", V13_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V12)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'extension_tool_invocations'").fetchone())
        self.assert_preserved(self.open_runtime())

    async def test_future_table_in_v12_is_rejected_before_migration(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE extension_tool_invocations(invocation_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V12)

    async def test_changed_v12_or_v13_fingerprint_is_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'untrusted' WHERE migration_id = ?", (MIGRATION_V11_TO_V12_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V12)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?",
                               (MIGRATION_V11_TO_V12_FINGERPRINT, MIGRATION_V11_TO_V12_ID))
            connection.commit()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'untrusted' WHERE migration_id = ?", (MIGRATION_V12_TO_V13_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
