"""A single typed field registry with explicit probability and legacy units."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import math
from types import MappingProxyType

from .models import ApplyMode, ConfigLayer, ConfigurationError, Scalar, fingerprint


class ValueKind(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    TEXT = "text"
    PROBABILITY = "probability"
    WEIGHT = "weight"


@dataclass(frozen=True)
class FieldDefinition:
    field_id: str
    group_id: str
    consumer_id: str
    kind: ValueKind
    default: Scalar
    layers: tuple[ConfigLayer, ...] = (ConfigLayer.INSTALLATION, ConfigLayer.ROLE, ConfigLayer.WINDOW)
    apply_mode: ApplyMode = ApplyMode.NEXT_TASK
    minimum: int | float | None = None
    maximum: int | float | None = None
    maximum_chars: int | None = None
    decimal_places: int | None = 6
    owner_id: str = "configuration"
    core_only: bool = False

    def __post_init__(self) -> None:
        for value in (self.field_id, self.group_id, self.consumer_id, self.owner_id):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("field identifiers must be nonblank")
        if type(self.core_only) is not bool:
            raise ValueError("configuration permission classification must be explicit")
        if not isinstance(self.kind, ValueKind) or not isinstance(self.apply_mode, ApplyMode):
            raise ValueError("invalid configuration type or apply mode")
        if not self.layers or len(set(self.layers)) != len(self.layers) or any(not isinstance(v, ConfigLayer) for v in self.layers):
            raise ValueError("configuration layers must be unique and explicit")
        object.__setattr__(self, "layers", tuple(self.layers))
        if self.decimal_places is not None and (type(self.decimal_places) is not int or not 0 <= self.decimal_places <= 12):
            raise ValueError("unsupported decimal precision")
        for boundary in (self.minimum, self.maximum):
            if boundary is not None and (type(boundary) not in (int, float) or not math.isfinite(boundary)):
                raise ValueError("numeric boundaries must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum exceeds maximum")
        if self.maximum_chars is not None and (
                self.kind is not ValueKind.TEXT or type(self.maximum_chars) is not int or self.maximum_chars < 0):
            raise ValueError("text length boundary must be a non-negative integer on text fields")
        object.__setattr__(self, "default", self.validate(self.default))

    def validate(self, value: object) -> Scalar:
        valid = {
            ValueKind.BOOLEAN: type(value) is bool,
            ValueKind.INTEGER: type(value) is int,
            ValueKind.TEXT: type(value) is str,
            ValueKind.PROBABILITY: type(value) in (int, float),
            ValueKind.WEIGHT: type(value) in (int, float),
        }[self.kind]
        if not valid:
            raise ConfigurationError("invalid_configuration_value", f"{self.field_id}: incorrect type")
        if (self.kind is ValueKind.TEXT and self.maximum_chars is not None
                and len(value) > self.maximum_chars):
            raise ConfigurationError("invalid_configuration_value", f"{self.field_id}: text exceeds maximum length")
        if type(value) in (int, float):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ConfigurationError("invalid_configuration_value", f"{self.field_id}: nonfinite number")
            if self.kind is ValueKind.PROBABILITY and not 0 <= value <= 1:
                raise ConfigurationError("invalid_probability", f"{self.field_id}: expected fraction 0..1")
            if self.kind is ValueKind.WEIGHT and value <= 0:
                raise ConfigurationError("invalid_weight", f"{self.field_id}: expected positive weight")
            if ((self.minimum is not None and value < self.minimum)
                    or (self.maximum is not None and value > self.maximum)):
                raise ConfigurationError("invalid_configuration_value", f"{self.field_id}: outside range")
            if self.kind in (ValueKind.PROBABILITY, ValueKind.WEIGHT):
                number = Decimal(str(value))
                if (self.decimal_places is not None and number.as_tuple().exponent < -self.decimal_places
                        and number != number.quantize(Decimal(1).scaleb(-self.decimal_places))):
                    raise ConfigurationError("invalid_precision", f"{self.field_id}: excessive precision")
                return float(value) if value != 0 else 0.0
        return value

    def from_percent(self, text: str) -> float:
        if self.kind is not ValueKind.PROBABILITY or not isinstance(text, str) or not text.strip():
            raise ConfigurationError("invalid_probability", "percentage input requires a probability field and number")
        try:
            number = Decimal(text)
            if not number.is_finite() or not 0 <= number <= 100:
                raise InvalidOperation
            fraction = number / 100
            value = self.validate(float(fraction))
            if Decimal(str(value)) != fraction:
                raise InvalidOperation
            return value
        except (InvalidOperation, ValueError, OverflowError) as error:
            raise ConfigurationError("invalid_probability", "invalid percentage or unsupported precision") from error

    def to_percent(self, value: Scalar) -> str:
        if self.kind is not ValueKind.PROBABILITY:
            raise ConfigurationError("invalid_probability", "field is not a probability")
        value = self.validate(value)
        return format((Decimal(str(value)) * 100).normalize(), "f")


class FieldRegistry:
    def __init__(self, *, version: str, fields: tuple[FieldDefinition, ...]) -> None:
        if not version or version != version.strip():
            raise ValueError("schema version is required")
        by_id = {field.field_id: field for field in fields}
        if not fields or len(by_id) != len(fields):
            raise ValueError("registry requires unique fields")
        groups = {}
        for field in fields:
            groups.setdefault(field.group_id, []).append(field)
        for group in groups.values():
            if len({(f.consumer_id, f.apply_mode, f.owner_id, f.layers, f.core_only) for f in group}) != 1:
                raise ValueError("one configuration group must have one owner, consumer, scope contract and apply boundary")
        self.version = version
        self.fields = MappingProxyType(by_id)
        self.groups = MappingProxyType({key: tuple(sorted(values, key=lambda f: f.field_id)) for key, values in groups.items()})
        self.fingerprint = fingerprint({"version": version, "fields": [asdict(by_id[key]) for key in sorted(by_id)]})

    def group(self, group_id: str) -> tuple[FieldDefinition, ...]:
        if group_id not in self.groups:
            raise ConfigurationError("unknown_configuration_group", "configuration group is not registered")
        return self.groups[group_id]


class LegacyProbabilityUnit(str, Enum):
    FRACTION = "fraction"
    PERCENT = "percent"


@dataclass(frozen=True)
class LegacyProbabilityRule:
    source_version: str
    old_key: str
    unit: LegacyProbabilityUnit
    negative_one_inherits: bool = False

    def convert(self, *, source_version: str, old_key: str, value: object, field: FieldDefinition) -> float | None:
        """None means reset-to-inherit only for the explicitly registered -1 sentinel."""
        if source_version != self.source_version or old_key != self.old_key:
            raise ConfigurationError("unknown_legacy_format", "legacy field/version does not match the migration rule")
        if not isinstance(self.unit, LegacyProbabilityUnit) or field.kind is not ValueKind.PROBABILITY:
            raise ConfigurationError("unknown_legacy_format", "legacy probability unit must be explicit")
        if type(value) not in (int, float):
            raise ConfigurationError("invalid_probability", "legacy probability must be numeric")
        if value == -1 and self.negative_one_inherits:
            return None
        if self.unit is LegacyProbabilityUnit.PERCENT:
            return field.from_percent(str(value))
        return field.validate(value)
