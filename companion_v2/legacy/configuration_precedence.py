"""Preserve active legacy branches instead of treating distinct settings as aliases."""

from .configuration_migration import ConfigurationDifference, _boolean, _number, _source_value


PROMPT_SOURCES = {
    "conversation.presentation.style_prompt": (
        ("basic_config.default_style", "默认语气"),
        ("basic_config.reply_style_prompt", "回复表达"),
        ("basic_config.persona_conversation_voice_prompt", "角色聊天口吻")),
    "role.life.diary_style_prompt": (
        ("basic_config.persona_creative_voice_prompt", "角色创作口吻"),
        ("schedule_detail_config.daily_diary_custom_direction", "日记方向")),
    "role.state.planning_prompt": (
        ("basic_config.persona_planning_voice_prompt", "角色规划倾向"),
        ("life_schedule_config.daily_plan_prompt", "日程规划偏好")),
}
_JUDGE_SWITCHES = (
    "proactive_generation_config.enable_llm_proactive_persona_judge",
    "emotion_relationship_config.enable_proactive_message_review",
)
_JUDGE_PROVIDERS = (
    "proactive_generation_config.PROACTIVE_PERSONA_JUDGE_PROVIDER_ID",
    "model_assignment_config.RESPONSE_REVIEW_PROVIDER_ID",
)
_PHOTO_LIMITS = (
    "photo_action_config.photo_generation_proactive_max_daily",
    "photo_action_config.photo_action_max_daily",
)
_ACTION_ALIASES = {
    "legacy_compat_config.allow_screen_peek_action": "screen_action_config.enable_screen_glance_action",
    "legacy_compat_config.allow_poke_action": "poke_action_config.enable_poke_action",
    "legacy_compat_config.allow_voice_action": "voice_action_config.enable_voice_action",
}
_COMPOUND = frozenset(source for pairs in PROMPT_SOURCES.values() for source, _ in pairs) | frozenset(
    (*_JUDGE_SWITCHES, *_JUDGE_PROVIDERS, *_PHOTO_LIMITS,
     "schedule_detail_config.daily_diary_creativity", "legacy_compat_config.enabled_proactive_actions",
     "model_assignment_config.SMART_SILENCE_PROVIDER_ID"))


def select_registry_rules(config, rules):
    selected, differences = [], []
    for rule in rules:
        source = rule["source"]
        if source == "basic_config.default_proactive_daily_limit":
            # New-profile defaults are not a decision-attempt budget. Individual
            # legacy quotas come from the verified user's profile instead.
            if _source_value(config, source)[0]:
                differences.append(ConfigurationDifference("proactive.contact.max_contacts_24h",
                    "derived_default", "旧版新用户默认次数不覆盖运行中的全局上限；个人次数按用户档案接续。", source))
            continue
        if rule["target"] == "role.life.timezone":
            present, raw = _source_value(config, source)
            if present:
                try:
                    from zoneinfo import ZoneInfo
                    ZoneInfo(raw)
                except (TypeError, ValueError, KeyError):
                    differences.append(ConfigurationDifference(rule["target"], "derived_default",
                        "旧空白或不可用的时区表示跟随环境；保留当前生活时区，不写入无效空值。", source))
                    continue
        if source in _COMPOUND:
            continue
        if source in _ACTION_ALIASES:
            present, raw = _source_value(config, source)
            if not present or raw is None or isinstance(raw, str) and not raw.strip():
                continue
            if _source_value(config, _ACTION_ALIASES[source])[0]:
                continue
        if source.startswith("external_memory_config.new_framework_dev_e2e_"):
            present, raw = _source_value(config, "external_memory_config.enable_new_framework_dev_e2e")
            try:
                active = present and _boolean(raw)
            except ValueError:
                active = False
            if not active or source.endswith(".new_framework_dev_e2e_max_memory_items"):
                if _source_value(config, source)[0]:
                    differences.append(ConfigurationDifference(rule["target"],
                        "partial_mapping" if active else "inactive_source",
                        "旧开发验证链路的专用预算不覆盖正式记忆上下文；新版统一采用正式记忆设置。", source))
                continue
        selected.append(rule)
    return tuple(selected), tuple(differences)


