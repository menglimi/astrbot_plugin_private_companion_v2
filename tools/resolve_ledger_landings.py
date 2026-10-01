"""Resolve every V1 ledger row down to a concrete V2 landing.

The ledger (``docs/V1_V2_CONFIG_VERIFIED_20260927.csv``) judges each V1 key, but only
100 of its 1010 rows name a ``v2_field``. The other 373 rows judged "already in V2"
carry prose in ``verified_landing`` instead, naming things like
``multi_host.targets[].account_id`` or ``conversation.presentation.style_prompt``.

Prose cannot be counted, compared, or migrated against. This script turns each row into
one of five kinds:

``registry``      the landing names a field the configuration registry really defines
``plugin-config`` the landing names a leaf in ``_conf_schema.json``
``other-surface`` the landing names a storage table, route, or page
``external``      the landing names another plugin, module, or file
``unresolved``    nothing extractable resolves — the row needs a human

Run from the repository root::

    python3 tools/resolve_ledger_landings.py

Writes ``docs/V1_V2_CONFIG_RESOLVED_20260928.csv`` and prints the tally. The tally is
the point: it says how much of the ledger is actually load-bearing for migration.
"""

from __future__ import annotations

import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "V1_V2_CONFIG_VERIFIED_20260927.csv"
OUT = ROOT / "docs" / "V1_V2_CONFIG_RESOLVED_20260928.csv"

# A path-shaped token: dotted lower-case segments, optionally with an index.
CANDIDATE = re.compile(r"\b([a-z][a-z0-9_]*(?:\.[a-z0-9_]+){1,8})")
TRAILING_INDEX = re.compile(r"\[\]?$")

# Suffixes that betray a filename rather than a field path.
FILE_SUFFIX = re.compile(r"\.(py|js|css|json|db|csv|md|txt|html)$")


def load_registry_fields() -> set[str]:
    sys.path.insert(0, str(ROOT))
    try:
        import stub_astrbot  # noqa: F401
    except ImportError:
        pass

    import importlib

    fields: set[str] = set()
    for path in (ROOT / "companion_v2").rglob("*.py"):
        if "def configuration_fields" not in path.read_text(encoding="utf-8"):
            continue
        dotted = str(path.relative_to(ROOT).with_suffix("")).replace("/", ".").replace("\\", ".")
        try:
            module = importlib.import_module(dotted)
        except Exception:
            continue
        factory = getattr(module, "configuration_fields", None)
        if not factory:
            continue
        try:
            produced = factory()
        except TypeError:
            # Argument-fed factories are handled by build_v2_inventory.py; for
            # resolution purposes their field names are recoverable from the CSV it
            # writes, which is read below.
            continue
        except Exception:
            continue
        fields |= {definition.field_id for definition in produced}

    surface = ROOT / "docs" / "V2_CONFIG_SURFACE_20260928.csv"
    if surface.exists():
        with surface.open(encoding="utf-8") as handle:
            fields |= {row["field_id"] for row in csv.DictReader(handle)}
    return fields


def load_plugin_leaves() -> set[str]:
    path = ROOT / "_conf_schema.json"
    if not path.exists():
        return set()
    leaves: set[str] = set()
    schema = json.loads(path.read_text(encoding="utf-8"))

    def walk(node, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        for name, spec in node.items():
            full = f"{prefix}.{name}" if prefix else name
            if not isinstance(spec, dict):
                continue
            if spec.get("type") == "object":
                walk(spec.get("items", {}), full)
            elif "type" in spec:
                leaves.add(full)
            else:
                walk(spec, full)

    walk(schema, "")
    return leaves


def load_tables() -> set[str]:
    tables: set[str] = set()
    for path in (ROOT / "companion_v2" / "storage").rglob("*.py"):
        tables |= set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)",
                                 path.read_text(encoding="utf-8")))
    return tables


