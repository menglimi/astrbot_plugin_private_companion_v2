"""Assemble the real bundled lease contract without independent plugin Stars."""

from types import SimpleNamespace

from astrbot_host.native_extensions import NativeExtensionRegistry
from astrbot_host.native_extensions.builtins import BundledNativeLease, MANAGED_EXTENSIONS
from companion_v2.capabilities.models import FurnitureDescriptor


def internal_lease(port):
    manifest = port.manifest()
    extension_id = manifest["package"]["extension_id"]
    return BundledNativeLease(manifest["plugin_id"], port,
        furniture=FurnitureDescriptor(extension_id, extension_id, extension_id, extension_id))


def internal_registry(*ports, **options):
    return NativeExtensionRegistry(SimpleNamespace(get_all_stars=lambda: ()),
        bundled_extensions=tuple(internal_lease(port) for port in ports),
        managed_extensions=MANAGED_EXTENSIONS, **options)
