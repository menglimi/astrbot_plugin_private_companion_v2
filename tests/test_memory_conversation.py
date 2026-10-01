import json
import unittest
from dataclasses import replace

from companion_v2.memory import codec
from companion_v2.memory.models import AtomRef, Proposal
from companion_v2.memory.management import MemoryManagement
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import requested, answered, call


class MemoryConversationTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def handles(self, envelope):
        return json.loads(next(m.payload for m in envelope.original.context.materials if m.purpose == "current_input_handles"))

    async def test_chat_creates_memory_and_next_turn_corrects_the_same_fact(self):
        async def respond(envelope):
            if not envelope.tool_history:
                item = {"operation": "add", "predicate": "饮用偏好", "object": "不喝咖啡",
                    "representation": "用户明确说不喝咖啡。", "single_value": True, "evidence_handles": self.handles(envelope)}
                if envelope.original.event.event_id == "correct":
                    previous = json.loads(next(m.payload for m in envelope.original.context.materials if m.purpose == "current_memory"))
                    item.update(operation="correct", target_atom_id=previous["atom_id"], expected_revision=previous["revision"],
                                object="偶尔喝咖啡", representation="用户现在偶尔喝咖啡。")
                return requested(call("remember", "memory.proposal.submit", proposal=item))
            self.assertEqual(json.loads(envelope.tool_history[-1].result_json)["payload"]["state"], "persisted")
            return answered("记住了。")
        self.model_behavior = respond
        host = await self.start()
        app = host.application
        first = host.receive(self.event("save", text="记住，我不喝咖啡")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, first))["state"], "complete")
        second = host.receive(self.event("correct", text="纠正一下，现在我偶尔喝咖啡了")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, second))["state"], "complete")
        rows = app.runtime.read_all("SELECT * FROM memory_atoms", ())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revision"], 2)
        self.assertEqual(app.memory.writer.read(self.context(app, second), AtomRef(rows[0]["atom_id"], 2)).unwrap()["object"], "偶尔喝咖啡")
        self.assertEqual([e.text for e in self.sent], ["记住了。", "记住了。"])

    async def test_query_read_and_correct_in_one_turn_refreshes_tool_history(self):
        phase = {"seed": True}
        async def respond(envelope):
            history = envelope.tool_history
            if phase["seed"]:
                if not history:
                    return requested(call("save", "memory.proposal.submit", proposal={"operation": "add", "predicate": "杯子颜色",
                        "object": "蓝色", "representation": "用户的杯子是蓝色。", "evidence_handles": self.handles(envelope), "single_value": True}))
                return answered("保存好了。")
            if not history:
                return requested(call("find", "memory.query", query_intent="杯子"))
            if len(history) == 1:
                item = json.loads(history[0].result_json)["payload"]["items"][0]
                return requested(call("fix", "memory.proposal.submit", proposal={"operation": "correct", "predicate": "杯子颜色",
                    "object": "绿色", "representation": "用户的杯子已改成绿色。", "evidence_handles": self.handles(envelope),
                    "target_atom_id": item["atom_id"], "expected_revision": item["revision"], "single_value": True}))
            self.assertEqual(json.loads(history[0].result_json)["state"], "superseded")
            self.assertNotIn("蓝色", history[0].result_json)
            return answered("已经更正为绿色。")
        self.model_behavior = respond
        host = await self.start()
        app = host.application
        first = host.receive(self.event("save", text="记住，杯子是蓝色的")).unwrap()
        self.advance(app)
        await self.done(app, first)
        phase["seed"] = False
        second = host.receive(self.event("correct", text="把记忆里的杯子颜色改成绿色")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, second))["state"], "complete")
        self.assertEqual(self.sent[-1].text, "已经更正为绿色。")

    async def test_long_chinese_message_and_disabled_memory_keep_normal_chat_available(self):
        async def respond(envelope):
            return answered("看到了。")
        self.model_behavior = respond
        host = await self.start()
        app = host.application
        first = host.receive(self.event("long", text="".join(chr(0x4e00 + n) for n in range(2000)))).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, first))["state"], "complete")
        context = self.context(app, first)
        manager = MemoryManagement(app.memory, self.core)
        settings = manager.settings(context).unwrap()
        manager.patch_settings(context, operation_key="off", expected_edit_token=settings["edit_token"], changes={"memory.enabled": False}).unwrap()
        second = host.receive(self.event("disabled", text="继续聊聊")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, second))["state"], "complete")
        self.assertFalse(any(tool.action.startswith("memory.") for tool in self.called[-1].tools))

    async def test_experience_tool_can_save_and_recall_the_same_object(self):
        async def respond(envelope):
            history = envelope.tool_history
            if not history:
                return requested(call("experience", "memory.experience.save", view_id="desk", expected_revision=0, title="书桌边的闲聊",
                    statements=[{"text": "一起聊过书桌旁的杯子。", "evidence_handles": self.handles(envelope), "atoms": []}], entities=["物件:书桌"]))
            if len(history) == 1:
                self.assertEqual(json.loads(history[0].result_json)["payload"]["state"], "saved")
                return requested(call("recall", "memory.query", query_intent="书桌", kind="experiences"))
            self.assertEqual(json.loads(history[-1].result_json)["payload"]["items"][0]["view_id"], "desk")
            return answered("我们聊过书桌旁的杯子。")
        self.model_behavior = respond
        host = await self.start()
        app = host.application
        batch = host.receive(self.event("experience", text="我们刚聊过书桌旁的杯子，记下这件小事")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, batch))["state"], "complete")

    async def test_durable_memory_enters_a_later_private_session_for_the_same_persona(self):
        host = await self.start()
        app = host.application
        first = host.receive(self.event("first-session", text="记住，我不喝咖啡")).unwrap()
        self.advance(app)
        self.assertEqual((await self.done(app, first))["state"], "complete")

        original_context = self.context(app, first)
        row = app.runtime.read_one(
            "SELECT event_json FROM conversation_inputs WHERE batch_id = ? ORDER BY event_key LIMIT 1",
            (first,),
        )
        source = codec.source(json.loads(row["event_json"])["source"])
        evidence = app.memory.writer.access.capture(original_context, source)
        saved = app.memory.writer.submit(original_context, Proposal(
            "add", predicate="饮用偏好", object="不喝咖啡", representation="用户明确说自己不喝咖啡。",
            evidence=(evidence,), single_value=True,
        ), operation_key="cross-session-preference").unwrap()

        later_scope = replace(original_context.scope, native_scope_id="later", conversation_id="later", session_id="later-session")
        self.grant(self.important, later_scope, "text")

        async def recall(envelope):
            return answered("我记得你不喝咖啡。")

        self.model_behavior = recall
        later = host.receive(self.event("later-session", scope=later_scope, text="我平时喝咖啡吗？")).unwrap()
        self.advance(app)

        later_result = await self.done(app, later)
        self.assertEqual(later_result["state"], "complete")
        envelope = next(item for item in self.called if item.original.event.event_id == "later-session")
        material = next(item for item in envelope.original.context.materials if item.purpose == "current_memory")
        self.assertEqual(json.loads(material.payload)["object"], "不喝咖啡")
        self.assertEqual(app.memory.writer.read(self.context(app, later), AtomRef(saved["atom_id"], 1)).unwrap()["object"], "不喝咖啡")
