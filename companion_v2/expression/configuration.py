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
    "sample_chars": (40, 4000),
    "rules_per_turn": (1, 16),
    "payload_chars": (500, 16000),
    "rotation_candidate_limit": (1, 64),
    "rotation_decay_hours": (1, 8760),
    "scan_interval_minutes": (5, 10080),
}
DEFAULTS = {
    "group_learning_enabled": False,
    "window_hours": 168,
    "sample_limit": 24,
    "min_samples": 4,
    "sample_chars": 800,
    "rules_per_turn": 8,
    "payload_chars": 4000,
    "rotation_candidate_limit": 24,
    "rotation_decay_hours": 336,
    "scan_interval_minutes": 1440,
}
BOOLEAN_FIELDS = ("group_learning_enabled",)
INTEGER_FIELDS = tuple(name for name in DEFAULTS if name not in BOOLEAN_FIELDS)


def configuration_fields():
    definitions = [FieldDefinition(GROUP + "." + name, GROUP, GROUP, ValueKind.BOOLEAN, DEFAULTS[name],
        layers=LAYERS, apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER) for name in BOOLEAN_FIELDS]
    for name in INTEGER_FIELDS:
        minimum, maximum = LIMITS[name]
        definitions.append(FieldDefinition(GROUP + "." + name, GROUP, GROUP, ValueKind.INTEGER, DEFAULTS[name],
            minimum=minimum, maximum=maximum, layers=LAYERS, apply_mode=ApplyMode.IMMEDIATE, owner_id=OWNER))
    return tuple(definitions)


def field_names():
    """Registered definitions for one window read; the sparse owner needs the definitions."""
    return configuration_fields()


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role,
                        context.scope)


@dataclass(frozen=True)
class ExpressionLearningSettings:
    group_learning_enabled: bool
    window_hours: int
    sample_limit: int
    min_samples: int
    sample_chars: int
    rules_per_turn: int
    payload_chars: int
    rotation_candidate_limit: int
    rotation_decay_hours: int
    scan_interval_minutes: int

    def __post_init__(self):
        if type(self.group_learning_enabled) is not bool:
            raise ConfigurationError("expression_settings_invalid", "group learning switch must be boolean")
        for name, (minimum, maximum) in LIMITS.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ConfigurationError("expression_settings_invalid",
                                         f"{name} is outside its registered range")
        if self.sample_limit < self.min_samples:
            raise ConfigurationError("expression_settings_invalid",
                                     "the sample batch cannot be smaller than the minimum sample count")
        if self.rotation_candidate_limit < self.rules_per_turn:
            raise ConfigurationError("expression_settings_invalid",
                                     "the rotation candidate pool cannot be smaller than one turn's rules")

    @classmethod
    def from_values(cls, values=None):
        values = values or {}
        return cls(**{name: values.get(name, default) for name, default in DEFAULTS.items()})

    def with_group_learning(self, enabled):
        return ExpressionLearningSettings(**{**self.__dict__, "group_learning_enabled": enabled})


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
        self._validate_combination(fields, self.preview_set(target, fields, changes=changes))
        return super().write(target, fields, changes=changes, reset=reset,
            expected_revision=expected_revision, observed_at=observed_at)
