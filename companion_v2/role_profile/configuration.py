"""Role-owned canon fields used by the dashboard and conversation runtime."""

import base64
import binascii
import json
import re

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind


GROUP = "role.profile"
OWNER = "role.profile.settings"
MAX_AVATAR_BYTES = 24 * 1024
MAX_AVATAR_DATA_URL_CHARS = len("data:image/jpeg;base64,") + ((MAX_AVATAR_BYTES + 2) // 3) * 4
WORLD_ADAPTATION_MODES = frozenset({"auto", "modern", "fantasy", "sci_fi", "custom", "off"})
FIELD_LIMITS = {
    "name": 80,
    "species": 120,
    "birthday": 120,
    "age": 80,
    "gender": 60,
    "occupation": 240,
    "identity": 2000,
    "appearance_points": 700,
    "hair": 240,
    "eyes": 200,
    "clothing": 420,
    "image_identity_hint": 600,
    "appearance": 1800,
    "personality": 2400,
    "first_person": 80,
    "speech_style": 700,
    "emotional_style": 700,
    "social_distance": 1000,
    "reaction_patterns": 1400,
    "voice_examples": 1800,
    "signature_phrases": 320,
    "daily_habits": 400,
    "key_lore": 1000,
    "character_extra": 700,
    "motivations": 1800,
    "core_values": 700,
    "desire": 700,
    "hobbies": 500,
    "boundaries": 1800,
    "taboos": 600,
    "world_name": 700,
    "era": 360,
    "tone": 520,
    "rules": 900,
    "scenes": 650,
    "network": 750,
    "world_extra": 600,
    "world": 4200,
    "platform_group_chat": 80,
    "platform_screen": 80,
    "platform_bilibili": 80,
    "platform_qzone": 80,
    "platform_library": 80,
    "platform_names": 1200,
    "world_adaptation_mode": 20,
    "world_adaptation": 1200,
    "main_companion_subject": 256,
    "expression_private_source_mode": 16,
    "expression_private_source_subject_ids": 4000,
    "expression_private_application_mode": 16,
    "expression_private_application_subject_ids": 4000,
    "avatar_data_url": MAX_AVATAR_DATA_URL_CHARS,
}
FIELD_DEFAULTS = {
    "world_adaptation_mode": "auto",
    "expression_private_source_mode": "owner",
    "expression_private_source_subject_ids": "[]",
    "expression_private_application_mode": "all",
    "expression_private_application_subject_ids": "[]",
    "avatar_data_url": "",
}
CONTROL_FIELDS = frozenset({"main_companion_subject", "expression_private_source_mode",
    "expression_private_source_subject_ids", "expression_private_application_mode",
    "expression_private_application_subject_ids", "avatar_data_url"})
TOTAL_CHAR_LIMIT = 30000


def configuration_fields():
    return tuple(
        FieldDefinition(
            f"{GROUP}.{name}", GROUP, GROUP, ValueKind.TEXT, FIELD_DEFAULTS.get(name, ""),
            layers=(ConfigLayer.ROLE,), apply_mode=ApplyMode.IMMEDIATE,
            owner_id=OWNER, core_only=True,
        )
        for name in FIELD_LIMITS
    )


def target_for(context):
    return ConfigTarget(
        context.scope.installation_id,
        ConfigLayer.ROLE,
        context.role_binding.role,
        bot_id=context.scope.bot_id,
    )


def validate_values(values):
    if type(values) is not dict or set(values) != set(FIELD_LIMITS):
        raise ConfigurationError("role_profile_configuration_invalid", "role profile fields are incomplete")
    total = 0
    for name, limit in FIELD_LIMITS.items():
        value = values[name]
        if type(value) is not str or len(value) > limit:
            raise ConfigurationError(
                "role_profile_configuration_invalid",
                f"{name} must be text no longer than {limit} characters",
            )
        if name != "avatar_data_url":
            total += len(value)
    avatar = values["avatar_data_url"]
    if avatar:
        prefix = "data:image/jpeg;base64,"
        if (not avatar.startswith(prefix) or len(avatar) > MAX_AVATAR_DATA_URL_CHARS
                or not re.fullmatch(r"data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}", avatar)):
            raise ConfigurationError("role_profile_configuration_invalid", "avatar_data_url must be a bounded JPEG data URL")
        try:
            image_bytes = base64.b64decode(avatar[len(prefix):], validate=True)
        except (binascii.Error, ValueError):
            raise ConfigurationError("role_profile_configuration_invalid", "avatar_data_url is invalid") from None
        if (not image_bytes or len(image_bytes) > MAX_AVATAR_BYTES
                or not image_bytes.startswith(b"\xff\xd8\xff") or not image_bytes.endswith(b"\xff\xd9")):
            raise ConfigurationError("role_profile_configuration_invalid", "avatar_data_url is not a bounded JPEG image")
    if values["world_adaptation_mode"] not in WORLD_ADAPTATION_MODES:
        raise ConfigurationError("role_profile_configuration_invalid",
                                  "world_adaptation_mode must be a supported mode")
    for name in ("expression_private_source_mode", "expression_private_application_mode"):
        if values[name] not in ("owner", "selected", "all"):
            raise ConfigurationError("role_profile_configuration_invalid", f"{name} is unsupported")
    for name in ("expression_private_source_subject_ids", "expression_private_application_subject_ids"):
        try:
            ids = json.loads(values[name])
        except (TypeError, ValueError):
            raise ConfigurationError("role_profile_configuration_invalid", f"{name} must be a JSON array") from None
        if (type(ids) is not list or len(ids) > 100
                or any(type(item) is not str or not item or item != item.strip() or len(item) > 256 for item in ids)
                or len(set(ids)) != len(ids)):
            raise ConfigurationError("role_profile_configuration_invalid", f"{name} contains invalid IDs")
    if total > TOTAL_CHAR_LIMIT:
        raise ConfigurationError(
            "role_profile_configuration_invalid",
            f"the complete role profile must be no longer than {TOTAL_CHAR_LIMIT} characters",
        )
    return values


class RoleProfileConfigurationOwner(SparseConfigurationOwner):
    """Keep every write path within the same bounded role-profile contract."""

    owner_id = OWNER

    @staticmethod
    def _values(snapshot, fields):
        prefix = GROUP + "."
        return {
            field.field_id.removeprefix(prefix): snapshot.fields[field.field_id].value
            for field in fields
        }

    def read(self, target, fields):
        snapshot = super().read(target, fields)
        validate_values(self._values(snapshot, fields))
        return snapshot

    def preview_set(self, target, fields, *, changes):
        current = super().read(target, fields)
        values = self._values(current, fields)
        prefix = GROUP + "."
        values.update({name.removeprefix(prefix): value for name, value in changes.items()})
        validate_values(values)
        return super().preview_set(target, fields, changes=changes)

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        current = super().read(target, fields)
        values = self._values(current, fields)
        prefix = GROUP + "."
        values.update({name.removeprefix(prefix): value for name, value in changes.items()})
        for name in reset:
            short_name = name.removeprefix(prefix)
            values[short_name] = FIELD_DEFAULTS.get(short_name, "")
        validate_values(values)
        return super().write(
            target, fields, changes=changes, reset=reset,
            expected_revision=expected_revision, observed_at=observed_at,
        )
