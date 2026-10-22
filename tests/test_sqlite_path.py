import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.storage.sqlite_path import readonly_uri


class ReadonlySQLitePathTests(unittest.TestCase):
    def test_unicode_and_reserved_characters_remain_readonly_on_the_current_drive(self):
        with TemporaryDirectory(prefix="sqlite-只读-100%#-") as temporary:
            path = Path(temporary) / "资料 #100%.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE evidence (value TEXT)")
                connection.execute("INSERT INTO evidence VALUES ('retained')")
                connection.commit()
            with closing(sqlite3.connect(readonly_uri(path), uri=True)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM evidence").fetchone(), ("retained",))
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("DELETE FROM evidence")

    def test_readonly_open_never_creates_a_missing_source(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing.sqlite3"
            with self.assertRaises(sqlite3.OperationalError):
                sqlite3.connect(readonly_uri(path), uri=True)
            self.assertFalse(path.exists())
