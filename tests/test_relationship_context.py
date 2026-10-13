from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import unittest

from companion_v2.conversation.foreground import ClaimKind, DraftClaim, ModelDraft
from companion_v2.conversation.messages import ConversationMessages
from companion_v2.conversation.relationship_context import (
    MAX_MEMORIES, MAX_PAYLOAD_CHARS, RELATIONSHIP_INSTRUCTION, RelationshipContext,
)
from companion_v2.execution.models import Lane, TaskError
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.relationships.models import (
    EmotionSubject, RelationshipMemory, RelationshipMemoryKind as Kind, RelationshipMemoryState as State,
)
from companion_v2.relationships.service import RelationshipMemoryService
from tests.test_conversation_messages import MessageFixture
from tests.test_host_application import HostFixture
from tests.test_management_access import INSTALLATION, NOW, SCOPE


def remember(service, context, source, *, identifier="memory-a", text="我们最近开始自在地聊生活小事。",
             state=State.ADOPTED, kind=Kind.CONTEXT, emotion_subject=None):
    memory = service.propose(RelationshipMemory(identifier,
        RoleOwnerRef(context.scope.installation_id, context.scope.bot_id, context.role_binding.role.subject_id),
        context.actor.subject, context.scope, kind, text, (source,), NOW, NOW,
        emotion_subject=emotion_subject), actor=context.actor).unwrap()
    for next_state in (State.REVIEWED, State.ADOPTED, State.RETRACTED):
        if memory.state is state:
            break
        memory = service.transition(memory.memory_id, actor=context.actor, scope=context.scope,
            expected_revision=memory.revision, operation_id=identifier + ":" + next_state.value,
            state=next_state).unwrap()
    return memory


class RelationshipContextTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        messages.relationship_context = RelationshipContext(RelationshipMemoryService(runtime, now=self.clock.now))
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.relationships = self.messages.relationship_context.service

    def remember(self, identifier="memory-a", *, context=None, source=None, **options):
        context = context or self.context
        source = source or self.event("evidence-" + identifier, context=context).source
        return remember(self.relationships, context, source, identifier=identifier, **options)

    def revise(self, memory):
        return self.relationships.revise(memory.memory_id, actor=self.context.actor, scope=self.context.scope,
            expected_revision=memory.revision, operation_id=memory.memory_id + ":revise",
            interpretation="更正：这是一次临时的感受。", sources=memory.sources).unwrap()

    def retract(self, memory):
        return self.relationships.transition(memory.memory_id, actor=self.context.actor, scope=self.context.scope,
            expected_revision=memory.revision, operation_id=memory.memory_id + ":retract",
            state=State.RETRACTED).unwrap()

    def restrict_relationship_access(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        for action in ("conversation.reply", "configuration.read"):
            self.grant(self.important, SCOPE, action)
        return self.grant(self.important, SCOPE, "relationship.memory.read")

    def snapshot(self, batch):
        return json.loads(self.messages.batch(batch)["contributions_json"])["relationship_context"]

    def materials(self, request=None):
        request = request or self.called[-1][1].original
        return [m for m in request.context.materials if m.owner == "relationship.memory"]

    async def discarded_during_generation(self, change):
        memory = self.remember()
        async def response(envelope):
            self.assertEqual(len(self.materials(envelope.original)), 1)
            change(memory)
            return ProviderResponse("generated", ModelDraft("旧关系背景下的草稿", ()), Amount(15, 40), "usage")
        self.responses["primary"] = response
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        task = (await self.runner().run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.sent, [])
        self.assertEqual((self.call_rows()[0]["state"], self.call_rows()[0]["actual_tokens"]), ("discarded", 15))

    async def test_adopted_context_and_emotion_are_subjective_material_not_fact_evidence(self):
        memory = self.remember()
        emotion = self.remember("memory-emotion", text="那次聊天让我感到轻松。", kind=Kind.EMOTION_EPISODE,
                                emotion_subject=EmotionSubject.ROLE)
        self.remember("only-proposed", state=State.PROPOSED)
        self.remember("only-reviewed", state=State.REVIEWED)
        self.remember("already-retracted", state=State.RETRACTED)
        event = self.event()
        batch = await self.generate(event)
        request = self.called[0][1].original
        self.assertEqual(request.role_instruction, "Original role prompt")
        self.assertEqual(request.role_binding, self.context.role_binding)
        self.assertIn(RELATIONSHIP_INSTRUCTION, request.instruction)
        self.assertEqual([m.purpose for m in self.materials()], ["relationship_context", "relationship_emotion_episode"])
        self.assertEqual([json.loads(m.payload)["interpretation"] for m in self.materials()],
                         [memory.interpretation, emotion.interpretation])
        self.assertEqual(json.loads(self.materials()[1].payload)["emotion_subject"], "role")
        self.assertEqual(request.context.evidence_sources, (event.source,))
        self.assertTrue(all(m.source is None for m in self.materials()))
        snapshot = self.snapshot(batch)
        self.assertEqual(snapshot["references"], [{"memory_id": m.memory_id, "revision": m.revision}
                                                  for m in (memory, emotion)])
        self.assertNotIn(memory.interpretation, self.messages.batch(batch)["contributions_json"])
        self.assertNotIn(memory.interpretation, json.dumps(self.messages.observe(self.context, batch).unwrap(), ensure_ascii=False))

    async def test_relationship_provenance_does_not_ground_an_observed_claim(self):
        memory = self.remember()
        self.responses["primary"] = ProviderResponse("generated", ModelDraft("你一直都这样。", (
            DraftClaim("claim", ClaimKind.OBSERVED, "你一直都这样。", memory.sources[0]),)), Amount(15, 40), "usage")
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "failed")
        self.assertEqual(self.parts(batch), ())

    async def test_revision_during_generation_discards_draft_and_keeps_usage(self):
        await self.discarded_during_generation(self.revise)

    async def test_retraction_during_generation_discards_draft_and_keeps_usage(self):
        await self.discarded_during_generation(self.retract)

    async def test_source_revocation_after_queue_prevents_dispatch(self):
        memory = self.remember()
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.messages.sources.revoke(memory.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.history(), [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "source_revoked")

    async def test_source_expiry_after_queue_prevents_dispatch(self):
        self.remember(source=self.event("short-memory", expires_at=NOW + timedelta(seconds=1)).source)
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.clock.advance(timedelta(seconds=2))
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "source_expired")

    async def test_read_permission_revocation_after_queue_prevents_dispatch(self):
        self.remember()
        grant = self.restrict_relationship_access()
        batch = await self.generate()
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code, "authorization_revoked")

    async def test_retraction_between_parts_keeps_receipt_and_blocks_remaining_text(self):
        memory = self.remember()
        batch = await self.generate()
        await self.deliver_next(batch)
        original = self.history()[0]
        receipt = self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?", (original["part_id"],))
        self.retract(memory)
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "relationship_context_changed")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.parts(batch)[0]["state"], "delivered")
        history = self.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["part_id"], original["part_id"])
        self.assertEqual(history[0]["delivered_at"], original["delivered_at"])
        self.assertEqual(dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?",
                                                   (original["part_id"],))), dict(receipt))
        self.assertIsNone(history[0]["text"])
        self.assertFalse(history[0]["body_available"])

    async def test_source_unavailable_before_capture_is_optional(self):
        memory = self.remember()
        self.messages.sources.revoke(memory.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["reason"], "source_revoked")
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.called[0][1].original.context.unavailable[0].owner, "relationship.memory")
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)

    async def test_read_permission_unavailable_before_capture_does_not_block_chat(self):
        self.remember()
        grant = self.restrict_relationship_access()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["reason"], "authorization_revoked")
        self.assertEqual(self.materials(), [])
        self.assertNotIn(RELATIONSHIP_INSTRUCTION, self.called[0][1].original.instruction)
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)

    async def test_another_human_and_another_full_scope_do_not_supply_material(self):
        other_person = self.context_for(self.standard)
        for action in ("propose", "review", "adopt"):
            self.grant(self.standard, other_person.scope, "relationship.memory." + action)
        self.remember("other-person", context=other_person)
        other_scope = replace(SCOPE, native_scope_id="other", conversation_id="other", session_id="other")
        other = self.context_for(self.important, other_scope)
        self.remember("other-route", context=other)
        self.remember("other-source", source=self.event("cross-route", context=other).source)
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["state"], "ready")
        self.assertEqual(self.materials(), [])

    async def test_persona_switch_does_not_reuse_previous_personas_memory(self):
        self.remember()
        role = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-b")
        current = self.personas.binding("base")
        self.personas.set_binding(replace(current, role=role, revision=current.revision + 1),
                                  expected_revision=current.revision, observed_at=NOW)
        self.context = self.context_for(self.important)
        await self.generate()
        self.assertEqual(self.materials(), [])
        self.assertEqual(self.called[0][1].original.role_binding.role, role)

    def test_audience_expansion_cannot_consume_the_private_snapshot(self):
        self.remember()
        consumer = self.messages.relationship_context
        snapshot = consumer.capture(self.context, NOW)
        expanded = replace(self.context, audience=AudienceRef(SCOPE, (self.important.subject, self.standard.subject)))
        self.assertEqual(consumer.capture(expanded, NOW)["state"], "unavailable")
        with self.assertRaises(TaskError) as error:
            consumer.contributions(snapshot, expanded, NOW)
        self.assertEqual(error.exception.code, "relationship_context_invalid")

    async def test_count_limit_and_unselected_change_preserve_original_selection(self):
        memories = [self.remember(f"memory-{i:02}") for i in range(MAX_MEMORIES + 1)]
        batch = self.accept()
        sealed = self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        original = self.snapshot(batch)
        self.assertEqual(len(original["references"]), MAX_MEMORIES)
        self.assertTrue(original["truncated"])
        self.revise(memories[-1])
        self.remember("000-added-later")
        self.assertEqual(self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap().task_id, sealed.task_id)
        self.assertEqual(self.snapshot(batch), original)
        self.assertEqual((await self.runner().run_once(Lane.FOREGROUND)).unwrap().task.state, "succeeded")
        self.assertEqual(len(self.materials()), MAX_MEMORIES)
        await self.deliver_next(batch)

    async def test_oversized_interpretation_is_omitted_without_cutting_other_text(self):
        self.remember("a-too-long", text="长" * MAX_PAYLOAD_CHARS)
        selected = self.remember("b-fits", text="语义完整的关系解释。" * 200)
        self.remember("c-over-total", text="另" * 6000)
        batch = await self.generate()
        self.assertEqual(self.snapshot(batch)["references"], [{"memory_id": selected.memory_id, "revision": selected.revision}])
        self.assertTrue(self.snapshot(batch)["truncated"])
        self.assertEqual(json.loads(self.materials()[0].payload)["interpretation"], selected.interpretation)
        self.assertLessEqual(sum(len(m.payload) for m in self.materials()), MAX_PAYLOAD_CHARS)

    async def test_reopen_reconstructs_original_references_and_checks_later_correction(self):
        memory = self.remember()
        batch = await self.generate()
        self.remember("000-new-memory")
        _, messages, delivery = self.components(self.open_runtime())
        request = messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual([json.loads(m.payload)["interpretation"] for m in self.materials(request)], [memory.interpretation])
        self.revise(memory)
        self.assertEqual(delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "relationship_context_changed")
        self.assertEqual(self.sent, [])

    async def test_missing_owner_fails_closed_for_a_snapshot_with_references(self):
        self.remember()
        batch = await self.generate()
        messages = ConversationMessages(self.tasks)
        with self.assertRaises(TaskError) as error:
            messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual(error.exception.code, "relationship_context_unavailable")

    async def test_legacy_batch_without_snapshot_is_not_enriched_after_sealing(self):
        consumer = self.messages.relationship_context
        self.messages.relationship_context = None
        batch = await self.generate()
        self.remember()
        self.messages.relationship_context = consumer
        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertEqual(self.materials(request), [])
        await self.deliver_next(batch)

    async def test_corrupt_snapshot_is_rejected_instead_of_losing_its_dependencies(self):
        self.remember()
        batch = await self.generate()
        row = self.messages.batch(batch)
        saved = json.loads(row["contributions_json"])
        snapshot = saved["relationship_context"]
        for invalid in (None, {**snapshot, "context_key": "other"},
                        {**snapshot, "references": snapshot["references"] * 2},
                        {**snapshot, "references": [{"memory_id": "memory-a", "revision": True}]}):
            with self.subTest(snapshot=invalid):
                changed = dict(row)
                changed["contributions_json"] = json.dumps({**saved, "relationship_context": invalid})
                with self.assertRaises(TaskError) as error:
                    self.messages._request(changed, self.context, NOW)
                self.assertEqual(error.exception.code, "relationship_context_invalid")


class RelationshipContextHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_host_automatically_supplies_adopted_relationship_material(self):
        host = await self.start()
        app = host.application
        batch = host.receive(self.event()).unwrap()
        context = self.context(app, batch)
        source = app.messages._request(app.messages.batch(batch), context, NOW).context.evidence_sources[0]
        memory = remember(app.relationship_memories, context, source)
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        original = self.called[0].original
        self.assertEqual([json.loads(m.payload)["interpretation"] for m in original.context.materials
                          if m.owner == "relationship.memory"], [memory.interpretation])
        self.assertEqual(original.role_instruction, "原角色人格提示")
        self.assertEqual([e.text for e in self.sent], ["第一段", "第二段"])
        self.assertEqual(len(app.messages.history(context).unwrap()["items"]), 2)


if __name__ == "__main__":
    unittest.main()
