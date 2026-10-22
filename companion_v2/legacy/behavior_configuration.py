"""Reviewed compound behavior settings that cannot use the old audit's first target."""

import json
import math
import re


TARGET_OVERRIDES = {
    "proactive_reach_config.max_daily_messages": "proactive.contact.max_contacts_24h",
    "memory_habit_config.expression_learning_mode": "expression.learning.learning_mode",
    "memory_habit_config.expression_group_learning_daily_batch_limit": "expression.learning.group_daily_batch_limit",
    "memory_habit_config.expression_group_learning_min_new_messages": "expression.learning.group_new_messages",
}
SPECIAL_SOURCES = frozenset({
    "basic_config.quiet_hours", "basic_config.default_proactive_daily_limit",
    "proactive_generation_config.proactive_persona_judge_max_daily",
    "recall_config.recall_message_cache_max_items", "news_config.news_sources",
    "memory_habit_config.expression_group_learning_source_mode",
    "humanized_state_config.advanced_cycle_start_offset",
    "experimental_motivation_config.emotion_judgement_mode",
    "memory_habit_config.meal_care_min_interval_hours",
    "memory_habit_config.meal_care_max_daily",
    "message_debounce_config.context_image_caption_max_items",
    "proactive_reach_config.proactive_share_priority",
    "daily_creative_config.creative_share_probability",
})
_QUIET = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")
_UNREPRESENTED = {
    "basic_config.default_proactive_daily_limit": (
        "proactive.contact.max_contacts_24h", "manual_mapping",
        "旧值仅为新用户档案的初始额度，不是全角色联系上限；不据此覆盖已授权用户的联系设置。"),
    "proactive_generation_config.proactive_persona_judge_max_daily": (
        "proactive.contact.enable_llm_proactive_persona_judge", "not_migrated",
        "新版不再以人格判定调用次数阻断主动消息；旧调用额度不转换为实际发送额度。"),
    "recall_config.recall_message_cache_max_items": (
        "conversation.recall.transcribe_max_items", "not_migrated",
        "旧值控制撤回摘要缓存容量；新版单次转述条数含义不同，不把缓存容量写成转述上限。"),
    "news_config.news_sources": (
        "proactive.contact.news_source_kind", "manual_mapping",
        "旧版多来源订阅不能等价写入新版单来源设置；保留来源并在升级页核对，不自动丢弃其余订阅。"),
    "experimental_motivation_config.emotion_judgement_mode": (
        "role.state.mood_update_probability", "partial_mapping",
        "旧情绪复核范围不等于角色情绪维护概率；保留已迁入的情绪开关，维护概率沿用新版设置。"),
    "memory_habit_config.meal_care_min_interval_hours": (
        "proactive.contact.interval_seconds", "partial_mapping",
        "旧值仅限制吃饭关心，不能改写所有主动消息的间隔；新版餐食时机由对应候选与近期对话决定。"),
    "memory_habit_config.meal_care_max_daily": (
        "proactive.contact.max_contacts_24h", "partial_mapping",
        "旧值仅限制餐食关心次数，不覆盖全角色主动联系上限；新版餐食候选结合已知回答与近期联系决定。"),
    "proactive_reach_config.proactive_share_priority": (
        "proactive.contact.proactive_share_probability", "manual_mapping",
        "旧候选排序优先级不等于分享概率，不将优先级百分数当作发送概率。"),
}


