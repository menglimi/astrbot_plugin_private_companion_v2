"""Installation tool directories are independent of a model request's budget."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.discovery import discover
from companion_v2.adapters.astrbot.tools import CompositeAstrBotToolPort, QzoneToolPort, map_tools
from companion_v2.capabilities.native import MAX_DOCUMENT_BYTES, parse_manifest
from companion_v2.conversation.external_tools import ExternalToolExecutor
from companion_v2.model_gateway.models import MAX_TOOL_CATALOG
from companion_v2.storage.runtime import StorageRuntime
from tests.test_native_extensions_registry import Port, Star
from tests.test_native_provider_contract import manifest


def declaration(count, prefix="first"):
    document = manifest()
    plugin_id = "astrbot_plugin_catalog_" + prefix
    document.update(plugin_id=plugin_id, provider_id="catalog." + prefix)
    document["package"].update(package_id=plugin_id, extension_id="catalog." + prefix)
    template = document["tools"][0]
    document["tools"] = [{**deepcopy(template), "action": f"catalog.{prefix}.{i}"} for i in range(count)]
    return document


def star(count, prefix="first"):
    port = Port()
    port.document = declaration(count, prefix)
    loaded = Star(port)
    loaded.root_dir_name = loaded.name = port.document["plugin_id"]
    return loaded


class DeclaredPort:
    def __init__(self, entries):
        self.entries = entries

    def declarations(self):
        return self.entries

    def current_declaration(self, host_tool_id):
        return next((item for item in self.entries if item.host_tool_id == host_tool_id), None)

    async def invoke(self, *args):
        raise AssertionError("catalog verification does not dispatch providers")


class NativeToolCatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_single_provider_keeps_complete_declarations_beyond_a_model_request(self):
        for size in (MAX_TOOL_CATALOG, MAX_TOOL_CATALOG + 1, 2 * MAX_TOOL_CATALOG):
            with self.subTest(size=size):
                document = declaration(size)
                parsed = parse_manifest(document, plugin_id=document["plugin_id"], version="0.5.0")
                self.assertEqual([tool["action"] for tool in parsed.tools],
                                 [tool["action"] for tool in document["tools"]])

    def test_manifest_retains_byte_budget_and_requires_nonempty_unique_actions(self):
        oversized = declaration(1)
        oversized["tools"][0]["description"] = "x" * MAX_DOCUMENT_BYTES
        with self.assertRaisesRegex(ValueError, "byte budget"):
            parse_manifest(oversized, plugin_id=oversized["plugin_id"], version="0.5.0")
        for invalid in (declaration(0), declaration(2)):
            if invalid["tools"]:
                invalid["tools"][1]["action"] = invalid["tools"][0]["action"]
            with self.assertRaises(ValueError):
                parse_manifest(invalid, plugin_id=invalid["plugin_id"], version="0.5.0")

    def test_aggregate_native_directory_keeps_every_attested_provider(self):
        for size in (MAX_TOOL_CATALOG, MAX_TOOL_CATALOG + 1, 2 * MAX_TOOL_CATALOG + 1):
            with self.subTest(size=size):
                context = SimpleNamespace(get_all_stars=lambda: (star(32), star(size - 32, "second")))
                entries, issues = discover(context)
                self.assertEqual(len(entries), size)
                self.assertEqual(issues, ())
                expected = {f"catalog.first.{i}" for i in range(32)} | {
                    f"catalog.second.{i}" for i in range(size - 32)}
                self.assertEqual({item[0].descriptor.tool.action for item in entries.values()}, expected)

    def test_host_mapping_and_external_registry_keep_all_installed_tools(self):
        size = MAX_TOOL_CATALOG + 1
        loaded = star(size)
        context = SimpleNamespace(get_all_stars=lambda: (loaded,))
        native = NativeExtensionRegistry(context, result_handlers={})
        self.addCleanup(native.close)
        with TemporaryDirectory(prefix="native-tool-catalog-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary), installation_id="native-tool-catalog")
            try:
                mapped = map_tools(runtime, native)
                self.assertEqual(len(mapped.providers), size)
                self.assertEqual(set(mapped.providers), {item.descriptor.tool.action for item in native.declarations()})
                original = native.declarations()[0]
                extra_descriptor = replace(original.descriptor,
                    tool=replace(original.descriptor.tool, action="catalog.overflow"))
                extra = replace(original, host_tool_id="native:overflow", descriptor=extra_descriptor)
                extended = map_tools(runtime, DeclaredPort(native.declarations() + (extra,)))
                self.assertEqual(set(extended.providers), {*mapped.providers, "catalog.overflow"})
                providers = tuple(mapped.providers.values())
                extended = ExternalToolExecutor(runtime, providers + (replace(providers[0], descriptor=extra_descriptor),))
                self.assertEqual(set(extended.providers), {*mapped.providers, "catalog.overflow"})
            finally:
                runtime.close()

    async def test_composition_preserves_qzone_and_dispatches_tail_tool_to_its_original_port(self):
        entries, issues = discover(SimpleNamespace(get_all_stars=lambda: (star(MAX_TOOL_CATALOG + 1),)))
        self.assertEqual(issues, ())
        native = DeclaredPort(tuple(item[0] for item in entries.values()))
        native.invoke = AsyncMock(return_value="original-port-result")
        qzone = QzoneToolPort(object())
        composite = CompositeAstrBotToolPort(native, qzone)
        self.assertEqual(composite.declarations(), native.declarations() + qzone.declarations())
        tail = native.declarations()[-1]
        self.assertEqual(composite.current_declaration(tail.host_tool_id), tail)
        invocation = object()
        self.assertEqual(await composite.invoke(tail.host_tool_id, invocation), "original-port-result")
        native.invoke.assert_awaited_once_with(tail.host_tool_id, invocation)
        native.entries = native.entries[:-1]
        self.assertIsNone(composite.current_declaration(tail.host_tool_id))
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            await composite.invoke(tail.host_tool_id, invocation)
        native.invoke.assert_awaited_once()
        with self.assertRaisesRegex(ValueError, "unique identities"):
            CompositeAstrBotToolPort(native, native)


if __name__ == "__main__":
    unittest.main()
