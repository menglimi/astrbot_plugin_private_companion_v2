"""存储基线审计工具的定向测试。

只断言五件对外可见的事，不断言"某个内部函数被调用了"：
  1. **硬线越线**：退出码非 0，并且输出点名越线的那一项；
  2. **正常**：退出码 0；
  3. **只读性**：跑完之后主库与 `-wal` 的内容哈希、mtime、大小都不变，目录里也不
     多出 `-wal` / `-shm` / `-journal`。`-shm` 的**字节**刻意不在断言范围：它是
     SQLite 的 wal-index 共享内存，任何一次只读打开都会更新里面的读标记，
     ReadOnlyTests 里有一条对照用例把这条边界钉住（只断言它仍然存在、大小不变）。
  4. **没数据**：库不存在或为空时按「未初始化」处理，退出码 0、不抛异常、不刷栈。
  5. **提示项不影响退出码**：WAL／主库比值越线只出现在 notices／"! 提示"里，
     violations 为空、退出码不变（WAL 的硬线只保留绝对大小 > 32 MiB）。

被测对象是 tests/../tools/audit_storage_baseline.py。工具只用标准库、不导入
`companion_v2` 或 `astrbot_host`，所以这里也**不**需要 AstrBot 运行实例：
临时目录里手搓一个最小 SQLite 就够了。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "audit_storage_baseline.py"


def _load_tool():
    """按文件路径载入工具模块，避免依赖 tools/ 是不是一个包。"""
    spec = importlib.util.spec_from_file_location("audit_storage_under_test", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def run_cli(*arguments: str) -> subprocess.CompletedProcess:
    """用当前解释器跑真实命令行：退出码与输出都是被测行为的一部分。"""
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(TOOL_PATH), *arguments],
        capture_output=True, text=True, encoding="utf-8", check=False)


def run_in_process(*arguments: str) -> tuple[int, str]:
    """进程内调用 main()：用于需要替换阈值常量的分支（见最后的绝对值触发线）。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = TOOL.main(list(arguments))
    return code, buffer.getvalue()


def clean_database(path: pathlib.Path) -> None:
    """一个"什么都不到触发线"的最小库：小文档、少量历史。"""
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE memory_views (view_id TEXT PRIMARY KEY, document_json TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO memory_views VALUES (?, ?)",
            [("view-%d" % index, "短文" * 20) for index in range(3)])
        connection.execute("CREATE TABLE role_state_history (id INTEGER PRIMARY KEY, note TEXT)")
        connection.executemany(
            "INSERT INTO role_state_history VALUES (?, ?)", [(1, "a"), (2, "b")])
        connection.commit()
    finally:
        connection.close()


def breaching_database(path: pathlib.Path) -> None:
    """一个把四条触发线全部踩过的库：大文档 + 历史合计/单域双双越线。"""
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE memory_views (view_id TEXT PRIMARY KEY, document_json TEXT NOT NULL)")
        oversized = "x" * 70000                      # > 64 KiB，平均也远超 4 KiB
        connection.executemany(
            "INSERT INTO memory_views VALUES (?, ?)",
            [("view-%d" % index, oversized) for index in range(3)])
        connection.execute("CREATE TABLE role_state_history (id INTEGER PRIMARY KEY, note TEXT)")
        connection.executemany(
            "INSERT INTO role_state_history VALUES (?, ?)",
            [(index, "n") for index in range(1001)])  # 单域 > 1000
        connection.execute("CREATE TABLE conversation_sent_history (id INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO conversation_sent_history VALUES (?)",
            [(index,) for index in range(4000)])      # 合计 1001 + 4000 = 5001 > 5000
        connection.commit()
    finally:
        connection.close()


def content_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def directory_listing(root: pathlib.Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir())


