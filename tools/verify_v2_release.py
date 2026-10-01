"""Verify and extract a built release; optionally run isolated install checks."""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

NATIVE_PROVIDER_FILES = {
    "astrbot_plugin_content_companion": ("companion/content_v2/assembly.py", "companion/content_v2/provider.py"),
    "astrbot_plugin_image_companion": ("image_companion/native_v2/bootstrap.py", "image_companion/native_v2/owner.py"),
    "astrbot_plugin_reality_companion": ("native_v2/provider.py",),
    "astrbot_plugin_screen_companion": ("native_v2/provider.py",),
    "astrbot_plugin_together_companion": ("native_v2/provider.py",),
    "astrbot_plugin_game_companion": ("native_v2/provider.py",),
    "astrbot_plugin_live_stream_companion": ("native_v2/provider.py",),
}


def _verify_v2_contracts(core: Path) -> dict[str, object]:
    """Check the release's executable migration and binding contracts.

    These checks intentionally import only the extracted package.  A source-tree
    test could pass while the builder omitted a fixture or a legacy module.
    """

    sys.path.insert(0, str(core))
    try:
        from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
        from companion_v2.legacy.catalog import CatalogAction, LEGACY_COMPATIBILITY_CATALOG
        from companion_v2.legacy.migration import HANDLERS

        fields = {field.name: field for field in dataclasses.fields(StagingConfiguration)}
        if fields["delivery_mode"].default != "onebot_private":
            raise ValueError("StagingConfiguration delivery_mode default is not onebot_private")

        fixture_path = core / "fixtures" / "astrbot_staging.example.json"
        fixture = StagingConfiguration.parse(fixture_path.read_text(encoding="utf-8"))
        if fixture.delivery_mode != "onebot_private":
            raise ValueError("legacy preview fixture did not normalize to onebot_private")

        weather_path = core / "companion_v2" / "legacy" / "weather_migration.py"
        if not weather_path.is_file():
            raise ValueError("weather migration source missing from release")
        if HANDLERS != frozenset({"v2.private-config-converter"}):
            raise ValueError("legacy handler inventory changed unexpectedly")

        no_handler_sources = {
            "private.core_profiles",
            "private.work_and_delivery",
            "private.world_assets",
        }
        for source_id in no_handler_sources:
            if LEGACY_COMPATIBILITY_CATALOG.entry(source_id).action is not CatalogAction.NO_HANDLER:
                raise ValueError("legacy source is no longer marked NO_HANDLER: " + source_id)
        return {
            "delivery_mode_default": "onebot_private",
            "legacy_preview_normalized": True,
            "weather_migration": True,
            "handlers": sorted(HANDLERS),
            "no_handler_sources": sorted(no_handler_sources),
        }
    finally:
        # Keep verification imports from affecting the optional host check below.
        sys.path.remove(str(core))


def verify(release, destination):
    release = release.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("verification destination must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((release / "release-manifest.json").read_text(encoding="utf-8"))
    reports = []
    for package in manifest["packages"]:
        filename = package["filename"]
        if Path(filename).name != filename:
            raise ValueError("invalid archive filename")
        source = release / filename
        if hashlib.sha256(source.read_bytes()).hexdigest() != package["sha256"]:
            raise ValueError("package hash mismatch: " + filename)
        prefix = package["plugin_id"] + "/"
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise ValueError("duplicate archive entries")
            for name in names:
                target = (destination / name).resolve()
                if (not name.startswith(prefix) or "\\" in name or not target.is_relative_to(destination)
                        or any(part in {"..", "data", ".git", "__pycache__", "node_modules", "protected_model"} for part in Path(name).parts)):
                    raise ValueError("invalid source-only archive path")
            if archive.testzip() is not None:
                raise ValueError("invalid archive CRC")
            content = json.loads(archive.read(prefix + "RELEASE_FILES.json"))
            expected = {prefix + name for name in content["files"]} | {prefix + "RELEASE_FILES.json"}
            if set(names) != expected:
                raise ValueError("file inventory mismatch")
            required_native = {prefix + name for name in NATIVE_PROVIDER_FILES.get(package["plugin_id"], ())}
            if not required_native.issubset(expected):
                raise ValueError("native provider source missing: " + package["plugin_id"])
            integration = ("native-core" if package["plugin_id"] == "astrbot_plugin_private_companion_v2"
                           else "native-provider" if required_native else "provider-metadata")
            if package["integration"] != integration:
                raise ValueError("provider integration mismatch: " + package["plugin_id"])
            python_count = 0
            for name, digest in content["files"].items():
                payload = archive.read(prefix + name)
                if hashlib.sha256(payload).hexdigest() != digest:
                    raise ValueError("file hash mismatch: " + name)
                if name.endswith(".py"):
                    ast.parse(payload.decode("utf-8"), filename=name)
                    python_count += 1
            # Paths have been validated above; destination contains no user data.
            archive.extractall(destination)
            reports.append({"plugin_id": package["plugin_id"], "files": len(names), "python_files": python_count})
    core = destination / "astrbot_plugin_private_companion_v2"
    schema = json.loads((core / "_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["staging"]["items"]["enabled"]["default"] is False
    assert schema["multi_host"]["items"]["enabled"]["default"] is False
    assert [p.name for p in (core / "pages").iterdir() if (p / "index.html").is_file()] == ["陪伴小屋"]
    contracts = _verify_v2_contracts(core)
    return {"packages": reports, "core": str(core), "default_enabled": False,
            "public_pages": ["陪伴小屋"], "hashes_and_syntax": "passed",
            "contracts": contracts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--extract-to", required=True, type=Path)
    parser.add_argument("--host-check", action="store_true")
    args = parser.parse_args()
    report = verify(args.release, args.extract_to)
    if args.host_check:
        # tests.multi_life_entry_process establishes a temporary SDK data root
        # before importing AstrBot. The providers and platform are local doubles.
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.multi_life_entry_process"],
                                cwd=report["core"], env=os.environ.copy(), timeout=90, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
        lines = result.stdout.splitlines()
        report["host_check"] = json.loads(next(line for line in reversed(lines) if line.startswith('{"life_routes"')))
    (args.extract_to / "package-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
