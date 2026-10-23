"""Immutable byte-for-byte archive for V1 data with no active V2 equivalent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid


SCHEMA = "companion.legacy-v1-archive.v1"
REPARSE_POINT = 0x400
COPY_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ArchiveFile:
    relative_path: str
    size: int
    modified_ns: int
    device: int
    inode: int

    def fingerprint_item(self):
        return [self.relative_path, self.size, self.modified_ns, self.device, self.inode]


@dataclass(frozen=True)
class V1ArchivePlan:
    root: Path
    files: tuple[ArchiveFile, ...]
    issues: tuple[tuple[str, str], ...]
    fingerprint: str
    excluded_directories: tuple[str, ...] = ()

    @property
    def total_bytes(self):
        return sum(item.size for item in self.files)

    @property
    def inventory_fingerprint(self):
        material = {
            "schema": SCHEMA,
            "files": [[item.relative_path, item.size] for item in self.files],
            "issues": [[path, reason] for path, reason in self.issues],
        }
        return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()

    def document(self):
        areas = {}
        for item in self.files:
            area = item.relative_path.split("/", 1)[0] if "/" in item.relative_path else "root"
            current = areas.setdefault(area, {"file_count": 0, "total_bytes": 0})
            current["file_count"] += 1
            current["total_bytes"] += item.size
        return {
            "state": "ready" if not self.issues else "incomplete",
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "areas": [{"name": name, **areas[name]} for name in sorted(areas)],
            "excluded_count": len(self.issues),
            "fingerprint": self.fingerprint,
        }


def _is_reparse(info):
    return bool(int(getattr(info, "st_file_attributes", 0)) & REPARSE_POINT)


def _file_key(path: Path):
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
        raise ValueError("archive_source_not_regular")
    return (int(info.st_size), int(info.st_mtime_ns), int(info.st_dev), int(info.st_ino))


def build_v1_archive_plan(v1_root: str | Path, *, exclude_roots=()) -> V1ArchivePlan:
    candidate = Path(v1_root).expanduser()
    try:
        root_info = candidate.lstat()
    except OSError as error:
        raise ValueError("archive_source_unavailable") from error
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        raise ValueError("archive_source_not_directory")
    root = candidate.resolve(strict=True)
    excluded = set()
    for value in exclude_roots:
        try:
            path = Path(value).expanduser().resolve(strict=True)
            if path != root and path.is_relative_to(root):
                excluded.add(path)
        except (OSError, RuntimeError, ValueError):
            continue
    excluded_relative = tuple(sorted(str(path.relative_to(root)).replace("\\", "/")
                                     for path in excluded))
    files, issues = [], []
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError:
            issues.append((prefix, "directory_unreadable"))
            continue
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                issues.append((relative, "entry_unreadable"))
                continue
            if entry.is_symlink() or _is_reparse(info):
                issues.append((relative, "reparse_point"))
            elif stat.S_ISDIR(info.st_mode):
                if Path(entry.path).resolve() not in excluded:
                    pending.append((Path(entry.path), relative))
            elif stat.S_ISREG(info.st_mode):
                try:
                    info = os.stat(entry.path, follow_symlinks=False)
                except OSError:
                    issues.append((relative, "entry_unreadable"))
                    continue
                if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
                    issues.append((relative, "entry_changed"))
                    continue
                files.append(ArchiveFile(relative.replace("\\", "/"), int(info.st_size),
                    int(info.st_mtime_ns), int(info.st_dev), int(info.st_ino)))
            else:
                issues.append((relative, "unsupported_file_type"))
    files.sort(key=lambda item: item.relative_path)
    issues.sort()
    material = {
        "schema": SCHEMA,
        "excluded_directories": list(excluded_relative),
        "files": [item.fingerprint_item() for item in files],
        "issues": [[path, reason] for path, reason in issues],
    }
    fingerprint = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return V1ArchivePlan(root, tuple(files), tuple(issues), fingerprint, excluded_relative)


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError("archive_path_invalid")
    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except OSError as error:
            raise ValueError("archive_source_changed") from error
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ValueError("archive_source_changed")
    return current


def _manifest_path(archive_directory: Path):
    path = archive_directory / "manifest.json"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or _is_reparse(info):
        raise ValueError("archive_manifest_invalid")
    return path


def _existing_archive(archive_directory: Path, plan: V1ArchivePlan, *, archive_id,
                      source_fingerprint, metadata):
    try:
        manifest = json.loads(_manifest_path(archive_directory).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or manifest.get("archive_id") != archive_id
            or manifest.get("source_fingerprint") != source_fingerprint
            or not isinstance(manifest.get("files"), list)
            or manifest.get("issues", []) != [[path, reason] for path, reason in plan.issues]
            or manifest.get("complete", True) is not (not plan.issues)
            or manifest.get("metadata") != metadata):
        return None
    expected = {item.relative_path: item.size for item in plan.files}
    recorded = {item.get("path"): item for item in manifest["files"]
                if isinstance(item, dict)}
    if (len(recorded) != len(manifest["files"])
            or {path: item.get("size") for path, item in recorded.items()} != expected):
        return None
    for relative_path, size in expected.items():
        try:
            path = _safe_relative_path(archive_directory / "files", relative_path)
            if _file_key(path)[0] != size:
                return None
            archived_digest = _sha256_file(path)
            if archived_digest != recorded[relative_path].get("sha256"):
                return None
            source = _safe_relative_path(plan.root, relative_path)
            if archived_digest != _sha256_file(source):
                return None
        except (OSError, ValueError):
            return None
    return manifest


def _sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_v1_archive(plan: V1ArchivePlan, archive_root: str | Path, *, archive_id=None,
                    source_fingerprint=None, metadata=None, allow_incomplete=False):
    if plan.issues and allow_incomplete is not True:
        raise ValueError("archive_source_incomplete")
    archive_id = plan.fingerprint if archive_id is None else archive_id
    source_fingerprint = plan.fingerprint if source_fingerprint is None else source_fingerprint
    if (not isinstance(archive_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", archive_id)
            or not isinstance(source_fingerprint, str) or len(source_fingerprint) > 256
            or (metadata is not None and not isinstance(metadata, dict))):
        raise ValueError("archive_identity_invalid")
    root = Path(archive_root).expanduser().resolve(strict=False)
    if root == plan.root or plan.root in root.parents:
        raise ValueError("archive_destination_inside_source")
    root.mkdir(parents=True, exist_ok=True)
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or _is_reparse(root_info):
        raise ValueError("archive_destination_invalid")
    target = root / archive_id
    existing = _existing_archive(target, plan, archive_id=archive_id,
                                 source_fingerprint=source_fingerprint,
                                 metadata=metadata) if target.exists() else None
    if existing is not None:
        return {"archive_id": archive_id, "file_count": len(plan.files),
                "total_bytes": plan.total_bytes, "already_present": True,
                "complete": not plan.issues, "excluded_count": len(plan.issues),
                "manifest_sha256": hashlib.sha256(_manifest_path(target).read_bytes()).hexdigest()}
    if target.exists():
        raise ValueError("archive_target_conflict")
    if shutil.disk_usage(root).free < plan.total_bytes + 1024 * 1024:
        raise OSError("archive_space_insufficient")

    stage = root / (".staging-" + uuid.uuid4().hex)
    stage.mkdir()
    entries = []
    try:
        for item in plan.files:
            source = _safe_relative_path(plan.root, item.relative_path)
            if _file_key(source) != (item.size, item.modified_ns, item.device, item.inode):
                raise ValueError("archive_source_changed")
            destination = stage / "files" / Path(*PurePosixPath(item.relative_path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with source.open("rb") as reader, destination.open("xb") as writer:
                while True:
                    chunk = reader.read(COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    writer.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            if size != item.size or _file_key(source) != (item.size, item.modified_ns, item.device, item.inode):
                raise ValueError("archive_source_changed")
            entries.append({"path": item.relative_path, "size": size, "sha256": digest.hexdigest()})

        current = build_v1_archive_plan(
            plan.root,
            exclude_roots=tuple(plan.root / relative for relative in plan.excluded_directories),
        )
        if current.fingerprint != plan.fingerprint or current.issues != plan.issues:
            raise ValueError("archive_source_changed")
        manifest = {
            "schema": SCHEMA,
            "archive_id": archive_id,
            "source_fingerprint": source_fingerprint,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(entries),
            "total_bytes": plan.total_bytes,
            "files": entries,
            "issues": [[path, reason] for path, reason in plan.issues],
            "complete": not plan.issues,
        }
        manifest["metadata"] = metadata
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")) + "\n").encode("utf-8")
        manifest_path = stage / "manifest.json"
        with manifest_path.open("xb") as stream:
            stream.write(manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        stage.rename(target)
        return {"archive_id": archive_id, "file_count": len(entries),
                "total_bytes": plan.total_bytes, "already_present": False,
                "complete": not plan.issues, "excluded_count": len(plan.issues),
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def verify_v1_archive(archive_directory: str | Path):
    archive = Path(archive_directory)
    try:
        if not stat.S_ISDIR(archive.lstat().st_mode) or _is_reparse(archive.lstat()):
            raise ValueError("archive_directory_invalid")
        manifest_path = _manifest_path(archive)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("archive_manifest_invalid") from error
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or manifest.get("archive_id") != archive.name
            or not isinstance(manifest.get("files"), list)
            or not isinstance(manifest.get("issues", []), list)
            or manifest.get("complete", True) is not (not manifest.get("issues", []))
            or any(not isinstance(item, list) or len(item) != 2
                   or any(not isinstance(value, str) for value in item)
                   for item in manifest.get("issues", ()))):
        raise ValueError("archive_manifest_invalid")
    expected = {}
    total = 0
    for item in manifest["files"]:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or type(item.get("size")) is not int or item["size"] < 0
                or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64):
            raise ValueError("archive_manifest_invalid")
        relative_path = item["path"]
        if relative_path in expected:
            raise ValueError("archive_manifest_invalid")
        path = _safe_relative_path(archive / "files", relative_path)
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b""):
                digest.update(chunk)
                size += len(chunk)
        if size != item["size"] or digest.hexdigest() != item["sha256"]:
            raise ValueError("archive_content_mismatch")
        expected[relative_path] = item["size"]
        total += size
    actual = set()
    files_root = archive / "files"
    if files_root.exists():
        for path in files_root.rglob("*"):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise ValueError("archive_content_mismatch")
            if stat.S_ISREG(info.st_mode):
                actual.add(path.relative_to(files_root).as_posix())
    if actual != set(expected) or len(expected) != manifest.get("file_count") or total != manifest.get("total_bytes"):
        raise ValueError("archive_content_mismatch")
    return {"archive_id": manifest["archive_id"], "file_count": len(expected),
            "total_bytes": total, "complete": manifest["complete"],
            "excluded_count": len(manifest["issues"]),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
