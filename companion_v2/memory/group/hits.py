"""Bounded, deterministic group member safety signals.

Signals are evidence for later human/model review. They never grant or revoke
permissions and deliberately avoid retaining a member profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re

from companion_v2.execution.models import encode


RULE_IMPERSONATED_BOT_NAME = "impersonated_bot_name"
RULE_VERIFICATION_OR_PAYMENT = "verification_or_payment"
RULE_REPEATED_MESSAGE = "repeated_message"
RULE_MENTION_BOMBARDMENT = "mention_bombardment"


@dataclass(frozen=True)
class GroupSafetyPolicy:
    """One bounded policy object for deterministic evidence extraction."""

    max_text_chars: int = 65536
    repeated_message_window: int = 5
    repeated_message_threshold: int = 2
    mention_threshold: int = 4
    reflection_hit_limit: int = 128
    impersonation_prefixes: tuple[str, ...] = ("我是", "自称", "冒充", "假冒", "官方", "官方的", "本群", "本群的")
    impersonation_roles: tuple[str, ...] = ("机器人", "bot", "助手", "管理员", "客服")
    sensitive_terms: tuple[str, ...] = ("验证码", "校验码", "支付", "转账", "收款", "付款", "红包", "银行卡", "口令")
    mention_marker: str = "@"

    def __post_init__(self):
        for name in ("max_text_chars", "repeated_message_window", "repeated_message_threshold",
                     "mention_threshold", "reflection_hit_limit"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.repeated_message_threshold > self.repeated_message_window:
            raise ValueError("repeated message threshold exceeds its window")
        if not self.mention_marker:
            raise ValueError("mention marker is required")
        if not self.impersonation_prefixes or not self.impersonation_roles or not self.sensitive_terms:
            raise ValueError("safety policy requires nonempty rule vocabulary")

    @property
    def impersonation_pattern(self):
        prefixes = "|".join(re.escape(value) for value in self.impersonation_prefixes)
        roles = "|".join(re.escape(value) for value in self.impersonation_roles)
        return re.compile(r"(?:" + prefixes + r")\s*(?:" + roles + r")", re.I)

    @property
    def payment_pattern(self):
        return re.compile("|".join(re.escape(value) for value in self.sensitive_terms), re.I)


DEFAULT_GROUP_SAFETY_POLICY = GroupSafetyPolicy()


@dataclass(frozen=True)
class SafetyHit:
    hit_id: str
    owner_key: str
    member_id: str
    message_id: str | None
    rule_id: str
    direction: str
    severity: int
    evidence: dict
    occurred_at: datetime
    review_state: str = "pending"

    def row(self, *, created_at: datetime | None = None, review_json: str | None = None):
        return (self.hit_id, self.owner_key, self.member_id, self.message_id, self.rule_id,
                self.direction, self.severity, json.dumps(self.evidence, ensure_ascii=False, sort_keys=True),
                self.occurred_at.isoformat(), self.review_state, review_json,
                (created_at or self.occurred_at).isoformat())


def _hit(owner_key, member_id, message_id, rule_id, direction, severity, evidence, occurred_at):
    token = json.dumps([owner_key, member_id, message_id, rule_id, direction,
                        occurred_at.isoformat(), evidence], ensure_ascii=False, sort_keys=True)
    hit_id = "safety-" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    return SafetyHit(hit_id, member_id=member_id, owner_key=owner_key, message_id=message_id,
                     rule_id=rule_id, direction=direction, severity=severity,
                     evidence=evidence, occurred_at=occurred_at)


def evaluate_message(*, owner_key, member_id, message_id=None, message_text="", occurred_at,
                     direction="inbound", recent_messages=(), mention_count=None,
                     policy=DEFAULT_GROUP_SAFETY_POLICY):
    """Return stable hits for one bounded text and optional recent window."""
    if direction not in ("inbound", "outbound"):
        raise ValueError("direction must be inbound or outbound")
    if not isinstance(message_text, str):
        raise TypeError("message_text must be text")
    if not isinstance(policy, GroupSafetyPolicy):
        raise TypeError("policy must be a GroupSafetyPolicy")
    text = message_text[:policy.max_text_chars]
    hits = []
    if policy.impersonation_pattern.search(text):
        hits.append(_hit(owner_key, member_id, message_id, RULE_IMPERSONATED_BOT_NAME, direction, 2,
                         {"match": "bot_name_impersonation"}, occurred_at))
    if policy.payment_pattern.search(text):
        hits.append(_hit(owner_key, member_id, message_id, RULE_VERIFICATION_OR_PAYMENT, direction, 3,
                         {"match": "verification_or_payment"}, occurred_at))
    if recent_messages:
        normalized = [v for v in recent_messages if isinstance(v, str) and v]
        window = normalized[-policy.repeated_message_window:]
        repeat_count = sum(v == text for v in window)
        if repeat_count >= policy.repeated_message_threshold:
            hits.append(_hit(owner_key, member_id, message_id, RULE_REPEATED_MESSAGE, direction, 2,
                             {"window": min(len(normalized), policy.repeated_message_window), "repeat_count": repeat_count}, occurred_at))
    mentions = int(mention_count if mention_count is not None else text.count(policy.mention_marker))
    if mentions >= policy.mention_threshold:
        hits.append(_hit(owner_key, member_id, message_id, RULE_MENTION_BOMBARDMENT, direction, 2,
                         {"mention_count": mentions}, occurred_at))
    return tuple(hits)


def persist_hits(connection, hits, *, created_at=None):
    """Insert evidence idempotently inside the caller's transaction."""
    for hit in hits:
        connection.execute(
            """INSERT OR IGNORE INTO group_member_safety_hits
            (hit_id, owner_key, member_id, message_id, rule_id, direction, severity,
             evidence_json, occurred_at, review_state, review_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", hit.row(created_at=created_at))
