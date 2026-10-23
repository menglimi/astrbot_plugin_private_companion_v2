import hashlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import companion_v2.legacy.archive as archive_module
from companion_v2.legacy.archive import (
    SCHEMA,
    build_v1_archive_plan,
    copy_v1_archive,
    verify_v1_archive,
)


class LegacyArchiveTests(unittest.TestCase):
    def test_snapshot_is_byte_exact_checksummed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1"
            source.mkdir()
            (source / "companions.json").write_bytes(b'{"old":"data"}\n')
            (source / "album" / "子目录").mkdir(parents=True)
            (source / "album" / "子目录" / "image.bin").write_bytes(bytes(range(256)) * 17)
            plan = build_v1_archive_plan(source)
            archive_root = root / "v2" / "legacy-v1-archives"

            first = copy_v1_archive(plan, archive_root)
            archive = archive_root / plan.fingerprint
            verified = verify_v1_archive(archive)
            second = copy_v1_archive(plan, archive_root)

            self.assertFalse(first["already_present"])
            self.assertTrue(second["already_present"])
            self.assertEqual(verified["file_count"], 2)
            self.assertEqual(verified["total_bytes"], plan.total_bytes)
            self.assertEqual((archive / "files" / "companions.json").read_bytes(),
                             (source / "companions.json").read_bytes())
            self.assertEqual((archive / "files" / "album" / "子目录" / "image.bin").read_bytes(),
                             (source / "album" / "子目录" / "image.bin").read_bytes())

    def test_changed_source_after_preview_does_not_commit_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1"
            source.mkdir()
            record = source / "record.json"
            record.write_bytes(b"before")
            plan = build_v1_archive_plan(source)
            record.write_bytes(b"after!")
            os.utime(record, ns=(record.stat().st_atime_ns, plan.files[0].modified_ns + 2_000_000_000))

            with self.assertRaisesRegex(ValueError, "archive_source_changed"):
                copy_v1_archive(plan, root / "v2" / "legacy-v1-archives")
            self.assertFalse((root / "v2" / "legacy-v1-archives" / plan.fingerprint).exists())
            self.assertFalse(any((root / "v2" / "legacy-v1-archives").glob(".staging-*")))

    def test_inventory_fingerprint_ignores_file_rewrites_but_tracks_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "v1"
            source.mkdir()
            record = source / "cache.json"
            record.write_bytes(b"version1")
            original = build_v1_archive_plan(source)

            record.write_bytes(b"version2")
            os.utime(record, ns=(record.stat().st_atime_ns, original.files[0].modified_ns + 2_000_000_000))
            updated = build_v1_archive_plan(source)
            self.assertNotEqual(updated.fingerprint, original.fingerprint)
            self.assertEqual(updated.inventory_fingerprint, original.inventory_fingerprint)

            record.write_bytes(b"version-two")
            resized = build_v1_archive_plan(source)
            self.assertNotEqual(resized.inventory_fingerprint, original.inventory_fingerprint)

    def test_corrupted_archive_bytes_fail_integrity_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1"
            source.mkdir()
            (source / "record.json").write_bytes(b"content")
            plan = build_v1_archive_plan(source)
            result = copy_v1_archive(plan, root / "v2" / "legacy-v1-archives")
            archived_file = root / "v2" / "legacy-v1-archives" / result["archive_id"] / "files" / "record.json"
            archived_file.write_bytes(b"changed")

            with self.assertRaisesRegex(ValueError, "archive_content_mismatch"):
                verify_v1_archive(archived_file.parents[1])

    def test_partial_archive_records_exclusions_and_is_only_allowed_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1"
            source.mkdir()
            (source / "readable.json").write_text("{}\n", encoding="utf-8")
            complete_plan = build_v1_archive_plan(source)
            issues = (("unreadable", "directory_unreadable"),)
            material = {"schema": SCHEMA,
                "files": [item.fingerprint_item() for item in complete_plan.files],
                "issues": [list(item) for item in issues]}
            fingerprint = hashlib.sha256(json.dumps(material, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            partial_plan = replace(complete_plan, issues=issues, fingerprint=fingerprint)
            destination = root / "v2" / "legacy-v1-archives"

            with patch.object(archive_module, "build_v1_archive_plan", return_value=partial_plan):
                with self.assertRaisesRegex(ValueError, "archive_source_incomplete"):
                    copy_v1_archive(partial_plan, destination)
                first = copy_v1_archive(partial_plan, destination, allow_incomplete=True)
                repeated = copy_v1_archive(partial_plan, destination, allow_incomplete=True)
                verified = verify_v1_archive(destination / partial_plan.fingerprint)

            self.assertFalse(first["complete"])
            self.assertEqual(first["excluded_count"], 1)
            self.assertTrue(repeated["already_present"])
            self.assertFalse(verified["complete"])
            self.assertEqual(verified["excluded_count"], 1)


    def test_archived_work_can_be_inspected_without_replaying_or_changing_it(self):
        import sqlite3
        from companion_v2.legacy.archived_work import archived_work_inventory, archived_work_rows
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'v1';(source/'framework_work').mkdir(parents=True)
            database=source/'framework_work'/'work.db'
            with sqlite3.connect(database) as connection:
                connection.executescript("CREATE TABLE jobs(id TEXT,status TEXT); INSERT INTO jobs VALUES('old','interrupted_unknown');")
            connection.close()
            before=hashlib.sha256(database.read_bytes()).hexdigest()
            plan=build_v1_archive_plan(source);copy_v1_archive(plan,root/'archive')
            inventory=archived_work_inventory(root/'archive')
            self.assertEqual(inventory['archives'][0]['areas']['work']['jobs'],1)
            rows=archived_work_rows(root/'archive',plan.fingerprint,'work','jobs')
            self.assertEqual(rows['items'][0]['status'],'interrupted_unknown')
            self.assertFalse(rows['execution_restored'])
            with self.assertRaises(ValueError):
                archived_work_rows(root/'archive','../v1','work','jobs')
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(),before)

    def test_nested_runtime_is_excluded_from_v1_archive_and_revalidated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1"
            runtime = source / "companion-7"
            runtime.mkdir(parents=True)
            (source / "companions.json").write_text("{}", encoding="utf-8")
            (runtime / "companion-v2.sqlite3").write_bytes(b"new runtime")
            plan = build_v1_archive_plan(source, exclude_roots=(runtime,))
            result = copy_v1_archive(plan, root / "archive")
            archive = root / "archive" / result["archive_id"]
            self.assertFalse((archive / "files" / "companion-7").exists())
            self.assertEqual(result["file_count"], 1)
            self.assertEqual(verify_v1_archive(archive)["file_count"], 1)


if __name__ == "__main__":
    unittest.main()
