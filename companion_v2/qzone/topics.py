"""Topic and scene contracts for public QQ Zone posts.

The model chooses a topic from this closed vocabulary after reading the
provided source material.  This module deliberately contains no keyword
matching: sources may come from a conversation, an external article, a
calendar item, a role activity or a user's own direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from typing import Mapping


class QzoneTopic(str, Enum):
    LIFE_DOCUMENTARY = "life_documentary"
    EMOTION_REFLECTION = "emotion_reflection"
    INTEREST_HOBBY = "interest_hobby"
    OPINION_HOT = "opinion_hot"
    HELP_INTERACTION = "help_interaction"
    RITUAL_MEMORY = "ritual_memory"
    MEANINGLESS_STATUS = "meaningless_status"


class QzoneScene(str, Enum):
    CONVERSATION = "conversation"
    EXTERNAL_MATERIAL = "external_material"
    AGENDA = "agenda"
    ROLE_ACTIVITY = "role_activity"
    RELATIONSHIP = "relationship"
    DATE_MARKER = "date_marker"
    FREE_EXPRESSION = "free_expression"


@dataclass(frozen=True)
class TopicSpec:
    topic: QzoneTopic
    label: str
    guidance: str
    scenes: tuple[QzoneScene, ...]


TOPIC_SPECS: tuple[TopicSpec, ...] = (
    TopicSpec(QzoneTopic.LIFE_DOCUMENTARY, "生活纪实类",
              "记录有明确来源的日常经历、观察或进展；不能把计划、想象或材料推断写成已经发生。",
              (QzoneScene.CONVERSATION, QzoneScene.ROLE_ACTIVITY, QzoneScene.DATE_MARKER)),
    TopicSpec(QzoneTopic.EMOTION_REFLECTION, "情绪感悟类",
              "表达经过整理的感受、体会或反思；去掉私密细节，不替他人诊断情绪，不把猜测写成事实。",
              (QzoneScene.CONVERSATION, QzoneScene.RELATIONSHIP, QzoneScene.FREE_EXPRESSION)),
    TopicSpec(QzoneTopic.INTEREST_HOBBY, "兴趣爱好类",
              "围绕兴趣、作品、阅读、练习或探索形成自然分享；来源不足时保持主观表述，不冒充完成过的活动。",
              (QzoneScene.CONVERSATION, QzoneScene.EXTERNAL_MATERIAL, QzoneScene.ROLE_ACTIVITY)),
    TopicSpec(QzoneTopic.OPINION_HOT, "观点/热点类",
              "对有出处的外部材料或公共议题作有限评论；保留标题、来源、日期和链接，不声称亲历或完整核实。",
              (QzoneScene.EXTERNAL_MATERIAL, QzoneScene.CONVERSATION)),
    TopicSpec(QzoneTopic.HELP_INTERACTION, "求助/互动类",
              "提出清晰、可回应的问题或邀请互动；不泄露不必要的对话内容，不把未确认的回复当成结果。",
              (QzoneScene.CONVERSATION, QzoneScene.AGENDA, QzoneScene.EXTERNAL_MATERIAL,
               QzoneScene.RELATIONSHIP)),
    TopicSpec(QzoneTopic.RITUAL_MEMORY, "仪式纪念类",
              "纪念有明确日期、关系或来源支撑的节点；不擅自为他人赋予个人意义，不编造共同经历。",
              (QzoneScene.DATE_MARKER, QzoneScene.RELATIONSHIP, QzoneScene.CONVERSATION)),
    TopicSpec(QzoneTopic.MEANINGLESS_STATUS, "无意义水动态",
              "允许轻量、低信息量的状态表达；不为凑数量虚构事实，也不借此绕过其他主题的发布条件。",
              (QzoneScene.FREE_EXPRESSION, QzoneScene.CONVERSATION, QzoneScene.ROLE_ACTIVITY)),
)

TOPICS: Mapping[str, TopicSpec] = {item.topic.value: item for item in TOPIC_SPECS}
SCENES: Mapping[str, str] = {
    QzoneScene.CONVERSATION.value: "对话",
    QzoneScene.EXTERNAL_MATERIAL.value: "外部资讯或材料",
    QzoneScene.AGENDA.value: "日程与待办",
    QzoneScene.ROLE_ACTIVITY.value: "角色活动与记录",
    QzoneScene.RELATIONSHIP.value: "关系与互动",
    QzoneScene.DATE_MARKER.value: "日期与纪念节点",
    QzoneScene.FREE_EXPRESSION.value: "自由表达",
}


@dataclass(frozen=True)
class AgendaProposal:
    """A pending agenda change suggestion carried with a public interaction.

    The proposal is evidence for a later, explicit agenda operation.  It is
    intentionally not an agenda mutation and therefore contains the observed
    object revision that a future confirmation must re-check.
    """

    agenda_id: str
    expected_revision: int
    intent: str
    source_refs: tuple[str, ...] = ()
    status: str = "pending_confirmation"

    def document(self) -> dict:
        return {
            "agenda_id": self.agenda_id,
            "expected_revision": self.expected_revision,
            "intent": self.intent,
            "source_refs": list(self.source_refs),
            "status": self.status,
        }


@dataclass(frozen=True)
class TopicDecision:
    """A model decision before a public body is accepted for publication."""

    topic: QzoneTopic
    scene: QzoneScene
    confidence: float
    should_publish: bool
    reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    agenda_proposal: AgendaProposal | None = None

    def document(self) -> dict:
        return {
            "topic": self.topic.value,
            "scene": self.scene.value,
            "confidence": self.confidence,
            "should_publish": self.should_publish,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "agenda_proposal": self.agenda_proposal.document() if self.agenda_proposal else None,
        }


def topic_spec(value: str | QzoneTopic) -> TopicSpec:
    key = value.value if isinstance(value, QzoneTopic) else value
    if not isinstance(key, str) or key not in TOPICS:
        raise ValueError("unknown QQ Zone topic")
    return TOPICS[key]


def normalize_topic(value: object) -> QzoneTopic:
    if isinstance(value, QzoneTopic):
        return value
    try:
        return QzoneTopic(value)
    except (TypeError, ValueError) as error:
        raise ValueError("unknown QQ Zone topic") from error


def normalize_scene(value: object) -> QzoneScene:
    if isinstance(value, QzoneScene):
        return value
    try:
        return QzoneScene(value)
    except (TypeError, ValueError) as error:
        raise ValueError("unknown QQ Zone scene") from error


def validate_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("topic confidence must be a number")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("topic confidence must be between 0 and 1")
    return confidence


def _agenda_proposal(value: object, *, topic: QzoneTopic, scene: QzoneScene) -> AgendaProposal | None:
    """Validate a pending agenda proposal without touching agenda storage."""
    if value is None:
        return None
    if topic is not QzoneTopic.HELP_INTERACTION or scene is not QzoneScene.AGENDA:
        raise ValueError("agenda proposal is only valid for agenda help interactions")
    if not isinstance(value, Mapping):
        raise ValueError("agenda proposal must be an object")
    allowed = {"agenda_id", "agenda_ref", "expected_revision", "intent", "source_refs", "status"}
    if set(value) - allowed:
        raise ValueError("agenda proposal has an unsupported field")
    agenda_id = value.get("agenda_id", value.get("agenda_ref"))
    if type(agenda_id) is not str or not agenda_id.strip() or len(agenda_id.strip()) > 160:
        raise ValueError("agenda proposal needs an agenda identifier")
    revision = value.get("expected_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("agenda proposal revision is invalid")
    intent = value.get("intent")
    if type(intent) is not str or not intent.strip() or len(intent.strip()) > 1000:
        raise ValueError("agenda proposal intent is invalid")
    refs = value.get("source_refs", ())
    if not isinstance(refs, (list, tuple)) or len(refs) > 32:
        raise ValueError("agenda proposal source_refs is invalid")
    source_refs = tuple(str(ref).strip() for ref in refs)
    if any(not ref or len(ref) > 256 for ref in source_refs):
        raise ValueError("agenda proposal source_refs is invalid")
    status = value.get("status", "pending_confirmation")
    if status != "pending_confirmation":
        raise ValueError("agenda proposal must remain pending confirmation")
    return AgendaProposal(agenda_id.strip(), revision, intent.strip(), source_refs, status)


def allowed_scenes(value: object) -> tuple[QzoneScene, ...]:
    """Parse a comma-separated or JSON-list configuration value."""
    if isinstance(value, (tuple, list)):
        raw = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = text.split(",")
        else:
            raw = parsed if isinstance(parsed, list) else text.split(",")
    else:
        return ()
    result = []
    for item in raw:
        scene = normalize_scene(str(item).strip())
        if scene not in result:
            result.append(scene)
    return tuple(result)


def parse_decision(value: str | bytes | Mapping[str, object]) -> TopicDecision:
    """Parse the strict JSON result emitted by the topic prompt."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            data = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("topic decision must be a JSON object") from error
    else:
        data = value
    if not isinstance(data, dict):
        raise ValueError("topic decision must be a JSON object")
    allowed = {"topic", "scene", "confidence", "should_publish", "reason", "evidence_refs", "agenda_proposal"}
    if set(data) - allowed or "topic" not in data or "scene" not in data or "confidence" not in data:
        raise ValueError("topic decision has an unsupported or missing field")
    topic = normalize_topic(data["topic"])
    scene = normalize_scene(data["scene"])
    if scene not in topic_spec(topic).scenes:
        raise ValueError("topic and scene are not compatible")
    confidence = validate_confidence(data["confidence"])
    should_publish = data.get("should_publish", False)
    if type(should_publish) is not bool:
        raise ValueError("should_publish must be boolean")
    reason = data.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 1000:
        raise ValueError("topic decision reason is invalid")
    refs = data.get("evidence_refs", ())
    if not isinstance(refs, (list, tuple)) or len(refs) > 32:
        raise ValueError("topic decision evidence_refs is invalid")
    evidence_refs = tuple(str(ref) for ref in refs)
    if any(not ref or len(ref) > 256 for ref in evidence_refs):
        raise ValueError("topic decision evidence_refs is invalid")
    proposal = _agenda_proposal(data.get("agenda_proposal"), topic=topic, scene=scene)
    if proposal is not None and not evidence_refs and proposal.source_refs:
        evidence_refs = proposal.source_refs
    return TopicDecision(topic, scene, confidence, should_publish, reason, evidence_refs, proposal)


def topic_setting_key(topic: str | QzoneTopic, suffix: str) -> str:
    return f"{normalize_topic(topic).value}_{suffix}"


__all__ = ["AgendaProposal", "QzoneScene", "QzoneTopic", "SCENES", "TOPICS", "TOPIC_SPECS", "TopicDecision",
           "TopicSpec", "allowed_scenes", "normalize_scene", "normalize_topic", "parse_decision",
           "topic_setting_key", "topic_spec", "validate_confidence"]
