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
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
V1_SCHEMA = _ROOT.parent / "astrbot_plugin_private_companion" / "_conf_schema.json"
LEDGER = Path("docs/V1_V2_CONFIG_PROGRESS_20260926.csv")
SOURCE_ROOTS = ("companion_v2", "astrbot_host", "main.py")
# Dispositions that mean the key is accounted for, not owed.
DECIDED = ("不迁入", "移交", "不做", "v1 专有", "范围待定", "已销账", "不适用")
# Dispositions that mean the key is still owed.
OWED = ("待接入", "待补齐", "待迁移", "未接入")


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
        base = Path(root)
        for path in ([base] if base.is_file() else base.rglob("*.py")):
            if "companion_v2/configuration/" in path.as_posix():
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(chunks)


def main():
    schema = json.loads(V1_SCHEMA.read_text(encoding="utf-8-sig"))
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
    by_group_leaf = {}
    lines = LEDGER.read_text(encoding="utf-8-sig").splitlines()
    header = lines[0].split(",")
    idx_group, idx_key = header.index("V1配置组"), header.index("配置键")
    idx_item, idx_sub, idx_next = (header.index("V2配置项进度"), header.index("V2子类进度"),
                                   header.index("下一步"))
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) <= max(idx_group, idx_key, idx_item, idx_sub, idx_next):
            continue
        note = " ".join(cells[i].strip() for i in (idx_item, idx_sub, idx_next))
        ledger[normalize(cells[idx_key])] = note
        if cells[idx_group].strip():
            by_group_leaf[(cells[idx_group].strip(), normalize(cells[idx_key]))] = note

    def ledger_note(path):
        """Look a schema path up in the ledger by group and last segment."""
        group, leaf = (path.rsplit(".", 1) if "." in path else ("", path))
        return by_group_leaf.get((group, normalize(leaf))) or ledger.get(normalize(leaf))

    def classify(path):
        note = ledger_note(path)
        if note is None:
            return "no-ledger-row"
        if any(mark in note for mark in DECIDED):
            return "decided-not-migrated"
        if any(mark in note for mark in OWED):
            return "owed"
        return "recorded-other"

    matched = []
    unmatched = []
    for path, _kind in leaves:
        leaf = path.rsplit(".", 1)[-1]
        fields = by_key.get(leaf) or by_key.get(normalize(leaf)) or []
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
    decided = sum(count for name, count in buckets.items() if name.endswith("/decided-not-migrated"))
    norow = sum(count for name, count in buckets.items() if name.endswith("/no-ledger-row"))
    print("OWED (any)         ", owed, f"{100.0 * owed / total:.1f}%")
    print("DECIDED_NOT_MIGRATED", decided, f"{100.0 * decided / total:.1f}%")
    print("NO_LEDGER_ROW      ", norow, f"{100.0 * norow / total:.1f}%")
    print("--- 30 matched examples")
    for path, fields in matched[:30]:
        print(f"   {path:52} -> {fields[0]}")

    # A per-key ledger so every number above can be checked line by line.
    out = Path("docs/V1_V2_CONFIG_COVERAGE_AUDIT_20260927.csv")
    rows = ["v1_key,v1_type,v2_field,v2_group,disposition"]
    for path, kind in leaves:
        leaf = path.rsplit(".", 1)[-1]
        fields = by_key.get(leaf) or by_key.get(normalize(leaf)) or []
        rows.append(",".join((path, str(kind), fields[0] if fields else "",
                              fields[0].rsplit(".", 1)[0] if fields else "", classify(path))))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print("WROTE", out, len(rows) - 1, "rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