def fingerprint(*paths: pathlib.Path) -> dict:
    """文件指纹：内容哈希 + mtime + 大小。三者任一变了都算被动过。"""
    return {path.name: (content_hash(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in paths}


def wal_backlog_database(directory: pathlib.Path) -> sqlite3.Connection:
    """造出"实例正在跑、WAL 有积压"的形态，返回必须由调用方持有的写连接。

    最后一个连接关闭时 SQLite 会 checkpoint 并删掉 `-wal`，那样就测不到常驻
    WAL 了——所以连接的所有权交给调用方。
    """
    database = directory / "companion-v2.sqlite3"
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE bulk (id INTEGER PRIMARY KEY, payload TEXT)")
    writer.executemany("INSERT INTO bulk VALUES (?, ?)",
                       [(index, "y" * 400) for index in range(2000)])
    writer.commit()
    # 先把已有内容 checkpoint 回主库（主库才不是 0 字节），再关掉自动 checkpoint，
    # 让接下来的写入全部堆在 -wal 里。
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.executemany("INSERT INTO bulk VALUES (?, ?)",
                       [(index, "z" * 400) for index in range(4001, 8000)])
    writer.commit()
    return writer


class ThresholdBreachTests(unittest.TestCase):
    def test_every_breach_is_named_and_exits_nonzero(self) -> None:
        """四条越线（历史合计、单域历史、文档最大、文档平均）都要被点名。"""
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            breaching_database(root / "companion-v2.sqlite3")

            result = run_cli("--data-root", str(root))

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("越线 4 项", result.stdout)
            # 断言"越线标记 + 检查项名"这一对，而不是单独出现过的字符串：
            # 检查项在表格里本来就会出现，只查名字等于什么都没查。
            for item in ("历史表合计行数", "单域历史最大行数",
                         "document_json 最大长度", "document_json 平均长度"):
                self.assertIn("✗ %s" % item, result.stdout)

    def test_json_report_lists_the_same_breaches(self) -> None:
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            breaching_database(root / "companion-v2.sqlite3")

            result = run_cli("--data-root", str(root), "--json")

            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "RED")
            self.assertEqual(
                sorted(check["key"] for check in report["violations"]),
                ["document_average", "document_max", "history_domain", "history_total"])

    def test_wal_absolute_limit_breach_exits_nonzero(self) -> None:
        """WAL 的**唯一硬线**（绝对值 > 32 MiB）越线必须判红。

        绝对值线用替换常量来测：不为它真造 33 MiB 写入。工具只 stat `-wal` 的
        大小、不解析它的内容，所以这里放一个非零的侧车文件就足以走到那条分支；
        主库不是 WAL 模式，SQLite 不会去读这个残留文件。
        """
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            clean_database(root / "companion-v2.sqlite3")
            (root / "companion-v2.sqlite3-wal").write_bytes(b"\0" * 1024)

            with mock.patch.object(TOOL, "WAL_ABSOLUTE_LIMIT_BYTES", 512):
                code, output = run_in_process("--data-root", str(root))

            self.assertEqual(code, 1, output)
            self.assertIn("✗ WAL 常驻大小", output)

    def test_wal_ratio_over_the_notice_line_does_not_change_the_exit_code(self) -> None:
        """比值越线只是提示：violations 里没有它，退出码不变。

        一条常驻阈值在小库上必然误报（主库几 MiB 时一次批量写入就能让比值过半），
        所以比值降级为提示项；这里用一个真实的 WAL 积压来测它。
        """
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            writer = wal_backlog_database(root)
            try:
                database = root / "companion-v2.sqlite3"
                wal = pathlib.Path(str(database) + "-wal")
                self.assertGreater(wal.stat().st_size, database.stat().st_size * 0.25)

                result = run_cli("--data-root", str(root), "--json")

                self.assertEqual(result.returncode, 0, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "OK")
                self.assertEqual(report["violations"], [])
                self.assertEqual([check["key"] for check in report["notices"]], ["wal_ratio"])
                self.assertTrue(report["notices"][0]["over_line"])
                self.assertFalse(report["notices"][0]["violated"])

                text = run_cli("--data-root", str(root))
                self.assertEqual(text.returncode, 0, text.stdout)
                self.assertIn("! WAL／主库比值", text.stdout)
                self.assertIn("不参与退出码", text.stdout)
                # 关键区分：同一条检查绝不能同时以"越线"的形态出现。
                self.assertNotIn("✗ WAL／主库比值", text.stdout)
            finally:
                writer.close()


class CleanStateTests(unittest.TestCase):
    def test_clean_database_exits_zero_and_says_so(self) -> None:
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            clean_database(root / "companion-v2.sqlite3")

            result = run_cli("--data-root", str(root))

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("全部在观察线以内", result.stdout)

    def test_json_report_of_a_clean_database_has_no_violations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            clean_database(root / "companion-v2.sqlite3")

            result = run_cli("--data-root", str(root), "--json")

            self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "OK")
            self.assertEqual(report["violations"], [])
            # 临时目录不叫 runtime，所以没有 profile 名可报：工具不编一个出来。
            self.assertIsNone(report["profile"])
            self.assertEqual(report["runtime_root"], str(root))
            self.assertEqual(report["database_bytes"],
                             (root / "companion-v2.sqlite3").stat().st_size)

    def test_missing_database_is_uninitialized_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            result = run_cli("--data-root", temporary)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("未初始化", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_nonexistent_root_is_a_sentence_not_a_traceback(self) -> None:
        missing = pathlib.Path(tempfile.gettempdir()) / "companion-v2-audit-does-not-exist"
        self.assertFalse(missing.exists())

        result = run_cli("--data-root", str(missing))

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("未初始化", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


class ReadOnlyTests(unittest.TestCase):
    def test_audit_leaves_the_database_bytes_and_mtime_untouched(self) -> None:
        """只读性：内容哈希、mtime 与目录文件集合都必须一模一样。"""
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            database = root / "companion-v2.sqlite3"
            clean_database(database)
            before_hash = content_hash(database)
            before_mtime = database.stat().st_mtime_ns
            before_files = directory_listing(root)

            result = run_cli("--data-root", str(root))

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(content_hash(database), before_hash)
            self.assertEqual(database.stat().st_mtime_ns, before_mtime)
            # 目录里不许因此多出 -wal / -shm / -journal（那会是"审计顺手写了库"）。
            self.assertEqual(directory_listing(root), before_files)

    def test_audit_leaves_a_wal_backlog_untouched(self) -> None:
        """被审计的实例正在跑（WAL 有积压）时：主库与 -wal 一个字节都不许动。

        `-shm` 单独对待，理由见下面那条对照用例：它是 SQLite 的 wal-index 共享
        内存，任何只读打开都会更新读标记（字节变、大小不变），所以这里只断言它
        仍然存在且大小不变。退出码按提示项口径断言为 0（比值只提示、不判红）。
        """
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            writer = wal_backlog_database(root)
            try:
                database = root / "companion-v2.sqlite3"
                wal = pathlib.Path(str(database) + "-wal")
                shm = pathlib.Path(str(database) + "-shm")
                # 前置条件：确实是"WAL 常驻且已越过提示线"的形态。
                self.assertTrue(wal.is_file(), "没有 -wal 侧车文件，测不到这个形态")
                self.assertGreater(wal.stat().st_size, database.stat().st_size * 0.25)
                before = fingerprint(database, wal)
                shm_size = shm.stat().st_size

                result = run_cli("--data-root", str(root))

                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("! WAL／主库比值", result.stdout)
                self.assertEqual(fingerprint(database, wal), before)
                self.assertTrue(shm.is_file())
                self.assertEqual(shm.stat().st_size, shm_size)
            finally:
                writer.close()

    def test_a_bare_read_only_connection_is_no_less_invasive(self) -> None:
        """对照句：审计的副作用不超过"任何一次只读打开"。

        这条是为了让上一条的断言可证伪：只读连接确实会动 `-shm`（SQLite 的
        wal-index 读标记），但**不会**动主库与 `-wal`。所以"只读"能立住的精确
        说法是"主库与 -wal 不变"，而不是"三个文件一个字节都不变"。
        """
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            root = pathlib.Path(temporary)
            writer = wal_backlog_database(root)
            try:
                database = root / "companion-v2.sqlite3"
                wal = pathlib.Path(str(database) + "-wal")
                before = fingerprint(database, wal)

                connection = sqlite3.connect("file:%s?mode=ro" % database.as_posix(), uri=True)
                try:
                    connection.execute("PRAGMA query_only=ON")
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM bulk").fetchone()[0],
                                     5999)
                finally:
                    connection.close()

                self.assertEqual(fingerprint(database, wal), before)
            finally:
                writer.close()


class DiscoveryTests(unittest.TestCase):
    def test_plugin_data_root_picks_the_most_recently_written_profile(self) -> None:
        """给它插件数据目录时，选主库最近被写的那个 profile，并列出其余。"""
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            plugin_data = pathlib.Path(temporary) / "plugin_data" / "astrbot_plugin_private_companion"
            older = plugin_data / "profiles" / "older-profile" / "runtime"
            newer = plugin_data / "profiles" / "newer-profile" / "runtime"
            for runtime in (older, newer):
                runtime.mkdir(parents=True)
                clean_database(runtime / "companion-v2.sqlite3")
            os.utime(older / "companion-v2.sqlite3", (1_700_000_000, 1_700_000_000))
            os.utime(newer / "companion-v2.sqlite3", (1_800_000_000, 1_800_000_000))

            result = run_cli("--data-root", str(plugin_data), "--json")

            self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["profile"], "newer-profile")
            self.assertEqual(report["unused_runtime_roots"], [str(older)])

    def test_runtime_root_can_be_passed_directly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="companion-v2-audit-") as temporary:
            runtime = pathlib.Path(temporary) / "runtime"
            runtime.mkdir()
            clean_database(runtime / "companion-v2.sqlite3")

            result = run_cli("--data-root", str(runtime), "--json")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(result.stdout)["runtime_root"], str(runtime))


if __name__ == "__main__":
    unittest.main()
