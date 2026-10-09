"""Operator-visible bounds for background expression learning and its rotation.

Every bound used to be a module constant, so an installation could not widen the
sample window, raise the batch size or give an adopted rule more room without a
code change. They are now one configuration group with one owner.

``rotation_decay_hours`` is the answer to the distribution problem: a rule that
was just injected is de-prioritised for that many hours, so a pool with more
adopted rules than one reply can carry still rotates instead of repeating the
same handful of favourites. ``rotation_candidate_limit`` bounds how many rules a
single turn considers, which keeps the read per turn fixed.
"""

from dataclasses import dataclass

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind


GROUP = "expression.learning"
OWNER = "expression.learning"
LAYERS = (ConfigLayer.WINDOW,)
LIMITS = {
    "window_hours": (1, 720),
    "sample_limit": (4, 64),
    "min_samples": (1, 16),
    "group_min_samples": (5, 64),
    "sample_chars": (40, 4000),
    "active_signal_limit": (12, 240),
    "rules_per_turn": (1, 16),
    "payload_chars": (500, 16000),
    "rotation_candidate_limit": (1, 64),
    "rotation_decay_hours": (1, 8760),
    "scan_interval_minutes": (5, 10080),
    "group_daily_batch_limit": (1, 50),
    "group_new_messages": (5, 80),
}
DEFAULTS = {
    "private_learning_enabled": True,
    "group_learning_enabled": False,
    "window_hours": 168,
    "sample_limit": 24,
    "min_samples": 5,
    "group_min_samples": 20,
    "sample_chars": 800,
    "active_signal_limit": 60,
    "rules_per_turn": 8,
    "payload_chars": 4000,
    "rotation_candidate_limit": 24,
    "rotation_decay_hours": 336,
    "scan_interval_minutes": 1440,
    "learning_mode": "balanced",
    "private_application_enabled": True,
    "group_application_enabled": True,
    "sample_review_enabled": False,
    "style_review_enabled": True,
    "group_daily_batch_limit": 6,
    "group_new_messages": 20,
    "group_member_mode": "all",
    "group_member_ids": "",
}
BOOLEAN_FIELDS = ("private_learning_enabled", "group_learning_enabled", "private_application_enabled",
                  "group_application_enabled", "sample_review_enabled", "style_review_enabled")
TEXT_FIELDS = {"learning_mode": 16, "group_member_mode": 16, "group_member_ids": 4000}
INTEGER_FIELDS = tuple(LIMITS)
MODES = ("light", "balanced", "aggressive")


def member_ids(value):
    """Member IDs are interpreted only inside the selected exact group scope."""
    if type(value) is not str:
        raise ConfigurationError("expression_settings_invalid", "group member IDs must be text")
    values = value.replace("，", ",").replace("\n", ",").split(",")
    result = tuple(dict.fromkeys(item.strip() for item in values if item.strip()))
    if len(result) > 100 or any(len(item) > 128 or any(ch.isspace() for ch in item) for item in result):
        raise ConfigurationError("expression_settings_invalid", "group member IDs are invalid")
    return result


def configuration_fields():
    definitions = [FieldDefinition(GROUP + "." + name, GROUP, GROUP, ValueKind.BOOLEAN, DEFAULTS[name],
        layers=LAYERS, apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER) for name in BOOLEAN_FIELDS]
    for name in INTEGER_FIELDS:
        minimum, maximum = LIMITS[name]
        definitions.append(FieldDefinition(GROUP + "." + name, GROUP, GROUP, ValueKind.INTEGER, DEFAULTS[name],
            minimum=minimum, maximum=maximum, layers=LAYERS, apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER))
    for name, maximum in TEXT_FIELDS.items():
        definitions.append(FieldDefinition(GROUP + "." + name, GROUP, GROUP, ValueKind.TEXT, DEFAULTS[name],
            maximum_chars=maximum, layers=LAYERS, apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER))
    return tuple(definitions)


def field_names():
    """Registered definitions for one window read; the sparse owner needs the definitions."""
    return configuration_fields()


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role,
                        context.scope)


