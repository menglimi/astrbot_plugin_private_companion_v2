"""Real internal Image owner and bundled lease with local backend bytes."""

from types import SimpleNamespace as NS

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.builtins import MANAGED_EXTENSIONS
from astrbot_host.native_extensions.images import image_result_handler
from astrbot_host.native_extensions.image_native.owner import NativeImageOwner
from astrbot_host.native_extensions.image_native.adapter import NativeImageProvider
from astrbot_host.native_extensions.image_native.types import BackendResult
from companion_v2.product import PRODUCT_VERSION
from tests.test_conversation_images import image_bytes
from tests.native_internal_support import internal_lease


def image_types():
    return NativeImageOwner, NativeImageProvider, BackendResult


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
        self.image_port = provider_type(self.image_owner, package_version=PRODUCT_VERSION, artifact_hash="synthetic-image-package")
        self.image_lease = internal_lease(self.image_port)
        self.image_context = NS(get_all_stars=lambda: ())
        handlers = {action: lambda invocation, result: image_result_handler(invocation, result, observed_at=now())
                    for action in ("image.generate", "image.edit", "image.mask_edit")}
        registry = NativeExtensionRegistry(self.image_context, result_handlers=handlers, now=now,
            bundled_extensions=(self.image_lease,), managed_extensions=MANAGED_EXTENSIONS)
        self.addAsyncCleanup(registry.aclose)
        self.assertEqual(len(registry.declarations()), 3, registry.issues)
        return registry
