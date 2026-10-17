"""Safe V1 Reality Companion configuration conversion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


REALITY_SETTING_DEFAULTS = {
    "camera.enabled": False,
    "camera.min_interval_seconds": 60,
    "camera.capture_timeout_seconds": 5,
    "camera.analysis_timeout_seconds": 25,
    "audio.default_playback_volume": 35,
    "timezone": "Asia/Shanghai",
}


@dataclass(frozen=True)
class RealityConfigurationMigration:
    changes: dict[str, Any]
    differences: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


def _value_at(config: Any, dotted_key: str, default=None):
    current = config
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def reality_setting_value(config: Any, dotted_key: str, default=None):
    return _value_at(config, dotted_key, default)


def reality_settings_state_token(config: Any, fields=None) -> str:
    keys = tuple(sorted(fields or REALITY_SETTING_DEFAULTS))
    state = {key: _value_at(config, key, REALITY_SETTING_DEFAULTS.get(key)) for key in keys}
    encoded = json.dumps(state, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _boolean(value):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "enabled", "开启", "启用"}:
            return True
        if normalized in {"false", "0", "no", "off", "disabled", "关闭", "停用"}:
            return False
    return None


def _bounded_int(value, minimum, maximum):
    if type(value) is bool or not isinstance(value, (int, str)):
        return None
    try:
        text = str(value).strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            return None
        converted = int(text)
    except (TypeError, ValueError):
        return None
    return converted if minimum <= converted <= maximum else None


def convert_reality_configuration(source) -> RealityConfigurationMigration:
    """Convert only portable settings; identities, credentials, and device IDs stay put."""
    if not isinstance(source, dict):
        return RealityConfigurationMigration({}, (), ("V1 Reality 配置不是可识别的对象，本次没有迁移设置。",))

    changes: dict[str, Any] = {}
    differences: list[dict[str, str]] = []
    camera = source.get("camera") if isinstance(source.get("camera"), dict) else {}
    audio = source.get("audio") if isinstance(source.get("audio"), dict) else {}

    boolean = _boolean(camera.get("enabled"))
    if boolean is not None:
        changes["camera.enabled"] = boolean

    for key, minimum, maximum in (
        ("min_interval_seconds", 10, 3600),
        ("capture_timeout_seconds", 2, 20),
        ("analysis_timeout_seconds", 5, 90),
    ):
        if key not in camera:
            continue
        converted = _bounded_int(camera[key], minimum, maximum)
        target = f"camera.{key}"
        if converted is None:
            differences.append({
                "field": f"reality.{target}",
                "kind": "invalid_value",
                "explain": "V1 数值超出 V2 支持范围或格式无效，已跳过此项。",
            })
        else:
            changes[target] = converted

    if "default_playback_volume" in audio:
        volume = _bounded_int(audio["default_playback_volume"], 0, 100)
        if volume is None:
            differences.append({
                "field": "reality.audio.default_playback_volume",
                "kind": "invalid_value",
                "explain": "V1 音量不是 0 到 100 的整数，已跳过此项。",
            })
        else:
            changes["audio.default_playback_volume"] = volume

    timezone = source.get("timezone")
    if isinstance(timezone, str) and timezone.strip():
        timezone = timezone.strip()
        if len(timezone) <= 80:
            try:
                ZoneInfo(timezone)
            except (ValueError, ZoneInfoNotFoundError):
                differences.append({
                    "field": "reality.timezone",
                    "kind": "invalid_value",
                    "explain": "V1 时区在当前环境不可用，已跳过此项。",
                })
            else:
                changes["timezone"] = timezone

    if "index" in camera:
        differences.append({
            "field": "reality.camera.index",
            "kind": "device_mapping_required",
            "before": str(camera["index"])[:24],
            "explain": "摄像头索引由当前设备扫描确定，V1 索引不会直接复用。",
        })
    if camera.get("proactive_curiosity_enabled") is True:
        differences.append({
            "field": "reality.camera.proactive_curiosity_enabled",
            "kind": "v2_confirmation_required",
            "explain": "主动摄像头策略不从旧配置启用；请在 V2 按当前角色和授权单独设置。",
        })
    if source.get("vision_provider_id"):
        differences.append({
            "field": "reality.vision_provider_id",
            "kind": "provider_reselection_required",
            "explain": "视觉提供方 ID 属于宿主安装配置，请在 V2 重新选择。",
        })
    if source.get("authorized_user_ids"):
        differences.append({
            "field": "reality.authorized_user_ids",
            "kind": "identity_rebinding_required",
            "explain": "旧版用户授权不会迁成 V2 身份授权，请在 V2 按当前私聊身份重新确认。",
        })

    return RealityConfigurationMigration(
        changes=changes,
        differences=tuple(differences),
        warnings=(
            "本次只迁移摄像头基础参数、默认音量及时区；V2 已有非默认设置会保留。",
            "设备索引、授权、视觉提供方、扬声器路由、提醒与历史数据不会从 V1 复制。",
        ),
    )
