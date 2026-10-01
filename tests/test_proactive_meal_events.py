"""Meal opportunities reuse the original private contact and delivery path."""

from datetime import datetime, timedelta
import json
import unittest

from companion_v2.conversation.foreground import BackgroundPromptTrigger
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_role_tool_loop import answered


class MealContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_meal(self, *, enabled=True):
        host, batch = await self.scheduled()
        app = host.application
        settings = {"chat.enabled": False, "meal_lunch_time": "08:01"}
        if enabled is not None:
            settings["meal_checkin_enabled"] = enabled
        self.settings(app, settings).unwrap()
        return app, batch

    async def test_opt_in_is_required_and_invalid_local_time_is_rejected(self):
        app, _ = await self.setup_meal(enabled=None)
        self.assertFalse(self.preferences(app).values["meal_checkin_enabled"])
        self.assertFalse(self.settings(app, {"meal_lunch_time": "25:00"}).is_success)
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])

    async def test_current_lunch_slot_sends_once_and_restart_does_not_repeat_it(self):
        app, _ = await self.setup_meal()
        self.advance(app, 60)
        await self.automatic_delivery(app)
        calls = self.contact_calls()
        self.assertEqual(len(calls), 1)
        request = calls[0].original
        self.assertIn("午餐", request.context.materials[0].payload)
        self.assertEqual([item.payload for item in request.context.materials
                          if item.purpose == "contact_evidence"], ["输入 event-1"])
        record = json.loads(self.contacts(app)[0]["record_json"])
        self.assertEqual(record["purpose"], "meal")
        self.assertEqual(record["automatic_origin"]["meal_event"]["slot"], "lunch")
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime()), 1, 1)).application
        restarted.contact_schedule.advance()
        self.assertEqual(len(self.contact_calls()), 1)

    async def test_slot_change_during_generation_discards_the_old_draft(self):
        app, _ = await self.setup_meal()

        async def change_slot(envelope):
            if isinstance(envelope.original.event, BackgroundPromptTrigger):
                self.settings(app, {"meal_lunch_time": "12:00"}).unwrap()
                return answered('{"decision":"send","text":"该吃饭了"}')
            return answered("收到。")

        self.model_behavior = change_slot
        self.advance(app, 60)
        await self.until(lambda: len(self.contact_calls()) == 1)
        await self.until(lambda: not app.proactive.active_handles)
        self.assertEqual(self.contacts(app), ())
        self.assertEqual(len(self.sent), 1)

    async def test_expired_slot_does_not_catch_up(self):
        app, _ = await self.setup_meal()
        self.clock.advance(timedelta(hours=2))
        app.contact_schedule.advance()
        self.assertEqual(self.contact_calls(), [])


class MealFollowupWindowTests(MealContactTests):
    """C2-5: the meal slot's width is configuration, not a hard-coded 45 minutes."""

    async def slot_at(self, app, *, minutes_after_open):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        from companion_v2.proactive.configuration import local_time
        preferences = self.preferences(app)
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        day = self.clock.now().astimezone(zone).date()
        wall = local_time(preferences.values["meal_lunch_time"])
        opened = datetime.combine(day, wall, tzinfo=zone).astimezone(timezone.utc)
        return app.contact_schedule.meal_events._slots(
            self.contact_context(), preferences, opened + timedelta(minutes=minutes_after_open))

    async def test_the_default_keeps_the_original_forty_five_minutes(self):
        app, _ = await self.setup_meal()
        self.assertEqual(self.preferences(app).values["meal_care_followup_minutes"], 45)
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=44)), 1)
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=45)), 0)

    async def test_a_wider_window_holds_the_slot_open_longer(self):
        app, _ = await self.setup_meal()
        self.settings(app, {"meal_care_followup_minutes": 120}).unwrap()
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=119)), 1)
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=120)), 0)

    async def test_a_narrower_window_closes_the_slot_earlier(self):
        app, _ = await self.setup_meal()
        self.settings(app, {"meal_care_followup_minutes": 10}).unwrap()
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=9)), 1)
        self.assertEqual(len(await self.slot_at(app, minutes_after_open=10)), 0)

    async def test_the_window_is_bounded_on_both_sides(self):
        app, _ = await self.setup_meal()
        self.assertFalse(self.settings(app, {"meal_care_followup_minutes": 0}).is_success)
        self.assertFalse(self.settings(app, {"meal_care_followup_minutes": 241}).is_success)
        self.assertTrue(self.settings(app, {"meal_care_followup_minutes": 240}).is_success)

    async def test_the_opportunity_expiry_tracks_the_configured_window(self):
        # The marker's expiry must come from the same window, or a widened slot would
        # still be judged expired against the old constant.
        app, _ = await self.setup_meal()
        self.settings(app, {"meal_care_followup_minutes": 120}).unwrap()
        (opportunity, marker, _label), = await self.slot_at(app, minutes_after_open=60)
        self.assertEqual((opportunity.expires_at - opportunity.opened_at), timedelta(minutes=120))
        self.assertEqual(datetime.fromisoformat(marker["expires_at"]),
                         datetime.fromisoformat(marker["opened_at"]) + timedelta(minutes=120))
