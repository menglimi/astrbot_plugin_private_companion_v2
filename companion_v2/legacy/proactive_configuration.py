"""Carry legacy contact preferences only to their verified persona and person."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .profile_source import primary_profile


DEFAULT_ENABLED_SOURCE = "basic_config.default_proactive_enabled"
DEFAULT_LIMIT_SOURCE = "basic_config.default_proactive_daily_limit"
PRIVATE_RELATIONSHIP = "private_contact_relationship"
PRIVATE_WINDOW = "private_contact_window"
PRIVATE_KINDS = frozenset({PRIVATE_RELATIONSHIP, PRIVATE_WINDOW})


def append_contact_defaults(config, registry, candidates, differences):
    from .configuration_migration import ConfigurationDifference, _boolean, _source_value

    present, raw = _source_value(config, DEFAULT_ENABLED_SOURCE)
    if not present and "default_proactive_enabled" in config:
        present, raw = True, config["default_proactive_enabled"]
    if not present:
        return
    try:
        enabled = _boolean(raw)
    except ValueError:
        differences.append(ConfigurationDifference("proactive.contact.enabled", "invalid_value",
            "旧版新用户主动开关无法识别，保留当前默认；个人主动偏好分别核对。", DEFAULT_ENABLED_SOURCE))
        return
    for name in ("enabled", "automatic_enabled"):
        target = "proactive.contact." + name
        field = registry.fields.get(target)
        if field is not None:
            candidates.setdefault(target, []).append(({"source": DEFAULT_ENABLED_SOURCE,
                "confidence": "high"}, field.validate(enabled)))


@dataclass(frozen=True)
class PrivateContactConfiguration:
    changes: dict
    sources: dict
    differences: tuple[dict, ...]
    fingerprint: str


def private_contact_configuration(root, configuration, *, persona_id, platform_id, account_id, participant_id):
    """Read preferences, never old plans, queues, pause state or send counters."""
    from .configuration_migration import _number
    from .data_migration import _persona_sources, _profile_data, _selected_profile

    def result(changes=None, sources=None, reason="", material=None):
        encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                             default=str).encode("utf-8")
        differences = ({"field": "proactive.contact", "kind": "manual_required",
            "source_key": "private.core_profiles.users", "explain": reason},) if reason else ()
        return PrivateContactConfiguration(changes or {}, sources or {}, differences,
                                           hashlib.sha256(encoded).hexdigest())

    if not all(type(value) is str and value.strip() for value in
               (persona_id, platform_id, account_id, participant_id)):
        return result(reason="尚未确认角色、账号和私聊用户，个人主动偏好未自动迁移。")
    primary = primary_profile(Path(root), configuration)
    if primary.payload is None:
        if primary.error == "core_profile_missing":
            return result()
        return result(reason="旧版角色档案无法确认，个人主动偏好未自动迁移。", material=primary.error)
    payload = _profile_data(primary.payload)
    ownership = payload.get("primary_store_ownership", {})
    owner = ownership.get("owner_persona_id", "") if isinstance(ownership, dict) else ""
    if not owner:
        basic = configuration.get("basic_config", {})
        owner = basic.get("plugin_specific_persona_id", "") if isinstance(basic, dict) else ""
        owner = owner or configuration.get("plugin_specific_persona_id", "")
    if owner != persona_id:
        inventory, _ = _persona_sources(Path(root), primary)
        selected, issue, _ = _selected_profile(Path(root), persona_id, inventory, primary)
        if selected is None or issue:
            return result(reason="当前角色与旧版档案的归属不一致，个人主动偏好未自动迁移。",
                          material=[owner, persona_id, issue])
        payload = _profile_data(selected)
        selected_owner = payload.get("primary_store_ownership", {})
        if isinstance(selected_owner, dict) and selected_owner.get("owner_persona_id", persona_id) != persona_id:
            return result(reason="旧版人格子档案归属冲突，个人主动偏好未自动迁移。")
    users = payload.get("users", {})
    if not isinstance(users, dict):
        return result(reason="旧版用户主动配置结构无效，未自动迁移。")
    matches = []
    for user_key, user in users.items():
        if not isinstance(user, dict):
            continue
        # Identity metadata is adapter evidence; numeric keys and display names
        # alone are insufficient across multiple accounts or merged profiles.
        if (user.get("identity_subject_id") != participant_id
                or user.get("identity_adapter_instance_id") != platform_id
                or user.get("identity_bot_id") != account_id
                or user.get("identity_platform_kind") not in ("onebot", "aiocqhttp")):
            continue
        matches.append((str(user_key), user))
    if not matches:
        return result(reason="没有找到与当前账号和私聊用户身份一致的旧主动配置，未扩大主动联系范围。",
                      material=[persona_id, platform_id, account_id, participant_id])
    records = []
    for key, user in matches:
        values, sources = {}, {}
        capabilities = user.get("unified_profile_capabilities")
        capability = capabilities.get("proactive_private_enabled") if isinstance(capabilities, dict) else None
        direct = user.get("proactive_private_enabled")
        if type(capability) is bool and type(direct) is bool and capability != direct:
            return result(reason="旧版个人主动开关与权限记录不一致，请核对后迁移。", material=[key, capability, direct])
        enabled = capability if type(capability) is bool else direct
        prefix = "private.core_profiles.users." + key + "."
        if type(enabled) is bool:
            values.update(enabled=enabled, automatic_enabled=enabled)
            source = prefix + ("unified_profile_capabilities.proactive_private_enabled"
                               if type(capability) is bool else "proactive_private_enabled")
            sources.update(enabled=(source,), automatic_enabled=(source,))
        for old, new, factor in (("proactive_daily_limit", "max_contacts_24h", 1),
                                 ("proactive_idle_minutes", "idle_seconds", 60),
                                 ("proactive_min_interval_minutes", "interval_seconds", 60)):
            raw = user.get(old)
            if raw in (None, ""):
                continue
            try:
                number = _number(raw, integer=True)
            except (TypeError, ValueError, OverflowError):
                return result(reason="旧版个人主动次数或间隔无效，未自动迁移。", material=[key, old, raw])
            if number == -1:
                continue  # The old sentinel inherits current global defaults.
            if number < 0:
                return result(reason="旧版个人主动次数或间隔无效，未自动迁移。", material=[key, old, raw])
            values[new], sources[new] = number * factor, (prefix + old,)
        records.append((values, sources))
    if any(values != records[0][0] for values, _ in records[1:]):
        return result(reason="同一私聊身份存在冲突的旧主动配置，请核对后迁移。", material=records)
    values, sources = records[0]
    return result(values, sources, material=[persona_id, platform_id, account_id, participant_id, records])