@dataclass(frozen=True)
class ExpressionLearningSettings:
    private_learning_enabled: bool
    group_learning_enabled: bool
    window_hours: int
    sample_limit: int
    min_samples: int
    group_min_samples: int
    sample_chars: int
    active_signal_limit: int
    rules_per_turn: int
    payload_chars: int
    rotation_candidate_limit: int
    rotation_decay_hours: int
    scan_interval_minutes: int
    learning_mode: str = "balanced"
    private_application_enabled: bool = True
    group_application_enabled: bool = True
    sample_review_enabled: bool = False
    style_review_enabled: bool = True
    group_daily_batch_limit: int = 6
    group_new_messages: int = 20
    group_member_mode: str = "all"
    group_member_ids: str = ""

    def __post_init__(self):
        if any(type(getattr(self, name)) is not bool for name in BOOLEAN_FIELDS):
            raise ConfigurationError("expression_settings_invalid", "expression learning switches must be boolean")
        if self.learning_mode not in MODES or self.group_member_mode not in ("all", "selected"):
            raise ConfigurationError("expression_settings_invalid", "unknown expression learning mode")
        for name, maximum in TEXT_FIELDS.items():
            if type(getattr(self, name)) is not str or len(getattr(self, name)) > maximum:
                raise ConfigurationError("expression_settings_invalid", "expression text setting is invalid")
        member_ids(self.group_member_ids)
        for name, (minimum, maximum) in LIMITS.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ConfigurationError("expression_settings_invalid",
                                         f"{name} is outside its registered range")
        if self.sample_limit < max(self.min_samples, self.group_min_samples):
            raise ConfigurationError("expression_settings_invalid",
                                     "the sample batch cannot be smaller than either scope's minimum sample count")
        if self.rotation_candidate_limit < self.rules_per_turn:
            raise ConfigurationError("expression_settings_invalid",
                                     "the rotation candidate pool cannot be smaller than one turn's rules")

    @classmethod
    def from_values(cls, values=None):
        values = values or {}
        return cls(**{name: values.get(name, default) for name, default in DEFAULTS.items()})

    def with_group_learning(self, enabled):
        return ExpressionLearningSettings(**{**self.__dict__, "group_learning_enabled": enabled})

    def applies_to(self, context):
        return self.group_application_enabled if context.scope.kind.value == "group" else self.private_application_enabled

    @property
    def selected_members(self):
        return member_ids(self.group_member_ids) if self.group_member_mode == "selected" else None


def read_settings(runtime, context, *, override=None):
    """Read one window's effective bounds; malformed stored values never block a turn."""
    snapshot = SparseConfigurationOwner(runtime).read(target_for(context), field_names())
    values = {key.removeprefix(GROUP + "."): field.value for key, field in snapshot.fields.items()}
    if override is not None:
        values.update(override)
    try:
        return ExpressionLearningSettings.from_values(values)
    except ConfigurationError:
        return ExpressionLearningSettings.from_values(DEFAULTS)


class ExpressionConfigurationOwner(SparseConfigurationOwner):
    """Reject the combinations the loader could not honour.

    Individual ranges are already enforced by each ``FieldDefinition``. The two
    cross-field rules cannot be expressed there, and a silently defaulted pair
    would look saved while the effective bounds stayed at the defaults.
    """

    owner_id = OWNER

    @staticmethod
    def _validate_combination(fields, values):
        current = {field.field_id.removeprefix(GROUP + "."):
                   (values[field.field_id].value if field.field_id in values else field.default)
                   for field in fields}
        try:
            ExpressionLearningSettings.from_values(current)
        except ConfigurationError as error:
            raise ConfigurationError("expression_settings_invalid", str(error)) from error

    def preview_set(self, target, fields, *, changes):
        result = super().preview_set(target, fields, changes=changes)
        self._validate_combination(fields, result)
        return result

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        # The generic patch path only enforces each field's own range, so the
        # cross-field rules are applied here before anything is persisted.
        defaults = {field.field_id: field.default for field in fields}
        prospective = self.preview_set(target, fields,
            changes={**{key: defaults[key] for key in reset}, **changes})
        self._validate_combination(fields, prospective)
        return super().write(target, fields, changes=changes, reset=reset,
            expected_revision=expected_revision, observed_at=observed_at)
