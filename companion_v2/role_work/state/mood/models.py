"""Structured role mood: four independent axes with a personal baseline.

Mood stays part of the shared role body. It is ambient feeling, never a
relationship episode and never an observation of the user.
"""

from datetime import datetime

from companion_v2.execution.models import TaskError, stamp

AXES = ("joy", "anger", "sorrow", "fear")
MINIMUM = 1
MAXIMUM = 10
INTENSITIES = ("mild", "moderate", "strong")
KEYS = ("baseline", *AXES, "intensity", "description")
DEFAULT_BASELINE = 6
POLARITY = {"joy": 1, "anger": -1, "sorrow": -1, "fear": -1}


def _axis(value, name):
    if type(value) is not int or not MINIMUM <= value <= MAXIMUM:
        raise TaskError("role_mood_contract", f"{name} must be an integer from {MINIMUM} to {MAXIMUM}")
    return value


def validate(mood):
    """Normalize one mood value; a plain string keeps the original text contract."""
    if mood is None:
        return None
    if type(mood) is str:
        if not mood.strip() or len(mood) > 256:
            raise TaskError("role_mood_contract", "mood text must be a bounded description or null")
        return mood
    if type(mood) is not dict or set(mood) not in (set(KEYS), set(KEYS) - {"description"}):
        raise TaskError("role_mood_contract",
                        "mood must be text, null, or an object with baseline, four axes and intensity")
    values = {"baseline": _axis(mood["baseline"], "baseline")}
    values.update({name: _axis(mood[name], name) for name in AXES})
    if mood["intensity"] is not None and mood["intensity"] not in INTENSITIES:
        raise TaskError("role_mood_contract", "intensity must be mild, moderate, strong or null")
    description = mood.get("description")
    if description is not None and (type(description) is not str or not description.strip() or len(description) > 256):
        raise TaskError("role_mood_contract", "mood description must be a bounded description or null")
    return {"baseline": values["baseline"], **{name: values[name] for name in AXES},
            "intensity": mood["intensity"], "description": description}


def axes(mood):
    """The four axis values of one mood, or None when it carries no numbers."""
    return {name: mood[name] for name in AXES} if type(mood) is dict else None


def neutral(mood, band):
    """True when no axis rises above the neutral band, so mood stops colouring tone."""
    values = axes(mood)
    return values is None or all(value <= band for value in values.values())


def previous_axes(mood, dynamics):
    """The last observed axis state with its observation time, for decay math."""
    values = axes(mood)
    if not values or type(dynamics) is not dict or not dynamics.get("updated_at"):
        return None
    try:
        return {"updated_at": datetime.fromisoformat(dynamics["updated_at"]), **values}
    except ValueError:
        return None


def baseline_of(mood, dynamics):
    if type(mood) is dict:
        return mood["baseline"]
    stored = dynamics.get("baseline") if type(dynamics) is dict else None
    return stored if type(stored) is int and MINIMUM <= stored <= MAXIMUM else DEFAULT_BASELINE


def resting_target(axis, baseline):
    """Joy relaxes toward the personal baseline; distress axes relax toward MINIMUM (1)."""
    return float(baseline) if POLARITY[axis] > 0 else float(MINIMUM)


def decayed(previous, baseline, at, half_life_minutes):
    """Exponential regression toward each axis's resting target; no axis ever leaves its range."""
    if previous is None:
        return {name: resting_target(name, baseline) for name in AXES}
    minutes = max((at - previous["updated_at"]).total_seconds() / 60.0, 0.0)
    remaining = 0.5 ** (minutes / half_life_minutes)
    return {
        name: round(previous[name] + (resting_target(name, baseline) - previous[name]) * (1 - remaining), 3)
        for name in AXES
    }


