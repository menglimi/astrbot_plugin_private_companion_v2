"""Role reference material: registrations, digest checks and the wardrobe.

C2-1/C2-2 shared layer. A registration never carries the bytes; ``verify_asset`` is
the point where an asserted SHA-256 is checked against what the owner actually
still holds, so material that changed after registration is refused instead of
quietly influencing a generation.
"""

from .models import (ContentDigest, ReferenceAsset, ReferenceKind, ReferenceRole,
                     ReferenceSource, ReferenceState, WardrobeItem)
from .repositories import ReferenceAssetRepository

__all__ = [
    "ContentDigest", "ReferenceAsset", "ReferenceAssetRepository", "ReferenceKind",
    "ReferenceRole", "ReferenceSource", "ReferenceState", "WardrobeItem",
]
