"""Typed Laya questions and the bounded state sent to the decision model."""

from __future__ import annotations

import json
from typing import Any

from .contract import DECISION_FIELDS


DECISION_QUESTIONS = {
    "turn_state": {
        "type": "choice",
        "instructions": "结合当前用户消息判断这轮表达状态。",
        "criteria": {
            "complete": "用户当前想表达的事情已经说完整，可以回应。",
            "unfinished": "用户明显还在补充、列举或续说，适合先等后续消息。",
            "uncertain": "信息不足以判断用户是否说完，先谨慎等待或澄清。",
        },
    },
    "action": {
        "type": "choice",
        "instructions": "选择当前最合适的对话行为；这是语义分类，不是具体发送或等待参数。",
        "criteria": {
            "reply": "自然地回应用户当前表达。",
            "wait": "用户很可能还会继续表达，暂不回复当前消息。",
            "silent": "无需对当前消息发送可见回应。",
            "interject": "适合在群聊中简短加入当前话题。",
            "clarify": "关键意思不明确，先提出澄清问题。",
        },
    },
    "reply_intent": {
        "type": "choice",
        "instructions": "如果需要回应，选择主要沟通意图。",
        "criteria": {
            "answer": "回答问题或提供所需信息。",
            "acknowledge": "确认收到、接住情绪或简短回应。",
            "ask": "通过自然追问推动对话。",
            "comfort": "给予安慰、支持或陪伴。",
            "explain": "解释原因、背景或步骤。",
            "summarize": "归纳用户提供的信息或已有讨论。",
        },
    },
    "reply_style": {
        "type": "choice",
        "instructions": "选择合适的表达风格；不要判断回复长度数字。",
        "criteria": {
            "brief": "简洁但完整，适合轻量接话。",
            "normal": "自然、平衡的日常表达。",
            "detailed": "需要清楚说明多个要点或必要背景。",
            "serious": "认真、克制、准确。",
            "playful": "轻松活泼且符合关系和语境。",
        },
    },
    "reply_form": {
        "type": "choice",
        "instructions": "选择语义上适合的回复形式；可用能力仍由插件配置决定。",
        "criteria": {
            "text": "使用文字回复。",
            "voice": "语音更适合当前回应。",
            "text_voice": "文字与语音都适合。",
            "image": "图片表达更适合当前回应。",
            "none": "当前不发送可见回复。",
        },
    },
    "segment_mode": {
        "type": "choice",
        "instructions": "判断回复是否适合自然分成多个连续消息；不要决定具体段数。",
        "criteria": {
            "single": "内容紧凑，适合放在一条消息里。",
            "natural": "表达中有自然停顿或话题层次，可以顺势分段。",
            "keep_together": "步骤、引用、代码、列表或紧密语义应保持完整。",
        },
    },
    "tool_need": {
        "type": "choice",
        "instructions": "判断理解或回答可能需要哪类能力；这只是提示，不授权或触发工具。",
        "criteria": {
            "none": "仅凭当前对话即可回应。",
            "memory": "可能需要查阅已授权的对话记忆。",
            "vision": "可能需要理解用户提供的图片或视频。",
            "tts": "可能需要语音合成能力。",
            "image": "可能需要生成或编辑图片能力。",
            "external": "可能需要其他已注册能力。",
        },
    },
}


def _clean(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value[:12000]
    if isinstance(value, (list, tuple)):
        return [_clean(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, dict):
        return {str(key)[:80]: _clean(item, depth=depth + 1)
                for key, item in list(value.items())[:64]}
    return str(value)[:4000]


def facts_document(facts: dict[str, Any]) -> dict[str, Any]:
    return _clean(facts)


def build_state(facts: dict[str, Any]) -> str:
    """Laya accepts a textual state, so keep structured facts as readable JSON."""
    document = {"facts": facts_document(facts), "decision_fields": list(DECISION_FIELDS)}
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))
