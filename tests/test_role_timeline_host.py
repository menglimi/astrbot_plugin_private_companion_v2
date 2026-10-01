"""Host assembly and confirmed-reply provenance for the role timeline tool."""

import json
import unittest

from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.foundation.refs import AudienceRef
from companion_v2.role_work.growth import GrowthKind, RoleGrowthRecord
from companion_v2.role_work.models import RoleActivity, RoleActivityState, RoleReadingReceipt
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered, call, requested


class RoleTimelineHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_assembled_query_delivery_and_confirmed_quote_keep_original_source_dependency(self):
        host = await self.start()
        app = host.application
        evidence = host.inbound.ingest(self.event("evidence", text="一个水彩练习想法。"), capability="text").unwrap()
        reading = host.inbound.ingest(self.event("reading", text="一篇关于水彩构图的阅读材料。"), capability="text").unwrap()
        context = TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                              AudienceRef(SCOPE, (self.important.subject,)))
        owner = app.life_context.owner(context)
        app.role_growth.add(RoleGrowthRecord("goal", owner, SCOPE, GrowthKind.GOAL, "练习水彩", "从构图开始。", "",
            (evidence.source,), NOW, NOW, proposed_by=context.actor.subject))
        app.role_life.add_activity(RoleActivity("reading", owner.persona_id, SCOPE, NOW, RoleActivityState.COMPLETED,
            reading=RoleReadingReceipt(reading.source, reading.input_hash, len("一篇关于水彩构图的阅读材料。"), 0, 3, NOW)))
        async def respond(envelope):
            actions = {tool.action for tool in envelope.tools}
            self.assertTrue({"role.timeline.query", "role.growth.list", "memory.query", "memo.create"}.issubset(actions))
            if not envelope.tool_history:
                return requested(call("timeline", "role.timeline.query", kinds=["growth", "activity"]))
            item = json.loads(envelope.tool_history[0].result_json)["payload"]["items"][0]
            self.assertEqual(item["detail"]["state"], "proposed")
            return answered("之前记过一份水彩练习提案。\n当时尚未确认。")
        self.model_behavior = respond
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(len(self.sent), 2)
        sent_sources = app.memory.writer.access.sent_sources
        reference = next(sent_sources.rows(context))
        sent_sources.materialize(context, reference)
        self.assertIsNotNone(self.runtime.read_one("SELECT 1 FROM source_dependencies WHERE dependent_id = ? AND input_id = ?",
            (reference.source_id, evidence.source.source_id)))
        self.assertIsNotNone(self.runtime.read_one("SELECT 1 FROM source_dependencies WHERE dependent_id = ? AND input_id = ?",
            (reference.source_id, reading.source.source_id)))
        app.messages.sources.revoke(reading.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE source_id = ?", (reference.source_id,))["state"], "revoked")
        with self.assertRaises(TaskError):
            sent_sources.validate(context, reference)
        self.assertTrue(all(not item["body_available"] for item in app.messages.history(context).unwrap()["items"]))
