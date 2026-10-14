"""Current role-location weather through the private automatic contact path."""

from datetime import timedelta
from dataclasses import replace
import json
import unittest

from companion_v2.conversation.foreground import BackgroundPromptTrigger
from companion_v2.proactive.external_materials import WeatherSnapshot
from companion_v2.proactive.weather_events import SOURCE_OWNER
from companion_v2.execution.models import TaskError
from companion_v2.role_work.state.management import StateManagement
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_planning_weather import LOCATION, LOCATION_JSON
from tests.test_role_tool_loop import answered


class WeatherContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_weather_diagnostic_fetches_outside_daily_slot_and_validates_qweather(self):
        app, context, manager = await self.setup_weather()
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        events = app.contact_schedule.weather_events
        events.port = SimpleNamespace(provider="qweather", fetch=AsyncMock(return_value=replace(self.snapshot(), provider="qweather")))
        preferences = self.preferences(app, context)
        self.assertIsNone(events.select(context, preferences, self.clock.now()))
        candidate, stages = await events.diagnostic_candidate(context, preferences, test_id="weather-test")
        events.port.fetch.assert_awaited_once_with(LOCATION)
        self.assertEqual(stages[0]["stage"], "weather_fetch")
        events.validate(context, candidate[2], self.clock.now())
        self.assertEqual(events.retry_at, {})
        before = manager.status(self.core).unwrap()
        manager.command(self.core, dict(action="configure", operation_key="change-weather-location",
            edit_token=before["edit_token"], role_edit_token=before["role_edit_token"], changes={"planning_weather_location": ""})).unwrap()
        with self.assertRaises(TaskError):
            events.validate(context, candidate[2], self.clock.now())

    async def setup_weather(self, *, enabled=True, location=LOCATION_JSON):
        host, batch = await self.scheduled()
        self.host_instance = host
        app = host.application
        context = self.context(app, batch)
        manager = StateManagement(app, context)
        if location:
            before = manager.status(self.core).unwrap()
            manager.command(self.core, dict(action="configure", operation_key="weather-location",
                edit_token=before["edit_token"], role_edit_token=before["role_edit_token"], changes={"planning_weather_location": location})).unwrap()
        settings = {"chat.enabled": False, "weather_checkin_time": "08:01"}
        if enabled is not None:
            settings["weather_checkin_enabled"] = enabled
        self.settings(app, settings).unwrap()
        return app, context, manager

    def snapshot(self, location=LOCATION):
        return WeatherSnapshot("open-meteo", location.name, self.clock.now() - timedelta(minutes=10),
                               22, "小雨", 75, 12, ())

    async def test_opt_in_and_location_are_required(self):
        app, _, _ = await self.setup_weather(enabled=None, location="")
        self.assertFalse(self.preferences(app).values["weather_checkin_enabled"])
        self.assertFalse(self.settings(app, {"weather_checkin_time": "25:00"}).is_success)
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])

        self.settings(app, {"weather_checkin_enabled": True}).unwrap()
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])

    async def test_fresh_observation_reaches_model_once_and_restart_does_not_repeat(self):
        app, _, _ = await self.setup_weather()

        class WeatherPort:
            calls = 0

            async def fetch(self, location):
                self.calls += 1
                return test.snapshot(location)

        test = self
        port = WeatherPort()
        app.contact_schedule.weather_events.port = port
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.assertEqual(port.calls, 1)
        self.assertEqual(len(self.contact_calls()), 1)
        request = self.contact_calls()[0].original
        evidence = [json.loads(item.payload) for item in request.context.materials if item.owner == SOURCE_OWNER]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["event"], "role_location_current_weather")
        self.assertEqual(evidence[0]["role_location"], LOCATION.name)
        self.assertEqual(evidence[0]["provider"], "open-meteo")
        self.assertNotIn("_receipt", evidence[0])
        self.assertIn("不代表对方所在地", evidence[0]["meaning"])
        self.assertEqual(json.loads(self.contacts(app)[0]["record_json"])["purpose"], "environment")
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        restarted.contact_schedule.weather_events.port = port
        restarted.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.assertEqual(len(self.contact_calls()), 1)

    async def test_fetch_failure_retries_after_backoff_without_contact(self):
        app, _, _ = await self.setup_weather()

        class WeatherPort:
            calls = 0

            async def fetch(self, location):
                self.calls += 1
                raise OSError("weather unavailable")

        port = WeatherPort()
        app.contact_schedule.weather_events.port = port
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        app.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.assertEqual(self.contacts(app), ())
        self.assertEqual(self.contact_calls(), [])
        self.clock.advance(timedelta(minutes=5))
        app.contact_schedule.advance()
        await self.until(lambda: port.calls == 2)
        self.assertEqual(self.contacts(app), ())

    async def test_disabling_during_fetch_discards_observation(self):
        app, _, _ = await self.setup_weather()
        test = self

        class WeatherPort:
            calls = 0

            async def fetch(self, location):
                self.calls += 1
                test.settings(app, {"weather_checkin_enabled": False}).unwrap()
                return test.snapshot(location)

        port = WeatherPort()
        app.contact_schedule.weather_events.port = port
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        self.assertEqual(self.contact_calls(), [])
        self.assertEqual(self.contacts(app), ())

    async def test_new_conversation_during_fetch_discards_old_candidate(self):
        app, _, _ = await self.setup_weather()
        test = self

        class WeatherPort:
            calls = 0

            async def fetch(self, location):
                self.calls += 1
                batch = test.host_instance.receive(test.event("new-input")).unwrap()
                await test.done(app, batch)
                return test.snapshot(location)

        port = WeatherPort()
        app.contact_schedule.weather_events.port = port
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        self.assertEqual(self.contact_calls(), [])
        self.assertEqual(self.contacts(app), ())

    async def test_location_change_during_generation_invalidates_old_source(self):
        app, _, manager = await self.setup_weather()
        test = self

        class WeatherPort:
            async def fetch(self, location):
                return test.snapshot(location)

        app.contact_schedule.weather_events.port = WeatherPort()

        async def change_location(envelope):
            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                before = manager.status(self.core).unwrap()
                manager.command(self.core, dict(action="configure", operation_key="new-weather-location",
                    edit_token=before["edit_token"], role_edit_token=before["role_edit_token"], changes={"planning_weather_location":
                        json.dumps({"name": "新城市", "latitude": 39.9, "longitude": 116.4},
                                   ensure_ascii=False)})).unwrap()
                return answered('{"decision":"send","text":"旧城市天气"}')
            return answered("收到。")

        self.model_behavior = change_location
        self.advance(app, 60)
        await self.until(lambda: len(self.contact_calls()) == 1)
        await self.until(lambda: not app.proactive.active_handles)
        self.assertEqual(self.contacts(app), ())
        self.assertEqual(len(self.sent), 1)
        material = next(item for item in self.contact_calls()[0].original.context.materials
                        if item.owner == SOURCE_OWNER)
        self.assertFalse(app.proactive.sources.validate_reference(material.source,
            observed_at=self.clock.now()).is_success)
