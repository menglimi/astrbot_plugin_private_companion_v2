"""Record the C2-1 / C2-2 verdicts once their groups exist.

Each entry names the V2 field that now carries the V1 setting, so a later audit can
follow the mapping instead of re-deriving it. Two rows are settled by a recorded
decision rather than a field, and say so.

Usage:
    python tools/c2_group_verdicts.py --check
    python tools/c2_group_verdicts.py --apply
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
RETIRED = "not-migrated-by-design"

# v1_key -> (verdict, landing). The landing names the V2 carrier.
ROWS: dict[str, tuple[str, str]] = {
    # --- C2-1: the reference group (companion_v2/references/configuration.py) ---
    "photo_action_config.enable_photo_reference_image": (
        RENAMED, "photo.reference.enabled（按角色）；参考素材改为登记条目而非配置路径，"
                 "见 companion_v2/references/。"),
    "photo_action_config.enable_daily_outfit_photo": (
        RENAMED, "photo.reference.daily_outfit_enabled（按角色）。与参考图总闸分开："
                 "同意使用参考图不等于同意每天出穿搭图。"),
    "photo_action_config.daily_outfit_rotation_days": (
        RENAMED, "photo.reference.daily_outfit_rotation_days（按角色，1–365，默认 14）。"),
    # --- C2-2: the wardrobe group (companion_v2/references/wardrobe.py) ---
    "wardrobe_config.enable_wardrobe": (
        RENAMED, "wardrobe.enabled（按角色）。关闭后既不进提示词，也不接受新的识图入库；"
                 "已保存条目保留。"),
    "wardrobe_config.wardrobe_tendency": (
        RENAMED, "wardrobe.tendency（按角色，≤800 字，超长在写入时拒绝而非截断）。"),
    "wardrobe_config.enable_wardrobe_prompt": (
        RENAMED, "wardrobe.prompt_enabled（按角色）：关闭时衣柜完全不进提示词，条目仍可查看。"),
    "wardrobe_config.wardrobe_prompt_max_items": (
        RENAMED, "wardrobe.prompt_max_items（按角色，1–24，默认 12）：只限制单次提示词列出件数，"
                 "不删改已保存条目。"),
    "wardrobe_config.wardrobe_image_max_count": (
        RENAMED, "wardrobe.image_max_count（按角色，1–8，默认 3）：一次穿搭请求最多识别的图片数。"),
    "wardrobe_config.wardrobe_image_prompt": (
        RENAMED, "wardrobe.image_prompt（按角色，≤800 字）。"),
    # --- the two rows the plan itself settles elsewhere ---
    "wardrobe_config.wardrobe_items": (
        RETIRED, "（销号）条目是数据不是配置：V2 配置取值只有标量"
                 "（companion_v2/configuration/models.py:15），衣物条目落存储表 "
                 "wardrobe_items/reference_assets（companion_v2/storage/reference_asset_schema.py），"
                 "配置只留开关与上限。"),
    "wardrobe_config.WARDROBE_VISION_PROVIDER_ID": (
        RETIRED, "（销号）属「提供方凭据/指派」类，按既定取向不进 V2 配置文本；"
                 "识别改用通用视觉提供方档位。"),
}

# Rows that are implemented but whose V1 name carried no distinct meaning.
EXPECT_TOTAL = 11


# Every V2 field the landings name as a carrier. Checked against the live registry
# so a later rename cannot silently orphan the ledger's claim.
NAMED_FIELDS = (
    "photo.reference.enabled",
    "photo.reference.daily_outfit_enabled",
    "photo.reference.daily_outfit_rotation_days",
    "wardrobe.enabled",
    "wardrobe.tendency",
    "wardrobe.prompt_enabled",
    "wardrobe.prompt_max_items",
    "wardrobe.image_max_count",
    "wardrobe.image_prompt",
)


def verify_fields() -> list[str]:
    """Return the named carriers that no longer exist in the registry."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from companion_v2.references.configuration import configuration_fields as reference_fields
    from companion_v2.references.wardrobe import configuration_fields as wardrobe_fields
    registered = {field.field_id for field in (*reference_fields(), *wardrobe_fields())}
    return [name for name in NAMED_FIELDS if name not in registered]


def load_rows():
    with LEDGER.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def save_rows(fieldnames, rows, path=None):
    target = Path(path) if path is not None else LEDGER
    temp = target.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(target)


def plan(rows):
    by_key = {row["v1_key"]: row for row in rows}
    changes, problems = [], []
    for key, (verdict, landing) in ROWS.items():
        row = by_key.get(key)
        if row is None:
            problems.append(f"{key}: absent from ledger")
            continue
        if row["verified_verdict"] == OWED:
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
    if problems:
        return 1
    if len(ROWS) != EXPECT_TOTAL:
        print(f"PROBLEM  the mapping holds {len(ROWS)} rows, expected {EXPECT_TOTAL}", file=sys.stderr)
        return 1
    orphaned = verify_fields()
    if orphaned:
        for name in orphaned:
            print(f"PROBLEM  the ledger names {name}, which is not registered", file=sys.stderr)
        return 1
    named = sum(1 for verdict, _ in ROWS.values() if verdict == RENAMED)
    print(f"  named by a V2 field: {named}")
    print(f"  settled elsewhere : {len(ROWS) - named}")
    print(f"  carriers verified : {len(NAMED_FIELDS)}")
    if args.check:
        print(f"would record {len(changes)} rows (dry run, nothing written)")
        return 0
    backup = target.with_suffix(".csv.bak")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
    for key, row, verdict, landing in changes:
        row["verified_verdict"] = verdict
        row["verified_landing"] = landing
    save_rows(fieldnames, rows, target)
    print(f"recorded {len(changes)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
