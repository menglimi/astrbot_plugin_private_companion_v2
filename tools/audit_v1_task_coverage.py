"""Which V1 configuration keys the gap task list never mentions.

The task table cites V1 keys with `*` wildcards (for example
`group_member_safety_*`). This script expands those patterns against the
per-key progress CSV and reports the remaining keys, so an audit can tell a
real coverage gap apart from a group that was already written off.

Usage: python tools/audit_v1_task_coverage.py
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "docs" / "V2_GAP_CLOSING_TASKS_20260927.md"
PROGRESS = ROOT / "docs" / "V1_V2_CONFIG_PROGRESS_20260926.csv"
# Groups the task list explicitly wrote off, with the reason it gives.
WRITTEN_OFF = (
    "E6",  # 遗留与兼容
)


def cited_patterns():
    text = TASKS.read_text(encoding="utf-8")
    patterns = set()
    for match in re.finditer(r"`([A-Za-z][A-Za-z0-9_]*\*?)`", text):
        token = match.group(1)
        if token.endswith("*") and len(token) > 1:
            patterns.add(token[:-1])
    return patterns


def rows():
    with PROGRESS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("配置键") or row.get("閰嶇疆閿?") or "").strip()
            if key:
                yield row, key


def main():
    patterns = cited_patterns()
    per_key = []
    for row, key in rows():
        per_key.append((key, row))
    cited = {key for key, _ in per_key if any(key.startswith(pattern) for pattern in patterns)}
    missing = [(key, row) for key, row in per_key if key not in cited]
    print(f"V1_KEYS\t{len(per_key)}")
    print(f"PATTERNS\t{len(patterns)}")
    print(f"CITED\t{len(cited)}")
    print(f"NOT_CITED\t{len(missing)}")
    by_subcategory = defaultdict(int)
    for key, row in missing:
        subcategory = (row.get("子类") or "").strip()
        by_subcategory[subcategory or "?"] += 1
    for subcategory, count in sorted(by_subcategory.items(), key=lambda item: -item[1]):
        print(f"UNCOVERED_SUBCATEGORY\t{subcategory}\t{count}")
    print("--- first 120 uncovered keys by subcategory ---")
    grouped = defaultdict(list)
    for key, row in missing:
        grouped[(row.get("子类") or "?").strip()].append(key)
    for subcategory in sorted(grouped):
        print(f"[{subcategory}] " + ", ".join(grouped[subcategory][:24]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
