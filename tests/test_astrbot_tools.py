from dataclasses import replace
import unittest

from companion_v2.adapters.astrbot.tools import AstrBotToolDeclaration, map_tools
from companion_v2.conversation.tool_loop import LocalRoleTools
from companion_v2.execution.models import TaskError, encode
from companion_v2.model_gateway.models import ToolSpec
from tests.test_external_tools import ExternalFixture, descriptor


class HostTools:
    def __init__(self, declarations, invoke):
        self.items = declarations
        self.current = {item.host_tool_id: item for item in declarations}
        self.called = []
        self.handler = invoke

    def declarations(self):
        return self.items

    def current_declaration(self, host_tool_id):
        return self.current.get(host_tool_id)

    async def invoke(self, host_tool_id, invocation):
        self.called.append((host_tool_id, invocation))
        return await self.handler(invocation)


class AstrBotToolMappingTests(ExternalFixture, unittest.IsolatedAsyncioTestCase):
    def make_extension(self, runtime):
        self.port = HostTools(tuple(AstrBotToolDeclaration("astrbot:" + d.tool.action, d) for d in self.descriptors), self.invoke)
        return map_tools(runtime, self.port)

    async def test_host_mapping_dispatches_exact_tool_with_trusted_context(self):
        self.model_uses()
        await self.generate()
        host_id, invocation = self.port.called[0]
        self.assertEqual(host_id, "astrbot:device.read")
        self.assertEqual(invocation.context, self.context)
        self.assertEqual(invocation.arguments_json, encode({"query": "status"}))
        self.assertEqual(len(self.port.called), 1)

    async def test_unload_and_rebind_invalidate_original_material(self):
        self.model_uses()
        batch = await self.generate()
        original = self.port.current.pop("astrbot:device.read")
        self.assertNotIn("device.read", {s.action for s in self.tools.catalog_for(self.context)})
        self.assertEqual(self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).failure.code,
                         "external_provider_changed")
        self.port.current[original.host_tool_id] = replace(original, descriptor=replace(original.descriptor,
            binding=replace(original.descriptor.binding, generation="host-reloaded")))
        self.assertEqual(self.extension.catalog_for(self.context), (self.descriptors[1].tool,))
        self.assertEqual(len(self.port.called), 1)

    async def test_duplicate_host_id_or_action_is_rejected(self):
        declaration = self.port.items[0]
        for duplicate in (declaration, replace(declaration, host_tool_id="another-host-name")):
            port = HostTools((declaration, duplicate), self.invoke)
            with self.assertRaises(ValueError):
                map_tools(self.runtime, port)

    async def test_extension_cannot_replace_a_builtin_owner(self):
        original = descriptor()
        self.descriptors = (replace(original, tool=replace(original.tool, action="source.read")),)
        _, messages, _ = self.components(self.open_runtime())
        with self.assertRaisesRegex(ValueError, "built-in"):
            LocalRoleTools(messages, external=self.extension)
        self.assertIsNone(messages.tools)

    async def test_unknown_schema_features_and_undeclared_owner_are_rejected(self):
        original = descriptor()
        with self.assertRaises(ValueError):
            replace(original, source_owner="memory")
        with self.assertRaises(ValueError):
            replace(original, tool=ToolSpec("device.read", "Schema requires host normalization", encode({
                "type": "object", "properties": {}, "additionalProperties": False, "$ref": "external.json"})))
        self.assertEqual(self.port.called, [])


if __name__ == "__main__":
    unittest.main()
