"""A persistent fictional calendar; feelings and persona applicability remain model material."""

from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError, digest
from .cycle_feelings import validate_feeling
from . import cycle_variation

PHASES = ("menstrual", "follicular", "pre_ovulation", "ovulation", "luteal", "pms")
DISCOMFORT_OPTIONS = ("痛经", "头痛", "腰酸", "乏力", "情绪低落", "恶心")
DEFAULT_DISCOMFORT_TYPES = "痛经,头痛,腰酸,乏力"
PHASE_EXPRESSION_DEFAULTS = {
    "menstrual": (-12, "疲惫", "处于月经期，身体更容易疲倦，情绪感受稍敏锐"),
    "follicular": (0, "轻快", "处于卵泡期，精力平稳回升，心情逐渐轻快"),
    "pre_ovulation": (8, "期待", "处于排卵前期，身体逐渐轻盈，精力有所上升"),
    "ovulation": (9, "明朗", "处于排卵期，精力较充足，社交意愿稍有增强"),
    "luteal": (5, "平稳", "处于黄体期，精力尚可，情绪整体平稳"),
    "pms": (-8, "敏感", "处于 PMS 期，精力有所下降，情绪波动稍明显"),
}
DEFAULTS = {"cycle_mode": "basic", "cycle_timezone": "Asia/Shanghai",
    "cycle_menstrual_days": 5, "cycle_follicular_days": 7, "cycle_pre_ovulation_days": 2,
    "cycle_ovulation_days": 2, "cycle_luteal_days": 9, "cycle_pms_days": 3,
    "cycle_discomfort_enabled": False, "cycle_discomfort_chance": 55,
    "cycle_discomfort_types": DEFAULT_DISCOMFORT_TYPES, "cycle_link_intensity": False,
    "cycle_expression_prompt": "", "cycle_initialization": "natural",
    "cycle_variation_enabled": False,
    **{f"cycle_{phase}_{name}": value for phase, entries in PHASE_EXPRESSION_DEFAULTS.items()
       for name, value in zip(("energy", "mood", "prompt"), entries)}}
APPLICABILITY = ("unknown", "not_applicable", "applicable")


def validate_settings(values):
    if values["cycle_mode"] not in ("basic", "six_phase"):
        raise ConfigurationError("cycle_configuration_invalid", "cycle_mode must be basic or six_phase")
    if values["cycle_initialization"] not in ("natural", "unknown", "first_day"):
        raise ConfigurationError("cycle_configuration_invalid", "choose natural, unknown or first_day initialization")
    if type(values.get("cycle_variation_enabled", False)) is not bool:
        raise ConfigurationError("cycle_configuration_invalid", "cycle_variation_enabled must be a boolean")
    for name in ("cycle_enabled", "cycle_discomfort_enabled", "cycle_link_intensity"):
        if type(values[name]) is not bool:
            raise ConfigurationError("cycle_configuration_invalid", name + " must be a boolean")
    chance = values["cycle_discomfort_chance"]
    if type(chance) is not int or not 0 <= chance <= 100:
        raise ConfigurationError("cycle_configuration_invalid", "cycle_discomfort_chance must be from 0 to 100")
    selected = discomfort_type_list(values["cycle_discomfort_types"])
    if (type(values["cycle_discomfort_types"]) is not str or len(selected) != len(set(selected))
            or any(item not in DISCOMFORT_OPTIONS for item in selected)):
        raise ConfigurationError("cycle_configuration_invalid", "choose valid simulated discomfort types")
    try:
        ZoneInfo(values["cycle_timezone"])
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ConfigurationError("cycle_configuration_invalid", "use an IANA cycle timezone") from error
    if len(values["cycle_expression_prompt"]) > 2048:
        raise ConfigurationError("cycle_configuration_invalid", "keep cycle expression preferences within 2048 characters")
    for phase in PHASES:
        mood, prompt = (values.get(f"cycle_{phase}_{name}", DEFAULTS[f"cycle_{phase}_{name}"])
                        for name in ("mood", "prompt"))
        if len(mood) > 80 or len(prompt) > 512:
            raise ConfigurationError("cycle_configuration_invalid", "keep phase expression preferences short")


def phase_expression(values):
    settings = DEFAULTS | values
    intensity = settings.get("humanized_state_intensity", 50)
    return {phase: {"energy_tendency": int(round(settings[f"cycle_{phase}_energy"] * intensity / 50))
                        if settings["cycle_link_intensity"] else settings[f"cycle_{phase}_energy"],
                    "mood_tone": settings[f"cycle_{phase}_mood"],
                    "prompt": settings[f"cycle_{phase}_prompt"]} for phase in PHASES}


