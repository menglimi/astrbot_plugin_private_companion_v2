from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest

from companion_v2.adapters.astrbot.native import HostPersona, persona_instruction
from companion_v2.adapters.astrbot.staging import AstrBotStagingSession, NativeAdapterTypes, StagingProfile
from companion_v2.adapters.astrbot.staging_config import DELIVERY_CAPABILITY, DELIVERY_GRANT_ID
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.messages import event_from_document
from companion_v2.execution.models import TaskContext, digest
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from companion_v2.adapters.astrbot.provider import UsageTariff
from tests.native_adapter_support import completion, FakeEvent, FakeProvider, FakeReverseApi, NativeFixture
from tests.test_management_access import NOW, ROLE


class StagingFixture(NativeFixture):
    async def asyncSetUp(self):
        self.snapshot = await self.capture()
        self.personas.register_route(self.snapshot.route, observed_at=NOW)
        actor = self.identity.resolve_authenticated(self.snapshot.principal, observed_at=NOW).unwrap()
        role = self.personas.resolve(self.snapshot.route.scope, observed_at=NOW).unwrap().binding
        self.target = TaskContext(actor, role, self.snapshot.recipients)
        self.staging_profile = StagingProfile(self.target, RuntimeIdentity("companion", "runtime-1", "astrbot", "host"),
            HostPersona("bot-a", "original", ROLE, digest(persona_instruction(self.native.persona))), "native-model",
            UsageTariff(2000000, 1000000, 4000000), BudgetPolicy(*(Amount(10**8, 10**9) for _ in range(5))),
            "保持原角色，只使用有依据的材料。", max_output_tokens=100, policy=ConversationPolicy(0, 0, 180, 0))
        self.native_types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)

    def staging(self, *, runtime=None, review_only=False, **changes):
        session = AstrBotStagingSession(runtime or self.runtime, self.native,
            profile=replace(self.staging_profile, **changes), native_types=self.native_types,
            now=self.clock.now, review_only=review_only)
        self.addAsyncCleanup(session.close)
        return session

    async def start_staging(self, session=None, generation=0, *, review_only=False):
        session = session or self.staging(review_only=review_only)
        (await session.start(expected_task_generation=generation, expected_model_generation=generation)).unwrap()
        return session

    async def run_staging(self, session, *, event_id="event-1"):
        batch = (await session.receive(FakeEvent(self.native, event_id=event_id))).unwrap()
        await self.done(session.application, batch)
        return batch

    def patch_model(self, session, changes):
        service = session.application.configuration
        snapshot = service.read(self.target.actor, target=session.config_target,
            group_id=session.model_profile.group, observed_at=NOW).unwrap()
        return service.patch(self.target.actor, target=session.config_target,
            group_id=session.model_profile.group, expected_edit_token=snapshot.edit_token,
            operation=self.operation(self.target.scope), changes={session.model_profile.group + "." + k: v for k, v in changes.items()},
            observed_at=NOW).unwrap()

    def grant_delivery(self, *, grant_id=DELIVERY_GRANT_ID, scope=None,
                       valid_from=NOW, expires_at=None, capability=DELIVERY_CAPABILITY):
        return self.identity.issue_grant(
            grant_id=grant_id,
            subject=self.target.actor.subject,
            scope=scope or self.target.scope,
            capability=capability,
            tier=AuthorizationTier.STANDARD,
            valid_from=valid_from,
            expires_at=expires_at or NOW + timedelta(hours=1),
            expected_revision=self.identity.revision,
        )


