"""Explicit weather source reaches planning without turning failure into a plan failure."""

from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from astrbot_host.weather import ENDPOINT, OpenMeteoWeatherPort, normalize_open_meteo
from companion_v2.agenda.planning import planning_profile
from companion_v2.agenda.planning_config import (DEFAULTS as PLANNING_DEFAULTS, MAXIMUMS as PLANNING_MAXIMUMS,
    WEATHER_MAX_AGE_MINIMUM, WeatherLocation, configured_weather_location, configured_weather_max_age)
from companion_v2.agenda.weather_material import MAX_AGE, planning_weather_material
from companion_v2.agenda.weather_reading import WeatherReading
from companion_v2.configuration.models import ConfigurationError
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskError
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.proactive.external_materials import WeatherSnapshot
from companion_v2.role_work.state.configuration import configuration_fields as state_configuration_fields
from tests.test_management_access import NOW
from tests.test_role_state import StateFixture
from tests.test_role_tool_loop import answered


LOCATION = WeatherLocation("角色所在城市", 31.23, 121.47)
LOCATION_JSON = json.dumps({"name": LOCATION.name, "latitude": LOCATION.latitude,
                            "longitude": LOCATION.longitude}, ensure_ascii=False)


class WeatherContractTests(unittest.TestCase):
    def test_explicit_location_and_provider_mapping(self):
        self.assertEqual(configured_weather_location(LOCATION_JSON), LOCATION)
        alert_location = configured_weather_location(json.dumps({**json.loads(LOCATION_JSON),
            "alert_city": "所在城市", "alert_area": "目标镇街"}, ensure_ascii=False))
        self.assertEqual((alert_location.alert_city, alert_location.alert_area), ("所在城市", "目标镇街"))
        snapshot = normalize_open_meteo({"utc_offset_seconds": 0,
            "current": {"time": "2026-09-21T09:15", "weather_code": 61,
            "temperature_2m": 22.4, "relative_humidity_2m": 75, "wind_speed_10m": 12}}, LOCATION)
        self.assertEqual(snapshot.provider, "open-meteo")
        self.assertEqual(snapshot.location, LOCATION.name)
        self.assertEqual(snapshot.condition, "小雨")
        self.assertEqual(snapshot.observed_at.utcoffset(), timedelta(0))
        with self.assertRaises(ValueError):
            normalize_open_meteo({"utc_offset_seconds": 3600,
                "current": {"time": "2026-09-21T09:15", "weather_code": 61}}, LOCATION)

    def test_invalid_location_and_stale_observation_are_excluded(self):
        for value in ('{"name":"x","latitude":91,"longitude":0}',
                      '{"name":"x","latitude":true,"longitude":0}',
                      '{"name":"x\\nother","latitude":0,"longitude":0}',
                      '{"name":"x","latitude":0,"longitude":0,"user_id":"other"}'):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                configured_weather_location(value)
        with self.assertRaises(ConfigurationError):
            configured_weather_location('{"name":"x","latitude":0,"longitude":0,"alert_area":"目标镇街"}')
        snapshot = WeatherSnapshot("open-meteo", LOCATION.name, NOW - timedelta(hours=3),
                                   20, "晴", 40, 8, ())
        self.assertIsNone(planning_weather_material(snapshot, LOCATION, NOW))
        self.assertIsNone(planning_weather_material(snapshot, WeatherLocation("另一城市", 31, 121), NOW))

    def test_supported_qweather_observations_are_usable_and_unknown_providers_are_rejected(self):
        qweather = WeatherSnapshot("qweather", LOCATION.name, NOW, 20, "晴", 40, 8, ())
        unknown = WeatherSnapshot("other-source", LOCATION.name, NOW, 20, "晴", 40, 8, ())
        self.assertEqual(planning_weather_material(qweather, LOCATION, NOW)["provider"], "qweather")
        self.assertIsNone(planning_weather_material(unknown, LOCATION, NOW))

    def test_configured_freshness_window_narrows_inside_the_structural_ceiling(self):
        # A window the operator narrows must actually shorten acceptance...
        narrowed = planning_weather_material(
            WeatherSnapshot("open-meteo", LOCATION.name, NOW - timedelta(minutes=60), 20, "晴", 40, 8, ()),
            LOCATION, NOW, max_age=timedelta(minutes=30))
        self.assertIsNone(narrowed)
        # ...while the window that produced a payload decides its own validity bound.
        material = planning_weather_material(
            WeatherSnapshot("open-meteo", LOCATION.name, NOW - timedelta(minutes=20), 20, "晴", 40, 8, ()),
            LOCATION, NOW, max_age=timedelta(minutes=30))
        self.assertEqual(material["valid_until"], (NOW - timedelta(minutes=20) + timedelta(minutes=30)).isoformat())
        # The structural ceiling cannot be widened by any caller.
        self.assertIsNone(planning_weather_material(
            WeatherSnapshot("open-meteo", LOCATION.name, NOW - timedelta(minutes=90), 20, "晴", 40, 8, ()),
            LOCATION, NOW, max_age=MAX_AGE + timedelta(minutes=1)))
        self.assertEqual(MAX_AGE, timedelta(minutes=120))

    def test_freshness_setting_is_registered_and_bounded(self):
        fields = {f.field_id: f for f in state_configuration_fields()}
        field = fields["role.state.planning_weather_max_age_minutes"]
        self.assertEqual((field.default, field.minimum, field.maximum),
                         (PLANNING_DEFAULTS["planning_weather_max_age_minutes"],
                          WEATHER_MAX_AGE_MINIMUM, PLANNING_MAXIMUMS["planning_weather_max_age_minutes"]))
        # An installation that never set the field keeps the previous two-hour behaviour.
        self.assertEqual(configured_weather_max_age({}), MAX_AGE)
        self.assertEqual(configured_weather_max_age({"planning_weather_max_age_minutes": 45}), timedelta(minutes=45))
        for rejected in (0, WEATHER_MAX_AGE_MINIMUM - 1, 121, True, "45", None):
            with self.subTest(value=rejected):
                self.assertEqual(configured_weather_max_age({"planning_weather_max_age_minutes": rejected}), MAX_AGE)


class WeatherReadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_failure_keeps_only_a_still_valid_observation_as_stale(self):
        at = [NOW]

        class Port:
            calls = 0
            fail = False

            async def fetch(self, location):
                self.calls += 1
                if self.fail:
                    raise OSError("offline")
                return WeatherSnapshot("open-meteo", location.name, at[0], 22, "小雨", 75, 12, ())

        port, reader = Port(), WeatherReading()
        live = await reader.read(port, LOCATION, max_age=timedelta(minutes=30), now=lambda: at[0])
        self.assertEqual(live["state"], "live")
        self.assertEqual(port.calls, 1)
        at[0] += timedelta(minutes=6)
        port.fail = True
        stale = await reader.read(port, LOCATION, max_age=timedelta(minutes=30), now=lambda: at[0])
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(stale["condition"], "小雨")
        self.assertEqual(port.calls, 2)
        at[0] += timedelta(seconds=10)
        limited = await reader.read(port, LOCATION, max_age=timedelta(minutes=30), now=lambda: at[0], force=True)
        self.assertTrue(limited["refresh_throttled"])
        self.assertEqual(port.calls, 2)
        at[0] += timedelta(seconds=21)
        refreshed = await reader.read(port, LOCATION, max_age=timedelta(minutes=30), now=lambda: at[0], force=True)
        self.assertFalse(refreshed.get("refresh_throttled", False))
        self.assertEqual(port.calls, 3)
        at[0] += timedelta(minutes=25)
        expired = await reader.read(port, LOCATION, max_age=timedelta(minutes=30), now=lambda: at[0])
        self.assertEqual(expired["state"], "unavailable")


class OpenMeteoPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_endpoint_and_explicit_coordinates(self):
        request = {}

        class Response:
            status = 200
            content_length = None

            def __init__(self):
                self.content = self

            async def read(self, limit):
                request["limit"] = limit
                return json.dumps({"utc_offset_seconds": 0,
                    "current": {"time": "2026-09-21T09:15", "weather_code": 0,
                    "temperature_2m": 20, "relative_humidity_2m": 50, "wind_speed_10m": 8}}).encode()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        class Session:
            def __init__(self, **kwargs):
                request["session"] = kwargs

            def get(self, url, **kwargs):
                request["url"] = url
                request["get"] = kwargs
                return Response()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        with patch("astrbot_host.weather.aiohttp.ClientSession", Session):
            snapshot = await OpenMeteoWeatherPort().fetch(LOCATION)
        self.assertEqual(request["url"], ENDPOINT)
        self.assertEqual(request["get"]["params"]["latitude"], LOCATION.latitude)
        self.assertEqual(request["get"]["params"]["longitude"], LOCATION.longitude)
        self.assertFalse(request["get"]["allow_redirects"])
        self.assertFalse(request["session"]["trust_env"])
        self.assertEqual(request["limit"], 16385)
        self.assertEqual(snapshot.condition, "晴")


class _FixedObservationPort:
    """Return one observation at a fixed age, ignoring the requested location identity."""

    def __init__(self, observed_at):
        self.observed_at = observed_at

    async def fetch(self, location):
        return WeatherSnapshot("open-meteo", location.name, self.observed_at, 22, "小雨", 75, 12, ())


class PlanningWeatherTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += (planning_profile("primary", max_output_tokens=100),)
        self.registry = FieldRegistry(version="planning-weather-tests", fields=configuration_fields(self.profiles))

    async def test_enabled_weather_reaches_model_and_fetch_failure_degrades(self):
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_enabled=True,
                       planning_weather_location=LOCATION_JSON, planning_weather_enabled=True)
        await self.start(host)
        instruction = "原角色人格提示"
        app.state_maintenance.bind(context, instruction)
        app.calendar_planning.next_checks[context.key] = NOW + timedelta(days=1)

        class WeatherPort:
            fail = False
            calls = 0

            async def fetch(self, location):
                self.calls += 1
                if self.fail:
                    raise OSError("provider unavailable")
                return WeatherSnapshot("open-meteo", location.name, NOW - timedelta(minutes=15),
                                       22, "小雨", 75, 12, ())

        port = WeatherPort()
        app.calendar_planning.weather_port = port

        async def response(_):
            return answered('{"items":[]}')

        self.model_behavior = response
        first = await app.calendar_planning.run(context, instruction, mode="daily", slot="weather-ok")
        self.assertEqual(first["state"], "succeeded", first)
        material = json.loads(self.called[-1].original.context.materials[0].payload)
        self.assertEqual(material["current_weather"]["role_location"], LOCATION.name)
        self.assertEqual(material["current_weather"]["provider"], "open-meteo")
        self.assertNotIn("weather_unavailable", material["coverage"])

        port.fail = True
        second = await app.calendar_planning.run(context, instruction, mode="daily", slot="weather-failed")
        self.assertEqual(second["state"], "succeeded", second)
        material = json.loads(self.called[-1].original.context.materials[0].payload)
        self.assertNotIn("current_weather", material)
        self.assertTrue(material["coverage"]["weather_unavailable"])
        self.assertEqual(port.calls, 2)
        self.assertEqual(self.sent, [])

    async def test_location_change_during_fetch_discards_old_observation(self):
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_enabled=True,
                       planning_weather_location=LOCATION_JSON, planning_weather_enabled=True)
        await self.start(host)
        app.state_maintenance.bind(context, "原角色人格提示")
        app.calendar_planning.next_checks[context.key] = NOW + timedelta(days=1)
        changed = WeatherLocation("新城市", 39.9, 116.4)
        changed_json = json.dumps({"name": changed.name, "latitude": changed.latitude,
                                   "longitude": changed.longitude}, ensure_ascii=False)
        test = self

        class ChangingPort:
            async def fetch(self, location):
                test.assertEqual(location, LOCATION)
                test.configure(manager, planning_weather_location=changed_json)
                return WeatherSnapshot("open-meteo", location.name, NOW - timedelta(minutes=15),
                                       22, "小雨", 75, 12, ())

        app.calendar_planning.weather_port = ChangingPort()

        async def response(_):
            return answered('{"items":[]}')

        self.model_behavior = response
        result = await app.calendar_planning.run(context, "原角色人格提示", mode="daily", slot="location-changed")
        self.assertEqual(result["state"], "succeeded", result)
        material = json.loads(self.called[-1].original.context.materials[0].payload)
        self.assertNotIn("current_weather", material)
        self.assertTrue(material["coverage"]["weather_unavailable"])

    async def test_weather_remains_off_by_default(self):
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_enabled=True)
        await self.start(host)
        app.state_maintenance.bind(context, "原角色人格提示")
        app.calendar_planning.next_checks[context.key] = NOW + timedelta(days=1)

        class UnexpectedPort:
            async def fetch(self, location):
                raise AssertionError("weather must stay disabled")

        app.calendar_planning.weather_port = UnexpectedPort()

        async def response(_):
            return answered('{"items":[]}')

        self.model_behavior = response
        result = await app.calendar_planning.run(context, "原角色人格提示", mode="daily", slot="weather-off")
        self.assertEqual(result["state"], "succeeded", result)
        material = json.loads(self.called[-1].original.context.materials[0].payload)
        self.assertNotIn("current_weather", material)
        self.assertNotIn("weather_unavailable", material["coverage"])

    async def test_narrowed_freshness_window_excludes_an_older_observation(self):
        """The setting reaches planning, and its own window decides acceptance."""
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_enabled=True,
                       planning_weather_location=LOCATION_JSON, planning_weather_enabled=True,
                       planning_weather_max_age_minutes=30)
        await self.start(host)
        app.state_maintenance.bind(context, "原角色人格提示")
        app.calendar_planning.next_checks[context.key] = NOW + timedelta(days=1)
        # Fresh enough for the default two hours, too old for the configured thirty minutes.
        app.calendar_planning.weather_port = _FixedObservationPort(NOW - timedelta(minutes=60))

        async def response(_):
            return answered('{"items":[]}')

        self.model_behavior = response
        result = await app.calendar_planning.run(context, "原角色人格提示", mode="daily", slot="narrow")
        self.assertEqual(result["state"], "succeeded", result)
        material = json.loads(self.called[-1].original.context.materials[0].payload)
        self.assertNotIn("current_weather", material)
        self.assertTrue(material["coverage"]["weather_unavailable"])

    async def test_disabled_planning_does_not_fetch_configured_weather(self):
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_weather_location=LOCATION_JSON,
                       planning_weather_enabled=True)
        await self.start(host)
        app.state_maintenance.bind(context, "原角色人格提示")

        class UnexpectedPort:
            async def fetch(self, location):
                raise AssertionError("planning is disabled")

        app.calendar_planning.weather_port = UnexpectedPort()
        with self.assertRaises(TaskError) as raised:
            await app.calendar_planning.run(context, "原角色人格提示", mode="daily", slot="disabled")
        self.assertEqual(raised.exception.code, "planning_disabled")
