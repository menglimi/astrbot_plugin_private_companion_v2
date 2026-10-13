"""Privacy-preserving expression rule packs compatible with V1 exports."""

from __future__ import annotations

import math

from .learning import (APPLICABILITY_FIELDS, DIMENSIONS, MAX_OBSERVATION_CHARS,
                       MAX_PROPOSAL_CHARS, candidate_signature, normalize_applicability)


PACK_SCHEMA = "private-companion-expression-pack"
PACK_VERSION = 1
MAX_IMPORT_SIGNALS = 200
DIMENSION_LABELS = {
    "sentence_rhythm": "句读节奏", "emoji": "表情符号", "punctuation": "标点",
    "directness": "直接程度", "diction": "措辞", "formatting": "排版", "other": "其他",
}
UNSAFE_MARKERS = (
    "ignore previous", "ignore all previous", "system prompt", "developer message",
    "tool_calls", "<system", "</system", "忽略之前", "忽略以上", "无视之前",
    "忽略所有前面的指令", "系统提示词", "开发者消息", "调用工具",
)


def _line(value, maximum, field):
    if type(value) is not str:
        raise ValueError("invalid_" + field)
    value = " ".join(value.split()).strip()
    if not value or len(value) > maximum:
        raise ValueError("invalid_" + field)
    if any(marker in value.casefold() for marker in UNSAFE_MARKERS):
        raise ValueError("unsafe_rule")
    return value


def _dimension(rule):
    explicit = rule.get("dimension")
    if type(explicit) is str and explicit in DIMENSIONS:
        return explicit
    signals = rule.get("signals")
    if isinstance(signals, list):
        match = next((item for item in signals if type(item) is str and item in DIMENSIONS), None)
        if match is not None:
            return match
    kind = rule.get("kind", rule.get("type"))
    if kind == "grammar":
        return "sentence_rhythm"
    if kind == "style":
        return "diction"
    raise ValueError("invalid_dimension")


def normalize_pack(raw):
    """Accept V1 share packs, but retain only bounded, abstract expression fields."""
    if (type(raw) is not dict or raw.get("schema") != PACK_SCHEMA
            or type(raw.get("version")) is not int or raw["version"] != PACK_VERSION):
        raise ValueError("unsupported_pack")
    groups = raw.get("rule_groups")
    if type(groups) is not list or not groups or len(groups) > MAX_IMPORT_SIGNALS:
        raise ValueError("invalid_pack")
    title = "表达分享包"
    if type(raw.get("title")) is str and raw["title"].strip():
        title = _line(raw["title"], 80, "title")

    signals, rejected = [], []
    seen = set()
    for group_index, group in enumerate(groups):
        if type(group) is not dict or type(group.get("rules")) is not list:
            rejected.append({"group_index": group_index, "rule_index": None, "reason": "invalid_group"})
            continue
        if not group["rules"]:
            rejected.append({"group_index": group_index, "rule_index": None, "reason": "empty_group"})
            continue
        for rule_index, rule in enumerate(group["rules"]):
            if type(rule) is not dict:
                rejected.append({"group_index": group_index, "rule_index": rule_index,
                                 "reason": "invalid_rule"})
                continue
            try:
                dimension = _dimension(rule)
                observation = _line(rule.get("observation") or rule.get("situation") or rule.get("label"),
                                    MAX_OBSERVATION_CHARS, "observation")
                proposal = rule.get("proposal")
                if type(proposal) is not str or not proposal.strip():
                    instruction = rule.get("instruction")
                    pattern = rule.get("pattern") or rule.get("style")
                    if type(instruction) is str and type(pattern) is str and instruction.strip() != pattern.strip():
                        proposal = instruction.strip() + "（句式参考：" + pattern.strip() + "）"
                    else:
                        proposal = instruction if type(instruction) is str and instruction.strip() else pattern
                proposal = _line(proposal, MAX_PROPOSAL_CHARS, "proposal")
                confidence = rule.get("confidence", 0.5)
                if (type(confidence) not in (int, float) or not math.isfinite(confidence)
                        or not 0 <= confidence <= 1):
                    raise ValueError("invalid_confidence")
                supplied_applicability = rule.get("applicability")
                if supplied_applicability is None:
                    supplied_applicability = {field: rule[field] for field in APPLICABILITY_FIELDS if field in rule}
                    if "keywords" not in supplied_applicability and type(rule.get("tags")) is list:
                        supplied_applicability["keywords"] = rule["tags"]
                applicability = normalize_applicability(supplied_applicability)
            except (TypeError, ValueError) as error:
                rejected.append({"group_index": group_index, "rule_index": rule_index,
                                 "reason": str(error) or "invalid_rule"})
                continue
            signature = candidate_signature(dimension, observation, proposal, applicability)
            if signature in seen:
                rejected.append({"group_index": group_index, "rule_index": rule_index,
                                 "reason": "duplicate_in_pack"})
                continue
            seen.add(signature)
            signals.append({"dimension": dimension, "observation": observation,
                            "proposal": proposal, "applicability": applicability,
                            "confidence": float(confidence)})
            if len(signals) > MAX_IMPORT_SIGNALS:
                raise ValueError("too_many_signals")
    if not signals:
        raise ValueError("empty_pack")
    return {"schema": PACK_SCHEMA, "version": PACK_VERSION, "title": title,
            "group_count": len(groups), "signals": signals, "rejected": rejected}


def build_pack(signals, *, title="陪伴表达分享", exported_at=""):
    """Export V2 signals in the V1 rule-group envelope without personal evidence."""
    groups = []
    for index, signal in enumerate(signals, 1):
        dimension = signal["dimension"]
        proposal = signal["proposal"]
        applicability = normalize_applicability(signal.get("applicability"))
        kind = "grammar" if dimension == "sentence_rhythm" else "style"
        groups.append({"id": f"group-{index:03d}", "label": signal["observation"], "rules": [{
            "kind": kind,
            "dimension": dimension,
            "label": DIMENSION_LABELS.get(dimension, "表达形式"),
            "situation": signal["observation"],
            "pattern": proposal,
            "instruction": proposal,
            "signals": [dimension],
            **applicability,
        }]})
    return {"schema": PACK_SCHEMA, "version": PACK_VERSION, "title": title,
            "exported_at": exported_at,
            "privacy": "仅包含抽象表达规则，不包含对象、原始消息、证据或使用记录。",
            "rule_groups": groups}
