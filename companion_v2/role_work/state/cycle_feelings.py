"""Optional continuity of a fictional feeling, without symptom classifiers or numeric penalties."""

from companion_v2.execution.models import TaskError, digest, stamp

TRENDS = ("continuing", "easing", "worsening", "ended", "uncertain")


def validate_feeling(value):
    if value is None:
        return
    if (type(value) is not dict or set(value) != {"episode_id", "trend"} or value["trend"] not in TRENDS
            or value["episode_id"] is not None and (type(value["episode_id"]) is not str
            or not value["episode_id"] or len(value["episode_id"]) > 128)):
        raise TaskError("role_cycle_feeling", "provide the original episode id or null and a descriptive trend")


def update(previous, assertion, at, *, key):
    value = assertion.get("feeling") if type(assertion) is dict else None
    if value is None:
        return None
    if value["episode_id"] is not None and (not previous or value["episode_id"] != previous["episode_id"]):
        raise TaskError("role_cycle_feeling_changed", "the original feeling is no longer available")
    continuing = value["episode_id"] is not None
    if continuing and previous["trend"] == "ended" and value["trend"] != "ended":
        raise TaskError("role_cycle_feeling_ended", "use a new episode for a new feeling")
    return {"episode_id": previous["episode_id"] if continuing else "cycle-feeling-" + digest(key),
            "started_at": previous["started_at"] if continuing else stamp(at),
            "observed_at": stamp(at), "last_confirmed_at": (
                previous["last_confirmed_at"] if continuing else None) if value["trend"] == "uncertain" else stamp(at),
            "trend": value["trend"], "description": assertion["description"]}
