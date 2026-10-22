"""Apply a real V1 configuration to an isolated AstrBot V2 profile and reload it."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

# Keep AstrBot's import-time database under a disposable test root.
from tests.astrbot_data_root import assert_sdk_database_isolated

from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from astrbot_host.legacy_api import LegacyMigrationWebAPI
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot.core import db_helper
from astrbot_host.identity_derivation import derive_role_id
from astrbot_host.persona_catalog import available_personas
from companion_v2.configuration.models import ConfigLayer
from companion_v2.conversation.reply_settings import (
    GROUP as REPLY_GROUP, private_debounce_settings, target_for as reply_target, voice_policy,
)
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.legacy.migration import LegacyMigration
from companion_v2.model_gateway.budget import effective_soft
from astrbot_host.weather_settings import WeatherHostSettings, weather_settings
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes


def _require(outcome: Outcome, label: str):
    if not outcome.is_success:
        failure = outcome.failure
        # 带上 reason：迁移里同一个 code 可能有多条守卫，只有 reason 能指出是哪一条。
        raise RuntimeError(
            f"{label}:{getattr(failure, 'code', 'failed')}:"
            f"{getattr(failure, 'reason', '') or getattr(failure, 'message', '')}")
    return outcome.unwrap()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plugin_value(config, field_id):
    present, value = LegacyMigrationWebAPI._plugin_config_value(config, field_id)
    if not present:
        raise RuntimeError("plugin_config_value_missing")
    return value


def _difference_report(differences):
    """Keep field/category evidence without copying source values or private prompts."""
    explanations = {
        "already_present": "已有相同设置，保留现值。",
        "preserved_v2": "已有明确设置，保留现值。",
        "partial_mapping": "已接续可转换部分，行为存在差异，需核对。",
        "manual_required": "需要在升级页核对或补充配置。",
        "invalid_value": "旧值无法通过新配置校验，未自动写入。",
        "invalid_combination": "配置组合无法通过校验，未自动写入。",
        "unavailable": "当前运行环境未提供对应配置入口。",
    }
    return [{
        "field": item.get("field", item.get("field_id", "")),
        "source_key": item.get("source_key", ""),
        "kind": item.get("kind", "unknown"),
        "disposition": item.get("disposition", ""),
        "explanation": explanations.get(item.get("kind"), "按迁移规则保留差异，详见升级页预览。"),
    } for item in differences]


def _consumer_report(controller, session, api):
    application, context = session.application, session.profile.target
    snapshot = application.configuration._snapshot(
        api._operator(), reply_target(context), REPLY_GROUP, NOW, "configuration.read")
    values = {key.removeprefix(REPLY_GROUP + "."): item.value for key, item in snapshot.fields.items()}
    voice = voice_policy(values)
    debounce = private_debounce_settings(values)
    soft = effective_soft(application.runtime, context, controller.settings.common.budget_soft)
    host_voice = controller.settings.common.voice_reply_policy
    state_settings, _ = application.role_state.settings(context)
    if state_settings["enabled"]:
        application.role_state.access.check(context, "role.state.read")
        application.role_state.access.check(context, "role.state.maintain")
    from companion_v2.role_work.life.configuration import values as life_values, target_for as life_target
    life_settings = life_values(_require(application.configuration.read(api._operator(),
        target=life_target(context), group_id="role.life", observed_at=NOW), "life_settings"))
    if life_settings["enabled"]:
        for action in ("role.life.run", "role.life.read", "role.journal.write"):
            _require(application.tasks.identity.authorize(context.actor, scope=context.scope,
                capability=action, observed_at=NOW), "migrated_life_grant:" + action)
    return {
        "state_enabled_and_authorized": state_settings["enabled"],
        "life_enabled_and_authorized": life_settings["enabled"],
        "voice_enabled": voice is not None,
        "generation_mode": voice.generation_mode if voice else None,
        "conversion_scope": voice.conversion_scope if voice else None,
        "delivery_mode": voice.delivery_mode if voice else None,
        "private_cooldown_seconds": host_voice.cooldown("private"),
        "group_cooldown_seconds": host_voice.cooldown("group"),
        "effective_window_cooldown_seconds": voice.cooldown_seconds if voice else None,
        "private_debounce_enabled": debounce.enabled,
        "private_debounce_seconds": [debounce.min_seconds, debounce.max_seconds, debounce.total_seconds],
        "soft_budget_enabled": soft.enabled, "soft_budget_tokens": soft.tokens,
    }


async def run(v1_root: Path, v1_config_path: Path) -> dict:
    assert_sdk_database_isolated(db_helper)
    v1_config = json.loads(v1_config_path.read_text(encoding="utf-8-sig"))
    source_hash = _hash(v1_config_path)
    native = MultiNativeContext()
    types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace,
                               SimpleNamespace, FakeReverseApi)

    with TemporaryDirectory(prefix="companion-v2-v1-config-acceptance-") as temporary:
        data_root = Path(temporary) / "v2-data"
        saved_config_path = Path(temporary) / "v2-plugin-config.json"
        config = multi_config()

        def save_config(candidate):
            config.clear()
            config.update(candidate)
            saved_config_path.write_text(
                json.dumps(config, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")

        controller = AstrBotMultiController(native, config, data_root,
            native_types=types, now=lambda: NOW)
        controller.save_plugin_config = save_config
        controllers = [controller]
        try:
            _require(await controller.initialize_profile(), "initialize")
            _require(await controller.start(), "start")
            context = controller.session.authority.context("first", "role-a")
            session = SimpleNamespace(
                profile=SimpleNamespace(target=context),
                application=controller.session.application,
            )
            host_accounts = controller.session_topology.accounts()
            persona_ids = await available_personas(native) or ["[%None]"]
            for account in host_accounts:
                account["persona_roles"] = {
                    persona_id: derive_role_id(account["account_id"], persona_id)
                    for persona_id in persona_ids
                }
                account["persona_roles"][""] = derive_role_id(account["account_id"], None)
                account["persona_roles"]["[%None]"] = derive_role_id(account["account_id"], None)
                account["default_role_id"] = derive_role_id(account["account_id"], None)

            migration = LegacyMigration(
                v1_root=v1_root,
                v1_configuration=v1_config,
                configuration_registry=session.application.configuration.registry,
                host_accounts=host_accounts,
                configuration_scope_kind=ScopeKind.PRIVATE.value,
            )
            api = LegacyMigrationWebAPI(controller)
            configuration_receipts = []
            configuration = session.application.configuration
            original_patch = configuration.patch
            def record_patch(*args, **kwargs):
                receipt = original_patch(*args, **kwargs)
                if receipt.is_success:
                    configuration_receipts.extend(receipt.unwrap().changed_fields)
                return receipt
            request = PluginRequest(Request({"type": "http", "method": "POST", "path": "/",
                "headers": [], "query_string": b""}), username="acceptance-admin")
            with bind_request_context(request):
                preview = _require(api._plan(migration, v1_root, session), "plan")
                if not preview["intents"]:
                    raise RuntimeError("configuration_plan_empty")
                # Public previews deliberately redact weather credentials and host.
                # Verify the private prepared values, never the display placeholders.
                prepared, _, _, _ = api._prepare_intents(session, _require(migration.plan(), "source_plan"))
                intents = [{"scope": intent.scope, "group_id": intent.group_id,
                    "target_kind": intent.target_kind, "fields": sorted(intent.changes),
                    "values": dict(intent.changes)} for intent in prepared]
                target_layers = {}
                for intent in intents:
                    if intent["target_kind"] != "configuration_registry":
                        continue
                    target = api._scope_target(session, SimpleNamespace(
                        scope=intent["scope"], group_id=intent["group_id"],
                        target_kind=intent["target_kind"], changes=intent["values"]))
                    if target is None:
                        raise RuntimeError("configuration_target_missing:" + intent["group_id"])
                    layers = target_layers.setdefault(intent["group_id"], [])
                    if target.layer.value not in layers:
                        layers.append(target.layer.value)
                # role.growth.skills 的技能偏好已经改成安装级/角色级（SKILL_LAYERS），
                # 旧窗口值由 migrate_legacy_skill_values 提升为安装级兜底；
                # 这里只要求它落到安装级或角色级，不再要求窗口级。
                if "role.growth.skills" in target_layers and not set(target_layers["role.growth.skills"]) <= {
                        ConfigLayer.INSTALLATION.value, ConfigLayer.ROLE.value}:
                    raise RuntimeError("skill_target_layer_unexpected:"
                                       + str(target_layers["role.growth.skills"]))
                expected_receipts = Counter()
                for intent in intents:
                    prefix = (intent["group_id"] + "."
                              if intent["target_kind"] == "configuration_registry" else
                              "semantic." if intent["target_kind"] == "semantic_config" else
                              "weather." if intent["target_kind"] == "weather_host_settings" else "")
                    expected_receipts.update(prefix + field for field in intent["fields"])
                before_values = {(row["target_key"], row["field_id"]): row["value_json"]
                    for row in controller.runtime.read_all(
                        "SELECT target_key, field_id, value_json FROM configuration_values", ())}
                with patch.object(configuration, "patch", side_effect=record_patch):
                    result = _require(await api._apply(
                        migration, v1_root, session, preview["plan_token"]), "apply")
            if result["errors"]:
                raise RuntimeError("configuration_apply_errors:" + ",".join(
                    sorted({str(item.get("scope", "unknown")) + ":"
                            + str(item.get("code", "unknown")) for item in result["errors"]})))
            persisted = json.loads(saved_config_path.read_text(encoding="utf-8"))
            if persisted != config:
                raise RuntimeError("plugin_configuration_save_mismatch")

            expected_fields = sum(len(intent["fields"]) for intent in intents)
            if preview["change_count"] != expected_fields or result["change_count"] != expected_fields:
                raise RuntimeError("configuration_plan_count_mismatch")
            actual_receipts = Counter(result["written"])
            if expected_receipts - actual_receipts:
                raise RuntimeError("configuration_planned_receipt_missing")
            supplementary = actual_receipts - expected_receipts
            from companion_v2.role_work.life.configuration import SLEEP_FIELDS
            allowed_supplementary = {"role.life." + field for field in SLEEP_FIELDS}
            if set(supplementary) - allowed_supplementary:
                raise RuntimeError("configuration_unexpected_supplementary_write")
            persisted_values = {(row["target_key"], row["field_id"]): row["value_json"]
                for row in controller.runtime.read_all(
                    "SELECT target_key, field_id, value_json FROM configuration_values", ())
                if before_values.get((row["target_key"], row["field_id"])) != row["value_json"]}
            if Counter(field for _, field in persisted_values) != Counter(configuration_receipts):
                raise RuntimeError("configuration_receipt_storage_mismatch")
            for (_, field), value in persisted_values.items():
                if field in supplementary and json.loads(value) != configuration.registry.fields[field].default:
                    raise RuntimeError("configuration_supplementary_default_mismatch")
            target_kinds = {}
            for intent in intents:
                target_kinds[intent["target_kind"]] = target_kinds.get(intent["target_kind"], 0) + len(intent["fields"])
            await controller.terminate()

            reloaded = AstrBotMultiController(native, persisted, data_root,
                native_types=types, now=lambda: NOW)
            controllers.append(reloaded)
            loaded = _require(await reloaded.load_existing(), "reload")
            if not loaded.get("loaded"):
                raise RuntimeError("reload_not_loaded")
            _require(await reloaded.start(), "restart")
            api.controller = reloaded
            reloaded_context = reloaded.session.authority.context("first", "role-a")
            reloaded_session = SimpleNamespace(
                profile=SimpleNamespace(target=reloaded_context),
                application=reloaded.session.application,
            )
            mismatched_fields, verified_fields = [], 0
            with bind_request_context(request):
                for intent in intents:
                    if intent["target_kind"] == "configuration_registry":
                        target = api._scope_target(reloaded_session, SimpleNamespace(
                            scope=intent["scope"], group_id=intent["group_id"],
                            target_kind=intent["target_kind"], changes=intent["values"]))
                        if target is None:
                            mismatched_fields.extend(intent["fields"])
                            continue
                        snapshot = reloaded_session.application.configuration._snapshot(
                            api._operator(), target, intent["group_id"], NOW, "configuration.read")
                        mismatched_fields.extend(f"{intent['group_id']}.{field}"
                            for field, value in intent["values"].items()
                            if snapshot.fields[f"{intent['group_id']}.{field}"].value != value)
                    elif intent["target_kind"] == "semantic_config":
                        values = reloaded_session.application.semantics.store.configuration_snapshot()["values"]
                        mismatched_fields.extend(field for field, value in intent["values"].items()
                                                 if values[field] != value)
                    elif intent["target_kind"] == "plugin_config":
                        mismatched_fields.extend(field for field, value in intent["values"].items()
                                                 if _plugin_value(reloaded.config, field) != value)
                    elif intent["target_kind"] == "weather_host_settings":
                        settings = weather_settings(reloaded.config)
                        mismatched_fields.extend("weather." + field for field, value in intent["values"].items()
                                                 if settings[field] != value)
                        if WeatherHostSettings(reloaded).view()["source_state"] != "configured":
                            raise RuntimeError("weather_consumer_configuration_invalid")
                    else:
                        raise RuntimeError("configuration_verifier_missing:" + intent["target_kind"])
                    verified_fields += len(intent["fields"])
                consumers = _consumer_report(reloaded, reloaded_session, api)
                from companion_v2.legacy.configuration_migration import convert_configuration
                expected_reply = convert_configuration(v1_config,
                    registry=reloaded_session.application.configuration.registry, window_kind="private")
                debounce_key = REPLY_GROUP + ".private_debounce_enabled"
                if (debounce_key in expected_reply.changes and consumers["private_debounce_enabled"]
                        != expected_reply.changes[debounce_key]):
                    raise RuntimeError("reply_consumer_debounce_mismatch")
                provider_intents = [intent["values"]["model.provider_id"] for intent in intents
                    if intent["target_kind"] == "plugin_config" and "model.provider_id" in intent["values"]]
                consumers["model_route_matches_plan"] = (not provider_intents or
                    reloaded.settings.common.provider_id == provider_intents[-1])
                if not consumers["model_route_matches_plan"]:
                    raise RuntimeError("reply_consumer_model_route_mismatch")
            mismatches = len(mismatched_fields)
            restarted_values = {(row["target_key"], row["field_id"]): row["value_json"]
                for row in reloaded.runtime.read_all(
                    "SELECT target_key, field_id, value_json FROM configuration_values", ())}
            if any(restarted_values.get(key) != value for key, value in persisted_values.items()):
                raise RuntimeError("configuration_written_storage_restart_mismatch")
            if mismatches:
                raise RuntimeError("configuration_reload_mismatch:" + ",".join(mismatched_fields))
            if verified_fields != expected_fields:
                raise RuntimeError("configuration_verification_incomplete")
            if source_hash != _hash(v1_config_path):
                raise RuntimeError("configuration_source_changed")

            platform_sends = sum(
                1 for platform in native.platforms.values()
                for action, _ in platform.client._api._wsr_api.calls
                if action in {"send_private_msg", "send_group_msg", "send_msg"})
            model_calls = len(native.provider.client.state.calls)
            if platform_sends or model_calls:
                raise RuntimeError("unexpected_external_call")
            await reloaded.terminate()
            return {
                "configuration": {
                    "source_change_count": preview["source_change_count"],
                    "planned_fields": expected_fields,
                    "written_fields": result["written_count"],
                    "supplementary_written_fields": dict(supplementary),
                    "verified_written_fields": len(result["written"]),
                    "registry_writes_verified_after_restart": len(persisted_values),
                    "preserved_fields": preview["preserved_count"],
                    "target_kinds": target_kinds,
                    "target_layers": target_layers,
                    "verified_fields": verified_fields,
                    "persisted_after_restart": expected_fields - mismatches,
                    "mismatches": mismatches,
                    "restart_required": result["restart_required"],
                    "source_unchanged": source_hash == _hash(v1_config_path),
                    "model_calls": model_calls,
                    "platform_sends": platform_sends,
                    "consumers": consumers,
                    "difference_counts": dict(Counter(item.get("kind", "unknown")
                                                       for item in preview["differences"])),
                    "differences": _difference_report(preview["differences"]),
                }
            }
        finally:
            for instance in reversed(controllers):
                await instance.terminate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", type=Path, required=True)
    parser.add_argument("--v1-config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.v1_root, args.v1_config)),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
