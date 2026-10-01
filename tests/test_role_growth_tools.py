"""Growth tools run through real local model rounds without external IO."""

from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.growth_context import ConversationRoleGrowthContext
from companion_v2.conversation.foreground import PromptMaterial
from companion_v2.conversation.tool_loop import LocalRoleTools, ToolSource
from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.role_work.growth import GrowthKind, GrowthState, PersistentRoleGrowthLedger, RoleGrowthContextReader, RoleGrowthRecord
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import ToolLoopFixture, answered, call, requested


class GrowthToolFixture(ToolLoopFixture):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        reader = RoleGrowthContextReader(PersistentRoleGrowthLedger(runtime, now=self.clock.now), tasks)
        messages.role_growth_context = ConversationRoleGrowthContext(reader)
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.reader = self.messages.role_growth_context.reader
        self.growth = self.reader.ledger
        self.messages.tools = None
        self.tools = LocalRoleTools(self.messages, growth=self.reader)

    def seed(self, identifier="growth-original", *, context=None, **changes):
        context = context or self.context
        record = RoleGrowthRecord(identifier, self.reader.owner(context), context.scope,
            GrowthKind.GOAL, "练习水彩", "从构图开始。", "刚选好参考图。",
            (self.event("evidence-" + identifier, context=context).source,), NOW, NOW,
            proposed_by=context.actor.subject)
        return self.growth.add(replace(record, **changes))

    def propose(self, identifier="proposal", **changes):
        args = dict(kind="goal", title="水彩小计划", description="画一幅周末风景。",
                    progress_note="准备开始。", evidence_handles=["growth-input-1"]) | changes
        return call(identifier, "role.growth.propose", **args)

    def revise(self, record, identifier="revise", **changes):
        return call(identifier, "role.growth.revise", **(dict(growth_id=record.growth_id,
            expected_revision=record.revision, title="更聚焦的构图练习", description="先画小幅草稿。",
            progress_note="仍待确认。", evidence_handles=["growth-input-1"]) | changes))

    def answer_after(self, *calls):
        async def respond(envelope):
            return requested(*calls) if not envelope.tool_history else answered("已保存为待确认提案。")
        self.responses["primary"] = respond


