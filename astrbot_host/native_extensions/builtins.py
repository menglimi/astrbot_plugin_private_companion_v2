"""First-party optional providers packaged with Companion V2."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from companion_v2.capabilities.models import FurnitureDescriptor
from companion_v2.capabilities.native import parse_manifest
from companion_v2.product import PRODUCT_VERSION

from .discovery import declarations_for_manifest
from .image_native.adapter import PLUGIN_ID as IMAGE_PACKAGE_ID
from .image_native.extension import ImageExtensionAPI
from .screen_provider import NativeScreenProvider, PLUGIN_ID as SCREEN_PACKAGE_ID


IMAGE_EXTENSION_ID = "image"
SCREEN_EXTENSION_ID = "companion.screen.native"
LEGACY_SCREEN_EXTENSION_ID = "companion.screen"
MANAGED_EXTENSIONS = frozenset({IMAGE_EXTENSION_ID, SCREEN_EXTENSION_ID, LEGACY_SCREEN_EXTENSION_ID})


class BundledNativeLease:
    def __init__(self, package_id, port, *, api=None, furniture):
        self.port = port
        self.api = api
        self.star = None
        self.instance = api or port
        self._closed = False
        package_version = PRODUCT_VERSION
        manifest = parse_manifest(port.manifest(), plugin_id=package_id, version=package_version)
        package = replace(manifest.package, furniture=(furniture,))
        self.manifest = replace(manifest, package=package)

    def current(self, _context):
        return not self._closed and not getattr(self.port, "_closed", False)

    def declarations(self):
        return declarations_for_manifest(self.manifest)

    def close(self):
        if self._closed:
            return
        self._closed = True
        close = getattr(self.api, "close", None) or getattr(self.port, "close", None)
        if callable(close):
            close()


def create_bundled_extensions(data_root: Path, *, now=None):
    root = Path(data_root).resolve()
    leases, issues = [], []
    try:
        image_api = ImageExtensionAPI(data_root=root, config_path=root / "extensions" / "image" / "config.json",
                                      version=PRODUCT_VERSION)
        image_port = image_api.companion_v2_native()
        leases.append(BundledNativeLease(IMAGE_PACKAGE_ID, image_port, api=image_api,
            furniture=FurnitureDescriptor("image", IMAGE_EXTENSION_ID, "画面工作室", "image")))
    except Exception:
        issues.append((IMAGE_PACKAGE_ID, "native_configuration_invalid"))
    try:
        screen_port = NativeScreenProvider(root / "extensions" / "screen", version=PRODUCT_VERSION, now=now)
        leases.append(BundledNativeLease(SCREEN_PACKAGE_ID, screen_port,
            furniture=FurnitureDescriptor("screen", SCREEN_EXTENSION_ID, "屏幕台", "screen")))
    except Exception:
        issues.append((SCREEN_PACKAGE_ID, "native_extension_unavailable"))
    return tuple(leases), tuple(issues)
