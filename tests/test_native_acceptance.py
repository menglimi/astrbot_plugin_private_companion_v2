"""Adversarial dependency probes for native acceptance; uses only synthetic data."""

import builtins
import importlib
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace as NS
import unittest

from tools.native_acceptance_guard import NativeAcceptanceGuard, NativeAcceptanceViolation, scan_dependencies
from tools.native_acceptance_source import outside_scan, snapshot, snapshot_image


class NativeAcceptanceBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="native-acceptance-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.read_roots = (sys.prefix, sys.base_prefix, Path(__file__).resolve().parents[1])

    def guard(self):
        return NativeAcceptanceGuard(root=self.root, read_roots=self.read_roots)

    def test_direct_dynamic_nested_and_from_import_are_denied(self):
        with self.guard() as guard:
            for action in (
                lambda: builtins.__import__("astrbot_plugin_private_companion.main"),
                lambda: importlib.import_module("astrbot_plugin_" + "private_companion"),
                lambda: importlib.util.find_spec("data.plugins.astrbot_plugin_private_companion.main"),
                lambda: builtins.__import__("data.plugins", fromlist=("astrbot_plugin_private_companion",)),
            ):
                with self.subTest(action=action):
                    with self.assertRaises(NativeAcceptanceViolation):
                        action()
            self.assertEqual(len(guard.violations), 4)

    def test_cached_legacy_and_shadow_registration_cannot_pass(self):
        sys.modules["astrbot_plugin_private_companion"] = NS()
        try:
            with self.assertRaises(NativeAcceptanceViolation):
                with self.guard():
                    pass
        finally:
            sys.modules.pop("astrbot_plugin_private_companion", None)
        with self.guard() as guard:
            with self.assertRaises(NativeAcceptanceViolation):
                guard.catalog([NS(name="innocent", root_dir_name="astrbot_plugin_private_companion")])

    def test_cached_alias_from_legacy_origin_is_rejected(self):
        alias = ModuleType("native_acceptance_alias")
        alias.__file__ = str(self.root / "astrbot_plugin_private_companion" / "core.py")
        sys.modules[alias.__name__] = alias
        try:
            with self.assertRaisesRegex(NativeAcceptanceViolation, "forbidden_module_origin"):
                with self.guard():
                    pass
        finally:
            sys.modules.pop(alias.__name__, None)

    def test_name_alias_discovery_is_denied_and_v2_name_is_distinct(self):
        current = NS(name="astrbot_plugin_private_companion", root_dir_name="astrbot_plugin_private_companion")
        with self.guard() as guard:
            self.assertIs(guard.discover(current.name, [current]), current)
            for name in ("astrbot_plugin_private_companion", "PrivateCompanion"):
                with self.assertRaises(NativeAcceptanceViolation):
                    guard.discover(name)

    def test_legacy_file_open_and_sqlite_uri_are_denied_before_read(self):
        legacy = self.root / "astrbot_plugin_private_companion"
        legacy.mkdir()
        path = legacy / "synthetic.txt"
        path.write_text("synthetic secret", encoding="utf-8")
        with self.guard() as guard:
            for action in (lambda: path.read_text(encoding="utf-8"),
                           lambda: os.open(path, os.O_RDONLY),
                           lambda: sqlite3.connect((legacy / "owner.db").as_uri() + "?mode=rwc", uri=True),
                           lambda: list(legacy.iterdir())):
                with self.assertRaises(NativeAcceptanceViolation):
                    action()
            self.assertEqual({v["code"] for v in guard.violations}, {"legacy_data"})
        self.assertFalse((legacy / "owner.db").exists())

    def test_fresh_v2_data_allowed_legacy_filename_denied(self):
        with self.guard() as guard:
            (self.root / "v2.json").write_text("{}", encoding="utf-8")
            db = sqlite3.connect(self.root / "runtime.sqlite3")
            db.close()
            with self.assertRaises(NativeAcceptanceViolation):
                (self.root / "companions.json").read_bytes()

    def test_swallowed_dependency_exception_still_fails_final_audit(self):
        with self.guard() as guard:
            try:
                importlib.import_module("astrbot_plugin_private_companion")
            except Exception:
                pass
            with self.assertRaises(NativeAcceptanceViolation):
                guard.assert_clean()

    def test_network_and_child_process_fallbacks_are_denied(self):
        with self.guard() as guard:
            with socket.socket() as sock:
                with self.assertRaises(NativeAcceptanceViolation):
                    sock.connect(("127.0.0.1", 6185))
            with self.assertRaises(NativeAcceptanceViolation):
                subprocess.run([sys.executable, "-c", "pass"])
            self.assertEqual({v["code"] for v in guard.violations}, {"network", "child_process"})

    def test_runtime_bootstrap_does_not_allow_provider_native_loads_or_legacy_access(self):
        with self.guard() as guard:
            with guard.runtime_bootstrap({"kernel32"}):
                sys.audit("ctypes.dlopen", "kernel32")
                with self.assertRaises(NativeAcceptanceViolation):
                    sys.audit("ctypes.dlopen", "provider.dll")
                with self.assertRaises(NativeAcceptanceViolation):
                    importlib.import_module("astrbot_plugin_private_companion")
            with self.assertRaises(NativeAcceptanceViolation):
                sys.audit("ctypes.dlopen", "kernel32")
            self.assertEqual(guard.trusted_native_loads, ["kernel32"])
            self.assertEqual([v["code"] for v in guard.violations],
                             ["native_loader", "legacy_import", "native_loader"])

    def test_traversal_cannot_leave_data_boundary(self):
        with self.guard() as guard:
            with self.assertRaises(NativeAcceptanceViolation):
                (self.root / ".." / "native-external-sentinel.txt").write_text("bad", encoding="utf-8")
            self.assertEqual(guard.violations[-1]["code"], "outside_write_root")

    def test_forbidden_installed_data_wins_over_allowed_parent_read_root(self):
        live = self.root / "synthetic-live-data"
        live.mkdir()
        private = live / "account.json"
        private.write_text("synthetic-only", encoding="utf-8")
        with NativeAcceptanceGuard(root=self.root, forbidden_roots=(live,)) as guard:
            with self.assertRaisesRegex(NativeAcceptanceViolation, "installed_data_or_plugin_access"):
                private.read_bytes()
            self.assertEqual(guard.violations, [{"code": "installed_data_or_plugin_access"}])

    def test_source_scan_detects_executable_legacy_dependency_not_metadata(self):
        self.assertEqual(scan_dependencies('META={"plugin_id":"astrbot_plugin_private_companion"}\n'), [])
        source = """from data.plugins import astrbot_plugin_private_companion
importlib.import_module('astrbot_plugin_' + 'private_companion')
context.get_registered_star('PrivateCompanion')
open('data/astrbot_plugin_private_companion/user.json')
"""
        self.assertEqual([v["code"] for v in scan_dependencies(source)],
                         ["legacy_import", "legacy_import", "legacy_discovery", "legacy_data"])

    def test_snapshot_never_copies_data_or_live_legacy_siblings(self):
        scanner = self.root / "scanner"
        source = scanner / "astrbot_plugin_private_companion"
        source.mkdir(parents=True)
        for name, text in {"main.py":"pass\n", "metadata.yaml":"name: fixture\n", "_conf_schema.json":"{}\n", "requirements.txt":"\n"}.items():
            (source / name).write_text(text, encoding="utf-8")
        (source / "companion_v2" / "data").mkdir(parents=True)
        (source / "companion_v2" / "data" / "user.py").write_text("should never be copied", encoding="utf-8")
        (scanner / "astrbot_plugin_private_companion").mkdir()
        target = self.root / "scratch" / "astrbot_plugin_private_companion"
        inventory = snapshot(source, target)
        self.assertEqual(len(inventory["files"]), 4)
        self.assertFalse((target / "companion_v2" / "data").exists())
        self.assertFalse((target.parent / "astrbot_plugin_private_companion").exists())
        with self.assertRaises(ValueError):
            outside_scan(scanner / "test-clone", source)

    def test_snapshot_rejects_linked_source_before_reading_target(self):
        source = self.root / "plugins" / "v2"
        source.mkdir(parents=True)
        secret = self.root / "synthetic-legacy.py"
        secret.write_text("raise AssertionError('must not read')", encoding="utf-8")
        try:
            (source / "main.py").symlink_to(secret)
        except OSError:
            self.skipTest("symlink creation unavailable")
        for name in ("metadata.yaml", "_conf_schema.json", "requirements.txt"):
            (source / name).write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            snapshot(source, self.root / "scratch" / "v2")

    def test_image_snapshot_has_no_legacy_entry_or_data_and_scans_transports(self):
        source = self.root / "scanner" / "image"
        paths = ("__init__.py", "image_companion/__init__.py", "tests/native_v2_support.py",
                 "image_native_client.py", "comfyui_service.py", "comfyui_workflows.py", "comfyui_prompts.py",
                 "reference_receipt.py", "image_operations.py", "image_preparation_task.py",
                 "image_companion/native_v2/adapter.py", "main.py", "data/old-user.py")
        for relative in paths:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pass\n", encoding="utf-8")
        destination = self.root / "scratch" / "image"
        inventory = snapshot_image(source, destination)
        self.assertNotIn("main.py", inventory["files"])
        self.assertFalse((destination / "data").exists())
        (source / "image_native_client.py").write_text("import astrbot_plugin_remember_you\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "legacy executable dependency"):
            snapshot_image(source, self.root / "scratch" / "adversarial")


if __name__ == "__main__":
    unittest.main()