class RoleGrowthToolTests(GrowthToolFixture, unittest.IsolatedAsyncioTestCase):
    async def test_proposal_is_attributed_but_never_confirmed_and_duplicate_keeps_receipt(self):
        async def respond(envelope):
            offers = next(m for m in envelope.original.context.materials if m.purpose == "growth_evidence_handles")
            self.assertEqual(json.loads(offers.payload)[0]["handle"], "growth-input-1")
            return requested(self.propose()) if len(envelope.tool_history) < 2 else answered("提案待确认。")
        self.responses["primary"] = respond
        batch = await self.generate()
        records = self.growth.for_role(self.reader.owner(self.context))
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.state, GrowthState.PROPOSED)
        self.assertEqual(record.proposed_by, self.context.actor.subject)
        self.assertIsNone(record.confirmed_by)
        self.assertEqual(record.sources, (self.event().source,))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.called[-1][1].tool_history[0], self.called[-1][1].tool_history[1])
        self.assertEqual(json.loads(self.messages.batch(batch)["contributions_json"])["role_growth"]["references"], [])
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)

    async def test_query_then_same_turn_revision_replaces_only_old_query(self):
        original = self.seed()
        async def respond(envelope):
            count = len(envelope.tool_history)
            if count == 0:
                return requested(call("query", "role.growth.list", state="proposed"))
            if count == 1:
                return requested(self.revise(original))
            if count == 2:
                old = json.loads(envelope.tool_history[0].result_json)
                self.assertEqual(old, {"state": "superseded", "effect": "none", "reason": "changed_by_this_turn"})
                return requested(call("query-new", "role.growth.list", state="proposed"))
            fresh = json.loads(envelope.tool_history[-1].result_json)["payload"]["items"][0]
            self.assertEqual((fresh["revision"], fresh["title"]), (2, "更聚焦的构图练习"))
            return answered("已更新提案，仍待确认。")
        self.responses["primary"] = respond
        batch = await self.generate()
        self.assertEqual(len(self.growth.revisions(original.growth_id, owner=original.owner)), 2)
        await self.deliver_next(batch)
        self.assertTrue(self.history()[0]["body_available"])

    async def test_same_round_multiple_revisions_keep_a_contiguous_receipt_chain(self):
        original = self.seed()
        self.answer_after(self.revise(original, "one"), self.revise(replace(original, revision=2), "two", title="第二次修订"))
        await self.generate()
        current = self.growth.record(original.growth_id, owner=original.owner)
        self.assertEqual((current.revision, current.title), (3, "第二次修订"))
        self.assertEqual([r["effect"] for r in self.rows()], ["committed", "committed"])

    async def test_external_change_during_query_continuation_blocks_manifest(self):
        original = self.seed()
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("query", "role.growth.list", state="proposed"))
            self.growth.confirm(original.growth_id, owner=original.owner, scope=original.scope,
                expected_revision=1, operation_id="human-confirmation", actor=self.core.subject, observed_at=NOW)
            return answered("旧查询不应发送。")
        self.responses["primary"] = respond
        batch, run = await self.manual_run()
        with self.assertRaises(TaskError) as error:
            await self.generator.generate(run)
        self.assertEqual(error.exception.code, "growth_result_changed")
        self.assertEqual(self.parts(batch), ())

    async def test_role_cannot_confirm_complete_or_revise_confirmed_growth(self):
        original = self.seed()
        active = self.growth.confirm(original.growth_id, owner=original.owner, scope=original.scope,
            expected_revision=1, operation_id="confirmed", actor=self.core.subject, observed_at=NOW)
        self.answer_after(call("confirm", "role.growth.confirm", growth_id=original.growth_id),
                          call("complete", "role.growth.complete", growth_id=original.growth_id), self.revise(active))
        await self.generate()
        self.assertEqual([json.loads(r["result_json"])["code"] for r in self.rows()],
            ["tool_not_available", "tool_not_available", "growth_confirmation_required"])
        self.assertEqual(self.growth.record(original.growth_id, owner=original.owner), active)

    async def test_model_cannot_supply_authority_or_forge_original_sources(self):
        self.answer_after(self.propose("actor", confirmed_by="admin"), self.propose("scope", scope={}),
                          self.propose("source", sources=[]), self.propose("fake", evidence_handles=["not-offered"]))
        await self.generate()
        self.assertTrue(all(r["state"] == "failed" for r in self.rows()))
        self.assertEqual(self.growth.for_role(self.reader.owner(self.context)), ())

    async def test_catalog_and_execution_need_separate_read_and_propose_grants(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(self.tools.growth.catalog_for(self.context), ())
        self.grant(self.important, SCOPE, "role.growth.propose")
        self.assertEqual(self.tools.growth.catalog_for(self.context), ())
        self.grant(self.important, SCOPE, "role.growth.read")
        self.assertEqual(len(self.tools.growth.catalog_for(self.context)), 3)
        self.grant(self.important, SCOPE, "conversation.reply")
        self.grant(self.important, SCOPE, "configuration.read")
        self.answer_after(self.propose())
        batch = await self.generate()
        grant = next(g for g in self.identity.snapshot().grants if g.capability == "role.growth.propose")
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertEqual([t.action for t in self.tools.growth.catalog_for(self.context)], ["role.growth.list"])
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(self.sent, [])

    async def test_cross_scope_growth_and_host_offered_source_are_rejected(self):
        foreign_context = replace(self.context, role_binding=replace(self.context.role_binding,
            scope=replace(SCOPE, session_id="other-session")),
            audience=replace(self.context.audience, scope=replace(SCOPE, session_id="other-session")))
        other = self.seed("elsewhere", context=foreign_context)
        batch = self.accept()
        self.tools.offer_sources(self.context, batch, (ToolSource("foreign", other.sources[0], "text"),))
        self.answer_after(self.revise(other), self.propose("foreign-source", evidence_handles=["growth-source:foreign"]))
        await self.generate(batch=batch)
        self.assertTrue(all(r["state"] == "failed" for r in self.rows()))
        self.assertEqual(self.growth.record(other.growth_id, owner=other.owner), other)

    async def test_restart_preserves_proposal_and_rechecks_source_before_delivery(self):
        original = self.seed()
        self.answer_after(call("list", "role.growth.list", state="proposed"))
        batch = await self.generate()
        runtime = self.open_runtime()
        _, messages, delivery = self.components(runtime)
        LocalRoleTools(messages, growth=messages.role_growth_context.reader)
        self.assertTrue(delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        messages.sources.revoke(original.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as error:
            messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual(error.exception.code, "source_revoked")
        self.assertEqual(len(self.called), 2)

    async def test_unknown_tool_result_is_not_executed_again(self):
        selected = self.propose()
        self.responses["primary"] = requested(selected)
        batch, run = await self.manual_run()
        session = self.gateway.open_session(run, self.messages.request(run), tools=self.tools.catalog)
        completion = await session.generate(self.messages.request(run))
        with patch.object(self.tools.growth, "execute", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                self.tools.execute(run, completion.call_id, selected)
        replay = self.tools.execute(run, completion.call_id, selected)
        self.assertEqual(json.loads(replay.result_json)["state"], "unknown")
        self.assertEqual(self.growth.for_role(self.reader.owner(self.context)), ())
        self.assertEqual(self.parts(batch), ())

    async def test_query_budget_and_source_withdrawal_do_not_hide_coverage(self):
        for n in range(10):
            self.seed("growth-" + str(n), description="资料" * 2000, progress_note="定性进展" * 1000)
        hidden = self.seed("growth-99")
        self.messages.sources.revoke(hidden.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        self.answer_after(call("list", "role.growth.list", limit=20))
        await self.generate()
        result = json.loads(self.rows()[0]["result_json"])["payload"]
        self.assertTrue(result["selection_partial"])
        self.assertTrue(result["next_cursor"])
        self.assertTrue(result["items"][0]["truncated_fields"])
        self.assertLess(len(self.rows()[0]["result_json"].encode("utf-8")), 65536)

    async def test_growth_query_refresh_cannot_replace_another_owners_prompt_material(self):
        original = self.seed()
        async def respond(envelope):
            count = len(envelope.tool_history)
            if count == 0:
                return requested(call("query", "role.growth.list", state="proposed"))
            if count == 1:
                return requested(self.revise(original))
            return answered("已修改提案。")
        self.responses["primary"] = respond
        batch = await self.generate()
        first, queried, refreshed = (envelope for _, envelope in self.called)
        self.assertTrue(self.tools.validate_owner_refresh(self.context, batch, first.original,
            refreshed.original, queried.tool_history, refreshed.tool_history))
        injected = replace(refreshed.original, context=replace(refreshed.original.context,
            materials=refreshed.original.context.materials + (PromptMaterial("memory", "current_memory", "unrelated change"),)))
        self.assertFalse(self.tools.validate_owner_refresh(self.context, batch, first.original,
            injected, queried.tool_history, refreshed.tool_history))


if __name__ == "__main__":
    unittest.main()
