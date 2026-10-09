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
from tempfile import TemporaryDirectory
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

MIGRATION_ACCEPTANCE_MODULES = (
    "tests.test_configuration_migration",
    "tests.test_legacy_data_acceptance_process",
    "tests.test_legacy_memory_archive",
    "tests.test_legacy_memory_package_archive",
)


def _verify_v2_contracts(core: Path) -> dict[str, object]:
    """Check the release's executable migration and binding contracts.

    These checks intentionally import only the extracted package.  A source-tree
    test could pass while the builder omitted a fixture or a legacy module.
    """

    sys.path.insert(0, str(core))
    try:
        from companion_v2.adapters.astrbot.staging_config import StagingConfiguration
        from companion_v2.legacy.catalog import CatalogAction, LEGACY_COMPATIBILITY_CATALOG
        from companion_v2.legacy.configuration_migration import convert_account_configuration
        from companion_v2.legacy.data_migration import build_data_plan, map_legacy_worldbook
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
        expected_handlers = frozenset({"v2.private-config-converter",
            "v2.role-journal-importer", "v2.role-journal-and-worldbook-importer",
            "v2.group-relationship-importer", "v2.reaction-asset-importer",
            "v2.memory-snapshot-archive"})
        if HANDLERS != expected_handlers:
            raise ValueError("legacy handler inventory changed unexpectedly")
        if not callable(build_data_plan) or not callable(map_legacy_worldbook):
            raise ValueError("V1 data migration converters are missing from the release")

        account_plan = convert_account_configuration({
            "basic_config": {"bot_scope_mode": "allowlist", "bot_scope_ids": ["100"],
                             "target_user_ids": ["200"], "plugin_specific_persona_id": "native"},
        }, accounts=({"platform_id": "qq-main", "account_id": "100", "bot_id": "bot-100",
                      "persona_roles": {"native": "role-100-native", "[%None]": "role-100-default",
                                        "": "role-100-default"}},))
        expected_identity = {
            "target.platform_id": "qq-main", "target.account_id": "100",
            "target.bot_id": "bot-100", "target.participant_id": "200",
            "target.role_id": "role-100-native", "target.persona_id": "native",
        }
        if any(account_plan.changes.get(field) != value for field, value in expected_identity.items()):
            raise ValueError("account configuration migration contract failed")
        if account_plan.changes.get("multi_host.targets", [{}])[0].get("participant_id") != "200":
            raise ValueError("multi-target configuration migration contract failed")
        if "multi_host.enabled" in account_plan.changes:
            raise ValueError("account migration must not change the selected runtime mode")

        data_sources = {
            "private.core_profiles", "private.group_relationship_graph",
            "private.reaction_assets", "private.owned_reaction_assets",
        }
        for source_id in data_sources:
            if LEGACY_COMPATIBILITY_CATALOG.entry(source_id).action is not CatalogAction.DATA_CONVERTED:
                raise ValueError("legacy data source is not marked DATA_CONVERTED: " + source_id)
        documented_skips = {"private.work_and_delivery", "private.world_assets"}
        for source_id in documented_skips:
            if LEGACY_COMPATIBILITY_CATALOG.entry(source_id).action is not CatalogAction.DOCUMENTED_SKIP:
                raise ValueError("legacy data boundary is not documented: " + source_id)
        return {
            "delivery_mode_default": "onebot_private",
            "legacy_preview_normalized": True,
            "weather_migration": True,
            "account_configuration_migration": True,
            "handlers": sorted(HANDLERS),
            "data_sources": sorted(data_sources),
            "documented_skip_sources": sorted(documented_skips),
        }
    finally:
        # Keep verification imports from affecting the optional host check below.
        sys.path.remove(str(core))


def _host_check_environment(temporary_root: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["ASTRBOT_ROOT"] = temporary_root

    # AstrBot's bundled Python keeps the backend application beside its venv.
    app_path = Path(sys.prefix).resolve().parent / "app"
    if app_path.is_dir():
        search_paths = [item for item in environment.get("PYTHONPATH", "").split(os.pathsep) if item]
        resolved_app_path = app_path.resolve()
        if not any(Path(item).resolve() == resolved_app_path for item in search_paths):
            environment["PYTHONPATH"] = os.pathsep.join([str(app_path), *search_paths])
    return environment


def _run_host_process(core: str, environment: dict[str, str], arguments: list[str],
                      label: str, timeout: int) -> str:
    result = subprocess.run([sys.executable, "-X", "utf8", *arguments],
        cwd=core, env=environment, timeout=timeout, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}:\n{result.stdout[-12000:]}")
    return result.stdout


def _run_migration_acceptance(core: str, environment: dict[str, str]) -> dict[str, object]:
    output = _run_host_process(core, environment,
        ["-m", "unittest", "-q", *MIGRATION_ACCEPTANCE_MODULES],
        "candidate migration acceptance", timeout=240)
    summary = next((line.strip() for line in reversed(output.splitlines())
                    if line.strip().startswith("Ran ")), "")
    if not summary:
        raise RuntimeError("candidate migration acceptance did not report a unittest summary")
    try:
        tests_run = int(summary.split()[1])
    except (IndexError, ValueError) as error:
        raise RuntimeError("candidate migration acceptance returned an invalid unittest summary") from error
    return {"status": "passed", "tests_run": tests_run,
            "modules": list(MIGRATION_ACCEPTANCE_MODULES)}


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
        # These checks run only from the extracted candidate package and use local doubles.
        with TemporaryDirectory(prefix="companion-v2-release-host-check-") as temporary:
            environment = _host_check_environment(temporary)
            output = _run_host_process(report["core"], environment,
                ["-m", "tests.multi_life_entry_process"],
                "candidate host lifecycle check", timeout=90)
            report["migration_acceptance"] = _run_migration_acceptance(report["core"], environment)
        lines = output.splitlines()
        report["host_check"] = json.loads(next(line for line in reversed(lines) if line.startswith('{"life_routes"')))
    (args.extract_to / "package-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
