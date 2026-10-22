"""Import every readable V1 profile into a disposable AstrBot host and reload it."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

# Keep AstrBot's import-time database under a disposable test root.
from tests.astrbot_data_root import assert_sdk_database_isolated
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot.core import db_helper
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.execution.models import TaskContext
from companion_v2.foundation.clock import DeterministicClock
from companion_v2.foundation.refs import AudienceRef, ScopeKind
from companion_v2.legacy.archive import build_v1_archive_plan, verify_v1_archive
from companion_v2.legacy.data_migration import build_data_plan
from companion_v2.legacy.migration import LegacyMigration
from companion_v2.role_work.journal import JournalKey, JournalKind
from companion_v2.foundation.refs import RoleOwnerRef
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target_group_id(source_group_id: str) -> str:
    return "acceptance-" + hashlib.sha256(source_group_id.encode("utf-8")).hexdigest()[:16]


def _target_role_id(source_persona_id: str, target_id="first") -> str:
    if not source_persona_id and target_id == "first":
        return "role-a"
    identity = json.dumps([str(target_id), source_persona_id or "primary"],
                          ensure_ascii=True, separators=(",", ":"))
    return "migration-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _role_context(base_context, role_id, *, runtime=None, at=None):
    if base_context.role_binding.role.subject_id == role_id:
        return base_context
    role = replace(base_context.role_binding.role, subject_id=role_id)
    if runtime is None:
        raise ValueError("mapped_role_requires_persistent_binding")
    from companion_v2.identity_policy.personas import ConversationRoute, PersonaDirectory
    from companion_v2.identity_policy.repository import PersistentIdentityDirectory
    scope = replace(base_context.scope, conversation_id="migration-acceptance:" + role_id)
    PersonaDirectory(runtime).register_route(ConversationRoute(scope, user=base_context.actor.subject),
                                             observed_at=at)
    identities = PersistentIdentityDirectory(runtime)
    existing = identities.resolve_role(scope, observed_at=at)
    if existing.is_success:
        binding = existing.unwrap()
        if binding.role != role:
            raise RuntimeError("mapped_role_binding_changed")
    else:
        if existing.failure.code != "role_binding_missing":
            raise RuntimeError("mapped_role_binding_invalid")
        binding = identities.bind_role(scope=scope, role=role, expected_revision=0, observed_at=at)
    return TaskContext(base_context.actor, binding,
        AudienceRef(scope, (base_context.actor.subject,)))


def _require(outcome, label: str):
    if not outcome.is_success:
        failure = outcome.failure
        raise RuntimeError(f"{label}:{getattr(failure, 'code', 'failed')}")
    return outcome.unwrap()


async def _apply(api, migration, root, session, *, source_group_id="", source_persona_id="",
                 import_reactions=False, import_group_network=False, confirm_member_ids=False,
                 import_journals=False, confirm_persona_mapping=False, import_worldbook=False,
                 import_archive=False, import_reference_images=False, import_wardrobe_items=False):
    plan = _require(api._data_plan(migration, root, session, source_group_id, source_persona_id),
                    "data_plan")
    request = PluginRequest(Request({"type": "http", "method": "POST", "path": "/",
        "headers": [], "query_string": b""}), username="acceptance-admin")
    with bind_request_context(request):
        return _require(await api._data_apply(
            migration, root, session, plan["plan_token"], source_group_id, source_persona_id,
            import_reactions, import_group_network, confirm_member_ids, import_journals,
            confirm_persona_mapping, import_worldbook, import_archive,
            import_reference_images=import_reference_images, import_wardrobe_items=import_wardrobe_items,
            confirm_reference_persona_mapping=confirm_persona_mapping), "data_apply")


def _verify_references(application, context, source_plan, root):
    service = application.references
    owner = service.owner(context)
    assets = service.assets.list(owner)
    by_hash = {asset.content_hash.sha256: asset for asset in assets}
    expected = {item.sha256: item for item in source_plan.reference_images}
    expected.update({item.image.sha256: item.image for item in source_plan.wardrobe_items
                     if item.image is not None})
    from companion_v2.legacy.data_migration import load_reference_image
    for sha, item in expected.items():
        asset = by_hash.get(sha)
        if asset is None or service.assets.get_payload(owner, asset.asset_id) != load_reference_image(root, item):
            raise RuntimeError("reference_payload_mismatch")
        if not set(item.roles) <= set(service.assets.roles_of(owner, asset.asset_id)):
            raise RuntimeError("reference_roles_mismatch")
    items = {item.item_id: item for item in service.assets.list_items(owner)}
    for item in source_plan.wardrobe_items:
        saved = items.get(item.item_id)
        if saved is None or (saved.name, saved.description, saved.tags) != (
                item.name, item.description, tuple(sorted(item.tags))):
            raise RuntimeError("wardrobe_content_mismatch")
        if item.image is not None and saved.asset_id != by_hash[item.image.sha256].asset_id:
            raise RuntimeError("wardrobe_reference_mismatch")
    if len(assets) != len(expected) or len(items) != len(source_plan.wardrobe_items):
        raise RuntimeError("reference_owner_isolation_mismatch")
    return {"reference_payloads": len(expected), "wardrobe_items": len(items)}


def _source_files(root, config_path, plans):
    files = {
        root / "companions.json",
        root / "reaction_expression_library" / "catalog.json",
        config_path,
        root / "framework_work" / "work.db",
        root / "framework_work" / "delivery.db",
        root / "framework_world" / "album.db",
    }
    profiles = root / "persona_profiles"
    if profiles.is_dir() and not profiles.is_symlink():
        files.update(path for path in profiles.iterdir()
                     if path.is_file() and path.suffix.lower() in (".json", ".db"))
    for plan in plans:
        files.update(root / item.relative_path for item in plan.reaction_assets)
    return tuple(sorted(path for path in files if path.is_file()))


async def run(v1_root: Path, v1_config_path: Path, *, target_sources=None,
              skip_incomplete_archive=False) -> dict:
    assert_sdk_database_isolated(db_helper)
    target_sources = target_sources or {"first": (v1_root, v1_config_path)}
    source_bundles = {}
    matrix_rows = []
    source_files = set()
    for target_id, (source_root, config_path) in target_sources.items():
        source_root, config_path = Path(source_root), Path(config_path)
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        migration = LegacyMigration(v1_root=source_root, v1_configuration=config)
        archive_plan = build_v1_archive_plan(source_root)
        inventory = build_data_plan(source_root, v1_configuration=config)
        source_plans = []
        for source in inventory.persona_sources:
            if source["state"] != "ready":
                continue
            plan = build_data_plan(source_root, source_persona_id=source["persona_id"],
                                   v1_configuration=config)
            source_plans.append((source["persona_id"], plan, plan.document()))
        if not source_plans:
            raise RuntimeError("no_ready_persona_profiles:" + str(target_id))
        files = _source_files(source_root, config_path,
                              [plan for _, plan, _ in source_plans])
        source_files.update(files)
        bundle = {"root": source_root, "config_path": config_path, "migration": migration,
                  "archive_plan": archive_plan, "source_plans": source_plans}
        source_bundles[str(target_id)] = bundle
        matrix_rows.extend((str(target_id), source[0], source[1], source[2], bundle)
                           for source in source_plans)
    if not matrix_rows:
        raise RuntimeError("no_ready_persona_profiles")
    before = {str(path): _fingerprint(path) for path in sorted(source_files)}

    native = MultiNativeContext()
    clock = DeterministicClock.at(NOW)
    async def selected_persona(_umo):
        return "original"

    native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
                                      SimpleNamespace, FakeReverseApi,
                                      session_persona_override_lookup=selected_persona)
    with TemporaryDirectory(prefix="companion-v2-complete-v1-data-acceptance-") as temporary:
        data_root = Path(temporary) / "v2-data"
        controller = AstrBotMultiController(native, multi_config(), data_root,
            native_types=native_types, now=clock.now)
        controllers = [controller]
        role_mappings = []
        groups = []
        archive_results = {}
        totals = {"reaction_assets_expected": 0, "reaction_assets_created": 0,
            "reaction_assets_remaining": 0, "journals_expected": 0, "journals_created": 0,
            "journals_remaining": 0, "journal_fragments_expected": 0,
            "journal_derivative_records_created": 0, "worldbook_entries": 0,
            "worldbook_members": 0, "group_worldbook_entries": 0,
            "group_worldbook_members": 0, "private_duplicate_retries": 0,
            "archive_files": 0, "archive_bytes": 0, "reference_images_created": 0,
            "wardrobe_items_created": 0}
        try:
            _require(await controller.initialize_profile(), "initialize")
            _require(await controller.start(), "start")
            api = LegacyMigrationWebAPI.__new__(LegacyMigrationWebAPI)
            api.controller = SimpleNamespace(runtime=controller.session.runtime, now=clock.now,
                                             data_root=data_root)

            for target_id, source_persona_id, source_plan, expected, bundle in matrix_rows:
                v1_root = bundle["root"]
                migration = bundle["migration"]
                base_context = controller.session.authority.context(target_id, "role-a")
                role_id = _target_role_id(source_persona_id, target_id)
                private_context = _role_context(base_context, role_id,
                    runtime=controller.runtime, at=clock.now())
                private_session = SimpleNamespace(
                    profile=SimpleNamespace(target=private_context),
                    application=controller.session.application)
                totals["reaction_assets_expected"] += expected["reaction_assets"]["ready"]
                totals["journals_expected"] += expected["journals"]["ready"]
                totals["journal_fragments_expected"] += sum(
                    len(item.dream_fragments) for item in source_plan.journals)
                private_counts = {"reaction_created": 0, "journal_created": 0,
                    "journal_derivatives_created": 0, "reaction_remaining": 0,
                    "journal_remaining": 0}
                archive_result = archive_results.get(target_id)
                private_worldbook = None
                for attempt in range(101):
                    result = await _apply(api, migration, v1_root, private_session,
                        source_persona_id=source_persona_id, confirm_member_ids=True,
                        import_reactions=True, import_journals=bool(source_plan.journals),
                        confirm_persona_mapping=True, import_worldbook=True,
                        import_reference_images=bool(source_plan.reference_images),
                        import_wardrobe_items=bool(source_plan.wardrobe_items),
                        import_archive=(target_id not in archive_results
                                        and not skip_incomplete_archive))
                    if result["errors"]:
                        raise RuntimeError("private_import_errors:" + ",".join(sorted(
                            {str(item.get("reason", "unknown")) for item in result["errors"]})))
                    for field in ("reaction_created", "journal_created",
                                  "journal_derivatives_created"):
                        private_counts[field] += result[field]
                    private_counts["reaction_remaining"] = result["reaction_remaining"]
                    private_counts["journal_remaining"] = result["journal_remaining"]
                    references = result["reference_images"] or {}
                    totals["reference_images_created"] += references.get("reference_created", 0)
                    totals["wardrobe_items_created"] += references.get("wardrobe_created", 0)
                    if result["archive"]:
                        archive_result = result["archive"]
                        if target_id not in archive_results:
                            archive_results[target_id] = archive_result
                            totals["archive_files"] += archive_result["file_count"]
                            totals["archive_bytes"] += archive_result["total_bytes"]
                    private_worldbook = result["worldbook"]
                    if (not private_counts["reaction_remaining"] and not private_counts["journal_remaining"]
                            and not references.get("reference_remaining") and not references.get("wardrobe_remaining")):
                        break
                    if attempt == 100 or not (any(result[field] for field in (
                            "reaction_created", "journal_created", "journal_derivatives_created"))
                            or references.get("reference_created") or references.get("wardrobe_created")):
                        raise RuntimeError("private_import_batch_stalled")

                totals["reaction_assets_created"] += private_counts["reaction_created"]
                totals["reaction_assets_remaining"] += private_counts["reaction_remaining"]
                totals["journals_created"] += private_counts["journal_created"]
                totals["journals_remaining"] += private_counts["journal_remaining"]
                totals["journal_derivative_records_created"] += private_counts["journal_derivatives_created"]
                if archive_result is None and not skip_incomplete_archive:
                    raise RuntimeError("v1_archive_not_written")
                totals["worldbook_entries"] += private_worldbook["entries_imported"]
                totals["worldbook_members"] += private_worldbook["members_imported"]

                repeated_private = await _apply(api, migration, v1_root, private_session,
                    source_persona_id=source_persona_id, confirm_member_ids=True,
                    import_reactions=True, import_journals=bool(source_plan.journals),
                    confirm_persona_mapping=True, import_worldbook=True,
                    import_reference_images=bool(source_plan.reference_images),
                    import_wardrobe_items=bool(source_plan.wardrobe_items))
                if repeated_private["errors"]:
                    raise RuntimeError("private_retry_errors:" + ",".join(sorted(
                        {str(item.get("reason", "unknown")) for item in repeated_private["errors"]})))
                if any(repeated_private[field] for field in (
                        "reaction_created", "journal_created", "journal_derivatives_created",
                        "reaction_remaining", "journal_remaining", "journal_derivatives_remaining")):
                    raise RuntimeError("private_retry_not_idempotent")
                if any((repeated_private["reference_images"] or {}).get(field, 0) for field in (
                        "reference_created", "reference_roles_added", "wardrobe_created",
                        "reference_remaining", "wardrobe_remaining")):
                    raise RuntimeError("reference_retry_not_idempotent")
                _verify_references(private_session.application, private_context, source_plan, v1_root)
                retry_worldbook = repeated_private.get("worldbook") or {}
                retry_states = [retry_worldbook.get(field, "unchanged") for field in (
                    "base_state", "entries_state", "members_state", "group_state")]
                if any(state != "unchanged" for state in retry_states):
                    raise RuntimeError("private_worldbook_retry_not_idempotent")
                totals["private_duplicate_retries"] += 1

                group_ids = {item["source_group_id"] for item in source_plan.group_networks}
                group_ids.update(item["source_group_id"] for item in expected["worldbook"]["groups"])
                group_ids.update(item["source_group_id"]
                                 for item in expected["worldbook"]["member_profile_groups"])
                network_by_id = {item["source_group_id"]: item for item in source_plan.group_networks}
                for source_group_id in sorted(group_ids):
                    source_group = network_by_id.get(source_group_id)
                    target_scope = replace(private_context.scope, kind=ScopeKind.GROUP,
                        native_scope_id=_target_group_id(source_group_id))
                    group_context = TaskContext(private_context.actor,
                        replace(private_context.role_binding, scope=target_scope),
                        AudienceRef(target_scope, (private_context.actor.subject,)))
                    group_session = SimpleNamespace(profile=SimpleNamespace(target=group_context),
                        application=private_session.application)
                    result = await _apply(api, migration, v1_root, group_session,
                        source_group_id=source_group_id, source_persona_id=source_persona_id,
                        import_group_network=source_group is not None,
                        confirm_member_ids=True, import_worldbook=True)
                    if result["errors"]:
                        raise RuntimeError("group_import_errors:" + ",".join(sorted(
                            {str(item.get("reason", "unknown")) for item in result["errors"]})))
                    projection = None
                    duplicate_retry = None
                    if source_group is not None:
                        projection = controller.session.application.messages.group_network.projection(
                            group_context)
                        expected_counts = (len(source_group["members"]), len(source_group["edges"]))
                        actual_counts = (projection["member_count"], len(projection["edges"]))
                        if actual_counts != expected_counts:
                            raise RuntimeError("group_import_count_mismatch")
                        expected_members = {str(key) for key in source_group["members"]}
                        actual_members = {str(item["native_account_id"])
                                          for item in projection["members"]}
                        if actual_members != expected_members:
                            raise RuntimeError("group_import_member_isolation_mismatch")
                        expected_edges = {tuple(sorted((str(item["a"]), str(item["b"]))))
                                          for item in source_group["edges"]}
                        actual_edges = {tuple(sorted((str(item["a"]), str(item["b"]))))
                                        for item in projection["edges"]}
                        if actual_edges != expected_edges:
                            raise RuntimeError("group_import_edge_isolation_mismatch")
                    repeated = await _apply(api, migration, v1_root, group_session,
                        source_group_id=source_group_id, source_persona_id=source_persona_id,
                        import_group_network=source_group is not None,
                        confirm_member_ids=True, import_worldbook=True)
                    if repeated["errors"]:
                        raise RuntimeError("group_retry_errors")
                    duplicate_retry = (source_group is None or bool(repeated["group_network"]
                        and repeated["group_network"].get("duplicate")))
                    group_worldbook_duplicate_retry = (
                        repeated.get("worldbook", {}).get("group_state", "unchanged") == "unchanged")
                    if not duplicate_retry or not group_worldbook_duplicate_retry:
                        raise RuntimeError("group_retry_not_idempotent")
                    totals["group_worldbook_entries"] += result["worldbook"]["group_entries_imported"]
                    totals["group_worldbook_members"] += result["worldbook"]["group_members_imported"]
                    groups.append({
                        "target_id": target_id,
                        "persona_key": hashlib.sha256((source_persona_id or "primary").encode("utf-8")).hexdigest()[:8],
                        "source_group_key": hashlib.sha256(source_group_id.encode("utf-8")).hexdigest()[:10],
                        "members": projection["member_count"] if projection else 0,
                        "edges": len(projection["edges"]) if projection else 0,
                        "duplicate_retry": duplicate_retry,
                        "group_worldbook_duplicate_retry": group_worldbook_duplicate_retry,
                        "group_worldbook_entries": result["worldbook"]["group_entries_imported"],
                        "group_worldbook_members": result["worldbook"]["group_members_imported"],
                    })
                role_mappings.append({"target_id": target_id, "source_persona_id": source_persona_id,
                    "role_id": role_id, "source_plan": source_plan,
                    "expected": expected, "group_ids": sorted(group_ids), "bundle": bundle})

            await controller.terminate()
            reopened = AstrBotMultiController(native, multi_config(), data_root,
                native_types=native_types, now=clock.now)
            controllers.append(reopened)
            loaded = _require(await reopened.load_existing(), "reload")
            if not loaded.get("loaded"):
                raise RuntimeError("reload_not_loaded")
            _require(await reopened.start(), "restart")
            api.controller = SimpleNamespace(runtime=reopened.session.runtime, now=clock.now,
                                             data_root=data_root)

            archived_by_target = {}
            if not skip_incomplete_archive:
                for target_id, bundle in source_bundles.items():
                    archive_result = archive_results.get(target_id)
                    if archive_result is None:
                        raise RuntimeError("v1_archive_not_written:" + target_id)
                    archive_path = data_root / "legacy-v1-archives" / archive_result["archive_id"]
                    archived = verify_v1_archive(archive_path)
                    archive_plan = bundle["archive_plan"]
                    if (archived["file_count"] != len(archive_plan.files)
                            or archived["total_bytes"] != archive_plan.total_bytes):
                        raise RuntimeError("v1_archive_verification_mismatch:" + target_id)
                    archived_by_target[target_id] = archived

            reopened_groups = []
            persisted_dream_fragments = 0
            persisted_references = {"reference_payloads": 0, "wardrobe_items": 0}
            for mapping in role_mappings:
                target_id = mapping["target_id"]
                source_persona_id = mapping["source_persona_id"]
                role_id = mapping["role_id"]
                source_plan = mapping["source_plan"]
                expected = mapping["expected"]
                group_ids = mapping["group_ids"]
                bundle = mapping["bundle"]
                v1_root = bundle["root"]
                migration = bundle["migration"]
                reopened_base = _role_context(
                    reopened.session.authority.context(target_id, "role-a"), role_id,
                    runtime=reopened.runtime, at=clock.now())
                private_session = SimpleNamespace(profile=SimpleNamespace(target=reopened_base),
                    application=reopened.session.application)
                verified = _verify_references(private_session.application, reopened_base, source_plan, v1_root)
                for name, count in verified.items():
                    persisted_references[name] += count
                preview = _require(api._data_plan(migration, v1_root, private_session,
                    source_persona_id=source_persona_id), "reload_preview")
                if (preview["reaction_assets"]["already_present"] != expected["reaction_assets"]["ready"]
                        or preview["journals"]["already_present"] != expected["journals"]["ready"]
                        or (expected["worldbook"]["general_count"]
                            and not preview["worldbook"]["base_entries_matches"])
                        or (expected["worldbook"]["member_count"]
                            + expected["worldbook"]["member_profile_count"]
                            and not preview["worldbook"]["base_members_matches"])):
                    raise RuntimeError("reload_content_mismatch:" + target_id + ":"
                        + (source_persona_id or "primary") + ":reaction="
                        + str(preview["reaction_assets"]["already_present"]) + "/"
                        + str(expected["reaction_assets"]["ready"]) + ":journals="
                        + str(preview["journals"]["already_present"]) + "/"
                        + str(expected["journals"]["ready"]) + ":entries="
                        + str(preview["worldbook"]["base_entries_matches"]) + ":members="
                        + str(preview["worldbook"]["base_members_matches"]))
                journal_owner = RoleOwnerRef(reopened_base.scope.installation_id,
                    reopened_base.scope.bot_id, role_id)
                for item in source_plan.journals:
                    kind = JournalKind.DIARY if item.kind == "diary" else JournalKind.DREAM
                    journal_key = JournalKey(journal_owner, kind, item.local_date)
                    entry = reopened.session.application.role_journal.get(journal_key)
                    if entry is None or entry.draft.body != item.body:
                        raise RuntimeError("reload_journal_body_mismatch")
                    if item.dream_fragments:
                        derivatives = reopened.session.application.role_journal.derivatives(journal_key)
                        if (derivatives is None
                                or derivatives.material.dream_fragments != item.dream_fragments):
                            raise RuntimeError("reload_journal_derivatives_mismatch")
                        persisted_dream_fragments += len(derivatives.material.dream_fragments)
                if source_plan.journals and any(
                        source_item.body == other_item.body
                        for source_item in source_plan.journals
                        for other_mapping in role_mappings
                        if other_mapping["target_id"] != target_id
                        and other_mapping["source_persona_id"] == source_persona_id
                        for other_item in other_mapping["source_plan"].journals):
                    raise RuntimeError("synthetic_target_journal_fixture_not_distinct")
                source_group_entries = {item["source_group_id"]: item["entry_count"]
                                        for item in expected["worldbook"]["groups"]}
                source_group_members = {item["source_group_id"]: item["member_count"]
                                         for item in expected["worldbook"]["member_profile_groups"]}
                source_networks = {item["source_group_id"]: item for item in source_plan.group_networks}
                for source_group_id in group_ids:
                    scope = replace(reopened_base.scope, kind=ScopeKind.GROUP,
                        native_scope_id=_target_group_id(source_group_id))
                    group_context = TaskContext(reopened_base.actor,
                        replace(reopened_base.role_binding, scope=scope),
                        AudienceRef(scope, (reopened_base.actor.subject,)))
                    group_session = SimpleNamespace(profile=SimpleNamespace(target=group_context),
                        application=reopened.session.application)
                    group_preview = _require(api._data_plan(migration, v1_root, group_session,
                        source_group_id=source_group_id, source_persona_id=source_persona_id),
                        "reload_group_preview")
                    if (source_group_entries.get(source_group_id, 0)
                            + source_group_members.get(source_group_id, 0)
                            and not group_preview["worldbook_state"]["group_matches"]):
                        raise RuntimeError("reload_group_knowledge_mismatch")
                    source_network = source_networks.get(source_group_id)
                    if source_network is not None:
                        projection = reopened.session.application.messages.group_network.projection(
                            group_context)
                        expected_counts = (len(source_network["members"]), len(source_network["edges"]))
                        actual_counts = (projection["member_count"], len(projection["edges"]))
                        if actual_counts != expected_counts:
                            raise RuntimeError("reload_group_mismatch")
                        expected_members = {str(key) for key in source_network["members"]}
                        actual_members = {str(item["native_account_id"])
                                          for item in projection["members"]}
                        if actual_members != expected_members:
                            raise RuntimeError("reload_group_member_isolation_mismatch")
                        expected_edges = {tuple(sorted((str(item["a"]), str(item["b"]))))
                                          for item in source_network["edges"]}
                        actual_edges = {tuple(sorted((str(item["a"]), str(item["b"]))))
                                        for item in projection["edges"]}
                        if actual_edges != expected_edges:
                            raise RuntimeError("reload_group_edge_isolation_mismatch")
                        reopened_groups.append({
                            "target_id": target_id,
                            "persona_key": hashlib.sha256((source_persona_id or "primary").encode("utf-8")).hexdigest()[:8],
                            "source_group_key": hashlib.sha256(source_group_id.encode("utf-8")).hexdigest()[:10],
                            "members": projection["member_count"], "edges": len(projection["edges"])})

            send_actions = {"send_private_msg", "send_group_msg", "send_msg"}
            platform_sends = sum(1 for platform in native.platforms.values()
                for action, _ in platform.client._api._wsr_api.calls if action in send_actions)
            model_calls = len(native.provider.client.state.calls)
            if platform_sends or model_calls:
                raise RuntimeError("unexpected_external_call")
            source_inputs_unchanged = before == {str(path): _fingerprint(path)
                                                 for path in source_files if path.is_file()}
            archive_inventory_unchanged = all(
                build_v1_archive_plan(bundle["root"]).fingerprint
                == bundle["archive_plan"].fingerprint
                for bundle in source_bundles.values())
            v1_unchanged = source_inputs_unchanged and archive_inventory_unchanged
            if not source_inputs_unchanged:
                raise RuntimeError("v1_source_changed_during_import:source_inputs")
            if not skip_incomplete_archive and not archive_inventory_unchanged:
                raise RuntimeError("v1_source_changed_during_import:archive_inventory")
            findings_by_target = {
                target_id: {item.source_id: item.state
                            for item in bundle["migration"].discover().unwrap()}
                for target_id, bundle in source_bundles.items()}
            summary_plans = [row[2] for row in matrix_rows]
            archived = next(iter(archived_by_target.values()), None)
            return {
                "migration": {
                    "source_personas": len({row[1] for row in matrix_rows}),
                    "target_persona_mappings": len(matrix_rows),
                    "targets": sorted(source_bundles),
                    **totals,
                    "groups": groups,
                    "persisted_after_restart": {
                        "personas_verified": len(role_mappings),
                        "targets_verified": len(source_bundles),
                        "journal_fragments": persisted_dream_fragments,
                        **persisted_references,
                        "groups": reopened_groups,
                    },
                    "model_calls": model_calls,
                    "platform_sends": platform_sends,
                    "v1_unchanged": v1_unchanged,
                    "v1_source_inputs_unchanged": source_inputs_unchanged,
                    "archive_inventory_unchanged": archive_inventory_unchanged,
                    "archive_verified_after_restart": archived,
                    "archives_verified_by_target": archived_by_target,
                    "archive_skipped_due_to_incomplete_source": bool(skip_incomplete_archive),
                    "archive_source_issues": [
                        {"target_id": target_id, "path": path, "reason": reason}
                        for target_id, bundle in source_bundles.items()
                        for path, reason in bundle["archive_plan"].issues],
                },
                "v1_findings": next(iter(findings_by_target.values()), {}),
                "v1_findings_by_target": findings_by_target,
                "documented_omissions": {
                    "private_user_profiles": sum(plan.profile_summary["private_user_profiles"]
                                                  for plan in summary_plans),
                    "rejected_member_profiles": sum(len(plan.member_profile_rejected)
                                                    for plan in summary_plans),
                    "rejected_worldbook_items": sum(len(plan.worldbook_rejected)
                                                     for plan in summary_plans),
                    "unsafe_dream_fragments": sum(1 for plan in summary_plans
                        for item in plan.journal_rejected if item.get("kind") in (
                            "dream_fragment", "diary_dream_fragment")),
                    "work_delivery_state": summary_plans[0].work_delivery["import_state"],
                    "world_assets_state": summary_plans[0].world_assets["import_state"],
                },
            }
        finally:
            for instance in reversed(controllers):
                await instance.terminate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", type=Path, required=True)
    parser.add_argument("--v1-config", type=Path, required=True)
    parser.add_argument("--skip-incomplete-archive", action="store_true",
                        help="Import supported runtime data while reporting an unreadable archive source.")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.v1_root, args.v1_config,
                                     skip_incomplete_archive=args.skip_incomplete_archive)),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