def drift(previous, interest_level, max_delta):
    """The bounded displacement one engagement window may cause.

    Engagement lifts joy and eases the three distress axes; a quiet gap drives the
    opposite direction. Weights are fixed and the step is capped, so one message can
    never swing an axis from one extreme to the other.
    """
    baseline = previous["baseline"] if previous and "baseline" in previous else DEFAULT_BASELINE
    values = axes(previous) or {name: resting_target(name, baseline) for name in AXES}
    level = max(int(interest_level or 0), 0)
    magnitude = min(level if level else 1, max_delta)
    shift = 1 if level else -1
    moved = {name: min(max(values[name] + POLARITY[name] * shift * magnitude, MINIMUM), MAXIMUM) for name in AXES}
    return {"baseline": baseline, "axes": {name: round(value, 3) for name, value in moved.items()}}


def bounds(previous, *, at, half_life_minutes, max_delta):
    """Per-axis relaxation reference and the one window an observation may land in.

    Relaxation is never capped: an axis may always move toward, reach, or cross its
    resting target, because that is what a half-life means. Acceleration is capped: beyond
    the relaxed value an axis may move only one bounded step, and never away from the
    resting target past it. That asymmetry is what keeps a single message from swinging an
    extreme, while still letting a strong episode fade within one round.
    """
    baseline = previous["baseline"] if previous and "baseline" in previous else DEFAULT_BASELINE
    reference = decayed(previous, baseline, at, half_life_minutes)
    if previous is None:
        return {"reference": reference, "allowed": {name: [MINIMUM, MAXIMUM] for name in AXES}}
    allowed = {}
    for name in AXES:
        target = resting_target(name, baseline)
        relaxed = reference[name]
        low = min(relaxed - max_delta, target + max_delta)
        high = max(relaxed + max_delta, target - max_delta)
        allowed[name] = [round(max(low, MINIMUM), 3), round(min(high, MAXIMUM), 3)]
    return {"reference": reference, "allowed": allowed}


def validate_update(previous, mood, *, at, half_life_minutes, max_delta):
    """Reject a model-written mood that leaves the bounded window of one round.

    The first structured mood is unpinned: a body that has never carried numbers may
    start anywhere in range, exactly like a cycle's first observed feeling.
    """
    checked = validate(mood)
    if type(checked) is not dict or not previous:
        return checked
    allowed = bounds(previous, at=at, half_life_minutes=half_life_minutes, max_delta=max_delta)["allowed"]
    for name in AXES:
        low, high = allowed[name]
        if not low <= checked[name] <= high:
            raise TaskError("role_mood_contract",
                            f"{name} leaves the bounded range for one maintenance round")
    return checked


def document(mood, previous, *, at, half_life_minutes, interest_level, cross_window):
    """The explainable trace stored beside the record, mirroring cycle_clock."""
    values = axes(mood)
    baseline = mood["baseline"] if type(mood) is dict else DEFAULT_BASELINE
    observed = None if previous is None else {
        "updated_at": datetime.fromisoformat(str(previous["updated_at"])), **{name: previous[name] for name in AXES}}
    return {"updated_at": stamp(at), "half_life_minutes": int(half_life_minutes),
            "interest_level": interest_level, "baseline": baseline,
            "cross_window": bool(cross_window), "axes": values,
            "previous_axes": axes(previous),
            "reference": decayed(observed, baseline, at, half_life_minutes)}


def project(mood, dynamics, *, at, half_life_minutes, band, cross_window):
    """Presentation copy: decayed reference values plus the neutral and sharing flags."""
    previous = previous_axes(mood, dynamics)
    values = axes(mood)
    baseline = baseline_of(mood, dynamics)
    return {"updated_at": dynamics.get("updated_at") if type(dynamics) is dict else None,
            "baseline": baseline, "axes": values,
            "reference": decayed(previous, baseline, at, half_life_minutes),
            "interest_level": dynamics.get("interest_level") if type(dynamics) is dict else None,
            "neutral": neutral(mood, band), "cross_window": bool(cross_window)}
