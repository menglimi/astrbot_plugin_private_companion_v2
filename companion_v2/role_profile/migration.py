"""Conservatively map structured AstrBot persona canon into V2 role fields."""

from __future__ import annotations

import hashlib
import re

from .configuration import FIELD_LIMITS


MAX_PERSONA_CHARS = 30000
_BLOCK = re.compile(r"<Role_Profile>(.*?)</Role_Profile>", re.DOTALL)
_BOLD_HEADER = re.compile(r"^\s*(?:[-*+]\s*)?\*\*(?P<label>[^*\n]{1,80})\*\*\s*[:：]?\s*(?P<value>.*)$")
_PLAIN_HEADER = re.compile(r"^\s*(?:[-*+]\s*)?(?P<label>[^:：\n]{1,80})\s*[:：]\s*(?P<value>.*)$")
_STANDALONE_HEADER = re.compile(r"^\s*(?:[-*+]\s*)?\*\*(?P<label>[^*\n]{1,80})\*\*\s*$")
_USER_HEADER = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?\s*用户(?:\s*[（(][^）)]{0,120}[）)])?\s*(?:\*\*)?\s*[:：]?.*$")

# Only these explicit, role-owned sections are imported. Relationship details
# about the operator are deliberately outside this mapping.
_SECTION_FIELDS = {
    "姓名": "name",
    "基本信息": "identity",
    "外貌特征": "appearance",
    "特殊设定": "character_extra",
    "性格特质": "personality",
    "底色与气质": "personality",
    "内在驱动": "motivations",
    "外显表现": "reaction_patterns",
    "亲疏变化": "social_distance",
    "压力与冲突": "reaction_patterns",
    "矛盾感": "personality",
    "兴趣爱好": "hobbies",
    "厌恶事物": "character_extra",
    "口头禅": "signature_phrases",
    "社会关系": "network",
}

_WORLD_KNOWLEDGE_FIELDS = {
    "姓名": "name",
    "名字": "name",
    "种族": "species",
    "生日": "birthday",
    "星座/生日": "birthday",
    "年龄": "age",
    "性别": "gender",
    "识别点": "appearance_points",
    "外貌识别点": "appearance_points",
    "外貌特征": "appearance",
    "外貌描述": "appearance",
    "发型发色": "hair",
    "发型": "hair",
    "发色": "hair",
    "瞳色": "eyes",
    "眼睛": "eyes",
    "服饰风格": "clothing",
    "服装风格": "clothing",
    "职业/身份": "occupation",
    "职业": "occupation",
    "身份": "occupation",
    "性格描述": "personality",
    "性格特质": "personality",
    "核心欲望/目标": "desire",
    "核心目标": "desire",
    "目标": "desire",
    "爱好": "hobbies",
    "兴趣爱好": "hobbies",
    "禁忌": "taboos",
    "关键设定": "key_lore",
    "日常习惯": "daily_habits",
    "作息": "daily_habits",
    "口头禅": "signature_phrases",
    "特殊图像身份线索": "image_identity_hint",
    "其他补充信息": "character_extra",
    "其它补充信息": "character_extra",
}
_EXCLUDED_LABELS = frozenset({
    "用户", "用户资料", "用户补充", "用户关系", "关系资料", "用户与关系",
    "对用户的称呼", "用户性别", "用户生日", "用户职业", "与用户关系",
    "是角色的xx", "是角色的XX", "相处方式", "所处世界", "时代背景",
    "基本法则/基调", "特殊规则", "主要活动场景", "世界观关系网",
})
_DAILY_HABIT_MARKERS = (
    "每天", "工作日", "周一", "周二", "周三", "周四", "周五", "周末",
    "上学", "放学", "起床", "睡觉", "作息", "早上", "上午", "下午", "晚上",
)


def _is_explicit_daily_habit(value: str) -> bool:
    return sum(marker in value for marker in _DAILY_HABIT_MARKERS) >= 3


class RoleProfileMigrationError(ValueError):
    """The host persona has no safely mappable structured canon."""


def role_profile_block(persona_text: str) -> str:
    if type(persona_text) is not str or not persona_text.strip() or len(persona_text) > MAX_PERSONA_CHARS:
        raise RoleProfileMigrationError("role_profile_source_invalid")
    blocks = _BLOCK.findall(persona_text)
    if len(blocks) != 1:
        raise RoleProfileMigrationError("role_profile_source_missing_or_ambiguous")
    return blocks[0]


