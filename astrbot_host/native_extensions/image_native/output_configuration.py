"""The dashboard edits the same independent V2 settings that execute images."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

from .types import NativeImageError, fingerprint

BACKENDS = {"auto", "online_api", "sd_webui", "comfyui"}
PLATFORMS = {"auto", "openai", "minimax"}


def settings(plugin):
    native = plugin.config.get("native_v2", {})
    saved = native.get("output")
    if isinstance(saved, dict):
        return copy.deepcopy(saved)
    connection = copy.deepcopy(native.get("connection", {}))
    return {"enabled": native.get("enabled") is True,
            "backend": native.get("backend", "sd_webui"), "endpoints": [],
            "sd_webui": connection if native.get("backend") != "comfyui" else {},
            "comfyui": connection if native.get("backend") == "comfyui" else {}}


def public_configuration(plugin):
    source = settings(plugin)
    result = copy.deepcopy(source)
    for item in [*result.get("endpoints", []), result.get("sd_webui", {}), result.get("comfyui", {})]:
        item["api_key_set"] = bool(item.pop("api_key", ""))
    provider = getattr(plugin, "_native_v2_provider", None)
    return {"revision": fingerprint(source), "settings": result,
            "live": bool(provider and not provider._closed),
            "limits": {"max_endpoints": 24, "timeout_min": 1, "timeout_max": 1800},
            "supported_backends": sorted(BACKENDS), "supported_platforms": sorted(PLATFORMS)}


def _connection(value, previous):
    if not isinstance(value, dict) or value.keys() - {"base_url", "api_key", "api_key_set", "clear_api_key",
            "timeout_seconds", "parameters", "workflows"}:
        raise NativeImageError("invalid_configuration")
    result = copy.deepcopy(value)
    result.pop("api_key_set", None)
    clear = result.pop("clear_api_key", False)
    key = result.get("api_key", "")
    if not isinstance(key, str) or type(clear) is not bool:
        raise NativeImageError("invalid_configuration")
    result["api_key"] = "" if clear else key or previous.get("api_key", "")
    raw = result.get("base_url", "")
    if not isinstance(raw, str):
        raise NativeImageError("invalid_configuration")
    if raw:
        url = urlsplit(raw)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.fragment:
            raise NativeImageError("invalid_configuration")
    timeout = result.get("timeout_seconds", 300)
    if type(timeout) is not int or not 1 <= timeout <= 1800:
        raise NativeImageError("invalid_configuration")
    result["timeout_seconds"] = timeout
    for key in ("parameters", "workflows"):
        if key in result:
            raw_value = result[key]
            if isinstance(raw_value, str):
                try:
                    raw_value = json.loads(raw_value)
                except ValueError as exc:
                    raise NativeImageError("invalid_configuration") from exc
            if not isinstance(raw_value, dict):
                raise NativeImageError("invalid_configuration")
            result[key] = raw_value
    return result


def save_configuration(plugin, revision, changes):
    before = settings(plugin)
    if fingerprint(before) != revision:
        raise NativeImageError("configuration_conflict")
    if not isinstance(changes, dict) or changes.keys() - {"enabled", "backend", "endpoints", "sd_webui", "comfyui"}:
        raise NativeImageError("invalid_configuration")
    candidate = {**before, **copy.deepcopy(changes)}
    if type(candidate.get("enabled")) is not bool or candidate.get("backend") not in BACKENDS:
        raise NativeImageError("invalid_configuration")
    for name in ("sd_webui", "comfyui"):
        candidate[name] = _connection(candidate.get(name, {}), before.get(name, {}))
    endpoints = candidate.get("endpoints")
    if not isinstance(endpoints, list) or len(endpoints) > 24:
        raise NativeImageError("invalid_configuration")
    ids = set()
    previous = {item["id"]: item for item in before.get("endpoints", [])}
    normalized = []
    for item in endpoints:
        if not isinstance(item, dict) or item.keys() - {"id", "name", "enabled", "platform", "model",
                "width", "height", "base_url", "api_key", "api_key_set", "clear_api_key", "timeout_seconds"}:
            raise NativeImageError("invalid_configuration")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 128 or identifier in ids:
            raise NativeImageError("invalid_configuration")
        ids.add(identifier)
        if (type(item.get("enabled")) is not bool or item.get("platform") not in PLATFORMS
                or any(type(item.get(key)) is not str or len(item[key]) > 240 for key in ("name", "model"))
                or any(type(item.get(key)) is not int or not 64 <= item[key] <= 8192 for key in ("width", "height"))):
            raise NativeImageError("invalid_configuration")
        connection = _connection({key:value for key,value in item.items() if key in
            {"base_url", "api_key", "api_key_set", "clear_api_key", "timeout_seconds"}}, previous.get(identifier, {}))
        normalized.append({**item, **connection})
        normalized[-1].pop("api_key_set", None)
        normalized[-1].pop("clear_api_key", None)
    candidate["endpoints"] = normalized
    if candidate["enabled"] and candidate["backend"] == "online_api" and not any(
            endpoint["enabled"] and endpoint["base_url"] and endpoint["model"]
            for endpoint in normalized):
        raise NativeImageError("invalid_configuration")
    for name in ("sd_webui", "comfyui"):
        connection = candidate[name]
        if connection.get("base_url"):
            from .backends import NativeTransportBackend
            NativeTransportBackend(name, connection, Path(plugin.data_dir) / "native_v2" / "validate")
    provider = getattr(plugin, "_native_v2_provider", None)
    if provider and provider.owner._tasks:
        raise NativeImageError("configuration_busy")
    from .output_routing import OutputRoutingBackend
    backend = OutputRoutingBackend(candidate, Path(plugin.data_dir) / "native_v2" / "transport")
    original = copy.deepcopy(plugin.config.get("native_v2", {}))
    saver = getattr(plugin.config, "save_config", None)
    if not callable(saver):
        raise NativeImageError("configuration_store_unavailable")
    try:
        plugin.config["native_v2"] = {**original, "enabled": candidate["enabled"],
                                      "backend": candidate["backend"], "output": candidate}
        saver()
    except Exception as exc:
        plugin.config["native_v2"] = original
        raise NativeImageError("configuration_save_failed") from exc
    if provider:
        provider.owner.backend = backend
        provider._closed = not candidate["enabled"]
        provider.wait_budget_seconds = 1800
    elif candidate["enabled"]:
        from .bootstrap import build_provider
        from ... import main
        plugin._native_v2_provider = build_provider(plugin, version=main.PLUGIN_VERSION)
    plugin._native_v2_mode = candidate["enabled"]
    return public_configuration(plugin)
