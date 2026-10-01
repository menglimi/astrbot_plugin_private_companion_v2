"""QQ Zone as an installable creation extension.

The split follows the repository rules: this package holds protocol, parsing,
policy and capability wiring that can be imported without AstrBot, while the
HTTP transport, credential acquisition and Dashboard routes live in
``astrbot_host``.
"""

from .configuration import (
    DEFAULTS, GROUP, LIMITS, OWNER, QzoneConfigurationOwner, QzoneSettings,
    configuration_fields, target_for, validate,
)

__all__ = ["DEFAULTS", "GROUP", "LIMITS", "OWNER", "QzoneConfigurationOwner", "QzoneSettings",
           "configuration_fields", "target_for", "validate"]
