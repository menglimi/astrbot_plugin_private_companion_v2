"""Verify independent V2 installation without V1 or production I/O.

Run with AstrBot Python: -X utf8 -m tools.native_acceptance
    --host-source <AstrBot/backend/app> --output <outside-plugins-directory>.
This does not build release ZIPs, register a live plugin or reload AstrBot.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from tools.native_acceptance_source import CORE_ID, outside_scan, snapshot, snapshot_image


def run(*, source, host_source, output, scratch_parent=None, image_source=None):
    source, host_source = Path(source).resolve(), Path(host_source).resolve()
    output = outside_scan(output, source)
    if not (host_source / "astrbot" / "__init__.py").is_file():
        raise ValueError("an installed AstrBot SDK source is required")
    if scratch_parent is not None:
        scratch_parent = outside_scan(scratch_parent, source)
        scratch_parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "native-acceptance.json"
    report_path.write_text('{"passed": false, "state": "incomplete"}\n', encoding="utf-8", newline="\n")
    report = {"schema": "companion.native-acceptance.v1", "passed": False,
              "provider_execution": "not_run", "native_providers": [], "core": None}
    inventory, root = {}, None
    with (output / "native-acceptance-process.log").open("w", encoding="utf-8", newline="\n") as log:
        try:
            with TemporaryDirectory(prefix="companion-native-acceptance-", dir=scratch_parent) as temporary:
                root = outside_scan(temporary, source)
                plugin = root / "plugins" / CORE_ID
                inventory[CORE_ID] = snapshot(source, plugin)
                if image_source is not None:
                    inventory["astrbot_plugin_image_companion"] = snapshot_image(
                        image_source, root / "plugins" / "astrbot_plugin_image_companion")
                environment = os.environ.copy()
                environment.pop("PYTHONPATH", None)
                environment["PYTHONIOENCODING"] = "utf-8"
                environment["ASTRBOT_ROOT"] = str(root / "sdk")
                command = [sys.executable, "-I", "-X", "utf8", str(plugin / "tools" / "native_acceptance_worker.py"),
                           "--root", str(root), "--plugin-root", str(plugin), "--host-source", str(host_source),
                           "--forbid-root", str(source.parent.parent), "--report", str(root / "result.json")]
                if image_source is not None:
                    command.append("--image")
                child = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=90)
                if (root / "result.json").is_file():
                    report = json.loads((root / "result.json").read_text(encoding="utf-8"))
                else:
                    report["failure"] = {"type": "missing_worker_report"}
                report["worker_exit"] = child.returncode
                report["passed"] = report.get("passed", False) and child.returncode == 0
        except subprocess.TimeoutExpired:
            report.update(passed=False, failure={"type": "timeout"})
        except Exception as error:
            report.update(passed=False, failure={"type": type(error).__name__, "message": str(error)[:2000]})
    report["source_inventory"] = {name: {"file_count": len(value["files"]),
        "inventory_sha256": hashlib.sha256(json.dumps(value["files"], sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest(),
        "legacy_static_findings": value["legacy_static_findings"]} for name, value in inventory.items()}
    (output / "native-source-files.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    report["temporary_installation_removed"] = root is not None and not root.exists()
    report["passed"] = report["passed"] and report["temporary_installation_removed"]
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch-parent", type=Path)
    parser.add_argument("--image-source", type=Path, help="opt in to actual Image native provider execution using its synthetic backend")
    args = parser.parse_args()
    result = run(source=args.source, host_source=args.host_source, output=args.output,
                 scratch_parent=args.scratch_parent, image_source=args.image_source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
