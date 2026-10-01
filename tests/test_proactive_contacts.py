import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.agenda.models import AgendaTarget, Schedule
from companion_v2.conversation.foreground import BackgroundPromptTrigger
from companion_v2.delivery.service import DeliveryRequest
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.proactive.configuration import GROUP, target_for
from companion_v2.proactive.prompts import contact_output
from companion_v2.proactive.service import CONTACT_KIND
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from companion_v2.adapters.astrbot.model_wire import build_wire
from tests.proactive_support import ContactFixture
from tests.test_management_access import INSTALLATION, NOW, ROLE, SCOPE
from tests.test_role_tool_loop import answered


class ProactiveContactTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def test_contact_uses_persona_evidence_shared_model_delivery_and_independent_receipts(self):
        app = await self.enabled()
        source = self.source(app)
        opportunity = self.opportunity()
        context = self.contact_context()
        result = (await self.contact(app, opportunity, (self.intent(opportunity, sources=(source,)),))).unwrap()
        task = result.task
        self.assertEqual(task.state, "succeeded")
        self.assertEqual(task.effect, "committed")
        row = await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(len(self.sent), 1)
        prompt = self.called[0].original
        self.assertIsInstance(prompt.event, BackgroundPromptTrigger)
        self.assertEqual(prompt.role_instruction, "这是原角色人格，保持自然。")
        self.assertEqual(prompt.output_format, "proactive_contact")
        self.assertEqual(build_wire(self.called[0]).output_format, "proactive_contact")
        self.assertEqual(prompt.context.evidence_sources, (source,))
        evidence = [item.payload for item in prompt.context.materials if item.purpose == "contact_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("用户先前说过", evidence[0])
        self.assertIn("未回应", prompt.instruction)
        self.assertEqual(self.sent[0].context, context)
        self.assertEqual(self.sent[0].text, "想起你上次提到的书，读到哪里了？")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM sources", ())[0], 1)
        self.assertNotIn(self.sent[0].text, row["request_json"])
        status = app.proactive.observe(context, task.task_id).unwrap()
        self.assertEqual((status["delivery"], status["receipt_ref"]), ("delivered", row["receipt_ref"]))
        adoption = app.configuration.application_status(self.important, target=target_for(context), group_id=GROUP, observed_at=NOW).unwrap()
        self.assertEqual(adoption.state, "applied")

    async def test_disabled_by_default_and_missing_profile_do_not_call_foreground_provider(self):
        app = (await self.start()).application
        self.assertEqual((await self.contact(app)).failure.code, "no_feasible_thought")
        self.assertEqual(self.called, [])
        adoption = app.configuration.application_status(self.important, target=target_for(self.contact_context()),
            group_id=GROUP, observed_at=NOW).unwrap()
        self.assertEqual(adoption.state, "applied")
        await app.close()
        missing = (await self.start(self.host(profiles=self.profiles[:-1]), task_generation=1, model_generation=1)).application
        self.settings(missing, {"enabled": True}).unwrap()
        self.assertEqual((await self.contact(missing)).failure.code, "model_task_unregistered")
        self.assertEqual(self.called, [])

    async def test_skip_is_successful_model_decision_without_draft_or_delivery(self):
        app = await self.enabled()
        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        task = (await self.contact(app)).unwrap().task
        self.assertEqual(task.state, "succeeded")
        self.assertTrue(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["skipped"])
        record = self.runtime.read_one("SELECT record_json, body FROM proactive_contacts", ())
        self.assertEqual((json.loads(record["record_json"])["decision"], record["body"]), ("skip", ""))
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM background_deliveries", ())[0], 0)
        self.assertEqual(self.sent, [])
        replay = (await self.contact(app)).unwrap().task
        self.assertEqual(replay.task_id, task.task_id)
        self.assertEqual(len(self.called), 1)

    async def test_low_confidence_send_is_saved_as_skip_without_delivery(self):
        app = await self.enabled()
        self.settings(app, {"silence_min_confidence": 0.8}).unwrap()
        async def uncertain_send(envelope):
            return answered('{"decision":"send","text":"想说一句","decision_confidence":0.62}')
        self.model_behavior = uncertain_send
        task = (await self.contact(app)).unwrap().task
        record = json.loads(self.runtime.read_one(
            "SELECT record_json, body FROM proactive_contacts WHERE task_id = ?", (task.task_id,))["record_json"])
        self.assertEqual(record["decision"], "skip")
        self.assertEqual(record["decision_confidence"], 0.62)
        self.assertEqual(record["silence_reason"], "below_confidence_threshold")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM background_deliveries", ())[0], 0)
        self.assertEqual(self.sent, [])

    def test_contact_output_rejects_invalid_decision_confidence(self):
        for confidence in ("0.8", -0.01, 1.01):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    contact_output(json.dumps({
                        "decision": "send", "text": "正文", "decision_confidence": confidence
                    }))

    async def test_replay_keeps_original_and_changed_opportunity_inputs_are_rejected(self):
        app = await self.enabled()
        opportunity = self.opportunity()
        intent = self.intent(opportunity)
        task = (await self.contact(app, opportunity, (intent,))).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual((await self.contact(app, opportunity, (intent,))).unwrap().task.task_id, task.task_id)
        changed = replace(intent, thought=replace(intent.thought, summary="重写原机会"))
        self.assertEqual((await self.contact(app, opportunity, (changed,))).failure.code, "contact_request_conflict")
        self.assertEqual((len(self.called), len(self.sent)), (1, 1))

    async def test_committed_skip_survives_task_fencing_after_local_receipt(self):
        app = await self.enabled()
        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        def changed_after_commit():
            self.settings(app, {"note": "提交之后调整偏好"}).unwrap()
            app.notify()
        with patch.object(app.proactive, "notify", side_effect=changed_after_commit):
            task = (await self.contact(app)).unwrap().task
        self.assertNotEqual(task.state, "succeeded")
        self.assertTrue(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["skipped"])
        self.assertEqual(self.sent, [])

    async def test_single_eligible_thought_does_not_use_weight_or_turn_weight_into_probability(self):
        app = await self.enabled()
        self.settings(app, {"news.enabled": False, "news.weight": 1000000.0, "chat.weight": 0.000001}).unwrap()
        opportunity = self.opportunity()
        intents = (self.intent(opportunity, purpose="news", identifier="news"), self.intent(opportunity, identifier="chat"))
        task = (await self.contact(app, opportunity, intents)).unwrap().task
        record = json.loads(self.runtime.read_one("SELECT record_json FROM proactive_contacts WHERE task_id = ?", (task.task_id,))[0])
        self.assertEqual((record["thought_id"], record["feasible_count"], record["weight_used"]), ("chat", 1, False))
        await self.delivery_state(app, task.task_id, "delivered")

    async def test_future_expired_or_wrong_window_opportunities_do_not_generate(self):
        app = await self.enabled()
        opportunity = self.opportunity()
        for item in (replace(opportunity, opened_at=NOW + timedelta(seconds=1)),
                     replace(opportunity, opened_at=NOW - timedelta(minutes=1), expires_at=NOW),
                     replace(opportunity, scope=replace(SCOPE, session_id="another"))):
            self.assertFalse((await self.contact(app, item)).is_success)
        self.assertEqual(self.called, [])

    async def test_source_read_grant_and_actual_audience_remain_required(self):
        app = await self.enabled()
        source = self.source(app, recipients=(self.core.subject,))
        opportunity = self.opportunity()
        self.assertEqual((await self.contact(app, opportunity, (self.intent(opportunity, sources=(source,)),))).failure.code,
                         "no_feasible_thought")
        visible = self.source(app, "visible")
        row = self.runtime.read_one("SELECT grant_id FROM identity_grants WHERE capability = 'text'", ())
        self.identity.revoke_grant(row[0], expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual((await self.contact(app, opportunity, (self.intent(opportunity, sources=(visible,)),))).failure.code,
                         "no_feasible_thought")
        self.assertEqual(self.called, [])

    async def test_changed_preferences_during_generation_discard_output_but_keep_usage(self):
        app = await self.enabled()
        async def change(envelope):
            self.settings(app, {"note": "现在只想安静一些"}).unwrap()
            return answered('{"decision":"send","text":"旧偏好下的文本"}')
        self.model_behavior = change
        task = (await self.contact(app)).unwrap().task
        self.assertNotEqual(task.state, "succeeded")
        row = self.runtime.read_one("SELECT state, actual_tokens, actual_cost FROM model_calls", ())
        self.assertEqual(row["state"], "discarded")
        self.assertEqual((row["actual_tokens"], row["actual_cost"]), (15, 40))
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM model_call_accounts", ())[0] > 0, True)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM proactive_contacts", ())[0], 0)
        self.assertEqual(self.sent, [])

    async def test_revoked_source_during_generation_discards_old_draft(self):
        app = await self.enabled()
        source = self.source(app)
        opportunity = self.opportunity()
        async def revoke(envelope):
            app.proactive.sources.revoke(source, expected_governance_revision=1, observed_at=NOW).unwrap()
            return answered('{"decision":"send","text":"已经失效的来源"}')
        self.model_behavior = revoke
        result = await self.contact(app, opportunity, (self.intent(opportunity, sources=(source,)),))
        self.assertNotEqual(result.unwrap().task.state, "succeeded")
        self.assertEqual(self.sent, [])

    async def test_quiet_hours_starting_during_generation_prevent_delivery(self):
        app = await self.enabled()
        self.settings(app, {"quiet_enabled": True, "quiet_timezone": "UTC", "quiet_start": "00:01", "quiet_end": "00:02"}).unwrap()
        async def advance(envelope):
            self.clock.advance(timedelta(minutes=1))
            return answered('{"decision":"send","text":"进入免打扰后的旧稿"}')
        self.model_behavior = advance
        result = await self.contact(app)
        self.assertNotEqual(result.unwrap().task.state, "succeeded")
        self.assertEqual(self.sent, [])

    async def test_pause_at_actual_sender_boundary_prevents_wire_effect(self):
        app = await self.enabled()
        wire_calls = []
        async def checked(envelope):
            self.settings(app, {"pause_until": (NOW + timedelta(hours=1)).isoformat()}).unwrap()
            try:
                envelope.before_dispatch()
            except TaskError:
                return self.receipt(envelope, "not_sent")
            wire_calls.append(envelope)
            return self.receipt(envelope)
        self.send_behavior = checked
        task = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, task.task_id, "failed")
        self.assertEqual(wire_calls, [])

    async def test_queued_draft_is_cancelled_on_pause_and_does_not_return_when_pause_expires(self):
        app = await self.enabled()
        opportunity = self.opportunity()
        intent = self.intent(opportunity)
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app, opportunity, (intent,))).unwrap().task
            self.settings(app, {"pause_until": (NOW + timedelta(seconds=1)).isoformat()}).unwrap()
        app.notify()
        await self.delivery_state(app, task.task_id, "cancelled")
        self.clock.advance(timedelta(seconds=2))
        app.notify()
        self.assertEqual((await self.contact(app, opportunity, (intent,))).unwrap().task.task_id, task.task_id)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.called), 1)

    async def test_unknown_is_not_replayed_after_restart_and_late_receipt_still_counts(self):
        app = await self.enabled()
        async def unknown(envelope):
            return self.receipt(envelope, "unknown")
        self.send_behavior = unknown
        opportunity = self.opportunity()
        task = (await self.contact(app, opportunity)).unwrap().task
        await self.delivery_state(app, task.task_id, "unknown")
        envelope = self.sent[0]
        await app.close()
        new = (await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)).application
        self.settings(new, {"enabled": False}).unwrap()
        self.assertEqual((await self.contact(new, opportunity)).unwrap().task.task_id, task.task_id)
        self.assertEqual((len(self.called), len(self.sent)), (1, 1))
        self.assertEqual(new.record_receipt(self.receipt(envelope)).unwrap(), "delivered")
        self.assertEqual(new.proactive.observe(self.contact_context(), task.task_id).unwrap()["delivery"], "delivered")

    async def test_queued_draft_survives_restart_without_another_model_call(self):
        app = await self.enabled()
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app)).unwrap().task
            original = app.proactive._delivery_row(task.task_id)["request_json"]
            await app.close()
        new = (await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)).application
        row = await self.delivery_state(new, task.task_id, "delivered")
        self.assertEqual(row["request_json"], original)
        self.assertEqual((len(self.called), len(self.sent)), (1, 1))

    async def test_restart_does_not_extend_draft_deadline(self):
        app = await self.enabled()
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app)).unwrap().task
            await app.close()
        self.clock.advance(timedelta(minutes=6))
        new = (await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)).application
        await self.delivery_state(new, task.task_id, "cancelled")
        self.assertEqual(self.sent, [])

    async def test_role_rebind_cancels_original_queued_contact(self):
        app = await self.enabled()
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app)).unwrap().task
            binding = self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap()
            self.identity.bind_role(scope=SCOPE, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "new-persona"),
                expected_revision=binding.revision, observed_at=NOW)
        app.notify()
        await self.delivery_state(app, task.task_id, "cancelled")
        self.assertEqual(self.sent, [])

    async def test_delivery_payload_or_logical_key_cannot_be_replaced(self):
        app = await self.enabled()
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app)).unwrap().task
            request = DeliveryRequest.restore(app.proactive._delivery_row(task.task_id)["request_json"])
            for forged in (replace(request, payload_hash="other"), replace(request, logical_key="another"),
                           replace(request, deadline_at=NOW + timedelta(hours=1))):
                self.assertFalse(app.outbound.queue(forged).is_success)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM background_deliveries", ())[0], 1)

    async def test_explicit_cancellation_stops_queued_delivery_and_observation_is_authorized(self):
        app = await self.enabled()
        context = self.contact_context()
        with patch.object(app.background, "advance", return_value=False):
            task = (await self.contact(app)).unwrap().task
            result = app.proactive.cancel(context, task.task_id, expected_revision=task.revision).unwrap()
            self.assertEqual(result["delivery"], "cancelled")
        self.assertFalse(app.proactive.observe(replace(context, actor=self.core), task.task_id).is_success)
        self.assertEqual(self.sent, [])

    async def test_pause_does_not_suppress_previously_accepted_agenda_reminder(self):
        app = await self.enabled()
        self.settings(app, {"pause_until": (NOW + timedelta(hours=1)).isoformat(), "reminder.enabled": False}).unwrap()
        context = self.contact_context()
        app.agenda.create_reminder(self.important, target=AgendaTarget(SCOPE, ROLE, self.important.subject),
            reminder_id="promised", message="按原约定提醒喝水", schedule=Schedule(NOW, "UTC"),
            operation=self.operation(SCOPE, owner="agenda"), expected_role_revision=context.role_binding.revision,
            observed_at=NOW).unwrap()
        app.notify()
        await self.until(lambda: len(self.sent) == 1)
        self.assertEqual(self.sent[0].text, "按原约定提醒喝水")
        self.assertEqual(self.called, [])

    async def test_invalid_model_contract_keeps_usage_and_cannot_be_sent(self):
        app = await self.enabled()
        async def invalid(envelope):
            return answered('{"decision":"send","text":""}')
        self.model_behavior = invalid
        result = await self.contact(app)
        self.assertNotEqual(result.unwrap().task.state, "succeeded")
        self.assertEqual(self.runtime.read_one("SELECT state FROM model_calls", ())[0], "discarded")
        self.assertEqual(self.sent, [])

    async def test_shutdown_waits_for_stubborn_model_and_discards_late_output(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        async def stubborn(envelope):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
            return answered('{"decision":"send","text":"停机之后的旧结果"}')
        self.model_behavior = stubborn
        app = await self.enabled(owns_runtime=True)
        invocation = asyncio.create_task(self.contact(app))
        await asyncio.wait_for(entered.wait(), 2)
        report = await app.close(grace_seconds=0)
        self.assertEqual((report.state, report.storage_closed), ("draining", False))
        self.assertTrue(report.pending_handles)
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)
        await self.until(lambda: not app.active_handles)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.runtime.read_one("SELECT state FROM model_calls", ())[0], "discarded")
        self.assertTrue((await app.close(grace_seconds=0)).storage_closed)

    async def test_delivery_capacity_failure_rolls_back_draft_and_local_operation_together(self):
        app = await self.enabled()
        async def full(envelope):
            return answered('{"decision":"send","text":"准备好的文本"}')
        self.model_behavior = full
        from companion_v2.foundation.outcome import Outcome
        with patch.object(app.outbound, "queue", return_value=Outcome.failed("task_queue_full", "no delivery capacity")):
            task = (await self.contact(app)).unwrap().task
        self.assertNotEqual(task.state, "succeeded")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM proactive_contacts", ())[0], 0)
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM operations WHERE operation_id LIKE 'save-contact-%'", ())[0], 0)
        self.assertEqual(self.runtime.read_one("SELECT state FROM model_calls", ())[0], "discarded")

    async def test_exhausted_budget_does_not_dispatch_a_model_or_sender(self):
        app = await self.enabled(budget=BudgetPolicy(*(Amount(0, 0) for _ in range(5))))
        task = (await self.contact(app)).unwrap().task
        self.assertNotEqual(task.state, "succeeded")
        self.assertEqual((self.called, self.sent), ([], []))

    async def test_accepted_receipt_is_not_reported_as_delivered(self):
        app = await self.enabled()
        async def accepted(envelope):
            return self.receipt(envelope, "accepted")
        self.send_behavior = accepted
        task = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, task.task_id, "accepted")
        self.assertEqual(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["delivery"], "accepted")
        app.record_receipt(self.receipt(self.sent[0])).unwrap()
        self.assertEqual(app.proactive.observe(self.contact_context(), task.task_id).unwrap()["delivery"], "delivered")

    async def test_temporary_pause_expiry_allows_a_new_opportunity_without_rewriting_settings(self):
        app = await self.enabled()
        self.settings(app, {"pause_until": (NOW + timedelta(seconds=1)).isoformat()}).unwrap()
        self.assertEqual((await self.contact(app)).failure.code, "no_feasible_thought")
        self.clock.advance(timedelta(seconds=1))
        task = (await self.contact(app, self.opportunity("after-pause"))).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual(len(self.called), 1)
