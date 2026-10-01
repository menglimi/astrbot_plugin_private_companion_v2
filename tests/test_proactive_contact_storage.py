from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (
    MIGRATION_V18_TO_V19_FINGERPRINT, MIGRATION_V18_TO_V19_ID,
    MIGRATION_V19_TO_V20_FINGERPRINT, MIGRATION_V19_TO_V20_ID,
    SCHEMA_VERSION, SCHEMA_VERSION_V19, SCHEMA_VERSION_V20, V19_REQUIRED_TABLES, V20_MIGRATION_STATEMENTS,
)
from tests.execution_support import remove_v20


class ProactiveContactStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-contact-schema-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        runtime = self.open_runtime()
        self.database = runtime.database_path
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("""INSERT INTO background_deliveries
                (delivery_id, owner, origin_key, request_json, payload_hash, sender_json, task_id, state)
                VALUES ('original', 'agenda', 'origin', '{"保留":"原请求"}', 'hash', '{}', 'task', 'accepted')""")
            remove_v20(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V19,))
            connection.commit()
            self.before = {table: connection.execute(f'SELECT * FROM "{table}"').fetchall()
                for table in V19_REQUIRED_TABLES - {"runtime_metadata", "schema_migrations"}}

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id="contact-schema")
        self.addCleanup(runtime.close)
        return runtime

    def assert_preserved(self, runtime):
        self.assertEqual({table: [tuple(row) for row in runtime.read_all(f'SELECT * FROM "{table}"', ())]
            for table in self.before}, self.before)

    def test_populated_v19_upgrade_preserves_original_rows_and_historical_fingerprints(self):
        runtime = self.open_runtime()
        self.assert_preserved(runtime)
        row = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V19_TO_V20_ID,))
        self.assertEqual((row["from_version"], row["to_version"], row["fingerprint"]),
            (SCHEMA_VERSION_V19, SCHEMA_VERSION_V20, MIGRATION_V19_TO_V20_FINGERPRINT))
        old = runtime.read_one("SELECT * FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V18_TO_V19_ID,))
        self.assertEqual((old["to_version"], old["fingerprint"]), (SCHEMA_VERSION_V19, MIGRATION_V18_TO_V19_FINGERPRINT))
        runtime.close()
        self.assert_preserved(self.open_runtime())

    def test_failed_upgrade_rolls_back_tables_version_and_receipt(self):
        with patch("companion_v2.storage.runtime.V20_MIGRATION_STATEMENTS", V20_MIGRATION_STATEMENTS + ("INVALID UPGRADE",)):
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=self.root, installation_id="contact-schema")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V19)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'proactive_contacts'").fetchone())
            self.assertIsNone(connection.execute("SELECT 1 FROM schema_migrations WHERE migration_id = ?", (MIGRATION_V19_TO_V20_ID,)).fetchone())
        self.assert_preserved(self.open_runtime())

    def test_partial_future_table_is_rejected_without_mutating_v19(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE proactive_contacts(contact_id TEXT)")
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id="contact-schema")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM runtime_metadata WHERE key = 'schema_version'").fetchone()[0], SCHEMA_VERSION_V19)

    def test_tampered_upgrade_receipt_is_rejected(self):
        runtime = self.open_runtime()
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE schema_migrations SET fingerprint = 'tampered' WHERE migration_id = ?", (MIGRATION_V19_TO_V20_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id="contact-schema")
