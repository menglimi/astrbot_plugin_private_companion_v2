"""数据根在插件改名后的解析规则。

背景：7.0.0 之后这个产品要从 `astrbot_plugin_private_companion_v2` 收编成
`astrbot_plugin_private_companion`。StarTools 按插件名算默认数据目录，改名会让
老用户的数据根指向一个空目录或者 V1 的目录——所以启动前先解析一次：现在的
默认目录里有数据就用它，否则沿用同级的旧 V2 目录。
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.storage_location import OWNER_NAME, V2_SUBDIRECTORY, resolve_data_root


def _root_with_data(base: Path, name: str) -> Path:
    root = base / name
    (root / "profiles" / "main").mkdir(parents=True)
    (root / OWNER_NAME).write_text("{}", encoding="utf-8")
    return root


class ResolveDataRootTests(unittest.TestCase):
    def test_new_name_with_data_wins(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            _root_with_data(base, "astrbot_plugin_private_companion_v2")
            current = _root_with_data(base, "astrbot_plugin_private_companion")
            self.assertEqual(resolve_data_root(current), current.resolve())

    def test_legacy_directory_is_reused_after_rename(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = _root_with_data(base, "astrbot_plugin_private_companion_v2")
            renamed = base / "astrbot_plugin_private_companion"
            self.assertEqual(resolve_data_root(renamed), legacy.resolve())

    def test_fresh_install_keeps_the_current_default(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            renamed = base / "astrbot_plugin_private_companion"
            self.assertEqual(resolve_data_root(renamed), renamed.resolve())

    def test_empty_directory_is_not_data(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = base / "astrbot_plugin_private_companion_v2"
            legacy.mkdir(parents=True)
            renamed = base / "astrbot_plugin_private_companion"
            self.assertEqual(resolve_data_root(renamed), renamed.resolve())

    def test_pointer_only_root_counts_as_data(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = base / "astrbot_plugin_private_companion_v2"
            legacy.mkdir(parents=True)
            (legacy / ".companion-v2-storage-location.json").write_text("{}", encoding="utf-8")
            renamed = base / "astrbot_plugin_private_companion"
            self.assertEqual(resolve_data_root(renamed), legacy.resolve())


class V1TakeoverTests(unittest.TestCase):
    """覆盖式更新：PLUGIN_NAME 变成 V1 的名字，默认根就是 V1 的数据目录。"""

    def test_v1_directory_gets_a_v2_subdirectory(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            v1 = base / "astrbot_plugin_private_companion"
            v1.mkdir(parents=True)
            (v1 / "companions.json").write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_data_root(v1), (v1 / V2_SUBDIRECTORY).resolve())

    def test_mixed_v1_data_and_profiles_directory_stays_read_only(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            v1 = base / "astrbot_plugin_private_companion"
            (v1 / "profiles" / "old-persona").mkdir(parents=True)
            (v1 / "companions.json").write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_data_root(v1), (v1 / V2_SUBDIRECTORY).resolve())

    def test_sqlite_only_v1_root_gets_an_isolated_upgrade_directory(self):
        with TemporaryDirectory() as temporary:
            v1 = Path(temporary) / "astrbot_plugin_private_companion"
            v1.mkdir()
            (v1 / "companions.db").write_bytes(b"legacy database sentinel")
            self.assertEqual(resolve_data_root(v1), (v1 / V2_SUBDIRECTORY).resolve())

    def test_v2_owner_marker_takes_precedence_over_v1_looking_files(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            v1 = base / "astrbot_plugin_private_companion"
            (v1 / "profiles" / "main").mkdir(parents=True)
            (v1 / "companions.json").write_text("{}", encoding="utf-8")
            (v1 / OWNER_NAME).write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_data_root(v1), v1.resolve())

    def test_old_v2_directory_wins_over_v1_takeover(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            legacy = _root_with_data(base, "astrbot_plugin_private_companion_v2")
            v1 = base / "astrbot_plugin_private_companion"
            v1.mkdir(parents=True)
            (v1 / "companions.json").write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_data_root(v1), legacy.resolve())

    def test_empty_v1_like_directory_is_not_treated_as_v1(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            v1 = base / "astrbot_plugin_private_companion"
            v1.mkdir(parents=True)
            self.assertEqual(resolve_data_root(v1), v1.resolve())


if __name__ == "__main__":
    unittest.main()