def discomfort_type_list(value):
    if type(value) is not str:
        return []
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def phase_plan(values):
    phases = [{"phase": phase, "days": values["cycle_" + phase + "_days"]} for phase in PHASES]
    if values["cycle_mode"] == "basic":
        return [phases[0], {"phase": "recovery", "days": sum(p["days"] for p in phases[1:-1])}, phases[-1]]
    return phases


def validate_assertion(value):
    # Text/null is the original state contract and remains valid, without guessing a phase.
    if value is None or type(value) is str and len(value) <= 256:
        return
    if (type(value) is not dict or set(value) not in ({"applicability", "description"}, {"applicability", "description", "feeling"})
            or value["applicability"] not in APPLICABILITY
            or value["description"] is not None and
            (type(value["description"]) is not str or len(value["description"]) > 256)):
        raise TaskError("role_cycle_contract", "cycle needs an applicability and optional short description")
    validate_feeling(value.get("feeling"))


def validate_alignment(applicability, day):
    if (applicability not in (*APPLICABILITY, "auto") or
            (applicability == "applicable" and (type(day) is not int or not 1 <= day <= 180)) or
            (applicability != "applicable" and day is not None)):
        raise TaskError("role_cycle_alignment", "provide a cycle day only for an applicable simulation")


def _calendar(clock, today):
    start = clock.get("segment_start_date", clock["anchor_date"])
    number = clock.get("segment_start_number", 1)
    phases = clock["phases"]
    variation_enabled = clock.get("variation_enabled", False)
    pending = clock.get("pending_plan")
    if pending and today.isoformat() >= pending["effective_date"]:
        start, number, phases = pending["effective_date"], pending["cycle_number"], pending["phases"]
        variation_enabled = pending.get("variation_enabled", variation_enabled)
    return date.fromisoformat(start), number, phases, variation_enabled


def _save_variation(clock, previous, seed, today):
    pending = clock.get("pending_plan") or {}
    if not clock["anchor_date"] or not (clock["variation_enabled"] or pending.get("variation_enabled")
                                       or previous and previous.get("variation_seed")):
        return clock
    clock["variation_seed"] = (previous or {}).get("variation_seed") or digest([seed, clock["anchor_date"]])
    clock["variation_version"] = (previous or {}).get("variation_version", cycle_variation.VERSION)
    if clock["applicability"] == "applicable":
        segment, number, phases, enabled = _calendar(clock, today)
        if enabled:
            length = sum(p["days"] for p in phases)
            completed = (today - segment).days // length
            start = segment + timedelta(days=completed * length)
            material = {**clock, "variation_plan": (previous or {}).get("variation_plan")}
            clock["variation_plan"] = cycle_variation.current(material, phases, start, number + completed)
    return clock


