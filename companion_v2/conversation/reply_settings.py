"""Reply preferences captured when inputs seal, independent of the host profile."""

from dataclasses import asdict, replace
import json
import math

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, ConfigurationError
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import require

from .segmentation import SegmentationPolicy
from .segmentation import PART_GAP_MODES
from .outbound_plan import component_order
from .text_processing import TEXT_DEFAULTS, text_policy
from .voice_reply import VoiceReplyPolicy


GROUP = "conversation.presentation"
OWNER = "conversation.presentation"
IMAGE_POSITIONS = frozenset(("after_text", "before_text"))
VOICE_FIELDS = tuple(key for key in asdict(VoiceReplyPolicy())
                     if key not in ("private_probability", "group_probability"))
GROUP_AIR_DEFAULTS = {"group_air_guard_enabled": True, "group_air_guard_window_seconds": 180,
                      "group_air_guard_max_bot_replies": 3, "group_air_guard_polite_loop_limit": 2}
GROUP_AIR_LIMITS = {"group_air_guard_window_seconds": (30, 1800),
                    "group_air_guard_max_bot_replies": (1, 20),
                    "group_air_guard_polite_loop_limit": (1, 10)}
GROUP_WAKEUP_LEGACY_FIELDS = frozenset(("group_wakeup_enabled", "group_wakeup_direct_words",
                                        "group_wakeup_context_words", "group_wakeup_interest_keywords",
                                        "group_wakeup_question_enabled"))
GROUP_WAKEUP_DEFAULTS = {"group_wakeup_enabled": True, "group_wakeup_direct_words": "[]",
                         "group_wakeup_context_words": '["机器人", "bot"]',
                         "group_wakeup_interest_keywords": "[]", "group_wakeup_question_enabled": True,
                         "group_wakeup_bot_name": "", "group_wakeup_primary_member_ids": "[]",
                         "group_wakeup_owner_direct_words": "[]",
                         "group_wakeup_interest_probability": 0.18, "group_wakeup_question_threshold": 65,
                         "group_wakeup_cold_group_enabled": False, "group_wakeup_cold_group_threshold": 65,
                         "group_wakeup_cold_group_idle_minutes": 25, "group_wakeup_cooldown_seconds": 90,
                         "group_wakeup_fatigue_limit": 5, "group_wakeup_fatigue_decay_minutes": 90,
                         "group_wakeup_bot_name_enabled": True,
                         "group_wakeup_generated_keyword_limit": 24,
                         "group_wakeup_topic_interest_max_boost": 45,
                         "group_wakeup_debounce_pending_penalty": 65,
                         "group_wakeup_image_enabled": False,
                         "group_wakeup_image_weight": 0.2,
                         "group_wakeup_short_text_wait_ms": 15000, "group_wakeup_log_limit": 80}
GROUP_WAKEUP_ADDED_FIELDS = frozenset(("group_wakeup_bot_name_enabled",
    "group_wakeup_generated_keyword_limit", "group_wakeup_topic_interest_max_boost",
    "group_wakeup_debounce_pending_penalty"))
GROUP_WAKEUP_TIMING_FIELDS = frozenset(("group_wakeup_short_text_wait_ms", "group_wakeup_log_limit"))
GROUP_WAKEUP_PROMPT_FIELDS = frozenset(GROUP_WAKEUP_DEFAULTS) - GROUP_WAKEUP_TIMING_FIELDS
GROUP_WAKEUP_PREVIOUS_FIELDS = GROUP_WAKEUP_PROMPT_FIELDS - GROUP_WAKEUP_ADDED_FIELDS
GROUP_WAKEUP_WORD_FIELDS = ("group_wakeup_direct_words", "group_wakeup_context_words",
                            "group_wakeup_interest_keywords", "group_wakeup_owner_direct_words")
GROUP_WAKEUP_LIMITS = {"group_wakeup_question_threshold": (0, 100),
                       "group_wakeup_cold_group_threshold": (0, 100),
                       "group_wakeup_cold_group_idle_minutes": (3, 720),
                       "group_wakeup_cooldown_seconds": (0, 3600),
                       "group_wakeup_fatigue_limit": (1, 20),
                       "group_wakeup_fatigue_decay_minutes": (5, 720),
                       "group_wakeup_generated_keyword_limit": (4, 80),
                       "group_wakeup_topic_interest_max_boost": (0, 150),
                       "group_wakeup_debounce_pending_penalty": (0, 100),
                       "group_wakeup_short_text_wait_ms": (0, 30000), "group_wakeup_log_limit": (10, 300)}

