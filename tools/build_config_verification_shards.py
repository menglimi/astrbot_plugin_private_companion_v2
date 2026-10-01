"""Build shard inputs for the V1-to-V2 configuration verification sweep.

Reads the coverage audit CSV, selects every key that still lacks a verified verdict,
attaches the V1 declaration (type, default, description) and the V2 field inventory,
and writes JSON shards sized for one reviewer each.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA = _ROOT.parent / "astrbot_plugin_private_companion" / "_conf_schema.json"
AUDIT = Path("docs/V1_V2_CONFIG_COVERAGE_AUDIT_20260927.csv")
OUT = Path(".verify-shards")
SHARD_SIZE = 16
PENDING = ("no-ledger-row", "recorded-other")


def v1_index(node, prefix=""):
    """Every scalar key of V1 mapped to its declaration."""
    for name, spec in node.items():
        path = f"{prefix}{name}"
        if not isinstance(spec, dict):
            continue
        if spec.get("type") == "object" and isinstance(spec.get("items"), dict):
            yield from v1_index(spec["items"], path + ".")
        else:
            yield path, spec


def main():
    schema = json.loads(V1_SCHEMA.read_text(encoding="utf-8-sig"))
    declarations = dict(v1_index(schema))
    rows = list(csv.DictReader(AUDIT.open(encoding="utf-8", newline="")))
    # Verify what is still undecided: no V2 field yet, or a field that exists while the
    # ledger still records the key as owed. Keys already matched and settled are done.
    pending = [row for row in rows
               if not row["v2_field"] or row["disposition"] == "owed"]

    # Shard by V1 group so one reviewer sees a coherent area.
    by_group = defaultdict(list)
    for row in pending:
        group = row["v1_key"].split(".", 1)[0] if "." in row["v1_key"] else "_top_level"
        by_group[group].append(row)

    OUT.mkdir(exist_ok=True)
    for stale in OUT.glob("shard-*.json"):
        stale.unlink()

    manifest = []
    shards = 0
    for group in sorted(by_group):
        items = by_group[group]
        for start in range(0, len(items), SHARD_SIZE):
            chunk = items[start:start + SHARD_SIZE]
            shards += 1
            payload = {
                "shard_id": f"{group}-{start // SHARD_SIZE + 1:02d}",
                "v1_group": group,
                "keys": [{
                    "v1_key": row["v1_key"],
                    "v1_type": row["v1_type"],
                    "v1_default": declarations.get(row["v1_key"], {}).get("default"),
                    "v1_description": declarations.get(row["v1_key"], {}).get("description", ""),
                    "ledger_disposition": row["disposition"],
                } for row in chunk],
            }
            path = OUT / f"shard-{shards:03d}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            manifest.append({"shard": path.name, "group": group, "keys": len(chunk)})
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8", newline="\n")
    print("PENDING_KEYS", len(pending), "SHARDS", shards, "GROUPS", len(by_group))
    print("MANIFEST", OUT / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
