"""Role-wide state preferences behind the existing window management API."""

from companion_v2.configuration.role_settings import RoleSharedSettingsOwner


def physical(field):
    name = field.field_id.rsplit(".", 1)[-1]
    window_fields = {"typing_enabled", "typing_refresh_seconds", "presence_enabled", "online_status_enabled"}
    return name not in window_fields


class PhysicalSettingsOwner(RoleSharedSettingsOwner):
    def is_shared(self, field):
        return physical(field)

    def role_value_overrides_window(self, field):
        name = field.field_id.rsplit(".", 1)[-1]
        return name == "calendar_enabled" or name == "schedule_simulation_mode" or name.startswith("planning_")
