"""Real Content and Screen providers used by core tools and later consumers."""

import asyncio
import base64
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as _host_import
from astrbot.core.agent.message import Message, ToolCall
from mcp.types import CallToolResult

from astrbot_host.core_reply import prepare_core_reply_event
from astrbot_host.core_reply_tools import close_core_reply_tools, inject_core_reply_tools, native_tool_name
from companion_v2.adapters.astrbot.native import NativeConversationInput
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.native_observations import NativeConversationObservations
from companion_v2.execution.models import TaskContext, digest, require
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.screen.configuration import GROUP as SCREEN_GROUP
from companion_v2.screen.models import SCREEN_EXTENSION
from companion_v2.screen.interpretation import screen_interpretation_profile
from tests.native_content_support import NativeContentFixture
from tests.test_astrbot_core_reply import FakeEvent
from tests.test_host_application import HostFixture
from tests.test_management_access import SCOPE
from tests.test_native_screen_flow import NativeScreenFlowTests as _ScreenFixture
from tests.test_role_tool_loop import answered


class NativeProviderCalls:
    def prepare_native(self, text, identifier):
        context = TaskContext(self.important, require(self.identity.resolve_role(SCOPE, observed_at=self.clock.now())),
                              AudienceRef(SCOPE, (self.important.subject,)))
        turn_id = "core-reply:" + digest([context.key, identifier])
        original = NativeConversationInput(identifier, context.actor.principal,
            ConversationRoute(SCOPE, user=context.actor.subject), context.audience, text,
            self.clock.now(), context.role_binding.role, "当前角色的屏幕和写作提示")
        source = NativeConversationObservations(self.app.messages).capture_input(context, original, turn_id=turn_id)
        observed = asyncio.get_running_loop().create_future()
        observed.set_result(source)
        event = FakeEvent()
        prepared = {"context": context, "event_id": identifier, "turn_id": turn_id,
                    "native_input": original, "instruction": original.instruction,
                    "native_source_future": observed}

        async def authorize(value):
            return self.app.tasks.check_context_access(value["context"], action="conversation.reply",
                                                       observed_at=self.clock.now())

        prepare_core_reply_event(event, prepared, authorize=authorize)
        request = NS(func_tool=None, system_prompt=original.instruction)
        inject_core_reply_tools(event, request, application=self.app)
        return event, request, prepared

    async def invoke_native(self, event, request, action, arguments, call_id):
        call = ToolCall(id=call_id, function=ToolCall.FunctionBody(
            name=native_tool_name(action), arguments=json.dumps(arguments)))
        wrapper = NS(context=NS(event=event), messages=[Message(role="assistant", tool_calls=[call])])
        tool = request.func_tool.get_tool(native_tool_name(action))
        self.assertIsNotNone(tool, action)
        return await tool.call(wrapper, **arguments)

    def assert_no_reply_pipeline(self):
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) FROM conversation_batches", ())[0], 0)
        self.assertEqual(self.sent, [])


