"""C2-1 (参考图链) dispositions that are settled by the code, not by preference.

Each entry records an architectural reason that can be re-checked against source,
so a later audit can tell a deliberate retirement from a convenient one.

Usage:
    python tools/c2_dispositions.py --check
    python tools/c2_dispositions.py --apply
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "V1_V2_CONFIG_VERIFIED_20260927.csv"

RETIRED = "not-migrated-by-design"
OWED = "owed"

# Overridable so a test can exercise the real code against a scratch copy instead
# of the governance artefact itself.
_TARGET: Path | None = None


def _target() -> Path:
    """Resolve the ledger for this call.

    The module-level override exists only for tests; when it is unset the real
    governance artefact is used.  Every read and write goes through here so a
    test can never write the scratch copy over the real ledger.
    """
    candidate = globals().get("_TARGET")
    return Path(candidate) if candidate is not None else LEDGER


def ledger_path() -> Path:
    return _target()

REASON_LIST = (
    "（销号）配置层不承载数据：V2 的配置取值是标量"
    "（companion_v2/configuration/models.py:15 Scalar = bool | int | float | str），"
    "注册表 ValueKind 也只有 boolean/integer/text/probability/weight，无列表类型。"
    "参考素材按 C2-1 口径是角色资产（引用 + SHA-256 + 职责），归资产注册表，不落配置。"
)
REASON_PATH = (
    "（销号）配置层不承载文件路径：在配置文本里存本地路径会绕过资产所有权与可见性检查"
    "（C2-1 验收标准第 2 条的明确要求）。参考图按登记条目存在资产注册表，配置里搜不到绝对路径。"
)
REASON_LOAD_GUARD = (
    "（销号）本机负载门控在 V2 无对象：V2 全仓 grep cpu_busy|memory_busy|load_guard|psutil "
    "命中 0，且生图执行在 Image 提供方侧、不在运行 V2 的进程里，"
    "本机的 CPU/内存阈值没有可门控的本地生成步骤。"
)

GROUPS: dict[str, dict[str, object]] = {
    "photo_reference_list_fields": {
        "reason": REASON_LIST,
        "keys": [
            "photo_action_config.photo_structured_reference_assets",
            "photo_action_config.photo_reference_catalog",
            "photo_action_config.photo_reference_library",
        ],
    },
    "photo_persona_reference_path": {
        "reason": REASON_PATH,
        "keys": [
            "photo_action_config.photo_persona_reference_image_path",
        ],
    },
    "local_photo_load_guard": {
        "reason": REASON_LOAD_GUARD,
        "keys": [
            "photo_action_config.enable_local_photo_load_guard",
            "photo_action_config.local_photo_cpu_busy_percent",
            "photo_action_config.local_photo_memory_busy_percent",
            "photo_action_config.local_photo_defer_minutes",
        ],
    },
}

# Keys that must still be owed because their behaviour does not exist yet. Empty
# once C2-1 landed: all three reference fields now have a group, a consumer and a
# page entry, and are recorded by tools/c2_group_verdicts.py instead.
PENDING: tuple[str, ...] = ()


def load_rows():
    with _target().open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def save_rows(fieldnames, rows, path=None):
    target = Path(path) if path is not None else _target()
    # Keep one restore point before the first mutation, so a bad run is reversible
    # without git (the ledger is a tracked artefact but the tree is untracked here).
    backup = target.with_suffix(".csv.bak")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
    temp = target.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(target)


def plan(rows, *, pending_only=False):
    """Return the rows this pass would change.

    ``pending_only`` filters to rows that are not already at the retired verdict,
    so an idempotent second pass reports nothing to do instead of re-listing work
    that was already done.
    """
    by_key = {row["v1_key"]: row for row in rows}
    todo, problems = [], []
    for group, spec in GROUPS.items():
        for key in spec["keys"]:
            row = by_key.get(key)
            if row is None:
                problems.append(f"{group}: {key} absent from ledger")
            elif row["verified_verdict"] == OWED:
                todo.append((group, key, row))
            elif row["verified_verdict"] != RETIRED:
                problems.append(f"{group}: {key} has unexpected verdict {row['verified_verdict']!r}")
    for key in PENDING:
        row = by_key.get(key)
        if row is None:
            problems.append(f"pending: {key} absent from ledger")
        elif row["verified_verdict"] != OWED:
            problems.append(f"pending: {key} is {row['verified_verdict']!r}, expected still owed")
    return todo, problems


def plan_changes(rows):
    """The rows a real apply pass would rewrite: those still owing a verdict."""
    todo, problems = plan(rows)
    return [(group, key, row) for group, key, row in todo
            if row["verified_verdict"] == OWED], problems

def main() -> int:
    global _TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ledger", type=Path, default=None,
                        help="operate on a scratch copy instead of the real ledger")
    args = parser.parse_args()
    if not (args.check or args.apply):
        parser.error("pass --check or --apply")
    if args.ledger is not None:
        _TARGET = args.ledger

    fieldnames, rows = load_rows()
    todo, problems = plan(rows)
    for item in problems:
        print(f"PROBLEM  {item}", file=sys.stderr)
    if problems:
        return 1
    changes = [(group, key, row) for group, key, row in todo if row["verified_verdict"] == OWED]
    for group in GROUPS:
        keys = GROUPS[group]["keys"]
        print(f"  {group}: {len(keys)} keys")
    print(f"  still owed pending the asset chain: {len(PENDING)}")
    if args.check:
        print(f"would retire {len(changes)} rows (dry run, nothing written)")
        return 0
    for group, key, row in changes:
        row["verified_verdict"] = RETIRED
        row["verified_landing"] = GROUPS[group]["reason"]
    save_rows(fieldnames, rows)
    print(f"retired {len(changes)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
