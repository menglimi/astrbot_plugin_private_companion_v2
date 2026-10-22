"""Role-level cross-window presence and attention metadata."""

from .service import RoleAwareness
from .store import RoleAwarenessStore

__all__ = ["RoleAwareness", "RoleAwarenessStore"]
