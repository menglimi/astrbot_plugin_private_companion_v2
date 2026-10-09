"""Structured, role-owned guidance for selecting saved image references."""

import re

from companion_v2.execution.models import TaskError


OUTFIT_CATEGORIES = ("", "home", "daily", "uniform", "formal", "swim", "custom")
OUTFIT_LOCKS = ("request", "reference")
DEFAULTS = {
    "base_identity": False,
    "outfit_category": "",
    "outfit_lock": "request",
    "preferred_scene": "",
    "scenes": [],
    "times": [],
    "excluded_scenes": [],
    "excluded_times": [],
}


def validate_usage(value):
    if type(value) is not dict or set(value) != set(DEFAULTS):
        raise TaskError("reference_usage_invalid", "reference usage fields are incomplete")
    if (type(value["base_identity"]) is not bool
            or value["outfit_category"] not in OUTFIT_CATEGORIES
            or value["outfit_lock"] not in OUTFIT_LOCKS
            or type(value["preferred_scene"]) is not str
            or value["preferred_scene"] and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,31}", value["preferred_scene"])):
        raise TaskError("reference_usage_invalid", "reference usage choices are invalid")
    for key in ("scenes", "times", "excluded_scenes", "excluded_times"):
        items = value[key]
        if (type(items) is not list or len(items) > 16
                or any(type(item) is not str or not item or item != item.strip()
                       or len(item) > 80 for item in items)
                or len(set(items)) != len(items)):
            raise TaskError("reference_usage_invalid", "reference scene and time tags must be unique bounded text")
    return {key: list(item) if isinstance(item, list) else item for key, item in value.items()}


def default_usage():
    return {key: list(value) if isinstance(value, list) else value for key, value in DEFAULTS.items()}
