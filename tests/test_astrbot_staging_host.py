from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

# AstrBot resolves its data directory during import.  Redirect that import-time
# state before loading the real SDK so this contract test cannot create a data/
# tree in the repository.
_previous_astrbot_root = os.environ.get("ASTRBOT_ROOT")
_astrbot_import_root = None
if _previous_astrbot_root is None:
    _astrbot_import_root = TemporaryDirectory(prefix="companion-v2-host-import-")
    os.environ["ASTRBOT_ROOT"] = _astrbot_import_root.name

from astrbot_host.controller import AstrBotStagingController
from astrbot_host.web_api import API_PREFIX
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.capabilities import CapabilityAuthorizationState, CapabilityRepository
from companion_v2.execution.models import TaskError
from companion_v2.screen import SCREEN_EXTENSION, SCREEN_PROCESS, SCREEN_READ
from tests.native_adapter_support import completion, FakeEvent, FakeHostContext, FakeProvider, FakeReverseApi
from tests.staging_bootstrap_support import database_contents, wait_for_batch
from tests.test_management_access import NOW
from tests.test_native_screen_flow import provider_module


def tearDownModule():
    if _astrbot_import_root is not None:
        os.environ.pop("ASTRBOT_ROOT", None)
        _astrbot_import_root.cleanup()


def host_config(**changes):
    config = {
        "staging": {"enabled": True, "profile_id": "preview-1", "delivery_mode": "preview"},
        "target": {
            "platform_id": "qq-main",
            "account_id": "100",
            "participant_id": "200",
            "bot_id": "bot-a",
            "role_id": "persona-a",
            "persona_id": "original",
        },
        "model": {
            "provider_id": "native-model",
            "task_prompt": "保持原角色，只根据当前输入回复。",
            "max_output_tokens": 100,
            "maximum_input_estimate": 131072,
            "output_parameter": "max_tokens",
            "input_microusd_per_million": 2_000_000,
            "cached_input_microusd_per_million": 1_000_000,
            "output_microusd_per_million": 4_000_000,
        },
        "runtime": {
            "budget_tokens": 100_000_000,
            "budget_cost_microusd": 1_000_000_000,
            "quiet_seconds": 0,
            "maximum_wait_seconds": 0,
            "turn_timeout_seconds": 180,
            "part_gap_seconds": 0,
            "foreground_slots": 2,
            "background_slots": 1,
            "queued_per_lane": 64,
            "retained_tasks": 2048,
        },
    }
    for section, values in changes.items():
        config[section].update(values)
    return config


class WebContext(FakeHostContext):
    def __init__(self):
        super().__init__()
        self.registered_web_apis = []

    def register_web_api(self, route, handler, methods, description):
        for index, item in enumerate(self.registered_web_apis):
            if item[0] == route and item[2] == methods:
                self.registered_web_apis[index] = (route, handler, methods, description)
                return
        self.registered_web_apis.append((route, handler, methods, description))

    def get_using_provider(self):
        return self.provider


class AstrBotStagingHostTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-host-")
        self.root = Path(self.temporary.name)
        self.native = WebContext()
        self.types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        self.controller = self.make_controller()

    def make_controller(self, *, config=None, root=None):
        return AstrBotStagingController(
            self.native,
            config or host_config(),
            root or self.root,
            native_types=self.types,
            now=lambda: NOW,
        )

    async def asyncTearDown(self):
        await self.controller.terminate()
        self.temporary.cleanup()

    async def initialize_and_start(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        started = await self.controller.start()
        self.assertTrue(started.is_success, started.failure)
        return initialized.unwrap(), started.unwrap()

    def load_screen_provider(self, *, version="3.3.0"):
        provider = provider_module().NativeScreenProvider(self.root / "screen-native", version=version,
            device_id="synthetic-desktop", platform_id="qq-main", account_id="100", bot_id="bot-a",
            capture=lambda: b"unused", now=lambda: NOW)
        self.addAsyncCleanup(provider.close)
        star = NS(root_dir_name="astrbot_plugin_screen_companion", version=version, activated=True,
            star_cls=NS(extension_api=NS(companion_v2_native=lambda: provider)))
        self.native.get_all_stars = lambda: (star,)
        return star

    async def test_prepare_screen_route_is_exact_idempotent_and_does_not_start_intake(self):
        star = self.load_screen_provider()
        self.controller.register_routes()
        handler = next(handler for route, handler, _, _ in self.native.registered_web_apis
                       if route == API_PREFIX + "/prepare-screen")
        self.assertEqual((await handler())["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        first = await handler()
        self.assertEqual(first["status"], "ok", first)
        self.assertFalse(first["data"]["replayed"])
        self.assertFalse(first["data"]["started"])
        self.assertEqual(self.controller.session.application.state, "new")
        self.assertFalse(self.controller.status()["accepting"])
        repository = CapabilityRepository(self.controller.runtime)
        config = self.controller.configuration
        self.assertEqual(repository.installation(extension_id=SCREEN_EXTENSION).unwrap().package_version, "3.3.0")
        self.assertTrue(repository.require_role_enabled(extension_id=SCREEN_EXTENSION,
            role=config.persona.role, bot_id=config.scope.bot_id).is_success)
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.assertTrue(repository.authorize(extension_id=SCREEN_EXTENSION,
                capability_id=capability, subject=config.subject, scope=config.scope).is_success)
        grants = self.controller.bootstrap.identity.snapshot().grants
        self.assertEqual({grant.capability for grant in grants} - set(config.capabilities),
                         {SCREEN_READ, SCREEN_PROCESS, "extension.tool.invoke"})
        before = database_contents(self.controller.runtime)
        self.assertTrue((await handler())["data"]["replayed"])
        self.assertEqual(database_contents(self.controller.runtime), before)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

        repository.set_authorization(extension_id=SCREEN_EXTENSION, capability_id=SCREEN_PROCESS,
            subject=config.subject, scope=config.scope, state=CapabilityAuthorizationState.REVOKED,
            expected_revision=1, observed_at=NOW).unwrap()
        before = database_contents(self.controller.runtime)
        self.assertEqual((await handler())["data"]["code"], "capability_consent_revoked")
        self.assertEqual(database_contents(self.controller.runtime), before)
        star.version = "3.3.1"
        self.assertEqual((await handler())["data"]["code"], "staging_screen_provider_changed")

    async def test_prepare_screen_rolls_back_partial_authority(self):
        self.load_screen_provider()
        (await self.controller.initialize_profile()).unwrap()
        before = database_contents(self.controller.runtime)
        identity = self.controller.bootstrap.identity
        original = identity.issue_grant
        count = 0

        def fail_second_grant(**kwargs):
            nonlocal count
            count += 1
            result = original(**kwargs)
            if count == 2:
                raise RuntimeError("synthetic sensitive failure")
            return result

        with patch.object(identity, "issue_grant", side_effect=fail_second_grant):
            result = await self.controller.prepare_screen()
        self.assertEqual(result.failure.code, "staging_screen_preparation_failed")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_upgrade_screen_requires_reviewed_revision_and_preserves_authority(self):
        self.load_screen_provider()
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.prepare_screen()).unwrap()
        previous = CapabilityRepository(self.controller.runtime).installation(extension_id=SCREEN_EXTENSION).unwrap()
        before = database_contents(self.controller.runtime)
        same_version = await self.controller.upgrade_screen(username="admin",
            previous_version=previous.package_version, previous_hash=previous.artifact_hash,
            expected_revision=previous.revision)
        self.assertEqual(same_version.failure.code, "staging_screen_upgrade_invalid")
        self.assertEqual(database_contents(self.controller.runtime), before)
        await self.controller.terminate()

        self.load_screen_provider(version="3.3.1")
        self.controller = self.make_controller()
        (await self.controller.load_existing()).unwrap()
        before = database_contents(self.controller.runtime)
        rejected = await self.controller.upgrade_screen(username="admin", previous_version=previous.package_version,
            previous_hash="incorrect-hash", expected_revision=previous.revision)
        self.assertEqual(rejected.failure.code, "staging_screen_upgrade_conflict")
        self.assertEqual(database_contents(self.controller.runtime), before)

        self.controller.register_routes()
        handler = next(handler for route, handler, _, _ in self.native.registered_web_apis
                       if route == API_PREFIX + "/upgrade-screen")

        async def body():
            return json.dumps({"previous_version": previous.package_version,
                "previous_hash": previous.artifact_hash,
                "expected_revision": previous.revision}).encode("utf-8")

        with patch("astrbot_host.web_api.request", NS(username="admin", query={}, body=body)):
            response = await handler()
        self.assertEqual(response["status"], "ok", response)
        upgraded = response["data"]
        self.assertEqual((upgraded["previous_version"], upgraded["package_version"], upgraded["revision"]),
                         ("3.3.0", "3.3.1", previous.revision + 1))
        self.assertFalse(upgraded["started"])
        self.assertEqual(self.controller.session.application.state, "new")
        self.assertFalse(self.controller.status()["accepting"])
        repository = CapabilityRepository(self.controller.runtime)
        self.assertEqual(repository.installation(extension_id=SCREEN_EXTENSION).unwrap().artifact_hash,
                         upgraded["artifact_hash"])
        config = self.controller.configuration
        for capability in (SCREEN_READ, SCREEN_PROCESS):
            self.assertTrue(repository.authorize(extension_id=SCREEN_EXTENSION, capability_id=capability,
                subject=config.subject, scope=config.scope).is_success)
        self.assertTrue((await self.controller.prepare_screen()).unwrap()["replayed"])
        self.assertEqual((await self.controller.upgrade_screen(username="admin",
            previous_version=previous.package_version, previous_hash=previous.artifact_hash,
            expected_revision=previous.revision)).failure.code, "staging_screen_upgrade_conflict")

    async def test_upgrade_screen_rolls_back_when_screen_consent_was_revoked(self):
        self.load_screen_provider()
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.prepare_screen()).unwrap()
        repository = CapabilityRepository(self.controller.runtime)
        previous = repository.installation(extension_id=SCREEN_EXTENSION).unwrap()
        config = self.controller.configuration
        repository.set_authorization(extension_id=SCREEN_EXTENSION, capability_id=SCREEN_PROCESS,
            subject=config.subject, scope=config.scope, state=CapabilityAuthorizationState.REVOKED,
            expected_revision=1, observed_at=NOW).unwrap()
        await self.controller.terminate()

        self.load_screen_provider(version="3.3.1")
        self.controller = self.make_controller()
        (await self.controller.load_existing()).unwrap()
        before = database_contents(self.controller.runtime)
        rejected = await self.controller.upgrade_screen(username="admin",
            previous_version=previous.package_version, previous_hash=previous.artifact_hash,
            expected_revision=previous.revision)
        self.assertEqual(rejected.failure.code, "capability_consent_revoked")
        self.assertEqual(database_contents(self.controller.runtime), before)

    async def test_probe_initialize_start_and_official_sender_records_real_delivery(self):
        probe = await self.controller.probe()
        self.assertTrue(probe.is_success, probe.failure)
        self.assertFalse(probe.unwrap()["pinned"])
        self.assertFalse(probe.unwrap()["model_request_sent"])
        self.assertFalse(probe.unwrap()["platform_message_sent"])
        self.assertEqual(self.native.provider.client.state.calls, [])

        initialized, started = await self.initialize_and_start()
        self.assertFalse(initialized["replayed"])
        self.assertEqual(started["state"], "running")
        event = FakeEvent(self.native)
        self.assertTrue(self.controller.claims(event))
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)

        preview = await self.controller.preview(batch)
        report = (await self.controller.inspect(batch)).unwrap()
        self.assertEqual(preview.failure.code, "staging_preview_disabled")
        self.assertEqual(report["conversation"]["receipt_basis"], "onebot_reverse_websocket")
        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["delivery_receipts"][0]["state"], "delivered")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_start_failure_keeps_intake_closed_and_can_be_retried(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        connected = self.native.platform.client._wsr_api_clients.pop("100")
        failed = await self.controller.start()
        self.assertEqual(failed.failure.code, "staging_account_unavailable")
        self.assertFalse(self.controller.status()["accepting"])
        self.assertFalse(self.controller.claims(FakeEvent(self.native)))

        self.native.platform.client._wsr_api_clients["100"] = connected
        started = await self.controller.start()
        self.assertTrue(started.is_success, started.failure)
        self.assertTrue(self.controller.claims(FakeEvent(self.native)))

    async def test_registered_routes_drive_one_official_profile_and_serialize_receipts(self):
        self.controller.register_routes()
        routes = {route.removeprefix(API_PREFIX): handler
                  for route, handler, _, _ in self.native.registered_web_apis}
        self.assertFalse((await routes["/status"]())["data"]["accepting"])
        self.assertEqual((await routes["/probe"]())["status"], "ok")
        self.assertEqual((await routes["/initialize"]())["status"], "ok")
        for route in ("/authorize-delivery", "/revoke-delivery"):
            response = await routes[route]()
            self.assertEqual(response["status"], "ok")
            self.assertFalse(response["data"]["required"])
        self.assertEqual((await routes["/start"]())["status"], "ok")
        batch = (await self.controller.receive_claimed(FakeEvent(self.native))).unwrap()
        await wait_for_batch(self.controller.session, batch)
        with patch("astrbot_host.web_api.request", NS(query={"batch_id": batch})):
            preview = await routes["/preview"]()
            report = await routes["/inspect"]()
        self.assertEqual(preview["status"], "error")
        self.assertEqual(preview["data"]["code"], "staging_preview_disabled")
        self.assertTrue(report["data"]["confirmed_delivery"])
        self.assertEqual(report["data"]["delivery_receipts"][0]["state"], "delivered")
        stopped = await routes["/stop"]()
        self.assertEqual(stopped["data"]["state"], "stopped")
        self.assertEqual(stopped["data"]["pending_handles"], [])
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_pinned_profile_rejects_persona_change_without_model_or_platform_io(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        await self.controller.terminate()
        before_model = list(self.native.provider.client.state.calls)
        before_send = list(self.native.platform.client._api._wsr_api.calls)
        # A different persona is a rebinding, which is what pinning forbids. The probe
        # refuses an inconsistent persona before the contract comparison runs, so this
        # asserts the loader still refuses; the contract split itself is pinned by
        # tests/test_astrbot_staging_config.py.
        self.native.persona["name"] = "changed-after-pin"

        other = self.make_controller()
        try:
            result = await other.probe()
            self.assertEqual(result.failure.code, "staging_persona_invalid")
            self.assertEqual(self.native.provider.client.state.calls, before_model)
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, before_send)
        finally:
            await other.terminate()

    async def test_a_fresh_profile_reports_where_the_targets_data_lives(self):
        """Pointing profile_id at a new name must say where the old data went.

        A store is per-profile, so a new name opens an empty one and the role reads as if
        it had forgotten everything while the old store sits untouched on disk. Nothing is
        lost and nothing said so, which is the one impression this project must never give.
        """
        config = host_config()
        target = (config["target"]["platform_id"], config["target"]["account_id"],
                  config["target"]["participant_id"])
        in_use = self.root / "profiles" / "in-use"
        (in_use / "runtime").mkdir(parents=True)
        (in_use / "staging-config.json").write_text(json.dumps(
            {"scope": {"platform": target[0], "account_id": target[1], "native_scope_id": target[2]},
             "subject": {"subject_id": target[2]}}), encoding="utf-8")
        store = in_use / "runtime" / "companion-v2.sqlite3"
        connection = sqlite3.connect(store)
        try:
            connection.execute("CREATE TABLE conversation_inputs (batch_id TEXT)")
            connection.execute("INSERT INTO conversation_inputs VALUES ('b1')")
            connection.commit()
        finally:
            connection.close()

        other = self.make_controller(config=host_config(
            staging={"enabled": False, "profile_id": "fresh"}))
        try:
            result = await other.probe()
            self.assertTrue(result.is_success, result.failure)
            self.assertEqual(result.unwrap().get("profile_residency"),
                             {"selected": "fresh", "holders": ["in-use"]})
        finally:
            await other.terminate()

    async def test_inspect_route_exposes_persisted_redacted_model_failure_without_send(self):
        private_response = "private malformed model reply"

        async def malformed(*_):
            return completion(private_response)

        self.native.provider.client.state.behavior = malformed
        self.controller.register_routes()
        await self.initialize_and_start()
        batch = (await self.controller.receive_claimed(FakeEvent(self.native))).unwrap()
        await wait_for_batch(self.controller.session, batch)
        handler = next(handler for route, handler, _, _ in self.native.registered_web_apis
                       if route == API_PREFIX + "/inspect")
        with patch("astrbot_host.web_api.request", NS(query={"batch_id": batch})):
            response = await handler()
        self.assertEqual(response["status"], "ok")
        call = response["data"]["model"]["calls"][0]
        self.assertEqual(call["state"], "unknown")
        self.assertEqual(call["usage_state"], "settled")
        self.assertEqual(call["actual_tokens"], 40)
        self.assertEqual(call["failure"]["phase"], "response_validation")
        self.assertEqual(call["failure"]["code"], "response_contract_rejected")
        self.assertNotIn(private_response, json.dumps(response))
        self.assertEqual(response["data"]["delivery_receipts"], [])
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_reload_only_loads_existing_profile_and_keeps_it_stopped(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        before = database_contents(self.controller.runtime)
        await self.controller.terminate()

        other = self.make_controller()
        try:
            loaded = await other.load_existing()
            self.assertTrue(loaded.is_success, loaded.failure)
            self.assertTrue(loaded.unwrap()["loaded"])
            self.assertEqual(other.session.application.state, "new")
            self.assertFalse(other.status()["accepting"])
            self.assertEqual(database_contents(other.runtime), before)
            self.assertEqual(self.native.provider.client.state.calls, [])
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await other.terminate()

    async def test_model_parameter_drift_does_not_block_fixed_profile_reload(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        await self.controller.terminate()

        config = host_config()
        config["model"]["max_output_tokens"] += 1
        other = self.make_controller(config=config)
        try:
            loaded = await other.load_existing()

            self.assertTrue(loaded.is_success, loaded.failure)
            self.assertTrue(loaded.unwrap()["loaded"])
            self.assertEqual(other.session.application.state, "new")
            self.assertIsNone(other.status()["last_failure"])
            self.assertEqual(self.native.provider.client.state.calls, [])
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await other.terminate()

    async def test_legacy_preview_profile_reloads_and_sends_on_the_same_binding(self):
        initialized = await self.controller.initialize_profile()
        self.assertTrue(initialized.is_success, initialized.failure)
        intent = self.controller.intent_path
        document = json.loads(intent.read_text(encoding="utf-8"))
        document["delivery_mode"] = "preview"
        intent.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
        await self.controller.terminate()

        other = self.make_controller()
        try:
            loaded = await other.load_existing()
            self.assertTrue(loaded.is_success, loaded.failure)
            self.assertTrue(loaded.unwrap()["loaded"])
            self.assertEqual(other.configuration.delivery_mode, "onebot_private")
            self.assertTrue((await other.start()).is_success)
            batch = (await other.receive_claimed(FakeEvent(self.native))).unwrap()
            await wait_for_batch(other.session, batch)
            report = (await other.inspect(batch)).unwrap()
            self.assertTrue(report["confirmed_delivery"])
            self.assertEqual(report["delivery_receipts"][0]["state"], "delivered")
            self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        finally:
            await other.terminate()

    async def test_hot_reload_stops_before_storage_close_and_unregisters_owned_routes(self):
        self.controller.register_routes()
        registered = {route: id(handler) for route, handler, _, _ in self.native.registered_web_apis}
        self.assertIn(API_PREFIX + "/status", registered)
        self.assertEqual(registered, {route: id(handler) for route, handler in self.controller.web_api._registered_routes})
        await self.initialize_and_start()
        await self.controller.terminate()

        self.assertFalse(self.controller.status()["accepting"])
        self.assertTrue(self.controller.status()["terminated"])
        self.assertIsNone(self.controller.runtime)
        self.assertEqual(self.native.registered_web_apis, [])
        late = await self.controller.probe()
        self.assertEqual(late.failure.code, "staging_host_terminated")

    async def test_old_instance_cannot_unregister_replacement_routes(self):
        old = self.controller
        new = self.make_controller(root=self.root / "other")
        old.register_routes()
        old_handlers = {route: id(handler) for route, handler, _, _ in self.native.registered_web_apis}
        new.register_routes()
        new_handlers = {route: id(handler) for route, handler, _, _ in self.native.registered_web_apis}
        self.assertEqual(set(old_handlers), set(new_handlers))
        self.assertTrue(all(old_handlers[route] != new_handlers[route] for route in old_handlers))
        self.assertTrue(all(route.startswith("/astrbot_plugin_private_companion_v2/") for route in new_handlers))

        old.unregister_routes()
        self.assertEqual(
            {route: id(handler) for route, handler, _, _ in self.native.registered_web_apis},
            new_handlers,
        )
        new.unregister_routes()
        self.assertEqual(self.native.registered_web_apis, [])
        await new.terminate()

    async def test_disabled_or_wrong_account_never_claims_private_events(self):
        disabled = self.make_controller(config=host_config(staging={"enabled": False}))
        try:
            result = await disabled.probe()
            self.assertTrue(result.is_success, result.failure)
            self.assertFalse(result.unwrap()["enabled"])
            self.assertEqual(result.unwrap()["connected_account_ids"], ["100", "101"])
            initialize = await disabled.initialize_profile()
            self.assertEqual(initialize.failure.code, "staging_disabled")
            self.assertFalse(disabled.claims(FakeEvent(self.native)))
        finally:
            await disabled.terminate()

        await self.initialize_and_start()
        self.assertFalse(self.controller.claims(FakeEvent(self.native, login="101")))
        self.assertFalse(self.controller.claims(FakeEvent(self.native, sender="201")))

    async def test_sender_records_ack_without_global_delivery_authorization(self):
        sender = self.make_controller(config=host_config(staging={
            "profile_id": "sender-1",
            "delivery_mode": "onebot_private",
        }))
        try:
            initialized = await sender.initialize_profile()
            self.assertTrue(initialized.is_success, initialized.failure)
            started = await sender.start()
            self.assertTrue(started.is_success, started.failure)
            self.assertFalse(sender.status()["delivery_authorization"]["required"])
            batch = (await sender.receive_claimed(FakeEvent(self.native))).unwrap()
            await wait_for_batch(sender.session, batch)
            report = (await sender.inspect(batch)).unwrap()
            self.assertTrue(report["confirmed_delivery"])
            self.assertEqual(report["delivery_authorization"]["state"], "not_required")
            self.assertEqual(len(self.native.provider.client.state.calls), 1)
            self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        finally:
            await sender.terminate()

    async def test_official_sender_accepts_the_default_profile_id(self):
        sender = self.make_controller(config=host_config(staging={"delivery_mode": "onebot_private"}))
        try:
            result = await sender.initialize_profile()
            self.assertTrue(result.is_success, result.failure)
            self.assertTrue((await sender.start()).is_success)
            self.assertFalse(sender.status()["delivery_authorization"]["required"])
            self.assertEqual(self.native.provider.client.state.calls, [])
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await sender.terminate()

    async def test_legacy_global_revoke_does_not_close_intake_or_block_delivery(self):
        sender = self.make_controller(config=host_config(staging={
            "profile_id": "sender-revoke",
            "delivery_mode": "onebot_private",
        }))
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(*_):
            entered.set()
            await release.wait()
            return completion()

        self.native.provider.client.state.behavior = delayed
        try:
            self.assertTrue((await sender.initialize_profile()).is_success)
            self.assertTrue((await sender.authorize_delivery()).is_success)
            self.assertTrue((await sender.start()).is_success)
            batch = (await sender.receive_claimed(FakeEvent(self.native))).unwrap()
            await asyncio.wait_for(entered.wait(), 2)
            revoked = await sender.revoke_delivery()
            self.assertTrue(revoked.is_success, revoked.failure)
            self.assertTrue(sender.status()["accepting"])
            self.assertTrue(sender.claims(FakeEvent(self.native, event_id="event-2")))
            self.assertEqual((await sender.authorize_delivery()).unwrap()["state"], "not_required")
            release.set()
            await wait_for_batch(sender.session, batch)
            report = (await sender.inspect(batch)).unwrap()
            self.assertEqual(report["delivery_authorization"]["state"], "not_required")
            self.assertEqual(report["delivery_receipts"][0]["state"], "delivered")
            self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        finally:
            release.set()
            await sender.terminate()

    async def test_reload_does_not_auto_start_and_needs_no_delivery_grant(self):
        config = host_config(staging={
            "profile_id": "sender-reload",
            "delivery_mode": "onebot_private",
        })
        sender = self.make_controller(config=config)
        try:
            self.assertTrue((await sender.initialize_profile()).is_success)
            self.assertTrue((await sender.authorize_delivery()).is_success)
        finally:
            await sender.terminate()

        other = self.make_controller(config=config)
        try:
            loaded = await other.load_existing()
            self.assertTrue(loaded.is_success, loaded.failure)
            self.assertEqual(other.session.application.state, "new")
            self.assertFalse(other.status()["accepting"])
            self.assertFalse(other.status()["delivery_authorization"]["required"])
            self.assertTrue(other.status()["delivery_authorization"]["authorized"])
            self.assertEqual(self.native.provider.client.state.calls, [])
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await other.terminate()

    async def test_revoked_dialogue_permission_keeps_the_profile_reopenable(self):
        """对话权限可以按人收回；收回之后 profile 仍要能重开、目标仍要能解析。

        收回前这条链路会在 `_target()` 里直接抛 `authorization_revoked`：既没有对话，
        也没有回话，用户看到的是"插件坏了"。礼貌拒绝属于收信闸，不属于授权供给。
        """
        (await self.controller.initialize_profile()).unwrap()
        bootstrap = self.controller.bootstrap
        identity = bootstrap.identity
        identifier = bootstrap.grant_id("conversation.reply")
        identity.revoke_grant(identifier, revoked_at=NOW, expected_revision=identity.revision)

        loaded = await self.controller.load_existing()
        self.assertTrue(loaded.is_success, loaded.failure)
        context = bootstrap._target(NOW)
        self.assertEqual(context.scope.key, self.controller.configuration.scope.key)

        # 撤销不会被重开流程补回来：授权层必须仍然说"已收回"。
        access = identity.authorize(context.actor, scope=context.scope,
                                    capability="conversation.reply", observed_at=NOW)
        self.assertEqual(access.failure.code, "authorization_revoked")

    async def test_revoked_required_capability_still_fails_hard(self):
        (await self.controller.initialize_profile()).unwrap()
        bootstrap = self.controller.bootstrap
        identity = bootstrap.identity
        identity.revoke_grant(bootstrap.grant_id("text"), revoked_at=NOW, expected_revision=identity.revision)

        with self.assertRaises(TaskError) as raised:
            bootstrap._target(NOW)
        self.assertEqual(raised.exception.code, "authorization_revoked",
                         "必需能力被收回是真故障，不能跟着一起放行")

    async def test_voice_switch_loads_existing_delivery_profile_without_repinning(self):
        config = host_config(staging={"profile_id": "sender-voice", "delivery_mode": "onebot_private"})
        original = self.make_controller(config=config)
        try:
            self.assertTrue((await original.initialize_profile()).is_success)
            self.assertTrue((await original.authorize_delivery()).is_success)
            fingerprint = original.configuration.fingerprint
        finally:
            await original.terminate()

        config["voice_reply"] = {"enabled": True}
        other = self.make_controller(config=config)
        try:
            loaded = await other.load_existing()
            self.assertTrue(loaded.is_success, loaded.failure)
            self.assertEqual(other.configuration.fingerprint, fingerprint)
            self.assertEqual(other.session.application.state, "new")
            self.assertTrue(other.settings.voice_reply_enabled)
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await other.terminate()

    async def test_revoke_waiting_for_start_still_leaves_intake_closed(self):
        sender = self.make_controller(config=host_config(staging={
            "profile_id": "sender-start-race",
            "delivery_mode": "onebot_private",
        }))
        entered, release = asyncio.Event(), asyncio.Event()
        try:
            self.assertTrue((await sender.initialize_profile()).is_success)
            self.assertTrue((await sender.authorize_delivery()).is_success)

            async def delayed(_):
                entered.set()
                await release.wait()

            self.native.before_resolve = delayed
            starting = asyncio.create_task(sender.start())
            await asyncio.wait_for(entered.wait(), 2)
            revoking = asyncio.create_task(sender.revoke_delivery())
            await asyncio.sleep(0)
            release.set()
            self.assertTrue((await starting).is_success)
            self.assertTrue((await revoking).is_success)
            self.assertFalse(sender.status()["accepting"])
            self.assertFalse(sender.status()["delivery_authorization"]["authorized"])
        finally:
            release.set()
            self.native.before_resolve = None
            await sender.terminate()

    async def test_incomplete_probe_discovers_account_and_default_provider_without_writes(self):
        incomplete = self.make_controller(
            config=host_config(
                staging={"enabled": False},
                target={"account_id": "", "participant_id": ""},
                model={"provider_id": ""},
            )
        )
        try:
            result = await incomplete.probe()
            self.assertTrue(result.is_success, result.failure)
            report = result.unwrap()
            self.assertEqual(report["connected_account_ids"], ["100", "101"])
            self.assertEqual(report["resolved_provider_id"], "native-model")
            self.assertFalse(report["target_ready"])
            self.assertFalse(report["model_request_sent"])
            self.assertFalse(report["platform_message_sent"])
            self.assertFalse(incomplete.intent_path.exists())
            self.assertEqual(self.native.provider.client.state.calls, [])
            self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        finally:
            await incomplete.terminate()


if __name__ == "__main__":
    unittest.main()
