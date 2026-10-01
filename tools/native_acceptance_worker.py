"""Fresh -I worker. Install all boundaries before importing AstrBot or V2."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--forbid-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--image", action="store_true")
    args = parser.parse_args()
    root, plugin, host = args.root.resolve(), args.plugin_root.resolve(), args.host_source.resolve()
    if not plugin.is_relative_to(root) or root.is_relative_to(args.forbid_root.resolve()):
        raise ValueError("invalid acceptance installation boundary")
    os.chdir(root)
    sys.dont_write_bytecode = True
    os.environ["ASTRBOT_ROOT"] = str(root / "sdk")
    sys.path[:0] = [str(plugin), str(plugin.parent), str(host)]
    from tools.native_acceptance_guard import NativeAcceptanceGuard
    guard = NativeAcceptanceGuard(root=root, read_roots=(host, sys.prefix, sys.base_prefix),
                                  forbidden_roots=(args.forbid_root,))
    report = {"schema": "companion.native-acceptance.v1", "passed": False,
              "native_providers": [], "provider_execution": "not_run", "core": None,
              "real_model_requests": 0, "real_platform_messages": 0}
    try:
        with guard:
            if os.name == "nt":
                # loguru/click use the Windows console APIs. Preload trusted
                # dependency before any SDK or copied plugin import; all other
                # dependency guards remain active throughout bootstrap.
                with guard.runtime_bootstrap({"kernel32", "shell32"}):
                    import ctypes
                    import win32_setctime
                    import loguru
                    import click
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            if Path(get_astrbot_data_path()).resolve() != root / "sdk" / "data":
                raise AssertionError("SDK root escaped temporary installation")
            logging.disable(logging.CRITICAL)
            if args.image:
                from tests.native_acceptance_image import run_image
                provider_report = {"provider_id": "image.native", "passed": False, "checks": [],
                    "synthetic_backend_submissions": 0, "synthetic_model_calls": 0, "synthetic_sender_attempts": 0,
                    "scope": "native_module_and_v2_registry_with_synthetic_star", "legacy_entry_loaded": False}
                report["native_providers"].append(provider_report)
                report["provider_execution"] = "running"
                asyncio.run(run_image(root, guard, provider_report))
                report["provider_execution"] = "passed"
            from tests.native_acceptance_cases import run_core
            report["core"] = asyncio.run(run_core(plugin, root, guard))
            guard.assert_clean()
        report["passed"] = True
    except Exception as error:
        if report["provider_execution"] == "running":
            report["provider_execution"] = "failed"
        traceback.print_exc()
        report["failure"] = {"type": type(error).__name__, "message": str(error)[:1000]}
    finally:
        report["violations"] = guard.violations
        report["trusted_bootstrap_native_loads"] = guard.trusted_native_loads
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
