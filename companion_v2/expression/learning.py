"""Proposed language-style observations with explicit evidence references."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import unicodedata
from typing import Mapping


DIMENSIONS = frozenset({
    "sentence_rhythm",
    "emoji",
    "punctuation",
    "directness",
    "diction",
    "formatting",
    "other",
})
CHANNELS = ("private", "group", "proactive", "qzone", "tts")
RELATIONSHIP_STAGES = ("stranger", "familiar", "close", "any")
EMOTION_GATES = ("normal", "positive", "low", "guarded", "any")
INTENTS = frozenset({
    "acknowledgement", "question", "request", "help", "comfort", "play", "tease",
    "intimacy", "boundary", "emotion", "casual", "proactive", "any",
})
APPLICABILITY_FIELDS = frozenset({
    "channels", "relationship_stages", "emotion_gates", "intent", "keywords",
})
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 32
MAX_SIGNALS_PER_RUN = 12
MAX_SUMMARY_CHARS = 500
MAX_OBSERVATION_CHARS = 800
MAX_PROPOSAL_CHARS = 1200


def candidate_signature(dimension, observation, proposal, applicability=None):
    """Normalize formatting differences without collapsing distinct rule meaning."""
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    checked = normalize_applicability(applicability)
    return (normalize(dimension), normalize(observation), normalize(proposal),
            json.dumps(checked, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def normalize_applicability(raw=None, *, default_channels=None):
    """Return the bounded V1-compatible applicability contract for one rule."""
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping) or set(raw) - APPLICABILITY_FIELDS:
        raise ValueError("invalid_applicability")

    channels_default = CHANNELS if default_channels is None else tuple(default_channels)
    if (not channels_default or any(type(value) is not str or value not in CHANNELS
                                    for value in channels_default)):
        raise ValueError("invalid_applicability")

    def values(field, choices, fallback, *, maximum):
        value = raw.get(field)
        if value is None or value == []:
            return list(fallback)
        if (type(value) is not list or not value or len(value) > maximum
                or any(type(item) is not str or item not in choices for item in value)
                or len(set(value)) != len(value)
                or "any" in value and len(value) != 1):
            raise ValueError("invalid_applicability")
        return sorted(value, key=choices.index)

    channels = values("channels", CHANNELS, channels_default, maximum=len(CHANNELS))
    stages = values("relationship_stages", RELATIONSHIP_STAGES, ("any",), maximum=len(RELATIONSHIP_STAGES))
    emotions = values("emotion_gates", EMOTION_GATES, ("any",), maximum=len(EMOTION_GATES))
    intent = raw.get("intent", "any")
    if type(intent) is not str or intent not in INTENTS:
        raise ValueError("invalid_applicability")

    keywords = raw.get("keywords", [])
    if (type(keywords) is not list or len(keywords) > MAX_KEYWORDS
            or any(type(value) is not str for value in keywords)):
        raise ValueError("invalid_applicability")
    accepted, seen = [], set()
    unsafe_markers = ("ignore previous", "system prompt", "developer message", "忽略之前", "系统提示词", "调用工具")
    for value in keywords:
        keyword = " ".join(unicodedata.normalize("NFKC", value).split()).strip()
        key = keyword.casefold()
        if (not keyword or len(keyword) > MAX_KEYWORD_CHARS or key in seen
                or any(marker in key for marker in unsafe_markers)):
            raise ValueError("invalid_applicability")
        seen.add(key)
        accepted.append(keyword)
    return {"channels": channels, "relationship_stages": stages, "emotion_gates": emotions,
            "intent": intent, "keywords": accepted}


def applicability_matches_channel(applicability, channel):
    if type(channel) is not str or channel not in CHANNELS:
        return False
    try:
        checked = normalize_applicability(applicability)
    except (TypeError, ValueError):
        return False
    return channel in checked["channels"]


def laya_intent_matches(applicability, decision):
    """Use only explicit Laya outcomes; unknown outcomes do not satisfy narrow rules."""
    try:
        checked = normalize_applicability(applicability)
    except (TypeError, ValueError):
        return False
    target = checked["intent"]
    if target == "any":
        return True
    if not isinstance(decision, Mapping):
        return False
    reply_intent = decision.get("reply_intent")
    reply_style = decision.get("reply_style")
    compatible = {
        "answer": {"question", "request", "help"},
        "acknowledge": {"acknowledgement"},
        "ask": {"question"},
        "comfort": {"comfort", "emotion"},
        "explain": {"help"},
        "summarize": set(),
    }.get(reply_intent, set())
    if reply_style == "playful":
        compatible = compatible | {"play", "tease", "intimacy", "casual"}
    return target in compatible

INSTRUCTION = (
    "只观察表达形式，例如句长、标点、常用措辞、直接程度和排版。"
    "不要从少量样本推断身份、性格、情绪、健康、关系或稳定偏好。"
    "区分明确反馈与偶然写法；证据不足时留空，不要把一次表达概括成长期习惯。"
    "每项候选都引用输入中给出的 evidence_handle。这里只提出供后续审核的候选，不宣布已学习或已保存。"
    "为每条候选填写 applicability：channels 从 private/group/proactive/qzone/tts 中选择，"
    "relationship_stages 从 stranger/familiar/close/any 中选择，emotion_gates 从 normal/positive/low/guarded/any 中选择，"
    "intent 从 acknowledgement/question/request/help/comfort/play/tease/intimacy/boundary/emotion/casual/proactive/any 中选择，"
    "keywords 最多 8 个简短情境词。来源频道必须包含在 channels 中；其他条件证据不足时填写 any 或空关键词，不能猜测身份、关系阶段或情绪。"
    "这些字段表达使用条件，不是事实声明；条件缺失或不确定时不要把规则当作匹配。"
    "只输出符合给定 JSON Schema 的 JSON，不输出推理过程。"
)

MODE_INSTRUCTIONS = {
    "light": "轻量学习：只提炼跨情境通用的句长、节奏、标点和排版习惯，最多提出3条。不要提取场景短语或口头禅。",
    "balanced": "均衡学习：兼顾稳定语法习惯和有重复证据的情境表达，最多提出6条；保留角色自己的表达，不模仿用户身份。",
    "aggressive": "深入学习：可提出最多12条细分的情境表达和句法模板，明确使用条件；不因强度提高而降低证据要求。",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "maxLength": MAX_SUMMARY_CHARS},
        "signals": {
            "type": "array",
            "maxItems": MAX_SIGNALS_PER_RUN,
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": sorted(DIMENSIONS)},
                    "observation": {"type": "string", "maxLength": MAX_OBSERVATION_CHARS},
                    "proposal": {"type": "string", "maxLength": MAX_PROPOSAL_CHARS},
                    "applicability": {
                        "type": "object",
                        "properties": {
                            "channels": {"type": "array", "items": {"type": "string", "enum": list(CHANNELS)},
                                         "minItems": 1, "maxItems": len(CHANNELS)},
                            "relationship_stages": {"type": "array", "items": {"type": "string", "enum": list(RELATIONSHIP_STAGES)},
                                                    "minItems": 1, "maxItems": len(RELATIONSHIP_STAGES)},
                            "emotion_gates": {"type": "array", "items": {"type": "string", "enum": list(EMOTION_GATES)},
                                              "minItems": 1, "maxItems": len(EMOTION_GATES)},
                            "intent": {"type": "string", "enum": sorted(INTENTS)},
                            "keywords": {"type": "array", "maxItems": MAX_KEYWORDS,
                                         "items": {"type": "string", "maxLength": MAX_KEYWORD_CHARS}},
                        },
                        "required": sorted(APPLICABILITY_FIELDS),
                        "additionalProperties": False,
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_handles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["dimension", "observation", "proposal", "applicability", "confidence", "evidence_handles"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "signals"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class StyleSignal:
    dimension: str
    observation: str
    proposal: str
    applicability: dict
    confidence: float
    evidence_handles: tuple[str, ...]


@dataclass(frozen=True)
class ExpressionLearningOutput:
    summary: str
    signals: tuple[StyleSignal, ...]


def parse_output(raw: object, *, allowed_evidence: set[str] | frozenset[str], default_channels=None) -> ExpressionLearningOutput:
    """Validate a model-authored candidate; never persists or activates the result."""
    if type(raw) is str:
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("invalid_json") from error
    if not isinstance(raw, Mapping) or set(raw) != {"summary", "signals"}:
        raise ValueError("invalid_shape")
    summary, signals = raw["summary"], raw["signals"]
    if (type(summary) is not str or len(summary) > MAX_SUMMARY_CHARS
            or not isinstance(signals, list) or len(signals) > MAX_SIGNALS_PER_RUN):
        raise ValueError("invalid_shape")
    accepted = []
    for item in signals:
        required = {"dimension", "observation", "proposal", "confidence", "evidence_handles"}
        if not isinstance(item, Mapping) or set(item) not in (required, required | {"applicability"}):
            raise ValueError("invalid_signal")
        dimension = item["dimension"]
        observation, proposal = item["observation"], item["proposal"]
        confidence, references = item["confidence"], item["evidence_handles"]
        if (dimension not in DIMENSIONS or type(observation) is not str or not observation.strip()
                or len(observation) > MAX_OBSERVATION_CHARS):
            raise ValueError("invalid_signal")
        if type(proposal) is not str or not proposal.strip() or len(proposal) > MAX_PROPOSAL_CHARS:
            raise ValueError("invalid_signal")
        try:
            applicability = normalize_applicability(item.get("applicability"), default_channels=default_channels)
        except (TypeError, ValueError):
            raise ValueError("invalid_applicability") from None
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid_confidence")
        if (not isinstance(references, list) or not references or
                any(type(reference) is not str or reference not in allowed_evidence for reference in references) or
                len(set(references)) != len(references)):
            raise ValueError("invalid_evidence")
        accepted.append(StyleSignal(dimension, observation.strip(), proposal.strip(), applicability, float(confidence),
                                    tuple(references)))
    return ExpressionLearningOutput(summary.strip(), tuple(accepted))
