"""Stable identity, personality and world canon shared by one role."""

from .configuration import (
    GROUP,
    OWNER,
    RoleProfileConfigurationOwner,
    configuration_fields,
    target_for,
)
from .context import ConversationRoleProfileContext

__all__ = [
    "ConversationRoleProfileContext",
    "GROUP",
    "OWNER",
    "RoleProfileConfigurationOwner",
    "configuration_fields",
    "target_for",
]
