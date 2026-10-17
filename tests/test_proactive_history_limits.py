"""Proactive generation history limits: configured item/char caps on the compose snapshot."""

import json
import unittest

from companion_v2.proactive.prompts import history_round_groups
from tests.contact_schedule_support import ContactScheduleFixture


class ProactiveHistoryLimitTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    def test_split_bubbles_share_one_history_round_and_keep_part_coverage(self):
        items = tuple({"role": "assistant", "delivered_at": f"2026-10-17T10:00:0{index}+00:00",
                       "text": text, "_history_round": "delivery:one",
                       "_history_part": {"sequence": index + 1, "part_count": 3}}
                      for index, text in enumerate(("先说", "再接着说", "最后说")))

        rounds = history_round_groups(items)

        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["indices"], (0, 1, 2))
        self.assertEqual(rounds[0]["item"]["messages"], [
            {"role": "assistant", "delivered_at": "2026-10-17T10:00:00+00:00", "text": "先说"},
            {"role": "assistant", "delivered_at": "2026-10-17T10:00:01+00:00", "text": "再接着说"},
            {"role": "assistant", "delivered_at": "2026-10-17T10:00:02+00:00", "text": "最后说"},
        ])
        self.assertEqual(rounds[0]["item"]["message_parts"], {
            "received": [1, 2, 3], "expected": 3, "complete": True})
        self.assertEqual(rounds[0]["size"], len(json.dumps(rounds[0]["item"], ensure_ascii=False)))

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

    async def test_history_window_defaults_to_eight_rounds(self):
        app = await self.enabled()
        self.assertEqual(self.preferences(app).values["generation_history_limit"], 8)
        self.assertFalse(self.settings(app, {"generation_history_limit": 9}).is_success)

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

    async def test_recent_user_answer_survives_a_run_of_newer_contact_messages(self):
        from companion_v2.conversation.flow import ConversationPolicy

        host = await self.start(self.host(policy=ConversationPolicy(0, 0, 180, 0)))
        app = host.application
        self.settings(app, {"enabled": True, "dedup_enabled": False,
                            "max_contacts_24h": 100}).unwrap()
        batch = host.receive(self.event("answered-lunch", text="吃了啦")).unwrap()
        await self.done(app, batch)

        for index in range(7):
            task = (await self.contact(app, self.opportunity(f"history-run-{index}"))).unwrap().task
            await self.delivery_state(app, task.task_id, "delivered")
            self.advance(app, 1)

        await self.contact(app, self.opportunity("history-retention-check"))
        request = self.contact_calls()[-1].original
        dialogue = [item.payload for item in request.context.materials
                    if item.purpose == "recent_private_dialogue"]
        self.assertTrue(any("吃了啦" in payload for payload in dialogue))


if __name__ == "__main__":
    unittest.main()
