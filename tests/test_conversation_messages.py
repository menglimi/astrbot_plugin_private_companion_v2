from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.configuration.service import ConfigurationService
from companion_v2.conversation.delivery import DeliveryReceipt, LocalConversationDelivery, LocalSender
from companion_v2.conversation.foreground import ClaimKind, ContextContribution, ContributionState, DraftClaim, ModelDraft
from companion_v2.conversation.generation import LocalReplyGenerator
from companion_v2.conversation.messages import ConversationMessages, DELIVERY_KIND, REPLY_ACTION, REPLY_KIND
from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.diagnostics.models import CheckStatus, DiagnosticContext, DiagnosticQuery
from companion_v2.diagnostics.service import DiagnosticService
from companion_v2.execution.models import Lane, ProviderBinding, SideEffect, TaskDefinition, TaskRegistration, TaskError, digest
from companion_v2.execution.runner import LocalTaskRunner, TaskRun
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.personas import PersonaBinding, PersonaSelector, SelectorKind
from companion_v2.model_gateway.budget import BudgetLedger
from companion_v2.model_gateway.models import Amount, BudgetPolicy, ModelTaskProfile, ProviderResponse
from companion_v2.model_gateway.routing import ModelRouter, configuration_fields
from companion_v2.model_gateway.service import LocalModelGateway
from companion_v2.sources.models import SourceRecord
from tests.test_management_access import INSTALLATION, NOW, SCOPE
from tests.test_model_gateway import ModelFixture


class MessageFixture(ModelFixture):
    def setUp(self):
        super().setUp()
        self.sent = []
        self.send_behavior = None
        self.sender = LocalSender(ProviderBinding("message.delivery", "local", "1", "sender-1"), self.send)
        self.tasks, self.messages, self.delivery = self.components(self.runtime, takeover=True)
        profile = ModelTaskProfile(REPLY_KIND, Lane.FOREGROUND, "primary", "Reply supplement", "", 10)
        self.profiles += (profile,)
        self.registry = FieldRegistry(version="messages.v1", fields=tuple(self.registry.fields.values()) + configuration_fields((profile,)))
        self.configuration = ConfigurationService(self.runtime, self.registry)
        self.router = ModelRouter(self.configuration, self.profiles, self.providers)
        self.router.start(expected_generation=1)
        self.ledger = BudgetLedger(self.runtime, BudgetPolicy(*(Amount(1000, 10000) for _ in range(5))))
        self.gateway = LocalModelGateway(self.router, self.ledger, self.tasks)
        self.responses["primary"] = ProviderResponse("generated", ModelDraft("First part.\nSecond part.", ()), Amount(15, 40), "model-receipt")
        self.generator = LocalReplyGenerator(self.messages, self.gateway,
            segmentation=SegmentationPolicy(enabled=False), split=lambda text: tuple(text.splitlines(keepends=True)))
        self.deadline = NOW + timedelta(minutes=2)
        self.grant(self.important, SCOPE, "text")

    def components(self, runtime, *, takeover=False):
        owners = {}
        definitions = (
            TaskRegistration(TaskDefinition(REPLY_KIND, "conversation", REPLY_ACTION, Lane.FOREGROUND, max_attempts=1),
                             lambda spec, at: owners["messages"].validate_generation(spec, at)),
            TaskRegistration(TaskDefinition(DELIVERY_KIND, "conversation.delivery", REPLY_ACTION, Lane.FOREGROUND,
                side_effect=SideEffect.MESSAGE_DELIVERY, binding=self.sender.binding, max_attempts=1),
                             lambda spec, at: owners["delivery"].validate(spec, at)),
        )
        tasks = self.supervisor(runtime, registrations=self.registrations + definitions)
        (tasks.start(expected_generation=1) if takeover else tasks.attach(expected_generation=2)).unwrap()
        owners["messages"] = ConversationMessages(tasks)
        owners["delivery"] = LocalConversationDelivery(owners["messages"], self.sender)
        return tasks, owners["messages"], owners["delivery"]

    def event(self, identifier="input-1", *, context=None, expires_at=None):
        context = context or self.context
        identifier_hash = digest([context.scope.key, identifier])
        reference = SourceRef("source-" + identifier_hash, "conversation", context.scope, VersionRef(identifier_hash, 1), NOW, expires_at)
        body = "private input " + identifier
        self.messages.sources.publish(SourceRecord(reference, context.audience, digest(body), body), observed_at=NOW).unwrap()
        return InboundConversationEvent(identifier, context.actor.principal, context.scope, reference, "text", digest(body), NOW)

    def accept(self, event=None, *, context=None, **kwargs):
        return self.messages.accept(context or self.context, event or self.event(),
                                    role_instruction="Original role prompt", **kwargs).unwrap()

    def runner(self, *, interval=0.005):
        async def noop(run):
            raise AssertionError("unrelated task must not execute")
        handlers = {kind: noop for kind in self.tasks.registrations}
        handlers.update({REPLY_KIND: self.generator.generate, DELIVERY_KIND: self.delivery.deliver})
        runner = LocalTaskRunner(self.tasks, handlers, check_interval=interval)
        self.addAsyncCleanup(runner.close)
        return runner

    async def generate(self, event=None, *, batch=None, context=None, contributions=()):
        context = context or self.context
        batch = batch or self.accept(event, context=context)
        self.messages.seal(context, batch, deadline_at=self.deadline, contributions=contributions).unwrap()
        result = (await self.runner().run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(result.state, "succeeded")
        return batch

    async def deliver_next(self, batch, **kwargs):
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline, **kwargs).unwrap()
        return (await self.runner().run_once(Lane.FOREGROUND)).unwrap().task

    def receipt(self, envelope, status="delivered", **changes):
        return replace(DeliveryReceipt(envelope.part_id, envelope.operation_id, envelope.context.key, envelope.payload_hash,
            envelope.sender, status, status + ":" + envelope.part_id,
            "local-message:" + envelope.part_id if status in ("delivered", "accepted") else None,
            self.clock.now() if status == "delivered" else None), **changes)

    async def send(self, envelope):
        self.sent.append(envelope)
        if self.send_behavior is not None:
            return await self.send_behavior(envelope)
        return self.receipt(envelope)

    def parts(self, batch):
        return self.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch,))

    def history(self):
        return self.messages.history(self.context).unwrap()["items"]


class ConversationMessageTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    async def test_reply_usage_cannot_discount_the_plugin_budget(self):
        self.ledger = BudgetLedger(self.runtime, BudgetPolicy(*(Amount(30, 1000) for _ in range(5))))
        self.gateway.ledger = self.ledger
        await self.generate()
        self.assertTrue(self.accounts())
        self.assertTrue(all(self.ledger.plugin_account_usage(row["account_key"])["spent_tokens"] == 0
                            for row in self.accounts()))
        run = self.model_run("plugin-call")
        await self.gateway.generate(run, self.request())

        with self.assertRaises(TaskError) as caught:
            self.ledger.reserve(run, call_id="plugin-over-budget", position=1,
                provider=self.providers[0].binding, amount=self.estimate)
        self.assertEqual(caught.exception.code, "model_budget_exhausted")
        self.assertEqual(len(self.call_rows()), 2)

    async def test_main_chain_reply_still_generates_when_plugin_budget_is_exhausted(self):
        self.ledger = BudgetLedger(self.runtime, BudgetPolicy(*(Amount(30, 1000) for _ in range(5))))
        self.gateway.ledger = self.ledger
        reply_response = self.responses["primary"]
        self.responses["primary"] = ProviderResponse("generated", ModelDraft("plugin work", ()),
                                                       Amount(30, 1000), "plugin-budget-receipt")
        await self.gateway.generate(self.model_run("plugin-budget-full"), self.request())
        account_keys = [row["account_key"] for row in self.accounts()]
        self.assertTrue(account_keys)
        self.assertTrue(all(self.ledger.plugin_account_usage(key)["spent_tokens"] == 30
                            for key in account_keys))

        self.responses["primary"] = reply_response
        await self.generate(self.event("after-plugin-budget"))

        self.assertEqual(len(self.called), 2)
        latest = self.runtime.read_one("""SELECT c.* FROM model_calls c
            JOIN execution_tasks t ON t.task_id = c.task_id
            WHERE t.kind = ? ORDER BY c.finished_at DESC LIMIT 1""", (REPLY_KIND,))
        self.assertEqual((latest["state"], latest["actual_tokens"]), ("generated", 15))
        self.assertTrue(all((row["held_tokens"], row["held_cost"]) == (0, 0) for row in self.accounts()))
        self.assertTrue(all(self.ledger.plugin_account_usage(key)["spent_tokens"] == 30
                            for key in account_keys))

    async def test_async_merge_preserves_role_and_governed_materials_without_waiting_for_maintenance(self):
        batch = self.accept()
        self.accept(self.event("input-2"), batch_id=batch)
        contribution = ContextContribution("slow", "memory", "maintenance", ContributionState.DEFERRED)
        await self.generate(batch=batch, contributions=(contribution,))
        request = self.called[0][1].original
        self.assertEqual(request.role_instruction, "Original role prompt")
        self.assertEqual(request.role_binding, self.context.role_binding)
        input_materials = [item for item in request.context.materials
                           if item.purpose == "current_source" or item.purpose.startswith("merged_input:")]
        self.assertEqual([item.payload for item in input_materials], ["private input input-1", "private input input-2"])
        calendar = next(item for item in request.context.materials if item.owner == "conversation.calendar")
        self.assertEqual(calendar.purpose, "local_calendar_context")
        self.assertIsNone(calendar.source)
        self.assertEqual(json.loads(calendar.payload)["timezone"], "Asia/Shanghai")
        self.assertEqual(json.loads(calendar.payload)["local_date"], "2026-09-21")
        self.assertIn("日历材料只表示按指定时区", request.instruction)
        self.assertEqual(request.context.deferred, (contribution,))
        self.assertEqual([p["state"] for p in self.parts(batch)], ["pending", "pending"])
        self.assertEqual(self.history(), [])
        stored = self.messages.batch(batch)
        self.assertNotIn("private input", stored["contributions_json"])
        self.assertNotIn("conversation.calendar", stored["contributions_json"])
        self.assertNotIn("2026-09-21", stored["contributions_json"])
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM operations", ())["n"], 0)

    async def test_generated_reply_log_preserves_the_final_segment_boundaries(self):
        with self.assertLogs("companion_v2.conversation.generation", level="INFO") as captured:
            batch = await self.generate()

        lines = [line for line in captured.output if "回复正文已通过校验" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("batch=" + batch, lines[0])
        self.assertIn("parts=2", lines[0])
        self.assertIn("分段正文=('First part.', 'Second part.')", lines[0])

    async def test_event_replay_and_withdrawal_tombstone_survive_reopen(self):
        event = self.event()
        batch = self.accept(event)
        self.assertEqual(self.accept(event), batch)
        changed = replace(event, input_hash="different")
        self.assertEqual(self.messages.accept(self.context, changed, role_instruction="Original role prompt").failure.code, "message_event_conflict")
        self.messages.withdraw(self.context, event.scoped_key).unwrap()
        _, other, _ = self.components(self.open_runtime())
        self.assertEqual(other.accept(self.context, event, role_instruction="Original role prompt").failure.code, "message_withdrawn")
        self.assertEqual(other.seal(self.context, batch, deadline_at=self.deadline).failure.code, "message_batch_empty")

    async def test_withdraw_before_seal_uses_remaining_inputs_in_original_order(self):
        event = self.event()
        batch = self.accept(event)
        self.accept(self.event("input-2"), batch_id=batch)
        self.messages.withdraw(self.context, event.scoped_key).unwrap()
        await self.generate(batch=batch)
        inputs = [m for m in self.called[0][1].original.context.materials
                  if m.purpose == "current_source" or m.purpose.startswith("merged_input:")]
        self.assertEqual([m.payload for m in inputs], ["private input input-2"])

    async def test_only_confirmed_parts_enter_paginated_history_and_delay_keeps_sequence(self):
        batch = await self.generate()
        self.assertEqual((await self.deliver_next(batch)).state, "succeeded")
        self.assertEqual([item["text"] for item in self.history()], ["First part."])
        self.assertIsNone(await self.deliver_next(batch, not_before=NOW + timedelta(seconds=3)))
        self.clock.advance(timedelta(seconds=3))
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "succeeded")
        self.assertEqual([item["text"] for item in self.history()], ["First part.", "Second part."])
        first = self.messages.history(self.context, limit=1).unwrap()
        second = self.messages.history(self.context, after=first["next_cursor"], limit=1).unwrap()
        self.assertEqual(second["items"][0]["sequence"], 2)
        self.assertIsNone(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap().task)
        self.assertEqual(len(self.sent), 2)

    async def test_accepted_needs_explicit_delivery_receipt_before_continuing(self):
        async def accepted(envelope):
            return self.receipt(envelope, "accepted")
        self.send_behavior = accepted
        batch = await self.generate()
        result = await self.deliver_next(batch)
        self.assertEqual(result.state, "uncertain")
        self.assertEqual(self.history(), [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "message_delivery_unresolved")
        receipt = self.receipt(self.sent[0])
        for _ in range(2):
            self.delivery.record_receipt(receipt).unwrap()
        self.delivery.reconcile_task(self.context, receipt.part_id).unwrap()
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.delivery.reconcile_task(self.context, receipt.part_id).unwrap().state, "succeeded")
        self.send_behavior = None
        await self.deliver_next(batch)
        self.assertEqual(len(self.history()), 2)

    async def test_sender_exception_never_resends_unknown_part(self):
        async def fail(envelope):
            raise RuntimeError("private sender failure")
        self.send_behavior = fail
        batch = await self.generate()
        result = await self.deliver_next(batch)
        self.assertEqual((result.state, self.parts(batch)[0]["state"]), ("uncertain", "unknown"))
        self.assertEqual(self.history(), [])
        self.assertIsNone((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task)
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(len(self.sent), 1)

    async def test_withdraw_during_generation_discards_draft_but_accounts_usage(self):
        event = self.event()
        batch = self.accept(event)
        async def withdraw(envelope):
            self.messages.withdraw(self.context, event.scoped_key).unwrap()
            return ProviderResponse("generated", ModelDraft("stale draft", ()), Amount(15, 40), "usage")
        self.responses["primary"] = withdraw
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual((self.call_rows()[0]["state"], self.call_rows()[0]["actual_tokens"]), ("discarded", 15))

    async def test_withdraw_between_parts_keeps_receipt_hides_body_and_leaves_other_batch_usable(self):
        event = self.event()
        batch = await self.generate(event)
        await self.deliver_next(batch)
        other = await self.generate(self.event("unrelated"))
        self.messages.withdraw(self.context, event.scoped_key).unwrap()
        self.assertEqual([p["state"] for p in self.parts(batch)], ["delivered", "cancelled"])
        self.assertIsNone(self.history()[0]["text"])
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        await self.deliver_next(other)
        self.assertEqual(self.history()[-1]["text"], "First part.")

    async def test_late_receipt_after_cancel_and_source_revocation_only_accounts_original_part(self):
        event = self.event()
        batch = await self.generate(event)
        async def cancelled(envelope):
            self.messages.cancel(self.context, batch).unwrap()
            self.messages.sources.revoke(event.source, expected_governance_revision=1, observed_at=NOW).unwrap()
            return self.receipt(envelope)
        self.send_behavior = cancelled
        await self.deliver_next(batch)
        self.assertEqual([p["state"] for p in self.parts(batch)], ["delivered", "cancelled"])
        self.assertEqual(len(self.history()), 1)
        self.assertFalse(self.history()[0]["body_available"])
        self.assertEqual(len(self.sent), 1)

    async def test_source_expiry_before_delivery_prevents_any_dispatch(self):
        batch = await self.generate(self.event(expires_at=NOW + timedelta(seconds=1)))
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.clock.advance(timedelta(seconds=2))
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.history(), [])

    async def test_receipt_target_provider_and_payload_are_exact_and_duplicates_cannot_change_outcome(self):
        batch = await self.generate()
        await self.deliver_next(batch)
        receipt = self.receipt(self.sent[0])
        for changed in (replace(receipt, origin_key="other-recipient"), replace(receipt, payload_hash="different"),
                        replace(receipt, sender=replace(receipt.sender, generation="replacement"))):
            self.assertEqual(self.delivery.record_receipt(changed).failure.code, "message_receipt_mismatch")
        self.assertEqual(self.delivery.record_receipt(replace(receipt, status="unknown", delivered_at=None)).failure.code,
                         "message_receipt_conflict")
        self.assertEqual(self.delivery.record_receipt(replace(receipt, receipt_ref="different", delivered_at=NOW + timedelta(seconds=1))).failure.code,
                         "message_receipt_time")
        self.assertEqual(len(self.history()), 1)

    async def test_cancel_pending_generation_and_redacted_projection(self):
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.messages.cancel(self.context, batch).unwrap()
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.called, [])
        projection = self.messages.observe(self.context, batch).unwrap()
        self.assertEqual(projection["sender"], "not_connected")
        for private in ("Original role prompt", "private input", "First part"):
            self.assertNotIn(private, json.dumps(projection))

    async def test_two_connections_admit_same_input_and_queue_one_original_part(self):
        event = self.event()
        _, other, delivery = self.components(self.open_runtime())
        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = tuple(pool.map(lambda service: service.accept(self.context, event,
                role_instruction="Original role prompt").unwrap(), (self.messages, other)))
        self.assertEqual(batches[0], batches[1])
        batch = await self.generate(batch=batches[0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            queued = tuple(pool.map(lambda service: service.queue_next(self.context, batch,
                deadline_at=self.deadline).unwrap().task, (self.delivery, delivery)))
        self.assertEqual(queued[0], queued[1])
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(len(self.sent), 1)

    async def test_actual_worker_cancel_marks_uncertainty_and_accepts_late_receipt_once(self):
        entered = asyncio.Event()
        async def hang(envelope):
            entered.set()
            await asyncio.Event().wait()
        self.send_behavior = hang
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        work = asyncio.create_task(self.runner().run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        self.messages.cancel(self.context, batch).unwrap()
        result = (await asyncio.wait_for(work, 2)).unwrap().task
        self.assertEqual(result.state, "uncertain")
        self.assertEqual([p["state"] for p in self.parts(batch)], ["unknown", "cancelled"])
        receipt = self.receipt(self.sent[0])
        self.delivery.record_receipt(receipt).unwrap()
        self.delivery.record_receipt(receipt).unwrap()
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.delivery.reconcile_task(self.context, receipt.part_id).unwrap().state, "succeeded")
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)

    async def test_restart_after_dispatch_recovers_unknown_without_replaying_and_preserves_history(self):
        batch = await self.generate()
        await self.deliver_next(batch)
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        claim = self.tasks.claim(Lane.FOREGROUND).unwrap().claim
        task = self.tasks.begin(claim).unwrap()
        envelope = self.delivery._dispatch(TaskRun(self.tasks, claim, task))
        tasks, messages, delivery = self.components(self.open_runtime())
        tasks.start(expected_generation=2).unwrap()
        self.assertEqual(delivery.recover_dispatches().unwrap(), (envelope.part_id,))
        self.assertEqual([p["state"] for p in self.parts(batch)], ["delivered", "unknown"])
        self.assertIsNone(tasks.claim(Lane.FOREGROUND).unwrap().claim)
        self.assertEqual(len(messages.history(self.context).unwrap()["items"]), 1)
        delivery.record_receipt(self.receipt(envelope)).unwrap()
        self.assertEqual(delivery.reconcile_task(self.context, envelope.part_id).failure.code, "task_worker_not_stopped")
        tasks.acknowledge_stopped(claim, proof_ref="local-process-exit-fixture").unwrap()
        delivery.reconcile_task(self.context, envelope.part_id).unwrap()
        self.assertEqual(len(messages.history(self.context).unwrap()["items"]), 2)
        self.assertEqual(len(self.sent), 1)

    async def test_queue_admission_failure_rolls_back_seal_and_part_assignment(self):
        batch = self.accept()
        failure = Outcome.failed("task_queue_full", "fixture capacity")
        with patch.object(self.tasks, "submit", return_value=failure):
            self.assertEqual(self.messages.seal(self.context, batch, deadline_at=self.deadline).failure.code, "task_queue_full")
        self.assertEqual(self.messages.batch(batch)["state"], "open")
        self.assertIsNone(self.messages.batch(batch)["generation_task_id"])
        await self.generate(batch=batch)
        with patch.object(self.tasks, "submit", return_value=failure):
            self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "task_queue_full")
        self.assertIsNone(self.parts(batch)[0]["task_id"])
        self.assertIsNone(self.parts(batch)[0]["sender_json"])
        await self.deliver_next(batch)
        self.assertEqual(len(self.history()), 1)

    async def test_manifest_transaction_failure_leaves_no_partial_reply_and_keeps_usage(self):
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        with self.runtime.transaction() as connection:
            connection.execute("""CREATE TEMP TRIGGER reject_second_part BEFORE INSERT ON conversation_parts
                WHEN NEW.sequence = 2 BEGIN SELECT RAISE(ABORT, 'fixture write failure'); END""")
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertIsNone(self.messages.batch(batch)["call_id"])
        self.assertEqual(self.call_rows()[0]["state"], "discarded")
        self.assertEqual(self.call_rows()[0]["actual_tokens"], 15)

    async def test_source_permission_revocation_hides_sent_body_and_stops_next_part(self):
        batch = await self.generate()
        await self.deliver_next(batch)
        self.identity.revoke_grant("grant-1", expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertIsNone(self.history()[0]["text"])
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(len(self.sent), 1)

    async def test_persona_switch_stops_original_send_but_author_can_still_withdraw_original_input(self):
        event = self.event()
        batch = await self.generate(event)
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        new_role = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")
        self.personas.set_binding(replace(self.personas.binding("base"), role=new_role, revision=2),
                                  expected_revision=1, observed_at=NOW)
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.messages.observe(self.context, batch).failure.code, "role_binding_changed")
        current = self.context_for(self.important)
        self.assertEqual(self.messages.withdraw(current, event.scoped_key).unwrap(), batch)
        self.assertEqual(self.messages.batch(batch)["state"], "invalidated")

    async def test_second_bot_same_native_event_cannot_merge_read_cancel_or_withdraw_first_bot_batch(self):
        batch = await self.generate()
        scope = replace(SCOPE, bot_id="bot-b", account_id="login-b")
        principal = replace(self.important.principal, bot_id="bot-b", account_id="login-b")
        self.identity.bind(binding_id="other-bot-binding", principal=principal, subject=self.important.subject,
                           valid_from=NOW, expected_revision=self.identity.revision)
        actor = self.identity.resolve_authenticated(principal, observed_at=NOW).unwrap()
        self.personas.set_binding(PersonaBinding("bot-b-persona", PersonaSelector(INSTALLATION, SelectorKind.BOT, bot_id="bot-b"),
                                  self.context.role_binding.role, 0, NOW, "fixture", "admin"), expected_revision=0, observed_at=NOW)
        context = self.context_for(actor, scope)
        self.grant(actor, scope, "text")
        event = self.event(context=context)
        other = self.accept(event, context=context)
        self.assertNotEqual(batch, other)
        for result in (self.messages.observe(context, batch), self.messages.cancel(context, batch),
                       self.messages.withdraw(context, self.event().scoped_key),
                       self.messages.accept(context, self.event("new", context=context), role_instruction="Original role prompt", batch_id=batch)):
            self.assertFalse(result.is_success)
        self.assertEqual(self.messages.history(context).unwrap()["items"], [])
        self.assertEqual(self.messages.batch(batch)["state"], "ready")

    async def test_declared_unsealed_evidence_discards_draft_without_another_model_call(self):
        event = self.event("not-part-of-turn")
        draft = ModelDraft("unsupported fact", (DraftClaim("fact", ClaimKind.OBSERVED, "claim", event.source),))
        self.responses["primary"] = ProviderResponse("generated", draft, Amount(15, 40), "usage")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.parts(batch), ())

    async def test_known_not_sent_is_not_archived_or_automatically_retried(self):
        async def not_sent(envelope):
            return self.receipt(envelope, "not_sent")
        self.send_behavior = not_sent
        batch = await self.generate()
        self.assertEqual((await self.deliver_next(batch)).state, "failed")
        self.assertEqual(self.parts(batch)[0]["state"], "failed")
        self.assertEqual(self.history(), [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "message_delivery_failed")
        self.assertIsNone((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task)

    async def test_deadline_during_send_cancels_worker_without_claiming_delivery(self):
        entered = asyncio.Event()
        async def hang(envelope):
            entered.set()
            await asyncio.Event().wait()
        self.send_behavior = hang
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        work = asyncio.create_task(self.runner().run_once(Lane.FOREGROUND))
        await asyncio.wait_for(entered.wait(), 1)
        self.clock.advance(timedelta(minutes=3))
        self.assertEqual((await asyncio.wait_for(work, 2)).unwrap().task.state, "uncertain")
        self.assertEqual(self.parts(batch)[0]["state"], "unknown")
        self.assertEqual(self.history(), [])
        self.assertEqual(len(self.sent), 1)

    async def test_rebound_account_cannot_use_or_withdraw_original_batch(self):
        event = self.event()
        batch = await self.generate(event)
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.identity.bind(binding_id="new-account-binding", principal=self.important.principal, subject=self.standard.subject,
                           valid_from=NOW, expected_revision=self.identity.revision)
        self.assertEqual(self.messages.withdraw(self.context, event.scoped_key).failure.code, "binding_rebound")
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertFalse(self.messages.history(self.context).is_success)

    async def test_ready_contribution_reloads_governed_body_and_stops_on_revocation(self):
        material = self.event("material")
        contribution = ContextContribution("current-material", "conversation", "background", ContributionState.READY,
                                          "stale caller copy", material.source, True)
        batch = await self.generate(contributions=(contribution,))
        background = next(item for item in self.called[0][1].original.context.materials
                          if item.owner == "conversation" and item.purpose == "background")
        self.assertEqual(background.payload, "private input material")
        self.assertNotIn("stale caller copy", self.messages.batch(batch)["contributions_json"])
        self.messages.sources.revoke(material.source, expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "source_revoked")

    async def test_generation_rechecks_persona_after_model_returns(self):
        async def change_role(envelope):
            binding = self.personas.binding("base")
            self.personas.set_binding(replace(binding, revision=2, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")),
                                      expected_revision=1, observed_at=NOW)
            return ProviderResponse("generated", ModelDraft("old persona reply", ()), Amount(15, 40), "usage")
        self.responses["primary"] = change_role
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.call_rows()[0]["state"], "discarded")

    async def test_original_task_diagnostics_show_partial_receipts_without_private_content(self):
        batch = await self.generate()
        await self.deliver_next(batch)
        async def accepted(envelope):
            return self.receipt(envelope, "accepted")
        self.send_behavior = accepted
        await self.deliver_next(batch)
        service = DiagnosticService(self.configuration, now=self.clock.now, tasks=self.tasks,
                                    models=self.gateway, messages=self.messages)
        context = DiagnosticContext(self.context.actor, self.context.role_binding, self.context.audience)
        report = service.inspect(context, DiagnosticQuery(execution=True,
            execution_task_id=self.messages.batch(batch)["generation_task_id"])).unwrap()
        check = report.results[0]
        details = json.loads(check.details_json)
        self.assertEqual(check.status, CheckStatus.UNKNOWN)
        self.assertEqual(details["sender"], "local_test_adapter")
        self.assertEqual(details["conversation"]["confirmed_parts"], 1)
        self.assertEqual(details["conversation"]["unresolved_parts"], 1)
        for private in ("First part", "Second part", "private input", "Original role prompt", "local-message:", "delivered:"):
            self.assertNotIn(private, check.details_json)


if __name__ == "__main__":
    unittest.main()
