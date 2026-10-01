"""Timeline selections survive newer history, but never outlive source authority."""

import json
import unittest

from companion_v2.conversation.tool_loop import LocalRoleTools
from companion_v2.execution.models import TaskError
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.role_work.journal import RoleJournalService
from companion_v2.role_work.ledger import PersistentRoleLifeLedger
from companion_v2.role_work.life.context import RoleLifeContextReader
from companion_v2.role_work.timeline import RoleTimeline
from tests.test_management_access import NOW, SCOPE
from tests.test_role_growth_tools import GrowthToolFixture
from tests.test_role_tool_loop import answered, call, requested


class TimelineToolFixture(GrowthToolFixture):
    def timeline_tools(self, messages):
        runtime, tasks = messages.runtime, messages.tasks
        reader = RoleLifeContextReader(PersistentRoleLifeLedger(runtime, now=self.clock.now),
            RoleJournalService(runtime, now=self.clock.now), tasks)
        messages.tools = None
        return LocalRoleTools(messages, growth=messages.role_growth_context.reader,
                              timeline=RoleTimeline(reader, messages.role_growth_context.reader))

    def setUp(self):
        super().setUp()
        self.tools = self.timeline_tools(self.messages)


class RoleTimelineToolTests(TimelineToolFixture, unittest.IsolatedAsyncioTestCase):
    async def test_tool_query_continuation_keeps_historical_proposal_after_later_confirmation(self):
        record = self.seed()
        async def respond(envelope):
            self.assertIn("role.timeline.query", {tool.action for tool in envelope.tools})
            if not envelope.tool_history:
                return requested(call("timeline", "role.timeline.query", kinds=["growth"]))
            result = json.loads(envelope.tool_history[0].result_json)
            self.assertEqual(result["effect"], "none")
            self.assertEqual(result["payload"]["items"][0]["detail"]["state"], "proposed")
            self.growth.confirm(record.growth_id, owner=record.owner, scope=SCOPE, expected_revision=1,
                operation_id="human-confirm", actor=self.core.subject, observed_at=NOW)
            return answered("当时保存过一份水彩练习提案。")
        self.responses["primary"] = respond
        batch = await self.generate()
        await self.deliver_next(batch)
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.history()[0]["body_available"])

    async def test_source_revoke_during_continuation_discards_draft(self):
        record = self.seed()
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("timeline", "role.timeline.query", kinds=["growth"]))
            self.messages.sources.revoke(record.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
            return answered("这份旧资料不应送出。")
        self.responses["primary"] = respond
        batch, run = await self.manual_run()
        with self.assertRaises(TaskError) as error:
            await self.generator.generate(run)
        self.assertEqual(error.exception.code, "source_revoked")
        self.assertEqual(self.parts(batch), ())

    async def test_revoke_between_parts_preserves_first_receipt_and_hides_original_history(self):
        record = self.seed()
        async def respond(envelope):
            return requested(call("timeline", "role.timeline.query", kinds=["growth"])) if not envelope.tool_history else answered("当时有一份提案。\n下一段。")
        self.responses["primary"] = respond
        batch = await self.generate()
        await self.deliver_next(batch)
        history = self.history()[0]
        receipt = dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?", (history["part_id"],)))
        self.messages.sources.revoke(record.sources[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertFalse(self.history()[0]["body_available"])
        self.assertEqual(dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts WHERE part_id = ?", (history["part_id"],))), receipt)
        self.assertEqual(len(self.sent), 1)

    async def test_restart_rereads_sealed_versions_without_needing_original_cursor_key(self):
        self.seed("one")
        self.seed("two")
        self.answer_after(call("timeline", "role.timeline.query", kinds=["growth"], limit=1))
        batch = await self.generate()
        self.assertTrue(json.loads(self.rows()[0]["result_json"])["payload"]["next_cursor"])
        runtime = self.open_runtime()
        _, messages, delivery = self.components(runtime)
        self.timeline_tools(messages)
        self.assertTrue(delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(len(self.called), 2)

    async def test_tool_cannot_supply_identity_and_permission_revocation_blocks_even_empty_selection(self):
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD, expected_revision=self.policy.revision, observed_at=NOW)
        self.assertEqual(self.tools.timeline.catalog_for(self.context), ())
        for action in ("conversation.reply", "configuration.read", "role.growth.read"):
            self.grant(self.important, SCOPE, action)
        self.assertEqual(len(self.tools.timeline.catalog_for(self.context)), 1)
        self.answer_after(call("forged", "role.timeline.query", kinds=["growth"], actor="admin"),
                          call("timeline", "role.timeline.query", kinds=["growth"]))
        batch = await self.generate()
        self.assertEqual([r["state"] for r in self.rows()], ["failed", "succeeded"])
        grant = next(g for g in self.identity.snapshot().grants if g.capability == "role.growth.read")
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        self.assertFalse(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).is_success)
        self.assertEqual(self.sent, [])
