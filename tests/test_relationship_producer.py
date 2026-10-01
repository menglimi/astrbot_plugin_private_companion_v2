"""Private role proposals use original sources and remain unadopted until human review."""

from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.relationship_context import RelationshipContext
from companion_v2.conversation.tool_loop import LocalRoleTools, ToolSource
from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.relationships.management import RelationshipMemoryManagement
from companion_v2.relationships.models import RelationshipMemoryState as State
from companion_v2.relationships.service import RelationshipMemoryService
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import ToolLoopFixture, answered, call, requested


class RelationshipProducerFixture(ToolLoopFixture):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        messages.relationship_context = RelationshipContext(RelationshipMemoryService(runtime, now=self.clock.now))
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.service = self.messages.relationship_context.service
        self.messages.tools = None
        self.tools = LocalRoleTools(self.messages, relationships=self.service)

    def propose(self, identifier="proposal", **changes):
        return call(identifier, "relationship.memory.propose", **(dict(kind="context",
            interpretation="这次认真听完彼此的顾虑，让我觉得交流比之前轻松一些。",
            evidence_handles=["relationship-input-1"]) | changes))

    def records(self):
        return self.service.for_relationship(actor=self.context.actor, scope=self.context.scope).unwrap()

    def answer_after(self, *calls):
        async def respond(envelope):
            return requested(*calls) if not envelope.tool_history else answered("已提交一份待审阅的提案。")
        self.responses["primary"] = respond


