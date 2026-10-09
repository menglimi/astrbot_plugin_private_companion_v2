from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.storage_location import (OWNER_NAME, PLUGIN_NAME, POINTER_NAME,
                                           prepare_storage_root, selected_backup_directory, selected_root)
from companion_v2.storage.backup import BACKUP_FORMAT, InstallationBackup
from companion_v2.storage.management import (cleanup_backups, cleanup_plan, copy_backup_snapshots,
                                             inventory, remove_transferred_backup_snapshots)
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def add_snapshot(root: Path, identifier: str, created_at: datetime, size: int) -> None:
    directory = root / "installations" / "main" / "runtime" / "backups"
    add_snapshot_to(directory, identifier, created_at, size)


def add_snapshot_to(directory: Path, identifier: str, created_at: datetime, size: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"companion-v2-{identifier}.sqlite3").write_bytes(b"x" * size)
    (directory / f"companion-v2-{identifier}.json").write_text(json.dumps({
        "format": BACKUP_FORMAT, "snapshot_id": identifier,
        "created_at": created_at.isoformat(), "content_hash": "fixture",
    }), encoding="utf-8")


class StorageManagementTests(unittest.TestCase):
    def test_usage_inventory_splits_database_backups_and_other_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "profiles" / "main" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "companion-v2.sqlite3").write_bytes(b"a" * 10)
            (runtime / "companion-v2.sqlite3-wal").write_bytes(b"b" * 2)
            add_snapshot(root, "a" * 32, NOW, 5)
            (root / "misc.json").write_bytes(b"{}")

            result = inventory(root)

            self.assertEqual(result["total_bytes"], 10 + 2 + 5 + len(
                (root / "installations" / "main" / "runtime" / "backups" /
                 ("companion-v2-" + "a" * 32 + ".json")).read_bytes()) + 2)
            self.assertEqual(result["categories"]["database"]["files"], 2)
            self.assertEqual(result["categories"]["backups"]["files"], 2)
            self.assertEqual(result["categories"]["other"]["files"], 1)
            self.assertIsNotNone(result["free_bytes"])

    def test_external_backup_directory_is_counted_and_managed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            external = Path(temporary) / "other-disk" / "snapshots"
            root.mkdir()
            add_snapshot_to(external, "a" * 32, NOW, 5)

            result = inventory(root, backup_directory=external)
            plan = cleanup_plan(root, retention_count=1, retention_days=90, now=NOW,
                                backup_directory=external)

            self.assertEqual(result["categories"]["backups"]["files"], 2)
            self.assertEqual(result["categories"]["backups"]["bytes"], result["total_bytes"])
            self.assertIsNotNone(result["backup_free_bytes"])
            self.assertEqual(plan["snapshot_count"], 1)

    def test_backup_directory_change_copies_verified_pairs_before_removing_source(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "runtime" / "backups"
            destination = base / "external" / "snapshots"
            add_snapshot_to(source, "a" * 32, NOW, 5)

            transferred = copy_backup_snapshots(source, destination)

            self.assertEqual(len(transferred), 1)
            self.assertTrue((destination / ("companion-v2-" + "a" * 32 + ".sqlite3")).exists())
            self.assertTrue((source / ("companion-v2-" + "a" * 32 + ".sqlite3")).exists())
            self.assertEqual(remove_transferred_backup_snapshots(transferred, destination), 1)
            self.assertFalse((source / ("companion-v2-" + "a" * 32 + ".sqlite3")).exists())

    def test_backup_directory_must_be_absolute_and_separate(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            self.assertEqual(selected_backup_directory(root, ""), root.resolve() / "backups")
            with self.assertRaises(ValueError):
                selected_backup_directory(root, "relative")
            with self.assertRaises(ValueError):
                selected_backup_directory(root, str(root / "nested"))

    def test_retention_combines_count_and_age_but_keeps_the_newest_snapshot(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, age in enumerate((0, 2, 10, 40)):
                add_snapshot(root, f"{index + 1:032x}", NOW - timedelta(days=age), 100 + index)

            by_count = cleanup_plan(root, retention_count=2, retention_days=90, now=NOW)
            self.assertEqual(by_count["snapshot_count"], 4)
            self.assertEqual(by_count["remove_count"], 2)
            self.assertEqual(by_count["snapshot_ids"], [f"{3:032x}", f"{4:032x}"])

            by_age = cleanup_plan(root, retention_count=20, retention_days=5, now=NOW)
            self.assertEqual(by_age["snapshot_ids"], [f"{3:032x}", f"{4:032x}"])

            all_but_latest = cleanup_backups(root, retention_count=1, retention_days=1, now=NOW)
            self.assertEqual(all_but_latest["removed_count"], 3)
            self.assertTrue((root / "installations" / "main" / "runtime" / "backups" /
                             f"companion-v2-{1:032x}.sqlite3").is_file())
            self.assertFalse((root / "installations" / "main" / "runtime" / "backups" /
                              f"companion-v2-{2:032x}.sqlite3").exists())

    def test_external_location_migrates_and_can_be_returned_to_default(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            default = base / "astrbot-data" / PLUGIN_NAME
            default.mkdir(parents=True)
            (default / "profiles" / "main" / "runtime").mkdir(parents=True)
            (default / "profiles" / "main" / "runtime" / "companion-v2.sqlite3").write_bytes(b"database")
            (default / "config.json").write_text("{}", encoding="utf-8")
            selected = base / "D-drive" / "AstrBotData"
            external = selected / PLUGIN_NAME

            actual = prepare_storage_root(default, {"storage": {"path": str(selected)}})

            self.assertEqual(actual, external.resolve())
            self.assertEqual((external / "config.json").read_text(encoding="utf-8"), "{}")
            self.assertEqual((external / "profiles" / "main" / "runtime" /
                              "companion-v2.sqlite3").read_bytes(), b"database")
            self.assertTrue((external / OWNER_NAME).is_file())
            self.assertEqual([path.name for path in default.iterdir()], [POINTER_NAME])
            self.assertEqual(prepare_storage_root(default, {"storage": {"path": str(selected)}}), external)

            restored = prepare_storage_root(default, {"storage": {"path": ""}})

            self.assertEqual(restored, default.resolve())
            self.assertEqual((default / "config.json").read_text(encoding="utf-8"), "{}")
            self.assertFalse((default / POINTER_NAME).exists())
            self.assertFalse(external.exists())

    def test_conflicting_destination_does_not_touch_current_data(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            default = base / "astrbot-data" / PLUGIN_NAME
            default.mkdir(parents=True)
            source = default / "keep.json"
            source.write_text("keep", encoding="utf-8")
            selected = base / "other"
            destination = selected / PLUGIN_NAME
            destination.mkdir(parents=True)
            (destination / "unrelated.txt").write_text("untouched", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "already contains files"):
                prepare_storage_root(default, {"storage": {"path": str(selected)}})

            self.assertEqual(source.read_text(encoding="utf-8"), "keep")
            self.assertEqual((destination / "unrelated.txt").read_text(encoding="utf-8"), "untouched")

    def test_restart_finishes_cleanup_after_pointer_switch_was_interrupted(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            default = base / "astrbot-data" / PLUGIN_NAME
            external = base / "D-drive" / PLUGIN_NAME
            external.mkdir(parents=True)
            (external / OWNER_NAME).write_text(json.dumps({
                "format": "companion-v2.storage-location.v1", "source": str(default), "id": "test",
            }), encoding="utf-8")
            (external / "owned.json").write_text("external", encoding="utf-8")
            default.mkdir(parents=True)
            (default / "stale-copy.json").write_text("stale", encoding="utf-8")
            (default / POINTER_NAME).write_text(json.dumps({
                "format": "companion-v2.storage-location.v1", "path": str(external),
                "cleanup_source": str(default),
            }), encoding="utf-8")

            actual = prepare_storage_root(default, {"storage": {"path": str(external.parent)}})

            self.assertEqual(actual, external.resolve())
            self.assertFalse((default / "stale-copy.json").exists())
            self.assertEqual((default / POINTER_NAME).read_text(encoding="utf-8"),
                             json.dumps({"format": "companion-v2.storage-location.v1",
                                         "path": str(external.resolve())}, sort_keys=True))

    def test_storage_target_must_be_absolute_and_separate(self):
        with TemporaryDirectory() as temporary:
            default = Path(temporary) / PLUGIN_NAME
            with self.assertRaises(ValueError):
                selected_root(default, "relative")
            with self.assertRaises(ValueError):
                selected_root(default, str(default / "nested"))

    def test_new_snapshot_applies_saved_retention_policy(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime"
            runtime = StorageRuntime.open(data_root=root, installation_id="storage-retention-test")
            try:
                clock = [NOW]
                backup = InstallationBackup(runtime, now=lambda: clock[0],
                                            retention_count=1, retention_days=90)
                backup.create(note="first").unwrap()
                clock[0] += timedelta(minutes=1)
                backup.create(note="second").unwrap()
                self.assertEqual(len(list(backup.directory.glob("companion-v2-*.sqlite3"))), 1)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
