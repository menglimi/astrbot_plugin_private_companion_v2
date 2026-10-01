import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.foreground import BackgroundPromptTrigger
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_management_access import INSTALLATION, SCOPE
from tests.test_role_tool_loop import answered


class ContactSchedulingTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_unanswered_slowdown_applies_to_ordinary_check_in_and_new_input_resets_pause(self):
        host, _ = await self.scheduled(automatic=False)
        app = host.application
        self.advance(app, 1)
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        self.settings(app, {"automatic_enabled": True, "unanswered_pause_after": 1,
                            "dedup_enabled": False}).unwrap()
        self.advance(app, 140)
        app.contact_schedule.advance()
        self.assertEqual(len(self.contact_calls()), 1)
        batch = host.receive(self.event("returned")).unwrap()
        await self.done(app, batch)
        self.assertEqual(app.background_history.interaction(self.contact_context(), self.clock.now())[
            "contacts_since_last_input"], 0)
        self.advance(app, 60)
        await self.automatic_delivery(app, count=2)

    async def test_unanswered_slowdown_does_not_delay_a_date_event(self):
        host, _ = await self.scheduled(automatic=False)
        app = host.application
        self.advance(app, 1)
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        date = json.dumps([{"month": 9, "day": 21, "label": "纪念日"}], ensure_ascii=False)
        self.settings(app, {"automatic_enabled": True, "date_checkin_enabled": True,
                            "date_checkin_time": "08:01", "important_dates": date,
                            "unanswered_pause_after": 1, "chat.enabled": False}).unwrap()
        self.advance(app, 60)
        await self.automatic_delivery(app, count=2)
        self.assertEqual(json.loads(self.contacts(app)[-1]["record_json"])["purpose"], "greeting")

    async def test_wall_clock_opportunity_runs_without_a_manual_scan_or_wake(self):
        current = lambda: datetime.now(timezone.utc)
        self.receipt_now = current
        host = await self.start(self.host(now=current, policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 1, "interval_seconds": 60}).unwrap()
        batch = host.receive(self.event(at=current())).unwrap()
        await self.done(app, batch)
        await self.automatic_delivery(app)
        self.assertEqual(len(self.contact_calls()), 1)

    async def test_automatic_requires_its_own_opt_in_and_completed_idle_conversation(self):
        host, _ = await self.scheduled(automatic=False)
        app = host.application
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])
        self.settings(app, {"automatic_enabled": True}).unwrap()
        app.notify()
        await self.automatic_delivery(app)
        request = self.contact_calls()[0].original
        self.assertEqual(request.role_instruction, "原角色人格提示")
        evidence = [m.payload for m in request.context.materials if m.purpose == "contact_evidence"]
        self.assertEqual(evidence, ["输入 event-1"])
        self.assertEqual(self.contacts(app)[0]["origin_key"], self.contact_context().key)

    async def test_repeated_ticks_and_restart_do_not_repeat_current_opportunity(self):
        host, _ = await self.scheduled()
        app = host.application
        self.advance(app, 60)
        row = await self.automatic_delivery(app)
        for _ in range(3):
            app.contact_schedule.advance()
            await asyncio.sleep(0)
        await app.close()
        new = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        new.contact_schedule.advance()
        await asyncio.sleep(0.02)
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(new.background_history.recent(self.contact_context()).unwrap()[0]["text"], "刚想起上次的话题。")
        self.assertEqual(self.contacts(new)[0]["contact_id"], json.loads(row["request_json"])["source_ref"])

    async def test_restart_produces_only_current_slot_without_missed_backlog(self):
        host, _ = await self.scheduled()
        await host.application.close()
        self.clock.advance(timedelta(days=3, seconds=60))
        app = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        row = await self.automatic_delivery(app)
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(json.loads(row["request_json"])["not_before"], self.clock.now().isoformat(timespec="microseconds"))

    async def test_skip_is_durable_and_next_slot_can_make_a_new_decision(self):
        host, _ = await self.scheduled()
        app = host.application
        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        self.advance(app, 60)
        await self.until(lambda: len(self.contacts(app)) == 1)
        await self.until(lambda: not app.proactive.active_handles)
        app.contact_schedule.advance()
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(len(self.sent), 1)  # Foreground reply only.
        self.advance(app, 60)
        await self.until(lambda: len(self.contacts(app)) == 2)
        self.assertTrue(all(json.loads(row["record_json"])["decision"] == "skip" for row in self.contacts(app)))

    async def test_pause_quiet_and_purpose_preference_prevent_automatic_model_calls(self):
        host, _ = await self.scheduled()
        app = host.application
        self.settings(app, {"pause_until": (self.clock.now() + timedelta(minutes=2)).isoformat()}).unwrap()
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])
        self.settings(app, {"quiet_enabled": True, "quiet_timezone": "UTC", "quiet_start": "00:00", "quiet_end": "00:03"}).unwrap()
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])
        self.settings(app, {"chat.enabled": False}).unwrap()
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])
        self.settings(app, {"chat.enabled": True}).unwrap()
        app.notify()
        await self.automatic_delivery(app)

    async def test_revoked_input_or_role_rebind_cannot_generate_for_old_conversation(self):
        host, batch = await self.scheduled()
        app = host.application
        context = self.context(app, batch)
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        self.identity.bind_role(scope=SCOPE, role=SubjectRef(INSTALLATION, SubjectKind.BOT, "new-role"),
            expected_revision=binding.revision, observed_at=self.clock.now())
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])
        self.assertFalse(app.background_history.recent(context).is_success)

    async def test_withdrawn_origin_is_not_replaced_with_older_input(self):
        host, batch = await self.scheduled()
        app = host.application
        key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))[0]
        app.withdraw(self.context(app, batch), key).unwrap()
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])

    async def test_new_user_input_during_generation_discards_contact_and_keeps_usage(self):
        host, _ = await self.scheduled()
        app = host.application
        async def interrupt(envelope):
            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                host.receive(self.event("new-input")).unwrap()
                return answered('{"decision":"send","text":"已经过时的主动消息"}')
            return answered("接到新消息。")
        self.model_behavior = interrupt
        self.advance(app, 60)
        await self.until(lambda: len(self.contact_calls()) == 1)
        await self.until(lambda: not app.proactive.active_handles)
        self.assertEqual(self.contacts(app), ())
        self.assertFalse(any(e.part_id.startswith("outbound-") for e in self.sent))
        self.assertEqual(app.runtime.read_one("""SELECT c.state FROM model_calls c JOIN execution_tasks t ON t.task_id = c.task_id
            WHERE t.kind = 'proactive.compose'""", ())[0], "discarded")

    async def test_new_input_at_sender_boundary_prevents_the_old_automatic_wire_effect(self):
        host, _ = await self.scheduled()
        app = host.application
        wire = []
        async def checked(envelope):
            if envelope.part_id.startswith("outbound-"):
                host.receive(self.event("arrived-before-send")).unwrap()
                try:
                    envelope.before_dispatch()
                except TaskError:
                    return self.receipt(envelope, "not_sent")
                wire.append(envelope)
            return self.receipt(envelope)
        self.send_behavior = checked
        self.advance(app, 60)
        await self.until(lambda: len(self.contacts(app)) == 1)
        await self.delivery_state(app, self.contacts(app)[0]["task_id"], "failed")
        self.assertEqual(wire, [])

    async def test_shutdown_keeps_storage_until_stubborn_automatic_model_stops(self):
        host, _ = await self.scheduled(owns_runtime=True)
        app = host.application
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        async def stubborn(envelope):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
            return answered('{"decision":"send","text":"停机后的结果"}')
        self.model_behavior = stubborn
        self.advance(app, 60)
        await asyncio.wait_for(entered.wait(), 3)
        report = await app.close(grace_seconds=0)
        self.assertEqual((report.state, report.storage_closed), ("draining", False))
        release.set()
        await self.until(lambda: not app.proactive.active_handles)
        self.assertTrue((await app.close(grace_seconds=0)).storage_closed)
        self.assertEqual(len(self.sent), 1)

    async def test_contact_capacity_is_reserved_until_pending_or_unknown_delivery_resolves(self):
        app = await self.enabled()
        self.settings(app, {"max_contacts_24h": 1}).unwrap()
        with patch.object(app.background, "advance", return_value=False):
            first = (await self.contact(app)).unwrap().task
            blocked = await self.contact(app, self.opportunity("second"))
            self.assertEqual(blocked.failure.code, "contact_delivery_budget")
            app.proactive.cancel(self.contact_context(), first.task_id, expected_revision=first.revision).unwrap()
        async def unknown(envelope):
            return self.receipt(envelope, "unknown")
        self.send_behavior = unknown
        second = (await self.contact(app, self.opportunity("second"))).unwrap().task
        await self.delivery_state(app, second.task_id, "unknown")
        self.clock.advance(timedelta(hours=25))
        self.assertEqual((await self.contact(app, self.opportunity("third"))).failure.code, "contact_delivery_budget")
        app.record_receipt(self.receipt(self.sent[0], "not_sent")).unwrap()
        self.send_behavior = None
        third = (await self.contact(app, self.opportunity("third"))).unwrap().task
        await self.delivery_state(app, third.task_id, "delivered")

    async def test_relationship_contact_allowance_spans_private_windows_and_unknown_receipts(self):
        app = await self.enabled()
        first_context = self.contact_context()
        second_context = self.other_window_context()
        from companion_v2.proactive.configuration import target_for
        relationship = target_for(first_context).chain()[2]
        self.settings(app, {"enabled": True, "max_relationship_contacts_24h": 1}, target=relationship).unwrap()

        async def unknown(envelope):
            return self.receipt(envelope, "unknown")
        self.send_behavior = unknown
        first = (await self.contact(app, context=first_context)).unwrap().task
        await self.delivery_state(app, first.task_id, "unknown")
        blocked = await self.contact(app, self.opportunity("other-window-contact", scope=second_context.scope),
                                     context=second_context)
        self.assertEqual(blocked.failure.code, "contact_relationship_delivery_budget")

        outbound = next(item for item in self.sent if item.part_id.startswith("outbound-"))
        app.record_receipt(self.receipt(outbound, "not_sent")).unwrap()
        self.send_behavior = None
        retried = (await self.contact(app, self.opportunity("other-window-contact", scope=second_context.scope),
                                      context=second_context)).unwrap().task
        await self.delivery_state(app, retried.task_id, "delivered")

    async def test_relationship_decision_allowance_spans_windows_but_is_separate_from_delivery_allowance(self):
        app = await self.enabled()
        first_context = self.contact_context()
        second_context = self.other_window_context()
        from companion_v2.proactive.configuration import target_for
        relationship = target_for(first_context).chain()[2]
        self.settings(app, {"enabled": True, "max_relationship_attempts_24h": 1}, target=relationship).unwrap()

        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        first = (await self.contact(app, context=first_context)).unwrap().task
        self.assertEqual(first.state, "succeeded")
        blocked = await self.contact(app, self.opportunity("other-window-attempt", scope=second_context.scope),
                                     context=second_context)
        self.assertEqual(blocked.failure.code, "contact_relationship_attempt_budget")
        self.assertEqual(self.sent, [])

    async def test_relationship_budget_fields_cannot_be_overridden_by_a_single_window(self):
        app = await self.enabled()
        from companion_v2.proactive.configuration import target_for
        window = target_for(self.contact_context())
        result = self.settings(app, {"max_relationship_contacts_24h": 1}, target=window)
        self.assertFalse(result.is_success)

    async def test_skips_consume_attempt_allowance_and_rolling_expiry_releases_it(self):
        app = await self.enabled()
        self.settings(app, {"max_attempts_24h": 1}).unwrap()
        async def skip(envelope):
            return answered('{"decision":"skip","text":""}')
        self.model_behavior = skip
        self.assertEqual((await self.contact(app)).unwrap().task.state, "succeeded")
        self.assertEqual((await self.contact(app, self.opportunity("next"))).failure.code, "contact_attempt_budget")
        self.clock.advance(timedelta(hours=24))
        self.assertEqual((await self.contact(app, self.opportunity("next"))).unwrap().task.state, "succeeded")
        self.assertEqual(self.sent, [])

    async def test_numeric_controls_inherit_and_zero_budget_blocks_without_model_usage(self):
        app = await self.enabled()
        from companion_v2.proactive.configuration import target_for
        relationship = target_for(self.contact_context()).chain()[2]
        self.settings(app, {"interval_seconds": 120, "max_contacts_24h": 0}, target=relationship).unwrap()
        self.assertEqual(self.preferences(app).values["interval_seconds"], 120)
        self.assertEqual((await self.contact(app)).failure.code, "contact_delivery_budget")
        for key, value in (("interval_seconds", 59), ("idle_seconds", -1), ("max_contacts_24h", True), ("max_attempts_24h", 1001)):
            self.assertFalse(self.settings(app, {key: value}).is_success)
        self.assertEqual(self.called, [])

    async def test_disabled_scan_page_does_not_starve_later_window_or_mix_its_persona(self):
        from companion_v2.proactive.configuration import target_for
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        for index in range(17):
            scope = replace(SCOPE, native_scope_id="window-" + str(index), conversation_id="conversation-" + str(index), session_id=str(index))
            self.grant(self.important, scope, "text")
            batch = host.receive(self.event(str(index), scope=scope, prompt="角色 " + str(index))).unwrap()
            await self.done(app, batch)
        context = self.context(app, batch)
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 60, "interval_seconds": 60},
                      target=target_for(context)).unwrap()
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.assertEqual(len(self.contact_calls()), 1)
        self.assertEqual(self.contact_calls()[0].original.role_instruction, "角色 16")
        self.assertEqual(self.sent[-1].context.scope, scope)

    async def test_busy_lane_discards_unstarted_contact_without_crashing_or_replaying(self):
        app = await self.enabled()
        entered, release = asyncio.Event(), asyncio.Event()
        self.addCleanup(release.set)
        async def held(envelope):
            entered.set()
            await release.wait()
            return answered('{"decision":"send","text":"第一个机会"}')
        self.model_behavior = held
        first = asyncio.create_task(self.contact(app))
        await asyncio.wait_for(entered.wait(), 3)
        second = (await self.contact(app, self.opportunity("busy"))).unwrap().task
        self.assertEqual(second.state, "cancelled")
        self.assertEqual(len(self.called), 1)
        release.set()
        task = (await first).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        self.assertEqual((await self.contact(app, self.opportunity("busy"))).unwrap().task.task_id, second.task_id)
        self.assertEqual(len(self.called), 1)

    async def test_known_delivery_releases_its_allowance_at_the_rolling_boundary(self):
        app = await self.enabled()
        self.settings(app, {"max_contacts_24h": 1}).unwrap()
        first = (await self.contact(app)).unwrap().task
        await self.delivery_state(app, first.task_id, "delivered")
        self.assertEqual((await self.contact(app, self.opportunity("later"))).failure.code, "contact_delivery_budget")
        self.clock.advance(timedelta(hours=24))
        later = (await self.contact(app, self.opportunity("later"))).unwrap().task
        await self.delivery_state(app, later.task_id, "delivered")