def climb(token: str, known: set[str], *, floor: int = 2) -> str | None:
    """Return the longest prefix of ``token`` that ``known`` contains.

    Ledger prose writes ``multi_host.targets[].account_id``, where only
    ``multi_host.targets`` exists, so prefixes are walked longest-first rather than
    demanding an exact match.

    ``floor`` is the number of segments a match must have. Without it a token like
    ``expression.learning`` climbs to the bare word ``expression`` and "resolves" to
    whatever single-segment key happens to exist -- which is how a resolver reports a
    landing as found when nothing was found. One segment is a domain, not a field.
    """
    parts = token.split(".")
    for length in range(len(parts), floor - 1, -1):
        candidate = ".".join(parts[:length])
        if candidate in known:
            return candidate
    return None


def resolve(landing: str, registry: set[str], plugins: set[str],
            tables: set[str]) -> tuple[str, str, str]:
    """Return (kind, target, note) for one landing string."""
    text = TRAILING_INDEX.sub("", landing)
    tokens = [token for token in CANDIDATE.findall(text) if not FILE_SUFFIX.search(token)]
    if not tokens:
        if text.strip():
            return "external", "", "landing 是散文，未给出字段路径"
        return "unresolved", "", "landing 为空"

    # Plugin config paths are shallow on purpose (``multi_host.targets``), so they get
    # the lower floor; registry field IDs carry the group, so two segments is right.
    best_registry = [climb(token, registry, floor=2) for token in tokens]
    hits = sorted({hit for hit in best_registry if hit})
    if hits:
        # Longest hit is the most specific, so prefer it as the headline target.
        return "registry", max(hits, key=len), ""

    plugin_hits = sorted({climb(token, plugins, floor=1) for token in tokens} - {None})
    if plugin_hits:
        return "plugin-config", max(plugin_hits, key=len), ""

    table_hits = [token.split(".")[0] for token in tokens if token.split(".")[0] in tables]
    if table_hits:
        return "other-surface", sorted(set(table_hits))[0], ""

    return "unresolved", "", f"候选 token 均无法定位：{', '.join(tokens[:3])}"


def main() -> int:
    registry = load_registry_fields()
    plugins = load_plugin_leaves()
    tables = load_tables()
    print(f"registry fields {len(registry)}   plugin leaves {len(plugins)}   tables {len(tables)}")

    with LEDGER.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    out_rows = []
    for row in rows:
        kind, target, note = resolve(row.get("verified_landing", ""), registry, plugins, tables)
        declared = (row.get("v2_field") or "").strip()
        # A row that names a field explicitly and resolves elsewhere is a contradiction
        # worth seeing, not one to paper over.
        conflict = "yes" if declared and kind == "registry" and declared != target else ""
        out_rows.append({**row, "resolved_kind": kind, "resolved_target": target,
                         "resolved_note": note, "declared_vs_resolved": conflict})

    with OUT.open("w", newline="\n", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    by_kind = collections.Counter(row["resolved_kind"] for row in out_rows)
    print(f"\nwrote {OUT.relative_to(ROOT)}  ({len(out_rows)} 行)\n")
    for kind, count in by_kind.most_common():
        print(f"  {kind:<16}{count:>5}  {count / len(out_rows):>6.1%}")

    print("\n按判定 × 落点类型：")
    grid = collections.defaultdict(collections.Counter)
    for row in out_rows:
        grid[row["verified_verdict"]][row["resolved_kind"]] += 1
    kinds = [k for k, _ in by_kind.most_common()]
    print(f"    {'判定':<26}" + "".join(f"{k:>16}" for k in kinds))
    for verdict, counter in sorted(grid.items(), key=lambda item: -sum(item[1].values())):
        print(f"    {verdict:<26}" + "".join(f"{counter[k]:>16}" for k in kinds))

    conflicts = [row for row in out_rows if row["declared_vs_resolved"]]
    print(f"\nv2_field 与 landing 指向不一致：{len(conflicts)} 行")
    for row in conflicts[:10]:
        print(f"    {row['v1_key'][:44]:<46}{row['v2_field']} -> {row['resolved_target']}")

    unresolved = [row for row in out_rows if row["resolved_kind"] == "unresolved"]
    print(f"\n无法定位（需要人工）：{len(unresolved)} 行")
    for row in unresolved[:15]:
        print(f"    {row['verified_verdict']:<22}{row['v1_key'][:34]:<36}{row['resolved_note'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
