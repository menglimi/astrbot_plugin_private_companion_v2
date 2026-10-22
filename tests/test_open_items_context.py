"""Open personal agenda items enter private replies through the existing agenda owner."""

import json
from datetime import timedelta
import unittest

from companion_v2.agenda.models import AgendaTarget
from companion_v2.agenda.service import AgendaService
from companion_v2.conversation.open_items_context import (MAX_ITEMS, ConversationOpenItems, INSTRUCTION,
                                                          OpenItemsReader)
from companion_v2.execution.models import Lane, TaskContext, TaskError
from companion_v2.foundation.refs import (AudienceRef, OperationRef, ScopeKind, ScopeRef,
                                           SubjectKind, SubjectRef, VersionRef)
from companion_v2.identity_policy.models import AuthorizationTier, RoleBinding
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered


class OpenItemsFixture(MessageFixture):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        agenda = AgendaService(runtime)
        reader = OpenItemsReader(agenda, tasks)
        messages.open_items_context = ConversationOpenItems(reader)
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.agenda = self.messages.open_items_context.reader.agenda

    def add_item(self, item_id="item-a", *, actor=None, owner=None, title="准备周末旅行", body="看看车票和天气",
                 purpose="open_loop"):
        actor = actor or self.important
        owner = owner or actor.subject
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        target = AgendaTarget(SCOPE, binding.role, owner)
        operation = OperationRef("create-" + item_id, "agenda", SCOPE,
                                 VersionRef("create-" + item_id, 1), "create-" + item_id)
        return self.agenda.create_memo(actor, target=target, memo_id=item_id, title=title, body=body,
            operation=operation, expected_role_revision=binding.revision, observed_at=self.clock.now(),
            purpose=purpose).unwrap()

    def change_item(self, item_id, *, action="edit", revision=1, actor=None, changes=None):
        actor = actor or self.important
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        target = AgendaTarget(SCOPE, binding.role, actor.subject)
        name = f"{action}-{item_id}-{revision}"
        operation = OperationRef(name, "agenda", SCOPE, VersionRef(name, 1), name)
        return self.agenda.change_memo(actor, target=target, memo_id=item_id, action=action,
            expected_revision=revision, expected_role_revision=binding.revision, operation=operation,
            observed_at=self.clock.now(), changes=changes).unwrap()

    def item_payloads(self, request=None):
        request = request or self.called[-1][1].original
        return [json.loads(item.payload) for item in request.context.materials
                if item.owner == "agenda.memo" and item.purpose == "participant_open_item"]


