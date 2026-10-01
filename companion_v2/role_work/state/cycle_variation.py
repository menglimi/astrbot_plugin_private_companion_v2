"""Versioned, reproducible phase variation; independent of chat and model output."""

from companion_v2.execution.models import TaskError, digest

VERSION = 1


def choose(phases, seed, number, version):
    """At most one day moves between two phases; a cycle may also keep its base plan."""
    if version != VERSION:
        raise TaskError("role_cycle_variation_version", "the saved cycle variation algorithm is unavailable")
    result = [dict(item) for item in phases]
    token = int(digest(["cycle-variation", version, seed, number, phases]), 16)
    # Recovery combines four phases, each configured for 1..30 days.
    transfers = [(plus, minus) for plus, gain in enumerate(phases) for minus, loss in enumerate(phases)
                 if plus != minus and gain["days"] < (120 if gain["phase"] == "recovery" else 30)
                 and loss["days"] > (4 if loss["phase"] == "recovery" else 1)]
    if token % 3 and transfers:
        plus, minus = transfers[(token // 3) % len(transfers)]
        result[plus]["days"] += 1
        result[minus]["days"] -= 1
    return result


def current(clock, phases, start, number):
    key = {"cycle_number": number, "cycle_start_date": start.isoformat(), "base_phases": phases,
           "version": clock["variation_version"]}
    saved = clock.get("variation_plan")
    if saved and all(saved[name] == value for name, value in key.items()):
        return {**key, "phases": [dict(item) for item in saved["phases"]]}
    return {**key, "phases": choose(phases, clock["variation_seed"], number, clock["variation_version"])}
