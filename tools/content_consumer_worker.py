"""Fresh worker with audited boundaries before importing the SDK or copied plugins."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest


MODULES = (
    "tests.test_native_content_flow",
    "tests.test_external_source_dependencies",
    "tests.test_source_owner_governance",
    "tests.test_model_source_fence",
)


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.checks.append({"test": test.id(), "passed": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--forbid-root", type=Path, action="append", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root, plugin, content, host = (p.resolve() for p in (args.root, args.plugin_root, args.content_root, args.host_source))
    if (not plugin.is_relative_to(root) or not content.is_relative_to(root)
            or not args.report.resolve().is_relative_to(root)
            or any(root.is_relative_to(p.resolve()) for p in args.forbid_root)):
        raise ValueError("invalid disposable Content installation boundary")
    os.chdir(root)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(plugin), str(plugin.parent), str(host)]
    os.environ["ASTRBOT_ROOT"] = str(root / "sdk")
    os.environ["CONTENT_V2_PROVIDER_ROOT"] = str(content)
    temporary = root / "temporary"
    temporary.mkdir()
    tempfile.tempdir = str(temporary)
    os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
    from tools.native_acceptance_guard import NativeAcceptanceGuard
    guard = NativeAcceptanceGuard(root=root, read_roots=(host, sys.prefix, sys.base_prefix),
                                  forbidden_roots=args.forbid_root)
    report = {"schema": "companion.content-consumer-acceptance.v1", "passed": False,
        "scope": "content_native_provider_and_v2_consumer_with_synthetic_star_model_sender",
        "modules": MODULES, "tests": 0, "real_model_requests": 0, "real_platform_messages": 0,
        "content_legacy_entry_loaded": False, "v1_loaded": False}
    try:
        with guard:
            if os.name == "nt":
                with guard.runtime_bootstrap({"kernel32", "shell32"}):
                    import ctypes
                    import win32_setctime
                    import loguru
                    import click
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            if Path(get_astrbot_data_path()).resolve() != root / "sdk" / "data":
                raise AssertionError("SDK data root escaped the temporary installation")
            logging.disable(logging.CRITICAL)
            suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
            result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
            report.update(tests=result.testsRun, checks=result.checks,
                failures=[{"test": t.id(), "traceback": trace} for t, trace in result.failures],
                errors=[{"test": t.id(), "traceback": trace} for t, trace in result.errors],
                skipped=[{"test": t.id(), "reason": reason} for t, reason in result.skipped])
            if "astrbot_plugin_content_companion" in sys.modules:
                raise AssertionError("the Content legacy plugin entry was loaded")
            guard.assert_clean()
            report["passed"] = result.wasSuccessful() and not result.skipped and result.testsRun > 0
    except Exception as error:
        traceback.print_exc()
        report["failure"] = {"type": type(error).__name__, "message": str(error)[:1000]}
    finally:
        report["violations"] = guard.violations
        report["trusted_bootstrap_native_loads"] = guard.trusted_native_loads
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
