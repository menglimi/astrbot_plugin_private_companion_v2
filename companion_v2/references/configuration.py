"""Whether a role may use registered reference material at all.

The group decides what the role may put into a generation; it never says where a
picture lives. Reference material is a registered asset (``companion_v2/references``),
so nothing here is a file path — a path in configuration text would bypass the
ownership and visibility checks the asset layer exists to enforce.

Both switches default to off, so an installation that never touches them behaves
exactly as it did before this group existed.
"""

from __future__ import annotations

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import require


GROUP = "photo.reference"
OWNER = GROUP
LAYER = (ConfigLayer.ROLE,)

DEFAULTS = {
    # Off until an operator turns reference material on for this role.
    "enabled": False,
    # The daily-outfit path stays separate: agreeing to reference pictures is not
    # agreement to a picture every day.
    "daily_outfit_enabled": False,
    # How often the same outfit may come round again.
    "daily_outfit_rotation_days": 14,
}
LIMITS = {"daily_outfit_rotation_days": (1, 365)}
BOOLEAN_FIELDS = ("enabled", "daily_outfit_enabled")
INTEGER_FIELDS = tuple(LIMITS)


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE,
                        context.role_binding.role, bot_id=context.scope.bot_id)


def validate(values):
    if type(values) is not dict or set(values) != set(DEFAULTS):
        raise ConfigurationError("photo_reference_configuration_invalid",
                                 "provide the declared reference settings")
    if any(type(values[name]) is not bool for name in BOOLEAN_FIELDS):
        raise ConfigurationError("photo_reference_configuration_invalid",
                                 "reference switches must be boolean")
    for name in INTEGER_FIELDS:
        low, high = LIMITS[name]
        value = values[name]
        if type(value) is not int or isinstance(value, bool) or not low <= value <= high:
            raise ConfigurationError("photo_reference_configuration_invalid",
                                     f"{name} must be an integer from {low} to {high}")
    return values


def configuration_fields():
    return tuple(FieldDefinition(GROUP + "." + name, GROUP, GROUP,
        ValueKind.BOOLEAN if type(value) is bool else ValueKind.INTEGER, value,
        layers=LAYER, owner_id=OWNER,
        **({"minimum": LIMITS[name][0], "maximum": LIMITS[name][1]} if name in LIMITS else {}))
        for name, value in DEFAULTS.items())


class ReferenceConfigurationOwner(SparseConfigurationOwner):
    owner_id = OWNER

    def preview_set(self, target, fields, *, changes):
        result = super().preview_set(target, fields, changes=changes)
        validate({key.removeprefix(GROUP + "."): item.value for key, item in result.items()})
        return result

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        with self.runtime.transaction():
            result = super().write(target, fields, changes=changes, reset=reset,
                                   expected_revision=expected_revision, observed_at=observed_at)
            validate({key.removeprefix(GROUP + "."): item.value
                      for key, item in self.read(target, fields).fields.items()})
            return result


class ReferenceSettings:
    """Read one role's reference options without inventing a second scope."""

    def __init__(self, configuration):
        self.configuration = configuration

    def read(self, context, at):
        snapshot = require(self.configuration.read(context.actor, target=target_for(context),
                                                  group_id=GROUP, observed_at=at))
        return validate({key.removeprefix(GROUP + "."): value for key, value in snapshot.values.items()})


__all__ = ["DEFAULTS", "GROUP", "LAYER", "LIMITS", "OWNER", "ReferenceConfigurationOwner",
           "ReferenceSettings", "configuration_fields", "target_for", "validate"]
