from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.legacy.archive import verify_v1_archive
from companion_v2.legacy.memory_archive import (
    build_memory_database_plan,
    copy_memory_database_archive,
)
from companion_v2.legacy.migration import LegacyMigration, MigrationState


class LegacyMemoryArchiveTests(unittest.TestCase):
    def _database(self, plugin_data):
        directory = plugin_data / "astrbot_plugin_memory_companion"
        directory.mkdir(parents=True)
        path = directory / "memory_companion.db"
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA journal_mode=WAL")
        for table in ("memories", "timeline", "identities", "review_queue",
                      "memory_acl_rules", "memory_acl_policies", "withdrawals"):
            connection.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, body TEXT)')
        connection.execute("INSERT INTO memories VALUES ('m1', 'fact')")
        connection.execute("INSERT INTO timeline VALUES ('t1', 'event')")
        connection.execute("INSERT INTO review_queue VALUES ('r1', 'pending')")
        connection.commit()
        return path, connection

    def test_discovery_includes_the_separate_plugin_data_database(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            v1_root = base / "astrbot_plugin_private_companion"
            v1_root.mkdir()
            path, connection = self._database(base)
            try:
                result = LegacyMigration(v1_root=v1_root).discover().unwrap()
                finding = next(item for item in result
                               if item.source_id == "memory.timeline_and_governance")
                self.assertEqual(finding.state, MigrationState.DATA_READY.value)
                self.assertGreater(finding.byte_size, path.stat().st_size)
            finally:
                connection.close()

    def test_wal_snapshot_preserves_timeline_and_governance_and_is_idempotent(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            path, connection = self._database(base)
            source_db_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            wal_path = Path(str(path) + "-wal")
            source_wal_hash = hashlib.sha256(wal_path.read_bytes()).hexdigest()
            plan = build_memory_database_plan(path)
            self.assertEqual(plan.state, "ready")
            self.assertEqual(plan.table_counts["timeline"], 1)

            archive_root = base / "v2" / "legacy-v1-archives"
            first = copy_memory_database_archive(plan, archive_root)
            archive_path = archive_root / first["archive_id"]
            verified = verify_v1_archive(archive_path)
            imported = sqlite3.connect(archive_path / "files" / "memory_companion.db")
            try:
                try:
                    self.assertEqual(imported.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)
                    self.assertEqual(imported.execute("SELECT COUNT(*) FROM timeline").fetchone()[0], 1)
                    self.assertEqual(imported.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0], 1)
                    self.assertEqual(imported.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_db_hash)
                    self.assertEqual(hashlib.sha256(wal_path.read_bytes()).hexdigest(), source_wal_hash)
                finally:
                    imported.close()

                repeated = copy_memory_database_archive(build_memory_database_plan(path), archive_root)
            finally:
                connection.close()

            self.assertEqual(verified["file_count"], 1)
            self.assertEqual(first["integrity_check"], "ok")
            self.assertTrue(repeated["already_present"])

    def test_changed_source_after_preview_is_rejected_without_archive(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            path, connection = self._database(base)
            plan = build_memory_database_plan(path)
            connection.execute("INSERT INTO timeline VALUES ('t2', 'later')")
            connection.commit()
            archive_root = base / "v2" / "legacy-v1-archives"

            with self.assertRaisesRegex(ValueError, "memory_archive_source_changed"):
                copy_memory_database_archive(plan, archive_root)
            self.assertFalse(any(archive_root.glob("memory-*")))
            connection.close()

    def test_fingerprint_detects_same_size_content_change_with_restored_file_timestamp(self):
        with TemporaryDirectory() as temporary:
            path, connection = self._database(Path(temporary))
            connection.close()
            before_stat = path.stat()
            before = build_memory_database_plan(path)

            changed = sqlite3.connect(path)
            changed.execute("UPDATE memories SET body = 'tact' WHERE id = 'm1'")
            changed.commit()
            changed.close()
            os.utime(path, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))

            after_stat = path.stat()
            after = build_memory_database_plan(path)

            self.assertEqual(after_stat.st_size, before_stat.st_size)
            self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)
            self.assertEqual(after.table_counts, before.table_counts)
            self.assertEqual(after.schema_fingerprint, before.schema_fingerprint)
            self.assertEqual(after.state, "ready")
            self.assertNotEqual(after.fingerprint, before.fingerprint)

    def test_empty_wal_created_by_read_only_inventory_does_not_change_plan(self):
        with TemporaryDirectory() as temporary:
            path, connection = self._database(Path(temporary))
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.close()

            first = build_memory_database_plan(path)
            second = build_memory_database_plan(path)

            self.assertEqual(first.state, "ready")
            self.assertEqual(second.fingerprint, first.fingerprint)


if __name__ == "__main__":
    unittest.main()
