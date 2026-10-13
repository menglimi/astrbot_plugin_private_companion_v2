"""V44→V45：人格草稿版本表落库，且旧库升级不丢数据。

这一条迁移是纯新增（一张表 + 一条索引 + 两个只读触发器），所以升级路径必须证明两件事：
旧库里已有的行还在，以及升级确实发生了（``schema_migrations`` 多一条、并且
``migration_count()`` 也跟着涨）。只在内存里新建一个库是证明不了第二件的——
真实用户手上的库是旧的。
"""

from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
import unittest

from companion_v2.storage import schema
from companion_v2.storage.persona_craft_schema import PERSONA_CRAFT_TABLES, PERSONA_CRAFT_TRIGGERS
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from tests.execution_support import remove_v45


NEW_TABLES = frozenset({"persona_draft_versions"})


class PersonaCraftMigrationTests(unittest.TestCase):
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

    def downgrade_to_v44(self):
        """把新库退回到 v44：这正是「磁盘上已经存在的旧库」的样子。"""
        with closing(sqlite3.connect(self.database)) as connection:
            remove_v45(connection)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                               (schema.SCHEMA_VERSION_V44,))
            connection.commit()

    def test_a_fresh_root_includes_the_v45_draft_table_and_triggers(self):
        self.open_runtime()
        self.assertEqual(self.query("SELECT value FROM runtime_metadata WHERE key='schema_version'")[0][0],
                         schema.SCHEMA_VERSION)
        self.assertGreaterEqual(schema.migration_count(), 44)
        table = self.query("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'persona_draft_versions'")
        self.assertEqual(len(table), 1)
        triggers = {row[0] for row in self.query(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'persona_draft_versions_%'")}
        self.assertEqual(triggers, set(PERSONA_CRAFT_TRIGGERS))
        self.assertEqual(schema.PERSONA_CRAFT_TABLES, NEW_TABLES)
        self.assertEqual(schema.V45_REQUIRED_TABLES - schema.V44_REQUIRED_TABLES, NEW_TABLES)

    def test_the_whole_chain_is_recorded_and_the_count_advanced(self):
        self.open_runtime()
        recorded = self.query("SELECT COUNT(*) FROM schema_migrations")[0][0]
        self.assertEqual(recorded, schema.migration_count())
        # 迁移数必须真的比 v44 时多：只断言「等于派生值」在没加迁移时也成立。
        # v44 时的迁移数是 43（V1→V2 … V43→V44），加了 V44→V45 之后是 44。
        earlier = sum(int(row["to_version"].rsplit(".v", 1)[1]) <= 44
                      for row in self.query("SELECT to_version FROM schema_migrations"))
        self.assertEqual(earlier, 43)
        self.assertGreaterEqual(schema.migration_count(), earlier + 1)
        self.assertGreaterEqual(recorded, 44)
        row = self.query("SELECT from_version, to_version, fingerprint FROM schema_migrations "
                         "WHERE migration_id = ?", (schema.MIGRATION_V44_TO_V45_ID,))
        self.assertEqual(len(row), 1, "the v45 draft migration must have run")
        self.assertEqual((row[0]["from_version"], row[0]["to_version"]),
                         (schema.SCHEMA_VERSION_V44, schema.SCHEMA_VERSION_V45))
        self.assertEqual(row[0]["fingerprint"], schema.MIGRATION_V44_TO_V45_FINGERPRINT)

    def test_an_old_store_upgrades_without_losing_rows(self):
        runtime = self.open_runtime()
        # 一条 v44 时代就存在的数据（阅读归档表在 v42 就有）。
        with runtime.transaction() as connection:
            connection.execute(
                """INSERT INTO reading_archive_entries(owner_key, entry_id, kind, title, author, origin,
                       metadata_json, state, revision, created_at, updated_at)
                   VALUES ('owner-a', 'entry-1', 'novel', '旧书架上的书', '', 'manual', '{}', 'available', 1,
                           '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')""")
        runtime.close()
        self.downgrade_to_v44()
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE name = 'persona_draft_versions'"), [])

        upgraded = self.open_runtime()
        self.assertEqual(upgraded.read_one(
            "SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], schema.SCHEMA_VERSION)
        kept = self.query("SELECT title, state FROM reading_archive_entries WHERE entry_id = 'entry-1'")
        self.assertEqual([(row[0], row[1]) for row in kept], [("旧书架上的书", "available")])
        self.assertEqual(len(self.query("SELECT 1 FROM schema_migrations WHERE migration_id = ?",
                                        (schema.MIGRATION_V44_TO_V45_ID,))), 1)
        self.assertEqual(len(self.query("SELECT name FROM sqlite_master WHERE name = 'persona_draft_versions'")), 1)

    def test_reopening_an_upgraded_root_is_a_no_op(self):
        self.open_runtime()
        first = self.query("SELECT COUNT(*) FROM schema_migrations")[0][0]
        self.open_runtime()
        self.assertEqual(self.query("SELECT COUNT(*) FROM schema_migrations")[0][0], first)

    def test_a_root_with_the_table_but_no_migration_record_is_refused(self):
        """表在、迁移记录不在，是「半升级」而不是「已升级」：只能拒绝打开。"""
        self.open_runtime().close()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("DELETE FROM schema_migrations WHERE migration_id = ?",
                               (schema.MIGRATION_V44_TO_V45_ID,))
            connection.commit()
        with self.assertRaises(StorageOpenError):
            StorageRuntime.open(data_root=self.root, installation_id="installation-a")

    def test_the_table_refuses_to_rewrite_history_at_the_sql_level(self):
        runtime = self.open_runtime()
        with runtime.transaction() as connection:
            connection.execute(
                """INSERT INTO persona_draft_versions(owner_key, version_id, sequence, kind, draft_text,
                       original_text, persona_name, note, restored_from, created_at)
                   VALUES ('owner-a', 'persona-draft-v000001', 1, 'draft', '草稿', '原文  ', 'original',
                           '第一版', NULL, '2026-09-30T00:00:00+00:00')""")
        runtime.close()
        with closing(sqlite3.connect(self.database)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE persona_draft_versions SET note = 'rewritten'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM persona_draft_versions")
            connection.rollback()
        self.assertEqual(self.query("SELECT note FROM persona_draft_versions")[0][0], "第一版")

    def test_a_restore_must_name_its_source_and_a_draft_must_not(self):
        runtime = self.open_runtime()
        with self.assertRaises(sqlite3.IntegrityError):
            with runtime.transaction() as connection:
                connection.execute(
                    """INSERT INTO persona_draft_versions(owner_key, version_id, sequence, kind, draft_text,
                           original_text, persona_name, note, restored_from, created_at)
                       VALUES ('owner-a', 'persona-draft-v000001', 1, 'restore', '草稿', '原文', 'original',
                               '撤回', NULL, '2026-09-30T00:00:00+00:00')""")
        with self.assertRaises(sqlite3.IntegrityError):
            with runtime.transaction() as connection:
                connection.execute(
                    """INSERT INTO persona_draft_versions(owner_key, version_id, sequence, kind, draft_text,
                           original_text, persona_name, note, restored_from, created_at)
                       VALUES ('owner-a', 'persona-draft-v000002', 2, 'draft', '草稿', '原文', 'original',
                               '保存', 'persona-draft-v000001', '2026-09-30T00:00:00+00:00')""")


if __name__ == "__main__":
    unittest.main()