def evolve(previous, assertion, settings, at, *, alignment=None, seed=""):
    """Only trusted clock/configuration chooses dates; the model supplies no clock fields."""
    phases = phase_plan(settings)
    if alignment is not None:
        applicability, day = alignment["applicability"], alignment["day"]
        validate_alignment(applicability, day)
        if day is not None and day > sum(p["days"] for p in phases):
            raise TaskError("role_cycle_alignment", "day exceeds the configured cycle length")
        zone = settings["cycle_timezone"]
        anchor = ((at.astimezone(ZoneInfo(zone)).date() - timedelta(days=day - 1)).isoformat()
                  if day is not None else None)
        result = {"schema": 2, "applicability": "unknown" if applicability == "auto" else applicability,
                "decision_origin": "model" if applicability == "auto" else "manual",
                "initialization": settings["cycle_initialization"] if applicability == "auto" else "manual",
                "anchor_date": anchor, "timezone": zone, "phases": phases,
                "segment_start_date": anchor, "segment_start_number": 1, "pending_plan": None,
                "expression_prompt": settings["cycle_expression_prompt"],
                "phase_expression": phase_expression(settings),
                "discomfort_enabled": settings["cycle_discomfort_enabled"],
                "discomfort_chance": settings["cycle_discomfort_chance"],
                "discomfort_types": settings["cycle_discomfort_types"],
                "variation_enabled": settings.get("cycle_variation_enabled", False)}
        return _save_variation(result, None, seed, at.astimezone(ZoneInfo(zone)).date())
    if not settings["cycle_enabled"]:
        return dict(previous) if previous else None
    if previous is None and type(assertion) is not dict:
        return None
    # Once anchored, changing the display timezone must not silently move the simulated day.
    zone = previous["timezone"] if previous and previous["anchor_date"] else settings["cycle_timezone"]
    applicability = assertion["applicability"] if type(assertion) is dict else previous["applicability"]
    origin = previous.get("decision_origin", "model") if previous else "model"
    if origin == "manual":
        applicability = previous["applicability"]
    anchor = previous["anchor_date"] if previous else None
    today = at.astimezone(ZoneInfo(zone)).date()
    initialization = (previous.get("initialization", "first_day") if previous and (anchor or origin == "manual")
                      else settings["cycle_initialization"])
    if applicability == "applicable" and anchor is None and initialization != "unknown":
        offset = int(digest([seed, today.isoformat(), phases]), 16) % sum(p["days"] for p in phases) if initialization == "natural" else 0
        anchor = (today - timedelta(days=offset)).isoformat()
    requested_variation = settings.get("cycle_variation_enabled", False)
    start, number, active, active_variation, pending = anchor, 1, phases, requested_variation, None
    if previous and previous["anchor_date"]:
        segment, number, active, active_variation = _calendar(previous, today)
        start = segment.isoformat()
        if phases != active or requested_variation != active_variation:
            length = sum(p["days"] for p in active)
            completed = max(0, (today - segment).days // length)
            pending = {"effective_date": (segment + timedelta(days=(completed + 1) * length)).isoformat(),
                       "cycle_number": number + completed + 1, "phases": phases,
                       "variation_enabled": requested_variation}
    result = {"schema": 2, "applicability": applicability, "decision_origin": origin,
            "initialization": initialization, "anchor_date": anchor, "timezone": zone, "phases": active,
            "segment_start_date": start, "segment_start_number": number, "pending_plan": pending,
            "expression_prompt": settings["cycle_expression_prompt"],
            "phase_expression": phase_expression(settings),
            "discomfort_enabled": settings["cycle_discomfort_enabled"],
            "discomfort_chance": settings["cycle_discomfort_chance"],
            "discomfort_types": settings["cycle_discomfort_types"],
            "variation_enabled": active_variation}
    return _save_variation(result, previous, seed, today)


def project(clock, at, *, discomfort_enabled):
    result = {"basis": "role_simulation", "applicability": clock["applicability"],
              "discomfort_enabled": discomfort_enabled and clock.get("discomfort_enabled", False),
              "expression_prompt": clock.get("expression_prompt", "")}
    if result["discomfort_enabled"]:
        result["discomfort_guidance"] = {
            "reference_probability": clock.get("discomfort_chance", 55),
            "types": discomfort_type_list(clock.get("discomfort_types", DEFAULT_DISCOMFORT_TYPES)),
        }
    if clock.get("schema") == 2:
        result.update(decision_origin=clock["decision_origin"], initialization=clock["initialization"])
    if clock["applicability"] != "applicable" or clock["anchor_date"] is None:
        return result
    zone = ZoneInfo(clock["timezone"])
    today, anchor = at.astimezone(zone).date(), date.fromisoformat(clock["anchor_date"])
    if today < anchor:
        return result | {"applicability": "unknown", "reason": "before_anchor"}
    segment, number, phases, variation_enabled = _calendar(clock, today)
    if clock.get("pending_plan") and today.isoformat() < clock["pending_plan"]["effective_date"]:
        result["pending_plan"] = clock["pending_plan"]
    length = sum(p["days"] for p in phases)
    completed, offset = divmod((today - segment).days, length)
    start = segment + timedelta(days=completed * length)
    cycle_number = completed + number
    if variation_enabled:
        phases = cycle_variation.current(clock, phases, start, cycle_number)["phases"]
        result["variation_enabled"] = True
        result["phase_plan"] = phases
    elapsed = 0
    for index, item in enumerate(phases):
        if offset < elapsed + item["days"]:
            phase_guidance = (clock.get("phase_expression") or {}).get(item["phase"]) if len(phases) == 6 else None
            return result | {"mode": "basic" if len(phases) == 3 else "six_phase", "timezone": clock["timezone"],
                "anchor_date": clock["anchor_date"], "cycle_start_date": start.isoformat(),
                "cycle_number": cycle_number, "cycle_day": offset + 1, "cycle_days": length,
                "phase": item["phase"], "phase_day": offset - elapsed + 1, "phase_days": item["days"],
                "phase_start_date": (start + timedelta(days=elapsed)).isoformat(),
                "next_phase": phases[(index + 1) % len(phases)]["phase"],
                "next_phase_date": (start + timedelta(days=elapsed + item["days"])).isoformat(),
                **({"phase_expression": phase_guidance} if phase_guidance is not None else {})}
        elapsed += item["days"]
