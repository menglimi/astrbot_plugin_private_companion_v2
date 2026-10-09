"""Explicit private statements may seed a purpose candidate; the contact model decides to skip or send."""

import json
import unittest
from datetime import timedelta

from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.storage.repositories import OperationRepository
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_role_tool_loop import answered


class RelationshipContactEventTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_explicit_feeling_creates_care_contact_from_original_private_turn(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True, "automatic_enabled": True,
                            "idle_seconds": 60, "chat.enabled": False}).unwrap()
        batch = host.receive(self.event(text="我最近很累，今天有点难过。", prompt="原角色人格提示")).unwrap()
        await self.done(app, batch)

        self.advance(app, 60)
        row = app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?""",
            (self.contact_context().scope.key,))
        plan = app.contact_schedule._plan(row, self.clock.now())
        self.assertIsNotNone(plan)
        await app.contact_schedule._run(plan)
        await self.automatic_delivery(app)

        contact = self.contacts(app)[0]
        record = json.loads(contact["record_json"])
        self.assertEqual(record["purpose"], "care")
        materials = self.contact_calls()[0].original.context.materials
        self.assertTrue(any(item.purpose == "contact_evidence" and "很累" in item.payload for item in materials))
        status = app.proactive.observe(self.context(app, batch), contact["task_id"]).unwrap()
        self.assertEqual(status["delivery"], "delivered")

    async def _assert_explicit_relationship_contact(self, text, purpose):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        app.contact_schedule.advance = lambda: None
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 60,
                            "chat.enabled": False}).unwrap()
        batch = host.receive(self.event("relationship-" + purpose, text=text)).unwrap()
        await self.done(app, batch)
        self.advance(app, 60)
        row = app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?""",
            (self.contact_context().scope.key,))
        plan = app.contact_schedule._plan(row, self.clock.now())
        self.assertIsNotNone(plan)
        self.assertEqual([intent.purpose for intent in plan[2]], [purpose])
        await app.contact_schedule._run(plan)
        await self.automatic_delivery(app)

        contact = self.contacts(app)[0]
        self.assertEqual(json.loads(contact["record_json"])["purpose"], purpose)
        evidence = [item.payload for item in self.contact_calls()[-1].original.context.materials
                    if item.purpose == "contact_evidence"]
        self.assertTrue(evidence)
        self.assertTrue(any(text_part in evidence[0] for text_part in text.split()), evidence[0])
        self.assertEqual(app.proactive.observe(self.context(app, batch), contact["task_id"])
                         .unwrap()["delivery"], "delivered")

    async def test_explicit_affection_reaches_the_contact_model_and_delivery(self):
        await self._assert_explicit_relationship_contact("我今天有点想你。", "affection")

    async def test_explicit_play_reaches_the_contact_model_and_delivery(self):
        await self._assert_explicit_relationship_contact("今天一起玩游戏吧。", "play")

    async def test_explicit_repair_reaches_the_contact_model_and_delivery(self):
        await self._assert_explicit_relationship_contact("你刚才那句话让我不舒服。", "repair")

    async def test_explicit_invitation_reaches_the_contact_model_and_delivery(self):
        await self._assert_explicit_relationship_contact("下次一起去看电影吧。", "invitation")

    async def test_common_interest_without_an_invitation_does_not_create_an_invitation_contact(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        app.contact_schedule.advance = lambda: None
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 60,
                            "chat.enabled": False}).unwrap()
        batch = host.receive(self.event("shared-interest", text="我喜欢看电影，最近看了三部。")).unwrap()
        await self.done(app, batch)
        self.advance(app, 60)
        row = app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""", (self.contact_context().scope.key,))
        self.assertIsNone(app.contact_schedule._plan(row, self.clock.now()))
        self.assertEqual(self.contacts(app), ())

    async def test_explicitly_rejected_invitation_can_be_skipped_without_a_delivery(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        app.contact_schedule.advance = lambda: None
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 60,
                            "chat.enabled": False}).unwrap()

        async def skip(_envelope):
            return answered('{"decision":"skip","text":"","skip_reason":"respect_user_boundary"}')

        batch = host.receive(self.event("declined-invitation", text="我不想和你一起去看电影，别约我。")).unwrap()
        await self.done(app, batch)
        self.sent.clear()
        self.model_behavior = skip
        self.advance(app, 60)
        row = app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""", (self.contact_context().scope.key,))
        plan = app.contact_schedule._plan(row, self.clock.now())
        self.assertIsNotNone(plan)
        self.assertEqual([intent.purpose for intent in plan[2]], ["invitation"])
        result = await app.contact_schedule._run(plan)
        self.assertTrue(result.is_success)
        self.assertEqual(len(self.contacts(app)), 1, getattr(self, "contact_error", ""))
        record = json.loads(self.contacts(app)[0]["record_json"])
        self.assertEqual((record["purpose"], record["decision"]), ("invitation", "skip"))
        self.assertEqual(self.sent, [])


class FollowupContactEventTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def _start_with_delivered_contact(self):
        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        app.contact_schedule.advance = lambda: None
        self.settings(app, {"enabled": True, "automatic_enabled": True, "idle_seconds": 60,
            "chat.enabled": False, "contact_followup_after_minutes": 10,
            "contact_followup_cooldown_minutes": 30, "event_max_age_seconds": 3600,
            "max_contacts_24h": 20, "max_attempts_24h": 50}).unwrap()
        batch = host.receive(self.event("followup-origin", text="今天先读了几页小说。")).unwrap()
        await self.done(app, batch)
        context = self.context(app, batch)
        opportunity = self.opportunity("prior-care")
        source = self.source(app, "prior-care-source")
        task = (await self.contact(app, opportunity,
            (self.intent(opportunity, purpose="care", sources=(source,)),), context=context)).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        return host, app, context, batch

    def _latest_row(self, app, context):
        return app.runtime.read_one("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""",
            (context.scope.key,))

    async def test_followup_waits_then_composes_and_delivers_and_respects_cooldown(self):
        _host, app, context, batch = await self._start_with_delivered_contact()
        self.clock.advance(timedelta(minutes=9))
        self.assertIsNone(app.contact_schedule._plan(self._latest_row(app, context), self.clock.now()))

        self.clock.advance(timedelta(minutes=1))
        plan = app.contact_schedule._plan(self._latest_row(app, context), self.clock.now())
        self.assertIsNotNone(plan)
        self.assertIn("followup_event", plan[4])
        self.assertEqual([intent.purpose for intent in plan[2]], ["followup"])
        await app.contact_schedule._run(plan)
        await self.automatic_delivery(app, count=2)
        followup = self.contacts(app)[-1]
        self.assertEqual(json.loads(followup["record_json"])["purpose"], "followup")
        self.assertEqual(app.proactive.observe(context, followup["task_id"]).unwrap()["delivery"], "delivered")

    async def test_recent_followup_receipt_blocks_a_second_followup_during_cooldown(self):
        _host, app, context, _batch = await self._start_with_delivered_contact()
        self.clock.advance(timedelta(minutes=10))
        operation_id = "followup-cooldown-marker-operation"
        operation = OperationRepository(app.runtime).reserve(OperationRef(
            operation_id, "proactive.contact", context.scope, VersionRef(operation_id, 1), operation_id),
            parameter_hash="followup-cooldown-marker", observed_at=self.clock.now()).unwrap()
        with app.runtime.transaction() as connection:
            connection.execute("""INSERT INTO proactive_contacts(contact_id, task_id, origin_key, record_json, body,
                payload_hash, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("followup-cooldown-marker", "followup-cooldown-marker-task", context.key,
                 json.dumps({"purpose": "followup"}), "marker", "marker-hash",
                 operation.operation.operation_id, self.clock.now().isoformat()))

        self.clock.advance(timedelta(minutes=10))
        self.assertIsNone(app.contact_schedule._plan(self._latest_row(app, context), self.clock.now()))

    async def test_a_new_user_input_supersedes_an_unanswered_followup(self):
        host, app, context, _batch = await self._start_with_delivered_contact()
        self.clock.advance(timedelta(minutes=9))
        batch = host.receive(self.event("followup-new-input", text="我回来继续聊了。")).unwrap()
        await self.done(app, batch)
        self.clock.advance(timedelta(minutes=1))
        self.assertIsNone(app.contact_schedule._plan(self._latest_row(app, context), self.clock.now()))
        self.assertEqual(len(self.contacts(app)), 1)