def append_compound_configuration(config, registry, candidates, differences):
    def note(source, target, kind, message):
        differences.append(ConfigurationDifference(target, kind, message, source))

    def add(source, target, value, *, confidence="medium"):
        field = registry.fields.get(target)
        if field is None:
            note(source, target, "unavailable", "当前运行档未注册此配置项。")
            return
        try:
            value = field.validate(value)
        except (TypeError, ValueError):
            note(source, target, "invalid_value", "合并后的旧配置超出当前字段合同，保留原文供核对。")
            return
        candidates.setdefault(target, []).append(({"source": source, "confidence": confidence}, value))

    # V1 scheduled diary/reading directly. V7 also has a life-runtime master;
    # carrying only the child switches leaves every migrated routine dormant.
    life_switches = []
    for target in ("role.life.diary_enabled", "role.life.reading_enabled"):
        values = candidates.get(target, ())
        if values and len({value for _, value in values}) == 1:
            life_switches.extend((rule["source"], value) for rule, value in values)
    if life_switches:
        for source, _ in life_switches:
            add(source, "role.life.enabled", any(value for _, value in life_switches), confidence="high")

    for target, pairs in PROMPT_SOURCES.items():
        parts, sources = [], []
        for source, label in pairs:
            present, raw = _source_value(config, source)
            if not present or raw == "":
                continue
            if type(raw) is not str:
                note(source, target, "invalid_value", "旧风格补充须为文本。")
                continue
            if raw.strip():
                parts.append((label, raw))
                sources.append(source)
        if not parts:
            continue
        text = parts[0][1] if len(parts) == 1 else "\n\n".join(f"【{label}】\n{raw}" for label, raw in parts)
        for source in sources:
            add(source, target, text, confidence="high" if len(parts) == 1 else "medium")
        if target == "conversation.presentation.style_prompt":
            # The old common reply style also constrained proactive replies.
            shared = [(source, label) for source, label in pairs
                      if source in sources and source != "basic_config.persona_conversation_voice_prompt"]
            if shared and "proactive.contact.style_prompt" not in candidates:
                values = [f"【{label}】\n{_source_value(config, source)[1]}" for source, label in shared]
                for source, _ in shared:
                    add(source, "proactive.contact.style_prompt", "\n\n".join(values))

    source = "schedule_detail_config.daily_diary_creativity"
    if _source_value(config, source)[0]:
        note(source, "role.life.diary_style_prompt", "partial_mapping",
            "旧日记创作档位不作为风格正文写入；新版保留角色创作口吻与日记方向，事实边界由来源约束。")

    enabled = []
    for source in _JUDGE_SWITCHES:
        present, raw = _source_value(config, source)
        if present:
            try:
                enabled.append((source, _boolean(raw)))
            except ValueError:
                note(source, "proactive.contact.enable_llm_proactive_persona_judge", "invalid_value",
                    "旧主动评审开关不可识别。")
    for source, _ in enabled:
        add(source, "proactive.contact.enable_llm_proactive_persona_judge", any(value for _, value in enabled))
    providers = [(source, _source_value(config, source)) for source in _JUDGE_PROVIDERS]
    selected = next(((source, raw) for source, (present, raw) in providers
                     if present and isinstance(raw, str) and raw.strip()
                     and (source == _JUDGE_PROVIDERS[0] or any(
                         key == _JUDGE_SWITCHES[1] and value for key, value in enabled))), None)
    if selected:
        add(selected[0], "model.proactive.judge.provider", selected[1])
    if any(_source_value(config, source)[0] for source in (_JUDGE_SWITCHES[1], _JUDGE_PROVIDERS[1])):
        note(_JUDGE_SWITCHES[1], "model.proactive.judge.provider", "partial_mapping",
            "旧主动人格判定与发送前复核合并为一次主动评审；任一开启则保留评审，模型优先采用主动人格判定配置。")
    source = "model_assignment_config.SMART_SILENCE_PROVIDER_ID"
    if _source_value(config, source)[0]:
        note(source, "model.proactive.judge.provider", "host_managed",
            "旧被动回复静默判定模型不覆盖主动评审模型；普通回复继续由 AstrBot 主链管理。")

    limits = []
    for source in _PHOTO_LIMITS:
        present, raw = _source_value(config, source)
        if not present:
            continue
        try:
            value = _number(raw, integer=True)
            if source == _PHOTO_LIMITS[1] and value == 0:
                value = -1  # The old per-user limit used zero for unlimited.
            if value < -1:
                raise ValueError()
            limits.append((source, value))
        except (TypeError, ValueError, OverflowError):
            note(source, "conversation.media_quota.proactive_max_daily", "invalid_value",
                "旧主动生图额度无法无损转换。")
    if limits:
        finite = [value for _, value in limits if value >= 0]
        value = min(finite) if finite else -1
        for source, _ in limits:
            add(source, "conversation.media_quota.proactive_max_daily", value)
        note(_PHOTO_LIMITS[0], "conversation.media_quota.proactive_max_daily", "partial_mapping",
            "新版按请求者统计主动生图，采用旧额度中更小的有效上限；旧全局计数与用户计数不再独立叠加。")

    source = "legacy_compat_config.enabled_proactive_actions"
    present, raw = _source_value(config, source)
    if present and raw is not None and str(raw).strip():
        note(source, "proactive.contact.screen_glance_enabled", "manual_mapping",
            "旧动作名单不能作为单个识屏开关；优先迁移各项明确动作开关，未解析名单不自动扩大设备访问权限。")


def select_semantic_rules(config, rules):
    source = "experimental_motivation_config.REACTION_EXPRESSION_EMBEDDING_PROVIDER_ID"
    if not isinstance(config, dict) or not _source_value(config, source)[0]:
        return rules, ()
    return tuple(rule for rule in rules if rule["source"] != source), (
        ConfigurationDifference("semantic.embedding_provider", "partial_mapping",
            "旧表情库专用向量模型不覆盖全插件语义模型；全局模型采用原全局配置，表情库差异保留供核对。", source),)
