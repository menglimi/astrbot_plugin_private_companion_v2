from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from companion_v2.legacy.archive import verify_v1_archive
from companion_v2.legacy.memory_archive import (
    build_memory_database_plan,
    copy_memory_database_archive,
)


class LegacyMemoryPackageArchiveTests(unittest.TestCase):
    def _database(self, path: Path, *, required=False, wal=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            if wal:
                connection.execute("PRAGMA journal_mode=WAL")
            if required:
                connection.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, body TEXT)")
                connection.execute("CREATE TABLE timeline (id TEXT PRIMARY KEY, body TEXT)")
                connection.execute("INSERT INTO memories VALUES ('m1', 'private fact')")
                connection.execute("INSERT INTO timeline VALUES ('t1', 'historic event')")
            else:
                connection.execute("CREATE TABLE req041 (id TEXT PRIMARY KEY, body TEXT)")
                connection.execute("INSERT INTO req041 VALUES ('r1', 'legacy scoped record')")
            connection.commit()
        except Exception:
            connection.close()
            raise
        if wal:
            return connection
        connection.close()

    @staticmethod
    def _sha256(path: Path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_archive_contains_both_database_snapshots_and_sidecars_idempotently(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            memory_dir = base / "astrbot_plugin_memory_companion"
            main = memory_dir / "memory_companion.db"
            scoped = memory_dir / "req041_scoped.db"
            sidecar = memory_dir / "historical_chat_imports" / "2026" / "import-001.jsonl"
            historical_db = memory_dir / "req041_backups" / "memory-old.db"
            phase_state = memory_dir / "relationship_phase.json"
            audit = memory_dir / "memory_audits" / "audit-001.json"
            outside = base / "not-in-plugin-data.json"
            self._database(main, required=True)
            scoped_connection = self._database(scoped, wal=True)
            self.addCleanup(scoped_connection.close)
            sidecar.parent.mkdir(parents=True)
            sidecar.write_bytes(b'{"opaque":"historical sidecar payload"}\n')
            historical_db.parent.mkdir(parents=True)
            historical_db.write_bytes(b"opaque historical database bytes")
            phase_state.write_bytes(b'{"phase":"opaque"}\n')
            audit.parent.mkdir(parents=True)
            audit.write_bytes(b'{"audit":"opaque"}\n')
            outside.write_bytes(b"must not be inventoried")
            scoped_wal = Path(str(scoped) + "-wal")
            source_hashes = {main: self._sha256(main), scoped: self._sha256(scoped),
                             sidecar: self._sha256(sidecar), historical_db: self._sha256(historical_db),
                             phase_state: self._sha256(phase_state), audit: self._sha256(audit),
                             scoped_wal: self._sha256(scoped_wal)}

            plan = build_memory_database_plan(main)
            self.assertEqual(plan.state, "ready")
            self.assertEqual({item.relative_path for item in plan.assets}, {
                "memory_companion.db", "req041_scoped.db",
                "historical_chat_imports/2026/import-001.jsonl",
                "req041_backups/memory-old.db", "relationship_phase.json",
                "memory_audits/audit-001.json",
            })
            self.assertNotIn(str(outside), {str(item.source_path) for item in plan.assets})
            self.assertEqual(plan.document()["record_count"], 2)
            scoped_asset = next(item for item in plan.document()["assets"]
                                if item["path"] == "req041_scoped.db")
            self.assertGreater(scoped_asset["wal_bytes"], 0)
            sidecar_asset = next(item for item in plan.document()["assets"]
                                 if item["path"] == "historical_chat_imports/2026/import-001.jsonl")
            self.assertEqual(scoped_asset["record_count"], 1)
            historical_assets = [item for item in plan.document()["assets"]
                                 if item["kind"] == "historical_file"]
            self.assertEqual(len(historical_assets), 4)
            self.assertEqual(sidecar_asset["record_count"], 0)
            self.assertEqual(next(item for item in plan.assets
                                  if item.relative_path == "historical_chat_imports/2026/import-001.jsonl").sha256,
                             source_hashes[sidecar])

            archive_root = base / "v2" / "legacy-v1-archives"
            first = copy_memory_database_archive(plan, archive_root)
            archive_path = archive_root / first["archive_id"]
            verified = verify_v1_archive(archive_path)
            manifest = json.loads((archive_path / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(verified["file_count"], 6)
            self.assertEqual(manifest["metadata"]["assets"], plan.document()["assets"])
            self.assertTrue(manifest["metadata"]["source_complete"])

            copied_main = sqlite3.connect(archive_path / "files" / "memory_companion.db")
            copied_scoped = sqlite3.connect(archive_path / "files" / "req041_scoped.db")
            try:
                self.assertEqual(copied_main.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)
                self.assertEqual(copied_main.execute("SELECT COUNT(*) FROM timeline").fetchone()[0], 1)
                self.assertEqual(copied_scoped.execute("SELECT COUNT(*) FROM req041").fetchone()[0], 1)
                self.assertEqual(copied_main.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(copied_scoped.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                copied_main.close()
                copied_scoped.close()
            self.assertEqual(self._sha256(archive_path / "files" / sidecar.relative_to(memory_dir)),
                             source_hashes[sidecar])
            for historical in (historical_db, phase_state, audit):
                self.assertEqual(self._sha256(archive_path / "files" / historical.relative_to(memory_dir)),
                                 source_hashes[historical])
            self.assertEqual({path: self._sha256(path) for path in source_hashes}, source_hashes)

            reopened = subprocess.run(
                [sys.executable, "-c",
                 "import json,sys; from companion_v2.legacy.archive import verify_v1_archive; "
                 "print(json.dumps(verify_v1_archive(sys.argv[1]), sort_keys=True))",
                 str(archive_path)],
                check=True, capture_output=True, text=True,
                cwd=Path(__file__).resolve().parents[1],
            )
            self.assertEqual(json.loads(reopened.stdout)["file_count"], 6)

            repeated = copy_memory_database_archive(build_memory_database_plan(main), archive_root)
            self.assertTrue(repeated["already_present"])
            self.assertEqual(repeated["archive_id"], first["archive_id"])
            self.assertEqual(verify_v1_archive(archive_path)["manifest_sha256"],
                             first["manifest_sha256"])
            scoped_connection.close()

    def test_scoped_database_or_sidecar_change_after_preview_is_rejected(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            memory_dir = base / "astrbot_plugin_memory_companion"
            main = memory_dir / "memory_companion.db"
            scoped = memory_dir / "req041_scoped.db"
            sidecar = memory_dir / "historical_chat_imports" / "import.jsonl"
            self._database(main, required=True)
            self._database(scoped)
            sidecar.parent.mkdir(parents=True)
            sidecar.write_bytes(b"opaque sidecar")
            plan = build_memory_database_plan(main)
            archive_root = base / "v2" / "archives"

            scoped_connection = sqlite3.connect(scoped)
            try:
                scoped_connection.execute("INSERT INTO req041 VALUES ('r2', 'changed')")
                scoped_connection.commit()
            finally:
                scoped_connection.close()
            with self.assertRaisesRegex(ValueError, "memory_archive_source_changed"):
                copy_memory_database_archive(plan, archive_root)
            self.assertFalse(archive_root.exists())

            refreshed = build_memory_database_plan(main)
            sidecar.write_bytes(b"changed sidecar")
            with self.assertRaisesRegex(ValueError, "memory_archive_source_changed"):
                copy_memory_database_archive(refreshed, archive_root)
            self.assertFalse(archive_root.exists())

    def test_unreadable_file_is_listed_and_marks_archive_incomplete(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            memory_dir = base / "astrbot_plugin_memory_companion"
            main = memory_dir / "memory_companion.db"
            unreadable = memory_dir / "memory_audits" / "restricted.json"
            self._database(main, required=True)
            unreadable.parent.mkdir(parents=True)
            unreadable.write_bytes(b"opaque")
            original_hash = __import__(
                "companion_v2.legacy.memory_archive", fromlist=["_sha256_file"]
            )._sha256_file

            def deny_one_path(path):
                if Path(path) == unreadable:
                    raise PermissionError("test-only unreadable input")
                return original_hash(path)

            archive_root = base / "v2" / "archives"
            with patch("companion_v2.legacy.memory_archive._sha256_file", side_effect=deny_one_path):
                plan = build_memory_database_plan(main)
                self.assertEqual(plan.state, "incomplete")
                self.assertIn(("memory_audits/restricted.json", "entry_unreadable"), plan.issues)
                archived = copy_memory_database_archive(plan, archive_root)
            self.assertFalse(archived["source_complete"])
            self.assertEqual(archived["source_issues"], [[
                "memory_audits/restricted.json", "entry_unreadable"]])
            manifest = json.loads((archive_root / archived["archive_id"] / "manifest.json")
                                 .read_text(encoding="utf-8"))
            self.assertFalse(manifest["metadata"]["source_complete"])
            self.assertEqual(manifest["metadata"]["source_issues"], archived["source_issues"])

    def test_capacity_limit_covers_the_complete_package_before_hashing_large_files(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            memory_dir = base / "astrbot_plugin_memory_companion"
            main = memory_dir / "memory_companion.db"
            scoped = memory_dir / "req041_scoped.db"
            historical = memory_dir / "memory_audits" / "audit.json"
            self._database(main, required=True)
            self._database(scoped)
            historical.parent.mkdir(parents=True)
            historical.write_bytes(b"oversized sidecar")
            database_bytes = main.stat().st_size + scoped.stat().st_size

            with patch("companion_v2.legacy.memory_archive.MAX_DATABASE_BYTES", database_bytes), \
                    patch("companion_v2.legacy.memory_archive._sha256_file",
                          side_effect=AssertionError("over-limit file must not be hashed")):
                plan = build_memory_database_plan(main)

            self.assertEqual(plan.state, "too_large")
            self.assertEqual(plan.total_bytes, database_bytes + historical.stat().st_size)


if __name__ == "__main__":
    unittest.main()
