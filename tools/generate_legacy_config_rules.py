"""Generate the shipped V1-to-V2 configuration rule table from the audit ledger."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion_v2.storage.semantic import DEFAULTS as SEMANTIC_DEFAULTS
from companion_v2.storage.semantic import INTEGER_LIMITS as SEMANTIC_INTEGER_LIMITS
from companion_v2.storage.semantic import PROBABILITY_FIELDS as SEMANTIC_PROBABILITY_FIELDS
from companion_v2.storage.semantic import SETTING_OPTIONS as SEMANTIC_OPTIONS

SOURCE = ROOT / "docs" / "V1_V2_CONFIG_RESOLVED_20260928.csv"
DESTINATION = ROOT / "companion_v2" / "legacy" / "configuration_rules.json"
MIGRATABLE_VERDICTS = {"already-in-v2", "renamed-equivalent"}
SUPPORTED_CONFIDENCE = {"high", "medium"}
PLUGIN_CONVERSIONS = {
    "auto_voice_config.auto_voice_enabled": "bool_to_voice_trigger",
    "auto_voice_config.auto_voice_full_conversion_enabled": "bool_to_voice_delivery",
    "voice_action_config.tts_conversion_scope": "voice_delivery_scope",
    "legacy_compat_config.maintenance_token_soft_limit": "numeric_string_integer",
    "weather_config.weather_source": "weather_provider",
}
PLUGIN_REVIEWED_OWED = {
    # V2 now exposes this bounded intake field; keep its source medium-confidence
    # because V1 counts messages while V2 counts forward-tree nodes.
    "forward_message_config.forward_message_max_messages": "integer",
}
RULE_EXCLUSIONS = {
    "basic_config.owner_exclusive_proactive_limit":
        "V2 已取消跨私聊窗口的关系级额度；每日决策调用与实际联系上限由各私聊窗口分别配置，不自动迁移旧关系额度。",
    "voice_action_config.tts_message_scope":
        "旧版该枚举控制主动正文是否进入回复 TTS 链；V2 主动语音使用独立授权策略，不能据此改写 proactive.contact.voice_action_enabled。",
    "emotion_relationship_config.enable_smart_silence":
        "V2 没有独立的智能沉默开关；沉默由主动联系的单次生成决策及策略共同决定，不能把旧开关误写成置信度阈值。",
}
REGISTRY_SPECIAL_SOURCES = frozenset({
    "legacy_compat_config.segmented_proactive_image_strategy",
    "legacy_compat_config.segmented_proactive_voice_strategy",
    "legacy_compat_config.segmented_proactive_at_strategy",
})
REGISTRY_TRANSFORMS = {
    "humanized_state_config.inject_passive_states": "bool_to_expression_intensity",
    "humanized_state_config.enable_advanced_cycle_strategy": "bool_to_cycle_mode",
}
PLUGIN_TEXT_OVERRIDES = {
    "model_token_limit_overrides",
    "model_fallback_overrides",
    "task_prompt_overrides",
}
SEMANTIC_TRANSFORMS = {
    "relay_bridge_config.group_slang_summary_minutes": "minutes_to_seconds",
    "experimental_motivation_config.reaction_expression_embedding_timeout_ms": "milliseconds_to_seconds",
}
REGISTRY_LIST_FORMATS = {
    "conversation.presentation.recall_forbidden_words": "json",
    "conversation.presentation.group_wakeup_direct_words": "json",
    "conversation.presentation.group_wakeup_owner_direct_words": "json",
    "conversation.presentation.group_wakeup_context_words": "json",
    "conversation.presentation.group_wakeup_interest_keywords": "json",
    "knowledge.source_ids": "newline",
    "conversation.presentation.component_order": "json",
    "conversation.presentation.content_cleanup_words": "json",
    "conversation.presentation.content_replacements": "json",
}


def _plugin_contract(schema, target):
    section, _, field = target.partition(".")
    group = schema.get(section)
    if not isinstance(group, dict) or group.get("type") != "object":
        return None
    fields = group.get("items")
    contract = fields.get(field) if isinstance(fields, dict) else None
    if not isinstance(contract, dict) or contract.get("type") not in {"bool", "int", "float", "string", "text", "list"}:
        return None
    return contract


def _plugin_transform(source, source_type, target, contract):
    explicit = PLUGIN_CONVERSIONS.get(source)
    if explicit:
        return explicit
    target_type = contract["type"]
    if source_type == "bool" and target_type == "bool":
        return "identity"
    if source_type in {"int", "integer", "float"} and target_type in {"int", "float"}:
        if target_type == "float" and "probability" in target.rsplit(".", 1)[-1]:
            return "percent" if source_type in {"int", "integer"} else "identity"
        if target_type == "int" and source_type == "float":
            return "integer"
        return "identity"
    if source_type in {"string", "text"} and target_type in {"string", "text"}:
        if source in PLUGIN_TEXT_OVERRIDES:
            return None
        return "identity"
    if source_type == "list" and target_type == "list":
        return "identity"
    if source_type == "list" and target_type == "text":
        return "json_list"
    return None


def generate() -> int:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        rules = []
        plugin_rules = []
        exclusions = []
        semantic_rules = []
        seen = set()
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        for row in rows:
            source = row.get("v1_key", "").strip()
            if source in RULE_EXCLUSIONS:
                exclusions.append({"source": source, "reason": RULE_EXCLUSIONS[source]})
                continue
            reopened = source in PLUGIN_REVIEWED_OWED
            if ((row.get("verified_verdict") not in MIGRATABLE_VERDICTS and not reopened)
                    or row.get("verified_confidence") not in SUPPORTED_CONFIDENCE):
                continue
            target = row.get("resolved_target", "").strip()
            source_type = row.get("v1_type", "").strip()
            if not source or not target or not source_type:
                continue
            if source in seen:
                raise ValueError(f"duplicate V1 configuration key: {source}")
            if "." not in target:
                raise ValueError(f"configuration target must be group-qualified: {source} -> {target}")
            if row.get("resolved_kind") == "registry" and "." not in source:
                raise ValueError(f"registry source must be group-qualified: {source} -> {target}")
            seen.add(source)
            rule = {
                "source": source,
                "source_type": source_type,
                "target": target,
                "confidence": row["verified_confidence"],
            }
            if row.get("resolved_kind") == "semantic-config":
                contract = _semantic_contract(target)
                if contract is None:
                    raise ValueError(f"semantic target is not a registered setting: {source} -> {target}")
                rule["transform"] = SEMANTIC_TRANSFORMS.get(source, "identity")
                rule["contract"] = contract
                semantic_rules.append(rule)
                continue
            if row.get("resolved_kind") == "registry":
                if source in REGISTRY_SPECIAL_SOURCES:
                    continue
                if source in REGISTRY_TRANSFORMS:
                    rule["transform"] = REGISTRY_TRANSFORMS[source]
                if source_type.lower() == "list":
                    try:
                        rule["list_format"] = REGISTRY_LIST_FORMATS[target]
                    except KeyError as error:
                        raise ValueError(f"list serialization is not reviewed: {target}") from error
                rules.append(rule)
                continue
            if row.get("resolved_kind") != "plugin-config":
                continue
            contract = _plugin_contract(schema, target)
            transform = (PLUGIN_REVIEWED_OWED.get(source) or
                         _plugin_transform(source, source_type.lower(), target, contract or {})) if contract else None
            if transform is None:
                continue
            if source in PLUGIN_REVIEWED_OWED:
                rule["confidence"] = "medium"
            rule["transform"] = transform
            rule["contract"] = {
                key: contract[key] for key in ("type", "default", "options", "minimum", "maximum", "min", "max", "items")
                if key in contract
            }
            plugin_rules.append(rule)

    audit_sources = []
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            source = row.get("v1_key", "").strip()
            if not source:
                continue
            landing = row.get("verified_landing", "").strip()
            if source in RULE_EXCLUSIONS:
                landing = RULE_EXCLUSIONS[source]
            if not landing:
                verdict = row.get("verified_verdict", "")
                landing = {
                    "owed": "该配置仍在迁移欠账中，目前没有经过核实的自动转换规则。",
                    "implemented-elsewhere": "V2 已由其他功能承接，不需要复制成同名配置。",
                    "not-migrated-by-design": "该设置按 V1/V2 功能审计结论保留，不自动迁移。",
                    "not-applicable": "该设置不适用于当前迁移目标。",
                }.get(verdict, "没有经过核实的 V2 配置落点，暂不自动迁移。")
            target = row.get("resolved_target", "").strip()
            verdict = row.get("verified_verdict", "").strip()
            if source in RULE_EXCLUSIONS:
                target = ""
                verdict = "not-migrated-by-design"
            audit_sources.append({
                "source": source,
                "source_type": row.get("v1_type", "").strip(),
                "resolved_kind": row.get("resolved_kind", "").strip(),
                "target": target,
                "verdict": verdict,
                "confidence": row.get("verified_confidence", "").strip(),
                "summary": landing[:600],
            })

    document = {
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "supported_v1_version": "6.6.2",
        "rules": rules,
        "plugin_rules": plugin_rules,
        "exclusions": exclusions,
        "semantic_rules": semantic_rules,
        "audit_sources": audit_sources,
    }
    with DESTINATION.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return len(rules) + len(plugin_rules) + len(semantic_rules)


def _semantic_contract(target):
    group, _, name = target.partition(".")
    if group != "semantic" or name not in SEMANTIC_DEFAULTS:
        return None
    default = SEMANTIC_DEFAULTS[name]
    value_type = "bool" if type(default) is bool else "int" if type(default) is int else \
        "float" if type(default) is float else "string"
    contract = {"type": value_type, "default": default}
    if name in SEMANTIC_INTEGER_LIMITS:
        contract["minimum"], contract["maximum"] = SEMANTIC_INTEGER_LIMITS[name]
    if name in SEMANTIC_PROBABILITY_FIELDS:
        contract["minimum"], contract["maximum"] = 0, 1
    if name in SEMANTIC_OPTIONS:
        contract["options"] = list(SEMANTIC_OPTIONS[name])
    if value_type == "string":
        contract["maximum_chars"] = 200
    return contract


if __name__ == "__main__":
    print(f"generated {generate()} rules in {DESTINATION.relative_to(ROOT)}")
