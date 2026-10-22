"""Resolve and safely relocate the plugin-owned data directory at startup."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from uuid import uuid4

from companion_v2.storage.sqlite_path import readonly_uri


PLUGIN_NAME = "astrbot_plugin_private_companion_v2"
POINTER_NAME = ".companion-v2-storage-location.json"
OWNER_NAME = ".companion-v2-storage-owner.json"
_FORMAT = "companion-v2.storage-location.v1"
# 这个产品在 7.0.0 之前一直用带 _v2 的插件名；收编成 V1 的 7.0.0 之后，
# StarTools 会算出 V1 的数据目录，老用户的数据却还在下面这个目录里。
LEGACY_DATA_NAMES = ("astrbot_plugin_private_companion_v2",)
# 覆盖式更新（V2 顶替 V1 的插件身份）时，默认数据根就是 V1 的目录；
# V2 不能把库建在 V1 用户的数据里，改用这个子目录。
V2_SUBDIRECTORY = "companion-7"
# V1 的数据目录特征：它把全部陪伴数据放在这几个文件里。
_V1_MARKERS = ("companions.json", "companions.db", ".storage-backend-state.json")


def _looks_like_data_root(path: Path) -> bool:
    """目录里有没有本插件的数据（有 profiles、或者是带 ownership 指针的根）。"""
    if not path.is_dir():
        return False
    if (path / OWNER_NAME).is_file() or (path / POINTER_NAME).is_file():
        return True
    if any((path / name).exists() for name in _V1_MARKERS):
        return False
    return (path / "profiles").is_dir()


def _looks_like_v1_root(path: Path) -> bool:
    """这是不是 V1 的数据目录。

    覆盖式更新时 `PLUGIN_NAME` 等于 V1 的名字，StarTools 算出来的默认根正好是
    V1 的目录。V2 绝不能把库建在那儿（那就改了 V1 用户数据），所以先认出来，
    再换到它下面的 V2 专属子目录。
    """
    if not path.is_dir() or (path / OWNER_NAME).is_file() or (path / POINTER_NAME).is_file():
        return False
    return any((path / name).exists() for name in _V1_MARKERS)


def resolve_data_root(default_root: Path, *, legacy_names=LEGACY_DATA_NAMES) -> Path:
    """插件改名前后的数据根解析。

    优先级：现在的默认目录（已有 V2 数据就用它）→ 同级的旧名字目录（改名后老用户
    仍然能读到自己的库）→ V1 目录下的 V2 子目录（覆盖式更新，不写进 V1 的目录）
    → 现在的默认目录（全新安装，交给 prepare_storage_root 去建）。两个候选都非空
    时以现在的名字为准，避免改名后新旧目录各写一半。
    """
    default = Path(default_root).resolve()
    if _looks_like_data_root(default):
        return default
    for name in legacy_names:
        candidate = default.parent / name
        if candidate == default:
            continue
        if _looks_like_data_root(candidate):
            return candidate.resolve()
    if _looks_like_v1_root(default):
        return default / V2_SUBDIRECTORY
    return default


def _is_link(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(junction) and junction())


def selected_root(default_root: Path, selected_path: object) -> Path:
    default = Path(default_root).resolve()
    if selected_path is None or (type(selected_path) is str and not selected_path.strip()):
        return default
    if type(selected_path) is not str or len(selected_path) > 2048:
        raise ValueError("storage path must be an absolute directory path")
    candidate = Path(selected_path.strip()).expanduser()
    if not candidate.is_absolute():
        raise ValueError("storage path must be absolute")
    target = (candidate / PLUGIN_NAME).resolve()
    if target == default or target.is_relative_to(default) or default.is_relative_to(target):
        raise ValueError("storage path cannot be inside the current plugin data directory")
    return target


def selected_backup_root(data_root: Path, selected_path: object) -> Path | None:
    """Resolve the external backup base selected in plugin configuration."""
    root = Path(data_root).resolve()
    if selected_path is None or (type(selected_path) is str and not selected_path.strip()):
        return None
    if type(selected_path) is not str or len(selected_path) > 2048:
        raise ValueError("backup path must be an absolute directory path")
    candidate = Path(selected_path.strip()).expanduser()
    if not candidate.is_absolute():
        raise ValueError("backup path must be absolute")
    target = candidate.resolve()
    if target == root or target.is_relative_to(root) or root.is_relative_to(target):
        raise ValueError("backup path must be separate from the runtime data directory")
    if target.exists() and not target.is_dir():
        raise ValueError("backup path must name a directory")
    return target


def selected_backup_directory(runtime_root: Path, selected_path: object, installation_id: str | None = None,
                              *, plugin_root: Path | None = None) -> Path:
    """Resolve the active runtime's folder inside an optional external backup base."""
    runtime = Path(runtime_root).resolve()
    base = selected_backup_root(plugin_root or runtime, selected_path)
    if base is None:
        return runtime / "backups"
    if type(installation_id) is not str or not installation_id or len(installation_id) > 512:
        raise ValueError("an installation identity is required for external backups")
    installation_key = hashlib.sha256(installation_id.encode("utf-8")).hexdigest()
    return base / "installations" / installation_key / "backups"


