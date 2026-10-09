"""V42→V43 adds the role reference-asset tables (C2-1/C2-2 shared asset layer)."""
from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
import unittest

from companion_v2.storage import schema
from companion_v2.storage.reference_asset_schema import (
    REFERENCE_ASSET_TABLES, reference_limit,
)
from companion_v2.storage.runtime import StorageRuntime
from tests.execution_support import remove_v51


NEW_TABLES = frozenset({"reference_assets", "reference_asset_roles", "wardrobe_items"})


class ReferenceAssetMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / StorageRuntime.DATABASE_FILENAME

    def open_runtime(self) -> StorageRuntime:
        runtime = StorageRuntime.open(data_root=self.root, installation_id="installation-a")
        self.addCleanup(runtime.close)
        return runtime

    def query(self, statement, parameters=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(statement, parameters).fetchall()

    def writing(self):
        """A connection that enforces foreign keys, as the runtime does.

        SQLite leaves ``foreign_keys`` off by default, so a bare connection would
        let a dangling asset reference through and make the constraint tests pass
        vacuously.
        """
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def test_fresh_root_lands_on_v43_with_the_asset_tables(self):
        self.open_runtime()
        version = self.query("SELECT value FROM runtime_metadata WHERE key = 'schema_version'")[0][0]
        # The head version moves as later migrations land; what this test owns is
        # that the v43 asset migration ran and its tables exist.
        self.assertEqual(version, schema.SCHEMA_VERSION)
        recorded = self.query("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = ?",
                              (schema.MIGRATION_V42_TO_V43_ID,))[0][0]
        self.assertEqual(recorded, 1, "the v43 asset migration must have run")
        names = {row[0] for row in self.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue(NEW_TABLES.issubset(names), NEW_TABLES - names)
        self.assertEqual(schema.REFERENCE_ASSET_TABLES if hasattr(schema, "REFERENCE_ASSET_TABLES")
                         else REFERENCE_ASSET_TABLES, NEW_TABLES)
        columns = {row[1] for row in self.query("PRAGMA table_info(reference_assets)")}
        self.assertIn("position", columns)
        final_migration = self.query("SELECT from_version, to_version FROM schema_migrations WHERE migration_id = ?",
                                     (schema.MIGRATION_V50_TO_V51_ID,))
        self.assertEqual(len(final_migration), 1)
        self.assertEqual((final_migration[0]["from_version"], final_migration[0]["to_version"]),
                         (schema.SCHEMA_VERSION_V50, schema.SCHEMA_VERSION_V51))

    def test_the_whole_migration_chain_is_recorded(self):
        self.open_runtime()
        recorded = self.query("SELECT COUNT(*) FROM schema_migrations")[0][0]
        self.assertEqual(recorded, schema.migration_count())
        # The count is derived, so it must also have actually grown past v42.
        self.assertGreaterEqual(recorded, 42)
        row = self.query("SELECT from_version, to_version, fingerprint FROM schema_migrations "
                         "WHERE migration_id = ?", (schema.MIGRATION_V42_TO_V43_ID,))
        self.assertEqual(len(row), 1)
        self.assertEqual((row[0]["from_version"], row[0]["to_version"]),
                         (schema.SCHEMA_VERSION_V42, schema.SCHEMA_VERSION_V43))
        self.assertEqual(row[0]["fingerprint"], schema.MIGRATION_V42_TO_V43_FINGERPRINT)

    def test_the_trigger_cursors_arrived_after_the_asset_tables(self):
        # v44 is independent of v43: the shelf's throttle cursor is its own step, so
        # a root that already had reference assets still upgrades.
        self.open_runtime()
        row = self.query("SELECT from_version, to_version FROM schema_migrations WHERE migration_id = ?",
                         (schema.MIGRATION_V43_TO_V44_ID,))
        self.assertEqual(len(row), 1)
        self.assertEqual((row[0]["from_version"], row[0]["to_version"]),
                         (schema.SCHEMA_VERSION_V43, schema.SCHEMA_VERSION_V44))
        names = {item[0] for item in self.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("reading_archive_triggers", names)

    def test_reopening_an_upgraded_root_is_a_no_op(self):
        self.open_runtime()
        first = self.query("SELECT COUNT(*) FROM schema_migrations")[0][0]
        self.open_runtime()
        self.assertEqual(self.query("SELECT COUNT(*) FROM schema_migrations")[0][0], first)

    def test_v50_assets_keep_their_existing_order_after_gallery_migration(self):
        runtime = self.open_runtime()
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v51(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                               (schema.SCHEMA_VERSION_V50,))
            for owner, asset_id, created_at in (("owner-a", "b", "2026-10-02"),
                                               ("owner-a", "a", "2026-10-01"),
                                               ("owner-a", "c", "2026-10-02"),
                                               ("owner-b", "d", "2026-10-03")):
                connection.execute("""INSERT INTO reference_assets
                    (owner_key, asset_id, kind, role, label, content_hash, size_bytes, mime_type,
                     media_ref, source, state, revision, created_at, updated_at)
                    VALUES(?, ?, 'reference_image', 'identity', '', ?, 10, 'image/png',
                           'media', 'operator', 'active', 1, ?, ?)""",
                    (owner, asset_id, "a" * 64, created_at, created_at))
            connection.commit()
        self.open_runtime()
        rows = self.query("SELECT owner_key, asset_id, position FROM reference_assets ORDER BY owner_key, position")
        self.assertEqual([tuple(row) for row in rows],
                         [("owner-a", "a", 0), ("owner-a", "b", 1), ("owner-a", "c", 2), ("owner-b", "d", 0)])

    def test_reference_assets_carry_the_hash_and_role_constraints(self):
        self.open_runtime()
        columns = {row[1]: row for row in
                   self.query("PRAGMA table_info(reference_assets)")}
        for name in ("owner_key", "asset_id", "kind", "role", "content_hash",
                     "size_bytes", "mime_type", "media_ref", "source", "state", "revision"):
            self.assertIn(name, columns, name)
        # A registration without a full SHA-256 is not a registration.
        connection = self.writing()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO reference_assets(
                    owner_key, asset_id, kind, role, label, content_hash, size_bytes, mime_type,
                    media_ref, source, state, revision, created_at, updated_at, position)
                    VALUES('owner', 'asset-short', 'reference_image', 'identity', '', 'abc',
                    10, 'image/png', 'media-1', 'operator', 'active', 1, 'now', 'now', 0)""")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO reference_asset_roles VALUES('owner', 'missing', 'identity', 'now')")

    def test_a_role_outside_the_declared_vocabulary_is_rejected(self):
        self.open_runtime()
        connection = self.writing()
        connection.execute(
                """INSERT INTO reference_assets(
                    owner_key, asset_id, kind, role, label, content_hash, size_bytes, mime_type,
                    media_ref, source, state, revision, created_at, updated_at, position) VALUES(
                    'owner', 'asset-1', 'reference_image', 'identity', 'label', ?, 10,
                    'image/png', 'media-1', 'operator', 'active', 1, 'now', 'now', 0)""",
            ("a" * 64,))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO reference_asset_roles VALUES('owner', 'asset-1', 'made_up_role', 'now')")

    def test_wardrobe_items_may_point_at_a_registered_asset_or_stand_alone(self):
        self.open_runtime()
        connection = self.writing()
        # An item without an image is legitimate, so asset_id must be nullable.
        connection.execute(
            """INSERT INTO wardrobe_items VALUES(
                'owner', 'item-1', NULL, '米色针织衫', '常穿', '["针织"]',
                'operator', 'active', 1, 'now', 'now')""")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO wardrobe_items VALUES(
                    'owner', 'item-2', 'no-such-asset', '外套', '', '[]',
                    'operator', 'active', 1, 'now', 'now')""")

    def test_the_registration_limit_is_declared_not_implied(self):
        self.assertEqual(reference_limit(), 24)
        self.assertEqual(schema.REFERENCE_ASSET_TABLES, NEW_TABLES)


if __name__ == "__main__":
    unittest.main()
