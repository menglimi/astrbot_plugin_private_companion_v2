"""Pure mapping from V2 image intent fields to a NovelAI generation request."""

from __future__ import annotations

import math
from typing import Mapping


SAMPLERS = frozenset({
    "k_euler",
    "k_euler_ancestral",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "k_dpmpp_2m_sde",
    "k_dpm_2",
    "k_dpm_2_ancestral",
    "k_heun",
    "k_lms",
    "k_ancestral",
    "ddim_v3",
})
NOISE_SCHEDULES = frozenset({"karras", "exponential", "polyexponential"})
ALLOWED_INPUTS = frozenset({
    "width", "height", "steps", "cfg_scale", "seed", "batch_size", "sampler_name", "scheduler",
    "quality_toggle", "sm", "sm_dyn",
})


def map_nai_request(
    *,
    model: str,
    positive_prompt: str,
    negative_prompt: str,
    parameters: Mapping[str, object],
) -> dict[str, object]:
    """Create an API-shaped request without reading credentials or calling a backend."""
    if type(model) is not str or not model.strip():
        raise ValueError("model is required")
    if type(positive_prompt) is not str or not positive_prompt.strip():
        raise ValueError("positive_prompt is required")
    if type(negative_prompt) is not str:
        raise ValueError("negative_prompt must be text")
    if not isinstance(parameters, Mapping) or parameters.keys() - ALLOWED_INPUTS:
        raise ValueError("unsupported NAI parameter")
    values = dict(parameters)

    def integer(name: str, default: int, low: int, high: int) -> int:
        value = values.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(name)
        return value

    width, height = integer("width", 832, 64, 2048), integer("height", 1216, 64, 2048)
    if width % 64 or height % 64:
        raise ValueError("dimensions must be multiples of 64")
    steps = integer("steps", 28, 1, 100)
    count = integer("batch_size", 1, 1, 4)
    seed = values.get("seed")
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 4294967295):
        raise ValueError("seed")
    scale = values.get("cfg_scale", 5.0)
    if type(scale) not in (int, float) or not math.isfinite(scale) or not 0 <= scale <= 20:
        raise ValueError("cfg_scale")
    sampler = values.get("sampler_name", "k_euler_ancestral")
    schedule = values.get("scheduler", "karras")
    if sampler not in SAMPLERS or schedule not in NOISE_SCHEDULES:
        raise ValueError("sampler or scheduler")
    toggles = {}
    for source, target, default in (
        ("quality_toggle", "qualityToggle", True),
        ("sm", "sm", False),
        ("sm_dyn", "sm_dyn", False),
    ):
        value = values.get(source, default)
        if type(value) is not bool:
            raise ValueError(source)
        toggles[target] = value

    nai_parameters: dict[str, object] = {
        "width": width,
        "height": height,
        "steps": steps,
        "scale": float(scale),
        "sampler": sampler,
        "n_samples": count,
        "uc": negative_prompt.strip(),
        "noise_schedule": schedule,
        **toggles,
    }
    if seed is not None:
        nai_parameters["seed"] = seed
    return {"input": positive_prompt.strip(), "model": model.strip(), "parameters": nai_parameters}