class CoreContentConsumerTests(NativeProviderCalls, NativeContentFixture, HostFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.create_content_port()
        host = self.host(tool_port=self.native_registry)
        self.content_grants(self.native_registry)
        self.app = (await self.start(host)).application
        self.addAsyncCleanup(close_core_reply_tools, self.app)

    async def test_create_read_continue_adopt_and_retract_through_native_tools(self):
        event, request, prepared = self.prepare_native("一起写一篇关于晚风的故事", "native-content")

        async def operate(action, arguments, call_id):
            output = await self.invoke_native(event, request, "content.work." + action, arguments, call_id)
            result = json.loads(output)
            self.assertEqual(result["state"], "succeeded", (result, self.content_errors))
            return json.loads(result["payload"])["native"]["result"]

        first = (await operate("create", {"title": "晚风", "work_type": "story",
            "chapters": [{"chapter_id": "one", "text": "第一阵晚风。"}]}, "create"))["receipt"]
        original = await operate("read", {"work_id": first["work_id"], "version_id": first["version_id"]}, "read")
        self.assertEqual("".join(segment["text"] for segment in original["segments"]), "第一阵晚风。")
        candidate = (await operate("save_candidate", {"work_id": first["work_id"], "base_revision": 1,
            "base_version": first["version_id"], "chapters": [{"chapter_id": "one", "text": "第一阵晚风。灯亮了。"}]},
            "candidate"))["receipt"]
        await operate("adopt", {"work_id": first["work_id"], "version_id": candidate["version_id"],
                                "expected_revision": 1}, "adopt")
        summary = self.native_registry.content.dashboard_summary(prepared["context"], self.clock.now())
        self.assertEqual((summary["works_count"], summary["candidate_count"]), (1, 1))
        await operate("retract", {"work_id": first["work_id"], "expected_revision": 2}, "retract")
        unavailable = json.loads(await self.invoke_native(event, request, "content.work.read",
            {"work_id": first["work_id"], "version_id": first["version_id"]}, "withdrawn-read"))
        self.assertNotEqual(unavailable["state"], "succeeded")
        self.assertNotIn("第一阵晚风", json.dumps(unavailable, ensure_ascii=False))
        self.assertEqual(self.called, [])
        self.assert_no_reply_pipeline()


class CoreScreenConsumerTests(NativeProviderCalls, HostFixture, unittest.IsolatedAsyncioTestCase):
    create_screen_registry = _ScreenFixture.create_screen_registry
    capture = _ScreenFixture.capture
    consent = _ScreenFixture.consent
    screen_model = _ScreenFixture.screen_model

    def setUp(self):
        super().setUp()
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM capability_descriptors WHERE extension_id=?", (SCREEN_EXTENSION,))
        from tests.test_native_screen_flow import sample_jpeg
        from dataclasses import replace
        self.jpeg, self.captures, self.capture_error = sample_jpeg(), 0, None
        self.provider_directory = self.root.parent / "screen-native-v2"
        self.native_registry = self.create_screen_registry()
        self.providers = tuple(replace(provider, capabilities=("text", "tools", "image")) for provider in self.providers)
        from companion_v2.capabilities import CapabilityAuthorizationState, CapabilityRepository
        self.capabilities = CapabilityRepository(self.runtime)
        self.package = self.native_registry.declarations()[0].descriptor.package
        require(self.capabilities.register_descriptor(self.package, registered_at=self.clock.now()))
        require(self.capabilities.acquire(extension_id=SCREEN_EXTENSION, package_id=self.package.package_id,
            package_version=self.package.package_version, expected_revision=0, observed_at=self.clock.now()))
        require(self.capabilities.set_role_enabled(extension_id=SCREEN_EXTENSION, role=self.window.role, bot_id=SCOPE.bot_id,
            enabled=True, expected_revision=0, observed_at=self.clock.now()))
        for capability in self.package.capabilities:
            self.grant(self.important, SCOPE, capability)
            self.consent(capability, CapabilityAuthorizationState.ACTIVE, 0)
        self.profiles += (screen_interpretation_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="core-screen.v1", fields=configuration_fields(self.profiles))

    async def asyncSetUp(self):
        self.app = (await self.start(self.host(tool_port=self.native_registry))).application
        self.addAsyncCleanup(close_core_reply_tools, self.app)

    async def test_interpretation_schedule_failure_keeps_successful_native_capture(self):
        event, request, _ = self.prepare_native("看看屏幕", "native-screen-observer-error")
        with patch.object(self.app.screen_interpretation, "submit", side_effect=OSError("local observer unavailable")):
            output = await self.invoke_native(event, request, "screen.capture", {}, "capture-observer-error")
        self.assertIsInstance(output, CallToolResult, output)
        self.assertEqual(json.loads(output.content[0].text)["state"], "succeeded")
        self.assertEqual(base64.b64decode(output.content[1].data), self.jpeg)
        self.assertEqual((self.captures, len(self.called)), (1, 0))
        self.assert_no_reply_pipeline()

    async def test_native_capture_returns_original_while_interpretation_runs_in_background(self):
        event, request, prepared = self.prepare_native("看看我屏幕里在做什么", "native-screen")
        context = prepared["context"]
        target = ConfigTarget(SCOPE.installation_id, ConfigLayer.WINDOW, context.role_binding.role, SCOPE)
        settings = require(self.app.configuration.read(context.actor, target=target,
            group_id=SCREEN_GROUP, observed_at=self.clock.now()))
        require(self.app.configuration.patch(context.actor, target=target, group_id=SCREEN_GROUP,
            expected_edit_token=settings.edit_token, changes={SCREEN_GROUP + ".interpretation_enabled": True,
            SCREEN_GROUP + ".journal_material_enabled": True},
            operation=self.operation(SCOPE, owner=SCREEN_GROUP), observed_at=self.clock.now()))
        entered, release = asyncio.Event(), asyncio.Event()

        async def interpretation(envelope):
            self.assertEqual(envelope.original.role_instruction, prepared["instruction"])
            entered.set()
            await release.wait()
            return answered('{"interpretation":"画面里有一个编辑器窗口。"}')

        self.model_behavior = interpretation
        try:
            output = await self.invoke_native(event, request, "screen.capture", {}, "capture")
            self.assertIsInstance(output, CallToolResult, output)
            self.assertEqual(base64.b64decode(output.content[1].data), self.jpeg)
            self.assertEqual(json.loads(output.content[0].text)["state"], "succeeded")
            await asyncio.wait_for(entered.wait(), timeout=10)
            self.assertEqual(self.app.screen_interpretation.results, {})
            self.assert_no_reply_pipeline()
            release.set()
            await self.until(lambda: bool(self.app.screen_interpretation.results))
            anchors = self.runtime.read_all("SELECT feedback_kind FROM screen_feedback_anchors", ())
            self.assertEqual({row["feedback_kind"] for row in anchors}, {"reply", "journal"})
            self.assertEqual(self.captures, 1)
            self.assertEqual(len(self.called), 1)
            self.assert_no_reply_pipeline()
        finally:
            release.set()
