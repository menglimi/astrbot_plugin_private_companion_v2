"""Copy V2 and Content native sources, then verify the consumer in a fresh -I worker.

Requires AstrBot Python and its installed SDK. No live plugin load or release build.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from tools.native_acceptance_guard import scan_dependencies
from tools.native_acceptance_source import CORE_ID, EXCLUDED, outside_scan, snapshot


def snapshot_content(source, destination):
    source, destination = Path(source).resolve(), outside_scan(destination, source)
    native = source / "companion" / "content_v2"
    if not (native / "assembly.py").is_file():
        raise ValueError("the native Content provider source is required")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Content acceptance destination must be new or empty")
    hashes, findings = {}, []
    for base, dirs, files in os.walk(native, followlinks=False):
        for child in dirs:
            path = Path(base) / child
            if path.is_symlink() or not path.resolve().is_relative_to(native):
                raise ValueError("Content source link escapes its selected native package")
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(f for f in files if f.endswith(".py")):
            path = Path(base) / name
            if path.is_symlink() or not path.resolve().is_relative_to(native):
                raise ValueError("Content source link escapes its selected native package")
            relative = path.relative_to(native)
            payload = path.read_bytes()
            findings.extend(scan_dependencies(payload.decode("utf-8-sig"), relative.as_posix()))
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            hashes[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
    if findings:
        raise ValueError("Content native source contains executable legacy dependencies")
    return {"files": hashes, "legacy_static_findings": findings}


def run(*, source, content_source, host_source, output, scratch_parent=None):
    source, content_source, host_source = (Path(p).resolve() for p in (source, content_source, host_source))
    output = outside_scan(outside_scan(output, source), content_source)
    if not (host_source / "astrbot" / "__init__.py").is_file():
        raise ValueError("an installed AstrBot SDK source is required")
    if scratch_parent is not None:
        scratch_parent = outside_scan(outside_scan(scratch_parent, source), content_source)
        scratch_parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "content-consumer-acceptance.json"
    report = {"schema": "companion.content-consumer-acceptance.v1", "passed": False, "state": "incomplete"}
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8", newline="\n")
    inventory, root = {}, None
    with (output / "content-consumer-process.log").open("w", encoding="utf-8", newline="\n") as log:
        try:
            with TemporaryDirectory(prefix="content-native-acceptance-", dir=scratch_parent) as temporary:
                root = outside_scan(outside_scan(temporary, source), content_source)
                plugin, native = root / "plugins" / CORE_ID, root / "providers" / "content_v2"
                inventory[CORE_ID] = snapshot(source, plugin)
                inventory["content.native"] = snapshot_content(content_source, native)
                environment = os.environ.copy()
                environment.pop("PYTHONPATH", None)
                environment["PYTHONIOENCODING"] = "utf-8"
                environment["ASTRBOT_ROOT"] = str(root / "sdk")
                command = [sys.executable, "-I", "-X", "utf8", str(plugin / "tools" / "content_consumer_worker.py"),
                    "--root", str(root), "--plugin-root", str(plugin), "--content-root", str(native),
                    "--host-source", str(host_source), "--forbid-root", str(source.parent.parent),
                    "--forbid-root", str(content_source.parent.parent), "--report", str(root / "result.json")]
                child = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=180)
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
    (output / "content-source-files.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8", newline="\n")
    report["temporary_installation_removed"] = root is not None and not root.exists()
    report["passed"] = report["passed"] and report["temporary_installation_removed"]
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--content-source", type=Path, required=True)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch-parent", type=Path)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
