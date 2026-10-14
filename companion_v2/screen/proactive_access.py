"""Use the visible contact setting for Screen's proactive feedback consent."""

from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.proactive.configuration import ContactConfigurationOwner, configuration_fields

from .models import SCREEN_EXTENSION


FIELD = "proactive.contact.screen_glance_enabled"
FIELDS = tuple(field for field in configuration_fields() if field.field_id == FIELD)


def proactive_allowed(runtime, *, scope, role, subject):
    target = ConfigTarget(scope.installation_id, ConfigLayer.WINDOW, role, scope, subject=subject)
    value = ContactConfigurationOwner(runtime).read(target, FIELDS).fields[FIELD]
    if value.source is not None:
        return value.value is True
    # Preserve explicit legacy preferences until the visible V2 switch is saved.
    projection = CapabilityRepository(runtime).projection(extension_id=SCREEN_EXTENSION, scope=scope)
    return (projection.is_success and projection.unwrap().settings is not None
            and projection.unwrap().settings.proactive_enabled)