class OpenItemsContextTests(OpenItemsFixture, unittest.IsolatedAsyncioTestCase):
    async def test_owner_open_items_enter_reply_without_becoming_observed_evidence(self):
        self.add_item()
        self.add_item("other", title="处理保险报销", body="把票据放好")
        self.change_item("other", action="complete")
        batch = await self.generate()
        request = self.called[-1][1].original
        self.assertIn(INSTRUCTION, request.instruction)
        self.assertEqual([item["memo_id"] for item in self.item_payloads(request)], ["item-a"])
        self.assertEqual(self.agenda.repository.memo("item-a").context_count, 1)
        self.assertEqual(request.context.evidence_sources, (self.event().source,))
        saved = self.messages.batch(batch)["contributions_json"]
        self.assertNotIn("准备周末旅行", saved)
        self.assertNotIn("看看车票和天气", saved)

    async def test_edit_after_seal_discards_old_item_reference_before_model_call(self):
        self.add_item()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.change_item("item-a", changes={"body": "已经改成周日下午出发"})
        await self.runner().run_once(Lane.FOREGROUND)
        task = self.tasks.read(self.context, "generate-" + batch).unwrap()
        self.assertEqual(task.state, "failed")
        self.assertEqual(self.called, [])


    async def test_edit_during_generation_discards_draft_and_keeps_actual_usage(self):
        self.add_item()
        async def edit_during_generation(envelope):
            self.change_item("item-a", changes={"body": "最新安排已经改变"})
            from companion_v2.model_gateway.models import Amount, ProviderResponse
            from companion_v2.conversation.foreground import ModelDraft
            return ProviderResponse("generated", ModelDraft("沿用旧安排的回复", ()), Amount(15, 40), "usage")
        self.responses["primary"] = edit_during_generation
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        result = await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(result.unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.sent, [])
        self.assertEqual((self.call_rows()[0]["state"], self.call_rows()[0]["actual_tokens"]), ("discarded", 15))

    async def test_completed_after_first_part_blocks_later_delivery_and_keeps_receipt(self):
        self.add_item()
        batch = await self.generate()
        await self.deliver_next(batch)
        first = self.history()[0]
        self.change_item("item-a", action="complete")
        next_part = self.delivery.queue_next(self.context, batch, deadline_at=self.deadline)
        self.assertEqual(next_part.failure.code, "open_items_changed")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.history()[0]["part_id"], first["part_id"])

    async def test_other_person_items_and_group_material_are_not_injected(self):
        other = SubjectRef(INSTALLATION, SubjectKind.HUMAN, "another-user")
        self.add_item("other-owner", actor=self.core, owner=other, title="绝不能泄露", body="私人正文")
        batch = await self.generate()
        self.assertEqual(self.item_payloads(), [])
        group = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "group-a", "bot-a", "login-a",
                         "conversation-group", "session-group")
        group_context = TaskContext(self.important, RoleBinding(group, self.context.role_binding.role, 1),
                                    AudienceRef(group, (self.important.subject,)))
        snapshot = self.messages.open_items_context.capture(group_context, NOW)
        self.assertEqual(snapshot["state"], "unavailable")
        self.assertEqual(self.messages.open_items_context.contributions(snapshot, group_context, NOW)[0].state.value,
                         "unavailable")
        self.assertEqual(self.item_payloads(), [])

    async def test_revoked_feature_permission_blocks_a_sealed_item(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        for action in ("conversation.reply", "memo.list", "memo.create"):
            self.grant(self.important, SCOPE, action)
        read_grant = self.grant(self.important, SCOPE, "memo.read")
        self.add_item()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.identity.revoke_grant(read_grant.grant_id, expected_revision=self.identity.revision,
                                   revoked_at=self.clock.now())
        await self.runner().run_once(Lane.FOREGROUND)
        task = self.tasks.read(self.context, "generate-" + batch).unwrap()
        self.assertEqual(task.state, "failed")
        self.assertEqual(self.called, [])

    async def test_selection_keeps_whole_items_and_rejects_corrupted_reference_snapshot(self):
        self.add_item("a-large", title="长事项", body="甲" * 9000)
        for index in range(MAX_ITEMS + 1):
            self.add_item(f"b-{index}", title=f"事项 {index}", body="保留完整正文")
        consumer = self.messages.open_items_context
        snapshot = consumer.capture(self.context, self.clock.now())
        self.assertEqual(len(snapshot["references"]), MAX_ITEMS)
        self.assertTrue(snapshot["truncated"])
        payloads = [json.loads(item.payload) for item in consumer.contributions(
            snapshot, self.context, self.clock.now()) if item.purpose == "participant_open_item"]
        self.assertEqual(len(payloads), MAX_ITEMS)
        self.assertNotIn("a-large", [item["memo_id"] for item in payloads])
        with self.assertRaises(TaskError):
            consumer.reader.validate_snapshot({**snapshot, "references": [snapshot["references"][0]] * 2},
                                               self.context)

    async def test_context_exposure_has_a_persistent_cooldown_and_lifetime_cap(self):
        self.add_item()
        reader = self.messages.open_items_context.reader
        first = reader.capture(self.context, self.clock.now())
        self.assertEqual(len(first["references"]), 1)
        self.assertEqual(self.agenda.repository.memo("item-a").context_count, 0)
        with self.runtime.read_snapshot():
            materials = self.messages.open_items_context.contributions(first, self.context, self.clock.now())
        self.assertEqual(self.agenda.repository.memo("item-a").context_count, 0)
        self.assertEqual(self.messages.open_items_context.record_exposure(
            first, self.context, self.clock.now(), materials), frozenset({"item-a"}))
        self.assertEqual(self.agenda.repository.memo("item-a").context_count, 1)
        self.assertEqual(reader.capture(self.context, self.clock.now())["references"], [])
        for _ in range(2):
            self.clock.advance(timedelta(days=4))
            snapshot = reader.capture(self.context, self.clock.now())
            self.assertEqual(len(snapshot["references"]), 1)
            materials = self.messages.open_items_context.contributions(snapshot, self.context, self.clock.now())
            self.assertEqual(self.messages.open_items_context.record_exposure(
                snapshot, self.context, self.clock.now(), materials), frozenset({"item-a"}))
        self.clock.advance(timedelta(days=4))
        self.assertEqual(reader.capture(self.context, self.clock.now())["references"], [])

    async def test_exposure_cooldown_removes_stale_optional_material_from_request(self):
        self.add_item()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        claimed = self.agenda.repository.claim_open_loop_context(
            "item-a", at=self.clock.now(), cooldown=timedelta(days=3), max_count=3)
        self.assertTrue(claimed)
        self.clock.advance(timedelta(seconds=1))

        await self.runner().run_once(Lane.FOREGROUND)

        task = self.tasks.read(self.context, "generate-" + batch).unwrap()
        self.assertEqual(task.state, "succeeded")
        request = self.called[-1][1].original
        self.assertEqual(self.item_payloads(request), [])
        self.assertNotIn(INSTRUCTION, request.instruction)

    async def test_expired_open_loop_is_not_captured_or_injected(self):
        self.add_item()
        self.clock.advance(timedelta(days=31))
        snapshot = self.messages.open_items_context.capture(self.context, self.clock.now())
        self.assertEqual(snapshot["references"], [])
        self.assertEqual(self.messages.open_items_context.contributions(snapshot, self.context, self.clock.now()), ())

    async def test_ordinary_note_is_not_exposed_as_an_open_loop(self):
        self.add_item(purpose="note")
        snapshot = self.messages.open_items_context.capture(self.context, self.clock.now())
        self.assertEqual(snapshot["references"], [])

    async def test_recently_past_due_open_loop_is_marked_for_natural_post_event_care(self):
        from companion_v2.agenda.models import Schedule
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        target = AgendaTarget(SCOPE, binding.role, self.important.subject)
        operation = OperationRef("create-due", "agenda", SCOPE, VersionRef("create-due", 1), "create-due")
        due_time = self.clock.now() - timedelta(hours=2)
        self.agenda.create_memo(
            self.important, target=target, memo_id="due-item", title="下午面试", body="两点半产品岗面试",
            operation=operation, expected_role_revision=binding.revision, observed_at=self.clock.now(),
            purpose="open_loop", schedule=Schedule(due_time, "Asia/Shanghai"),
        ).unwrap()
        snapshot = self.messages.open_items_context.capture(self.context, self.clock.now())
        payloads = [json.loads(item.payload) for item in self.messages.open_items_context.contributions(
            snapshot, self.context, self.clock.now()) if item.purpose == "participant_open_item"]
        self.assertEqual(len(payloads), 1)
        self.assertTrue(payloads[0].get("just_past_due"))
        # Replay later with advanced `at` preserves the exact sealed payload
        later_payloads = [json.loads(item.payload) for item in self.messages.open_items_context.contributions(
            snapshot, self.context, self.clock.now() + timedelta(days=3)) if item.purpose == "participant_open_item"]
        self.assertEqual(payloads, later_payloads)


class OpenItemsHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_composition_root_injects_open_items_through_the_ordinary_host_reply(self):
        host = await self.start()
        app = host.application
        binding = self.identity.resolve_role(SCOPE, observed_at=self.clock.now()).unwrap()
        context = TaskContext(self.important, binding, AudienceRef(SCOPE, (self.important.subject,)))
        identifier = "host-open-item"
        operation = OperationRef("host-open-item-operation", "agenda", SCOPE,
                                 VersionRef("host-open-item-operation", 1), "host-open-item-operation")
        target = AgendaTarget(SCOPE, binding.role, self.important.subject)
        app.agenda.create_memo(self.important, target=target, memo_id=identifier, title="周末整理花园",
            body="先给薄荷换个花盆", operation=operation, expected_role_revision=binding.revision,
            observed_at=self.clock.now(), purpose="open_loop").unwrap()

        async def model(envelope):
            self.called.append(envelope)
            return answered("要不要周末继续整理花园？")

        self.model_behavior = model
        batch = host.receive(self.event("open-item-reply")).unwrap()
        self.advance(app)
        result = await self.done(app, batch)
        self.assertEqual(result["state"], "complete")
        original = next(e.original for e in self.called if e.original.output_format == "conversation")
        found = [json.loads(m.payload) for m in original.context.materials
                 if m.owner == "agenda.memo" and m.purpose == "participant_open_item"]
        self.assertEqual(found[0]["memo_id"], identifier)
        self.assertIn(INSTRUCTION, original.instruction)
        self.assertEqual([e.text for e in self.sent], ["要不要周末继续整理花园？"])


if __name__ == "__main__":
    unittest.main()
