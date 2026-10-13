import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.storage.semantic import SemanticStore


class SemanticStoreTests(unittest.TestCase):
    def test_schema_six_learning_rows_gain_retry_cooldown_without_data_loss(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "semantic-catalog.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE learning (owner TEXT PRIMARY KEY, checked_at REAL NOT NULL)")
            db.execute("INSERT INTO learning VALUES ('group-a', 123.5)")
            db.execute("PRAGMA user_version=6")
            db.commit()
            db.close()

            store = SemanticStore(Path(temporary))

            with store.db() as db:
                row = db.execute("SELECT checked_at,retry_after FROM learning WHERE owner='group-a'").fetchone()
                self.assertEqual((row["checked_at"], row["retry_after"]), (123.5, 0))
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 8)

    def test_group_slang_learning_uses_v1_cadence_and_preserves_explicit_interval(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)
            store = SemanticStore(path)
            self.assertEqual(store.settings()["learning_interval_seconds"], 21600)
            with store.db() as db:
                self.assertIn("retry_after", {row["name"] for row in db.execute("PRAGMA table_info(learning)")})
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 8)
            with store.db() as db:
                db.execute("UPDATE settings SET revision=3,payload=?,explicit='[]' WHERE id=1",
                           (json.dumps({"learning_interval_seconds": 900}),))

            upgraded = SemanticStore(path)
            snapshot = upgraded.configuration_snapshot()
            self.assertEqual(snapshot["values"]["learning_interval_seconds"], 21600)
            self.assertEqual(snapshot["revision"], 4)

            with upgraded.db() as db:
                db.execute("UPDATE settings SET revision=5,payload=?,explicit=? WHERE id=1",
                           (json.dumps({"learning_interval_seconds": 900}),
                            json.dumps(["learning_interval_seconds"])))
            explicit = SemanticStore(path).configuration_snapshot()
            self.assertEqual(explicit["values"]["learning_interval_seconds"], 900)
            self.assertEqual(explicit["revision"], 5)

    def test_group_candidate_counts_accumulate_once_per_source_and_stay_isolated(self):
        with TemporaryDirectory() as temporary:
            store = SemanticStore(Path(temporary))
            first = store.record_slang_candidates("group-a", "event-1", ("观星局", "观星局"), observed_at=1)
            duplicate = store.record_slang_candidates("group-a", "event-1", ("观星局",), observed_at=2)
            second = store.record_slang_candidates("group-a", "event-2", ("观星局", "摸鱼王"), observed_at=3)

            self.assertEqual(first, {"观星局": 1})
            self.assertEqual(duplicate, {"观星局": 1})
            self.assertEqual(second, {"观星局": 2, "摸鱼王": 1})
            self.assertEqual(store.slang_candidate_counts("group-b"), {})
