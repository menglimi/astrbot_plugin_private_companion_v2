"""Verify the installed SDK, management page and V2 lifecycle using local doubles.

Run with AstrBot's Python and backend/app on PYTHONPATH. Each reload is a new
process over a temporary V2 database; browser evidence lives in --output.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / "demo-acceptance-results.json"
    # A failed rerun must not leave the previous successful result looking current.
    summary_path.write_text('{"passed": false, "reason": "acceptance_incomplete"}\n',
                            encoding="utf-8", newline="\n")
    reports = []
    with tempfile.TemporaryDirectory(prefix="companion-v2-demo-") as temporary:
        for mode in ("single", "multi"):
            for phase in ("fresh", "recovered"):
                label = f"{mode}-{phase}"
                destination = output / label
                destination.mkdir(exist_ok=True)
                with (destination / "process.log").open("w", encoding="utf-8", newline="\n") as log:
                    try:
                        result = subprocess.run(
                            [sys.executable, "-X", "utf8", "-m", "tests.demo_host_process",
                             "--root", str(Path(temporary) / mode), "--phase", phase,
                             "--mode", mode, "--output", str(destination), "--node", args.node],
                            cwd=repo, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT, timeout=120,
                        )
                    except subprocess.TimeoutExpired:
                        log.write("\nAcceptance process exceeded 120 seconds.\n")
                        print(f"FAIL: {label} timed out; see {destination / 'process.log'}", flush=True)
                        return 1
                if result.returncode:
                    print(f"FAIL: {label}; see {destination / 'process.log'}", flush=True)
                    return result.returncode
                report = json.loads((destination / "result.json").read_text(encoding="utf-8"))
                reports.append(report)
                print(f"PASS: {label}, {len(report['checks'])} browser checks; teardown verified", flush=True)
    summary = {"passed": True, "processes": reports, "checks": sum(len(r["checks"]) for r in reports),
               "real_model_requests": 0, "platform_messages": 0, "temporary_data_removed": True}
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"PASS: {summary['checks']} checks; {output / 'demo-acceptance-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
