"""Native core chats feed memory without creating V2 replies or delivery receipts."""

import asyncio
from datetime import timedelta
import json
import unittest

from companion_v2.conversation.native_observations import ASSISTANT_OWNER, INPUT_OWNER
from companion_v2.conversation.native_history import dialogue
from companion_v2.conversation.recalls import MessageRecall
from companion_v2.execution.models import require, stamp
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.memory.episodes import recent_dialogue_lines
from companion_v2.memory.models import Proposal
from companion_v2.role_work.journal.models import JournalContext, JournalKey, JournalKind
from tests.multi_host_support import MultiFixture


class CoreReplyObservationTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()

    async def prepared(self, *, identifier="native-evidence", text="我平时不喝咖啡"):
        event = self.event(identifier=identifier, text=text)
        result = await self.controller.prepare_core_reply(event)
        self.assertTrue(result.is_success, result.failure)
        return result.unwrap()

    def sources(self, context, session_id="native-source-query"):
        self.app.memory.query.begin(context, session_id)
        return require(self.app.memory.query.query(context, session_id, query_intent="", kind="sources"))

    async def test_real_native_input_becomes_memory_evidence_and_recall_source(self):
        prepared = await self.prepared()
        reference = await prepared["native_source_future"]
        context = prepared["context"]

        self.assertEqual(reference.owner, INPUT_OWNER)
        indexes = {row["name"] for row in self.app.runtime.read_all(
            "PRAGMA index_list(conversation_native_observations)", ())}
        self.assertTrue({"conversation_native_input_context_idx", "conversation_native_input_role_idx"}
                        .issubset(indexes))
        evidence = self.app.memory.writer.access.capture(context, reference)
        self.assertEqual(evidence.source_kind, "human_message")
        self.assertEqual(evidence.speaker_id, context.actor.subject.subject_id)
        self.assertEqual(self.app.memory.writer.access.evidence(context, evidence), "我平时不喝咖啡")
        saved = require(self.app.memory.writer.submit(context, Proposal("add", predicate="饮用偏好",
            object="不喝咖啡", representation="用户自述平时不喝咖啡", evidence=(evidence,)),
            operation_key="native-save"))
        self.assertEqual(saved["state"], "persisted")
        result = self.sources(context)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["excerpt"], "我平时不喝咖啡")
        self.assertEqual(result["items"][0]["delivery_state"], "input_observed")
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())
        self.assertEqual(self.app.runtime.read_all("SELECT part_id FROM conversation_delivery_receipts", ()), ())
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_generated_output_is_excluded_and_only_actual_sent_text_is_recalled(self):
        prepared = await self.prepared(identifier="native-partial-send", text="读完了吗")
        await prepared["native_source_future"]
        observer = self.controller.session.core_reply_observations
        pending = await observer.output(prepared, "我读完了，接下来聊聊后半章", state="output_observed")

        generated = self.app.memory.writer.access.capture(prepared["context"], pending)
        self.assertEqual(generated.source_kind, "observation")

        before = self.sources(prepared["context"], "native-before-send")
        self.assertEqual([item["source_kind"] for item in before["items"]], ["human_message"])
        sent = await observer.output(prepared, "我读完了", state="send_returned")
        self.assertEqual(sent.owner, ASSISTANT_OWNER)
        self.assertNotEqual(sent, pending)
        after = self.sources(prepared["context"], "native-after-send")
        replies = [item for item in after["items"] if item["source_kind"] == "bot_message"]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["excerpt"], "我读完了")
        self.assertEqual(replies[0]["delivery_state"], "send_returned")
        self.assertEqual(self.app.runtime.read_all("SELECT part_id FROM conversation_delivery_receipts", ()), ())

    async def test_intervention_dialogue_contains_only_real_role_replies(self):
        prepared = await self.prepared(identifier="native-intervention-dialogue", text="你早点休息吧")
        await prepared["native_source_future"]
        observer = self.controller.session.core_reply_observations
        await observer.output(prepared, "我先想想", state="output_observed")

        context = prepared["context"]
        before_send = dialogue(self.app.messages, context, self.clock.now(), limit=16)
        self.assertEqual([(item["speaker"], item["text"]) for item in before_send],
                         [("user", "你早点休息吧")])

        await observer.output(prepared, "那我去休息一会儿", state="send_returned")
        after_send = dialogue(self.app.messages, context, self.clock.now(), limit=16)
        self.assertEqual([(item["speaker"], item["text"]) for item in after_send], [
            ("user", "你早点休息吧"), ("assistant", "那我去休息一会儿")])

    async def test_intervention_is_queued_after_input_and_rechecked_after_role_reply(self):
        observer = self.controller.session.core_reply_observations
        queued = []
        observer._queue_intervention = lambda context, ticket, **kwargs: queued.append((ticket, kwargs.get("delay")))

        prepared = await self.prepared(identifier="native-intervention-input-only", text="那件事可以之后再说")
        await prepared["native_source_future"]
        await asyncio.sleep(0)

        self.assertEqual(len(queued), 1)
        input_ticket = queued[0][0]
        await observer.output(prepared, "好，那就改到明天", state="send_returned")
        await asyncio.sleep(0)

        self.assertEqual(len(queued), 2)
        self.assertIsNot(queued[1][0], input_ticket)
        self.assertEqual(queued[1][1], 0.2)

    async def test_withdrawn_native_input_is_unavailable_to_memory(self):
        prepared = await self.prepared(identifier="native-recall-input")
        reference = await prepared["native_source_future"]
        context = prepared["context"]
        notice = MessageRecall.from_scope(context.scope, prepared["event_id"],
                                           context.actor.principal.native_account_id)

        require(self.app.messages.recalls.accept(notice))

        with self.assertRaises(Exception) as raised:
            self.app.memory.writer.access.capture(context, reference)
        self.assertEqual(raised.exception.code, "message_withdrawn")
        self.assertEqual(self.sources(context)["items"], [])

    async def test_episode_and_reflection_selection_include_core_sources_without_reply_batches(self):
        prepared = await self.prepared(identifier="native-reflection-source",
            text="这周我一直在看一本讲天文学的书，晚上通常会做一点笔记；我很喜欢拿里面的例子和你聊天。")
        reference = await prepared["native_source_future"]
        await self.controller.session.core_reply_observations.output(prepared, "这本书的星图很有趣", state="send_returned")
        self.clock.advance(timedelta(seconds=2))
        context = prepared["context"]
        start, end = reference.issued_at - timedelta(seconds=1), self.clock.now()
        manifest = {"start": stamp(start), "end": stamp(end)}

        lines = recent_dialogue_lines(self.app.runtime, self.app.memory.writer.access, context, manifest)
        self.assertEqual({line["speaker"] for line in lines}, {"user", "bot"})
        self.assertTrue(any(line.get("delivery_state") == "send_returned" for line in lines))
        result = require(self.app.memory_reflection.prepare(context, request_id="core-source-reflection",
            start=start, end=end, role_instruction=prepared["instruction"]))
        saved = self.app.runtime.read_one("SELECT manifest_json FROM memory_reflections WHERE batch_id = ?",
                                          (result["batch_id"],))
        selected = json.loads(saved["manifest_json"])["evidence"]
        self.assertEqual({item["source"]["owner"] for item in selected}, {INPUT_OWNER, ASSISTANT_OWNER})
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())

    async def test_diary_material_reads_native_input_and_paginates_without_batch(self):
        first = await self.prepared(identifier="native-diary-1", text="今天读了一章天文学")
        await first["native_source_future"]
        self.clock.advance(timedelta(seconds=1))
        second = await self.prepared(identifier="native-diary-2", text="里面的星图很漂亮")
        await second["native_source_future"]
        context = first["context"]
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        target = JournalContext(JournalKey.at(owner, JournalKind.DIARY, self.clock.now(), timezone="Asia/Shanghai"),
                                context.scope, "Asia/Shanghai")
        producer = self.app.journal_conversation_material_producer

        page = producer.for_day(context, target, limit=1)
        following = producer.for_day(context, target, limit=1, after_id=page.next_cursor)

        self.assertEqual([item.text for item in page.materials], ["对方当时表达：今天读了一章天文学"])
        self.assertEqual([item.text for item in following.materials], ["对方当时表达：里面的星图很漂亮"])
        self.assertTrue(page.next_cursor.startswith("native-observation:"))
        self.assertEqual(self.app.runtime.read_all("SELECT batch_id FROM conversation_batches", ()), ())

    async def test_background_failure_does_not_reject_preparation_and_close_drains_jobs(self):
        observer = self.controller.session.core_reply_observations
        original = observer.owner.capture_input
        observer.owner.capture_input = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("store unavailable"))

        prepared = await self.prepared(identifier="native-observation-failed")

        self.assertIsNone(await prepared["native_source_future"])
        observer.owner.capture_input = original
        working = await self.prepared(identifier="native-observation-drained")
        await observer.close()
        self.assertTrue(working["native_source_future"].done())
        self.assertEqual((await working["native_source_future"]).owner, INPUT_OWNER)


if __name__ == "__main__":
    unittest.main()
