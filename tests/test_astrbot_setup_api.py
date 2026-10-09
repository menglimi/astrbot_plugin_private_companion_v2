"""Exercise the persistent first-run guide against synthetic AstrBot adapters."""

import json
import asyncio
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_astrbot_staging_host import WebContext, host_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi, completion
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_management_access import NOW
from astrbot_host.binding_store import PendingBinding, write_binding
from astrbot_host.controller import AstrBotStagingController
from astrbot_host.multi_controller import AstrBotMultiController
from astrbot_host.setup_api import SetupWebAPI
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind


class AstrBotSetupFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-setup-")
        self.root = Path(self.temporary.name)
        self.native = WebContext()
        self.types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        self.config = host_config(staging={"profile_id": "setup-flow", "delivery_mode": "onebot_private"})
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        self.native.get_all_providers = lambda: [self.native.provider]
        self.native.provider.meta = lambda: NS(id="native-model", name="Fixture model")

    def make_single_controller(self):
        return AstrBotStagingController(self.native, self.config, self.root,
                                        native_types=self.types, now=lambda: NOW)

    def attach_config_writer(self):
        def save(candidate):
            self.config.clear()
            self.config.update(candidate)
            self.controller.refresh_settings()
        self.controller.save_plugin_config = save

    async def asyncTearDown(self):
        await self.controller.terminate()
        self.temporary.cleanup()

    async def call(self, name, body=None, *, username="administrator"):
        payload = (b"" if name in {"model_tasks", "profile"} else
                   json.dumps(body if body is not None else {}, ensure_ascii=False).encode("utf-8"))
        request = NS(username=username, query={}, body=AsyncMock(return_value=payload))
        with patch("astrbot_host.setup_api.request", request):
            return await getattr(self.api, name)()

    async def test_setup_api_has_no_runtime_mode_endpoint_or_status_field(self):
        routes = {route for route, *_ in self.api.routes()}
        self.assertNotIn("/astrbot_plugin_private_companion_v2/setup/mode", routes)
        status = await self.call("status")
        self.assertEqual(status["status"], "ok", status)
        self.assertNotIn("mode", status["data"])

    def prepare_contact_model(self, text="想起你说过的航行计划。"):
        async def behavior(_payload, _tools):
            return completion(json.dumps({"decision": "send", "text": text,
                                          "decision_confidence": 0.96}, ensure_ascii=False))
        self.native.provider.client.state.behavior = behavior

    async def wait_for_test(self):
        for _ in range(500):
            receipt = self.api.progress.read()["proactive_test"]
            if receipt and receipt["state"] != "started":
                return receipt
            await asyncio.sleep(0.01)
        self.fail(f"proactive test did not reach a terminal receipt: {self.api.progress.read()['proactive_test']}")

    def message_calls(self):
        calls = self.native.platform.client._api._wsr_api.calls
        self.assertTrue(all(action in {"send_private_msg", "get_friend_list", "get_stranger_info", "get_login_info"}
                            for action, _ in calls))
        return [call for call in calls if call[0] == "send_private_msg"]

    async def prepare_trusted_conversation_source(self):
        started = await self.controller.start()
        self.assertIsNone(started.failure, started.failure)
        batch = (await self.controller.receive_claimed(
            FakeEvent(self.native, event_id="setup-trusted-source"))).unwrap()
        await wait_for_batch(self.controller.session, batch)
        self.assertEqual(len(self.message_calls()), 1)

    async def test_proactive_diagnostic_uses_source_backed_route_and_core_context(self):
        context = NS(scope=NS(kind=ScopeKind.PRIVATE))
        task = NS(task_id="diagnostic-task", state="succeeded", reason=None)
        route = {"id": "weather_event", "label": "天气观测生产器", "variant": "weather"}
        candidate = {"opportunity": object(), "intents": (NS(purpose="environment",
            thought=NS(summary="角色配置地点的当前天气观测：晴，18℃。")),),
            "role_instruction": "role instructions", "route": route, "diagnostic_origin": {
                "_diagnostic": {"route_id": "weather_event", "batch_id": "batch-1",
                    "purpose": "environment", "event_key": "event-1", "event_hash": "hash-1", "role_hash": "role-1"},
                "weather_event": {"slot": "slot-1"}}}
        app = NS(state="running", now=lambda: NOW)
        app.proactive = NS(contact=AsyncMock(return_value=Outcome.success(NS(task=task))),
            observe=lambda _context, _task_id: Outcome.success({"skipped": False, "delivery": "delivered",
                "judge": "allowed", "judge_allowed": True, "judge_reason": None, "receipt_ref": "receipt-1"}))
        app.tasks = NS(read=lambda _context, _task_id: Outcome.success(task))
        app.contact_schedule = NS(diagnostic_candidate=AsyncMock(return_value=candidate))
        session = NS(application=app)
        controller = NS(session=session, last_session=None, runtime=object(), now=lambda: NOW,
            start=AsyncMock(return_value=Outcome.success({})))
        api = SetupWebAPI.__new__(SetupWebAPI)
        api.controller = controller
        api._test_lock = asyncio.Lock()
        api._setup_context = AsyncMock(return_value=(session, context, "role instructions"))
        api._binding = lambda: {"bound": True, "pending": False}

        class ContactManager:
            def __init__(self, _app, _context):
                pass

            def status(self, _operator):
                return Outcome.success({"purposes": {"environment": {"allowed": True, "reason": None}}})

        payload = json.dumps({"purpose": "environment", "confirm_delivery": True}).encode("utf-8")
        request = NS(username="administrator", query={}, body=AsyncMock(return_value=payload))
        with patch("astrbot_host.setup_api.request", request), \
             patch("astrbot_host.setup_api.ContactManagement", ContactManager), \
             patch("astrbot_host.setup_api.dashboard_operator", return_value=object()):
            response = await api.proactive_diagnostic()

        result = response["data"]
        self.assertEqual(result["state"], "passed", result)
        self.assertEqual(result["recipient"], "core_administrator")
        self.assertEqual(result["purpose"], "environment")
        self.assertEqual(result["route"], route)
        app.contact_schedule.diagnostic_candidate.assert_awaited_once_with(context, "environment", at=NOW)
        app.proactive.contact.assert_awaited_once()
        args, kwargs = app.proactive.contact.await_args
        self.assertIs(args[0], context)
        self.assertEqual(args[2][0].purpose, "environment")
        self.assertEqual(args[2][0].thought.summary, "角色配置地点的当前天气观测：晴，18℃。")
        self.assertEqual(kwargs["role_instruction"], "role instructions")
        self.assertTrue(kwargs["administrator_test"])
        self.assertTrue(kwargs["diagnostic_source_backed"])
        self.assertEqual(kwargs["diagnostic_origin"], candidate["diagnostic_origin"])
        self.assertFalse(result["replay_allowed"])

        app.proactive.observe = lambda _context, _task_id: Outcome.success({"skipped": True,
            "delivery": None, "judge": None, "judge_allowed": None, "judge_reason": None,
            "receipt_ref": None, "skip_reason": "model_decision", "model_skip_reason": "no_natural_opening",
            "dedup_reason": None, "presentation_reason": None, "decision_confidence": 0.91,
            "silence_threshold": 0.65})
        with patch("astrbot_host.setup_api.request", request), \
             patch("astrbot_host.setup_api.ContactManagement", ContactManager), \
             patch("astrbot_host.setup_api.dashboard_operator", return_value=object()):
            skipped_response = await api.proactive_diagnostic()
        skipped = skipped_response["data"]
        self.assertEqual((skipped["state"], skipped["skip_reason"], skipped["model_skip_reason"]),
                         ("skipped", "model_decision", "no_natural_opening"))
        self.assertIn({"stage": "model_generation", "state": "passed"}, skipped["stages"])

    async def test_proactive_diagnostic_allows_manual_test_during_quiet_hours(self):
        context = NS(scope=NS(kind=ScopeKind.PRIVATE))
        task = NS(task_id="diagnostic-task", state="succeeded", reason=None)
        candidate = {"opportunity": object(), "intents": (NS(purpose="care",
            thought=NS(summary="对方刚才明确说最近很累。")),), "role_instruction": "role instructions",
            "route": {"id": "relationship_event", "label": "明确关系表达生产器", "variant": "care"},
            "diagnostic_origin": {"_diagnostic": {"route_id": "relationship_event", "batch_id": "batch-1",
                "purpose": "care", "event_key": "event-1", "event_hash": "hash-1", "role_hash": "role-1"},
                "relationship_event": {"purpose": "care"}}}
        app = NS(state="running", now=lambda: NOW)
        app.proactive = NS(
            contact=AsyncMock(return_value=Outcome.success(NS(task=task))),
            observe=lambda _context, _task_id: Outcome.success({"skipped": False, "delivery": "delivered",
                "judge": None, "judge_allowed": None, "judge_reason": None, "receipt_ref": "receipt-1"}))
        app.tasks = NS(read=lambda _context, _task_id: Outcome.success(task))
        app.contact_schedule = NS(diagnostic_candidate=AsyncMock(return_value=candidate))
        session = NS(application=app)
        controller = NS(session=session, last_session=None, runtime=object(), now=lambda: NOW,
            start=AsyncMock(return_value=Outcome.success({})))
        api = SetupWebAPI.__new__(SetupWebAPI)
        api.controller = controller
        api._test_lock = asyncio.Lock()
        api._setup_context = AsyncMock(return_value=(session, context, "role instructions"))
        api._binding = lambda: {"bound": True, "pending": False}

        class ContactManager:
            def __init__(self, _app, _context):
                pass

            def status(self, _operator):
                return Outcome.success({"settings": {"enabled": True, "care.enabled": True},
                    "purposes": {"care": {"allowed": False, "reason": "proactive_quiet_hours"}}})

        payload = json.dumps({"purpose": "care", "confirm_delivery": True}).encode("utf-8")
        request = NS(username="administrator", query={}, body=AsyncMock(return_value=payload))
        with patch("astrbot_host.setup_api.request", request), \
             patch("astrbot_host.setup_api.ContactManagement", ContactManager), \
             patch("astrbot_host.setup_api.dashboard_operator", return_value=object()):
            response = await api.proactive_diagnostic()

        result = response["data"]
        self.assertEqual(result["state"], "passed", result)
        self.assertEqual(result["delivery_state"], "delivered")
        app.proactive.contact.assert_awaited_once()
        self.assertTrue(app.proactive.contact.await_args.kwargs["administrator_test"])

    async def test_proactive_diagnostic_without_a_real_source_never_calls_contact(self):
        context = NS(scope=NS(kind=ScopeKind.PRIVATE))
        app = NS(state="running", now=lambda: NOW)
        app.proactive = NS(contact=AsyncMock())
        app.contact_schedule = NS(diagnostic_candidate=AsyncMock(side_effect=TaskError(
            "contact_diagnostic_source_required", "no current news source")))
        session = NS(application=app)
        controller = NS(session=session, last_session=None, runtime=object(), now=lambda: NOW,
            start=AsyncMock(return_value=Outcome.success({})))
        api = SetupWebAPI.__new__(SetupWebAPI)
        api.controller = controller
        api._test_lock = asyncio.Lock()
        api._setup_context = AsyncMock(return_value=(session, context, "role instructions"))
        api._binding = lambda: {"bound": True, "pending": False}

        class ContactManager:
            def __init__(self, _app, _context):
                pass

            def status(self, _operator):
                return Outcome.success({"purposes": {"news": {"allowed": True, "reason": None}}})

        payload = json.dumps({"purpose": "news", "confirm_delivery": True}).encode("utf-8")
        request = NS(username="administrator", query={}, body=AsyncMock(return_value=payload))
        with patch("astrbot_host.setup_api.request", request), \
             patch("astrbot_host.setup_api.ContactManagement", ContactManager), \
             patch("astrbot_host.setup_api.dashboard_operator", return_value=object()):
            response = await api.proactive_diagnostic()

        result = response["data"]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["code"], "contact_diagnostic_source_required")
        self.assertEqual(result["stage"], "trusted_candidate")
        app.proactive.contact.assert_not_awaited()
        app.contact_schedule.diagnostic_candidate.assert_awaited_once_with(context, "news", at=NOW)

    async def bind_core_window(self, persona_id="original"):
        write_binding(self.controller.binding_root,
                      PendingBinding("qq-main", "100", "200", persona_id))
        result = await self.call("confirm_binding")
        self.assertEqual(result["status"], "ok", result)

    async def enter_model_step(self):
        self.attach_config_writer()
        await self.bind_core_window()
        self.assertIsNone(self.controller.runtime)
        status = await self.call("status")
        self.assertEqual(status["data"]["step"], "model")

    async def test_binding_precedes_model_and_does_not_initialize_the_runtime(self):
        initial = await self.call("status")
        self.assertEqual(initial["data"]["step"], "binding")
        await self.enter_model_step()
        self.assertEqual(self.message_calls(), [])
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_setup_saves_config_data_without_copying_host_locks(self):
        class HostConfig(dict):
            pass

        self.config = HostConfig(self.config)
        self.config.save_lock = threading.Lock()
        self.controller.config = self.config
        await self.enter_model_step()
        result = await self.call("model", {"provider_id": "native-model"})
        self.assertEqual(result["status"], "ok", result)

    async def test_model_selection_persists_and_prepares_before_knowledge(self):
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "native-model"})

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["model"]["provider_id"], "native-model")
        self.assertIsNotNone(self.controller.runtime)
        self.assertFalse(self.controller.status()["accepting"])
        status = await self.call("status")
        self.assertEqual(status["data"]["step"], "model")
        advanced = await self.call("complete", {"step": "model", "skipped": False})
        self.assertEqual(advanced["status"], "ok", advanced)
        self.assertEqual((await self.call("status"))["data"]["step"], "knowledge")
        self.assertEqual(self.message_calls(), [])
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_model_selection_rejects_unloaded_provider_without_saving(self):
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "missing-model"})

        self.assertEqual(result["data"]["code"], "host_provider_unavailable")
        self.assertEqual(self.config["model"]["provider_id"], "native-model")
        self.assertIsNone(self.controller.runtime)

    async def test_model_setup_uses_all_loaded_providers_without_registering_them(self):
        secondary = FakeProvider()
        secondary.provider_config["id"] = "secondary-model"
        secondary.meta = lambda: NS(id="secondary-model", name="Second model")
        providers = {"native-model": self.native.provider, "secondary-model": secondary}
        self.native.get_all_providers = lambda: list(providers.values())
        self.native.get_provider_by_id = lambda provider_id: providers.get(provider_id)
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "native-model"})

        self.assertEqual(result["status"], "ok", result)
        self.assertNotIn("additional_providers", self.config["model"])
        routes = await self.call("model_tasks")
        self.assertEqual(routes["status"], "ok", routes)
        self.assertEqual({item["id"] for item in routes["data"]["providers"]},
                         {"native-model", "secondary-model"})

    async def test_selecting_a_loaded_primary_clears_only_conflicting_legacy_routes(self):
        self.config["model"].update(
            additional_providers=[
                {"provider_id": "secondary-model", "max_output_tokens": 4096},
                {"provider_id": "other-model", "max_output_tokens": 1024},
            ],
            fallback_provider_id="secondary-model",
            replacement_rules='[{"keywords":["use other"],"provider_id":"other-model"}]',
        )
        secondary = FakeProvider()
        secondary.provider_config["id"] = "secondary-model"
        secondary.meta = lambda: NS(id="secondary-model", name="Second model")
        other = FakeProvider()
        other.provider_config["id"] = "other-model"
        other.meta = lambda: NS(id="other-model", name="Other model")
        providers = {"native-model": self.native.provider, "secondary-model": secondary, "other-model": other}
        self.native.get_all_providers = lambda: list(providers.values())
        self.native.get_provider_by_id = lambda provider_id: providers.get(provider_id)
        self.attach_config_writer()
        await self.enter_model_step()

        result = await self.call("model", {"provider_id": "secondary-model"})

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(self.config["model"]["provider_id"], "secondary-model")
        self.assertEqual(self.config["model"]["additional_providers"], [
            {"provider_id": "other-model", "max_output_tokens": 1024},
        ])
        self.assertEqual(self.config["model"]["fallback_provider_id"], "")
        self.assertIn('"provider_id":"other-model"', self.config["model"]["replacement_rules"])

    async def test_setup_reads_and_saves_task_routes_and_profiles_without_get_bodies(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")

        routes = await self.call("model_tasks")
        profiles = await self.call("profile")

        self.assertEqual(routes["status"], "ok", routes)
        self.assertTrue(any(item["kind"] == "conversation.reply" for item in routes["data"]["tasks"]))
        self.assertEqual(profiles["status"], "ok", profiles)
        self.assertIn("role_profile", profiles["data"])
        self.assertIn("relationship_profile", profiles["data"])

        task = next(item for item in routes["data"]["tasks"] if item["kind"] == "conversation.reply")
        saved = await self.call("configure_model_task", {
            "kind": task["kind"], "operation_key": "setup-route-test", "edit_token": task["edit_token"],
            "changes": {"provider": "native-model", "fallback": ""}, "reset": [],
        })
        self.assertEqual(saved["status"], "ok", saved)

    async def test_multi_mode_confirmation_seeds_the_first_private_target_and_persona(self):
        await self.controller.terminate()
        self.config["staging"]["enabled"] = False
        self.config["multi_host"] = {"enabled": True, "installation_id": "setup-shared"}
        self.controller = AstrBotMultiController(self.native, self.config, self.root,
                                                 native_types=self.types, now=lambda: NOW)
        self.api = SetupWebAPI(self.controller)
        self.native.persona_manager.get_persona_v3_by_id = lambda persona_id: (
            self.native.persona if persona_id == "original" else None)
        self.attach_config_writer()

        await self.bind_core_window()

        target, persona = self.config["multi_host"]["targets"][0], self.config["multi_host"]["personas"][0]
        self.assertEqual((target["platform_id"], target["account_id"], target["participant_id"]),
                         ("qq-main", "100", "200"))
        self.assertEqual((persona["bot_id"], persona["persona_id"]), (target["bot_id"], "original"))
        self.assertIsNone(self.controller.settings_error)
        self.assertTrue(self.controller.binding_state()["configured_target"])

    async def test_active_test_is_persisted_and_never_replayed(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "model", "skipped": False}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")
        await self.prepare_trusted_conversation_source()

        generated_text = "想起你说过的航行计划。"
        self.prepare_contact_model(generated_text)
        self.native.platform.client._api._wsr_api.result = {"message_id": -456}
        first = await self.call("proactive_test", {"enable_proactive": True})
        again = await self.call("proactive_test", {"enable_proactive": True})
        receipt = await self.wait_for_test()

        self.assertEqual(first["data"]["state"], "started")
        self.assertEqual(again["data"]["state"], "started")
        self.assertEqual(receipt["state"], "delivered", receipt)
        calls = self.message_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], "send_private_msg")
        self.assertIn(generated_text, json.dumps(calls[1][1], ensure_ascii=False))
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        from astrbot_host.management_identity import dashboard_operator
        from companion_v2.proactive.management import ContactManagement
        session = self.controller.session or self.controller.last_session
        settings = ContactManagement(session.application, session.profile.target).status(
            dashboard_operator(self.controller.runtime, "administrator", at=NOW)).unwrap()["settings"]
        self.assertFalse(settings["enabled"])
        self.assertFalse(settings["automatic_enabled"])

    async def test_recipient_confirmation_finishes_unknown_test_without_sending_again(self):
        await self.enter_model_step()
        await self.call("model", {"provider_id": "native-model"})
        await self.call("complete", {"step": "model", "skipped": False})
        await self.call("complete", {"step": "knowledge", "skipped": True})
        await self.call("complete", {"step": "relationships", "skipped": True})
        await self.prepare_trusted_conversation_source()
        self.prepare_contact_model()
        reverse_api = self.native.platform.client._api._wsr_api
        reverse_api.error = TimeoutError("the message may have been sent")
        self.assertEqual((await self.call("proactive_test", {"enable_proactive": True}))["data"]["state"], "started")
        receipt_after_test = await self.wait_for_test()
        self.assertEqual(receipt_after_test["state"], "unknown", receipt_after_test)
        self.assertEqual((await self.call("proactive_test", {"enable_proactive": True}))["data"]["code"],
                         "setup_test_non_replayable")
        receipt = self.api.progress.read()["proactive_test"]

        stale = await self.call("confirm_proactive_test", {"attempt_id": "another-attempt"})
        self.assertEqual(stale["data"]["code"], "setup_test_confirmation_invalid")
        denied = await self.call("confirm_proactive_test", {"attempt_id": receipt["attempt_id"]},
                                 username="api_key:fixture")
        self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        self.assertFalse(self.api.progress.read()["ready"])

        sends_before_confirmation = len(self.message_calls())
        confirmed = await self.call("confirm_proactive_test", {"attempt_id": receipt["attempt_id"]})
        self.assertEqual(confirmed["data"]["state"], "received")
        self.assertTrue(confirmed["data"]["ready"])
        saved = self.api.progress.read()["proactive_test"]
        self.assertEqual(saved["finished_at"], receipt["finished_at"])
        self.assertEqual(saved["confirmed_by"], "administrator")
        self.assertEqual((await self.call("proactive_test", {"enable_proactive": True}))["data"]["state"], "received")
        self.assertEqual(len(self.message_calls()), sends_before_confirmation)

        await self.controller.terminate()
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        self.assertEqual((await self.call("status"))["data"]["step"], "complete")

    async def test_recipient_confirmation_cannot_complete_setup_without_a_test(self):
        await self.enter_model_step()
        denied = await self.call("proactive_test", {"enable_proactive": False})
        self.assertEqual(denied["data"]["code"], "setup_proactive_opt_in_required")
        result = await self.call("confirm_proactive_test", {"attempt_id": "unstarted"})
        self.assertEqual(result["data"]["code"], "setup_test_confirmation_invalid")
        self.assertFalse(self.api.progress.read()["ready"])
        self.assertEqual(self.message_calls(), [])

    async def test_completed_guide_survives_plugin_restart_without_reopening_setup_steps(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "model", "skipped": False}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")
        await self.prepare_trusted_conversation_source()
        self.prepare_contact_model()
        self.assertEqual((await self.call("proactive_test", {"enable_proactive": True}))["data"]["state"], "started")
        receipt = await self.wait_for_test()
        self.assertEqual(receipt["state"], "delivered", receipt)

        await self.controller.terminate()
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        status = await self.call("status")

        self.assertEqual(status["data"]["step"], "complete")
        self.assertTrue(status["data"]["ready"])
        self.assertFalse(status["data"]["host"]["accepting"])

    async def test_interrupted_test_restores_contact_permission_after_plugin_restart(self):
        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "model", "skipped": False}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")

        started = await self.controller.start()
        self.assertIsNone(started.failure, started.failure)
        from astrbot_host.management_identity import dashboard_operator
        from companion_v2.proactive.management import ContactManagement

        session = self.controller.session or self.controller.last_session
        context = session.profile.target
        operator = dashboard_operator(self.controller.runtime, "administrator", at=NOW)
        manager = ContactManagement(session.application, context)
        current = manager.status(operator).unwrap()
        attempt_id = "interrupted-setup-test"
        self.api.progress.begin_proactive_test(attempt_id=attempt_id, started_at=NOW.isoformat())
        self.api.progress.record_test_contact_permission(attempt_id=attempt_id, enabled_before=False)
        manager.configure(operator, {"operation_key": "setup-test-" + attempt_id,
            "edit_token": current["edit_token"], "changes": {"enabled": True}}).unwrap()

        await self.controller.terminate()
        self.controller = self.make_single_controller()
        self.api = SetupWebAPI(self.controller)
        status = await self.call("status")

        self.assertEqual(status["status"], "ok", status)
        self.assertEqual(status["data"]["proactive_test"]["state"], "unknown")
        self.assertEqual(status["data"]["proactive_test"]["error_code"], "setup_test_interrupted")
        self.assertTrue(status["data"]["proactive_test"]["contact_permission_restored"])
        recovered_session = self.controller.session or self.controller.last_session
        restored = ContactManagement(recovered_session.application, context).status(
            dashboard_operator(self.controller.runtime, "administrator", at=NOW)).unwrap()["settings"]
        self.assertFalse(restored["enabled"])
        self.assertFalse(restored["automatic_enabled"])
        self.assertEqual(self.message_calls(), [])

    async def test_reconnect_route_starts_only_a_completed_setup(self):
        denied = await self.call("reconnect_host")
        self.assertEqual(denied["data"]["code"], "setup_completion_required")

        await self.enter_model_step()
        self.assertEqual((await self.call("model", {"provider_id": "native-model"}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "model", "skipped": False}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "knowledge", "skipped": True}))["status"], "ok")
        self.assertEqual((await self.call("complete", {"step": "relationships", "skipped": True}))["status"], "ok")
        await self.prepare_trusted_conversation_source()
        self.prepare_contact_model()
        self.assertEqual((await self.call("proactive_test", {"enable_proactive": True}))["data"]["state"], "started")
        receipt = await self.wait_for_test()
        self.assertEqual(receipt["state"], "delivered", receipt)

        connected = await self.call("reconnect_host")

        self.assertEqual(connected["status"], "ok", connected)
        self.assertTrue(connected["data"]["status"]["host"]["accepting"])


if __name__ == "__main__":
    unittest.main()