def map_persona_role_profile(persona_text: str) -> dict:
    """Extract explicitly labeled fields, excluding user-specific relationship text."""
    block = role_profile_block(persona_text)
    sections: list[tuple[str, list[str]]] = []
    current_label = ""
    current_lines: list[str] = []

    def finish():
        if current_label:
            value = "\n".join(line for line in current_lines if line).strip()
            sections.append((current_label, [value] if value else []))

    for line in block.splitlines():
        if _USER_HEADER.match(line):
            finish()
            current_label, current_lines = "", []
            continue
        match = _BOLD_HEADER.match(line) or _PLAIN_HEADER.match(line) or _STANDALONE_HEADER.match(line)
        if match:
            label = match.group("label").strip().strip("*# ")
            if label in _SECTION_FIELDS:
                finish()
                current_label = label
                current_lines = [match.groupdict().get("value", "").strip()]
                continue
        if current_label:
            current_lines.append(line.strip())
    finish()

    collected: dict[str, list[tuple[str, str]]] = {}
    for label, values in sections:
        value = "\n".join(values).strip()
        if value:
            collected.setdefault(_SECTION_FIELDS[label], []).append((label, value))

    fields: dict[str, str] = {}
    rejected: list[str] = []
    for field, values in collected.items():
        merged = "\n".join(
            value if len(values) == 1 else f"{label}：{value}"
            for label, value in values
        ).strip()
        if len(merged) > FIELD_LIMITS[field]:
            rejected.append(field)
            continue
        fields[field] = merged

    if not fields and not rejected:
        raise RoleProfileMigrationError("role_profile_source_has_no_supported_fields")
    return {
        "fields": fields,
        "rejected_fields": sorted(rejected),
        "source_chars": len(persona_text),
        "block_chars": len(block),
        "source_fingerprint": hashlib.sha256(persona_text.encode("utf-8")).hexdigest(),
        "excluded_relationship_sections": sum(bool(_USER_HEADER.match(line)) for line in block.splitlines()),
    }


def map_v1_world_knowledge_role_profile(persona_text: str, image_identity_hint: str = "", *,
                                        configuration_fingerprint: str = "") -> dict:
    """Map the V1 World Knowledge role form into explicit V2 role fields."""
    if (type(persona_text) is not str or type(image_identity_hint) is not str
            or len(persona_text) > MAX_PERSONA_CHARS or len(image_identity_hint) > FIELD_LIMITS["image_identity_hint"] * 8):
        raise RoleProfileMigrationError("role_profile_source_invalid")

    sections: list[tuple[str, str]] = []
    current_label = ""
    current_lines: list[str] = []
    excluded = 0

    def finish():
        if current_label:
            value = "\n".join(line for line in current_lines if line).strip()
            if value:
                sections.append((current_label, value))

    for line in persona_text.splitlines():
        if _USER_HEADER.match(line):
            finish()
            current_label, current_lines = "", []
            excluded += 1
            continue
        match = _BOLD_HEADER.match(line) or _PLAIN_HEADER.match(line) or _STANDALONE_HEADER.match(line)
        if match:
            label = match.group("label").strip().strip("*# ")
            if label in _WORLD_KNOWLEDGE_FIELDS:
                finish()
                current_label = label
                current_lines = [match.groupdict().get("value", "").strip()]
                continue
            finish()
            current_label, current_lines = "", []
            if label in _EXCLUDED_LABELS or label.startswith("用户"):
                excluded += 1
            continue
        if current_label:
            current_lines.append(line.strip())
    finish()

    if image_identity_hint.strip():
        sections.append(("特殊图像身份线索", image_identity_hint.strip()))

    collected: dict[str, list[tuple[str, str]]] = {}
    for label, value in sections:
        field = _WORLD_KNOWLEDGE_FIELDS[label]
        if label in {"其他补充信息", "其它补充信息"} and _is_explicit_daily_habit(value):
            field = "daily_habits"
        collected.setdefault(field, []).append((label, value))

    fields: dict[str, str] = {}
    rejected: list[str] = []
    for field, values in collected.items():
        merged = "\n".join(
            value if len(values) == 1 else f"{label}：{value}"
            for label, value in values
        ).strip()
        if len(merged) > FIELD_LIMITS[field]:
            rejected.append(field)
            continue
        fields[field] = merged

    if not fields and not rejected:
        raise RoleProfileMigrationError("role_profile_source_has_no_supported_fields")

    source_material = persona_text + "\0" + image_identity_hint
    return {
        "fields": fields,
        "rejected_fields": sorted(rejected),
        "source_chars": len(persona_text) + len(image_identity_hint),
        "block_chars": len(persona_text),
        "source_fingerprint": configuration_fingerprint or hashlib.sha256(
            source_material.encode("utf-8")).hexdigest(),
        "excluded_relationship_sections": excluded,
    }


__all__ = ["MAX_PERSONA_CHARS", "RoleProfileMigrationError", "map_persona_role_profile",
           "map_v1_world_knowledge_role_profile", "role_profile_block"]