# These switches are deliberately part of the sealed reply snapshot.  The
# prompt and the outbound policy must agree about the group audience that was
# authorized when the turn started; reading live persona settings here would
# make a reply change meaning halfway through generation.
GROUP_SAFETY_DEFAULTS = {"enable_group_injection_guard": True,
                         "enable_group_privacy_guard": True,
                         "enable_group_reality_promise_guard": True}

# What one reply may carry beyond its text and originals. The component order
# replaces the old four-value position switches only when it is non-empty, so an
# installation that never edits it keeps its current placement; the quote
# switches are off by default for the same reason V1's master switch was off.
OUTBOUND_DEFAULTS = {"component_order": "[]", "reply_quote_enabled": False,
                     "reply_quote_group_enabled": True, "reply_quote_first_part_only": True,
                     "reply_quote_skip_chars": 0, "reply_mention_speaker_enabled": False}
OUTBOUND_LIMITS = {"reply_quote_skip_chars": (0, 120)}
OUTBOUND_BOOLEAN_FIELDS = ("reply_quote_enabled", "reply_quote_group_enabled",
                           "reply_quote_first_part_only", "reply_mention_speaker_enabled")
SPACING_DEFAULTS = {"part_gap_mode": "fixed", "part_gap_min_ms": 1500,
                    "part_gap_max_ms": 3500, "part_gap_log_base": 1.8}
SPACING_FIELDS = frozenset(SPACING_DEFAULTS)
CONTEXT_IMAGE_DEFAULTS = {"enable_context_image_captioning": False,
                          "context_image_caption_max_items": 2}


def outbound_settings(values):
    settings = {key: values.get(key, default) for key, default in OUTBOUND_DEFAULTS.items()}
    if any(type(settings[key]) is not bool for key in OUTBOUND_BOOLEAN_FIELDS):
        raise ConfigurationError("reply_configuration_invalid", "outbound switches must be boolean")
    for key, (minimum, maximum) in OUTBOUND_LIMITS.items():
        if type(settings[key]) is not int or not minimum <= settings[key] <= maximum:
            raise ConfigurationError("reply_configuration_invalid", "invalid outbound quote setting")
    try:
        component_order(settings)
    except ValueError as error:
        raise ConfigurationError("reply_configuration_invalid", str(error)) from error
    return settings


def group_safety_settings(values):
    settings = {key: values.get(key, default) for key, default in GROUP_SAFETY_DEFAULTS.items()}
    if any(type(value) is not bool for value in settings.values()):
        raise ConfigurationError("reply_configuration_invalid", "group safety switches must be boolean")
    return settings


def group_air_settings(values):
    settings = {key: values.get(key, default) for key, default in GROUP_AIR_DEFAULTS.items()}
    if type(settings["group_air_guard_enabled"]) is not bool:
        raise ConfigurationError("reply_configuration_invalid", "group air guard enabled must be boolean")
    for key, (minimum, maximum) in GROUP_AIR_LIMITS.items():
        if type(settings[key]) is not int or not minimum <= settings[key] <= maximum:
            raise ConfigurationError("reply_configuration_invalid", "invalid group air guard setting")
    return settings