def _backup_installations(directory: Path) -> tuple[str, ...]:
    from companion_v2.storage.backup import BACKUP_FORMAT

    identities = set()
    if not directory.is_dir() or _is_link(directory):
        return ()
    for sidecar in directory.glob("companion-v2-*.json"):
        if _is_link(sidecar):
            continue
        try:
            document = json.loads(sidecar.read_text(encoding="utf-8"))
            identity = document.get("installation_id")
            if (document.get("format") == BACKUP_FORMAT and type(identity) is str
                    and identity and len(identity) <= 512):
                identities.add(identity)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return tuple(sorted(identities))


def _runtime_root_for_installation(plugin_root: Path, installation_id: str) -> Path:
    matches = []
    for database in plugin_root.rglob("companion-v2.sqlite3"):
        if _is_link(database) or not database.is_file():
            continue
        connection = None
        try:
            connection = sqlite3.connect(readonly_uri(database), uri=True, timeout=0.25)
            row = connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'installation_id'").fetchone()
            if row is not None and row[0] == installation_id:
                matches.append(database.parent.resolve())
        except sqlite3.Error:
            continue
        finally:
            if connection is not None:
                connection.close()
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError("the runtime for an existing backup could not be identified")
    return unique[0]


def relocate_backup_storage(plugin_root: Path, current_path: object,
                            selected_path: object) -> tuple[tuple[tuple[Path, Path], Path], ...]:
    """Copy verified pairs to per-installation folders before changing the path."""
    from companion_v2.storage.management import backup_directories, copy_backup_snapshots

    root = Path(plugin_root).resolve()
    current_base = selected_backup_root(root, current_path)
    next_base = selected_backup_root(root, selected_path)
    if current_base == next_base:
        return ()
    if current_base is not None and not current_base.is_dir():
        raise OSError("the configured backup directory is unavailable")
    if next_base is not None:
        next_base.mkdir(parents=True, exist_ok=True)

    source_root = current_base or root
    transfers = []
    for source in backup_directories(source_root):
        for installation_id in _backup_installations(source):
            destination = (selected_backup_directory(root, selected_path, installation_id, plugin_root=root)
                           if next_base is not None
                           else _runtime_root_for_installation(root, installation_id) / "backups")
            pairs = copy_backup_snapshots(source, destination, installation_id=installation_id)
            if pairs:
                transfers.append((pairs, destination))
    return tuple(transfers)


def finish_backup_relocation(transfers: tuple[tuple[tuple[Path, Path], Path], ...]) -> int:
    """Remove source pairs only after the config points at verified destinations."""
    from companion_v2.storage.management import remove_transferred_backup_snapshots

    return sum(remove_transferred_backup_snapshots(pairs, destination)
               for pairs, destination in transfers)


def _read_pointer_document(default: Path) -> dict | None:
    pointer = default / POINTER_NAME
    if not pointer.is_file():
        return None
    try:
        document = json.loads(pointer.read_text(encoding="utf-8"))
        if document.get("format") != _FORMAT or type(document.get("path")) is not str:
            raise ValueError()
        current = Path(document["path"]).resolve()
        if current != default and not (current / OWNER_NAME).is_file():
            raise ValueError()
        return {**document, "path": str(current)}
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise RuntimeError("V2 storage location pointer is unreadable; data writes were stopped") from error


def _read_pointer(default: Path) -> Path:
    document = _read_pointer_document(default)
    return Path(document["path"]) if document else default


def _write_pointer(default: Path, document: dict) -> None:
    default.mkdir(parents=True, exist_ok=True)
    temporary = default / (POINTER_NAME + ".tmp")
    temporary.write_text(json.dumps({"format": _FORMAT, **document}, sort_keys=True),
                         encoding="utf-8", newline="\n")
    os.replace(temporary, default / POINTER_NAME)


