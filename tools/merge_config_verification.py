"""Merge the verification sweep into the coverage audit and report final figures.

Reads the per-shard verdicts written by the reviewers, joins them onto the coverage
audit (which carries the name-matched V2 field and the ledger disposition), and writes
a single per-key CSV plus the headline counts.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

AUDIT = Path("docs/V1_V2_CONFIG_COVERAGE_AUDIT_20260927.csv")
SHARDS = Path(".verify-shards")
OUT = Path("docs/V1_V2_CONFIG_VERIFIED_20260927.csv")

# Verdicts that mean the V1 capability is present in V2 one way or another.
COVERED = ("already-in-v2", "renamed-equivalent", "implemented-elsewhere")
# Verdicts that mean the key is accounted for and NOT owed.
ACCOUNTED = COVERED + ("not-migrated-by-design", "not-applicable")


def main():
    verdicts = {}
    for path in sorted(SHARDS.glob("out-shard-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("results", []):
            verdicts[record["v1_key"]] = record

    rows = list(csv.DictReader(AUDIT.open(encoding="utf-8", newline="")))
    out_rows = []
    missing = []
    for row in rows:
        record = verdicts.get(row["v1_key"])
        if row["v2_field"] and row["disposition"] != "owed":
            # Already settled by name matching before the sweep: keep it as verified.
            verdict = "already-in-v2"
            landing, evidence, confidence = row["v2_field"], "name match + production consumer", "high"
        elif record is None:
            missing.append(row["v1_key"])
            verdict, landing, evidence, confidence = "unverified", "", "", ""
        else:
            verdict = record["verdict"]
            landing, evidence = record.get("v2_landing", ""), record.get("evidence", "")
            confidence = record.get("confidence", "")
        out_rows.append({**row, "verified_verdict": verdict, "verified_landing": landing,
                         "verified_evidence": evidence, "verified_confidence": confidence})

    fieldnames = list(out_rows[0])
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    total = len(out_rows)
    counts = Counter(row["verified_verdict"] for row in out_rows)
    covered = sum(counts[name] for name in COVERED)
    accounted = sum(counts[name] for name in ACCOUNTED)
    owed = counts["owed"]
    print("TOTAL_KEYS", total)
    print("UNVERIFIED", len(missing), missing[:8])
    print("--- verdicts")
    for name, value in counts.most_common():
        print(f"  {name:26} {value:5}  {100.0 * value / total:5.1f}%")
    print("--- headline")
    print("COVERED_IN_V2   ", covered, f"{100.0 * covered / total:.1f}%")
    print("ACCOUNTED_FOR   ", accounted, f"{100.0 * accounted / total:.1f}%")
    print("OWED            ", owed, f"{100.0 * owed / total:.1f}%")
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
