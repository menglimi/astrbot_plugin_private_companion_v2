"""Real optional Image owner with local bytes and an ordinary native registry."""

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.images import image_result_handler
from tests.test_conversation_images import image_bytes


def image_types():
    plugin_parent = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, plugin_parent)
    try:
        prefix = "astrbot_plugin_image_companion.image_companion.native_v2."
        owner = importlib.import_module(prefix + "owner").NativeImageOwner
        provider = importlib.import_module(prefix + "adapter").NativeImageProvider
        result = importlib.import_module(prefix + "types").BackendResult
        return owner, provider, result
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("astrbot_plugin_image_companion"):
            raise unittest.SkipTest("native integration requires the optional Image package") from error
        raise
    finally:
        sys.path.remove(plugin_parent)


class ImageBackend:
    def __init__(self, result_type):
        self.result_type, self.calls = result_type, []
        self.operations = ("generate", "edit", "mask_edit")
        self.unknown = False
        self.closed = False

    async def execute(self, invocation, references, before_dispatch):
        await before_dispatch()
        self.calls.append((invocation, references))
        if self.unknown:
            raise ConnectionError("synthetic response lost after dispatch")
        return self.result_type(images=(image_bytes("blue" if references else "red"),),
                                receipt={"backend": "synthetic"})

    async def recover(self, locator, authorize):
        raise AssertionError("unknown operations have no locator to poll")

    async def close(self):
        self.closed = True


class NativeImageFixture:
    def create_image_port(self, directory, now):
        owner_type, provider_type, result_type = image_types()
        self.image_backend = ImageBackend(result_type)
        self.image_owner = owner_type(directory, self.image_backend)
        self.addAsyncCleanup(self.image_owner.close)
        self.image_port = provider_type(self.image_owner, package_version="0.5.0", artifact_hash="synthetic-image-package")
        self.image_star = NS(root_dir_name="astrbot_plugin_image_companion", name="astrbot_plugin_image_companion",
            version="0.5.0", activated=True, star_cls=NS(extension_api=NS(companion_v2_native=lambda: self.image_port)))
        self.image_context = NS(get_all_stars=lambda: [self.image_star])
        handlers = {action: lambda invocation, result: image_result_handler(invocation, result, observed_at=now())
                    for action in ("image.generate", "image.edit", "image.mask_edit")}
        registry = NativeExtensionRegistry(self.image_context, result_handlers=handlers, now=now)
        self.addCleanup(registry.close)
        self.assertEqual(len(registry.declarations()), 3, registry.issues)
        return registry
