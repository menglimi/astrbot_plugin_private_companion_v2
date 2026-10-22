"""Legacy reply settings whose precedence cannot be expressed as flat rules."""

from __future__ import annotations

import math


PRIVATE_DEBOUNCE_SOURCES = frozenset(
    "message_debounce_config." + name for name in (
        "enable_message_debounce", "enable_semantic_message_debounce",
        "text_message_debounce_seconds", "semantic_message_debounce_seconds",
        "text_message_debounce_max_wait_seconds",
    )
)
SOFT_ALIASES = {
    "legacy_compat_config.enable_maintenance_token_saver": "basic_config.enable_daily_token_soft_limit",
    "legacy_compat_config.maintenance_token_soft_limit": "basic_config.daily_token_soft_limit",
}


def soft_alias_is_inactive(config, source):
    from .configuration_migration import _boolean, _number, _source_value

    present, raw = _source_value(config, source)
    if not present or raw is None or isinstance(raw, str) and not raw.strip():
        return True
    primary = SOFT_ALIASES.get(source)
    if primary is None:
        return False
    present, raw = _source_value(config, primary)
    if not present or raw is None or isinstance(raw, str) and not raw.strip():
        return False
    try:
        if primary.endswith("enable_daily_token_soft_limit"):
            _boolean(raw)
        elif _number(raw, integer=True) < 0:
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def select_plugin_rules(config, rules):
    """Respect V1's active branch and alias priority before checking collisions."""
    from .configuration_migration import ConfigurationDifference, _source_value

    if not isinstance(config, dict):
        return rules, ()
    differences, selected = [], []
    scope_source = "voice_action_config.tts_conversion_scope"
    scope_present, scope = _source_value(config, scope_source)
    scope_explicit = scope_present and scope is not None and str(scope).strip() != ""
    mode_source = "voice_action_config.tts_frequency_control_mode"
    mode_present, mode = _source_value(config, mode_source)
    mode = str(mode).strip().lower() if mode_present else "global"
    interval_sources = {
        "voice_action_config.tts_session_min_interval_seconds",
        "voice_action_config.tts_private_min_interval_seconds",
        "voice_action_config.tts_group_min_interval_seconds",
    }
    for rule in rules:
        source = rule["source"]
        present, raw = _source_value(config, source)
        if source == "operation_access.public_operations":
            if present:
                differences.append(ConfigurationDifference("native.image.permissions", "manual_mapping",
                    "旧普通用户操作名单只管理生图权限，不覆盖新版记忆、状态或对话能力；生图授权需按原对象单独核对。", source))
            continue
        if source in SOFT_ALIASES and soft_alias_is_inactive(config, source):
            continue
        if source == "auto_voice_config.auto_voice_full_conversion_enabled" and scope_explicit:
            continue
        if source == scope_source and not scope_explicit:
            continue
        if source in interval_sources and mode == "legacy":
            continue
        if source == "auto_voice_config.auto_voice_cooldown_seconds":
            if mode != "legacy":
                continue
            if present:
                differences.append(ConfigurationDifference(rule["target"], "partial_mapping",
                    "旧自动语音冷却仅作用于旧频控的自动语音路径；新版按会话统一冷却，请核对按请求语音的频率。", source))
        if source == "voice_action_config.tts_generation_mode" and present:
            if isinstance(raw, str) and raw.strip().lower() in {"postprocess", "convert", "post", "llm"}:
                differences.append(ConfigurationDifference(rule["target"], "partial_mapping",
                    "旧发送前二次模型转换改由主回复模型编写语音标签；保留语种、译文与转换范围，不再执行旧独立转换模型。", source))
        if mode not in {"global", "legacy"} and (source in interval_sources
                or source == "auto_voice_config.auto_voice_cooldown_seconds"):
            if present:
                differences.append(ConfigurationDifference(rule["target"], "invalid_value",
                    "旧语音频控模式不可识别，冷却设置未自动迁移。", mode_source))
            continue
        selected.append(rule)
    return tuple(selected), tuple(differences)


def append_private_debounce(config, registry, candidates, differences, *, window_kind):
    """Move text waiting onto the actual AstrBot core-reply debounce owner."""
    from .configuration_migration import ConfigurationDifference, _boolean, _number, _source_value

    if not any(_source_value(config, source)[0] for source in PRIVATE_DEBOUNCE_SOURCES):
        return
    if window_kind == "group":
        differences.append(ConfigurationDifference(
            "conversation.presentation.private_debounce_enabled", "partial_mapping",
            "旧文本补话等待仅接续到私聊主链；群聊使用独立的时机判断，未将私聊等待写入群聊设置。",
            "message_debounce_config.enable_message_debounce"))
        return
    prefix, group = "message_debounce_config.", "conversation.presentation."

    def effective(primary, alias, default):
        for name in (primary, alias):
            if name is None:
                continue
            present, value = _source_value(config, prefix + name)
            if present and value is not None and not (isinstance(value, str) and not value.strip()):
                return value, prefix + name
        return default, prefix + primary

    enabled, switch_source = effective("enable_message_debounce", "enable_semantic_message_debounce", True)
    quiet, quiet_source = effective("text_message_debounce_seconds", "semantic_message_debounce_seconds", 8.0)
    total, total_source = effective("text_message_debounce_max_wait_seconds", None, 12.0)
    try:
        enabled = _boolean(enabled)
        quiet = _number(quiet, integer=False)
        if not math.isfinite(quiet) or quiet < 0:
            raise ValueError("旧文本补话等待必须为非负有限秒数")
        values = {"private_debounce_enabled": (enabled and quiet > 0, switch_source)}
        if enabled and quiet > 0:
            total = _number(total, integer=False)
            if not math.isfinite(total) or total <= 0:
                raise ValueError("旧无限总等待没有等价的有限等待设置，需手动核对")
            # V1 closed the buffer at the earlier of quiet and total deadlines.
            quiet = min(quiet, total)
            for name, seconds, source in (
                ("private_debounce_min_ms", quiet, quiet_source),
                ("private_debounce_max_ms", quiet, quiet_source),
                ("private_debounce_total_ms", total, total_source),
            ):
                millis = seconds * 1000
                if not math.isfinite(millis) or not math.isclose(millis, round(millis), abs_tol=1e-7):
                    raise ValueError("旧等待时间不能无损转换为毫秒")
                values[name] = (round(millis), source)
        checked = {}
        for name, (value, source) in values.items():
            field = registry.fields.get(group + name)
            if field is None:
                differences.append(ConfigurationDifference(group + name, "unavailable",
                    "当前运行档没有注册主链文本补话设置，此项未迁移。", source))
                return
            checked[group + name] = (field.validate(value), source)
    except (TypeError, ValueError, OverflowError) as error:
        differences.append(ConfigurationDifference(group + "private_debounce_enabled", "invalid_value",
            f"文本补话设置未迁移：{error}。", quiet_source))
        return
    for target, (value, source) in checked.items():
        candidates.setdefault(target, []).append(({"source": source, "confidence": "high"}, value))
