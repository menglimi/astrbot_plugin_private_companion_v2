"""Fixed Open-Meteo current-weather adapter for explicit role coordinates."""

import json
from datetime import datetime, timezone

import aiohttp

from companion_v2.agenda.planning_config import WeatherLocation
from companion_v2.proactive.external_materials import parse_weather_response


ENDPOINT = "https://api.open-meteo.com/v1/forecast"
GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
MAX_RESPONSE_BYTES = 16384
CONDITIONS = {
    0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def normalize_open_meteo(payload, location):
    if type(payload) is not dict or type(payload.get("current")) is not dict:
        raise ValueError("current weather is unavailable")
    current = payload["current"]
    code, observed = current.get("weather_code"), current.get("time")
    if (type(code) is not int or code not in CONDITIONS or type(observed) is not str
            or type(payload.get("utc_offset_seconds")) is not int
            or payload["utc_offset_seconds"] != 0):
        raise ValueError("current weather fields are invalid")
    timestamp = datetime.fromisoformat(observed)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    envelope = {
        "provider": "open-meteo", "location": location.name,
        "observed_at": timestamp.isoformat(),
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "condition": CONDITIONS[code],
            "weather_code": code,
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_kph": current.get("wind_speed_10m"),
        },
    }
    return parse_weather_response(envelope)[0]


class OpenMeteoWeatherPort:
    provider = "open-meteo"

    async def _coordinates(self, location, session):
        if location.latitude is not None and location.longitude is not None:
            return location.latitude, location.longitude
        params = {"name": location.name, "count": 1, "language": "zh", "format": "json"}
        async with session.get(GEOCODING_ENDPOINT, params=params, allow_redirects=False) as response:
            if (response.status != 200 or response.content_length is not None
                    and response.content_length > MAX_RESPONSE_BYTES):
                raise ValueError("weather location could not be resolved")
            raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("weather location response exceeds the limit")
        results = json.loads(raw).get("results") or []
        if not results or type(results[0].get("latitude")) not in (int, float) or type(results[0].get("longitude")) not in (int, float):
            raise ValueError("weather location could not be resolved")
        return float(results[0]["latitude"]), float(results[0]["longitude"])

    async def fetch(self, location):
        if type(location) is not WeatherLocation:
            raise ValueError("weather query requires an explicit role location")
        params = {
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "temperature_unit": "celsius", "wind_speed_unit": "kmh", "timezone": "UTC",
        }
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            latitude, longitude = await self._coordinates(location, session)
            params["latitude"], params["longitude"] = latitude, longitude
            async with session.get(ENDPOINT, params=params, allow_redirects=False) as response:
                if response.status != 200 or response.content_length is not None and response.content_length > MAX_RESPONSE_BYTES:
                    raise ValueError("weather provider response is unavailable")
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("weather provider response exceeds the limit")
        return normalize_open_meteo(json.loads(raw), location)
