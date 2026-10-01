"""When the shelf may speak, and how often.

C2-3b. Two independent questions, deliberately kept apart:

* *may it speak at all right now* — a wall-clock interval, evaluated against a
  cursor that is **stored**, not held in memory. An in-memory throttle would be
  reset by every restart, which is exactly how a "rare" behaviour becomes chatty.
* *does it choose to* — a probability, sampled from a seed the caller supplies so
  a run is reproducible instead of merely statistical.

The probability is checked only after the interval passes, so setting it to 1 does
not make the shelf ignore its own spacing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import normalize_utc


SHARE = "share"
ASK = "ask"
ACTIONS = (SHARE, ASK)

# The two actions keep separate cursors: a shared shelf update must not consume
# the budget for asking the reader something.
def cursor_key(action: str) -> str:
    if action not in ACTIONS:
        raise ValueError("unknown reading-archive action")
    return "library.trigger." + action


def interval_for(settings, action: str) -> int:
    """The spacing for this action, as whole hours.

    One setting governs both: a shared shelf update and a question to the reader are
    equally "the shelf speaking". The stored value is cast rather than trusted, so a
    float arriving from a rolled-back or hand-edited config cannot reach ``due``.
    """
    if action not in ACTIONS:
        raise ValueError("unknown reading-archive action")
    value = settings["min_interval_hours"]
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError("min_interval_hours must be a number")
    return int(value)


def probability_for(settings, action: str) -> float:
    if action == SHARE:
        return float(settings["share_probability"])
    if action == ASK:
        return float(settings["ask_probability"])
    raise ValueError("unknown reading-archive action")


def due(last_at, *, now: datetime, hours: int) -> bool:
    """Whether the interval has elapsed. A missing cursor is due immediately."""
    if type(hours) is not int or hours < 0:
        raise ValueError("the interval must be a non-negative number of hours")
    if last_at is None:
        return True
    observed = normalize_utc(last_at, field="library trigger cursor")
    return normalize_utc(now, field="library trigger time") - observed >= timedelta(hours=hours)


def sampled(*, seed_parts, probability: float) -> bool:
    """A reproducible draw, so a test can pin the answer instead of averaging.

    The value comes from the same digest the rest of the system uses, truncated to
    a fraction — no global random state, and the same inputs always agree.
    """
    if type(probability) not in (int, float) or isinstance(probability, bool):
        raise ValueError("a probability must be a number")
    if not 0.0 <= float(probability) <= 1.0:
        raise ValueError("a probability must be between 0 and 1")
    if probability <= 0.0:
        return False
    if probability >= 1.0:
        return True
    token = digest(list(seed_parts))
    # 12 hex digits is plenty of resolution for a gate and keeps the arithmetic exact.
    draw = int(token[:12], 16) / float(16 ** 12)
    return draw < float(probability)


def decide(settings, action: str, *, last_at, now: datetime, seed_parts):
    """The full gate: enabled, spaced, then chosen. Returns (allowed, reason)."""
    if action not in ACTIONS:
        raise ValueError("unknown reading-archive action")
    if not settings["enabled"]:
        return False, "library_disabled"
    hours = interval_for(settings, action)
    if not due(last_at, now=now, hours=hours):
        return False, "interval_not_elapsed"
    if not sampled(seed_parts=seed_parts, probability=probability_for(settings, action)):
        return False, "not_sampled"
    return True, ""


__all__ = ["ACTIONS", "ASK", "SHARE", "cursor_key", "decide", "due", "interval_for",
           "probability_for", "sampled"]
