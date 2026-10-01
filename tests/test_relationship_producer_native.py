"""Actual MultiSession and native model wire, with synthetic platform/provider IO."""

from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest

# This support module redirects ASTRBOT_ROOT before importing the host SDK.
from tests.multi_host_support import MultiFixture, multi_config
from tests.native_adapter_support import completion, final_text
from astrbot_host.management_identity import dashboard_operator
from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.adapters.astrbot.staging_config import REQUIRED_CAPABILITIES
from companion_v2.relationships.management import RelationshipMemoryManagement


class NativeRelationshipProducerTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.capabilities = sorted(REQUIRED_CAPABILITIES | {
            "memory.read", "memory.propose", "relationship.memory.read", "relationship.memory.propose"})
        self.controller = self.make_controller(multi_config(capabilities=self.capabilities,
                                                           delivery_mode="onebot_private"))

    async def test_native_private_proposal_continuation_review_reset_and_delivery(self):
        app = await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        interpretation = "认真听完彼此的顾虑之后，我觉得交流轻松了一些。"
        async def propose(payload, tools):
            self.assertIn(tool_alias("relationship.memory.propose"), {tool.name for tool in tools.tools})
            self.assertIn("relationship-input-1", json.dumps(payload, ensure_ascii=False))
            if not any(message.get("role") == "tool" for message in payload["messages"]):
                return completion(tools=[NS(id="relationship-proposal", type="function", function=NS(
                    name=tool_alias("relationship.memory.propose"), arguments=json.dumps(dict(
                        kind="emotion_episode", emotion_subject="role", interpretation=interpretation,
                        evidence_handles=["relationship-input-1"]), ensure_ascii=False)))])
            receipt = next(message for message in payload["messages"] if message.get("role") == "tool")
            self.assertIn('"applied_state":"proposed"', receipt["content"])
            return completion(final_text("我把这次交流的感受提交为待审阅提案。"))
        self.native.provider.client.state.behavior = propose
        first, batch = await self.accepted(text="今天认真聊完彼此的顾虑，我很开心。")
        self.assertEqual(app.flow.row(batch)["state"], "complete")
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        record, = app.relationship_memories.for_relationship(actor=first.actor, scope=first.scope).unwrap()
        self.assertEqual((record.state.value, record.subject), ("proposed", first.actor.subject))
        self.assertIsNone(record.adopted_by)
        self.assertEqual(app.messages.relationship_context.capture(first, self.clock.now())["references"], [])

        operator = dashboard_operator(app.runtime, "synthetic-admin", at=self.clock.now())
        manager = RelationshipMemoryManagement(app.relationship_memories)
        item = manager.list(operator=operator, context=first).unwrap()["items"][0]
        for action in ("review", "adopt"):
            item = manager.command(operator=operator, context=first, memory_id=item["memory_id"],
                action=action, expected_revision=item["revision"], view_token=item["view_token"],
                operation_key=action).unwrap()["item"]
        self.native.conversations["qq-main"] = "conversation-after-reset"
        self.clock.advance(timedelta(seconds=1))
        async def recall(payload, tools):
            return completion(final_text("我记得那次交流带来的踏实感。"))
        self.native.provider.client.state.behavior = recall
        current, later = await self.accepted(identifier="after-reset", text="我们继续聊吧。")
        self.assertEqual(app.flow.row(later)["state"], "complete")
        snapshot = json.loads(app.messages.batch(later)["contributions_json"])["relationship_context"]
        self.assertEqual(len(snapshot["references"]), 1, snapshot)
        wire = self.native.provider.client.state.calls[-1][0]
        materials = json.loads(next(message["content"] for message in wire["messages"]
                                    if message["role"] == "user"))["materials"]
        relationship = json.loads(next(material["text"] for material in materials
                                       if material["owner"] == "relationship.memory"))
        self.assertEqual(relationship["interpretation"], interpretation)
        self.assertEqual(relationship["basis"], "subjective_relationship_interpretation")
        self.assertNotEqual(first.scope.conversation_id, current.scope.conversation_id)
        self.assertEqual(first.actor.subject, current.actor.subject)
        self.assertEqual(first.role_binding.role, current.role_binding.role)
        adopted = app.relationship_memories.read(record.memory_id, actor=current.actor, scope=current.scope).unwrap()
        self.assertEqual(adopted.sources, record.sources)
        self.assertEqual(adopted.sources[0].scope, first.scope)
        self.assertEqual(adopted.adopted_by, operator.subject)
        sends = self.native.platforms["qq-main"].client._api._wsr_api.calls
        self.assertEqual(len(sends), 2)
        self.assertTrue(all(action == "send_private_msg" and body["self_id"] == "100"
                            and body["user_id"] == 200 for action, body in sends))
        self.assertEqual(self.native.platforms["qq-second"].client._api._wsr_api.calls, [])

    async def test_existing_installation_without_relationship_grants_keeps_tool_unavailable(self):
        old_capabilities = [value for value in self.capabilities if not value.startswith("relationship.")]
        self.controller = self.make_controller(multi_config(capabilities=old_capabilities))
        app = await self.start_host()
        async def respond(payload, tools):
            self.assertNotIn(tool_alias("relationship.memory.propose"), {tool.name for tool in tools.tools})
            return completion(final_text("我们继续聊。"))
        self.native.provider.client.state.behavior = respond
        context, _ = await self.accepted()
        self.assertEqual(app.tools.relationships.catalog_for(context), ())
        self.assertEqual(app.runtime.read_all("SELECT * FROM relationship_memories", ()), ())


if __name__ == "__main__":
    unittest.main()
