"""Native V2 image operations and immutable originals.

This package never imports the legacy runtime or a private companion plugin.
The host owns permissions, adoption, and platform delivery.
"""

from .owner import NativeImageOwner
from .types import BackendResult, ImageInvocation, NativeImageError, ReferenceImage

__all__ = ["NativeImageOwner", "BackendResult", "ImageInvocation", "NativeImageError", "ReferenceImage"]
