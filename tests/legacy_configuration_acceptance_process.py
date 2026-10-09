"""Apply a real V1 configuration to an isolated AstrBot V2 profile and reload it."""

from __future__ import annotations

import argparse
import asyncio
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
from astrbot_host.identity_derivation import derive_role_id
from astrbot_host.persona_catalog import available_personas
from companion_v2.configuration.models import ConfigLayer
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind
from companion_v2.legacy.migration import LegacyMigration
from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes


def _require(outcome: Outcome, label: str):
    if not outcome.is_success:
        failure = outcome.failure
        raise RuntimeError(f"{label}:{getattr(failure, 'code', 'failed')}")
    return outcome.unwrap()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plugin_value(config, field_id):
    present, value = LegacyMigrationWebAPI._plugin_config_value(config, field_id)
    if not present:
        raise RuntimeError("plugin_config_value_missing")
    return value


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
            request = PluginRequest(Request({"type": "http", "method": "POST", "path": "/",
                "headers": [], "query_string": b""}), username="acceptance-admin")
            with bind_request_context(request):
                preview = _require(api._plan(migration, v1_root, session), "plan")
                if not preview["intents"]:
                    raise RuntimeError("configuration_plan_empty")
                target_layers = {}
                for intent in preview["intents"]:
                    if intent["target_kind"] != "configuration_registry":
                        continue
                    target = api._scope_target(session, SimpleNamespace(
                        scope=intent["scope"], group_id=intent["group_id"],
                        target_kind=intent["target_kind"]))
                    if target is None:
                        raise RuntimeError("configuration_target_missing:" + intent["group_id"])
                    target_layers[intent["group_id"]] = target.layer.value
                for group_id in ("role.life", "role.growth.skills"):
                    if group_id in target_layers and target_layers[group_id] != ConfigLayer.WINDOW.value:
                        raise RuntimeError("role_shared_target_not_window:" + group_id)
                result = _require(await api._apply(
                    migration, v1_root, session, preview["plan_token"]), "apply")
            if result["errors"]:
                raise RuntimeError("configuration_apply_errors:" + ",".join(
                    sorted({str(item.get("scope", "unknown")) + ":"
                            + str(item.get("code", "unknown")) for item in result["errors"]})))
            persisted = json.loads(saved_config_path.read_text(encoding="utf-8"))
            if persisted != config:
                raise RuntimeError("plugin_configuration_save_mismatch")

            intents = preview["intents"]
            expected_fields = sum(len(intent["fields"]) for intent in intents)
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
            mismatches = 0
            with bind_request_context(request):
                for intent in intents:
                    if intent["target_kind"] == "configuration_registry":
                        target = api._scope_target(reloaded_session, SimpleNamespace(
                            scope=intent["scope"], group_id=intent["group_id"],
                            target_kind=intent["target_kind"]))
                        if target is None:
                            mismatches += len(intent["fields"])
                            continue
                        snapshot = reloaded_session.application.configuration._snapshot(
                            api._operator(), target, intent["group_id"], NOW, "configuration.read")
                        mismatches += sum(
                            snapshot.fields[f"{intent['group_id']}.{field}"].value != value
                            for field, value in intent["values"].items())
                    elif intent["target_kind"] == "semantic_config":
                        values = reloaded_session.application.semantics.store.configuration_snapshot()["values"]
                        mismatches += sum(values[field] != value
                            for field, value in intent["values"].items())
                    elif intent["target_kind"] == "plugin_config":
                        mismatches += sum(_plugin_value(reloaded.config, field) != value
                            for field, value in intent["values"].items())
            if mismatches:
                raise RuntimeError(f"configuration_reload_mismatch:{mismatches}")

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
                    "preserved_fields": preview["preserved_count"],
                    "target_kinds": target_kinds,
                    "target_layers": target_layers,
                    "persisted_after_restart": expected_fields - mismatches,
                    "mismatches": mismatches,
                    "restart_required": result["restart_required"],
                    "source_unchanged": source_hash == _hash(v1_config_path),
                    "model_calls": model_calls,
                    "platform_sends": platform_sends,
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
