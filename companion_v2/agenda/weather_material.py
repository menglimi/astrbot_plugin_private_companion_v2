"""Current weather as a bounded, explicitly located planning observation."""

from datetime import timedelta
import math

from companion_v2.proactive.external_materials import WeatherSnapshot
from .planning_config import WEATHER_MAX_AGE_MINUTES


# The structural ceiling. An operator may narrow the freshness window per window,
# but never widen it past this, so `max_age` can only ever be the smaller of the two.
MAX_AGE = timedelta(minutes=WEATHER_MAX_AGE_MINUTES)
FUTURE_TOLERANCE = timedelta(minutes=5)
SUPPORTED_PROVIDERS = frozenset({"open-meteo", "qweather"})


def planning_weather_material(snapshot, location, at, *, max_age=MAX_AGE):
    if (type(snapshot) is not WeatherSnapshot or snapshot.provider not in SUPPORTED_PROVIDERS
            or snapshot.location != location.name or snapshot.observed_at.tzinfo is None
            or type(max_age) is not timedelta or not timedelta(0) < max_age <= MAX_AGE
            or not -FUTURE_TOLERANCE <= at - snapshot.observed_at <= max_age
            or not math.isfinite(snapshot.temperature_c) or len(snapshot.condition) > 64):
        return None
    material = {
        "basis": "external_current_observation",
        "provider": snapshot.provider,
        "role_location": location.name,
        "observed_at": snapshot.observed_at.isoformat(),
        "valid_until": (snapshot.observed_at + max_age).isoformat(),
        "condition": snapshot.condition,
        "temperature_c": snapshot.temperature_c,
        "humidity_pct": snapshot.humidity_pct,
        "wind_kph": snapshot.wind_kph,
    }
    if snapshot.weather_code is not None:
        material["weather_code"] = snapshot.weather_code
    return material
