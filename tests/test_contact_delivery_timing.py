"""Exercise real timers and shared capacity, using isolated model/send ports."""

import asyncio
from datetime import datetime, timezone
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.proactive_support import ContactFixture
from tests.test_role_tool_loop import answered


class ContactDeliveryTimingTests(ContactFixture, unittest.IsolatedAsyncioTestCase):
    async def test_wall_clock_parts_follow_configured_gap_without_a_polling_second(self):
        self.clock = SimpleNamespace(now=lambda: datetime.now(timezone.utc))
        self.receipt_now = self.clock.now
        app = await self.enabled(now=self.clock.now)
        from tests.test_proactive_contacts import ProactiveContactTests
        ProactiveContactTests.presentation_settings(self, app, {
            "enabled": True, "llm_controlled": True, "rules_enabled": False,
            "part_gap_mode": "fixed", "part_gap_ms": 150,
        }).unwrap()
        sent_at = []

        async def model(_envelope):
            return answered(json.dumps({"decision": "send", "text":
                "第一句。\n<<PRIVATE_COMPANION_SPLIT>>\n第二句。\n<<PRIVATE_COMPANION_SPLIT>>\n第三句。"},
                ensure_ascii=False))

        async def send(envelope):
            sent_at.append(time.monotonic())
            return self.receipt(envelope)

        self.model_behavior, self.send_behavior = model, send
        task = (await self.contact(app)).unwrap().task
        await self.until(lambda: len(self.sent) == 3 and all(
            row["state"] == "delivered" for row in app.proactive._delivery_rows(task.task_id)))
        self.assertEqual([part.sequence for part in self.sent], [0, 1, 2])
        for previous, current in zip(sent_at, sent_at[1:]):
            self.assertGreaterEqual(current - previous, 0.15)
            self.assertLess(current - previous, 0.9,
                            "delivery waited for a whole maintenance/polling cycle")

    async def test_saturated_shared_lane_has_no_due_delivery_wake(self):
        app = await self.enabled()
        entered, release = asyncio.Event(), asyncio.Event()

        async def held(_envelope):
            entered.set()
            await release.wait()
            return answered('{"decision":"send","text":"下一条"}')

        other = self.opportunity("other")
        # Keep a legitimate delivery queued while composition holds the shared
        # lane. The source and original permission checks still execute.
        with patch.object(app.background, "advance", return_value=False):
            second = (await self.contact(app, other, administrator_test=True)).unwrap().task
            self.assertIsNotNone(app.outbound.next_wake())
            self.model_behavior = held
            third = asyncio.create_task(self.contact(app, self.opportunity("held"), administrator_test=True))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                self.assertIsNone(app.background.next_wake())
            finally:
                release.set()
                await third
        app.notify()
        await self.delivery_state(app, second.task_id, "delivered")


if __name__ == "__main__":
    unittest.main()
