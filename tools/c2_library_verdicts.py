"""Record the C2-3 verdicts once the library group carries them.

Each landing names the V2 field that now holds the setting, and the names are
checked against the live registry so a later rename cannot silently orphan the
claim.

Usage:
    python tools/c2_library_verdicts.py --check
    python tools/c2_library_verdicts.py --apply
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "V1_V2_CONFIG_VERIFIED_20260927.csv"

OWED = "owed"
RENAMED = "renamed-equivalent"

ROWS: dict[str, tuple[str, str]] = {
    # --- C2-3a: ratings become taste ------------------------------------------
    "reading_archive_config.enable_reading_archive_rating": (
        RENAMED, "library.rating_enabled（按角色）：书评打分范围 1–5；不打分的书评只是"
                 "「读过」，不参与口味判断。"),
    "reading_archive_config.enable_reading_archive_preference_influence": (
        RENAMED, "library.preference_influence_enabled（按角色）：偏好只作口味参考注入，"
                 "不是本轮要求，角色可以不同意；关闭后完全不注入。"),
    "reading_archive_config.reading_archive_preference_min_ratings": (
        RENAMED, "library.preference_min_ratings（按角色，1–64，默认 5）：打分数不到下限时"
                 "什么都不注入——证据不足时沉默，而不是给一个更弱的猜测。"),
    "reading_archive_config.reading_archive_preference_max_terms": (
        RENAMED, "library.preference_max_terms（按角色，1–32，默认 8）：一次最多列出几部作品，"
                 "按口味强弱取前几名，不改动已保存的书评。"),
    # --- C2-3b: when the shelf may speak --------------------------------------
    "reading_archive_config.reading_archive_min_interval_hours": (
        RENAMED, "library.min_interval_hours（按角色，1–720，默认 18）：游标存于"
                 "reading_archive_triggers 表，重启不会重置；间隔先于概率判定，"
                 "概率设为 1 也不能越过间距。"),
    "reading_archive_config.reading_archive_share_probability": (
        RENAMED, "library.share_probability（按角色，0–1，默认 0.18）：主动分享读书进展的概率；"
                 "与询问各自计时。"),
    "reading_archive_config.reading_archive_ask_probability": (
        RENAMED, "library.ask_probability（按角色，0–1，默认 0.16）：主动询问对方阅读的概率。"),
}

NAMED_FIELDS = (
    "library.rating_enabled",
    "library.preference_influence_enabled",
    "library.preference_min_ratings",
    "library.preference_max_terms",
    "library.min_interval_hours",
    "library.share_probability",
    "library.ask_probability",
)
EXPECT_TOTAL = 7

# The table the trigger cursor lives in; the landing claims it, so it is checked too.
TRIGGER_TABLE = "reading_archive_triggers"


def verify_carriers() -> list[str]:
    """Return the named carriers that no longer exist, fields or table."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from companion_v2.library.configuration import configuration_fields
    from companion_v2.storage import schema
    registered = {field.field_id for field in configuration_fields()}
    problems = [name for name in NAMED_FIELDS if name not in registered]
    if TRIGGER_TABLE not in schema.REQUIRED_TABLES:
        problems.append(TRIGGER_TABLE)
    return problems


def plan(rows):
    by_key = {row["v1_key"]: row for row in rows}
    changes, problems = [], []
    for key, (verdict, landing) in ROWS.items():
        row = by_key.get(key)
        if row is None:
            problems.append(f"{key}: absent from ledger")
        elif row["verified_verdict"] == OWED:
            changes.append((key, row, verdict, landing))
        elif row["verified_verdict"] != verdict:
            problems.append(f"{key}: already {row['verified_verdict']!r}, expected {verdict!r}")
    return changes, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args()
    if not (args.check or args.apply):
        parser.error("pass --check or --apply")
    target = args.ledger or LEDGER

    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames, rows = reader.fieldnames, list(reader)
    changes, problems = plan(rows)
    for item in problems:
        print(f"PROBLEM  {item}", file=sys.stderr)
    if len(ROWS) != EXPECT_TOTAL:
        print(f"PROBLEM  the mapping holds {len(ROWS)} rows, expected {EXPECT_TOTAL}", file=sys.stderr)
        return 1
    orphans = verify_carriers()
    for name in orphans:
        print(f"PROBLEM  the ledger names {name}, which is not registered", file=sys.stderr)
    if problems or orphans:
        return 1
    print(f"  rows recorded by a V2 field: {len(ROWS)}")
    print(f"  carriers verified         : {len(NAMED_FIELDS)} fields + {TRIGGER_TABLE}")
    if args.check:
        print(f"would record {len(changes)} rows (dry run, nothing written)")
        return 0
    backup = target.with_suffix(".csv.bak")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
    for key, row, verdict, landing in changes:
        row["verified_verdict"] = verdict
        row["verified_landing"] = landing
    temp = target.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(target)
    print(f"recorded {len(changes)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
