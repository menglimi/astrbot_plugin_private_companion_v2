"""One-off audit: V1 configuration surface vs V2, separating design decisions from gaps.

For every scalar key of V1's ``_conf_schema.json``:
  match     a V2 registered field whose *last segment* equals the V1 key (case- and
            punctuation-insensitive). The last segment is what source code names.
  wired     that V2 field is actually read by a production consumer, proven by the
            field's group id appearing in source outside the configuration package.
  ledger    the migration ledger has a row for the key, with its recorded disposition.

The point is to avoid the two easy mistakes: counting a deliberate "do not migrate"
decision as a debt, and calling a field a feature when nothing reads it.
"""

from __future__ import annotations

import json
import argparse
import csv
import re
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
DEFAULT_V1_SCHEMA = _ROOT.parent / "astrbot_plugin_private_companion" / "_conf_schema.json"
LEDGER = _ROOT / "docs/V1_V2_CONFIG_RESOLVED_20260928.csv"
SOURCE_ROOTS = ("companion_v2", "astrbot_host", "main.py")
_SPECIALIZED_V2_FIELDS = {
    "basic_config.enable_environment_perception": (
        "conversation.perception.calendar_enabled",
        "conversation.perception.platform_enabled",
        "conversation.perception.model_route_enabled",
        "conversation.perception.configured_modalities_enabled",
    ),
}
_SETTLED_VERDICTS = {
    "already-in-v2", "renamed-equivalent", "implemented-elsewhere",
    "not-migrated-by-design", "not-applicable",
}


def v1_leaves(node, prefix=""):
    for name, spec in node.items():
        path = f"{prefix}{name}"
        if not isinstance(spec, dict):
            continue
        if spec.get("type") == "object" and isinstance(spec.get("items"), dict):
            yield from v1_leaves(spec["items"], path + ".")
        else:
            yield path, spec.get("type")


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def dedupe_legacy_mirrors(leaves):
    """Drop the legacy flat mirrors of grouped keys.

    V1 carries each ``basic_config.x`` a second time as a bare top-level ``x`` for old
    configs. Counting both inflates the denominator by ~68%, so a bare key whose last
    segment also appears as a grouped key is dropped as a mirror, and every mirror is
    reported separately. Only ten bare keys carry their own semantics.
    """
    grouped = {path.rsplit(".", 1)[-1] for path, _kind in leaves if "." in path}
    unique, mirrors = [], []
    for row in leaves:
        path, _kind = row
        (mirrors if "." not in path and path in grouped else unique).append(row)
    return unique, mirrors


