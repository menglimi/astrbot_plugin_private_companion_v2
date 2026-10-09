"""Atomic, role-scoped Laya configuration stored under the V2 data root."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shlex
import sys
from pathlib import Path
from uuid import uuid4


DEFAULTS = {
    "enabled": False,
    "mode": "local",
    "endpoint": "",
    "api_key": "",
    "timeout_seconds": 20,
}
ALLOWED_CHANGES = frozenset(DEFAULTS)
MODEL_REPOSITORY = "models--convaiinnovations--laya"


class LayaSettingsError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def role_storage_key(target_id: object, role_id: object) -> str:
    raw = f"{target_id or 'installation'}\0{role_id or 'default'}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _model_cache_dir() -> Path:
    configured = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if configured:
        return Path(configured).expanduser()
    home = Path(os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface")).expanduser()
    return home / "hub"


def _has_multilingual_model(snapshot: Path) -> bool:
    model = snapshot / "multilingual"
    required_files = (
        model / "rl_agent_config.json",
        model / "model.safetensors",
        model / "tokenizer" / "tokenizer.json",
        model / "encoder" / "config.json",
    )
    return all(path.is_file() for path in required_files)


def _install_command() -> str:
    executable = str(Path(sys.executable).resolve())
    if os.name == "nt":
        quote = lambda value: "'" + value.replace("'", "''") + "'"
        return f"& {quote(executable)} -m pip install 'laya==0.4.0'"
    return f"{shlex.quote(executable)} -m pip install 'laya==0.4.0'"


def _remote_commands() -> tuple[str, str]:
    executable = str(Path(sys.executable).resolve())
    if os.name == "nt":
        quote = lambda value: "'" + value.replace("'", "''") + "'"
        install = f"& {quote(executable)} -m pip install 'laya[serve]==0.4.0'"
        start = f"$env:LAYA_DEFAULT_MODEL='multilingual'; & {quote(executable)} -m laya.serve"
    else:
        install = f"{shlex.quote(executable)} -m pip install 'laya[serve]==0.4.0'"
        start = f"LAYA_DEFAULT_MODEL=multilingual {shlex.quote(executable)} -m laya.serve"
    return install, start


def _package_status() -> tuple[bool, str]:
    try:
        installed = importlib.util.find_spec("laya") is not None
    except (ImportError, ValueError):
        installed = False
    try:
        version = importlib.metadata.version("laya")
    except importlib.metadata.PackageNotFoundError:
        version = ""
    return installed, version


class LayaSettingsStore:
    def __init__(self, root: Path, target_id: object = "installation", role_id: object = "default"):
        self.root = Path(root).resolve()
        self.directory = self.root / "decision" / "roles"
        self.path = self.directory / (role_storage_key(target_id, role_id) + ".json")

    def _read(self) -> dict:
        if not self.path.exists():
            return {**DEFAULTS, "revision": "initial"}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise LayaSettingsError("laya_config_unreadable", "Laya 配置不可读取") from error
        if type(data) is not dict:
            raise LayaSettingsError("laya_config_invalid", "Laya 配置格式无效")
        values = {**DEFAULTS, **{key: data.get(key, default) for key, default in DEFAULTS.items()}}
        # Read the first integration's mode-less settings as a remote endpoint setup.
        if "mode" not in data and values["endpoint"]:
            values["mode"] = "remote"
        revision = data.get("revision")
        values["revision"] = revision if type(revision) is str and revision else uuid4().hex
        self._validate(values)
        return values

    @staticmethod
    def _validate(values: dict) -> None:
        if type(values["enabled"]) is not bool:
            raise LayaSettingsError("laya_config_invalid", "enabled 必须是布尔值")
        if values["mode"] not in {"local", "remote"}:
            raise LayaSettingsError("laya_config_invalid", "mode 必须是 local 或 remote")
        for key in ("endpoint", "api_key"):
            if type(values[key]) is not str or len(values[key]) > 4096:
                raise LayaSettingsError("laya_config_invalid", f"{key} 配置无效")
        if type(values["timeout_seconds"]) is not int or isinstance(values["timeout_seconds"], bool) or not 1 <= values["timeout_seconds"] <= 120:
            raise LayaSettingsError("laya_config_invalid", "timeout_seconds 超出范围")

    def read(self) -> dict:
        values = self._read()
        installed, version = _package_status()
        cache_dir = _model_cache_dir()
        snapshots = cache_dir / MODEL_REPOSITORY / "snapshots"
        try:
            model_cache_ready = snapshots.is_dir() and any(
                snapshot.is_dir() and _has_multilingual_model(snapshot)
                for snapshot in snapshots.iterdir())
        except OSError:
            model_cache_ready = False
        remote_install_command, remote_start_command = _remote_commands()
        return {
            "enabled": values["enabled"],
            "mode": values["mode"],
            "endpoint": values["endpoint"],
            "default_model": "multilingual",
            "api_key_set": bool(values["api_key"]),
            "timeout_seconds": values["timeout_seconds"],
            "package_installed": installed,
            "package_version": version,
            "model_cache_ready": model_cache_ready,
            "model_cache_path": str(cache_dir),
            "python_executable": str(Path(sys.executable).resolve()),
            "install_command": _install_command(),
            "remote_install_command": remote_install_command,
            "remote_start_command": remote_start_command,
            "revision": values["revision"],
        }

    def raw(self) -> dict:
        return self._read()

    def update(self, revision: object, changes: object) -> dict:
        current = self._read()
        if type(revision) is not str or revision != current["revision"]:
            raise LayaSettingsError("laya_config_conflict", "Laya 配置已变化，请刷新后再保存")
        if type(changes) is not dict or not changes or set(changes) - ALLOWED_CHANGES:
            raise LayaSettingsError("laya_config_invalid", "Laya 配置字段无效")
        next_values = {**current, **changes}
        if "api_key" in changes and changes["api_key"] == "":
            next_values["api_key"] = current["api_key"]
        self._validate(next_values)
        next_values["revision"] = uuid4().hex
        self._write(next_values)
        return self.read()

    def _write(self, values: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name("." + self.path.name + "." + uuid4().hex + ".tmp")
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
