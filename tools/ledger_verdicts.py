"""Write verified C-class verdicts back into the V1→V2 config ledger.

The ledger carries embedded newlines inside quoted fields, so it is edited
through a real CSV parser rather than line surgery.  Output keeps the repo
contract: UTF-8 without BOM and LF line endings.

Usage:
    python tools/ledger_verdicts.py --check
    python tools/ledger_verdicts.py --apply

Retired groups land as ``not-migrated-by-design`` — the same verdict the other
252 retired rows already use — and each records its reason in
``verified_landing`` prefixed with （销号）, so a later audit can tell a
deliberate retirement from a silent one.

Deliberately key-listed rather than prefix-matched: ``experimental_motivation_config``
holds both the relationship-penalty family and the qzone emotional-vent family,
so a prefix rule would retire the wrong set.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "V1_V2_CONFIG_VERIFIED_20260927.csv"

# Verdict vocabulary already present in the ledger; 销号 uses the same word the
# other 252 retired rows use.
RETIRED = "not-migrated-by-design"
OWED = "owed"

# Each group lists the exact v1_key values it retires and the reason recorded in
# verified_landing.  Listing keys explicitly (instead of matching a prefix) is
# deliberate: experimental_motivation_config holds both the relationship-penalty
# items and the qzone vent items, so a prefix rule would retire the wrong set.
GROUPS: dict[str, dict[str, object]] = {
    "relay_bridge": {
        "reason": "跨授权域能力，V2 不迁移：V2 群聊是独立授权域，"
                  "conversation.group_participation 全部动作 shareable=False，"
                  "转述会把一个群的可见内容带进另一个群的受众；V2 无转述模块（grep relay|atrelay 命中 0）。",
        "keys": [
            "relay_bridge_config.enable_atrelay_tools",
            "relay_bridge_config.atrelay_sensitive_confirm",
            "relay_bridge_config.enable_atrelay_llm_rewrite",
            "relay_bridge_config.atrelay_default_relay_style",
            "relay_bridge_config.atrelay_multi_target_limit",
        ],
    },
    "reading_archive_candidate_filter": {
        "reason": "V2 无外部检索源：阅读材料由 operator 显式投喂"
                  "（role_work/life/management.py），没有候选池可供筛选，"
                  "关键词与屏蔽标签无作用对象。",
        "keys": [
            "reading_archive_config.reading_archive_default_keywords",
            "reading_archive_config.reading_archive_blocked_tags",
            "reading_archive_config.reading_archive_max_photo_count",
        ],
    },
    "reading_archive_vision_comment_recommend": {
        "reason": "依赖 V2 不存在的对象：页边短批注与页面图像要求图片型阅读材料，"
                  "V2 阅读对象是纯文本 SourceRecord；征求推荐依赖外部检索源，V2 无检索源。",
        "keys": [
            "reading_archive_config.enable_reading_archive_vision",
            "reading_archive_config.enable_reading_archive_page_comments",
            "reading_archive_config.enable_reading_archive_ask_recommendation",
        ],
    },
    "voice_playback": {
        "reason": "本机侧能力（在运行 AstrBot 的电脑上播放 TTS、叠加直播字幕），"
                  "既定不迁入 V2：V2 的出站投递面向平台受众，"
                  "本机播放与字幕 overlay 不属于任何 scope 的授权对象。",
        "keys": [
            "voice_playback_config.enable_tts_local_playback",
            "voice_playback_config.enable_tts_local_playback_live_only",
            "voice_playback_config.tts_local_playback_volume",
            "voice_playback_config.tts_local_playback_min_interval_seconds",
            "voice_playback_config.enable_tts_live_subtitle_sync",
            "voice_playback_config.tts_live_subtitle_url",
        ],
    },
    "experimental_motivation_relationship_penalty": {
        "reason": "属「亲密度数值化系统」不迁入类目：V2 关系模型不使用边界分级、"
                  "违规惩罚与道歉分级，已由表达层与记忆层的既有机制承担。",
        "keys": [
            "experimental_motivation_config.enable_relationship_violation_penalties",
            "experimental_motivation_config.enable_relationship_boundary_feedback",
            "experimental_motivation_config.enable_relationship_boundary_stage",
            "experimental_motivation_config.enable_relationship_boundary_apology",
            "experimental_motivation_config.enable_relationship_boundary_bottom_line",
            "experimental_motivation_config.relationship_boundary_tier_adaptive",
            "experimental_motivation_config.relationship_boundary_penalty_light",
            "experimental_motivation_config.relationship_boundary_penalty_mid",
            "experimental_motivation_config.relationship_boundary_penalty_severe",
            "experimental_motivation_config.relationship_boundary_penalty_bottom_line",
        ],
    },
    "qzone": {
        "reason": "属「QQ 空间全链」不迁入类目：V2 不含 QQ 空间读写，"
                  "评论收件箱轮询与情绪宣泄发布都依赖该链。",
        "keys": [
            "qzone_config.qzone_comment_inbox_interval_minutes",
            "qzone_config.qzone_comment_inbox_recent_posts",
            "qzone_config.qzone_comment_inbox_max_replies_per_tick",
            "experimental_motivation_config.enable_qzone_emotional_vent_publish",
            "experimental_motivation_config.qzone_emotional_vent_threshold",
            "experimental_motivation_config.qzone_emotional_vent_cooldown_hours",
            "experimental_motivation_config.qzone_emotional_vent_probability",
        ],
    },
    "photo_action_prompt_series": {
        "reason": "用户已定：V2 取消生图提示词编排层。风格、负向提示词与固定提示词"
                  "都不在 V2 注册；画面要求由原模型在对话内表达。",
        "keys": [
            "photo_action_config.photo_generation_prompt_format",
            "photo_action_config.photo_generation_style",
            "photo_action_config.photo_generation_style_custom_prompt",
            "photo_action_config.photo_generation_negative_prompt_mode",
            "photo_action_config.photo_generation_negative_prompt",
            "photo_action_config.photo_generation_text2img_negative_prompt",
            "photo_action_config.photo_generation_selfie_negative_prompt",
            "photo_action_config.photo_generation_edit_negative_prompt",
            "photo_action_config.photo_generation_text2img_fixed_prompt",
            "photo_action_config.photo_generation_selfie_fixed_prompt",
            "photo_action_config.photo_generation_edit_fixed_prompt",
            "photo_action_config.photo_generation_fixed_prompt",
            "photo_action_config.daily_outfit_photo_prompt",
        ],
    },
}


def load_rows():
    with LEDGER.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def save_rows(fieldnames, rows):
    temp = LEDGER.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(LEDGER)


def plan(rows):
    """Return (changes, missing) without mutating anything."""
    by_key = {}
    for row in rows:
        by_key.setdefault(row["v1_key"], []).append(row)
    changes, missing = [], []
    for group, spec in GROUPS.items():
        for key in spec["keys"]:
            matches = by_key.get(key)
            if not matches:
                missing.append((group, key, "key absent from ledger"))
                continue
            for row in matches:
                if row["verified_verdict"] == OWED:
                    changes.append((group, key, row, OWED, RETIRED))
                elif row["verified_verdict"] == RETIRED:
                    changes.append((group, key, row, RETIRED, RETIRED))
                else:
                    missing.append((group, key,
                                    f"unexpected verdict {row['verified_verdict']!r}"))
    return changes, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report without writing")
    parser.add_argument("--apply", action="store_true", help="write the verdicts")
    args = parser.parse_args()
    if not (args.check or args.apply):
        parser.error("pass --check or --apply")

    fieldnames, rows = load_rows()
    changes, missing = plan(rows)
    for group, key, reason in missing:
        print(f"MISSING  {group}: {key} -> {reason}", file=sys.stderr)
    if missing:
        return 1

    todo = [(group, key, row) for group, key, row, before, after in changes if before == OWED]
    print(f"ledger rows: {len(rows)}  fieldnames: {len(fieldnames or ())}")
    for group in GROUPS:
        keys = GROUPS[group]["keys"]
        pending = sum(1 for g, _k, _r in todo if g == group)
        print(f"  {group}: {len(keys)} keys, {pending} still owed")
    if args.check:
        print(f"would retire {len(todo)} rows (dry run, nothing written)")
        return 0

    for group, key, row in todo:
        row["verified_verdict"] = RETIRED
        row["verified_landing"] = f"（销号）{GROUPS[group]['reason']}"
    save_rows(fieldnames, rows)
    print(f"retired {len(todo)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
