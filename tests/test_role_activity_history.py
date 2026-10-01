"""Activity history writes and populated V22 upgrade keep real receipt provenance."""

from contextlib import closing
from dataclasses import replace
import sqlite3
from unittest.mock import patch

from companion_v2.execution.models import encode
from companion_v2.foundation.refs import ReferenceValidationError
from companion_v2.role_work.ledger import PersistentRoleLifeLedger
from companion_v2.role_work.models import RoleActivity, RoleActivityState as State
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (SCHEMA_VERSION_V22, SCHEMA_VERSION_V23, MIGRATION_V22_TO_V23_ID,
    MIGRATION_V22_TO_V23_FINGERPRINT, V22_REQUIRED_TABLES, V23_MIGRATION_STATEMENTS)
from tests.execution_support import remove_v23
from tests.test_management_access import ManagementFixture, INSTALLATION, NOW, SCOPE


class RoleActivityHistoryTests(ManagementFixture):
    def setUp(self):
        super().setUp()
        self.life = PersistentRoleLifeLedger(self.runtime, now=lambda: NOW)
        self.original = self.life.add_activity(RoleActivity("walk", "persona-a", SCOPE, NOW, State.ACTIVE))

    def transition(self, revision=1, state=State.PAUSED, operation="pause"):
        return self.life.transition_activity("walk", owner=self.original.owner, expected_revision=revision,
            state=state, operation_id=operation, checkpoint="走到河边。", observed_at=NOW)

    def downgrade(self):
        self.before = {table: tuple(tuple(r) for r in self.runtime.read_all(f'SELECT * FROM "{table}"', ()))
                       for table in V22_REQUIRED_TABLES - {"schema_migrations", "runtime_metadata"}}
        self.database = self.runtime.database_path
        self.runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v23(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V22,))
            connection.commit()

    def test_new_versions_replay_and_failed_compare_swap_preserve_exact_history(self):
        second = self.transition()
        third = self.transition(2, State.ACTIVE, "resume")
        self.assertEqual(self.transition(), second)
        with self.assertRaises(ReferenceValidationError):
            self.transition(operation="stale")
        for revision, expected in enumerate((self.original, second, third), 1):
            self.assertEqual(self.life.activity_revision("walk", revision, owner=self.original.owner), expected)
        rows = self.runtime.read_all("SELECT provenance, operation_id FROM role_activity_revisions ORDER BY revision", ())
        self.assertEqual([tuple(r) for r in rows], [("recorded", None), ("recorded", "pause"), ("recorded", "resume")])

    def test_history_write_failure_rolls_back_head_receipt_and_operation(self):
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TRIGGER reject_history BEFORE INSERT ON role_activity_revisions
                WHEN NEW.revision = 2 BEGIN SELECT RAISE(ABORT, 'fixture rejection'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.transition()
        self.assertEqual(self.life.activity("walk", owner=self.original.owner), self.original)
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM operations WHERE operation_id = 'pause'", ()))
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM role_activity_revisions", ())), 1)

    def test_populated_upgrade_recovers_receipts_and_heads_without_inventing_missing_initial_version(self):
        self.transition()
        third = self.transition(2, State.ACTIVE, "resume")
        self.life.add_activity(replace(self.original, activity_id="untouched"))
        self.downgrade()
        runtime = self.open_runtime()
        for table, rows in self.before.items():
            self.assertEqual(tuple(tuple(r) for r in runtime.read_all(f'SELECT * FROM "{table}"', ())), rows)
        history = runtime.read_all("SELECT activity_id, revision, provenance, operation_id FROM role_activity_revisions ORDER BY activity_id, revision", ())
        self.assertEqual([tuple(r) for r in history], [("untouched", 1, "legacy_head", None),
            ("walk", 2, "legacy_receipt", "pause"), ("walk", 3, "legacy_receipt", "resume")])
        ledger = PersistentRoleLifeLedger(runtime)
        self.assertEqual(ledger.activity_revision("walk", 3, owner=self.original.owner), third)
        with self.assertRaises(KeyError):
            ledger.activity_revision("walk", 1, owner=self.original.owner)
        receipt = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V22_TO_V23_ID,))
        self.assertEqual((receipt["from_version"], receipt["to_version"], receipt["fingerprint"]),
                         (SCHEMA_VERSION_V22, SCHEMA_VERSION_V23, MIGRATION_V22_TO_V23_FINGERPRINT))
        runtime.close()
        self.assertEqual(len(self.open_runtime().read_all("SELECT * FROM role_activity_revisions", ())), 3)

    def assert_upgrade_rolled_back(self):
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V22)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'role_activity_revisions'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V22_TO_V23_ID,)).fetchone())

    def test_conflicting_legacy_head_and_receipt_fail_closed_and_rollback(self):
        second = self.transition()
        self.downgrade()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE role_life_operations SET result_json = ? WHERE operation_id = 'pause'",
                               (encode(replace(second, checkpoint="不同的历史正文")),))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assert_upgrade_rolled_back()

    def test_unknown_legacy_operation_does_not_become_completed_history(self):
        self.transition()
        self.downgrade()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE operations SET state = 'unknown' WHERE operation_id = 'pause'")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assert_upgrade_rolled_back()

    def test_ddl_failure_and_tampered_migration_receipt_are_rejected(self):
        self.downgrade()
        with patch("companion_v2.storage.runtime.V23_MIGRATION_STATEMENTS", V23_MIGRATION_STATEMENTS + ("INVALID MIGRATION",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assert_upgrade_rolled_back()
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'changed' WHERE migration_id = ?", (MIGRATION_V22_TO_V23_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)

    def test_legacy_receipt_cannot_borrow_another_scopes_operation(self):
        self.transition()
        self.downgrade()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE operations SET session_id = 'other-session' WHERE operation_id = 'pause'")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.assert_upgrade_rolled_back()

    def test_partial_future_history_table_does_not_complete_an_untrusted_migration(self):
        self.downgrade()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE role_activity_revisions(revision INTEGER)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V22)
