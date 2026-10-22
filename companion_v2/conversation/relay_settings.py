"""跨窗口递话的窗口级设置。

产品口径（2026-10-19）：核心管理员可以让 bot 帮忙私聊递话（只发白名单目标、
默认需确认）；其他用户只能让 bot 给核心管理员递话。这里只存开关与目标，
真正的授权判定在 `relay_policy`，发送在宿主层。
"""

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import require


GROUP = "conversation.relay"
OWNER = GROUP
DEFAULTS = {
    # 默认关闭：跨窗口发送属于强能力，必须由管理员在这个窗口显式打开。
    "enabled": False,
    "require_confirm": True,
    "max_text_chars": 500,
    "allowed_targets": "",
    "core_target_id": "",
}
LIMITS = {"max_text_chars": (20, 2000)}


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW,
                        context.role_binding.role, context.scope)


def validate(values):
    if type(values) is not dict or set(values) != set(DEFAULTS):
        raise ConfigurationError("relay_configuration_invalid", "provide the declared relay settings")
    for name in ("enabled", "require_confirm"):
        if type(values[name]) is not bool:
            raise ConfigurationError("relay_configuration_invalid", f"{name} must be boolean")
    for name in ("allowed_targets", "core_target_id"):
        if type(values[name]) is not str:
            raise ConfigurationError("relay_configuration_invalid", f"{name} must be text")
    low, high = LIMITS["max_text_chars"]
    if type(values["max_text_chars"]) is not int or not low <= values["max_text_chars"] <= high:
        raise ConfigurationError("relay_configuration_invalid",
                                 f"max_text_chars must be an integer from {low} to {high}")
    return values


def configuration_fields():
    return tuple(FieldDefinition(GROUP + "." + name, GROUP, GROUP,
        ValueKind.BOOLEAN if type(value) is bool else ValueKind.TEXT if type(value) is str
        else ValueKind.INTEGER, value,
        layers=(ConfigLayer.WINDOW,), owner_id=OWNER,
        **({"minimum": LIMITS[name][0], "maximum": LIMITS[name][1]} if name in LIMITS else {}))
        for name, value in DEFAULTS.items())


class RelayConfigurationOwner(SparseConfigurationOwner):
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


class RelaySettings:
    def __init__(self, configuration):
        self.configuration = configuration

    def read(self, context, at):
        snapshot = require(self.configuration.read(context.actor, target=target_for(context),
                                                   group_id=GROUP, observed_at=at))
        return validate({key.removeprefix(GROUP + "."): value for key, value in snapshot.values.items()})


__all__ = ["DEFAULTS", "GROUP", "LIMITS", "OWNER", "RelayConfigurationOwner", "RelaySettings",
           "configuration_fields", "target_for", "validate"]
