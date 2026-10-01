"""Native declarations share the model catalog budget without truncating tools."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.discovery import discover
from companion_v2.adapters.astrbot.tools import map_tools
from companion_v2.capabilities.native import parse_manifest
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


class NativeToolCatalogTests(unittest.TestCase):
    def test_single_provider_accepts_64_complete_declarations_and_rejects_65(self):
        self.assertEqual(MAX_TOOL_CATALOG, 64)
        document = declaration(64)
        parsed = parse_manifest(document, plugin_id=document["plugin_id"], version="0.5.0")
        self.assertEqual([tool["action"] for tool in parsed.tools], [tool["action"] for tool in document["tools"]])
        overflowing = declaration(65)
        with self.assertRaisesRegex(ValueError, "bounded complete declaration"):
            parse_manifest(overflowing, plugin_id=overflowing["plugin_id"], version="0.5.0")

    def test_aggregate_native_directory_accepts_64_and_rejects_65_without_partial_catalog(self):
        for size in (64, 65):
            with self.subTest(size=size):
                context = SimpleNamespace(get_all_stars=lambda: (star(32), star(size - 32, "second")))
                entries, issues = discover(context)
                if size == 64:
                    self.assertEqual(len(entries), 64)
                    self.assertEqual(issues, ())
                    self.assertEqual(len({item[0].descriptor.tool.action for item in entries.values()}), 64)
                else:
                    self.assertEqual(entries, {})
                    self.assertEqual(issues, (("native", "native_catalog_capacity"),))

    def test_host_mapping_and_external_registry_keep_all_64_and_reject_65(self):
        loaded = star(64)
        context = SimpleNamespace(get_all_stars=lambda: (loaded,))
        native = NativeExtensionRegistry(context, result_handlers={})
        self.addCleanup(native.close)
        with TemporaryDirectory(prefix="native-tool-catalog-") as temporary:
            runtime = StorageRuntime.open(data_root=Path(temporary), installation_id="native-tool-catalog")
            try:
                mapped = map_tools(runtime, native)
                self.assertEqual(len(mapped.providers), 64)
                self.assertEqual(set(mapped.providers), {item.descriptor.tool.action for item in native.declarations()})
                original = native.declarations()[0]
                extra_descriptor = replace(original.descriptor,
                    tool=replace(original.descriptor.tool, action="catalog.overflow"))
                extra = replace(original, host_tool_id="native:overflow", descriptor=extra_descriptor)
                with self.assertRaisesRegex(ValueError, "bounded unique trusted"):
                    map_tools(runtime, DeclaredPort(native.declarations() + (extra,)))
                providers = tuple(mapped.providers.values())
                with self.assertRaisesRegex(ValueError, "bounded tuple"):
                    ExternalToolExecutor(runtime, providers + (replace(providers[0], descriptor=extra_descriptor),))
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
