"""The small, numeric-free contract returned by the Laya decision model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DECISION_FIELDS = (
    "turn_state",
    "action",
    "reply_intent",
    "reply_style",
    "reply_form",
    "segment_mode",
    "tool_need",
    "reason_codes",
)

TURN_STATES = frozenset({"complete", "unfinished", "uncertain"})
ACTIONS = frozenset({"reply", "wait", "silent", "interject", "clarify"})
REPLY_INTENTS = frozenset({"answer", "acknowledge", "ask", "comfort", "explain", "summarize"})
REPLY_STYLES = frozenset({"brief", "normal", "detailed", "serious", "playful"})
REPLY_FORMS = frozenset({"text", "voice", "text_voice", "image"})
SEGMENT_MODES = frozenset({"single", "natural", "keep_together"})
TOOL_NEEDS = frozenset({"none", "memory", "vision", "tts", "image", "external"})
DECISION_DEFAULTS = {
    "turn_state": "complete",
    "action": "reply",
    "reply_intent": "answer",
    "reply_style": "normal",
    "reply_form": "text",
    "segment_mode": "natural",
    "tool_need": "none",
}
CONFIGURABLE_DECISION_FIELDS = tuple(DECISION_DEFAULTS)


class DecisionContractError(ValueError):
    """The model returned data outside the versioned decision contract."""


@dataclass(frozen=True)
class LayaDecision:
    turn_state: str
    action: str
    reply_intent: str
    reply_style: str
    reply_form: str
    segment_mode: str
    tool_need: str
    reason_codes: tuple[str, ...]

    def document(self) -> dict[str, Any]:
        return {
            "turn_state": self.turn_state,
            "action": self.action,
            "reply_intent": self.reply_intent,
            "reply_style": self.reply_style,
            "reply_form": self.reply_form,
            "segment_mode": self.segment_mode,
            "tool_need": self.tool_need,
            "reason_codes": list(self.reason_codes),
        }


def _enum(data: dict[str, Any], key: str, values: frozenset[str]) -> str:
    value = data.get(key)
    if type(value) is not str or value not in values:
        raise DecisionContractError(f"invalid decision field: {key}")
    return value


def parse_decision(value: Any) -> LayaDecision:
    """Validate an exact object and reject all unapproved numeric metadata."""
    if type(value) is not dict or set(value) != set(DECISION_FIELDS):
        raise DecisionContractError("decision must contain the exact approved fields")
    reasons = value["reason_codes"]
    if type(reasons) is not list or len(reasons) > 8:
        raise DecisionContractError("reason_codes must be a short list")
    checked_reasons = []
    for reason in reasons:
        if type(reason) is not str or not reason or len(reason) > 64:
            raise DecisionContractError("reason_codes must contain short strings")
        checked_reasons.append(reason)
    return LayaDecision(
        turn_state=_enum(value, "turn_state", TURN_STATES),
        action=_enum(value, "action", ACTIONS),
        reply_intent=_enum(value, "reply_intent", REPLY_INTENTS),
        reply_style=_enum(value, "reply_style", REPLY_STYLES),
        reply_form=_enum(value, "reply_form", REPLY_FORMS),
        segment_mode=_enum(value, "segment_mode", SEGMENT_MODES),
        tool_need=_enum(value, "tool_need", TOOL_NEEDS),
        reason_codes=tuple(checked_reasons),
    )


def deterministic_skip_reason(facts: Any) -> str | None:
    """Return a rule-owned skip reason before any Laya request is made.

    Message ownership and addressing are platform facts.  They do not benefit
    from a semantic model, especially when an inbound event quotes the bot's
    own message.
    """
    if type(facts) is not dict:
        return "facts_invalid"
    if any(facts.get(name) is True for name in (
        "is_bot_message", "sender_is_bot", "robot_message", "is_robot_message",
        "quoted_bot_message", "quotes_bot_message", "has_bot_quote",
        "referenced_bot_message", "reply_to_bot_message",
    )):
        return "robot_message_reference"
    kind = facts.get("message_kind") or facts.get("event_kind")
    if kind in {"system", "notice", "command", "callback", "reaction"}:
        return "explicit_event_rule"
    if facts.get("rule_skip") is True:
        return "explicit_event_rule"
    return None
