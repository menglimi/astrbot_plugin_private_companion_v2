"""Synthetic-model end-to-end coverage for native Content authoring."""

import json
import unittest

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.content.authoring_tasks import DRAFT_KIND, authoring_profiles
from companion_v2.execution.models import encode
from companion_v2.model_gateway.routing import configuration_fields
from tests.native_content_support import NativeContentFixture
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered, requested
from companion_v2.model_gateway.models import ToolCall


class NativeAuthoringFlowTests(NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    async def test_create_and_continue_use_the_writing_route_and_save_native_versions(self):
        self.profiles += authoring_profiles("primary", draft_tokens=87)
        self.registry = FieldRegistry(version="native-authoring-test.v1",
                                      fields=configuration_fields(self.profiles))
        self.phase = "create"
        self.authoring_envelopes = []
        first_body = "海边的旧车站亮起一盏灯。" * 430
        continuation_body = "她沿着潮声走去，终于认出了那封信的笔迹。"

        async def model(envelope):
            if envelope.original.output_format == "content_authoring":
                self.authoring_envelopes.append(envelope)
                self.assertEqual(envelope.original.role_instruction, "原角色人格提示")
                schema = json.loads(envelope.original.response_schema_json)
                if "title" in schema["required"]:
                    value = {"title": "潮汐来信", "work_type": "短篇小说", "body": first_body}
                else:
                    value = {"body": continuation_body}
                return answered(encode(value))

            if not envelope.tool_history:
                actions = {tool.action for tool in envelope.tools}
                if self.phase == "create":
                    self.assertIn("content.authoring.create", actions)
                    return requested(ToolCall("author-new-work", "content.authoring.create",
                        encode({"brief": "写一个关于海边车站和一封旧信的短篇开头"})))
                self.assertIn("content.authoring.continue", actions)
                continue_tool = next(tool for tool in envelope.tools
                                     if tool.action == "content.authoring.continue")
                self.assertIn("work_title", json.loads(continue_tool.parameters_json)["properties"])
                return requested(ToolCall("author-continue-work", "content.authoring.continue",
                    encode({"work_title": "潮汐来信", "brief": "让主人公发现寄信人的身份"})))
            return answered("作品已保存到 Content。")

        self.model_behavior = model
        host = await self.content_host()
        self.assertIn(DRAFT_KIND, host.application.router.profiles)
        created_batch = host.receive(self.event("authoring-create")).unwrap()
        created = await self.done(host.application, created_batch, seconds=45)
        self.assertEqual(created["state"], "complete", self.content_errors)
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

        self.phase = "continue"
        continued_batch = host.receive(self.event("authoring-continue")).unwrap()
        continued = await self.done(host.application, continued_batch, seconds=45)
        self.assertEqual(continued["state"], "complete", self.content_errors)
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

        operations = self.runtime.read_all(
            "SELECT action,state,effect FROM extension_tool_invocations "
            "WHERE action IN ('content.work.create','content.work.list','content.work.describe',"
            "'content.work.read','content.work.save_candidate') ORDER BY action", ())
        self.assertEqual([(row["action"], row["state"], row["effect"]) for row in operations], [
            ("content.work.create", "succeeded", "committed"),
            ("content.work.describe", "succeeded", "none"),
            ("content.work.list", "succeeded", "none"),
            ("content.work.read", "succeeded", "none"),
            ("content.work.read", "succeeded", "none"),
            ("content.work.save_candidate", "succeeded", "committed"),
        ])
        read_calls = self.runtime.read_all(
            "SELECT tool_call_id FROM extension_tool_invocations WHERE action='content.work.read' "
            "AND tool_call_id LIKE 'content-authoring-subcall:%'", ())
        read_steps = sorted(int(row["tool_call_id"].split(":", 2)[1]) for row in read_calls)
        self.assertEqual(read_steps, [3, 4])


if __name__ == "__main__":
    unittest.main()
