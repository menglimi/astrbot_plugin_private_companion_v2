"""Person acquaintance consumes the unified sparse configuration; it owns no settings copy."""

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind


GROUP = "person"


def configuration_fields():
    return (
        FieldDefinition("person.acquaintance_enabled", GROUP, "person", ValueKind.BOOLEAN, True,
                        apply_mode=ApplyMode.IMMEDIATE, core_only=True),
        FieldDefinition("person.acquaintance_card_chars", GROUP, "person", ValueKind.INTEGER, 1024,
                        minimum=256, maximum=4096, apply_mode=ApplyMode.IMMEDIATE, core_only=True),
    )


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)


class AcquaintanceSettings:
    def __init__(self, configuration):
        self.configuration = configuration
        self.owner = SparseConfigurationOwner(configuration.runtime)
        self.definitions = configuration.registry.group(GROUP)

    def read(self, context):
        with self.configuration.runtime.read_snapshot():
            snapshot = self.owner.read(target_for(context), self.definitions)
            return {key: item.value for key, item in snapshot.fields.items()}