def group_wakeup_settings(values):
    settings = {key: values.get(key, default) for key, default in GROUP_WAKEUP_DEFAULTS.items()}
    if any(type(settings[key]) is not bool for key in ("group_wakeup_enabled", "group_wakeup_question_enabled",
                                                    "group_wakeup_cold_group_enabled", "group_wakeup_bot_name_enabled",
                                                    "group_wakeup_image_enabled")):
        raise ConfigurationError("reply_configuration_invalid", "group wakeup switches must be boolean")
    for key in GROUP_WAKEUP_WORD_FIELDS:
        raw = settings[key]
        try:
            words = json.loads(raw) if type(raw) is str and len(raw.encode("utf-8")) <= 2048 else None
        except (ValueError, TypeError):
            words = None
        if (type(words) is not list or len(words) > 24
                or any(type(word) is not str or word != word.strip() or not 1 <= len(word) <= 40
                       or any(ord(char) < 32 for char in word) for word in words)
                or len({word.casefold() for word in words}) != len(words)):
            raise ConfigurationError("reply_configuration_invalid", "group wakeup words require a short JSON string list")
        settings[key] = tuple(words)
    name = settings["group_wakeup_bot_name"]
    if (type(name) is not str or len(name) > 40 or name != name.strip()
            or any(ord(char) < 32 for char in name)):
        raise ConfigurationError("reply_configuration_invalid", "group bot name must be a short display name")
    raw = settings["group_wakeup_primary_member_ids"]
    try:
        members = json.loads(raw) if type(raw) is str and len(raw.encode("utf-8")) <= 512 else None
    except (ValueError, TypeError):
        members = None
    if (type(members) is not list or len(members) > 16
            or any(type(member) is not str or not member.isascii() or not member.isdecimal()
                   or not 1 <= len(member) <= 20 or member.startswith("0") for member in members)
            or len(set(members)) != len(members)):
        raise ConfigurationError("reply_configuration_invalid", "primary group members require account IDs")
    settings["group_wakeup_primary_member_ids"] = tuple(members)
    chance = settings["group_wakeup_interest_probability"]
    if type(chance) not in (int, float) or not 0 <= chance <= 1 or not math.isfinite(chance):
        raise ConfigurationError("reply_configuration_invalid", "invalid group interest probability")
    image_weight = settings["group_wakeup_image_weight"]
    if (type(image_weight) not in (int, float) or not 0 <= image_weight <= 1
            or not math.isfinite(image_weight)):
        raise ConfigurationError("reply_configuration_invalid", "invalid group image wakeup weight")
    for key, (minimum, maximum) in GROUP_WAKEUP_LIMITS.items():
        if type(settings[key]) is not int or not minimum <= settings[key] <= maximum:
            raise ConfigurationError("reply_configuration_invalid", "invalid group wakeup setting")
    return settings


def voice_settings(policy=None):
    return {"voice_enabled": policy is not None,
            **{"voice_" + key: value for key, value in asdict(policy or VoiceReplyPolicy()).items()
               if key in VOICE_FIELDS}}


def voice_policy(values):
    policy = VoiceReplyPolicy(**{key: values["voice_" + key] for key in VOICE_FIELDS})
    if type(values["voice_enabled"]) is not bool:
        raise ValueError("voice enabled must be boolean")
    return policy if values["voice_enabled"] else None


def target_for(context):
    return ConfigTarget(context.scope.installation_id, ConfigLayer.WINDOW, context.role_binding.role, context.scope)


def validate(values):
    if type(values) is not dict:
        raise ConfigurationError("reply_configuration_invalid", "provide the declared reply settings")
    segmentation_defaults = asdict(SegmentationPolicy())
    expected = set(segmentation_defaults) | {"streaming", "part_gap_ms"}
    legacy_required = expected - {"split_words", "match_width_variants", "rule_regex"}
    voice = set(voice_settings())
    air = set(GROUP_AIR_DEFAULTS)
    wakeup = set(GROUP_WAKEUP_DEFAULTS)
    safety = set(GROUP_SAFETY_DEFAULTS)
    outbound = set(OUTBOUND_DEFAULTS)
    presentation = set(TEXT_DEFAULTS)
    captions = set(CONTEXT_IMAGE_DEFAULTS)
    spacing = set(SPACING_DEFAULTS)
    optional = set(values) - expected - {"image_position"}
    provided = set(values)
    if (not legacy_required <= provided
            or optional - voice - air - wakeup - safety - presentation - outbound - captions - spacing
            or any(optional & block and not block <= optional for block in (voice, air, presentation))
            or optional & spacing not in (set(), spacing)
            or optional & wakeup not in (set(), set(GROUP_WAKEUP_LEGACY_FIELDS),
                                        set(GROUP_WAKEUP_PREVIOUS_FIELDS), set(GROUP_WAKEUP_PROMPT_FIELDS), wakeup)):
        raise ConfigurationError("reply_configuration_invalid", "provide the declared reply settings")
    try:
        policy = SegmentationPolicy(**{key: values.get(key, default)
                                       for key, default in segmentation_defaults.items()})
        if type(values["streaming"]) is not bool or type(values["part_gap_ms"]) is not int or not 0 <= values["part_gap_ms"] <= 60000:
            raise ValueError("invalid transport or spacing")
        if values.get("image_position", "after_text") not in IMAGE_POSITIONS:
            raise ValueError("invalid image position")
        spacing_values = {**SPACING_DEFAULTS, **{name: values[name] for name in spacing if name in values}}
        if (spacing_values["part_gap_mode"] not in PART_GAP_MODES
                or type(spacing_values["part_gap_min_ms"]) is not int
                or type(spacing_values["part_gap_max_ms"]) is not int
                or not 100 <= spacing_values["part_gap_min_ms"] <= 60000
                or not 100 <= spacing_values["part_gap_max_ms"] <= 60000
                or spacing_values["part_gap_min_ms"] > spacing_values["part_gap_max_ms"]
                or type(spacing_values["part_gap_log_base"]) not in (int, float)
                or not 1.1 <= spacing_values["part_gap_log_base"] <= 5.0):
            raise ValueError("invalid part spacing settings")
        if "voice_enabled" in values:
            voice_policy(values)
        group_air_settings(values)
        group_wakeup_settings(values)
        group_safety_settings(values)
        outbound_settings(values)
        text_policy(values)
        if (type(values.get("enable_context_image_captioning", False)) is not bool
                or type(values.get("context_image_caption_max_items", 2)) is not int
                or not 0 <= values.get("context_image_caption_max_items", 2) <= 8):
            raise ValueError("invalid historical image caption setting")
    except (ValueError, TypeError) as error:
        raise ConfigurationError("reply_configuration_invalid", "invalid reply settings or prompt length") from error
    return policy


