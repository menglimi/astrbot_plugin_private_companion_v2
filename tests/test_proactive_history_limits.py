"""Proactive generation history limits: configured item/char caps on the compose snapshot."""

import unittest

from tests.contact_schedule_support import ContactScheduleFixture


class ProactiveHistoryLimitTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def confirmed(self, app, tag=""):
        source = self.source(app)
        opportunity = self.opportunity(tag)
        task = (await self.contact(app, opportunity,
                                   (self.intent(opportunity, sources=(source,)),))).unwrap().task
        await self.delivery_state(app, task.task_id, "delivered")
        self.advance(app, 1)

    async def test_configured_limits_reach_the_compose_snapshot(self):
        app = await self.enabled()
        self.settings(app, {"dedup_enabled": False, "generation_history_limit": 1,
                            "history_max_chars": 8192}).unwrap()
        self.assertEqual(self.preferences(app).values["generation_history_limit"], 1)
        await self.confirmed(app, "one")
        await self.confirmed(app, "two")
        context = self.contact_context()
        full = app.background_history.capture(context, self.clock.now(), action="proactive.contact")
        self.assertEqual(len(full["references"]), 2)
        limited = app.background_history.capture(context, self.clock.now(), action="proactive.contact", limit=1)
        self.assertEqual(len(limited["references"]), 1)
        self.advance(app, 1)
        await self.confirmed(app, "three")
        materials = [m for m in self.called[-1].original.context.materials if m.owner == "delivery.history"]
        self.assertLessEqual(len(materials), 1)

    async def test_capture_clamps_override_to_hard_bounds(self):
        app = await self.enabled()
        self.settings(app, {"dedup_enabled": False}).unwrap()
        await self.confirmed(app, "one")
        await self.confirmed(app, "two")
        context = self.contact_context()
        at = self.clock.now()
        clamped = app.background_history.capture(context, at, action="proactive.contact",
                                                 limit=99, max_chars=10 ** 9)
        self.assertEqual(len(clamped["references"]), 2)
        empty = app.background_history.capture(context, at, action="proactive.contact", limit=0)
        self.assertEqual(empty["references"], [])


if __name__ == "__main__":
    unittest.main()
