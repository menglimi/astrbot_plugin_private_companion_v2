"""Run the formal V1 memory-database migration against a disposable AstrBot host."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace

# Keep AstrBot's import-time database under a disposable test root.
from tests.astrbot_data_root import assert_sdk_database_isolated

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot.core import db_helper
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.legacy.archive import verify_v1_archive
from companion_v2.legacy.memory_archive import build_memory_database_plan
from companion_v2.legacy.migration import LegacyMigration, plugin_data_path
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW


def _sha256(path: Path):
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(outcome, label):
    if not outcome.is_success:
        failure = outcome.failure
        raise RuntimeError(f"{label}:{getattr(failure, 'code', 'failed')}")
    return outcome.unwrap()


def _source_fingerprints(plan):
    fingerprints = {}
    for asset in plan.assets:
        fingerprints[asset.relative_path] = _sha256(asset.source_path)
        if asset.kind == "sqlite" and asset.wal_signature:
            wal_path = Path(str(asset.source_path) + "-wal")
            fingerprints[asset.relative_path + "-wal"] = _sha256(wal_path)
    return fingerprints


def _verify_database_asset(archive_path: Path, asset):
    snapshot_path = archive_path / "files" / Path(*asset.relative_path.split("/"))
    snapshot = sqlite3.connect(snapshot_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        snapshot.execute("PRAGMA query_only=ON")
        counts = {}
        for table in sorted(asset.table_counts or {}):
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = int(snapshot.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
        integrity = snapshot.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        snapshot.close()
    if counts != (asset.table_counts or {}) or integrity != "ok":
        raise RuntimeError("restart_memory_database_asset_mismatch")
    return counts


async def run(v1_root: Path):
    assert_sdk_database_isolated(db_helper)
    v1_root = v1_root.resolve(strict=True)
    memory_path = plugin_data_path(v1_root,
        "astrbot_plugin_memory_companion/memory_companion.db")
    memory_plan = build_memory_database_plan(memory_path)
    if memory_plan.state != "ready":
        raise RuntimeError("memory_database_not_ready:" + memory_plan.state)
    source_hashes = _source_fingerprints(memory_plan)
    expected_assets = [asset.document() for asset in memory_plan.assets]

    native = MultiNativeContext()
    clock = DeterministicClock.at(NOW)
    native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider,
        SimpleNamespace, SimpleNamespace, FakeReverseApi)
    with TemporaryDirectory(prefix="companion-v2-memory-data-acceptance-") as temporary:
        data_root = Path(temporary) / "v2-data"
        controller = AstrBotMultiController(native, multi_config(), data_root,
            native_types=native_types, now=clock.now)
        controllers = [controller]
        try:
            _require(await controller.initialize_profile(), "initialize")
            _require(await controller.start(), "start")
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                application=controller.session.application)
            migration = LegacyMigration(v1_root=v1_root)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.session.runtime,
                now=clock.now, data_root=data_root)

            preview = _require(api._data_plan(migration, v1_root, session), "data_plan")
            if preview["memory_database"]["fingerprint"] != memory_plan.fingerprint:
                raise RuntimeError("preview_memory_source_changed")
            if preview["memory_database"].get("assets") != expected_assets:
                raise RuntimeError("preview_memory_asset_mismatch")
            applied = _require(await api._data_apply(migration, v1_root, session,
                preview["plan_token"], "", "", False, False, False, False, False,
                False, False, True), "data_apply")
            result = applied.get("memory_archive")
            if (not result or result["table_counts"] != memory_plan.table_counts
                    or result.get("assets") != expected_assets
                    or result.get("source_complete") is not True):
                raise RuntimeError("memory_archive_count_mismatch")
            archive_path = data_root / "legacy-v1-archives" / result["archive_id"]
            await controller.terminate()

            restarted = AstrBotMultiController(native, multi_config(), data_root,
                native_types=native_types, now=clock.now)
            controllers.append(restarted)
            loaded = _require(await restarted.load_existing(), "reload")
            if not loaded.get("loaded"):
                raise RuntimeError("reload_not_loaded")
            _require(await restarted.start(), "restart")

            verified = verify_v1_archive(archive_path)
            manifest = json.loads((archive_path / "manifest.json").read_text(encoding="utf-8"))
            metadata = manifest.get("metadata", {})
            if (verified.get("complete") is not True or result.get("source_complete") is not True
                    or metadata.get("source_complete") is not True
                    or metadata.get("assets") != expected_assets):
                raise RuntimeError("memory_archive_incomplete")
            archive_entries = {item.get("path"): item for item in manifest.get("files", [])
                               if isinstance(item, dict)}
            expected_paths = {asset.relative_path for asset in memory_plan.assets}
            if (verified["file_count"] != len(expected_paths)
                    or set(archive_entries) != expected_paths):
                raise RuntimeError("memory_archive_file_count_mismatch")

            restored_table_counts = {}
            restored_asset_counts = {}
            historical_file_count = 0
            integrity_checks = []
            for asset in memory_plan.assets:
                archive_asset = archive_path / "files" / Path(*asset.relative_path.split("/"))
                if asset.kind == "sqlite":
                    restored = _verify_database_asset(archive_path, asset)
                    restored_asset_counts[asset.relative_path] = restored
                    integrity_checks.append(asset.relative_path)
                    if asset.relative_path == "memory_companion.db":
                        restored_table_counts = restored
                else:
                    if _sha256(archive_asset) != asset.sha256:
                        raise RuntimeError("memory_archive_historical_file_mismatch")
                    historical_file_count += 1

            if metadata.get("table_counts") != restored_table_counts:
                raise RuntimeError("memory_archive_manifest_mismatch")

            send_actions = {"send_private_msg", "send_group_msg", "send_msg"}
            platform_sends = sum(1 for platform in native.platforms.values()
                for action, _ in platform.client._api._wsr_api.calls if action in send_actions)
            model_calls = len(native.provider.client.state.calls)
            if model_calls or platform_sends:
                raise RuntimeError("unexpected_external_call")

            latest_plan = build_memory_database_plan(memory_path)
            source_unchanged = (latest_plan.state == "ready"
                                and source_hashes == _source_fingerprints(latest_plan))
            if not source_unchanged:
                raise RuntimeError("v1_memory_source_changed")
            if metadata.get("table_counts") != restored_table_counts:
                raise RuntimeError("memory_archive_manifest_mismatch")
            return {
                "source_state": "unchanged",
                "source_database_bytes": memory_plan.database_bytes,
                "source_wal_bytes": memory_plan.wal_bytes,
                "table_count": len(restored_table_counts),
                "record_count": sum(restored_table_counts.values()),
                "table_counts": restored_table_counts,
                "database_asset_table_counts": restored_asset_counts,
                "archive_asset_count": len(memory_plan.assets),
                "historical_file_count": historical_file_count,
                "sqlite_integrity_checked": integrity_checks,
                "archive_id": result["archive_id"],
                "archive_bytes": verified["total_bytes"],
                "archive_verified_after_restart": True,
                "integrity_check": "ok",
                "model_calls": model_calls,
                "platform_sends": platform_sends,
            }
        finally:
            for instance in reversed(controllers):
                await instance.terminate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.v1_root)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