def append_behavior_configuration(config, registry, candidates, differences):
    from .configuration_migration import ConfigurationDifference, _boolean, _number, _source_value

    def note(source, target, kind, message):
        differences.append(ConfigurationDifference(target, kind, message, source))

    def add(source, target, value):
        field = registry.fields.get(target)
        if field is None:
            note(source, target, "unavailable", "当前运行档未注册此配置项。")
            return
        candidates.setdefault(target, []).append((
            {"source": source, "confidence": "high"}, field.validate(value)))

    for source, (target, kind, message) in _UNREPRESENTED.items():
        if _source_value(config, source)[0]:
            note(source, target, kind, message)

    source = "message_debounce_config.context_image_caption_max_items"
    present, raw = _source_value(config, source)
    if present:
        from companion_v2.conversation.media.models import MAX_INPUT_IMAGES
        target = "conversation.presentation.context_image_caption_max_items"
        try:
            count = _number(raw, integer=True)
            if count < 0:
                raise ValueError()
            add(source, target, min(count, MAX_INPUT_IMAGES))
            if count > MAX_INPUT_IMAGES:
                note(source, target, "partial_mapping",
                     f"旧图片描述上限超过新版单轮输入合同，按 {MAX_INPUT_IMAGES} 张接续，未退回默认条数。")
        except (TypeError, ValueError, OverflowError):
            note(source, target, "invalid_value", "旧图片描述条数不是有效的非负整数。")

    source = "basic_config.quiet_hours"
    present, raw = _source_value(config, source)
    if present:
        try:
            if not isinstance(raw, str):
                raise ValueError("免打扰时段须为文本")
            values = {"quiet_enabled": bool(raw.strip())}
            if raw.strip():
                match = _QUIET.fullmatch(raw)
                if match is None:
                    raise ValueError("免打扰时段须为 HH:MM-HH:MM")
                hours, minutes, end_hours, end_minutes = map(int, match.groups())
                if max(hours, end_hours) > 23 or max(minutes, end_minutes) > 59:
                    raise ValueError("免打扰时间超出有效范围")
                values.update(quiet_start=f"{hours:02d}:{minutes:02d}",
                              quiet_end=f"{end_hours:02d}:{end_minutes:02d}")
            # Validate the complete range before adding any of its fields.
            for name, value in values.items():
                registry.fields["proactive.contact." + name].validate(value)
            for name, value in values.items():
                add(source, "proactive.contact." + name, value)
        except (KeyError, TypeError, ValueError):
            note(source, "proactive.contact.quiet_enabled", "invalid_value",
                 "旧免打扰时段无法完整转换，未写入其中任何一项。")

    source = "humanized_state_config.advanced_cycle_start_offset"
    present, raw = _source_value(config, source)
    if present:
        try:
            offset = _number(raw, integer=True)
            if not 0 <= offset <= 180:
                raise ValueError()
            if offset == 0:
                add(source, "role.state.cycle_initialization", "natural")
            else:
                note(source, "role.state.cycle_initialization", "manual_mapping",
                     "旧周期日是一次性对齐操作；请在角色状态中核对当前周期，不把它转换为反复重放的初始化设置。")
        except (TypeError, ValueError, OverflowError):
            note(source, "role.state.cycle_initialization", "invalid_value", "旧周期日不在有效范围内。")

    source = "memory_habit_config.expression_group_learning_source_mode"
    present, raw = _source_value(config, source)
    if present:
        target = "expression.learning.group_learning_enabled"
        if raw in ("disabled", "selected", "all"):
            existing = candidates.get(target, ())
            enabled = raw == "all" and all(value for _, value in existing)
            candidates.pop(target, None)
            add(source, target, enabled)
            if raw == "selected":
                note(source, target, "manual_mapping",
                     "旧版仅从选定群学习；共享默认保持关闭，所选群须在群聊页核对，未扩展为所有群。")
        else:
            note(source, target, "invalid_value", "旧群学习来源范围不可识别。")

    source = "daily_creative_config.creative_share_probability"
    present, raw = _source_value(config, source)
    if present:
        target = "proactive.contact.proactive_share_probability"
        primary = "daily_creative_config.proactive_share_probability"
        if _source_value(config, primary)[0]:
            note(source, target, "partial_mapping",
                 "新版生活与创作共用分享概率，采用旧通用分享概率；单独创作概率保留为行为差异。")
        else:
            try:
                probability = _number(raw, integer=False)
                if not math.isfinite(probability) or not 0 <= probability <= 1:
                    raise ValueError()
                add(source, target, round(probability * 100))
                note(source, target, "partial_mapping",
                     "旧创作概率已转换为百分比；新版同时作用于生活与创作分享。")
            except (TypeError, ValueError, OverflowError):
                note(source, target, "invalid_value", "旧创作分享概率无法转换为百分比。")

    # The explicit intensity refines the enabled switch rather than competing
    # with a second candidate containing the new field's default.
    source = "humanized_state_config.inject_passive_states"
    present, raw = _source_value(config, source)
    target = "role.state.humanized_state_intensity"
    if present and _source_value(config, "humanized_state_config.humanized_state_intensity")[0]:
        try:
            enabled = _boolean(raw)
        except ValueError:
            return
        values = candidates.get(target, [])
        selected = [item for item in values if (item[0]["source"] != source if enabled
                    else item[0]["source"] == source)]
        if selected:
            candidates[target] = selected


def component_order(value):
    """Retain supported V1 component ordering without inventing new kinds."""
    from companion_v2.delivery.plan import CONTENT_KINDS

    if (type(value) is not list or any(type(item) is not str or item not in
            (*CONTENT_KINDS, "other", "reaction") for item in value)):
        raise ValueError("旧组件顺序含不可识别的种类")
    return json.dumps(list(dict.fromkeys(item for item in value if item in CONTENT_KINDS)),
                      ensure_ascii=False, separators=(",", ":"))
