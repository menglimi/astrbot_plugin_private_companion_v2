"""Copy only selected V2 source into an installation outside the live scanner."""

import hashlib
import os
from pathlib import Path

from tools.native_acceptance_guard import LEGACY_IDS, scan_dependencies

CORE_ID = "astrbot_plugin_private_companion"
EXCLUDED = {"data", "__pycache__", ".git", ".pytest_cache", "node_modules", "dist", "build", "logs"}


def outside_scan(path, source):
    path, source = Path(path).resolve(), Path(source).resolve()
    if path.is_relative_to(source.parent):
        raise ValueError("native acceptance output and scratch must be outside the plugin scanner")
    return path


def snapshot(source, destination):
    source, destination = Path(source).resolve(), outside_scan(destination, source)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("native acceptance installation must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    selected = [source / p for p in ("main.py", "metadata.yaml", "_conf_schema.json", "requirements.txt")]
    for name in ("astrbot_host", "companion_v2", "tests", "tools"):
        for base, dirs, files in os.walk(source / name, followlinks=False):
            for child in dirs:
                p = Path(base) / child
                if p.is_symlink() or not p.resolve().is_relative_to(source):
                    raise ValueError("source link escapes the selected native package")
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
            selected.extend(Path(base) / f for f in files if f.endswith(".py"))
    hashes, findings = {}, []
    for path in sorted(selected):
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("source link escapes the selected native package")
        if not path.is_file():
            raise ValueError("native source is incomplete")
        relative = path.relative_to(source)
        payload = path.read_bytes()
        if path.suffix == ".py" and relative.parts[0] in {"main.py", "astrbot_host", "companion_v2"}:
            findings.extend(scan_dependencies(payload.decode("utf-8-sig"), relative.as_posix()))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
    assert not any((destination.parent / name).exists() for name in LEGACY_IDS)
    if findings:
        raise ValueError("legacy executable dependency in native source: " + repr(findings))
    return {"files": hashes, "legacy_static_findings": findings}


def snapshot_image(source, destination):
    """Copy the independent Image native module, never its V1 entry or stores.

    This verifies native-provider independence, not a legacy plugin entry load.
    The real namespace initializers and synthetic backend are copied unchanged.
    """
    source, destination = Path(source).resolve(), outside_scan(destination, source)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("native provider installation must be new or empty")
    selected = [source / p for p in ("__init__.py", "image_companion/__init__.py", "tests/native_v2_support.py",
        "image_native_client.py", "comfyui_service.py", "comfyui_workflows.py", "comfyui_prompts.py",
        "reference_receipt.py", "image_operations.py", "image_preparation_task.py")]
    native = source / "image_companion" / "native_v2"
    for base, dirs, files in os.walk(native, followlinks=False):
        for child in dirs:
            path = Path(base) / child
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError("native provider source link escapes its package")
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        selected.extend(Path(base) / f for f in files if f.endswith(".py"))
    if not (native / "adapter.py").is_file():
        raise ValueError("Image native provider source is unavailable")
    hashes, findings = {}, []
    for path in sorted(selected):
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("native provider source link escapes its package")
        relative = path.relative_to(source)
        payload = path.read_bytes()
        if relative.parts[0] != "tests":
            findings.extend(scan_dependencies(payload.decode("utf-8-sig"), relative.as_posix()))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
    if findings:
        raise ValueError("legacy executable dependency in native provider: " + repr(findings))
    return {"files": hashes, "legacy_static_findings": findings}
