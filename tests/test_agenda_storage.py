from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.agenda.models import encode, stamp
from companion_v2.configuration.service import ConfigurationService
from companion_v2.identity_policy.models import AuthorizationTier, CapabilityGrant, IdentityBinding
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    migration_count,
    MIGRATION_V1_TO_V2_ID, MIGRATION_V1_TO_V2_FINGERPRINT,
    MIGRATION_V2_TO_V3_ID, MIGRATION_V2_TO_V3_FINGERPRINT,
    MIGRATION_V3_TO_V4_ID, MIGRATION_V3_TO_V4_FINGERPRINT,
    MIGRATION_V45_TO_V46_ID, MIGRATION_V45_TO_V46_FINGERPRINT,
    MIGRATION_V46_TO_V47_ID, MIGRATION_V46_TO_V47_FINGERPRINT,
    MIGRATION_V47_TO_V48_ID, MIGRATION_V47_TO_V48_FINGERPRINT,
    MIGRATION_V48_TO_V49_ID, MIGRATION_V48_TO_V49_FINGERPRINT,
    MIGRATION_V49_TO_V50_ID, MIGRATION_V49_TO_V50_FINGERPRINT,
    SCHEMA_VERSION, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2, SCHEMA_VERSION_V3, SCHEMA_VERSION_V45,
    SCHEMA_VERSION_V46, SCHEMA_VERSION_V47, SCHEMA_VERSION_V48, SCHEMA_VERSION_V49, SCHEMA_VERSION_V50,
    V1_SCHEMA_STATEMENTS, V2_MIGRATION_STATEMENTS, V3_MIGRATION_STATEMENTS, V4_MIGRATION_STATEMENTS,
)
from tests.test_configuration import INSTALLATION, NOW, PRINCIPAL, USER, ROLE_A, WINDOW, WINDOW_TARGET, registry
from tests.execution_support import remove_v50


class AgendaStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-agenda-migration-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v2-data"
        self.root.mkdir()
        self.database = self.root / StorageRuntime.DATABASE_FILENAME
        binding = IdentityBinding("binding-a", PRINCIPAL, USER, 1, NOW)
        grant = CapabilityGrant("grant-a", USER, WINDOW, "configuration.read", AuthorizationTier.STANDARD, 1, NOW)
        with closing(sqlite3.connect(self.database)) as connection:
            for statement in V1_SCHEMA_STATEMENTS + V2_MIGRATION_STATEMENTS + V3_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.executemany("INSERT INTO runtime_metadata VALUES (?, ?)", (
                ("installation_id", INSTALLATION), ("schema_version", SCHEMA_VERSION_V3),
            ))
            for migration, previous, current, fingerprint in (
                (MIGRATION_V1_TO_V2_ID, SCHEMA_VERSION_V1, SCHEMA_VERSION_V2, MIGRATION_V1_TO_V2_FINGERPRINT),
                (MIGRATION_V2_TO_V3_ID, SCHEMA_VERSION_V2, SCHEMA_VERSION_V3, MIGRATION_V2_TO_V3_FINGERPRINT),
            ):
                connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?, ?)", (migration, previous, current, fingerprint, stamp(NOW)))
            connection.execute("INSERT INTO identity_bindings VALUES (?, ?, ?, ?, ?, ?, ?)", (
                binding.binding_id, INSTALLATION, PRINCIPAL.host_id, PRINCIPAL.platform, PRINCIPAL.native_account_id, 1, encode(binding),
            ))
            connection.execute("INSERT INTO identity_grants VALUES (?, ?, ?, ?, ?)", (grant.grant_id, USER.kind.value, USER.subject_id, grant.capability, encode(grant)))
            connection.execute("UPDATE identity_policy_metadata SET revision = 3")
            connection.execute("INSERT INTO role_bindings VALUES (?, ?, ?, ?, ?, ?)", (
                INSTALLATION, WINDOW.platform, WINDOW.kind.value, WINDOW.native_scope_id, ROLE_A.subject_id, 7,
            ))
            connection.execute("INSERT INTO configuration_targets VALUES (?, ?, ?, ?)", (WINDOW_TARGET.key, encode(WINDOW_TARGET.document()), 8, stamp(NOW)))
            connection.executemany("INSERT INTO configuration_values VALUES (?, ?, ?, ?)", (
                (WINDOW_TARGET.key, "output.probability", "0.0", 8),
                (WINDOW_TARGET.key, "output.enabled", "false", 5),
                (WINDOW_TARGET.key, "output.prompt", '""', 4),
            ))
            connection.commit()

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def mutate(self, statement, values=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(statement, values)
            connection.commit()

    def assert_v3_unchanged(self):
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V3)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 2)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'agenda_memos'").fetchone())
            self.assertEqual(connection.execute("SELECT revision FROM role_bindings").fetchone()[0], 7)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM configuration_values").fetchone()[0], 3)

    def test_empty_data_root_reaches_latest_schema_and_records_v46_through_v50(self):
        fresh_root = Path(self.temporary.name) / "fresh-data"
        runtime = StorageRuntime.open(data_root=fresh_root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)

        version = runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"]
        migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?",
                                     (MIGRATION_V45_TO_V46_ID,))
        previous_migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?",
                                              (MIGRATION_V47_TO_V48_ID,))
        latest_migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?",
                                            (MIGRATION_V48_TO_V49_ID,))
        current_migration = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?",
                                             (MIGRATION_V49_TO_V50_ID,))
        columns = {row["name"] for row in runtime.read_all("PRAGMA table_info(model_calls)", ())}

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(migration["from_version"], SCHEMA_VERSION_V45)
        self.assertEqual(migration["fingerprint"], MIGRATION_V45_TO_V46_FINGERPRINT)
        self.assertEqual(previous_migration["from_version"], SCHEMA_VERSION_V47)
        self.assertEqual(previous_migration["to_version"], SCHEMA_VERSION_V48)
        self.assertEqual(previous_migration["fingerprint"], MIGRATION_V47_TO_V48_FINGERPRINT)
        self.assertEqual(latest_migration["from_version"], SCHEMA_VERSION_V48)
        self.assertEqual(latest_migration["to_version"], SCHEMA_VERSION_V49)
        self.assertEqual(latest_migration["fingerprint"], MIGRATION_V48_TO_V49_FINGERPRINT)
        self.assertEqual(current_migration["from_version"], SCHEMA_VERSION_V49)
        self.assertEqual(current_migration["to_version"], SCHEMA_VERSION_V50)
        self.assertEqual(current_migration["fingerprint"], MIGRATION_V49_TO_V50_FINGERPRINT)
        self.assertIsNotNone(runtime.read_one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                                              ("model_call_cache_signatures",)))
        self.assertIsNotNone(runtime.read_one("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                                              ("inbound_no_replies",)))
        self.assertIn("code", {row["name"] for row in runtime.read_all("PRAGMA table_info(inbound_no_replies)", ())})
        self.assertTrue({"input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens"}.issubset(columns))
        self.assertEqual(len(runtime.read_all("SELECT * FROM schema_migrations", ())), migration_count())

    def test_v49_no_reply_rows_survive_v50_error_code_migration(self):
        root = Path(self.temporary.name) / "v49-data"
        runtime = StorageRuntime.open(data_root=root, installation_id=INSTALLATION)
        runtime.read_one("SELECT 1", ())
        with runtime.transaction() as connection:
            connection.execute("""INSERT INTO inbound_no_replies
                (event_ref, origin_key, channel, reason_code, observed_at)
                VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'role-a', 'private', 'conversation_task_failed', ?)""",
                (stamp(NOW),))
            remove_v50(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                               (SCHEMA_VERSION_V49,))
            connection.execute("DELETE FROM schema_migrations WHERE migration_id = ?",
                               (MIGRATION_V49_TO_V50_ID,))
        runtime.close()

        upgraded = StorageRuntime.open(data_root=root, installation_id=INSTALLATION)
        self.addCleanup(upgraded.close)
        row = upgraded.read_one("SELECT reason_code, code FROM inbound_no_replies "
                                "WHERE event_ref = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'", ())
        self.assertEqual((row["reason_code"], row["code"]), ("conversation_task_failed", None))
        self.assertEqual(upgraded.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"],
                         SCHEMA_VERSION)

    def test_nonempty_v3_upgrade_preserves_identity_zero_false_empty_and_revisions(self):
        runtime = self.open_runtime()
        actor = PersistentIdentityDirectory(runtime).resolve_authenticated(PRINCIPAL, observed_at=NOW).unwrap()
        values = ConfigurationService(runtime, registry()).read(actor, target=WINDOW_TARGET, group_id="output", observed_at=NOW).unwrap()
        self.assertEqual(values.values, {"output.probability": 0.0, "output.enabled": False, "output.prompt": ""})
        self.assertEqual(values.revision, 8)
        self.assertEqual(PersistentIdentityDirectory(runtime).role_binding(WINDOW).revision, 7)
        self.assertEqual(runtime.read_one("SELECT fingerprint FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V3_TO_V4_ID,))["fingerprint"], MIGRATION_V3_TO_V4_FINGERPRINT)
        self.assertEqual(runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], SCHEMA_VERSION)
        runtime.close()
        self.assertEqual(len(self.open_runtime().read_all("SELECT * FROM schema_migrations", ())), migration_count())

    def test_failed_v4_ddl_rolls_back_and_original_config_can_upgrade_later(self):
        with patch("companion_v2.storage.runtime.V4_MIGRATION_STATEMENTS", (*V4_MIGRATION_STATEMENTS[:4], "INVALID DDL")):
            with self.assertRaises(StorageOpenError):
                self.open_runtime()
        self.assert_v3_unchanged()
        self.assertEqual(self.open_runtime().read_all("SELECT * FROM agenda_memos", ()), ())

    def test_partial_new_table_is_rejected_before_any_upgrade(self):
        self.mutate("CREATE TABLE agenda_results(untrusted TEXT)")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v3_unchanged()

    def test_prior_fingerprint_and_unknown_versions_are_not_silently_repaired(self):
        self.mutate("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V2_TO_V3_ID,))
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.assert_v3_unchanged()
        self.mutate("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?", (MIGRATION_V2_TO_V3_FINGERPRINT, MIGRATION_V2_TO_V3_ID))
        self.mutate("UPDATE runtime_metadata SET value = 'future' WHERE key = 'schema_version'")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()

    def test_reopen_rejects_missing_due_index_and_changed_v4_migration_record(self):
        self.open_runtime().close()
        self.mutate("UPDATE schema_migrations SET fingerprint = 'bad' WHERE migration_id = ?", (MIGRATION_V3_TO_V4_ID,))
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
        self.mutate("UPDATE schema_migrations SET fingerprint = ? WHERE migration_id = ?", (MIGRATION_V3_TO_V4_FINGERPRINT, MIGRATION_V3_TO_V4_ID))
        self.mutate("DROP INDEX agenda_occurrences_due_idx")
        with self.assertRaises(StorageOpenError):
            self.open_runtime()
