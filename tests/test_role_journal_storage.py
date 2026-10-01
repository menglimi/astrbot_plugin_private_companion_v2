from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.role_work import PersistentRoleLifeLedger, RoleActivity, RoleActivityState
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    SCHEMA_VERSION, SCHEMA_VERSION_V15, SCHEMA_VERSION_V16, SCHEMA_VERSION_V17,
    V16_REQUIRED_TABLES, V17_MIGRATION_STATEMENTS,
    MIGRATION_V15_TO_V16_ID, MIGRATION_V15_TO_V16_FINGERPRINT,
    MIGRATION_V16_TO_V17_ID, MIGRATION_V16_TO_V17_FINGERPRINT,
)
from tests.execution_support import remove_v16, remove_v17
from tests.test_management_access import INSTALLATION, NOW, ROLE, SCOPE
from tests.test_model_gateway import ModelFixture


class RoleJournalStorageTests(ModelFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await self.gateway.generate(self.model_run(), self.request())
        life = PersistentRoleLifeLedger(self.runtime, now=lambda: NOW)
        life.add_activity(RoleActivity("reading", ROLE.subject_id, SCOPE, NOW, RoleActivityState.PAUSED, checkpoint="第三章"))
        self.before = {table: tuple(tuple(row) for row in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V16_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v17(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V16,))
            connection.commit()

    def version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0]

    def assert_preserved(self, runtime):
        self.assertEqual({table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                          for table in self.before}, self.before)

    async def test_populated_v16_upgrade_keeps_activity_and_model_records_and_previous_fingerprint(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        previous = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V15_TO_V16_ID,))
        self.assertEqual((previous["to_version"], previous["fingerprint"]), (SCHEMA_VERSION_V16, MIGRATION_V15_TO_V16_FINGERPRINT))
        current = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V16_TO_V17_ID,))
        self.assertEqual((current["from_version"], current["to_version"], current["fingerprint"]),
                         (SCHEMA_VERSION_V16, SCHEMA_VERSION_V17, MIGRATION_V16_TO_V17_FINGERPRINT))
        for table in ("role_journals", "role_journal_derivatives", "role_journal_operations"):
            self.assertEqual(runtime.read_all(f'SELECT * FROM "{table}"', ()), ())
        runtime.close()
        self.assert_preserved(self.open_runtime())
        self.assertEqual(len(self.called), 1)

    async def test_failed_upgrade_rolls_back_new_tables_and_version(self):
        with patch("companion_v2.storage.runtime.V17_MIGRATION_STATEMENTS", V17_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V16)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name IN "
                "('role_journals', 'role_journal_derivatives', 'role_journal_operations')").fetchall(), [])
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V16_TO_V17_ID,)).fetchone())
        self.assert_preserved(self.open_runtime())

    async def test_partial_future_journal_table_is_rejected_in_v16_and_older_stores(self):
        for version in (SCHEMA_VERSION_V16, SCHEMA_VERSION_V15):
            with self.subTest(version=version):
                with closing(sqlite3.connect(self.database)) as connection:
                    if version == SCHEMA_VERSION_V15:
                        remove_v16(connection)
                    connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (version,))
                    connection.execute("CREATE TABLE role_journals(entry_key TEXT)")
                    connection.commit()
                with self.assertRaises(StorageOpenError):
                    StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
                self.assertEqual(self.version(), version)

    async def test_tampered_journal_migration_fingerprint_is_rejected(self):
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V16_TO_V17_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
