"""Read-only access to V1 plugin settings stored by AstrBot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


V1_PLUGIN_DATA_NAME = "astrbot_plugin_private_companion"
V1_HOST_CONFIG_NAME = V1_PLUGIN_DATA_NAME + "_config.json"


def v1_host_config_path(data_root) -> Path | None:
    """Locate the V1 settings file beside this plugin's AstrBot data root."""
    base = Path(data_root)
    for parent in (base.parent.parent, base.parent):
        path = parent / "config" / V1_HOST_CONFIG_NAME
        if path.is_file():
            return path
    return None


def read_v1_host_configuration(data_root):
    """Return decoded settings, path and byte fingerprint without writing V1."""
    path = v1_host_config_path(data_root)
    if path is None:
        return None, None, ""
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if type(value) is not dict:
        raise ValueError("V1 plugin settings must be an object")
    return value, path, hashlib.sha256(raw).hexdigest()


__all__ = ["V1_HOST_CONFIG_NAME", "V1_PLUGIN_DATA_NAME", "read_v1_host_configuration",
           "v1_host_config_path"]
