"""Carry standalone recall preferences into the native memory configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .native_extension_configuration import _leaves, setting_value


SOURCE = "astrbot_plugin_memory_companion_config.json"
FIELDS = {
    "memory_injection.top_k": "memory.context_items",
    "memory_injection.max_chars": "memory.context_chars",
}
RECALL_SCOPES = ("scope_control.private_recall_enabled", "scope_control.group_recall_enabled")
SUMMARY_MODELS = tuple("memory_summary." + key for key in (
    "provider_id", "fallback_provider_id", "private_provider_id", "private_fallback_provider_id",
    "group_provider_id", "group_fallback_provider_id"))
SUMMARY_TIMEOUT = "memory_summary.provider_timeout_seconds"
_MISSING = object()


@dataclass(frozen=True)
class MemoryConfigurationMigration:
    changes: dict
    sources: dict
    differences: tuple[dict, ...]


def convert_memory_configuration(source, registry):
    """Carry recall and compatible extraction routes, without flattening scope overrides."""
    if not isinstance(source, dict):
        return MemoryConfigurationMigration({}, {}, ())
    changes, sources, differences = {}, {}, []
    fields = getattr(registry, "fields", {})

    def accept(path, target, value, dependencies=()):
        definition = fields.get(target)
        if definition is None:
            differences.append({"field": target, "kind": "unavailable",
                                "explain": "当前版本未注册此记忆设置，未迁移。"})
            return
        try:
            changes[target] = definition.validate(value)
        except (TypeError, ValueError, OverflowError):
            differences.append({"field": "memory." + path, "kind": "invalid_value",
                                "explain": "旧记忆偏好不符合目标字段的类型或范围，未迁移。"})
        else:
            sources[target] = tuple(SOURCE + ":" + item for item in (path, *dependencies))

    for path, target in FIELDS.items():
        value = setting_value(source, path, _MISSING)
        if value is not _MISSING:
            accept(path, target, value)

    model_values = {path: setting_value(source, path, _MISSING) for path in SUMMARY_MODELS}
    invalid_models = [path for path, value in model_values.items()
                      if value is not _MISSING and type(value) is not str]
    for path in invalid_models:
        differences.append({"field": "memory." + path, "kind": "invalid_value",
                            "explain": "旧摘要模型选择不是文本，未迁移模型路线。"})
    if not invalid_models:
        configured = {path: value.strip() for path, value in model_values.items()
                      if value is not _MISSING and value.strip()}
        common = tuple(configured.get(path, "") for path in SUMMARY_MODELS[:2])
        routes = [tuple(dict.fromkeys(value for value in (
            configured.get(f"memory_summary.{scene}_provider_id", ""),
            configured.get(f"memory_summary.{scene}_fallback_provider_id", ""), *common) if value))
            for scene in ("private", "group")]
        if routes[0] != routes[1] or len(routes[0]) > 2:
            differences.append({"field": "model.memory.reflect", "kind": "scope_review_required",
                                "explain": "旧私聊与群聊摘要采用不同模型链，或超过新版主备两级路线；未覆盖成角色通用模型。"})
        elif routes[0]:
            dependencies = tuple(configured)
            for suffix, value in zip(("provider", "fallback"), routes[0]):
                accept(dependencies[0], "model.memory.reflect." + suffix, value, dependencies[1:])
            differences.append({"field": "model.memory.reflect", "kind": "partial_mapping",
                                "explain": "旧摘要主备模型接续至新版记忆反思任务；采集、摘要触发与画像调度仍按新版运行。"})
    timeout = setting_value(source, SUMMARY_TIMEOUT, _MISSING)
    if timeout is not _MISSING:
        accept(SUMMARY_TIMEOUT, "model.memory.reflect.timeout_seconds", timeout)

    enabled = setting_value(source, "memory_injection.enabled", _MISSING)
    scoped = {path: setting_value(source, path, _MISSING) for path in RECALL_SCOPES}
    valid_scopes = all(value is _MISSING or type(value) is bool for value in scoped.values())
    disabled_scopes = [path for path, value in scoped.items() if value is False]
    if enabled is not _MISSING and type(enabled) is not bool:
        differences.append({"field": "memory.memory_injection.enabled", "kind": "invalid_value",
                            "explain": "旧记忆注入开关类型无效，未迁移。"})
    elif enabled is False or len(disabled_scopes) == len(RECALL_SCOPES):
        paths = (("memory_injection.enabled",) if enabled is not _MISSING else ()) + tuple(
            path for path in scoped if scoped[path] is not _MISSING)
        accept(paths[0], "memory.automatic_context", False, paths[1:])
    elif enabled is True and valid_scopes and not disabled_scopes:
        accept("memory_injection.enabled", "memory.automatic_context", True,
               tuple(path for path in scoped if scoped[path] is not _MISSING))
    if enabled is not _MISSING and type(enabled) is bool:
        differences.append({"field": "memory.memory_injection.enabled", "kind": "partial_mapping",
                            "explain": "新版开关控制自动相关记忆检索；核心记忆、工具查询及原文采集分别管理，不等同于旧版全部注入。"})

    for path, value in _leaves(source):
        if path in FIELDS or path == "memory_injection.enabled" or path == SUMMARY_TIMEOUT:
            continue
        if path in SUMMARY_MODELS:
            continue
        if path in RECALL_SCOPES and type(value) is not bool:
            kind, explain = "invalid_value", "旧私聊或群聊召回开关类型无效，未据此开启新版自动检索。"
        elif path.startswith(("scope_control.", "visibility.", "private_companion_bridge.")):
            kind, explain = "changed_semantics", "旧窗口开关、跨窗桥接和可见性不等同于新版角色及受众权限；未自动扩大记忆共享范围。"
        elif path.startswith(("retrieval.", "retrieval_advanced.")):
            kind, explain = "changed_semantics", "新版检索模型与语义索引还供表情包和黑话使用，旧记忆专用模型及索引参数未写入共享设置。"
        elif path.startswith(("memory_capture.", "memory_summary.", "portrait.",
                              "conversation_memory.", "conversation_memory_advanced.")):
            kind, explain = "changed_semantics", "旧采集、摘要及画像链已由新版原文记录和反思链承接，开关与调度条件不能按名称替换。"
        else:
            kind, explain = "changed_semantics", "旧工具、上下文编排或维护参数没有同义消费入口，保留旧配置供核对。"
        differences.append({"field": "memory." + path, "kind": kind, "explain": explain})
    if enabled is True and (not valid_scopes or disabled_scopes) and len(disabled_scopes) != len(RECALL_SCOPES):
        differences.append({"field": "memory.automatic_context", "kind": "scope_review_required",
                            "explain": "旧私聊与群聊召回设置不一致或无效，未将其覆盖为角色通用开关；请在对应用户或群聊页核对。"})
    return MemoryConfigurationMigration(changes, sources, tuple(differences))
