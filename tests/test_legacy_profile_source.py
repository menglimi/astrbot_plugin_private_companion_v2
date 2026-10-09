from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.legacy.data_migration import build_data_plan


class LegacyPrimaryProfileSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-profile-source-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_sqlite(self, path: Path, payload, *, deleted=()):
        deleted = tuple(deleted)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.executescript("""
                CREATE TABLE store_sections (
                    section_name TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    checksum TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    is_deleted INTEGER NOT NULL
                );
                CREATE TABLE store_meta (
                    meta_key TEXT PRIMARY KEY,
                    meta_value TEXT NOT NULL
                );
                PRAGMA user_version = 2;
            """)
            for revision, (name, value) in enumerate(payload.items(), start=1):
                raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT INTO store_sections VALUES (?, ?, ?, ?, 2, ?, 0)",
                    (name, raw, float(revision), digest, revision),
                )
            for offset, name in enumerate(deleted, start=len(payload) + 1):
                raw = "null"
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT INTO store_sections VALUES (?, ?, ?, ?, 2, ?, 1)",
                    (name, raw, float(offset), digest, offset),
                )
            maximum_revision = len(payload) + len(tuple(deleted))
            connection.executemany("INSERT INTO store_meta VALUES (?, ?)", (
                ("initialized", "1"), ("next_revision", str(maximum_revision + 1)),
            ))
            connection.commit()
        finally:
            connection.close()

    def marker(self, backend, sqlite_path=""):
        self.write_json(self.root / ".storage-backend-state.json", {
            "backend": backend,
            "sqlite_path": sqlite_path,
        })

    def assert_profile_rejected(self, plan, reason):
        self.assertEqual(plan.profile_summary["non_equivalent_reason"], reason)
        self.assertEqual(plan.profile_summary["source_groups"], 0)
        self.assertEqual(plan.group_networks, ())

    def test_json_only_keeps_existing_primary_profile_behavior(self):
        self.write_json(self.root / "companions.json", {"groups": {"json-group": {}}})

        plan = build_data_plan(self.root)

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["format"], "json")
        self.assertEqual(plan.document()["selected_persona"]["state"], "ready")

    def test_sqlite_only_primary_profile_is_loaded(self):
        self.write_sqlite(self.root / "companions.db", {"groups": {"db-group": {}}})
        self.marker("sqlite")

        plan = build_data_plan(self.root)

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["format"], "sqlite")
        self.assertEqual(plan.document()["selected_persona"]["source_path"], "companions.db")

    def test_configuration_selects_sqlite_over_stale_json(self):
        self.write_json(self.root / "companions.json", {"groups": {"stale-json": {}}})
        self.write_sqlite(self.root / "companions.db", {"groups": {"current-db": {}}})
        self.marker("sqlite")

        plan = build_data_plan(self.root, v1_configuration={
            "basic_config": {"storage_backend": "sqlite"},
        })

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["source_path"], "companions.db")
        self.assertEqual(plan.document()["selected_persona"]["authority"],
                         "configuration+backend_state")

    def test_custom_sqlite_path_is_honored(self):
        custom = self.root / "state" / "primary-profile.db"
        self.write_json(self.root / "companions.json", {"groups": {"stale-json": {}}})
        self.write_sqlite(custom, {"groups": {"custom-db": {}}})

        plan = build_data_plan(self.root, v1_configuration={
            "basic_config.storage_backend": "sqlite",
            "basic_config.storage_sqlite_path": str(custom),
        })

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["source_path"], "state/primary-profile.db")

    def test_conflicting_copies_without_authority_are_not_guessed(self):
        self.write_json(self.root / "companions.json", {"groups": {"json-group": {}}})
        self.write_sqlite(self.root / "companions.db", {"groups": {"db-group": {}}})

        plan = build_data_plan(self.root)

        self.assert_profile_rejected(plan, "core_profile_ambiguous")
        self.assertEqual(plan.document()["selected_persona"]["state"], "ambiguous")

    def test_matching_copies_are_accepted_when_authority_is_unavailable(self):
        payload = {"groups": {"shared-group": {}}}
        self.write_json(self.root / "companions.json", payload)
        self.write_sqlite(self.root / "companions.db", payload)

        plan = build_data_plan(self.root)

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["authority"], "matching_copies")

    def test_selected_missing_or_corrupt_sqlite_never_falls_back_to_json(self):
        self.write_json(self.root / "companions.json", {"groups": {"stale-json": {}}})
        self.marker("sqlite")
        cases = (
            ("missing", "core_profile_missing"),
            ("corrupt", "profile_database_unreadable"),
        )
        for case, reason in cases:
            with self.subTest(case=case):
                database = self.root / "companions.db"
                if database.exists():
                    database.unlink()
                if case == "corrupt":
                    database.write_bytes(b"not a sqlite database")

                plan = build_data_plan(self.root)

                self.assert_profile_rejected(plan, reason)

    def test_selected_missing_or_corrupt_json_never_falls_back_to_sqlite(self):
        self.write_sqlite(self.root / "companions.db", {"groups": {"stale-db": {}}})
        cases = (
            ("missing", "core_profile_missing"),
            ("corrupt", "core_profile_unreadable"),
        )
        for case, reason in cases:
            with self.subTest(case=case):
                path = self.root / "companions.json"
                if path.exists():
                    path.unlink()
                if case == "corrupt":
                    path.write_text("{broken", encoding="utf-8")

                plan = build_data_plan(self.root, v1_configuration={"storage_backend": "json"})

                self.assert_profile_rejected(plan, reason)

    def test_configuration_and_backend_marker_disagreement_is_reported(self):
        self.write_json(self.root / "companions.json", {"groups": {"json-group": {}}})
        self.write_sqlite(self.root / "companions.db", {"groups": {"db-group": {}}})
        self.marker("sqlite")

        plan = build_data_plan(self.root, v1_configuration={"storage_backend": "json"})

        self.assert_profile_rejected(plan, "core_profile_authority_conflict")

    def test_tombstoned_sqlite_sections_are_not_resurrected(self):
        self.write_sqlite(self.root / "companions.db", {"groups": {"active": {}}},
                          deleted=("worldbook_entries",))
        self.marker("sqlite")

        plan = build_data_plan(self.root)

        self.assertEqual(plan.profile_summary["source_groups"], 1)
        self.assertEqual(plan.document()["selected_persona"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
