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
MAX_SIGNALS_PER_RUN = 12
MAX_SUMMARY_CHARS = 500
MAX_OBSERVATION_CHARS = 800
MAX_PROPOSAL_CHARS = 1200


def candidate_signature(dimension, observation, proposal):
    """Normalize formatting differences without collapsing distinct rule meaning."""
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return normalize(dimension), normalize(observation), normalize(proposal)

INSTRUCTION = (
    "只观察表达形式，例如句长、标点、常用措辞、直接程度和排版。"
    "不要从少量样本推断身份、性格、情绪、健康、关系或稳定偏好。"
    "区分明确反馈与偶然写法；证据不足时留空，不要把一次表达概括成长期习惯。"
    "每项候选都引用输入中给出的 evidence_handle。这里只提出供后续审核的候选，不宣布已学习或已保存。"
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
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_handles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["dimension", "observation", "proposal", "confidence", "evidence_handles"],
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
    confidence: float
    evidence_handles: tuple[str, ...]


@dataclass(frozen=True)
class ExpressionLearningOutput:
    summary: str
    signals: tuple[StyleSignal, ...]


def parse_output(raw: object, *, allowed_evidence: set[str] | frozenset[str]) -> ExpressionLearningOutput:
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
        if not isinstance(item, Mapping) or set(item) != {
            "dimension", "observation", "proposal", "confidence", "evidence_handles"
        }:
            raise ValueError("invalid_signal")
        dimension = item["dimension"]
        observation, proposal = item["observation"], item["proposal"]
        confidence, references = item["confidence"], item["evidence_handles"]
        if (dimension not in DIMENSIONS or type(observation) is not str or not observation.strip()
                or len(observation) > MAX_OBSERVATION_CHARS):
            raise ValueError("invalid_signal")
        if type(proposal) is not str or not proposal.strip() or len(proposal) > MAX_PROPOSAL_CHARS:
            raise ValueError("invalid_signal")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("invalid_confidence")
        if (not isinstance(references, list) or not references or
                any(type(reference) is not str or reference not in allowed_evidence for reference in references) or
                len(set(references)) != len(references)):
            raise ValueError("invalid_evidence")
        accepted.append(StyleSignal(dimension, observation.strip(), proposal.strip(), float(confidence),
                                    tuple(references)))
    return ExpressionLearningOutput(summary.strip(), tuple(accepted))
