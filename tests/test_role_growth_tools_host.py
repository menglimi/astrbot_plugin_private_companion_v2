"""Composed growth tools preserve private delivery and downstream source governance."""

import json
import unittest

from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.foundation.refs import AudienceRef
from companion_v2.role_work.growth import GrowthKind, RoleGrowthRecord
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered, call, requested


class RoleGrowthToolsHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_propose_query_revise_and_deliver_with_memory_tools_enabled(self):
        host = await self.start()
        app = host.application
        async def respond(envelope):
            actions = {t.action for t in envelope.tools}
            self.assertTrue({"memory.query", "memo.create", "role.growth.propose"}.issubset(actions))
            count = len(envelope.tool_history)
            if count == 0:
                return requested(call("propose", "role.growth.propose", kind="skill", title="水彩构图",
                                      evidence_handles=["growth-input-1"]))
            if count == 1:
                return requested(call("list", "role.growth.list", state="proposed"))
            if count == 2:
                receipt = json.loads(envelope.tool_history[0].result_json)["payload"]
                return requested(call("revise", "role.growth.revise", growth_id=receipt["growth_id"],
                    expected_revision=receipt["applied_revision"], title="水彩构图练习", description="从简单风景开始。",
                    progress_note="先准备参考图。", evidence_handles=["growth-input-1"]))
            self.assertEqual(json.loads(envelope.tool_history[1].result_json)["state"], "superseded")
            return answered("已整理好提案。\n等你确认后再继续。")
        self.model_behavior = respond
        batch = host.receive(self.event(text="我们整理一个水彩构图练习的提案吧。")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        context = self.context(app, batch)
        records = app.role_growth.for_role(app.role_growth_context.reader.owner(context))
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0].revision, records[0].state.value, records[0].confirmed_by), (2, "proposed", None))
        self.assertEqual([e.text for e in self.sent], ["已整理好提案。", "等你确认后再继续。"])
        self.assertEqual(len(app.messages.history(context).unwrap()["items"]), 2)

    async def test_confirmed_reply_source_retains_growth_evidence_dependency(self):
        host = await self.start()
        app = host.application
        evidence = host.inbound.ingest(self.event("separate-evidence", text="准备画水彩的想法。"), capability="text").unwrap()
        context = TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                              AudienceRef(SCOPE, (self.important.subject,)))
        record = RoleGrowthRecord("read-growth", app.role_growth_context.reader.owner(context), SCOPE,
            GrowthKind.GOAL, "水彩练习", "一个待确认的想法。", "", (evidence.source,), NOW, NOW,
            proposed_by=context.actor.subject)
        app.role_growth.add(record)
        async def respond(envelope):
            if not envelope.tool_history:
                return requested(call("list", "role.growth.list", state="proposed"))
            return answered("之前有一份待确认的水彩练习提案。")
        self.model_behavior = respond
        batch = host.receive(self.event()).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        sent_sources = app.memory.writer.access.sent_sources
        reference = next(sent_sources.rows(context))
        sent_sources.materialize(context, reference)
        linked = self.runtime.read_one("SELECT 1 FROM source_dependencies WHERE dependent_id = ? AND input_id = ?",
                                      (reference.source_id, evidence.source.source_id))
        self.assertIsNotNone(linked)
        app.messages.sources.revoke(evidence.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        self.assertEqual(self.runtime.read_one("SELECT state FROM sources WHERE source_id = ?", (reference.source_id,))["state"], "revoked")
        with self.assertRaises(TaskError):
            sent_sources.validate(context, reference)
        self.assertFalse(app.messages.history(context).unwrap()["items"][0]["body_available"])
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
