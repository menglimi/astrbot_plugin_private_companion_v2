"""Native core tools keep Content writing routes and saved version boundaries."""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as host_support
from astrbot.core.agent.message import Message, ToolCall as NativeCall
from astrbot_host.core_reply import prepare_core_reply_event
from astrbot_host.core_reply_observations import CoreReplyObservations
from astrbot_host.core_reply_tools import close_core_reply_tools, inject_core_reply_tools, native_tool_name
from companion_v2.adapters.astrbot.native import NativeConversationInput
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.content.authoring_tasks import DRAFT_KIND, authoring_profiles
from companion_v2.conversation.native_tool_results import operation_rows
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.model_gateway.models import ToolCall
from tests.test_astrbot_core_reply import FakeEvent
from tests.native_content_support import NativeContentFixture
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE
from tests.test_role_tool_loop import answered, requested


class NativeAuthoringFlowTests(NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += authoring_profiles("primary", draft_tokens=87)
        self.registry = FieldRegistry(version="native-authoring-test.v2", fields=configuration_fields(self.profiles))

    async def native_turn(self, host, action, arguments, identifier, *, text=None):
        app = host.application
        self.addAsyncCleanup(close_core_reply_tools, app)
        context = TaskContext(self.important, require(self.identity.resolve_role(SCOPE, observed_at=self.clock.now())),
                              AudienceRef(SCOPE, (self.important.subject,)))

        def access(current):
            return app.tasks.check_context_access(current, action="conversation.reply", observed_at=self.clock.now())

        observer = CoreReplyObservations(SimpleNamespace(application=app, runtime=app.runtime,
            now=self.clock.now, authorize=lambda current: require(access(current))))
        self.addAsyncCleanup(observer.close)
        native_input = NativeConversationInput(identifier, context.actor.principal,
            ConversationRoute(SCOPE, user=context.actor.subject), context.audience,
            text or "请创作并保存作品：" + arguments.get("brief", identifier), self.clock.now(),
            context.role_binding.role, "原角色人格提示")
        turn_id = "core-reply:" + digest([context.key, identifier])
        pending = observer.input(context, native_input, turn_id=turn_id)
        reference = await pending
        self.assertIsNotNone(reference)
        await app.state_maintenance.bind_async(context, native_input.instruction)
        prepared = {"context": context, "event_id": identifier, "turn_id": turn_id,
            "instruction": native_input.instruction, "native_input": native_input, "native_source_future": pending}
        event = FakeEvent()
        prepare_core_reply_event(event, prepared, authorize=lambda _: asyncio.sleep(0, result=access(context)))
        request = SimpleNamespace(func_tool=None, system_prompt=native_input.instruction)
        offered = inject_core_reply_tools(event, request, application=app)
        name = native_tool_name(action)
        call = NativeCall(id=identifier, function=NativeCall.FunctionBody(name=name, arguments=encode(arguments)))
        wrapper = SimpleNamespace(context=SimpleNamespace(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        await observer.phase(prepared, "running")
        return SimpleNamespace(context=context, observer=observer, prepared=prepared, event=event,
            request=request, offered=offered, name=name, wrapper=wrapper, reference=reference, arguments=arguments)

    async def invoke(self, turn, *, complete=True):
        self.assertIn(turn.name, {tool.name for tool in turn.request.func_tool.tools})
        result = json.loads(await turn.request.func_tool.get_tool(turn.name).call(turn.wrapper, **turn.arguments))
        if complete:
            await turn.observer.phase(turn.prepared, "completed")
        self.assertEqual(turn.event.sent, [])
        self.assertEqual(self.runtime.read_all("SELECT * FROM conversation_batches", ()), ())
        self.assertEqual(self.sent, [])
        self.assertTrue(all(item.original.output_format == "content_authoring" for item in self.called))
        return result

    async def test_create_and_continue_use_the_writing_route_and_save_native_versions(self):
        self.authoring_envelopes = []
        first_body = "海边的旧车站亮起一盏灯。" * 430
        continuation_body = "她沿着潮声走去，终于认出了那封信的笔迹。"

        async def model(envelope):
            self.assertEqual(envelope.original.output_format, "content_authoring")
            self.authoring_envelopes.append(envelope)
            self.assertEqual(envelope.original.role_instruction, "原角色人格提示")
            self.assertEqual(envelope.original.reply_actions, ("text",))
            schema = json.loads(envelope.original.response_schema_json)
            if "title" in schema["required"]:
                value = {"title": "潮汐来信", "work_type": "短篇小说", "body": first_body}
            else:
                self.assertIn(first_body, envelope.original.instruction)
                value = {"body": continuation_body}
            return answered(encode(value))

        self.model_behavior = model
        host = await self.content_host()
        self.assertIn(DRAFT_KIND, host.application.router.profiles)
        create_turn = await self.native_turn(host, "content.authoring.create",
            {"brief": "写一个关于海边车站和一封旧信的短篇开头"}, "authoring-create")
        self.assertTrue({"content.authoring.create", "content.authoring.continue"}.issubset(create_turn.offered))
        self.assertEqual({action for action in create_turn.offered if action.startswith("content.work.")},
                         set(self.content_port.manifest()["package"]["capabilities"]))
        continued_tool = create_turn.request.func_tool.get_tool(native_tool_name("content.authoring.continue"))
        self.assertIn("work_title", continued_tool.parameters["properties"])
        self.assertIn("日常讨论、构思或询问不等于创作授权", create_turn.request.system_prompt)
        created = await self.invoke(create_turn)
        self.assertEqual((created["state"], created["effect"]), ("succeeded", "committed"), created)
        self.assertEqual(len(self.authoring_envelopes), 1, (
            [dict(row) for row in self.runtime.read_all(
                "SELECT action,state,effect,result_json FROM conversation_tool_calls", ())],
            self.content_errors,
            [dict(row) for row in self.runtime.read_all(
                "SELECT kind,state,json_extract(record_json,'$.reason') AS reason FROM execution_tasks", ())],
        ))
        self.assertEqual(self.authoring_envelopes[0].max_output_tokens, 87)
        self.assertEqual(self.authoring_envelopes[0].original.output_format, "content_authoring")

        connection = self.content_port.service.repository._connection
        work = connection.execute("SELECT * FROM content_v2_works").fetchone()
        self.assertIsNotNone(work)
        self.work_id = work["work_id"]
        self.assertEqual((work["title"], work["work_type"], work["revision"]),
                         ("潮汐来信", "短篇小说", 1))
        first_version = connection.execute(
            "SELECT * FROM content_v2_versions WHERE work_id=? AND version_id=?",
            (self.work_id, work["head_version"])).fetchone()
        first_chapters = json.loads(first_version["manuscript_json"])
        self.assertEqual(first_chapters[0]["text"], first_body)
        self.assertEqual(first_chapters[0]["title"], "潮汐来信")

        continue_turn = await self.native_turn(host, "content.authoring.continue",
            {"work_title": "潮汐来信", "brief": "让主人公发现寄信人的身份"}, "authoring-continue")
        continued = await self.invoke(continue_turn)
        self.assertEqual((continued["state"], continued["effect"]), ("succeeded", "committed"), continued)
        self.assertEqual(len(self.authoring_envelopes), 2, (
            [dict(row) for row in self.runtime.read_all(
                "SELECT action,state,effect,result_json FROM conversation_tool_calls", ())],
            [dict(row) for row in self.runtime.read_all(
                "SELECT action,state,effect,tool_call_id FROM extension_tool_invocations", ())],
            self.content_errors,
            [dict(row) for row in self.runtime.read_all(
                "SELECT kind,state,json_extract(record_json,'$.reason') AS reason FROM execution_tasks", ())],
        ))
        self.assertEqual(self.authoring_envelopes[1].max_output_tokens, 87)

        work_after = connection.execute("SELECT * FROM content_v2_works WHERE work_id=?",
                                        (self.work_id,)).fetchone()
        self.assertEqual((work_after["revision"], work_after["head_version"]),
                         (1, work["head_version"]))
        versions = connection.execute("SELECT * FROM content_v2_versions WHERE work_id=? ORDER BY created_at",
                                      (self.work_id,)).fetchall()
        self.assertEqual(len(versions), 2)
        candidate = next(row for row in versions if row["version_id"] != work["head_version"])
        self.assertEqual((candidate["base_revision"], candidate["base_version"]),
                         (1, work["head_version"]))
        candidate_chapters = json.loads(candidate["manuscript_json"])
        self.assertEqual(candidate_chapters[0]["chapter_id"], first_chapters[0]["chapter_id"])
        self.assertEqual(candidate_chapters[0]["title"], first_chapters[0]["title"])
        self.assertEqual(candidate_chapters[0]["text"], first_body)
        self.assertEqual(candidate_chapters[-1]["text"], continuation_body)

        operations = sorted(operation_rows(self.runtime, create_turn.context, {
            "content.work.create", "content.work.list", "content.work.describe", "content.work.read", "content.work.save_candidate"}),
            key=lambda row: row["action"])
        self.assertTrue(all(row["execution_path"] == "astrbot_core" for row in operations))
        self.assertEqual([(row["action"], row["state"], row["effect"]) for row in operations], [
            ("content.work.create", "succeeded", "committed"),
            ("content.work.describe", "succeeded", "none"),
            ("content.work.list", "succeeded", "none"),
            ("content.work.read", "succeeded", "none"),
            ("content.work.read", "succeeded", "none"),
            ("content.work.save_candidate", "succeeded", "committed"),
        ])
        read_calls = [row for row in operations if row["action"] == "content.work.read"
                      and row["tool_call_id"].startswith("content-authoring-subcall:")]
        read_steps = sorted(int(row["tool_call_id"].split(":", 2)[1]) for row in read_calls)
        self.assertEqual(read_steps, [3, 4])

        first_summary, first_material = host.application.tools.external.snapshot(
            operations[0], create_turn.context, self.clock.now())
        self.assertEqual(first_summary["effect"], "committed")
        self.assertIsNotNone(first_material)
        with self.assertRaises(TaskError):
            host.application.tools.external.snapshot(operations[0], replace(create_turn.context, actor=self.core), self.clock.now())

        adopt_turn = await self.native_turn(host, "content.work.adopt",
            {"work_id": self.work_id, "version_id": candidate["version_id"], "expected_revision": 1}, "authoring-adopt",
            text="采用潮汐来信刚才保存的候选稿")
        adopted = await self.invoke(adopt_turn)
        self.assertEqual((adopted["state"], adopted["effect"]), ("succeeded", "committed"), adopted)
        adopted_work = connection.execute("SELECT * FROM content_v2_works WHERE work_id=?", (self.work_id,)).fetchone()
        self.assertEqual((adopted_work["revision"], adopted_work["head_version"]), (2, candidate["version_id"]))
        self.assertEqual(len(self.authoring_envelopes), 2)

        host.application.messages.sources.revoke(first_material.source, expected_governance_revision=1,
                                                  observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError):
            host.application.tools.external.snapshot(operations[0], create_turn.context, self.clock.now())

    async def test_two_authoring_calls_in_one_native_turn_keep_separate_receipts_and_replay(self):
        async def model(envelope):
            self.assertEqual(envelope.original.output_format, "content_authoring")
            return answered(encode({"title": "拟定标题", "work_type": "短篇小说", "body": "车站的灯亮了。"}))

        self.model_behavior = model
        host = await self.content_host()
        first_arguments = {"title": "第一篇", "brief": "写车站并保存"}
        second_arguments = {"title": "第二篇", "brief": "写海边并保存"}
        turn = await self.native_turn(host, "content.authoring.create", first_arguments, "two-works",
                                      text="请分别写一篇车站故事和海边故事，并都保存为作品")
        second_call = NativeCall(id="two-works-second", function=NativeCall.FunctionBody(
            name=turn.name, arguments=encode(second_arguments)))
        turn.wrapper.messages[0].tool_calls.append(second_call)
        first = await self.invoke(turn, complete=False)
        self.assertEqual((first["state"], first["effect"]), ("succeeded", "committed"), first)
        turn.arguments = second_arguments
        second = await self.invoke(turn, complete=False)
        self.assertEqual((second["state"], second["effect"]), ("succeeded", "committed"), second)
        self.assertNotEqual(first["work_id"], second["work_id"])

        for arguments, original in ((first_arguments, first), (second_arguments, second)):
            turn.arguments = arguments
            replay = await self.invoke(turn, complete=False)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["work_id"], original["work_id"])
            self.assertNotIn("material_state", replay)
        await turn.observer.phase(turn.prepared, "completed")
        self.assertEqual(len(self.called), 2)
        self.assertEqual(self.content_port.service.repository._connection.execute(
            "SELECT COUNT(*) FROM content_v2_works").fetchone()[0], 2)
        self.assertEqual(len(operation_rows(self.runtime, turn.context, {"content.work.create"})), 2)

    async def test_create_grant_revoked_during_writing_prevents_save_and_removes_the_core_tool(self):
        async def model(envelope):
            CapabilityRepository(self.runtime).set_authorization(extension_id="content", capability_id="content.work.create",
                subject=self.important.subject, scope=SCOPE, state=CapabilityAuthorizationState.REVOKED,
                expected_revision=1, observed_at=self.clock.now()).unwrap()
            return answered(encode({"title": "失去授权的草稿", "work_type": "短篇小说", "body": "不应保存。"}))

        self.model_behavior = model
        host = await self.content_host()
        turn = await self.native_turn(host, "content.authoring.create", {"brief": "写作并保存"}, "revoked-create")
        result = await self.invoke(turn)
        self.assertEqual((result["state"], result["effect"]), ("failed", "none"), result)
        self.assertEqual(self.content_port.service.repository._connection.execute(
            "SELECT COUNT(*) FROM content_v2_works").fetchone()[0], 0)
        self.assertEqual(operation_rows(self.runtime, turn.context, {"content.work.create"}), ())
        offered = inject_core_reply_tools(turn.event, turn.request, application=host.application)
        self.assertNotIn("content.authoring.create", offered)
        self.assertNotIn("content.work.create", offered)
        self.assertEqual(len(self.called), 1)

    async def test_withdrawal_during_writing_discards_the_draft_and_preserves_actual_usage(self):
        async def model(envelope):
            host.application.messages.sources.revoke(envelope.original.event.source, expected_governance_revision=1,
                                                      observed_at=self.clock.now()).unwrap()
            return answered(encode({"title": "撤回的请求", "work_type": "短篇小说", "body": "不应保存。"}))

        self.model_behavior = model
        host = await self.content_host()
        turn = await self.native_turn(host, "content.authoring.create", {"brief": "写作并保存"}, "withdrawn-writing")
        result = await self.invoke(turn)
        self.assertEqual((result["state"], result["effect"]), ("failed", "none"), result)
        self.assertEqual(result["code"], "source_revoked")
        self.assertEqual(self.content_port.service.repository._connection.execute(
            "SELECT COUNT(*) FROM content_v2_works").fetchone()[0], 0)
        call = self.runtime.read_one("SELECT state,actual_tokens,receipt_ref FROM model_calls "
                                     "WHERE task_id LIKE 'content-authoring-%'", ())
        self.assertEqual(call["state"], "discarded")
        self.assertIsNotNone(call["actual_tokens"])
        self.assertIsNotNone(call["receipt_ref"])

    async def test_unknown_create_receipt_is_not_repeated_with_the_same_or_new_call_id(self):
        async def model(envelope):
            return answered(encode({"title": "回执丢失的作品", "work_type": "短篇小说", "body": "保存结果待确认。"}))

        self.model_behavior = model
        host = await self.content_host()
        provider_calls = []
        original = self.content_port.execute

        async def lose_receipt(request, *, before_dispatch):
            provider_calls.append(request)
            await original(request, before_dispatch=before_dispatch)
            raise TaskError("synthetic_receipt_lost", "the committed operation's response did not return")

        arguments = {"brief": "写作并保存"}
        turn = await self.native_turn(host, "content.authoring.create", arguments, "unknown-writing")
        with patch.object(self.content_port, "execute", side_effect=lose_receipt):
            unknown = await self.invoke(turn, complete=False)
            self.assertEqual((unknown["state"], unknown["effect"]), ("unknown", "unknown"), unknown)
            replay = await self.invoke(turn, complete=False)
            self.assertEqual((replay["state"], replay["effect"]), ("unknown", "unknown"), replay)
            new_turn = await self.native_turn(host, "content.authoring.create", arguments, "unknown-writing-new-id")
            blocked = await self.invoke(new_turn)
            self.assertEqual((blocked["state"], blocked["effect"], blocked["code"]),
                             ("failed", "none", "external_effect_unresolved"), blocked)
        await turn.observer.phase(turn.prepared, "completed")
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.content_port.service.repository._connection.execute(
            "SELECT COUNT(*) FROM content_v2_works").fetchone()[0], 1)


class LegacyAuthoringCompatibilityTests(NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += authoring_profiles("primary", draft_tokens=87)
        self.registry = FieldRegistry(version="legacy-authoring-test.v1", fields=configuration_fields(self.profiles))

    async def test_legacy_conversation_actions_do_not_block_the_dedicated_writing_child(self):
        async def model(envelope):
            if envelope.original.output_format == "content_authoring":
                self.assertEqual(envelope.original.reply_actions, ("text",))
                return answered(encode({"title": "兼容草稿", "work_type": "短篇小说", "body": "车站的灯亮了。"}))
            if not envelope.tool_history:
                self.assertTrue(any(action != "text" for action in envelope.original.reply_actions))
                return requested(ToolCall("legacy-writing", "content.authoring.create", encode({"brief": "写作并保存"})))
            return answered("已保存作品。")

        self.model_behavior = model
        host = await self.content_host()
        batch = host.receive(self.event("legacy-writing", text="请创作并保存作品")).unwrap()
        result = await self.done(host.application, batch, seconds=45)
        self.assertEqual(result["state"], "complete", self.content_errors)
        self.assertEqual(self.content_port.service.repository._connection.execute(
            "SELECT COUNT(*) FROM content_v2_works").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