class RelationshipProducerTests(RelationshipProducerFixture, unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_submission_keeps_one_pending_record_and_original_receipt(self):
        async def respond(envelope):
            self.assertIn("relationship.memory.propose", {tool.action for tool in envelope.tools})
            offered = next(m for m in envelope.original.context.materials if m.purpose == "relationship_evidence_handles")
            self.assertEqual(json.loads(offered.payload)[0]["handle"], "relationship-input-1")
            return requested(self.propose()) if len(envelope.tool_history) < 2 else answered("已提交待审阅提案。")
        self.responses["primary"] = respond
        batch = await self.generate()
        record, = self.records()
        self.assertEqual((record.subject, record.state, record.revision), (self.context.actor.subject, State.PROPOSED, 1))
        self.assertEqual(record.sources, (self.event().source,))
        self.assertIsNone(record.reviewed_by)
        self.assertIsNone(record.adopted_by)
        self.assertEqual(len(self.rows()), 1)
        history = self.called[-1][1].tool_history
        self.assertEqual(history[0].result_json, history[1].result_json)
        self.assertEqual(json.loads(self.messages.batch(batch)["contributions_json"])["relationship_context"]["references"], [])
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)

    async def test_emotion_has_explicit_subject_and_never_enters_factual_evidence(self):
        self.answer_after(self.propose(kind="emotion_episode", emotion_subject="role"))
        batch = await self.generate()
        record, = self.records()
        self.assertEqual(record.emotion_subject.value, "role")
        self.assertEqual(record.state, State.PROPOSED)
        request = self.called[-1][1].original
        self.assertEqual(request.context.evidence_sources, (self.event().source,))
        self.assertFalse(any(m.owner == "relationship.memory" for m in request.context.materials))
        await self.deliver_next(batch)

    async def test_model_cannot_forge_authority_sources_or_human_adoption(self):
        self.answer_after(self.propose("state", state="adopted"), self.propose("actor", subject="another-user"),
            self.propose("fake", evidence_handles=["invented-source"]),
            call("adopt", "relationship.memory.adopt", memory_id="invented", expected_revision=1))
        await self.generate()
        self.assertTrue(all(row["state"] == "failed" for row in self.rows()))
        self.assertEqual(self.records(), ())

    async def test_missing_or_inapplicable_emotion_subject_does_not_create_a_record(self):
        self.answer_after(self.propose("no-subject", kind="emotion_episode"),
                          self.propose("irrelevant-subject", emotion_subject="human"))
        await self.generate()
        self.assertTrue(all(row["state"] == "failed" for row in self.rows()))
        self.assertEqual(self.records(), ())

    async def test_foreign_host_handle_cannot_become_current_private_evidence(self):
        other = self.context_for(self.important, replace(SCOPE, conversation_id="elsewhere", session_id="elsewhere"))
        source = self.event("foreign", context=other).source
        self.grant(self.important, other.scope, "text")
        batch = self.accept()
        offered = self.tools.offer_sources(self.context, batch, (ToolSource("foreign", source, "text"),))
        self.assertFalse(offered.is_success)
        self.answer_after(self.propose(evidence_handles=["relationship-source:foreign"]))
        await self.generate(batch=batch)
        self.assertEqual(json.loads(self.rows()[0]["result_json"])["code"], "relationship_source_unavailable")
        self.assertEqual(self.records(), ())

    async def test_host_offered_original_can_support_a_proposal_without_model_supplied_refs(self):
        source = self.event("additional-private-evidence").source
        batch = self.accept()
        self.tools.offer_sources(self.context, batch, (ToolSource("original", source, "text"),)).unwrap()
        self.answer_after(self.propose(evidence_handles=["relationship-source:original"]))
        await self.generate(batch=batch)
        self.assertEqual(self.records()[0].sources, (source,))

    async def test_revoked_propose_grant_blocks_pending_delivery_without_erasing_receipt(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(self.tools.relationships.catalog_for(self.context), ())
        for action in ("relationship.memory.read", "conversation.reply", "configuration.read"):
            self.grant(self.important, SCOPE, action)
        grant = self.grant(self.important, SCOPE, "relationship.memory.propose")
        self.answer_after(self.propose())
        batch = await self.generate()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual(self.tools.relationships.catalog_for(self.context), ())
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.rows()[0]["effect"], "committed")
        self.assertEqual(self.sent, [])

    async def test_unknown_call_is_not_reexecuted(self):
        proposal = self.propose()
        self.responses["primary"] = requested(proposal)
        batch, run = await self.manual_run()
        session = self.gateway.open_session(run, self.messages.request(run), tools=self.tools.catalog)
        completion = await session.generate(self.messages.request(run))
        with patch.object(self.tools.relationships, "execute", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                self.tools.execute(run, completion.call_id, proposal)
        with patch.object(self.tools.relationships, "execute", side_effect=AssertionError("must not retry")):
            replay = self.tools.execute(run, completion.call_id, proposal)
        self.assertEqual(json.loads(replay.result_json)["state"], "unknown")
        with self.assertRaises(TaskError) as error:
            self.tools.relationships.execute(self.context, batch, "renamed-retry", proposal.action,
                                             json.loads(proposal.arguments_json))
        self.assertEqual(error.exception.code, "relationship_proposal_unknown")
        self.assertEqual(self.records(), ())
        self.assertEqual(self.parts(batch), ())

    async def test_restart_and_source_revocation_recheck_before_delivery(self):
        self.answer_after(self.propose())
        batch = await self.generate()
        runtime = self.open_runtime()
        _, messages, delivery = self.components(runtime)
        LocalRoleTools(messages, relationships=messages.relationship_context.service)
        self.assertTrue(delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        original, = self.records()
        messages.sources.revoke(original.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as error:
            messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual(error.exception.code, "source_revoked")
        self.assertEqual(len(self.called), 2)
        self.assertEqual(self.rows()[0]["state"], "succeeded")

    async def test_human_review_does_not_rewrite_the_original_submission_receipt(self):
        self.answer_after(self.propose())
        batch = await self.generate()
        original, = self.records()
        original_result = self.rows()[0]["result_json"]
        manager = RelationshipMemoryManagement(self.service)
        item = manager.list(operator=self.core, context=self.context).unwrap()["items"][0]
        for action in ("review", "adopt", "retract"):
            item = manager.command(operator=self.core, context=self.context, memory_id=item["memory_id"],
                action=action, expected_revision=item["revision"], view_token=item["view_token"],
                operation_key=action).unwrap()["item"]
        await self.deliver_next(batch)
        self.assertEqual(self.rows()[0]["result_json"], original_result)
        self.assertEqual(self.records()[0].state, State.RETRACTED)
        self.assertEqual(json.loads(original_result)["payload"]["applied_state"], "proposed")
        self.assertEqual(len(self.sent), 1)
        reopened = RelationshipMemoryService(self.open_runtime(), now=self.clock.now)
        operation = json.loads(original_result)["payload"]["operation_id"]
        later = NOW + timedelta(seconds=1)
        repeated = replace(original, created_at=later, observed_at=later, updated_at=later)
        receipt = reopened.propose(repeated, actor=self.context.actor, observed_at=later,
                                   operation_id=operation).unwrap()
        self.assertEqual(receipt, original)
        conflict = reopened.propose(replace(repeated, interpretation="另一份内容"), actor=self.context.actor,
                                    observed_at=later, operation_id=operation)
        self.assertFalse(conflict.is_success)
        self.assertEqual(self.records()[0].state, State.RETRACTED)


class RelationshipProducerHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_ingress_proposal_review_reset_and_following_consumption(self):
        host = await self.start()
        app = host.application
        async def propose(envelope):
            if not envelope.tool_history:
                return requested(call("relationship-proposal", "relationship.memory.propose",
                    kind="emotion_episode", emotion_subject="role", interpretation="那次认真倾听让我感到踏实。",
                    evidence_handles=["relationship-input-1"]))
            return answered("我把这次交流的感受整理为待审阅提案。")
        self.model_behavior = propose
        first = host.receive(self.event(text="今天能认真聊完彼此的顾虑，我很开心。")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, first))["state"], "complete")
        first_context = self.context(app, first)
        memory, = app.relationship_memories.for_relationship(actor=first_context.actor, scope=SCOPE).unwrap()
        self.assertEqual(memory.state, State.PROPOSED)
        self.assertEqual(app.messages.relationship_context.capture(first_context, self.clock.now())["references"], [])

        new_scope = replace(SCOPE, conversation_id="reset-conversation", session_id="reset-session")
        self.grant(self.important, new_scope, "text")
        self.model_behavior = None
        second = host.receive(self.event("after-reset", scope=new_scope)).unwrap()
        second_context = self.context(app, second)
        manager = RelationshipMemoryManagement(app.relationship_memories)
        item = manager.list(operator=self.core, context=second_context).unwrap()["items"][0]
        for action in ("review", "adopt"):
            item = manager.command(operator=self.core, context=second_context, memory_id=item["memory_id"],
                action=action, expected_revision=item["revision"], view_token=item["view_token"],
                operation_key=action).unwrap()["item"]
        self.advance(app)
        self.assertEqual((await self.done(app, second))["state"], "complete")
        materials = [m for m in self.called[-1].original.context.materials if m.owner == "relationship.memory"]
        self.assertEqual(len(materials), 1)
        self.assertEqual(json.loads(materials[0].payload)["interpretation"], memory.interpretation)
        self.assertIsNone(materials[0].source)
        current = app.relationship_memories.read(memory.memory_id, actor=second_context.actor, scope=new_scope).unwrap()
        self.assertEqual(current.sources, memory.sources)
        self.assertEqual(current.sources[0].scope, SCOPE)
        self.assertEqual(current.adopted_by, self.core.subject)

    async def test_sent_reply_propagates_the_proposals_source_revocation(self):
        host = await self.start()
        app = host.application
        async def propose(envelope):
            if not envelope.tool_history:
                return requested(call("proposal", "relationship.memory.propose", kind="context",
                    interpretation="我们尝试先互相听完再表达不同意见。", evidence_handles=["relationship-input-1"]))
            return answered("这段相处体会已经提交待审阅。")
        self.model_behavior = propose
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        context = self.context(app, batch)
        memory, = app.relationship_memories.for_relationship(actor=context.actor, scope=context.scope).unwrap()
        sent_sources = app.memory.writer.access.sent_sources
        reference = next(sent_sources.rows(context))
        sent_sources.materialize(context, reference)
        self.assertIsNotNone(self.runtime.read_one(
            "SELECT 1 FROM source_dependencies WHERE dependent_id = ? AND input_id = ?",
            (reference.source_id, memory.sources[0].source_id)))
        app.messages.sources.revoke(memory.sources[0], expected_governance_revision=1,
                                    observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError):
            sent_sources.validate(context, reference)
        self.assertFalse(app.messages.history(context).unwrap()["items"][0]["body_available"])
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
