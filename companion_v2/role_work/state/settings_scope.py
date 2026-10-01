"""Role-wide state preferences behind the existing window management API."""

from companion_v2.configuration.role_settings import RoleSharedSettingsOwner


def physical(field):
    name = field.field_id.rsplit(".", 1)[-1]
    window_fields = {"calendar_enabled", "typing_enabled", "typing_refresh_seconds",
                     "presence_enabled", "online_status_enabled"}
    return name not in window_fields


class PhysicalSettingsOwner(RoleSharedSettingsOwner):
    def is_shared(self, field):
        return physical(field)
