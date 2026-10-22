"""Convert old route policies only onto registered V2 model task profiles."""

import json


def append_model_configuration(config, registry, candidates, differences):
    from .configuration_migration import ConfigurationDifference, _source_value, _boolean
    from companion_v2.model_gateway.replacement_rules import checked_rules
    from companion_v2.model_gateway.refusal import parse_refusal_terms

    prefix = "model_assignment_config."
    fields = {field.group_id for field in registry.fields.values()
              if field.field_id.startswith("model.") and field.field_id.endswith(".provider")}
    def add(group, suffix, value, source):
        field_id = group + "." + suffix
        field = registry.fields.get(field_id)
        if field is None:
            return
        try:
            value = field.validate(value)
            if suffix == "replacement_rules":
                checked_rules(value)
            elif suffix == "refusal_terms":
                parse_refusal_terms(value)
            elif suffix == "replacement_scope" and value not in ("all", "plugin", "conversation"):
                raise ValueError()
        except (ValueError, TypeError):
            differences.append(ConfigurationDifference(field_id, "invalid_value",
                "旧模型策略不符合当前任务合同，保留原文归档供核对。", source))
            return
        candidates.setdefault(field_id, []).append(({"source":source,"confidence":"high"}, value))

    for name, suffix in (("model_replacement_rules", "replacement_rules"),
                         ("model_replacement_scope", "replacement_scope"),
                         ("enable_sensitive_model_replacement", "fallback_on_refusal"),
                         ("SENSITIVE_REPLACEMENT_PROVIDER_ID", "fallback"),
                         ("sensitive_replacement_keywords", "refusal_terms")):
        source = prefix + name
        present, value = _source_value(config, source)
        if not present:
            continue
        if suffix == "fallback_on_refusal":
            try:
                value = _boolean(value)
            except ValueError:
                continue
        if suffix == "replacement_rules" and isinstance(value, list):
            value = json.dumps(value,ensure_ascii=False,separators=(",",":"))
        if suffix == "refusal_terms" and isinstance(value, list) and all(isinstance(i,str) for i in value):
            value = "\n".join(value)
        if suffix == "fallback" and not value:
            continue
        # V1 conversation replacements apply to conversational work, not image/audio providers.
        if "model.conversation.reply" in fields:
            differences.append(ConfigurationDifference("model.conversation.reply." + suffix, "host_managed",
                "普通对话的模型选路、拒答回退与超时由 AstrBot 当前会话管理；插件默认策略只供插件附加任务使用。", source))

    timeouts = config.get("model_timeout_overrides", {})
    if isinstance(timeouts, dict):
        for task, value in timeouts.items():
            group = task if task.startswith("model.") else "model." + task
            if group in fields and group != "model.conversation.reply":
                add(group, "timeout_seconds", value, "model_timeout_overrides")
            else:
                differences.append(ConfigurationDifference(group + ".timeout_seconds", "host_managed" if group == "model.conversation.reply" else "unavailable",
                    "此旧任务由宿主管理或没有对应的 V2 任务档；超时保留在原配置中。", "model_timeout_overrides"))
