"""Record the C2-4 and C2-5 verdicts.

Both groups turned out to be settled by machinery that already exists, and the
landings say which machinery — including two places where V2 is deliberately
stronger than the V1 field it replaces. Carriers are checked against the live
code, so a rename cannot silently orphan a claim.

Usage:
    python tools/c2_model_and_scatter_verdicts.py --check
    python tools/c2_model_and_scatter_verdicts.py --apply
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

# The three per-task provider assignments are retired rather than renamed: their V1
# mechanism (a dedicated provider id per auxiliary task) is superseded by the V2
# task-profile surface, and no profile of that kind exists. Retirement says "this
# concept is gone"; calling it a rename would claim a carrier that is not there.
_PROFILE_GONE = ("按 V2 模型任务档面注销：V2 用 ModelTaskProfile.default_provider 按档指派模型"
                 "（可再按 replacement_rules 改派），全仓 KIND 常量里没有对应档位"
                 "（对话 conversation.reply、计划 calendar.plan、自省 memory.reflect 等各有其档）。"
                 "V1 的“为一个辅助任务单列一个 Provider 指派”这套机制已由档位面取代，")
ROWS: dict[str, tuple[str, str]] = {
    # --- C2-4 model assignment: superseded by the V2 task-profile surface --------
    "model_assignment_config.sensitive_replacement_keywords": (
        RENAMED, "model_gateway 的 replacement_rules（按任务档的替换规则，"
                 "model_gateway/routing.py:88-103）+ 档位字段 fallback_on_refusal"
                 "（routing.py:31）：拒答即按规则改派。比 V1 强的一点是只有**已封存输入**"
                 "能触发关键词路由，召回记忆、人格提示词与工具续答都改不了选路"
                 "（routing.py:93-94），V1 那层按生成文本匹配的拒答词表因此不再需要。"),
    "model_assignment_config.deepseek_peak_match_keywords": (
        RENAMED, "replacement_rules 的 time_window（timezone + start/end + weekdays，"
                 "支持跨夜，replacement_rules.py:109-126）：V2 直接按时间窗改派，"
                 "不需要先按关键词认出是哪个 Provider 再套时段规则，"
                 "因此 V1 的“识别 DeepSeek Provider”机制整体冗余。"),
    "model_assignment_config.DETAIL_ENHANCEMENT_PROVIDER_ID": (
        RETIRED, _PROFILE_GONE + "该档位本身是实验性质，故不新建档位承接。"),
    "model_assignment_config.HISTORY_SUMMARY_PROVIDER_ID": (
        RETIRED, _PROFILE_GONE + "V2 的历史压缩由记忆与群历史链各自承担，不再单列一个指派。"),
    "model_assignment_config.DAILY_REVIEW_PROVIDER_ID": (
        RETIRED, _PROFILE_GONE + "角色自省改由 memory.reflect 档承担"
                 "（companion_v2/memory/reflection.py:31），不另设“每日复盘”档。"),
    # --- C2-5 scatter -----------------------------------------------------------
    "basic_config.persona_inner_voice_prompt": (
        RETIRED, "（销号）V2 没有“内部动机/内心活动风格”这条独立入口。发送前自检通道确实存在"
                 "（proactive.judge，companion_v2/proactive/persona_judge.py:73-84），"
                 "但它的角色指令取自 job[\"role_instruction\"]，即与其他通道共用的同一份人格，"
                 "并非可单独设置文风的第五个 style_prompt 槽位。若要补这条通道，"
                 "应作为新增功能设计，不在配置缺口范围。"),
    "weather_config.weather_refresh_minutes": (
        RENAMED, "role.state.planning_weather_max_age_minutes"
                 "（companion_v2/agenda/planning_config.py:14-30，默认 120，下限 5）："
                 "账本记为 owed 属未回写，B 批已落地。"),
    "skill_growth_config.skill_growth_rate": (
        RETIRED, "（销号）与同组的 enable_skill_growth_simulation、"
                 "enable_personal_goal_auto_progress 一并处理：V2 不注册“按固定速率累积成长”"
                 "这套机制，全仓无该字段实现；技能成长由 role.growth 的既有机制承担。"),
    "memory_habit_config.meal_care_followup_minutes": (
        RENAMED, "proactive.contact.meal_care_followup_minutes（按窗口，1–240，默认 45）："
                 "此前是 companion_v2/proactive/meal_events.py:13 硬编码的 45 分钟槽宽；"
                 "现已由配置驱动（同文件 _window），默认值与原行为一致。"),
    "life_schedule_config.daily_plan_time": (
        RETIRED, "（销号）V2 的每日规划由**本地日期**把关，不按时刻："
                 "CalendarPlanning.opportunity 的每日档以 daily:<时区>:<ISO 日期> 为尝试键"
                 "（companion_v2/agenda/planning.py:178-183），当天未尝试过就生成，"
                 "刻意不做任何时刻门（_run 只校验 mode）。同组的 enable_daily_plan、"
                 "daily_plan_item_count、daily_plan_prompt 已分别落到 role.state.planning_enabled、"
                 "planning_max_items、planning_prompt，规划机制本身在 V2 是存在的。"
                 "V1 该字段是「几点之后才允许生成」的门（daily_state.py:10208-10213，"
                 "now.hour*60+now.minute >= plan_minutes，默认 07:30）；V2 改为当日零点一过即生成，"
                 "生成得更早，于是“当天几点之后才许生成”这个门不再有作用对象。"),
    "schedule_detail_config.important_date_lookahead_days": (
        RENAMED, "proactive.contact.important_date_lookahead_days（按窗口，0–30，默认 0）："
                 "前瞻窗口内可提前提到临近纪念日；0 表示维持 V1 的仅当日问候行为。"),
    "humanized_state_config.enable_group_cycle_awareness": (
        RETIRED,
        "（销号）V2 群聊不携带角色身体/周期材料：group_cycle、cycle_boundary、"
        "group_awareness 全仓零命中，私聊之外不封存角色状态，"
        "因此没有“群聊一轮的周期语气边界”这个作用对象。"),
}

# Carriers that must still exist.
FIELD_CARRIERS = (
    ("companion_v2.proactive.persona_judge", "KIND", "attr"),
    ("companion_v2.model_gateway.routing", "CONSUMER", "attr"),
    ("companion_v2.agenda.planning_config", "DEFAULTS", "attr"),
)

# Every configuration field a RENAMED landing names as its carrier. Checked against
# the live registries: an earlier revision of this file recorded three fields that had
# never been implemented, and only a check like this one catches that.
NAMED_CONFIG_FIELDS = (
    "proactive.contact.important_date_lookahead_days",
    "proactive.contact.meal_care_followup_minutes",
)
EXPECT_TOTAL = 12


def verify_carriers() -> list[str]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import importlib
    problems = []
    for module_name, attribute, _kind in FIELD_CARRIERS:
        try:
            module = importlib.import_module(module_name)
        except Exception as error:                       # pragma: no cover - import guard
            problems.append(f"{module_name} did not import: {error}")
            continue
        if not hasattr(module, attribute):
            problems.append(f"{module_name}.{attribute} is gone")
    # The planning field the weather row names must really be a default.
    from companion_v2.agenda.planning_config import DEFAULTS
    if "planning_weather_max_age_minutes" not in DEFAULTS:
        problems.append("planning_weather_max_age_minutes is not a planning default")
    # Every named contact field must be registered.
    from companion_v2.proactive.configuration import configuration_fields as contact_fields
    registered = {field.field_id for field in contact_fields()}
    for name in NAMED_CONFIG_FIELDS:
        if name not in registered:
            problems.append(f"the ledger names {name}, which is not registered")
    # A landing may only claim a carrier that its row does not already name as owed.
    claims = {key: landing for key, (_v, landing) in ROWS.items()}
    for name in NAMED_CONFIG_FIELDS + ("planning_weather_max_age_minutes",):
        if not any(name in landing for landing in claims.values()):
            problems.append(f"{name} is listed as a carrier but no landing names it")
    # Routing must still be keyword+window aware, since two landings claim it.
    from companion_v2.model_gateway import replacement_rules
    import dataclasses
    for name in ("match_route", "build_rules", "RouteRule", "RouteMatch"):
        if not hasattr(replacement_rules, name):
            problems.append(f"replacement_rules.{name} is gone")
    rule_fields = {field.name for field in dataclasses.fields(replacement_rules.RouteRule)}
    for name in ("keywords", "match_mode", "keyword_logic", "start_minute", "end_minute",
                 "weekdays", "timezone"):
        if name not in rule_fields:
            problems.append(f"RouteRule no longer carries {name}")
    if not callable(getattr(replacement_rules, "match_route", None)):
        problems.append("keyword routing is gone")
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
        print(f"PROBLEM  {name}", file=sys.stderr)
    if problems or orphans:
        return 1
    renamed = sum(1 for verdict, _ in ROWS.values() if verdict == RENAMED)
    retired = sum(1 for verdict, _ in ROWS.values() if verdict == RETIRED)
    print(f"  superseded by existing machinery: {renamed}")
    print(f"  retired with a reason          : {retired}")
    print(f"  carriers verified              : {len(FIELD_CARRIERS)} modules + planning field + rule engine")
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
