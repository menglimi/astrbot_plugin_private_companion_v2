"""Check real SDK config reloads and automatic role startup on isolated V2 data."""

import asyncio
from functools import partial
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import sys
from unittest.mock import patch

from tests.multi_host_support import MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.test_management_access import NOW
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.execution.models import digest
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core import db_helper
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request


async def run():
    # The real host initializes its preferences DB before loading plugins. Do
    # the same before the fixture performs concurrent native session reads.
    await db_helper.initialize()
    db_helper.inited = True
    source = Path(__file__).resolve().parents[1]
    package = ModuleType("companion_role_restart_fixture")
    package.__path__ = [str(source)]
    sys.modules[package.__name__] = package
    entry = importlib.import_module(package.__name__ + ".main")
    schema = json.loads((source / "_conf_schema.json").read_text(encoding="utf-8"))
    native = MultiNativeContext()
    native.conversation_manager.session_conversations = {
        "qq-main:FriendMessage:200": "conversation-a", "qq-second:FriendMessage:200": "conversation-b"}
    types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, SimpleNamespace, SimpleNamespace, FakeReverseApi)
    factory = partial(entry.AstrBotMultiController, native_types=types, now=lambda: NOW)
    with TemporaryDirectory(prefix="companion-role-restart-") as temporary:
        root = Path(temporary)
        config_file = root / "plugin-config.json"
        initial = multi_config()
        initial["multi_host"]["targets"][0]["participant_id"] = "*"
        config_file.write_text(json.dumps(initial, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        expected_binding = None
        expected_context = None
        for cycle in range(3):
            if cycle == 1:
                # Reproduce the row inserted by older V2 startup migration after
                # the operator had already saved the wildcard role mapping.
                damaged = json.loads(config_file.read_text(encoding="utf-8-sig"))
                damaged["multi_host"]["targets"].append({
                    "target_id": "legacy-" + digest(["qq-main", "100", "200"])[:20],
                    "platform_id": "qq-main", "account_id": "100", "bot_id": "bot-a", "participant_id": "200"})
                config_file.write_text(json.dumps(damaged, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            config = AstrBotConfig(config_path=str(config_file), schema=schema)
            with patch.object(entry.StarTools, "get_data_dir", return_value=root / "v2"), \
                    patch.object(entry, "AstrBotMultiController", factory):
                plugin = entry.PrivateCompanionV2StagingPlugin(native, config)
            controller = plugin.staging
            try:
                def unexpected_failure(error, **_):
                    raise error

                with patch.object(controller, "_failure", side_effect=unexpected_failure):
                    await plugin.initialize()
                assert controller._accepting, controller.last_failure
                assert controller.session.application.state == "running"
                if expected_binding is None:
                    expected_binding = controller.settings.binding_contract
                assert controller.settings.binding_contract == expected_binding
                assert not any(row["target_id"].startswith("legacy-") for row in config["multi_host"]["targets"])
                persisted = json.loads(config_file.read_text(encoding="utf-8-sig"))
                assert not any(row["target_id"].startswith("legacy-") for row in persisted["multi_host"]["targets"])
                context = controller.authority.context("first", "role-a")
                identity = (context.actor.subject, context.scope, context.role_binding.role)
                if expected_context is None:
                    expected_context = identity
                assert identity == expected_context
                routes = {route: handler for route, handler, _, _ in native.registered_web_apis}

                async def read(path):
                    request = Request({"type": "http", "method": "GET", "path": path,
                                       "headers": [], "query_string": b""})
                    with bind_request_context(PluginRequest(request, username="admin")):
                        response = await routes[path]()
                    assert response["status"] == "ok", response
                    return response["data"]

                directory = await read("/astrbot_plugin_private_companion/page/targets")
                assert directory["targets"]
                role = next(role for role in directory["targets"][0]["roles"] if role["role_id"] == "role-a")
                await read(role["state_api"])
                assert native.provider.client.state.calls == []
                assert all(action in {"get_login_info", "get_friend_list", "get_stranger_info"}
                           for platform in native.platforms.values() for action, _ in platform.client._api._wsr_api.calls)
            finally:
                await controller.terminate()
            assert controller.runtime is None and not native.registered_web_apis
        await plugin.terminate()
    print(json.dumps({"startup_cycles": 3, "saved_config_recovery": True, "role_state_readable": True,
                      "same_role_owner": True, "route_cleanup": True, "manual_mapping_saves": 0,
                      "model_calls": 0, "platform_sends": 0}))


if __name__ == "__main__":
    asyncio.run(run())
