from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V1_TO_V2_FINGERPRINT, MIGRATION_V1_TO_V2_ID,
    MIGRATION_V2_TO_V3_FINGERPRINT, MIGRATION_V2_TO_V3_ID,
    SCHEMA_VERSION, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2,
    V1_SCHEMA_STATEMENTS, V2_MIGRATION_STATEMENTS, V3_MIGRATION_STATEMENTS,
    V3_REQUIRED_TABLES,
)


class ConfigurationStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory(prefix="companion-v2-config-schema-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.root.mkdir()
        self.database = self.root / StorageRuntime.DATABASE_FILENAME
        with closing(sqlite3.connect(self.database)) as connection:
            for statement in V1_SCHEMA_STATEMENTS + V2_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.executemany("INSERT INTO runtime_metadata VALUES (?, ?)", (
                ("installation_id", "installation-a"), ("schema_version", SCHEMA_VERSION_V2),
            ))
            connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?, ?)", (
                MIGRATION_V1_TO_V2_ID, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2,
                MIGRATION_V1_TO_V2_FINGERPRINT, "2026-09-21T00:00:00+00:00",
            ))
            connection.execute("INSERT INTO capability_descriptors VALUES ('screen', 'screen-package', '1', 'publisher', 'hash', '{}', '2026-09-21T00:00:00+00:00')")
            connection.execute("INSERT INTO capability_installations VALUES ('screen', 'screen-package', '1', 'hash', 'paused', 4, '[]', '2026-09-21T00:00:00+00:00', '2026-09-21T00:00:00+00:00')")
            connection.execute("INSERT INTO capability_settings VALUES ('screen', 'installation-a', 'onebot', 'private', 'window-a', 0, 2.5, 7, '2026-09-21T00:00:00+00:00')")
            connection.commit()

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="installation-a")
        self.addCleanup(runtime.close)
        return runtime

    def mutate(self, sql, parameters=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def assert_v2_unchanged(self):
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'identity_policy_metadata'").fetchone())
            self.assertEqual(connection.execute("SELECT proactive_enabled, thought_weight, revision FROM capability_settings").fetchone(), (0, 2.5, 7))

    def test_nonempty_v2_upgrade_preserves_capability_owner_settings_and_choice(self):
        runtime = self.open_runtime()
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", ("schema_version",))["value"], SCHEMA_VERSION)
        self.assertEqual(runtime.read_one("SELECT desired_state FROM capability_installations", ())["desired_state"], "paused")
        self.assertEqual(tuple(runtime.read_one("SELECT proactive_enabled, thought_weight, revision FROM capability_settings", ())), (0, 2.5, 7))
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V2_TO_V3_ID,))["fingerprint"], MIGRATION_V2_TO_V3_FINGERPRINT)
        tables = {row["name"] for row in runtime.read_all("SELECT name FROM sqlite_master WHERE type = 'table'", ())}
        self.assertTrue(V3_REQUIRED_TABLES.issubset(tables))
        migrations = tuple(tuple(row) for row in runtime.read_all("SELECT * FROM schema_migrations ORDER BY migration_id", ()))
        runtime.close()
        self.assertEqual(tuple(tuple(row) for row in self.open_runtime().read_all(
            "SELECT * FROM schema_migrations ORDER BY migration_id", ())), migrations)

    def test_failed_v3_upgrade_rolls_back_schema_version_and_record(self):
        with patch("companion_v2.storage.runtime.V3_MIGRATION_STATEMENTS", (*V3_MIGRATION_STATEMENTS[:4], "INVALID DDL")):
            with self.assertRaises(StorageOpenError):
                self.open_runtime()
        self.assert_v2_unchanged()
        self.assertEqual(self.open_runtime().read_one("SELECT revision FROM identity_policy_metadata", ())["revision"], 1)

    def test_partial_v3_is_not_silently_completed(self):
        self.mutate("CREATE TABLE configuration_values(untrusted TEXT)")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v2_unchanged()

    def test_old_migration_fingerprint_is_checked_before_upgrading(self):
        self.mutate("UPDATE schema_migrations SET fingerprint = 'tampered'")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v2_unchanged()

    def test_v3_record_and_identity_metadata_are_required_on_reopen(self):
        self.open_runtime().close()
        self.mutate("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE migration_id = ?", (MIGRATION_V2_TO_V3_ID,))
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.mutate("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?", (MIGRATION_V2_TO_V3_FINGERPRINT, MIGRATION_V2_TO_V3_ID))
        self.mutate("DELETE FROM identity_policy_metadata")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()

    def test_nested_write_failure_can_be_caught_without_committing_its_rows(self):
        runtime = self.open_runtime()
        with runtime.transaction() as connection:
            connection.execute("INSERT INTO inbox VALUES ('outer', 'one', 'hash', '2026-09-21T00:00:00+00:00')")
            with self.assertRaises(RuntimeError):
                with runtime.transaction() as nested:
                    nested.execute("INSERT INTO inbox VALUES ('inner', 'two', 'hash', '2026-09-21T00:00:00+00:00')")
                    raise RuntimeError("rollback inner savepoint")
            connection.execute("INSERT INTO inbox VALUES ('outer', 'three', 'hash', '2026-09-21T00:00:00+00:00')")
        self.assertEqual({row["event_id"] for row in runtime.read_all("SELECT event_id FROM inbox", ())}, {"one", "three"})

    def test_outer_rollback_also_rolls_back_successful_nested_writes(self):
        runtime = self.open_runtime()
        with self.assertRaises(RuntimeError):
            with runtime.transaction():
                with runtime.transaction() as connection:
                    connection.execute("INSERT INTO inbox VALUES ('inner', 'one', 'hash', '2026-09-21T00:00:00+00:00')")
                raise RuntimeError("rollback outer transaction")
        self.assertEqual(runtime.read_all("SELECT * FROM inbox", ()), ())

    def test_read_snapshot_cannot_be_promoted_to_a_write(self):
        runtime = self.open_runtime()
        with runtime.read_snapshot():
            with self.assertRaisesRegex(StorageOpenError, "read snapshot"):
                with runtime.transaction():
                    self.fail("read-only scope unexpectedly acquired a write transaction")
        with runtime.transaction() as connection:
            connection.execute("INSERT INTO inbox VALUES ('after', 'one', 'hash', '2026-09-21T00:00:00+00:00')")
        self.assertEqual(len(runtime.read_all("SELECT * FROM inbox", ())), 1)
