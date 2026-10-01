"""Build installable V2 and optional-provider archives from source only."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CORE_ID = "astrbot_plugin_private_companion_v2"
VERSION = "2.0.0"
PROVIDERS = {
    "content": ("companion", "pages"),
    "image": ("image_companion",),
    "reality": ("native_v2", "pages", "assets"),
    "screen": ("core", "native_v2", "pages", "web", "deploy", "scripts"),
    "together": ("native_v2", "pages", "web"),
    "game": ("native_v2", "pages", "web"),
    "live_stream": ("blivedm", "native_v2", "pages", "vendor"),
}
NATIVE_PROVIDER_FILES = {
    "content": ("companion/content_v2/assembly.py", "companion/content_v2/provider.py"),
    "image": ("image_companion/native_v2/bootstrap.py", "image_companion/native_v2/owner.py"),
    "reality": ("native_v2/provider.py",),
    "screen": ("native_v2/provider.py",),
    "together": ("native_v2/provider.py",),
    "game": ("native_v2/provider.py",),
    "live_stream": ("native_v2/provider.py",),
}
CORE_DIRS = ("companion_v2", "astrbot_host", "pages", "docs", "tests", "fixtures", "tools")
ROOT_FILES = {
    "metadata.yaml", "_conf_schema.json", "README.md", "CHANGELOG.md",
    "requirements.txt", "requirements-optional-input.txt", "requirements-optional-mic.txt",
    "pyproject.toml", "LICENSE", "NOTICE", "logo.png", ".editorconfig",
    "soullink_bridge.mjs", "手机陪伴终端从零配对说明书.md",
}
EXCLUDED_DIRS = {
    "data", ".git", "__pycache__", ".pytest_cache", "node_modules", "logs",
    "dist", "build", "protected_model", "desktop_pet", ".codex-plugin", "%SystemDrive%",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".cjs", ".mjs", ".css", ".html", ".md", ".txt", ".json",
    ".yaml", ".yml", ".toml", ".sql", ".svg", ".ps1", ".sh", ".bat", ".ini", ".conf", ".csv",
}
SECRET_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(rb"abk_[A-Za-z0-9_-]{30,}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*[A-Za-z0-9+/=\r\n]{80,}-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def allowed(path, root):
    relative = path.relative_to(root)
    return (not any(part in EXCLUDED_DIRS for part in relative.parts)
            and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and path.suffix.lower() not in {".pyc", ".pyo", ".log", ".db", ".sqlite", ".sqlite3", ".bak"}
            and not path.name.startswith(("_tmp", ".env", "REGISTRATION_COORDINATION_"))
            and not (root.name.endswith("content_companion") and "framework-preview-v1" in relative.parts))


def sources(root, directories):
    # Do not walk data roots and then filter their files: never enter them.
    selected = [p for p in root.iterdir() if p.is_file() and (p.name in ROOT_FILES or p.suffix == ".py")]
    for name in directories:
        folder = root / name
        if not folder.is_dir():
            continue
        for base, children, filenames in os.walk(folder, followlinks=False):
            children[:] = sorted(child for child in children if allowed(Path(base) / child, root))
            selected.extend(Path(base) / name for name in sorted(filenames))
    return sorted({p for p in selected if allowed(p, root)}, key=lambda p: p.relative_to(root).as_posix())


def checked_payload(path, root):
    payload = path.read_bytes()
    if any(pattern.search(payload.replace(b"\\n", b"\n")) for pattern in SECRET_PATTERNS):
        raise ValueError("credential-like content rejected in " + str(path.relative_to(root)))
    # The historical V1 classification source keeps an XLSX container under a
    # .csv name. It is a binary, read-only source documented by the project;
    # normalize real CSV text while preserving that workbook byte-for-byte.
    is_historical_workbook = path.suffix.lower() == ".csv" and payload.startswith(b"PK\x03\x04")
    if (path.suffix.lower() in TEXT_SUFFIXES and not is_historical_workbook) or path.name in {"LICENSE", "NOTICE", ".editorconfig"}:
        text = payload.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if path.suffix == ".py":
            ast.parse(text, filename=str(path.relative_to(root)))
        if path.suffix == ".json":
            json.loads(text)
        payload = (text.rstrip("\n") + "\n").encode("utf-8")
    return payload


def zip_entries(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("archive CRC failed: " + path.name)


def metadata(root):
    raw = (root / "metadata.yaml").read_text(encoding="utf-8-sig")
    def field(name):
        found = re.search(r"^" + name + r":\s*(.+)$", raw, re.MULTILINE)
        if not found:
            raise ValueError("metadata missing " + name + ": " + root.name)
        return found.group(1).strip().strip("\"'")
    return {"plugin_id": field("name"), "version": field("version"), "display_name": field("display_name")}


def build_plugin(root, directories, output, core=False):
    info = metadata(root)
    if info["plugin_id"] != root.name:
        raise ValueError("plugin directory and metadata identity mismatch: " + root.name)
    if core and info["version"] != VERSION:
        raise ValueError("core version mismatch")
    files = {}
    for path in sources(root, directories):
        files[root.name + "/" + path.relative_to(root).as_posix()] = checked_payload(path, root)
    required = {root.name + "/" + name for name in ("main.py", "metadata.yaml", "_conf_schema.json")}
    provider = root.name.removeprefix("astrbot_plugin_").removesuffix("_companion")
    required.update(root.name + "/" + name for name in NATIVE_PROVIDER_FILES.get(provider, ()))
    if not required.issubset(files):
        raise ValueError("incomplete plugin source: " + root.name)
    if core:
        public_entries = [name for name in files if len(Path(name).parts) == 4
                          and Path(name).parts[1] == "pages" and name.endswith("/index.html")]
        if public_entries != [root.name + "/pages/陪伴小屋/index.html"]:
            raise ValueError("V2 must expose exactly one Dashboard page: 陪伴小屋")
        manifest_path = root.name + "/pages/陪伴小屋/page-build.json"
        manifest = json.loads(files[manifest_path])
        for name, expected in manifest["files"].items():
            if digest(files[root.name + "/pages/陪伴小屋/" + name]) != expected:
                raise ValueError("stale cottage asset: " + name + "; run sync_framework_page.py first")
    else:
        tree = ast.parse(files[root.name + "/main.py"].decode("utf-8"))
        if not any(isinstance(node, ast.FunctionDef) and node.name == "companion_v2_status" for node in ast.walk(tree)):
            raise ValueError("provider status adapter missing: " + root.name)
    file_manifest = {name.split("/", 1)[1]: digest(payload) for name, payload in files.items()}
    files[root.name + "/RELEASE_FILES.json"] = (json.dumps({"product_version": VERSION,
        "plugin": info, "files": file_manifest}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    integration = "native-core" if core else "native-provider" if provider in NATIVE_PROVIDER_FILES else "provider-metadata"
    suffix = "" if core else "-v2-native" if provider in NATIVE_PROVIDER_FILES else "-v2-status"
    filename = root.name + "-" + info["version"] + suffix + ".zip"
    target = output / filename
    zip_entries(target, files)
    return {**info, "filename": filename, "sha256": digest(target.read_bytes()),
            "bytes": target.stat().st_size, "files": len(files),
            "integration": integration,
            "execution_owner": root.name}


def build(output, core_only=False):
    output = output.resolve()
    if output.is_relative_to(ROOT.parent):
        raise ValueError("release output must be outside installed plugin directories")
    output.mkdir(parents=True, exist_ok=True)
    # Stage the complete release first. A validation failure publishes no new ZIP.
    with TemporaryDirectory(prefix="companion-v2-package-") as temporary:
        stage = Path(temporary)
        packages = [build_plugin(ROOT, CORE_DIRS, stage, core=True)]
        if not core_only:
            for name, directories in PROVIDERS.items():
                packages.append(build_plugin(ROOT.parent / ("astrbot_plugin_" + name + "_companion"), directories, stage))
        manifest = {"product": "我会永远陪着你 V2.0", "version": VERSION, "astrbot_version": "4.27.2",
                    "data_policy": "V2 独立数据，不打包或迁移 V1 用户数据",
                    "provider_integration": "All listed providers ship their native_v2 source; Content, Image and Screen expose native V2 execution, while the remaining providers retain explicit host adapters and status boundaries",
                    "packages": packages}
        (stage / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        for filename in ("RELEASE_V2_0.md", "INTEGRATION_ACCEPTANCE_V2_0.md"):
            (stage / filename).write_bytes(checked_payload(ROOT / "docs" / filename, ROOT))
        hashes = [(p.name, digest(p.read_bytes())) for p in sorted(stage.iterdir()) if p.is_file()]
        (stage / "SHA256SUMS.txt").write_text("".join(sha + "  " + name + "\n" for name, sha in hashes), encoding="utf-8", newline="\n")
        if not core_only:
            suite = "companion-v2-" + VERSION + "-suite.zip"
            zip_entries(stage / suite, {p.name: p.read_bytes() for p in stage.iterdir() if p.is_file()})
        for path in stage.iterdir():
            target = output / path.name
            target.write_bytes(path.read_bytes())
        report = {"output": str(output), "packages": len(packages),
                  "archives": [{"name": p.name, "sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                               for p in sorted(stage.glob("*.zip"))]}
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.core_only), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
