"""Where a target's data lives when the selected profile is not it.

The failure this guards against is silent: pointing ``staging.profile_id`` at a new
name opens an empty store, the role reads as if it had forgotten everything, and the
old store sits untouched. Nothing is lost and nothing says so.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.profile_residency import profile_residency

TARGET = ("qq-main", "100", "200")


def pinned(platform: str = TARGET[0], account: str = TARGET[1], participant: str = TARGET[2]) -> dict:
    """A document shaped like a real pinned profile, reduced to what residency reads."""
    return {"scope": {"platform": platform, "account_id": account, "native_scope_id": participant},
            "subject": {"subject_id": participant}}


class ResidencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-residency-")
        self.root = Path(self.temporary.name)
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()

    def profile(self, name: str, *, document: dict | None = None, rows: int = 0) -> Path:
        directory = self.profiles / name
        runtime = directory / "runtime"
        runtime.mkdir(parents=True)
        if document is not None:
            (directory / "staging-config.json").write_text(
                json.dumps(document, ensure_ascii=False), encoding="utf-8")
        store = runtime / "companion-v2.sqlite3"
        connection = sqlite3.connect(store)
        try:
            connection.execute("CREATE TABLE conversation_inputs (batch_id TEXT)")
            for index in range(rows):
                connection.execute("INSERT INTO conversation_inputs VALUES (?)", (f"b{index}",))
            connection.commit()
        finally:
            connection.close()
        # Provisioned stores carry the schema and are therefore never tiny; pad the file
        # so a size-based check would call this "holds data" too.
        with store.open("ab") as handle:
            handle.write(b"\0" * 8192)
        return directory

    def test_a_new_profile_reports_where_the_targets_data_is(self):
        self.profile("in-use", document=pinned(), rows=3)
        self.profile("fresh", document=pinned(), rows=0)
        report = profile_residency(self.root, profile_id="fresh", target=TARGET)
        self.assertEqual(report, {"selected": "fresh", "holders": ["in-use"]})

    def test_a_profile_that_has_rows_is_not_reported(self):
        self.profile("in-use", document=pinned(), rows=3)
        self.profile("fresh", document=pinned(), rows=0)
        self.assertIsNone(profile_residency(self.root, profile_id="in-use", target=TARGET))

    def test_an_empty_store_is_not_mistaken_for_data(self):
        """A provisioned store has the full schema before any conversation happens.

        An earlier version compared the file against a byte threshold and so called every
        profile on the machine "holds data", which silently disabled the whole report.
        """
        self.profile("only", document=pinned(), rows=0)
        self.assertIsNone(profile_residency(self.root, profile_id="only", target=TARGET))

    def test_another_target_is_never_reported(self):
        self.profile("someone-else", document=pinned(participant="999"), rows=5)
        self.profile("fresh", document=pinned(), rows=0)
        self.assertIsNone(profile_residency(self.root, profile_id="fresh", target=TARGET))

    def test_an_unknown_target_never_reports(self):
        self.profile("in-use", document=pinned(), rows=3)
        self.assertIsNone(profile_residency(self.root, profile_id="fresh", target=None))

    def test_a_missing_or_damaged_profile_directory_does_not_raise(self):
        self.profile("in-use", document=pinned(), rows=3)
        (self.profiles / "broken").mkdir()
        (self.profiles / "broken" / "staging-config.json").write_text("{not json", encoding="utf-8")
        report = profile_residency(self.root, profile_id="broken", target=TARGET)
        self.assertEqual(report, {"selected": "broken", "holders": ["in-use"]})
        self.assertIsNone(profile_residency(self.root / "absent", profile_id="x", target=TARGET))


if __name__ == "__main__":
    unittest.main()
