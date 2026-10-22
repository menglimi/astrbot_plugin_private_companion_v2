"""Preserve the legacy host settings before AstrBot normalizes the new schema."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4


CONFIG_NAME = "astrbot_plugin_private_companion_config.json"
ARCHIVE_DIRECTORY = ".private-companion-upgrade"


def is_legacy_configuration(value):
    return isinstance(value, dict) and any(key in value for key in (
        "basic_config", "legacy_compat_config", "target_user_ids", "LLM_PROVIDER_ID",
    ))


def _has_value(value):
    """Whether a stored legacy value carries data worth preserving."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _value_at_path(value, path):
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _preserved_values_would_be_lost(previous, candidate):
    """Keep an earlier source when a later legacy-shaped file is pruned.

    AstrBot can rewrite a plugin config while a replacement schema is being
    loaded. The rewritten document may still contain V1 marker keys, so marker
    detection alone cannot distinguish it from the original V1 configuration.
    Compare populated paths instead of ranking documents by size: schema
    defaults can make a pruned document larger than the original.
    """
    pending = [((), previous)]
    while pending:
        path, value = pending.pop()
        if isinstance(value, dict):
            pending.extend((path + (key,), child) for key, child in value.items())
            continue
        if not _has_value(value):
            continue
        later = _value_at_path(candidate, path)
        if not _has_value(later):
            return True
        if isinstance(value, list) and isinstance(later, list):
            # A list can carry several independent targets/assets. Retain the
            # source if even one earlier item disappears from the later copy.
            if any(item not in later for item in value):
                return True
    return False


def preserved_configuration_path(directory):
    archive = Path(directory) / ARCHIVE_DIRECTORY
    pointer = archive / "source.json"
    if not pointer.is_file():
        return None
    document = json.loads(pointer.read_text(encoding="utf-8"))
    fingerprint = document.get("sha256", "")
    if (not isinstance(fingerprint, str) or len(fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in fingerprint)):
        raise ValueError("the saved upgrade source fingerprint is invalid")
    source = archive / (fingerprint + ".json")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != fingerprint:
        raise ValueError("the saved upgrade configuration changed")
    if not is_legacy_configuration(json.loads(raw.decode("utf-8-sig"))):
        raise ValueError("the saved upgrade source is not a legacy configuration")
    return source


def preserve_before_schema(directory):
    """Archive exact bytes; fail before schema pruning if preservation is impossible."""
    directory = Path(directory)
    source = directory / CONFIG_NAME
    if not source.is_file():
        return None
    raw = source.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if not is_legacy_configuration(value):
        return preserved_configuration_path(directory)
    existing = preserved_configuration_path(directory)
    if existing is not None:
        previous = json.loads(existing.read_text(encoding="utf-8-sig"))
        if _preserved_values_would_be_lost(previous, value):
            # Keep an audit copy of the later document, but do not let a
            # defaulted/pruned configuration replace the migration source.
            fingerprint = hashlib.sha256(raw).hexdigest()
            archive = directory / ARCHIVE_DIRECTORY
            archive.mkdir(parents=True, exist_ok=True)
            destination = archive / (fingerprint + ".json")
            if destination.exists():
                if destination.read_bytes() != raw:
                    raise ValueError("the upgrade archive is inconsistent")
            else:
                temporary = archive / ("." + uuid4().hex + ".tmp")
                try:
                    with temporary.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            return existing
    fingerprint = hashlib.sha256(raw).hexdigest()
    archive = directory / ARCHIVE_DIRECTORY
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / (fingerprint + ".json")
    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValueError("the upgrade archive is inconsistent")
    else:
        temporary = archive / ("." + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    pointer = archive / "source.json"
    document = {"format": "private-companion.upgrade-source.v1", "sha256": fingerprint}
    temporary = archive / ("." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, pointer)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def preserve_host_configuration():
    from astrbot.core.utils.astrbot_path import get_astrbot_config_path
    return preserve_before_schema(get_astrbot_config_path())
