"""Verify role canon and exact person-private history through formal migration routes."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS

from tests.astrbot_data_root import assert_sdk_database_isolated
from astrbot.api.web import PluginRequest, bind_request_context
from astrbot.core import db_helper
from starlette.requests import Request

from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.legacy_config import V1_HOST_CONFIG_NAME, v1_setting
from astrbot_host.legacy_private_memory_api import PrivateMemoryMigrationAPI
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot_host.persona_workshop_api import PersonaWorkshopWebAPI
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.legacy.migration import LegacyMigration
from companion_v2.legacy.private_memory import build_private_memory_plan
from companion_v2.role_profile.configuration import (GROUP, RoleProfileConfigurationOwner,
    configuration_fields, target_for)
from tests.legacy_data_acceptance_process import _require, _role_context
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW


async def _call(handler, body=None):
    payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    raw = Request({"type": "http", "method": "GET" if body is None else "POST",
        "path": "/acceptance", "scheme": "http", "headers": [], "query_string": b""}, receive)
    with bind_request_context(PluginRequest(raw, username="acceptance-admin")):
        response = await handler()
    if response.get("status") != "ok":
        raise RuntimeError("migration_route_failed:" + str(response.get("data", {}).get("code", "unknown")))
    return response["data"]


def _query_all(store, context):
    documents, cursor, seen = {}, None, set()
    for _ in range(10000):
        page = _require(store.query(context, cursor=cursor, max_result_chars=48000), "history_query")
        for item in page["items"]:
            if (item.get("current_fact") is not False or item.get("historical_only") is not True
                    or item.get("execution_restored") is not False):
                raise RuntimeError("history_became_current_or_executable")
            previous = documents.setdefault(item["id"], {"text": "", "kind": item["kind"],
                "person": item["source_person_id"], "field": item["source_field"]})
            if len(previous["text"]) != item["excerpt_start"]:
                raise RuntimeError("history_pagination_gap")
            previous["text"] += item["text"]
        cursor = page["next_cursor"]
        if cursor is None:
            return Counter((item["kind"], item["person"], item["field"], item["text"])
                           for item in documents.values())
        if cursor in seen:
            raise RuntimeError("history_pagination_repeated")
        seen.add(cursor)
    raise RuntimeError("history_pagination_stalled")


def _expected_history(records):
    return Counter((item["kind"], record["person_id"], item["attributes"]["source_field"], item["text"])
                   for record in records for item in record["materials"])


async def run(v1_root: Path, v1_config: Path):
    assert_sdk_database_isolated(db_helper)
    config_bytes = v1_config.read_bytes()
    config = json.loads(config_bytes.decode("utf-8-sig"))
    source = build_private_memory_plan(v1_root, config)
    if source.source_error or not source.records:
        raise RuntimeError("private_history_source_unavailable")
    source_persona = v1_setting(config, "basic_config.plugin_specific_persona_id", "")
    if not source_persona or v1_setting(config, "basic_config.enable_multi_persona_mode", False):
        raise RuntimeError("role_source_requires_explicit_persona_mapping")
    identities = sorted({(identity["bot_account_id"].split(":", 1)[-1], identity["platform_subject_id"])
                         for record in source.records for identity in record["identities"]
                         if identity["subject_namespace"] == "aiocqhttp:user"})
    if len({item[0] for item in identities}) != 1:
        raise RuntimeError("acceptance_requires_one_source_account")
    targets = [dict(target_id="person-" + str(index), platform_id="qq-main", account_id=account,
        bot_id="bot-a", participant_id=participant) for index, (account, participant) in enumerate(identities)]
    settings = multi_config(targets=targets, personas=[
        dict(bot_id="bot-a", persona_id=source_persona, role_id="role-a"),
        dict(bot_id="bot-a", persona_id="acceptance-other-persona", role_id="role-b")])
    native = MultiNativeContext()
    native.persona = {"name": source_persona, "prompt": "姓名：测试宿主后备人格"}
    native.persona_records = {source_persona: native.persona,
        "acceptance-other-persona": {"name": "acceptance-other-persona", "prompt": "独立角色"}}
    native.persona_manager.personas_v3 = list(native.persona_records.values())
    native.persona_manager.get_persona_v3_by_id = native.persona_records.get
    native.selections["qq-main"] = source_persona
    clients = native.platform.client._wsr_api_clients
    clients.clear()
    clients.update({identities[0][0]: object()})
    async def selected_persona(_umo):
        return source_persona
    types = NativeAdapterTypes("4.28.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi,
        session_persona_override_lookup=selected_persona)
    migration = LegacyMigration(v1_root=v1_root, v1_configuration=config)
    with TemporaryDirectory(prefix="companion-670-700-identity-acceptance-") as temporary:
        base = Path(temporary) / "data"
        saved_config = base / "config" / V1_HOST_CONFIG_NAME
        saved_config.parent.mkdir(parents=True)
        saved_config.write_bytes(config_bytes)
        data_root = base / "plugin_data" / "astrbot_plugin_private_companion" / "companion-7"
        data_root.parent.mkdir(parents=True)
        legacy_marker = data_root.parent / "companions.json"
        legacy_marker.write_bytes(b'{"legacy_layout_sentinel":true}\n')
        from astrbot_host.storage_location import resolve_data_root
        if resolve_data_root(data_root.parent) != data_root.resolve():
            raise RuntimeError("takeover_data_root_not_isolated")
        controller = AstrBotMultiController(native, settings, data_root, native_types=types, now=lambda: NOW)
        controllers = [controller]
        expected_by_target, profile_values, imported = {}, {}, Counter()
        try:
            _require(await controller.initialize_profile(), "initialize")
            _require(await controller.start(), "start")
            for index, target in enumerate(targets):
                context = controller.session.authority.context(target["target_id"], "role-a")
                session = NS(profile=NS(target=context), application=controller.session.application)
                view = NS(runtime=controller.runtime, now=lambda: NOW, data_root=data_root,
                    session=session, last_session=None, _terminated=False, _control_lock=asyncio.Lock(),
                    controller=controller)
                legacy = LegacyMigrationWebAPI(view)
                async def fixed_source(_root_override=None, *, session=None):
                    return migration, v1_root, "fixed-acceptance-source"
                legacy._migration = fixed_source
                if index == 0:
                    workshop = PersonaWorkshopWebAPI(view)
                    plan = await _call(workshop.profile_migration_plan, {"persona_id": source_persona})
                    if plan["source"]["kind"] != "v1_world_knowledge" or not plan["changes"]:
                        raise RuntimeError("world_knowledge_role_profile_not_planned")
                    if plan["rejected_fields"]:
                        raise RuntimeError("role_profile_fields_over_limit")
                    profile_values = dict(plan["changes"])
                    body = {"persona_id": source_persona, "plan_token": plan["plan_token"],
                        "edit_token": plan["edit_token"], "changes": profile_values}
                    await _call(workshop.profile_migration_apply, body)
                    if not (await _call(workshop.profile_migration_apply, body))["replayed"]:
                        raise RuntimeError("role_profile_retry_not_idempotent")
                api = PrivateMemoryMigrationAPI(legacy)
                plan = await _call(api.plan)
                records = source.matching(account_id=context.scope.account_id,
                    native_actor_id=context.actor.principal.native_account_id)
                expected = _expected_history(records)
                if not records or plan["matched_material_count"] != sum(expected.values()):
                    raise RuntimeError("private_identity_match_incomplete")
                body = {"plan_token": plan["plan_token"], "confirmed": True}
                result = await _call(api.apply, body)
                if not (await _call(api.apply, body))["already_present"]:
                    raise RuntimeError("private_history_retry_not_idempotent")
                imported.update(result["imported"])
                if _query_all(session.application.memory.query.legacy, context) != expected:
                    raise RuntimeError("private_history_content_or_user_isolation_mismatch")
                expected_by_target[target["target_id"]] = expected
                other = _role_context(context, "role-b", runtime=controller.runtime, at=NOW)
                directory = controller.session.authority.identities
                directory.issue_grant(grant_id="acceptance-other-role-memory-" + str(index),
                    subject=other.actor.subject, scope=other.scope, capability="memory.read",
                    tier=AuthorizationTier.STANDARD, valid_from=NOW, expected_revision=directory.revision)
                if _query_all(session.application.memory.query.legacy, other):
                    raise RuntimeError("private_history_cross_role_leak")
            await controller.terminate()
            reopened = AstrBotMultiController(native, settings, data_root, native_types=types, now=lambda: NOW)
            controllers.append(reopened)
            if not _require(await reopened.load_existing(), "reload").get("loaded"):
                raise RuntimeError("saved_profile_not_loaded")
            _require(await reopened.start(), "restart")
            for target in targets:
                context = reopened.session.authority.context(target["target_id"], "role-a")
                if _query_all(reopened.session.application.memory.query.legacy, context) != expected_by_target[target["target_id"]]:
                    raise RuntimeError("restarted_private_history_mismatch")
                snapshot = RoleProfileConfigurationOwner(reopened.runtime).read(target_for(context), configuration_fields())
                if any(snapshot.fields[GROUP + "." + name].value != value for name, value in profile_values.items()):
                    raise RuntimeError("restarted_role_profile_mismatch")
            if (v1_config.read_bytes() != config_bytes or
                    build_private_memory_plan(v1_root, config).source_fingerprint != source.source_fingerprint):
                raise RuntimeError("legacy_source_changed")
            if legacy_marker.read_bytes() != b'{"legacy_layout_sentinel":true}\n':
                raise RuntimeError("legacy_takeover_parent_changed")
            sends = sum(1 for platform in native.platforms.values()
                for action, _ in platform.client._api._wsr_api.calls
                if action in {"send_private_msg", "send_group_msg", "send_msg"})
            calls = len(native.provider.client.state.calls)
            if sends or calls:
                raise RuntimeError("unexpected_external_call")
            return {"source_configuration_sha256": hashlib.sha256(config_bytes).hexdigest(),
                "role_profile_source": "v1_world_knowledge", "role_profile_fields": sorted(profile_values),
                "private_people": len(targets), "imported": dict(imported),
                "material_count": sum(imported.values()), "source_rejected_records": len(source.rejected),
                "restarted_targets_verified": len(targets), "exact_content_verified": True,
                "cross_user_and_role_isolation": True, "duplicate_retries_verified": True,
                "historical_only": True, "execution_restored": False,
                "source_unchanged": True, "model_calls": calls, "platform_sends": sends}
        finally:
            for instance in reversed(controllers):
                await instance.terminate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", required=True, type=Path)
    parser.add_argument("--v1-config", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.v1_root, args.v1_config)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