class StagingTests(StagingFixture, unittest.IsolatedAsyncioTestCase):
    async def test_preflight_reads_authority_without_starting_tasks_or_claiming_config_adoption(self):
        session = self.staging()
        report = session.inspect().unwrap()
        self.assertEqual(report["configuration_application"], "consumer_not_started")
        self.assertEqual(report["state"], "new")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM task_supervisor", ()))
        self.assertFalse(session.application.tasks.authorize_context(self.target,
            action="conversation.reply", observed_at=NOW).is_success)
        self.assertEqual((await session.receive(FakeEvent(self.native))).failure.code, "host_not_running")

    async def test_internal_review_only_rehearsal_generates_local_draft(self):
        session = await self.start_staging(review_only=True)
        batch = await self.run_staging(session)
        preview = session.preview(batch).unwrap()
        report = session.inspect(batch).unwrap()
        self.assertEqual([p["text"] for p in preview["parts"]], ["我在这里。"])
        self.assertFalse(preview["sent"])
        self.assertTrue(report["preview_ready"])
        self.assertFalse(report["confirmed_delivery"])
        self.assertEqual(report["configuration_application"], "applied")
        self.assertEqual(report["model"]["transport"], "astrbot_openai")
        self.assertEqual(report["model"]["calls"][0]["actual_tokens"], 40)
        self.assertEqual(report["conversation"]["receipt_basis"], "staging_preview")
        self.assertEqual(report["delivery_receipts"][0]["state"], "failed")
        self.assertIsNone(report["delivery_receipts"][0]["platform_ref"])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])
        self.assertEqual(session.application.messages.history(self.target).unwrap()["items"], [])
        summary = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(self.snapshot.instruction, summary)
        self.assertNotIn("我在这里。", summary)

    async def test_official_delivery_reports_original_operation_and_real_ack_field(self):
        session = await self.start_staging(self.staging(delivery_mode="onebot_private"))
        batch = await self.run_staging(session)
        report = session.inspect(batch).unwrap()
        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["conversation"]["receipt_basis"], "onebot_reverse_websocket")
        self.assertEqual(report["conversation"]["recipient_read"], "unknown")
        receipt = report["delivery_receipts"][0]
        self.assertEqual(receipt["operation_id"], "send-" + receipt["part_id"])
        self.assertTrue(receipt["platform_ref"].endswith(":456"))
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        self.assertEqual(session.preview(batch).failure.code, "staging_preview_disabled")

    async def test_legacy_preview_value_uses_official_sender_after_restart(self):
        session = await self.start_staging(self.staging(delivery_mode="preview"))
        batch = await self.run_staging(session)
        report = session.inspect(batch).unwrap()
        self.assertTrue(report["confirmed_delivery"])
        self.assertEqual(report["delivery_mode"], "onebot_private")
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)
        await session.close()
        other = self.staging(runtime=self.open_runtime(), delivery_mode="onebot_private")
        result = await other.start(expected_task_generation=1, expected_model_generation=1)
        self.assertTrue(result.is_success, result.failure)
        self.assertEqual(self.runtime.read_one("SELECT generation FROM task_supervisor", ())["generation"], 1)
        self.assertEqual(other.inspect(batch).unwrap()["delivery_receipts"][0]["state"], "delivered")
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_restart_preserves_duplicate_input_budget_and_unknown_send_without_resubmission(self):
        self.grant_delivery()
        self.native.platform.client._api._wsr_api.error = TimeoutError("submitted but no ACK")
        session = await self.start_staging(self.staging(delivery_mode="onebot_private"))
        batch = await self.run_staging(session)
        before = session.inspect(batch).unwrap()
        self.assertEqual(before["delivery_receipts"][0]["state"], "unknown")
        await session.close()
        other = self.staging(runtime=self.open_runtime(), delivery_mode="onebot_private",
            runtime_identity=replace(self.staging_profile.runtime_identity, runtime_instance_id="runtime-2"))
        await self.start_staging(other, generation=1)
        self.assertNotEqual(other.inspect().unwrap()["configuration_application"], "applied")
        self.assertEqual((await other.receive(FakeEvent(self.native))).unwrap(), batch)
        report = other.inspect(batch).unwrap()
        self.assertEqual(report["delivery_receipts"], before["delivery_receipts"])
        self.assertEqual(report["model"]["calls"], before["model"]["calls"])
        self.assertFalse(report["confirmed_delivery"])
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)

    async def test_current_config_is_adopted_by_next_task_without_exposing_prompt_in_summary(self):
        session = await self.start_staging()
        self.patch_model(session, {"prompt": "新的任务提示，只供此测试角色使用。", "max_output_tokens": 40})
        self.assertNotEqual(session.inspect().unwrap()["configuration_application"], "applied")
        batch = await self.run_staging(session)
        payload = self.native.provider.client.state.calls[0][0]
        self.assertEqual(payload["max_tokens"], 40)
        self.assertIn("新的任务提示", json.dumps(payload, ensure_ascii=False))
        report = session.inspect(batch).unwrap()
        self.assertEqual(report["configuration_application"], "applied")
        self.assertNotIn("新的任务提示", json.dumps(report, ensure_ascii=False))

    async def test_unavailable_provider_config_fails_before_source_or_model_intake(self):
        session = self.staging()
        self.patch_model(session, {"provider": "unregistered"})
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "staging_model_configuration_mismatch")
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM task_supervisor", ()))
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM conversation_inputs", ()))
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_revoked_identity_is_not_recreated_on_restart(self):
        session = await self.start_staging()
        batch = await self.run_staging(session)
        await session.close()
        self.identity.revoke_binding(self.target.actor.binding_id, revoked_at=NOW, expected_revision=self.identity.revision)
        revision = self.identity.revision
        other = self.staging(runtime=self.open_runtime())
        result = await other.start(expected_task_generation=1, expected_model_generation=1)
        self.assertEqual(result.failure.code, "binding_revoked")
        self.assertEqual(session.preview(batch).failure.code, "binding_revoked")
        self.assertEqual(self.identity.revision, revision)
        self.assertEqual(len(self.native.provider.client.state.calls), 1)

    async def test_revocation_while_preflight_awaits_host_leaves_no_profile_or_runtime_generation(self):
        session = self.staging()
        entered, release = asyncio.Event(), asyncio.Event()
        async def pause(_):
            entered.set()
            await release.wait()
        self.native.before_resolve = pause
        pending = asyncio.create_task(session.start(expected_task_generation=0, expected_model_generation=0))
        await asyncio.wait_for(entered.wait(), 1)
        self.identity.revoke_binding(self.target.actor.binding_id, revoked_at=NOW, expected_revision=self.identity.revision)
        release.set()
        self.assertEqual((await pending).failure.code, "binding_revoked")
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM task_supervisor", ()))
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM operations WHERE operation_id = ?", (session.PIN_ID,)))

    async def test_unselected_window_and_account_cannot_publish_input(self):
        session = await self.start_staging()
        for event in (FakeEvent(self.native, sender="201"), FakeEvent(self.native, login="101")):
            self.assertFalse((await session.receive(event)).is_success)
        self.native.cid = "conversation-2"
        self.assertEqual((await session.receive(FakeEvent(self.native))).failure.code, "staging_target_mismatch")
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM conversation_inputs", ()))
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_a_reconfigured_provider_reopens_because_the_pin_is_identity_only(self):
        """The PIN guards *who* the profile is, not how its provider is tuned.

        A provider whose configuration moved is refused upstream, where the profile is
        actually rebuilt from the live host and the provider fingerprint is checked
        (``tests/test_astrbot_staging_bootstrap.py``). This layer previously hashed the
        provider binding and the model profile too, so a model renamed upstream or a
        re-tuned parameter took the whole role offline and the operator saw only
        "connection failed" -- the same defect the pinned-profile split fixed one layer
        up. Nothing here rebinds: same target, same persona, same account, same provider.
        """
        session = await self.start_staging()
        await session.close()
        self.native.provider.provider_config["custom_extra_body"]["temperature"] = 0.1
        other = self.staging(runtime=self.open_runtime())
        result = await other.start(expected_task_generation=1, expected_model_generation=1)
        self.assertTrue(result.is_success, result.failure)
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_cancelled_draft_cannot_be_read_or_delivered_as_a_preview(self):
        session = await self.start_staging()
        batch = await self.run_staging(session)
        event_key = self.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))["event_key"]
        session.application.withdraw(self.target, event_key).unwrap()
        self.assertFalse(session.preview(batch).is_success)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_original_source_revocation_removes_preview_access_without_erasing_receipt(self):
        session = await self.start_staging()
        batch = await self.run_staging(session)
        record = self.runtime.read_one("SELECT event_json FROM conversation_inputs WHERE batch_id = ?", (batch,))
        event = event_from_document(json.loads(record["event_json"]), self.target)
        before = session.inspect(batch).unwrap()["delivery_receipts"]
        session.application.messages.sources.revoke(event.source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(session.preview(batch).failure.code, "source_revoked")
        self.assertEqual(session.inspect(batch).unwrap()["delivery_receipts"], before)
        self.assertFalse(session.inspect(batch).unwrap()["preview_ready"])

    async def test_close_during_startup_does_not_wait_for_or_reactivate_slow_host_lookup(self):
        session = self.staging()
        entered, release = asyncio.Event(), asyncio.Event()
        async def pause(_):
            entered.set()
            await release.wait()
        self.native.before_resolve = pause
        pending = asyncio.create_task(session.start(expected_task_generation=0, expected_model_generation=0))
        await asyncio.wait_for(entered.wait(), 1)
        second = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(second.failure.code, "host_already_started")
        try:
            stopped = await asyncio.wait_for(session.close(), 1)
            self.assertEqual(stopped.state, "stopped")
        finally:
            release.set()
        self.assertEqual((await pending).failure.code, "host_not_running")
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM task_supervisor", ()))
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM operations WHERE operation_id = ?", (session.PIN_ID,)))

    async def test_stop_during_host_capture_closes_intake_and_keeps_borrowed_store_open(self):
        session = await self.start_staging()
        entered, release = asyncio.Event(), asyncio.Event()
        async def pause(_):
            entered.set()
            await release.wait()
        self.native.before_resolve = pause
        pending = asyncio.create_task(session.receive(FakeEvent(self.native)))
        await asyncio.wait_for(entered.wait(), 1)
        stopped = await session.close()
        self.assertFalse(stopped.storage_closed)
        self.assertEqual(stopped.state, "stopped")
        release.set()
        self.assertEqual((await pending).failure.code, "host_not_running")
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM conversation_inputs", ()))

    async def test_stop_during_model_cancels_work_keeps_unknown_usage_and_never_sends(self):
        entered = asyncio.Event()
        async def blocked(*_):
            entered.set()
            await asyncio.Event().wait()
        self.native.provider.client.state.behavior = blocked
        self.grant_delivery()
        session = await self.start_staging(self.staging(delivery_mode="onebot_private"))
        batch = (await session.receive(FakeEvent(self.native))).unwrap()
        await asyncio.wait_for(entered.wait(), 2)
        report = await session.close(grace_seconds=0)
        self.assertEqual(report.state, "stopped")
        self.assertEqual(session.inspect(batch).unwrap()["model"]["calls"][0]["usage_state"], "unknown")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_sender_start_requires_fixed_delivery_grant_before_any_io(self):
        session = self.staging(delivery_mode="onebot_private")
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "authorization_denied")
        self.assertFalse(session.inspect().unwrap()["delivery_authorization"]["authorized"])
        self.assertIsNone(self.runtime.read_one("SELECT 1 FROM task_supervisor", ()))
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_revoked_delivery_grant_prevents_sender_start(self):
        self.grant_delivery()
        self.identity.revoke_grant(
            DELIVERY_GRANT_ID,
            revoked_at=NOW,
            expected_revision=self.identity.revision,
        )
        session = self.staging(delivery_mode="onebot_private")
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "authorization_revoked")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_expired_delivery_grant_prevents_sender_start(self):
        self.grant_delivery(valid_from=NOW - timedelta(seconds=2), expires_at=NOW)
        session = self.staging(delivery_mode="onebot_private")
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "authorization_expired")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_wrong_scope_and_replacement_delivery_grants_are_rejected(self):
        wrong_scope = replace(
            self.target.scope,
            native_scope_id="201",
            session_id="201",
        )
        self.grant_delivery(scope=wrong_scope)
        session = self.staging(delivery_mode="onebot_private")
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "staging_delivery_grant_changed")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_alternative_delivery_grant_cannot_replace_fixed_grant(self):
        self.grant_delivery(grant_id="replacement-delivery-grant")
        session = self.staging(delivery_mode="onebot_private")
        result = await session.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "staging_delivery_grant_changed")
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_delivery_expiring_during_generation_never_calls_onebot(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(*_):
            entered.set()
            await release.wait()
            return completion()

        self.native.provider.client.state.behavior = delayed
        self.grant_delivery(expires_at=NOW + timedelta(seconds=1))
        session = await self.start_staging(self.staging(delivery_mode="onebot_private"))
        batch = (await session.receive(FakeEvent(self.native))).unwrap()
        await asyncio.wait_for(entered.wait(), 2)
        self.clock.advance(timedelta(seconds=1))
        release.set()
        await self.done(session.application, batch)
        report = session.inspect(batch).unwrap()
        self.assertEqual(report["delivery_authorization"]["state"], "authorization_expired")
        self.assertEqual(report["delivery_receipts"][0]["state"], "failed")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_unpinned_existing_runtime_cannot_be_adopted_by_loader(self):
        host = await self.setup_host()
        host.receive(self.snapshot).unwrap()
        await host.application.close(grace_seconds=0)
        session = self.staging()
        result = await session.start(expected_task_generation=1, expected_model_generation=1)
        self.assertEqual(result.failure.code, "staging_store_in_use")

    async def test_stale_start_cannot_take_over_generations(self):
        session = await self.start_staging()
        other = self.staging(runtime=self.open_runtime())
        result = await other.start(expected_task_generation=0, expected_model_generation=0)
        self.assertEqual(result.failure.code, "supervisor_generation_conflict")
        self.assertEqual(session.inspect().unwrap()["task_generation"], 1)
        self.assertEqual(session.inspect().unwrap()["model_generation"], 1)
