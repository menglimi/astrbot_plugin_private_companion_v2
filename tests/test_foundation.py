from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.sqlite import temporary_sqlite_database


class DeterministicClockTests(unittest.TestCase):
    def test_normalizes_to_utc_and_only_advances_explicitly(self) -> None:
        clock = DeterministicClock.at(
            datetime(2026, 9, 21, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        )

        self.assertEqual(clock.now(), datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(
            clock.advance(timedelta(minutes=15)),
            datetime(2026, 9, 21, 0, 15, tzinfo=timezone.utc),
        )
        with self.assertRaises(ValueError):
            clock.advance(timedelta(seconds=-1))
        with self.assertRaises(ValueError):
            clock.set(datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc))

    def test_rejects_naive_datetimes(self) -> None:
        with self.assertRaises(ValueError):
            DeterministicClock.at(datetime(2026, 9, 21, 0, 0))


class TemporarySQLiteTests(unittest.TestCase):
    def test_database_is_queryable_and_cleaned_after_context(self) -> None:
        database_path: Path
        with temporary_sqlite_database() as database:
            database_path = database.path
            database.connection.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, value TEXT)")
            database.connection.execute("INSERT INTO entries (value) VALUES (?)", ("fixture",))
            database.connection.commit()
            row = database.connection.execute("SELECT value FROM entries").fetchone()

            self.assertTrue(database_path.exists())
            self.assertEqual(row, ("fixture",))

        self.assertFalse(database_path.exists())