def _finish_pending_cleanup(default: Path, document: dict | None, current: Path) -> None:
    source_value = document.get("cleanup_source") if document else None
    if type(source_value) is not str:
        return
    source = Path(source_value).resolve()
    if source != current:
        if source == default:
            _remove_contents(default, preserve={POINTER_NAME})
        else:
            _remove_owned_root(source)
    if current == default:
        (default / POINTER_NAME).unlink(missing_ok=True)
    else:
        _write_pointer(default, {"path": str(current)})


def _files(root: Path):
    if not root.exists():
        return []
    found = []
    for path in root.rglob("*"):
        if _is_link(path):
            raise RuntimeError("V2 storage contains a symbolic link; relocation was stopped")
        if path.is_file() and path.name not in {POINTER_NAME, OWNER_NAME}:
            found.append(path)
    return sorted(found, key=lambda item: item.relative_to(root).as_posix())


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_contents(root: Path, *, preserve: set[str] = frozenset()) -> None:
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.name in preserve:
            continue
        if child.is_dir() and not _is_link(child):
            shutil.rmtree(child)
        else:
            child.rmdir() if child.is_dir() else child.unlink()


def _remove_owned_root(root: Path) -> None:
    if not root.exists() or _is_link(root):
        return
    owner_path = root / OWNER_NAME
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(owner, dict) or owner.get("format") != _FORMAT:
        return
    _remove_contents(root, preserve={OWNER_NAME})
    owner_path.unlink(missing_ok=True)
    root.rmdir()


def _copy_verified(source: Path, destination: Path) -> None:
    source_files = _files(source)
    for source_file in source_files:
        relative = source_file.relative_to(source)
        target_file = destination / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        if source_file.stat().st_size != target_file.stat().st_size or _digest(source_file) != _digest(target_file):
            raise RuntimeError("V2 storage copy verification failed; original data was preserved")


def prepare_storage_root(default_root: Path, config: object) -> Path:
    """Move V2 data before controllers open it; the AstrBot root keeps a tiny pointer."""
    default = Path(default_root).resolve()
    storage = config.get("storage", {}) if isinstance(config, dict) else {}
    selected = storage.get("path", "") if isinstance(storage, dict) else ""
    pointer_document = _read_pointer_document(default)
    current = Path(pointer_document["path"]) if pointer_document else default
    desired = selected_root(default, selected)
    if current == desired:
        desired.mkdir(parents=True, exist_ok=True)
        _finish_pending_cleanup(default, pointer_document, current)
        return desired
    if desired.is_relative_to(current) or current.is_relative_to(desired):
        raise ValueError("storage source and destination cannot contain one another")
    if current != default and not (current / OWNER_NAME).is_file():
        raise RuntimeError("V2 storage source ownership could not be verified; data writes were stopped")

    desired.parent.mkdir(parents=True, exist_ok=True)
    pointer = default / POINTER_NAME
    default.mkdir(parents=True, exist_ok=True)
    is_default_destination = desired == default
    if desired.exists() and not is_default_destination:
        owner_path = desired / OWNER_NAME
        try:
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            owner = None
        if not isinstance(owner, dict) or owner.get("format") != _FORMAT or owner.get("source") != str(current):
            if any(desired.iterdir()):
                raise RuntimeError("storage destination already contains files; original V2 data was preserved")
        else:
            _remove_contents(desired, preserve={OWNER_NAME})
            (desired / OWNER_NAME).unlink(missing_ok=True)
            desired.rmdir()

    stage_root = Path(tempfile.mkdtemp(prefix=".companion-v2-move-", dir=str(desired.parent)))
    try:
        _copy_verified(current, stage_root)
        owner_document = {"format": _FORMAT, "source": str(current), "id": uuid4().hex}
        (stage_root / OWNER_NAME).write_text(json.dumps(owner_document, sort_keys=True), encoding="utf-8", newline="\n")
        if is_default_destination:
            _remove_contents(default, preserve={POINTER_NAME})
            _copy_verified(stage_root, default)
            (default / OWNER_NAME).unlink(missing_ok=True)
            _write_pointer(default, {"path": str(default), "cleanup_source": str(current)})
        else:
            if desired.exists() and not any(desired.iterdir()):
                desired.rmdir()
            os.replace(stage_root, desired)
            _write_pointer(default, {"path": str(desired), "cleanup_source": str(current)})
            _remove_contents(default, preserve={POINTER_NAME})
        if current != default:
            _remove_owned_root(current)
        if is_default_destination:
            pointer.unlink(missing_ok=True)
        else:
            _write_pointer(default, {"path": str(desired)})
        return desired
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
