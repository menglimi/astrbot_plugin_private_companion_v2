from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch

from companion_v2.execution.models import digest, encode, stamp
from companion_v2.role_work.models import RoleActivity, RoleActivityState
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V16_TO_V17_ID,
    MIGRATION_V17_TO_V18_FINGERPRINT,
    MIGRATION_V17_TO_V18_ID,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V17,
    SCHEMA_VERSION_V18,
    V17_REQUIRED_TABLES,
    V18_MIGRATION_STATEMENTS,
    V18_REQUIRED_TABLES,
)


from tests.execution_support import remove_v18
from tests.test_management_access import NOW, SCOPE


INSTALLATION = "relationship-storage-installation"


class RelationshipMemoryStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="companion-v2-relationship-schema-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "runtime"
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.database = runtime.database_path
        runtime.close()
        activity = RoleActivity("existing-activity", "legacy-role", replace(SCOPE, installation_id=INSTALLATION),
                                NOW, RoleActivityState.PAUSED, checkpoint="preserve")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("INSERT INTO role_activities VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (digest(activity.owner), activity.activity_id, encode(activity.owner), activity.revision,
                                activity.state.value, stamp(activity.updated_at), encode(activity)))
            connection.commit()
        self.before = self.snapshot_v17_tables()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v18(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V17,))
            connection.commit()

    def snapshot_v17_tables(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return {table: tuple(tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"'))
                    for table in V17_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}

    def version(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0]

    def assert_preserved(self, runtime):
        current = {table: tuple(tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ()))
                   for table in self.before}
        self.assertEqual(current, self.before)

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def test_populated_v17_upgrades_once_and_preserves_previous_migration_records(self):
        runtime = self.open_runtime()
        self.assertEqual(self.version(), SCHEMA_VERSION)
        self.assertEqual(V18_REQUIRED_TABLES.issubset({row["name"] for row in runtime.read_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'", ())}), True)
        old = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V16_TO_V17_ID,))
        self.assertEqual((old["from_version"], old["to_version"]),
                         ("companion-v2.storage.v16", SCHEMA_VERSION_V17))
        current = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V17_TO_V18_ID,))
        self.assertEqual((current["from_version"], current["to_version"], current["fingerprint"]),
                         (SCHEMA_VERSION_V17, SCHEMA_VERSION_V18, MIGRATION_V17_TO_V18_FINGERPRINT))
        self.assert_preserved(runtime)
        runtime.close()
        self.assert_preserved(self.open_runtime())

    def test_failed_v18_upgrade_rolls_back_all_new_tables_and_can_retry(self):
        with patch("companion_v2.storage.runtime.V18_MIGRATION_STATEMENTS",
                   V18_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V17)
        with closing(sqlite3.connect(self.database)) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertFalse({"relationship_memories", "relationship_memory_revisions",
                              "relationship_memory_operations"}.intersection(names))
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?",
                                                 (MIGRATION_V17_TO_V18_ID,)).fetchone())
        self.assert_preserved(self.open_runtime())

    def test_partial_future_relationship_table_in_v17_fails_closed(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE relationship_memories(memory_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assertEqual(self.version(), SCHEMA_VERSION_V17)

    def test_tampered_v18_migration_record_is_rejected(self):
        runtime = self.open_runtime()
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?",
                               (MIGRATION_V17_TO_V18_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)


if __name__ == "__main__":
    unittest.main()