def configuration_fields(segmentation, streaming, gap, voice=None):
    defaults = {**asdict(segmentation), "streaming": streaming, "part_gap_ms": round(gap * 1000),
              **SPACING_DEFAULTS, "image_position": "after_text", **voice_settings(voice), **GROUP_AIR_DEFAULTS,
              **GROUP_WAKEUP_DEFAULTS, **GROUP_SAFETY_DEFAULTS, **OUTBOUND_DEFAULTS, **TEXT_DEFAULTS}
    defaults.update(CONTEXT_IMAGE_DEFAULTS)
    validate(defaults)
    limits = {"threshold": (1, 65536), "min_segment_chars": (1, 65536), "max_segments": (1, 64),
              "part_gap_ms": (0, 60000), "voice_cooldown_seconds": (0, 86400),
              "part_gap_min_ms": (100, 60000), "part_gap_max_ms": (100, 60000),
              "part_gap_log_base": (1.1, 5.0),
              "voice_max_speech_chars": (1, 10000), "voice_timeout_seconds": (1, 120),
              **GROUP_AIR_LIMITS, **GROUP_WAKEUP_LIMITS, **OUTBOUND_LIMITS}
    limits["context_image_caption_max_items"] = (0, 8)
    return tuple(FieldDefinition(GROUP + "." + name, GROUP, GROUP,
        ValueKind.WEIGHT if name == "part_gap_log_base" else
        ValueKind.PROBABILITY if name in ("voice_probability", "group_wakeup_interest_probability") else
        {bool: ValueKind.BOOLEAN, int: ValueKind.INTEGER, float: ValueKind.PROBABILITY, str: ValueKind.TEXT}[type(value)], value,
        layers=(ConfigLayer.WINDOW,), owner_id=OWNER,
        **(dict(zip(("minimum", "maximum"), limits[name])) if name in limits else {}),
        **({"decimal_places": 1} if name == "part_gap_log_base" else {}))
        for name, value in defaults.items())


class ReplyConfigurationOwner(SparseConfigurationOwner):
    owner_id = OWNER

    def __init__(self, runtime, voice=None):
        super().__init__(runtime)
        self.voice = voice or VoiceReplyPolicy()

    def read(self, target, fields):
        snapshot = super().read(target, fields)
        key = GROUP + ".voice_probability"
        current = snapshot.fields.get(key)
        if current is not None and current.source is None and target.scope is not None:
            snapshot = replace(snapshot, fields={**snapshot.fields,
                key: replace(current, value=self.voice.chance(target.scope.kind.value))})
        return snapshot

    def preview_set(self, target, fields, *, changes):
        result = super().preview_set(target, fields, changes=changes)
        validate({key.removeprefix(GROUP + "."): item.value for key, item in result.items()})
        return result

    def write(self, target, fields, *, changes, reset, expected_revision, observed_at):
        with self.runtime.transaction():
            result = super().write(target, fields, changes=changes, reset=reset,
                expected_revision=expected_revision, observed_at=observed_at)
            validate({key.removeprefix(GROUP + "."): item.value for key, item in self.read(target, fields).fields.items()})
            return result


class ReplySettings:
    def __init__(self, configuration):
        self.configuration = configuration

    def snapshot(self, actor, context, at):
        return require(self.configuration.read(actor, target=target_for(context), group_id=GROUP, observed_at=at))

    def capture(self, context, at):
        snapshot = self.snapshot(context.actor, context, at)
        settings = {key.removeprefix(GROUP + "."): value for key, value in snapshot.values.items()}
        validate(settings)
        return {"settings": settings, "configuration_token": snapshot.resolution_token,
                "streaming_explicit": snapshot.fields[GROUP + ".streaming"].explicit}
