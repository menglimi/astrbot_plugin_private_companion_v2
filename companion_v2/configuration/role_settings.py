"""Configuration owners that share selected fields across a role's windows."""

from dataclasses import replace

from .models import ConfigLayer, ConfigTarget, ConfigurationError
from .owners import OwnerSnapshot, OwnerWrite, SparseConfigurationOwner


class RoleSharedSettingsOwner(SparseConfigurationOwner):
    """Share selected preferences across windows while retaining legacy fallbacks."""

    def is_shared(self, field):
        raise NotImplementedError

    def role_value_overrides_window(self, field):
        return False

    def role_target(self, target):
        return ConfigTarget(target.installation_id, ConfigLayer.ROLE, target.role, bot_id=target.bot_id)

    def window_fields(self, fields):
        return tuple(replace(field, layers=(ConfigLayer.WINDOW,)) for field in fields)

    def role_fields(self, fields):
        return tuple(replace(field, layers=(ConfigLayer.ROLE,)) for field in fields if self.is_shared(field))

    def read(self, target, fields):
        local = super().read(target, self.window_fields(fields))
        role = super().read(self.role_target(target), self.role_fields(fields))
        values = dict(local.fields)
        for field in self.role_fields(fields):
            key = field.field_id
            value = role.fields[key]
            # Some role settings are authoritative even at their default, so an old
            # window value cannot split their behavior across private conversations.
            if self.role_value_overrides_window(field) or (
                    value.source is not None and local.fields[key].source is None):
                values[key] = value
        return OwnerSnapshot(local.revision + role.revision,
            tuple(dict.fromkeys((*local.dependencies, *role.dependencies))), values)

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        with self.runtime.transaction():
            current = self.read(target, fields)
            if current.revision != expected_revision:
                raise ConfigurationError("configuration_revision_conflict", "role settings changed in another window")
            role_target = self.role_target(target)
            role_fields = self.role_fields(fields)
            role_ids = {field.field_id for field in role_fields}
            local_fields = self.window_fields(fields)
            local = super().read(target, local_fields)
            role = super().read(role_target, role_fields)
            role_changes = {key: value for key, value in changes.items() if key in role_ids}
            # Adopt this window's pre-existing value only once, before the role
            # has an explicit value. Other windows can never overwrite it later.
            for field in role_fields:
                if role.fields[field.field_id].source is None:
                    role_changes.setdefault(field.field_id, current.fields[field.field_id].value)
                if field.field_id in reset:
                    role_changes[field.field_id] = field.default
            saved_role = super().write(role_target, role_fields, changes=role_changes, reset=(),
                expected_revision=role.revision, observed_at=observed_at)
            saved_window = super().write(target, local_fields,
                changes={key: value for key, value in changes.items() if key not in role_ids},
                reset=tuple(key for key in reset if key not in role_ids),
                expected_revision=local.revision, observed_at=observed_at)
            return OwnerWrite(saved_role.revision + saved_window.revision,
                tuple(sorted(set(saved_role.changed_fields) | set(saved_window.changed_fields))))