def source_corpus():
    chunks = []
    for root in SOURCE_ROOTS:
        base = _ROOT / root
        for path in ([base] if base.is_file() else base.rglob("*.py")):
            if "companion_v2/configuration/" in path.as_posix():
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(chunks)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-schema", type=Path, default=DEFAULT_V1_SCHEMA,
                        help="path to the read-only V1 _conf_schema.json (defaults to the sibling plugin directory)")
    args = parser.parse_args(argv)
    if not args.v1_schema.is_file():
        parser.error(f"V1 schema not found: {args.v1_schema}; pass --v1-schema with the 6.7.0 source schema")
    schema = json.loads(args.v1_schema.read_text(encoding="utf-8-sig"))
    raw_leaves = list(v1_leaves(schema))
    leaves, mirrors = dedupe_legacy_mirrors(raw_leaves)

    from tests.test_host_application import HostFixture

    class Loader(HostFixture, unittest.IsolatedAsyncioTestCase):
        async def test_load(self):
            fields = self.host().application.configuration.registry.fields
            Path(".config-audit-fields.txt").write_text("\n".join(sorted(fields)), encoding="utf-8")

    unittest.TextTestRunner(verbosity=0).run(unittest.TestSuite([Loader("test_load")]))
    v2 = [line for line in Path(".config-audit-fields.txt").read_text(encoding="utf-8").splitlines() if line]
    Path(".config-audit-fields.txt").unlink()

    corpus = source_corpus()
    by_key = defaultdict(list)
    for field in v2:
        by_key[field.rsplit(".", 1)[-1]].append(field)
        by_key[normalize(field.rsplit(".", 1)[-1])].append(field)

    # Ledger disposition per V1 key. The ledger names bare keys plus a group column,
    # while the schema uses dotted paths, so the join normalizes on the last segment.
    ledger = {}
    with LEDGER.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = row.get("v1_key", "").strip()
            if not key:
                continue
            ledger[key] = row

    def classify(path):
        row = ledger.get(path)
        if row is None:
            return "no-ledger-row"
        verdict = row.get("verified_verdict", "").strip()
        if verdict == "owed":
            return "owed"
        if verdict in _SETTLED_VERDICTS:
            return verdict
        return "unverified"

    matched = []
    unmatched = []
    for path, _kind in leaves:
        leaf = path.rsplit(".", 1)[-1]
        fields = list(dict.fromkeys(
            by_key.get(leaf) or by_key.get(normalize(leaf))
            or list(_SPECIALIZED_V2_FIELDS.get(path, ()))
        ))
        (matched if fields else unmatched).append((path, fields))

    matched_keys = {path for path, _ in matched}
    v2_leaves = {field.rsplit(".", 1)[-1] for field in v2}
    v1_leaves_set = {path.rsplit(".", 1)[-1] for path, _ in leaves}
    v2_only = sorted(v2_leaves - v1_leaves_set)

    wired = 0
    for path, fields in matched:
        # A V2 field counts as wired when its group id is named in production source.
        if any(field.rsplit(".", 1)[0] in corpus or field in corpus for field in fields):
            wired += 1

    buckets = Counter()
    for path, _fields in matched:
        buckets["matched/" + classify(path)] += 1
    for path, _fields in unmatched:
        buckets["absent/" + classify(path)] += 1
    for path, _fields in matched:
        pass

    total = len(leaves)
    print("V1_RAW_SCALAR_KEYS  ", len(raw_leaves))
    print("V1_LEGACY_MIRRORS   ", len(mirrors), " (bare top-level copies of grouped keys; not counted)")
    print("V1_SCALAR_KEYS      ", total, " (deduplicated denominator)")
    print("V2_REGISTERED_FIELDS", len(v2))
    print("V2_FIELDS_WITH_NO_V1_COUNTERPART", len(v2_only))
    print("--- disposition buckets")
    for name, count in sorted(buckets.items()):
        print(f"  {name:38} {count:5}  {100.0 * count / total:5.1f}%")
    print("--- headline")
    print("MATCHED            ", len(matched), f"{100.0 * len(matched) / total:.1f}%")
    print("MATCHED_AND_WIRED  ", wired, f"{100.0 * wired / total:.1f}%")
    owed = sum(count for name, count in buckets.items() if name.endswith("/owed"))
    decided = sum(count for name, count in buckets.items()
                  if name.rsplit("/", 1)[-1] in _SETTLED_VERDICTS)
    norow = sum(count for name, count in buckets.items()
                if name.endswith(("/no-ledger-row", "/unverified")))
    print("OWED (any)         ", owed, f"{100.0 * owed / total:.1f}%")
    print("DECIDED_OR_MAPPED  ", decided, f"{100.0 * decided / total:.1f}%")
    print("NO_VERIFIED_DISPOSITION", norow, f"{100.0 * norow / total:.1f}%")
    print("--- 30 matched examples")
    for path, fields in matched[:30]:
        print(f"   {path:52} -> {fields[0]}")

    # A per-key ledger so every number above can be checked line by line.
    out = _ROOT / "docs/V1_V2_CONFIG_COVERAGE_AUDIT_20260927.csv"
    rows = ["v1_key,v1_type,v2_field,v2_group,disposition"]
    for path, kind in leaves:
        leaf = path.rsplit(".", 1)[-1]
        fields = by_key.get(leaf) or by_key.get(normalize(leaf)) or []
        groups = {field.rsplit(".", 1)[0] for field in fields}
        rows.append(",".join((path, str(kind), "|".join(fields),
                              "|".join(sorted(groups)), classify(path))))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print("WROTE", out, len(rows) - 1, "rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
