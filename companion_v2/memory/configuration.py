"""Memory consumes the unified sparse configuration; it owns no settings copy."""

from dataclasses import fields
from datetime import time
from zoneinfo import ZoneInfo

from companion_v2.configuration.models import ApplyMode, ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, FieldRegistry, ValueKind
from companion_v2.execution.models import digest

from .models import MemoryPolicy


GROUP = "memory"
EPISODE_BOUNDS = {"group_episode_refresh_minutes": (30, 1440),
                  "group_episode_min_messages": (1, 64),
                  "max_group_episodes": (1, 32)}
EPISODE_DEFAULTS = (("group_episode_memory_enabled", True),
                    ("group_episode_refresh_minutes", 180),
                    ("group_episode_min_messages", 12),
                    ("max_group_episodes", 10))
# Private dialogue episodes and the user habit profile are the same kind of
# bounded material for the same reflection chain, so they declare into this group
# and keep its single owner, consumer and apply boundary.
DIALOGUE_BOUNDS = {"dialogue_episode_refresh_messages": (1, 64),
                   "dialogue_episode_refresh_minutes": (5, 1440),
                   "max_dialogue_episodes": (1, 32)}
DIALOGUE_DEFAULTS = (("dialogue_episode_memory_enabled", True),
                     ("dialogue_episode_refresh_messages", 8),
                     ("dialogue_episode_refresh_minutes", 90),
                     ("max_dialogue_episodes", 12))
HABIT_BOUNDS = {"habit_min_count": (2, 20), "habit_max_items": (8, 80), "habit_refresh_minutes": (30, 4320)}
HABIT_DEFAULTS = (("habit_learning_enabled", True),
                  ("food_menu_recommendation_enabled", True),
                  ("habit_min_count", 3),
                  ("habit_max_items", 24),
                  ("habit_refresh_minutes", 360))


def configuration_fields(defaults=MemoryPolicy()):
    bounds = {"context_items": (0, 16), "context_chars": (256, 24000), "query_items": (1, 50),
              "query_chars": (256, 48000), "source_chars": (256, 24000), "turn_chars": (1024, 200000), "turn_calls": (1, 32),
              "core_items": (0, 16), "core_chars": (256, 24000), "inclusion_chars": (512, 96000),
              **EPISODE_BOUNDS}
    result = []
    for field in fields(defaults):
        value = getattr(defaults, field.name)
        low, high = bounds.get(field.name, (None, None))
        result.append(FieldDefinition("memory." + field.name, GROUP, "memory", ValueKind.BOOLEAN if type(value) is bool else ValueKind.INTEGER,
            value, minimum=low, maximum=high, apply_mode=ApplyMode.IMMEDIATE, core_only=True))
    # 每日反思默认开启。它是把已经躺在 conversation_inputs 里的原文变成可用记忆的
    # 唯一批量路径：V2 没有"每轮自动提炼"，模型主动提议只覆盖被明确说出口的事，
    # 所以关掉它并不等于"更省"，而是"原文存着但没人整理"——用户看到的现象是
    # "它不记事"，且没有任何地方告诉他要去开一个开关。代价是每天一次模型调用。
    for name, value in (("reflection_enabled", True), ("reflection_timezone", "Asia/Shanghai"), ("reflection_time", "23:50"),
                        ("reflection_response_format", "text"), ("reflection_auto_repair", True)):
        result.append(FieldDefinition("memory." + name, GROUP, "memory", ValueKind.BOOLEAN if type(value) is bool else ValueKind.TEXT,
            value, apply_mode=ApplyMode.IMMEDIATE, core_only=True))
    # Periodic group activity belongs to this same group and owner: it is one more
    # bounded input to the existing memory reflection, not a second memory system.
    for name, value in EPISODE_DEFAULTS:
        low, high = EPISODE_BOUNDS.get(name, (None, None))
        result.append(FieldDefinition("memory." + name, GROUP, "memory",
            ValueKind.BOOLEAN if type(value) is bool else ValueKind.INTEGER, value,
            minimum=low, maximum=high, apply_mode=ApplyMode.IMMEDIATE, core_only=True))
    # The private dialogue episode (V1 `enable_dialogue_episode_memory` and its
    # three thresholds) and the user habit profile (V1 `enable_user_habit_learning`,
    # `enable_food_menu_recommendation`, `user_habit_min_count`,
    # `user_habit_max_items`, `memory_refresh_interval_minutes`) declare here as
    # well: same owner, same chain, no second configuration system.
    for defaults, bounds in ((DIALOGUE_DEFAULTS, DIALOGUE_BOUNDS), (HABIT_DEFAULTS, HABIT_BOUNDS)):
        for name, value in defaults:
            low, high = bounds.get(name, (None, None))
            result.append(FieldDefinition("memory." + name, GROUP, "memory",
                ValueKind.BOOLEAN if type(value) is bool else ValueKind.INTEGER, value,
                minimum=low, maximum=high, apply_mode=ApplyMode.IMMEDIATE, core_only=True))
    return tuple(result)


def extend_registry(registry, defaults):
    added = configuration_fields(defaults)
    present = {field.field_id for field in added}.intersection(registry.fields)
    if present:
        if present != {field.field_id for field in added}:
            raise ValueError("memory configuration requires its complete registered group")
        return registry
    return FieldRegistry(version=registry.version + "+memory.2", fields=tuple(registry.fields.values()) + added)


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)


def role_target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE,
                        context.role_binding.role, bot_id=context.scope.bot_id)


def validate_schedule(values):
    if values["memory.reflection_response_format"] not in ("text", "json_object", "json_schema"):
        raise ValueError("memory response format must match the selected provider's supported mode")
    ZoneInfo(values["memory.reflection_timezone"])
    clock = time.fromisoformat(values["memory.reflection_time"])
    if clock.tzinfo is not None:
        raise ValueError("daily clock uses its separate IANA timezone")


class MemorySettings:
    def __init__(self, configuration):
        self.configuration = configuration
        self.owner = SparseConfigurationOwner(configuration.runtime)
        self.definitions = configuration.registry.group(GROUP)

    def read(self, context):
        with self.configuration.runtime.read_snapshot():
            snapshot = self.owner.read(target_for(context), self.definitions)
            values = {key: item.value for key, item in snapshot.fields.items()}
            token = digest([(key, item.value, item.source_revision) for key, item in snapshot.fields.items()])
            return values, token

    def policy(self, context):
        values, _ = self.read(context)
        return MemoryPolicy(**{f.name: values["memory." + f.name] for f in fields(MemoryPolicy)})
