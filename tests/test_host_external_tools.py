import asyncio
from dataclasses import replace
import unittest

from companion_v2.adapters.astrbot.tools import AstrBotToolDeclaration
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.external_tools import ExternalToolResponse
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import digest
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.models import SourceRecord
from tests.test_astrbot_tools import HostTools
from tests.test_external_tools import PACKAGE, descriptor, tool_call
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered, requested


class HostExternalTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.invocations = []
        self.device_behavior = None
        self.device = replace(descriptor(), timeout_seconds=5)
        self.tool_port = HostTools((AstrBotToolDeclaration("host:phone", self.device),), self.invoke_device)
        self.capabilities = CapabilityRepository(self.runtime)
        self.capabilities.register_descriptor(PACKAGE, registered_at=NOW).unwrap()
        self.capabilities.acquire(extension_id=PACKAGE.extension_id, package_id=PACKAGE.package_id,
            package_version=PACKAGE.package_version, expected_revision=0, observed_at=NOW).unwrap()
        self.capabilities.set_role_enabled(extension_id=PACKAGE.extension_id, role=self.window.role,
            bot_id=SCOPE.bot_id, enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        self.consent(SCOPE)
        self.capabilities.set_settings(extension_id=PACKAGE.extension_id, scope=SCOPE,
            proactive_enabled=False, thought_weight=0.01, expected_revision=0, observed_at=NOW).unwrap()
        self.model_behavior = self.model_tool

    def consent(self, scope):
        self.capabilities.set_authorization(extension_id=PACKAGE.extension_id, capability_id="device.read",
            subject=self.important.subject, scope=scope, state=CapabilityAuthorizationState.ACTIVE,
            expected_revision=0, observed_at=NOW).unwrap()

    async def model_tool(self, envelope):
        return requested(tool_call()) if not envelope.tool_history else answered("实际收到的手机资料")

    async def invoke_device(self, invocation):
        self.invocations.append(invocation)
        if self.device_behavior:
            await self.device_behavior(invocation)
        source = SourceRef("phone:" + invocation.invocation_id, "device", invocation.context.scope,
                           VersionRef(invocation.invocation_id, 1), self.clock.now())
        body = "最近上报：57%，陪伴应用在后台"
        return ExternalToolResponse(invocation.invocation_id, invocation.context.key, invocation.arguments_hash,
            invocation.descriptor.binding, "succeeded", source=SourceRecord(source, invocation.context.audience, digest(body), body),
            receipt_ref="read:" + invocation.invocation_id)

    async def test_mapped_external_tools_have_reserved_child_capacity_for_two_conversations(self):
        two_entered, release = asyncio.Event(), asyncio.Event()
        async def device(invocation):
            if len(self.invocations) == 2:
                two_entered.set()
            await release.wait()
        self.device_behavior = device
        scope = replace(SCOPE, conversation_id="other-conversation", session_id="other-session", native_scope_id="other")
        self.grant(self.important, scope, "text")
        self.consent(scope)
        host = await self.start(self.host(tool_port=self.tool_port, policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        one = host.receive(self.event()).unwrap()
        two = host.receive(self.event(scope=scope)).unwrap()
        try:
            await asyncio.wait_for(two_entered.wait(), 3)
            self.assertEqual(len(app.active_handles), 4)
            self.assertEqual(self.runtime.read_one("SELECT COUNT(*) n FROM execution_attempts WHERE slot_held = 1", ())["n"], 4)
        finally:
            release.set()
        self.assertEqual((await self.done(app, one))["state"], "complete")
        self.assertEqual((await self.done(app, two))["state"], "complete")
        self.assertEqual(len(self.invocations), 2)
        self.assertEqual(len(self.called), 4)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual({i.context.scope for i in self.invocations}, {SCOPE, scope})
        self.assertTrue(all(e.original.role_instruction == "原角色人格提示" for e in self.called))
        self.assertTrue(all(row["state"] == "succeeded" for row in self.runtime.read_all("SELECT state FROM extension_tool_invocations", ())))

    async def test_shutdown_cancels_parent_and_tool_child_without_new_continuation(self):
        entered = asyncio.Event()
        async def wait(invocation):
            entered.set()
            await asyncio.Event().wait()
        self.device_behavior = wait
        host = await self.start(self.host(tool_port=self.tool_port, policy=ConversationPolicy(0, 0, 180, 0)))
        batch = host.receive(self.event()).unwrap()
        await asyncio.wait_for(entered.wait(), 3)
        self.assertEqual((await host.application.close(grace_seconds=0)).state, "stopped")
        self.assertEqual(host.application.active_handles, ())
        self.assertEqual(self.sent, [])
        new = await self.start(self.host(runtime=self.open_runtime(), tool_port=self.tool_port), 1, 1)
        self.advance(new.application)
        self.assertEqual((await self.done(new.application, batch))["state"], "blocked")
        self.assertEqual(len(self.invocations), 1)
        self.assertEqual(len(self.called), 1)


if __name__ == "__main__":
    unittest.main()
