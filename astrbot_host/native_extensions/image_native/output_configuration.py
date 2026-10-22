"""The dashboard edits the same independent V2 settings that execute images."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

from .types import NativeImageError, fingerprint

BACKENDS = {"auto", "online_api", "sd_webui", "comfyui"}
# Keep the complete V1 provider vocabulary in the persisted contract.  A saved
# provider can be shown and edited even when its protocol adapter is not loaded;
# routing reports it as unsupported instead of silently changing it to OpenAI.
PLATFORMS = {
    "auto", "openai", "openrouter", "agnes", "sensenova", "minimax",
    "bailian", "modelscope", "doubao", "gemini",
}
IMAGE_QUALITIES = {"auto", "low", "medium", "high", "standard", "hd"}
IMAGE_OPERATIONS = ("generate", "edit")
LOCAL_ROUTES = {"comfyui", "sd_webui"}


def _default_operation_routes(value):
    selected = value.get("backend", "auto")
    endpoints = value.get("endpoints", [])
    if not isinstance(selected, str) or selected not in BACKENDS:
        selected = "auto"
    if not isinstance(endpoints, list):
        endpoints = []
    online = ["online:" + item["id"] for item in endpoints
              if isinstance(item, dict) and isinstance(item.get("id"), str)]
    routes = []
    if selected in {"auto", "online_api"}:
        routes.extend(online)
    if selected in {"auto", "comfyui"}:
        routes.append("comfyui")
    if selected in {"auto", "sd_webui"}:
        routes.append("sd_webui")
    return {operation: list(routes) for operation in IMAGE_OPERATIONS}


def _stored_operation_routes(value):
    defaults = _default_operation_routes(value)
    raw = value.get("operation_routes")
    if not isinstance(raw, dict) or raw.keys() - set(IMAGE_OPERATIONS):
        return defaults
    endpoints = value.get("endpoints", [])
    endpoint_ids = {item["id"] for item in endpoints
                    if isinstance(item, dict) and isinstance(item.get("id"), str)}
    result = {}
    for operation in IMAGE_OPERATIONS:
        routes = raw.get(operation)
        if not isinstance(routes, list):
            result[operation] = defaults[operation]
            continue
        seen = set()
        normalized = []
        for route in routes:
            if not isinstance(route, str) or route in seen:
                continue
            if route in LOCAL_ROUTES or (route.startswith("online:") and route[7:] in endpoint_ids):
                normalized.append(route)
                seen.add(route)
        result[operation] = normalized
    return result


def _validate_operation_routes(value, endpoints):
    raw = value.get("operation_routes")
    if raw is None:
        return _default_operation_routes(value)
    if not isinstance(raw, dict) or raw.keys() - set(IMAGE_OPERATIONS):
        raise NativeImageError("invalid_configuration")
    endpoint_ids = {item["id"] for item in endpoints}
    result = {}
    for operation in IMAGE_OPERATIONS:
        routes = raw.get(operation)
        if not isinstance(routes, list) or len(routes) > 26:
            raise NativeImageError("invalid_configuration")
        seen = set()
        normalized = []
        for route in routes:
            if not isinstance(route, str) or route in seen:
                raise NativeImageError("invalid_configuration")
            if route in LOCAL_ROUTES:
                normalized.append(route)
            elif route.startswith("online:") and route[7:] in endpoint_ids:
                normalized.append(route)
            else:
                raise NativeImageError("invalid_configuration")
            seen.add(route)
        result[operation] = normalized
    return result


def settings(plugin):
    native = plugin.config.get("native_v2", {})
    saved = native.get("output")
    if isinstance(saved, dict):
        result = copy.deepcopy(saved)
        result.setdefault("legacy_backend", "")
        result.setdefault("legacy_options", {})
        result.setdefault("network", {})
        for endpoint in result.get("endpoints", []):
            if isinstance(endpoint, dict):
                endpoint.setdefault("quality", "standard")
                endpoint.setdefault("max_reference_images", 1)
                endpoint.setdefault("size_label", f"{endpoint.get('width', 1024)}x{endpoint.get('height', 1024)}")
        result["operation_routes"] = _stored_operation_routes(result)
        return result
    connection = copy.deepcopy(native.get("connection", {}))
    result = {"enabled": native.get("enabled") is True,
              "backend": native.get("backend", "sd_webui"), "endpoints": [],
              "legacy_backend": "",
              "legacy_options": {}, "network": {},
              "sd_webui": connection if native.get("backend") != "comfyui" else {},
              "comfyui": connection if native.get("backend") == "comfyui" else {}}
    result["operation_routes"] = _default_operation_routes(result)
    return result


def public_configuration(plugin):
    source = settings(plugin)
    result = copy.deepcopy(source)
    for item in [*result.get("endpoints", []), result.get("sd_webui", {}), result.get("comfyui", {})]:
        headers = item.pop("custom_headers", None)
        item["custom_headers_set"] = bool(headers)
        item["custom_header_names"] = sorted(headers) if isinstance(headers, dict) else []
        item["api_key_set"] = bool(item.pop("api_key", ""))
    network = result.setdefault("network", {})
    network["download_proxy_set"] = bool(network.pop("download_proxy", ""))
    provider = getattr(plugin, "_native_v2_provider", None)
    return {"revision": fingerprint(source), "settings": result,
            "live": bool(provider and not provider._closed),
            "limits": {"max_endpoints": 24, "timeout_min": 1, "timeout_max": 1800},
            "supported_backends": sorted(BACKENDS), "supported_platforms": sorted(PLATFORMS)}


def _network(value, previous):
    if not isinstance(value, dict) or value.keys() - {"download_proxy", "download_proxy_set",
                                                       "use_environment_proxy", "clear_download_proxy"}:
        raise NativeImageError("invalid_configuration")
    result = copy.deepcopy(value)
    proxy = result.get("download_proxy", previous.get("download_proxy", ""))
    use_environment_proxy = result.get("use_environment_proxy", previous.get("use_environment_proxy", False))
    result.pop("download_proxy_set", None)
    clear = result.pop("clear_download_proxy", False)
    if (not isinstance(proxy, str) or len(proxy) > 2048 or type(use_environment_proxy) is not bool
            or type(clear) is not bool):
        raise NativeImageError("invalid_configuration")
    if clear:
        proxy = ""
    elif not proxy:
        proxy = previous.get("download_proxy", "")
    if proxy:
        try:
            parsed = urlsplit(proxy)
        except ValueError as exc:
            raise NativeImageError("invalid_configuration") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password \
        or parsed.fragment:
            raise NativeImageError("invalid_configuration")
    return {"download_proxy": proxy.rstrip("/"), "use_environment_proxy": use_environment_proxy}


def _legacy_options(value, previous):
    if value is None:
        value = previous or {}
    if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False)) > 20000:
        raise NativeImageError("invalid_configuration")
    try:
        encoded = json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise NativeImageError("invalid_configuration") from exc
    return encoded


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
        try:
            url = urlsplit(raw)
        except ValueError as exc:
            raise NativeImageError("invalid_configuration") from exc
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
    if not isinstance(changes, dict) or changes.keys() - {
            "enabled", "backend", "legacy_backend", "legacy_options", "network", "endpoints", "sd_webui",
            "comfyui", "operation_routes"}:
        raise NativeImageError("invalid_configuration")
    candidate = {**before, **copy.deepcopy(changes)}
    if (type(candidate.get("enabled")) is not bool or candidate.get("backend") not in BACKENDS
            or not isinstance(candidate.get("legacy_backend", ""), str)
            or len(candidate.get("legacy_backend", "")) > 64):
        raise NativeImageError("invalid_configuration")
    candidate["legacy_options"] = _legacy_options(candidate.get("legacy_options"), before.get("legacy_options", {}))
    candidate["network"] = _network(candidate.get("network", {}), before.get("network", {}))
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
                "width", "height", "size_label", "quality", "max_reference_images", "base_url", "api_key", "api_key_set",
                "clear_api_key", "clear_custom_headers", "timeout_seconds", "custom_headers", "custom_headers_set",
                "custom_header_names", "ratio"}:
            raise NativeImageError("invalid_configuration")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 128 or identifier in ids:
            raise NativeImageError("invalid_configuration")
        ids.add(identifier)
        quality = item.get("quality", "standard")
        max_reference_images = item.get("max_reference_images", 1)
        if (type(item.get("enabled")) is not bool or item.get("platform") not in PLATFORMS
                or any(type(item.get(key)) is not str or len(item[key]) > 240 for key in ("name", "model"))
                or any(type(item.get(key)) is not int or not 64 <= item[key] <= 8192 for key in ("width", "height"))
                or ("size_label" in item and (not isinstance(item.get("size_label"), str)
                                               or len(item.get("size_label", "")) > 64))
                or quality not in IMAGE_QUALITIES
                or type(max_reference_images) is not int or not 0 <= max_reference_images <= 8):
            raise NativeImageError("invalid_configuration")
        clear_headers = item.get("clear_custom_headers", False)
        if type(clear_headers) is not bool:
            raise NativeImageError("invalid_configuration")
        headers = {} if clear_headers else item.get("custom_headers", previous.get(identifier, {}).get("custom_headers", {}))
        if headers in (None, ""):
            headers = {}
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except ValueError as exc:
                raise NativeImageError("invalid_configuration") from exc
        if (type(headers) is not dict or len(headers) > 32
                or any(not isinstance(key, str) or not key or len(key) > 80
                       or not isinstance(value, str) or len(value) > 2000
                       or "\r" in value or "\n" in value for key, value in headers.items())):
            raise NativeImageError("invalid_configuration")
        ratio = item.get("ratio", "")
        if not isinstance(ratio, str) or len(ratio) > 20:
            raise NativeImageError("invalid_configuration")
        connection = _connection({key:value for key,value in item.items() if key in
            {"base_url", "api_key", "api_key_set", "clear_api_key", "timeout_seconds"}}, previous.get(identifier, {}))
        normalized.append({**item, "size_label": item.get("size_label", f"{item.get('width')}x{item.get('height')}"),
                           **connection, "custom_headers": headers, "ratio": ratio, "quality": quality,
                           "max_reference_images": max_reference_images})
        normalized[-1].pop("api_key_set", None)
        normalized[-1].pop("clear_api_key", None)
        normalized[-1].pop("clear_custom_headers", None)
        normalized[-1].pop("custom_headers_set", None)
        normalized[-1].pop("custom_header_names", None)
    candidate["endpoints"] = normalized
    if "operation_routes" not in changes:
        if "backend" in changes and changes["backend"] != before.get("backend"):
            candidate["operation_routes"] = _default_operation_routes(candidate)
        else:
            valid_refs = {"online:" + item["id"] for item in normalized} | LOCAL_ROUTES
            routes = before.get("operation_routes") or _default_operation_routes(before)
            candidate["operation_routes"] = {
                operation: [route for route in routes.get(operation, []) if route in valid_refs]
                for operation in IMAGE_OPERATIONS}
            previous_ids = {item["id"] for item in before.get("endpoints", []) if isinstance(item, dict)}
            new_refs = ["online:" + item["id"] for item in normalized if item["id"] not in previous_ids]
            for operation in IMAGE_OPERATIONS:
                candidate["operation_routes"][operation].extend(new_refs)
    candidate["operation_routes"] = _validate_operation_routes(candidate, normalized)
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
    if candidate["enabled"] and not backend.operations:
        raise NativeImageError("native_endpoint_unconfigured")
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
