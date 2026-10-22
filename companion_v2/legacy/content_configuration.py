"""Map standalone Content preferences to the native authoring owner."""

from __future__ import annotations

from dataclasses import dataclass

from .native_extension_configuration import setting_value, _leaves


SOURCE = "astrbot_plugin_content_companion_config.json"
FIELDS = {
    "creative.enable_creative_writing": "content.authoring.enabled",
    "creative.creative_direction_prompt": "content.authoring.direction_prompt",
    "creative.enable_creative_cover_generation": "content.authoring.cover_enabled",
    "creative.CREATIVE_PROVIDER_ID": "model.content.authoring.draft.provider",
}
_MISSING = object()


@dataclass(frozen=True)
class ContentConfigurationMigration:
    changes: dict
    sources: dict
    differences: tuple[dict, ...]


def convert_content_configuration(source, registry):
    """Use registered consumers only; publication and credentials remain untouched."""
    if not isinstance(source, dict):
        return ContentConfigurationMigration({}, {}, ())
    changes, sources, differences = {}, {}, []
    master = source.get("enabled", True)
    fields = getattr(registry, "fields", {})
    for path, target in FIELDS.items():
        value = setting_value(source, path, _MISSING)
        if value is _MISSING and not (master is False and target.endswith("enabled")):
            continue
        if target.endswith("enabled"):
            if type(master) is not bool or value is not _MISSING and type(value) is not bool:
                differences.append({"field": "content." + path, "kind": "invalid_value",
                                    "explain": "旧创作开关类型无效，未迁移。"})
                continue
            value = master and value
        elif target.endswith(".provider") and isinstance(value, str):
            value = value.strip()
            if not value:
                continue  # An empty old selection inherits the host's model.
        field = fields.get(target)
        if field is None:
            differences.append({"field": target, "kind": "unavailable",
                                "explain": "当前版本未注册此创作设置，未迁移。"})
            continue
        try:
            changes[target] = field.validate(value)
        except (TypeError, ValueError, OverflowError):
            differences.append({"field": "content." + path, "kind": "invalid_value",
                                "explain": "旧创作偏好未通过目标字段校验，未迁移。"})
        else:
            sources[target] = ((SOURCE + ":" + path,)
                               if setting_value(source, path, _MISSING) is not _MISSING else ())
            if master is False and target.endswith("enabled"):
                sources[target] += (SOURCE + ":enabled",)
    for path, _ in _leaves(source):
        if path in FIELDS:
            continue
        if path == "enabled" and type(master) is bool:
            kind, explain = "partial_mapping", "旧拓展总开关只参与创作和封面开关的有效值计算，不开启空间发布。"
        elif path.startswith("qzone."):
            kind, explain = "manual_review_required", "空间账号、Cookie 与发布权限需在新版按账号确认，未自动启用。"
        elif path.startswith("creative."):
            kind, explain = "changed_semantics", "旧创作概率、篇幅、项目数或多阶段模型没有同义消费入口，保留旧配置供核对。"
        else:
            kind, explain = "unmapped", "当前版本没有可核实的同义落点，旧配置保持不变。"
        differences.append({"field": "content." + path, "kind": kind, "explain": explain})
    return ContentConfigurationMigration(changes, sources, tuple(differences))
