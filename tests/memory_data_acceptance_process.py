"""Run the formal V1 memory-database migration against a disposable AstrBot host."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace

# Keep AstrBot's import-time database under a disposable test root.
from tests.astrbot_data_root import assert_sdk_database_isolated
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot_host.legacy_config import v1_setting
from astrbot.core import db_helper
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import AudienceRef, ScopeKind
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.execution.models import TaskContext
from companion_v2.identity_policy.personas import ConversationRoute, PersonaDirectory
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.legacy.data_migration import build_data_plan
from companion_v2.legacy.archive import verify_v1_archive
from companion_v2.legacy.memory_archive import build_memory_database_plan
from companion_v2.legacy.migration import LegacyMigration, plugin_data_path
from companion_v2.legacy.sqlite_snapshot import open_readonly_sqlite_snapshot
from companion_v2.legacy.private_memory import build_private_memory_plan
from companion_v2.memory.legacy_materials import DATABASE_FILENAME, LegacyMemoryMaterials
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
    snapshot = open_readonly_sqlite_snapshot(snapshot_path)
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


def _identity_setup(v1_root, configuration, memory_path):
    source = build_private_memory_plan(v1_root, configuration)
    identities = {(identity["bot_account_id"].split(":", 1)[-1], identity["platform_subject_id"])
        for record in source.records for identity in record["identities"]
        if identity["subject_namespace"] == "aiocqhttp:user"}
    if len({item[0] for item in identities}) != 1:
        raise RuntimeError("memory_acceptance_requires_one_source_account")
    account = next(iter(identities))[0]
    persona = v1_setting(configuration, "basic_config.plugin_specific_persona_id", "")
    if not persona or v1_setting(configuration, "basic_config.enable_multi_persona_mode", False):
        raise RuntimeError("memory_acceptance_requires_explicit_source_persona")
    data = build_data_plan(v1_root, v1_configuration=configuration)
    group_ids = {item["source_group_id"] for item in data.group_networks}
    group_ids.update(group for item in data.worldbook_items for group in item.group_ids)
    group_ids.update(group for item in data.member_profiles for group in item.group_ids)
    targets = [dict(target_id="person-" + str(index), platform_id="qq-main", account_id=account,
        bot_id="bot-a", participant_id=user) for index, (_, user) in enumerate(sorted(identities))]
    groups = [dict(target_id="group-" + str(index), platform_id="qq-main", account_id=account,
        bot_id="bot-a", group_id=group) for index, group in enumerate(sorted(group_ids))]
    settings = multi_config(targets=targets, group_targets=groups, personas=[
        dict(bot_id="bot-a", persona_id=persona, role_id="role-a"),
        dict(bot_id="bot-a", persona_id="acceptance-other-persona", role_id="role-b")])
    native = MultiNativeContext()
    native.persona_records = {persona: {"name": persona, "prompt": "测试宿主人格"},
        "acceptance-other-persona": {"name": "acceptance-other-persona", "prompt": "独立角色"}}
    native.persona_manager.get_persona_v3_by_id = native.persona_records.get
    native.persona_manager.personas_v3 = list(native.persona_records.values())
    native.selections["qq-main"] = persona
    native.platform.client._wsr_api_clients.clear()
    native.platform.client._wsr_api_clients[account] = object()
    owners = LegacyMemoryMaterials.inspect_snapshot(memory_path)["owners"]
    def matching(owner):
        value = owner["source"]
        return (value["persona_id"] in (persona, "legacy") and
            (value["bot_id"] == "legacy-unscoped" or value["bot_id"].split(":")[-1] == account))
    return native, settings, targets, groups, [owner for owner in owners if matching(owner)], persona


def _query_all(store, context, *, group=False):
    documents, cursor, seen = {}, None, set()
    for _ in range(20000):
        page = _require(store.query(context, cursor=cursor, max_result_chars=48000,
            group_read_authorized=group), "memory_history_query")
        for item in page["items"]:
            if item.get("current_fact") is not False or item.get("historical_only") is not True:
                raise RuntimeError("memory_history_became_current_fact")
            document = documents.setdefault(item["id"], {"kind": item["kind"], "text": ""})
            if len(document["text"]) != item["excerpt_start"]:
                raise RuntimeError("memory_history_pagination_gap")
            document["text"] += item["text"]
        cursor = page["next_cursor"]
        if cursor is None:
            return Counter((item["kind"], item["text"]) for item in documents.values())
        if cursor in seen:
            raise RuntimeError("memory_history_pagination_repeated")
        seen.add(cursor)
    raise RuntimeError("memory_history_pagination_stalled")


def _projection_rows(runtime, context, *, group=False):
    connection = sqlite3.connect(runtime.data_root / DATABASE_FILENAME)
    try:
        native_scope_match = ("target_native_scope_id=?" if group
                              else "target_native_scope_id IN ('', ?)")
        return Counter((row[0], row[1]) for row in connection.execute(
            "SELECT material_kind,text_content FROM legacy_memory_materials WHERE target_installation_id=? "
            "AND target_bot_id=? AND target_role_id=? AND target_scope_kind=? AND target_actor_id=? "
            "AND target_platform=? AND target_account_id=? AND " + native_scope_match,
            (context.scope.installation_id, context.scope.bot_id, context.role_binding.role.subject_id,
             "group" if group else "private", "" if group else context.actor.subject.subject_id,
             context.scope.platform, context.scope.account_id, context.scope.native_scope_id)))
    finally:
        connection.close()


def _group_context(controller, target, base, at):
    scope = replace(base.scope, kind=ScopeKind.GROUP, native_scope_id=target["group_id"],
        conversation_id="memory-acceptance-group:" + target["group_id"], session_id=target["group_id"])
    PersonaDirectory(controller.runtime).register_route(
        ConversationRoute(scope, group_id=target["group_id"]), observed_at=at)
    directory = PersistentIdentityDirectory(controller.runtime)
    binding = directory.resolve_role(scope, observed_at=at)
    if not binding.is_success:
        if binding.failure.code != "role_binding_missing":
            raise RuntimeError("memory_group_binding_invalid")
        role_binding = directory.bind_role(scope=scope, role=base.role_binding.role,
            expected_revision=0, observed_at=at)
    else:
        role_binding = binding.unwrap()
    return TaskContext(base.actor, role_binding, AudienceRef(scope, (base.actor.subject,)))


async def _apply_memory(api, migration, root, session, *, owner_ids=(), group_mappings=()):
    preview = _require(api._data_plan(migration, root, session, memory_owner_ids=owner_ids,
        memory_group_mappings=group_mappings), "data_plan")
    raw = Request({"type": "http", "method": "POST", "path": "/",
                   "headers": [], "query_string": b""})
    with bind_request_context(PluginRequest(raw, username="acceptance-admin")):
        applied = _require(await api._data_apply(migration, root, session,
            preview["plan_token"], "", "", False, False, False, False, False, False,
            import_memory_database=True, memory_owner_ids=owner_ids,
            confirm_memory_mapping=bool(owner_ids or group_mappings),
            memory_group_mappings=group_mappings), "data_apply")
    if applied["errors"]:
        raise RuntimeError("memory_migration_apply_errors")
    return preview, applied


async def run(v1_root: Path, v1_config: Path | None = None):
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
    settings = multi_config()
    targets, groups, owners, source_persona = [], [], [], ""
    if v1_config is not None:
        config_bytes = v1_config.read_bytes()
        native, settings, targets, groups, owners, source_persona = _identity_setup(
            v1_root, json.loads(config_bytes.decode("utf-8-sig")), memory_path)
    clock = DeterministicClock.at(NOW)
    async def selected_persona(_umo):
        return source_persona or "original"
    native_types = NativeAdapterTypes("4.28.2", FakeEvent, FakeProvider,
        SimpleNamespace, SimpleNamespace, FakeReverseApi, session_persona_override_lookup=selected_persona)
    with TemporaryDirectory(prefix="companion-v2-memory-data-acceptance-") as temporary:
        data_root = Path(temporary) / "v2-data"
        controller = AstrBotMultiController(native, settings, data_root,
            native_types=native_types, now=clock.now)
        controllers = [controller]
        try:
            _require(await controller.initialize_profile(), "initialize")
            _require(await controller.start(), "start")
            context = controller.session.authority.context(targets[0]["target_id"] if targets else "first", "role-a")
            session = SimpleNamespace(profile=SimpleNamespace(target=context),
                application=controller.session.application)
            migration = LegacyMigration(v1_root=v1_root)
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = controller

            preview, applied = await _apply_memory(api, migration, v1_root, session)
            if preview["memory_database"]["fingerprint"] != memory_plan.fingerprint:
                raise RuntimeError("preview_memory_source_changed")
            if preview["memory_database"].get("assets") != expected_assets:
                raise RuntimeError("preview_memory_asset_mismatch")
            result = applied.get("memory_archive")
            if (not result or result["table_counts"] != memory_plan.table_counts
                    or result.get("assets") != expected_assets
                    or result.get("source_complete") is not True):
                raise RuntimeError("memory_archive_count_mismatch")
            archive_path = data_root / "legacy-v1-archives" / result["archive_id"]
            expected_queries, imported = {}, Counter()
            group_mappings = tuple({"owner_id": owner["owner_id"],
                "target_id": target["target_id"], "role_id": "role-a"}
                for target in groups for owner in owners
                if owner["source"]["scope"] == "group"
                and owner["source"]["group_id"] == target["group_id"])
            for index, target in enumerate(targets):
                selected = tuple(owner["owner_id"] for owner in owners
                    if owner["source"]["scope"] == "private"
                    and owner["source"]["actor_id"] == target["participant_id"])
                if not selected and not (index == 0 and group_mappings):
                    continue
                person_context = controller.session.authority.context(target["target_id"], "role-a")
                person_session = SimpleNamespace(profile=SimpleNamespace(target=person_context),
                    application=controller.session.application)
                arguments = dict(owner_ids=selected, group_mappings=group_mappings if index == 0 else ())
                plan, applied = await _apply_memory(api, migration, v1_root, person_session, **arguments)
                projection = applied["memory_materials"]
                if projection["imported"] != plan["memory_database"]["projection"]["imported"]:
                    raise RuntimeError("memory_projection_preview_mismatch")
                imported.update(projection["imported"])
                _, repeated = await _apply_memory(api, migration, v1_root, person_session, **arguments)
                if repeated["memory_materials"].get("already_present") is not True:
                    raise RuntimeError("memory_projection_retry_not_idempotent")
            for target in targets:
                person_context = controller.session.authority.context(target["target_id"], "role-a")
                expected = _projection_rows(controller.runtime, person_context)
                if _query_all(controller.session.application.memory.query.legacy, person_context) != expected:
                    raise RuntimeError("memory_private_content_or_identity_mismatch")
                expected_queries[target["target_id"]] = expected
                other = controller.session.authority.context(target["target_id"], "role-b")
                directory = controller.session.authority.identities
                directory.issue_grant(grant_id="acceptance-other-role-memory-" + target["target_id"],
                    subject=other.actor.subject, scope=other.scope, capability="memory.read",
                    tier=AuthorizationTier.STANDARD, valid_from=NOW, expected_revision=directory.revision)
                if _query_all(controller.session.application.memory.query.legacy, other):
                    raise RuntimeError("memory_private_cross_role_leak")
            for target in groups:
                group_context = _group_context(controller, target, context, clock.now())
                expected = _projection_rows(controller.runtime, group_context, group=True)
                store = controller.session.application.memory.query.legacy
                denied = store.query(group_context)
                if denied.is_success or denied.failure.code != "group_memory_access_denied":
                    raise RuntimeError("memory_group_read_authority_bypassed")
                if _query_all(store, group_context, group=True) != expected:
                    raise RuntimeError("memory_group_content_or_identity_mismatch")
                expected_queries[target["target_id"]] = expected
            if targets and sum(sum(values.values()) for values in expected_queries.values()) != sum(imported.values()):
                raise RuntimeError("memory_query_verification_count_mismatch")
            await controller.terminate()

            restarted = AstrBotMultiController(native, settings, data_root,
                native_types=native_types, now=clock.now)
            controllers.append(restarted)
            loaded = _require(await restarted.load_existing(), "reload")
            if not loaded.get("loaded"):
                raise RuntimeError("reload_not_loaded")
            _require(await restarted.start(), "restart")
            for target in targets:
                person_context = restarted.session.authority.context(target["target_id"], "role-a")
                if _query_all(restarted.session.application.memory.query.legacy, person_context) != expected_queries[target["target_id"]]:
                    raise RuntimeError("restarted_private_memory_mismatch")
            if targets:
                base_context = restarted.session.authority.context(targets[0]["target_id"], "role-a")
                for target in groups:
                    group_context = _group_context(restarted, target, base_context, clock.now())
                    if _query_all(restarted.session.application.memory.query.legacy, group_context, group=True) != expected_queries[target["target_id"]]:
                        raise RuntimeError("restarted_group_memory_mismatch")

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
            if verify_v1_archive(archive_path) != verified:
                raise RuntimeError("memory_archive_changed_during_query")
            if v1_config is not None and v1_config.read_bytes() != config_bytes:
                raise RuntimeError("memory_source_configuration_changed")

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
                "query_acceptance": {"enabled": v1_config is not None,
                    "private_targets": len(targets), "group_targets": len(groups),
                    "explicit_group_owner_mappings": len(group_mappings),
                    "imported": dict(imported), "verified_materials": sum(imported.values()),
                    "exact_content_after_restart": bool(targets),
                    "duplicate_import_verified": bool(targets),
                    "cross_role_isolation": bool(targets),
                    "archive_unchanged_after_queries": True},
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
    parser.add_argument("--v1-config", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.v1_root, args.v1_config)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
