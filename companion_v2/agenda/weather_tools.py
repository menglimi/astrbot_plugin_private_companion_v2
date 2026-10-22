"""On-demand, private-conversation reads of the configured role's weather."""

import asyncio
from datetime import datetime
import math

from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError, encode
from companion_v2.foundation.refs import ScopeKind
from companion_v2.model_gateway.models import ToolSpec
from companion_v2.agenda.planning_config import (
    configured_weather_location,
    configured_weather_max_age,
)
from companion_v2.agenda.weather_material import (
    FUTURE_TOLERANCE,
    SUPPORTED_PROVIDERS,
    planning_weather_material,
)


ACTION = "weather.current"
INSTRUCTION = (
    "天气实况只代表已配置的角色地点，不代表用户设备的当前位置。用户询问天气或天气相关出行时再读取；结合观测时间回答，地点不同要先说明，读取失败或资料过期时不猜测当前天气。"
)
MAX_FETCH_SECONDS = 7


class WeatherTools:
    actions = frozenset({ACTION})

    def __init__(self, port, role_state):
        self.port, self.role_state = port, role_state
        self.catalog = (ToolSpec(ACTION, "读取已配置角色地点的当前天气实况。", encode({
            "type": "object", "properties": {}, "additionalProperties": False,
        })),)

    def _configuration(self, context):
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("weather_private_required", "weather reads are available in private conversations only")
        if self.role_state is None:
            raise TaskError("weather_settings_unavailable", "weather settings are unavailable")
        values, _token = self.role_state.settings(context)
        if values.get("planning_weather_enabled") is not True:
            raise TaskError("weather_disabled", "enable role weather before reading current weather")
        location = configured_weather_location(values.get("planning_weather_location", ""))
        if location is None:
            raise TaskError("weather_location_required", "set the role location before reading current weather")
        return values, location, configured_weather_max_age(values)

    def catalog_for(self, context):
        try:
            self._configuration(context)
        except (TaskError, ConfigurationError):
            return ()
        return self.catalog

    async def execute(self, run, context, arguments, *, observed_at):
        if type(arguments) is not dict or arguments:
            return {"state": "failed", "code": "invalid_tool_arguments", "effect": "none"}
        try:
            _values, location, max_age = self._configuration(context)
        except (TaskError, ConfigurationError) as error:
            return {"state": "failed", "code": getattr(error, "code", "weather_settings_invalid"), "effect": "none"}
        if self.port is None:
            return {"state": "failed", "code": "weather_source_unavailable", "effect": "none"}
        try:
            snapshot = await asyncio.wait_for(self.port.fetch(location), timeout=MAX_FETCH_SECONDS)
        except Exception:
            return {"state": "failed", "code": "weather_source_unavailable", "effect": "none"}
        run.validate()
        material = planning_weather_material(snapshot, location, observed_at, max_age=max_age)
        if not self._valid_material(material):
            return {"state": "failed", "code": "weather_observation_unavailable", "effect": "none"}
        return {"state": "succeeded", "effect": "none", "payload": material}

    @staticmethod
    def _valid_material(material):
        if type(material) is not dict:
            return False
        required = {"basis", "provider", "role_location", "observed_at", "valid_until",
                    "condition", "temperature_c", "humidity_pct", "wind_kph"}
        if not required <= set(material) or set(material) - required - {"weather_code"}:
            return False
        if (material["basis"] != "external_current_observation"
                or material["provider"] not in SUPPORTED_PROVIDERS
                or type(material["role_location"]) is not str
                or not 1 <= len(material["role_location"]) <= 64
                or type(material["condition"]) is not str
                or not material["condition"] or len(material["condition"]) > 64):
            return False
        temperature = material["temperature_c"]
        if type(temperature) not in (int, float) or not math.isfinite(temperature):
            return False
        for key, minimum, maximum in (("humidity_pct", 0, 100), ("wind_kph", 0, None)):
            value = material[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                    or value < minimum or maximum is not None and value > maximum):
                return False
        if "weather_code" in material and type(material["weather_code"]) is not int:
            return False
        try:
            observed = datetime.fromisoformat(material["observed_at"])
            valid_until = datetime.fromisoformat(material["valid_until"])
        except (TypeError, ValueError):
            return False
        return observed.tzinfo is not None and valid_until.tzinfo is not None

    def validate(self, row, context, result, observed_at):
        _values, location, max_age = self._configuration(context)
        payload = result.get("payload") if type(result) is dict else None
        if not self._valid_material(payload) or payload["role_location"] != location.name:
            raise TaskError("weather_result_invalid", "the original weather observation is invalid")
        observed = datetime.fromisoformat(payload["observed_at"])
        valid_until = datetime.fromisoformat(payload["valid_until"])
        if (valid_until != observed + max_age
                or not -FUTURE_TOLERANCE <= observed_at - observed <= max_age):
            raise TaskError("weather_observation_stale", "the original weather observation is no longer current")
        if result.get("state") != "succeeded" or result.get("effect") != "none":
            raise TaskError("weather_result_invalid", "the original weather result changed")
        return result, None


__all__ = ["ACTION", "INSTRUCTION", "WeatherTools"]
