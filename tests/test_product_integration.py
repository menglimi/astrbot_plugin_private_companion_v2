"""Integration metadata and scoped workspaces; never touches live plugin stores."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from tests import test_astrbot_staging_host as support
from tests.multi_host_support import MultiFixture
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from astrbot_host.integration_registry import IntegrationRegistry, STATUS_SCHEMA
from astrbot_host.integration_catalog import OPTIONAL_PROVIDERS
from astrbot_host.management_identity import dashboard_operator
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.product import PRODUCT_VERSION

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/astrbot_plugin_private_companion_v2"


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.spec = OPTIONAL_PROVIDERS[1]
        self.provider = Mock(return_value={"schema": STATUS_SCHEMA, "plugin_id": self.spec["plugin_id"],
            "enabled": True, "runtime_ready": None, "private_record": "must-not-escape", "token": "secret"})
        self.api = NS(companion_v2_status=self.provider, status=Mock(side_effect=AssertionError("private API")))
        self.star = NS(root_dir_name=self.spec["plugin_id"], version="1.0", activated=True,
                       star_cls=NS(extension_api=self.api), pages=[])
        self.native = NS(get_all_stars=lambda: [self.star])
        self.registry = IntegrationRegistry(self.native)

    def item(self):
        return next(item for item in self.registry.snapshot()["providers"] if item["plugin_id"] == self.spec["plugin_id"])

    def test_native_catalog_conflict_is_visible_without_claiming_execution_or_losing_status(self):
        snapshot = self.registry.snapshot(native_issues=((self.spec["plugin_id"], "capability_descriptor_conflict"),))
        item = next(p for p in snapshot["providers"] if p["plugin_id"] == self.spec["plugin_id"])
        self.assertTrue(item["status_connected"])
        self.assertEqual(item["integration_state"], "degraded")
        self.assertEqual(item["execution_issue"], "capability_descriptor_conflict")
        self.assertFalse(item["execution_integrated"])
        self.assertIn("当前不能在对话中调用", item["reason"])

    def test_only_metadata_contract_is_invoked_and_private_fields_are_dropped(self):
        value = self.item()
        self.assertTrue(value["status_connected"])
        self.assertIsNone(value["runtime_ready"])
        self.assertFalse(value["execution_integrated"])
        self.assertNotIn("secret", json.dumps(value))
        self.assertNotIn("must-not-escape", json.dumps(value))
        self.api.status.assert_not_called()

    def test_disabled_stale_instance_and_duplicate_identity_never_invoked(self):
        self.star.activated = False
        self.assertEqual(self.item()["integration_state"], "disabled")
        self.provider.assert_not_called()
        self.star.activated = True
        self.native.get_all_stars = lambda: [self.star, self.star]
        self.assertEqual(self.item()["integration_state"], "conflict")
        self.provider.assert_not_called()

    def test_hot_replacement_missing_invalid_and_async_status(self):
        self.star.star_cls = NS(extension_api=NS())
        self.assertEqual(self.item()["integration_state"], "installed")
        self.star.star_cls.extension_api = NS(companion_v2_status=lambda: {"schema":STATUS_SCHEMA,"enabled":"true"})
        self.assertEqual(self.item()["integration_state"], "degraded")
        self.star.star_cls.extension_api = self.api
        self.provider.return_value["runtime_ready"] = False
        self.assertEqual(self.item()["integration_state"], "waiting")
        async def async_status():
            raise AssertionError("async discovery must not run")
        self.star.star_cls.extension_api = NS(companion_v2_status=async_status)
        self.assertEqual(self.item()["integration_state"], "installed")
        self.native.get_all_stars = lambda: []
        self.assertEqual(self.item()["integration_state"], "missing")

    def test_discovery_error_does_not_claim_plugins_are_missing(self):
        self.native.get_all_stars = Mock(side_effect=RuntimeError("private path"))
        value = self.registry.snapshot()
        self.assertTrue(all(item["integration_state"] == "unknown" for item in value["providers"]))
        self.assertNotIn("private path", json.dumps(value))

    def test_unreadable_optional_page_directory_keeps_status_available(self):
        with patch.object(Path, "is_dir", return_value=True), patch.object(
            Path, "iterdir", side_effect=PermissionError("unreadable source page directory")
        ):
            value = self.item()
        self.assertTrue(value["status_connected"])
        self.assertEqual(value["pages"], [])

    def test_distributed_provider_wrappers_are_metadata_only(self):
        checked = 0
        for spec in OPTIONAL_PROVIDERS:
            path = ROOT.parent / spec["plugin_id"] / "main.py"
            if not path.is_file():
                continue  # A core-only install does not ship optional providers or V1.
            checked += 1
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "companion_v2_status"]
            self.assertEqual(len(methods), 1, spec["plugin_id"])
            # Keep the real metadata helper bound to the real status method;
            # extracting status alone broke when providers added native readiness.
            helpers = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                       and node.name == "companion_v2_native"]
            probe_class = ast.ClassDef(name="StatusProbe", bases=[], keywords=[],
                                       body=[methods[0], *helpers], decorator_list=[])
            module = ast.Module(body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),
                                      probe_class], type_ignores=[])
            namespace = {"PLUGIN_NAME":spec["plugin_id"]}
            exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
            probe = namespace["StatusProbe"]()
            port = NS(_closed=False)
            probe._plugin = NS(enabled=True, server_enabled=True, _cfg_bool=lambda key,default:True,
                               room_server=NS(running=True), _native_provider=port,
                               _native_v2_provider=port, _native_v2_mode=True, native_v2_enabled=True,
                               native_v2_tictactoe_enabled=True, native_v2_gomoku_enabled=False,
                               native_v2_pig_dice_enabled=False, native_v2_blackjack_enabled=False,
                               native_v2_xiangqi_enabled=False)
            probe._management_preparation_closed = False
            probe.bridge_lifecycle_status = lambda:{"active":True}
            status = probe.companion_v2_status()
            self.assertEqual(set(status), {"schema", "plugin_id", "enabled", "runtime_ready"})
            self.assertEqual(status["plugin_id"], spec["plugin_id"])
            self.assertEqual(status["schema"], STATUS_SCHEMA)
            self.assertIs(status["enabled"], True, spec["plugin_id"])
            self.assertIn(status["runtime_ready"], (None, True), spec["plugin_id"])
            # No port means no execution readiness, including after reloading;
            # Together and Reality retain their separately reported readiness.
            probe._plugin._native_provider = None
            probe._plugin._native_v2_provider = None
            waiting = probe.companion_v2_status()
            if spec["capability_id"] in {"content", "image", "screen", "game", "live"}:
                self.assertIs(waiting["runtime_ready"], False, spec["plugin_id"])
        if not checked:
            self.skipTest("optional provider sources are not installed")


class MultiIntegrationTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller.register_routes()
        self.routes = {path: handler for path, handler, *_ in self.native.registered_web_apis}

    async def request(self, path, *, username="admin", query=""):
        req = Request({"type":"http", "method":"GET", "path":path,"headers":[],"query_string":query.encode()})
        with bind_request_context(PluginRequest(req, username=username)):
            return await self.routes[path]()

    async def test_manifest_readable_before_initialization_and_cleanup_is_owned(self):
        path = PREFIX + "/integration/manifest"
        for name in (None,"","api_key:synthetic"):
            self.assertEqual((await self.request(path,username=name))["data"]["code"], "dashboard_identity_required")
        result = await self.request(path)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["product"]["version"], PRODUCT_VERSION)
        self.assertIsNone(self.controller.runtime)
        self.assertEqual((await self.request(path,query="target_id=other"))["data"]["code"], "integration_request_invalid")
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.request(path))["data"]["code"], "staging_host_terminated")

    async def test_scoped_relationship_growth_and_life_read_current_target_and_role(self):
        (await self.controller.initialize_profile()).unwrap()
        inventory = (await self.request(PREFIX + "/page/targets"))["data"]["targets"]
        contexts = set()
        for target in inventory:
            for role in target["roles"]:
                for name in ("growth", "relationships", "life"):
                    response = await self.request(role[name + "_api"])
                    self.assertEqual(response["status"], "ok", (name, target["target_id"], role["role_id"], response))
                    if name in ("growth", "relationships"):
                        self.assertEqual(response["data"]["profile_id"], target["target_id"])
                    if name == "growth":
                        contexts.add(response["data"]["context_key"])
        self.assertEqual(len(contexts),4)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        operator = dashboard_operator(self.controller.runtime, "admin", at=support.NOW)
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,expected_revision=policy.revision,observed_at=support.NOW)
        self.assertEqual((await self.request(PREFIX + "/integration/manifest"))["data"]["code"], "core_access_required")
