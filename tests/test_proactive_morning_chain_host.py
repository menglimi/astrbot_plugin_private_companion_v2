"""Morning chain through the real contact scheduler and proactive ledger."""

import json
import unittest
from unittest.mock import patch

from companion_v2.proactive.configuration import PURPOSES
from companion_v2.proactive.morning_rhythm import RoutineSample
from companion_v2.proactive.wake_events import WakeContactEvents
from tests.contact_schedule_support import ContactScheduleFixture


class MorningChainHostTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def morning_host(self):
        host, _ = await self.scheduled()
        app = host.application
        context = self.contact_context()
        self.grant(context.actor, context.scope, "role.life.run")
        self.grant(context.actor, context.scope, "role.life.read")
        self.grant(context.actor, context.scope, "role.state.read")
        routine = app.life_runtime.bind(context, "原角色人格提示")
        sleep = routine.start_sleep("morning-sleep", 30)
        self.advance(app, 5)
        routine.wake(sleep.activity_id, expected_revision=sleep.revision,
                     operation_id="morning-wake")
        changes = {purpose + ".enabled": False for purpose in PURPOSES}
        changes.update({
            "greeting.enabled": True,
            "morning_chain_enabled": True,
            "morning_role_greeting_enabled": True,
            "morning_nudge_enabled": True,
            "routine_learning_enabled": True,
            "enable_daily_greetings": False,
            "dedup_enabled": False,
            "max_contacts_24h": 5,
            "morning_nudge_delay_minutes": 25,
            "wake_contact_max_daily": 1,
        })
        self.settings(app, changes).unwrap()
        events = app.contact_schedule.wake_events
        if events is None:
            events = WakeContactEvents(app.proactive, app.role_state, lambda context: {})
            app.contact_schedule.wake_events = events
        events.port = lambda context: {}
        samples = tuple(RoutineSample(f"2026-09-{day:02d}", wake_minutes=8 * 60)
                        for day in range(7, 12))
        return host, app, context, events, samples

    def marker(self, app, index=0):
        row = self.contacts(app)[index]
        return json.loads(row["record_json"])["automatic_origin"]["morning_event"]

    async def test_role_morning_is_queued_once_per_local_day(self):
        host, app, context, events, samples = await self.morning_host()
        with patch.object(events, "_routine_samples", return_value=samples):
            self.advance(app, 60)
            await self.automatic_delivery(app)
        record = json.loads(self.contacts(app)[0]["record_json"])
        self.assertEqual(record["purpose"], "greeting")
        self.assertEqual(self.marker(app)["action"], "role_morning")
        self.assertEqual(self.marker(app)["local_date"], "2026-09-21")
        with patch.object(events, "_routine_samples", return_value=samples):
            self.advance(app, 60)
            await self.until(lambda: not app.contact_schedule._workers)
        self.assertEqual(len(self.contacts(app)), 1)

    async def test_one_wake_nudge_follows_the_unanswered_role_morning(self):
        host, app, context, events, samples = await self.morning_host()
        with patch.object(events, "_routine_samples", return_value=samples):
            self.advance(app, 60)
            await self.automatic_delivery(app)
            await self.until(lambda: not app.contact_schedule._workers)
            await self.until(lambda: app.runtime.read_one(
                "SELECT COUNT(*) FROM execution_attempts WHERE lane = 'background' AND slot_held = 1", ())[0] == 0)
            events.port = lambda context: {"mobile": {
                "activity": {"available": True, "stale": False, "age_seconds": 20},
                "telemetry": {"available": True, "activity": {"state": "walking"}}}}
            self.advance(app, 25 * 60)
            await self.automatic_delivery(app, count=2)
        self.assertEqual([self.marker(app, index)["action"] for index in range(2)],
                         ["role_morning", "wake_nudge"])
        with patch.object(events, "_routine_samples", return_value=samples):
            self.advance(app, 60)
            await self.until(lambda: not app.contact_schedule._workers)
        self.assertEqual(len(self.contacts(app)), 2)


if __name__ == "__main__":
    unittest.main()