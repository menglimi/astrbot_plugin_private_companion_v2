from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.foundation.isolation import scan_source_tree


ROOT = Path(__file__).resolve().parents[1]


class IsolationScannerTests(unittest.TestCase):
    def test_g0_core_tree_stays_isolated_behind_the_explicit_host_entrypoint(self) -> None:
        report = scan_source_tree(ROOT / "companion_v2", package_name="companion_v2")

        self.assertTrue(report.is_clean, report.render())
        self.assertTrue((ROOT / "metadata.yaml").is_file())
        self.assertTrue((ROOT / "main.py").is_file())
        self.assertTrue((ROOT / "astrbot_host" / "controller.py").is_file())
        self.assertEqual({path.name for path in ROOT.glob("*.py")}, {"main.py"})
        self.assertFalse((ROOT / "__init__.py").exists())
        self.assertNotIn("import astrbot", (ROOT / "companion_v2" / "__init__.py").read_text(encoding="utf-8"))

    def test_rejects_host_v1_network_platform_and_legacy_data_access(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-isolation-") as temporary:
            source_root = Path(temporary)
            (source_root / "bad.py").write_text(
                "import astrbot\n"
                "from astrbot_host.controller import AstrBotStagingController\n"
                "import requests\n"
                "import subprocess\n"
                "from astrbot_plugin_private_companion.main import CompanionPlugin\n"
                "open('companions.json', 'r', encoding='utf-8')\n"
                "subprocess.run(['hostname'])\n",
                encoding="utf-8",
            )

            report = scan_source_tree(source_root, package_name="fixture")
            codes = {violation.code for violation in report.violations}

        self.assertIn("forbidden_import", codes)
        self.assertTrue(any(item.detail == "astrbot_host.controller" for item in report.violations))
        self.assertIn("forbidden_v1_runtime_import", codes)
        self.assertIn("forbidden_platform_or_network_call", codes)
        self.assertIn("legacy_data_access", codes)
        with self.assertRaises(RuntimeError):
            report.assert_clean()

    def test_rebuildable_memory_search_sqlite_access_is_scoped_to_its_module(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-isolation-") as temporary:
            source_root = Path(temporary)
            memory_root = source_root / "memory"
            memory_root.mkdir()
            (memory_root / "search.py").write_text(
                "import sqlite3\n"
                "sqlite3.connect('memory-search.sqlite3')\n",
                encoding="utf-8",
            )
            (memory_root / "other.py").write_text(
                "import sqlite3\n"
                "sqlite3.connect('unapproved.sqlite3')\n",
                encoding="utf-8",
            )

            report = scan_source_tree(source_root, package_name="companion_v2")

        self.assertEqual(
            [(item.relative_path, item.detail) for item in report.violations],
            [("memory/other.py", "sqlite3.connect")],
        )

    def test_reference_decoder_policy_allows_bytes_but_not_paths(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-isolation-") as temporary:
            source_root = Path(temporary) / "references"
            source_root.mkdir()
            (source_root / "management.py").write_text(
                "from io import BytesIO\n"
                "from PIL import Image\n"
                "Image.open(BytesIO(payload))\n"
                "Image.open(upload_path)\n",
                encoding="utf-8",
            )

            report = scan_source_tree(source_root, package_name="companion_v2.references")

        self.assertEqual(
            [(item.line, item.detail) for item in report.violations],
            [(4, "Image.open")],
        )

    def test_backup_inventory_io_is_scoped_to_the_storage_management_owner(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-isolation-") as temporary:
            source_root = Path(temporary) / "storage"
            source_root.mkdir()
            operations = ("import os\n"
                          "root.rglob('backups')\n"
                          "directory.glob('companion-v2-*.json')\n"
                          "sidecar.read_text(encoding='utf-8')\n"
                          "destination.mkdir()\n"
                          "snapshot.open('rb')\n"
                          "temporary.unlink()\n"
                          "os.replace(temporary, destination)\n")
            (source_root / "management.py").write_text(operations + "root.write_text('unapproved')\n",
                                                         encoding="utf-8")
            (source_root / "other.py").write_text(operations, encoding="utf-8")

            report = scan_source_tree(source_root, package_name="companion_v2.storage")

        self.assertEqual([(item.line, item.detail) for item in report.violations
                          if item.relative_path == "management.py"], [(9, "root.write_text")])
        self.assertEqual(len([item for item in report.violations if item.relative_path == "other.py"]), 7)

    def test_migration_rule_resource_policy_rejects_other_resources_paths_and_writes(self) -> None:
        with TemporaryDirectory(prefix="companion-v2-isolation-") as temporary:
            source_root = Path(temporary) / "legacy"
            source_root.mkdir()
            (source_root / "configuration_migration.py").write_text(
                "from importlib.resources import files\n"
                "files('companion_v2.legacy').joinpath('configuration_rules.json').read_text(encoding='utf-8')\n"
                "files('companion_v2.legacy').joinpath('other.json').read_text()\n"
                "files('other_package').joinpath('configuration_rules.json').read_text()\n"
                "files('companion_v2.legacy').joinpath(user_path).read_text()\n"
                "files('companion_v2.legacy').joinpath('configuration_rules.json').write_text(payload)\n"
                "user_path.read_text()\n",
                encoding="utf-8",
            )

            report = scan_source_tree(source_root, package_name="companion_v2.legacy")

        self.assertEqual([item.line for item in report.violations], [3, 4, 5, 6, 7])
