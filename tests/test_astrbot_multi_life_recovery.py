"""Persona retirement and durable private routines across host replacement."""

import asyncio
from datetime import timedelta
import unittest

from tests.multi_life_support import MultiLifeFixture


class MultiLifeRecoveryTests(MultiLifeFixture, unittest.IsolatedAsyncioTestCase):
    async def reload(self):
        await self.controller.terminate()
        self.assertIsNone(self.controller.runtime)
        self.assertEqual(self.native.registered_web_apis, [])
        self.controller = self.make_controller()
        self.register()
        loaded = await self.controller.load_existing()
        self.assertTrue(loaded.is_success, loaded.failure)
        self.assertFalse(loaded.unwrap()["started"])
        return await self.start()

    async def test_switch_cancels_original_reader_and_restores_only_current_diary_schedule(self):
        app = await self.initialize()
        for target, role in (("first", "role-a"), ("first", "role-b"), ("second", "role-a")):
            await self.enable(target, role, diary_enabled=True, diary_time="08:10")
        book = await self.book()
        await self.start()
        original, other = self.routine(), self.routine("second")
        stale = await self.body("read", item=book, key="stale")
        entered = asyncio.Event()

        async def held(payload, tools):
            if "original_reading_span" in str(payload):
                entered.set()
                await asyncio.Event().wait()
            return await self.model(payload, tools)

        self.native.provider.client.state.behavior = held
        await self.command("read", item=book)
        await asyncio.wait_for(entered.wait(), 2)
        self.native.selections["qq-main"] = "second"
        await self.accepted(identifier="switch-to-b")
        await self.settled()
        self.assertTrue(original._retired)
        self.assertEqual(original.active_handles, ())
        self.assertEqual(set(app.journal_schedule._schedules), {other.schedule_id, self.routine(role="role-b").schedule_id})
        old = (await self.status())["activities"][0]
        self.assertEqual((old["state"], old["current_context"], old["reflection"]), ("paused", False, None))
        self.assertEqual((await self.request(data=stale))["data"]["code"], "life_view_stale")
        before = len(self.native.provider.client.state.calls)
        self.assertEqual((await self.request(data=await self.body("diary")))["data"]["code"], "life_not_bound")
        self.assertEqual(len(self.native.provider.client.state.calls), before)

        self.native.provider.client.state.behavior = self.model
        self.native.selections["qq-main"] = "original"
        await self.accepted(identifier="switch-back-a")
        await self.settled()
        current = self.routine()
        self.assertNotEqual(current.context.key, original.context.key)
        self.assertEqual(set(app.journal_schedule._schedules), {other.schedule_id, current.schedule_id})
        old = (await self.status())["activities"][0]
        retry = await self.request(data=await self.body("read", item=old, key="cannot-adopt-old"))
        self.assertEqual(retry["data"]["code"], "life_context_changed")
        added = await self.command("add_text", key="current-book", title="新绑定原文", text="切回后新提供的原文。")
        fresh = next(a for a in (await self.status())["activities"] if a["activity_id"] in added["activity_ids"])
        await self.command("read", item=fresh, key="current-read")
        await self.settled()
        self.assertEqual(current.activity(fresh["activity_id"]).state.value, "completed")
        self.assertEqual(original.activity(book["activity_id"]).state.value, "paused")
        self.assertFalse(other._retired)

    async def test_sleep_recovers_per_target_and_finished_books_and_journals_are_not_replayed(self):
        self.native.selections["qq-second"] = "second"
        app = await self.initialize()
        pairs = (("first", "role-a"), ("second", "role-b"))
        for target, role in pairs:
            await self.enable(target, role, diary_enabled=True, diary_time="23:40")
            await self.book(target, role)
        await self.start()
        for target, role in pairs:
            await self.command("read", target, role, item=(await self.status(target, role))["activities"][0])
            await self.settled()
            self.assertEqual((await self.command("diary", target, role))["state"], "written")
        sleep_a = (await self.command("sleep", minutes=1))["activity_id"]
        sleep_b = (await self.command("sleep", "second", "role-b", minutes=3))["activity_id"]
        stopped = (await self.controller.stop()).unwrap()
        self.assertEqual((stopped.state, stopped.pending_handles), ("stopped", ()))
        self.assertEqual((await self.status())["host_state"], "stopped")
        self.assertEqual(len((await self.status())["journals"]), 1)
        self.clock.advance(timedelta(seconds=61))
        app = await self.reload()
        await self.until(lambda: sleep_a in self.routine().results)
        await self.settled()
        self.assertEqual(self.routine().activity(sleep_a).state.value, "completed")
        self.assertEqual(self.routine("second", "role-b").activity(sleep_b).state.value, "active")
        self.assertEqual({j["kind"] for j in (await self.status())["journals"]}, {"diary", "dream"})
        self.clock.advance(timedelta(seconds=120))
        app.notify()
        await self.until(lambda: sleep_b in self.routine("second", "role-b").results)
        await self.settled()
        saved = {(target, role): (await self.status(target, role))["journals"] for target, role in pairs}
        calls = len(self.native.provider.client.state.calls)
        app = await self.reload()
        await self.until(lambda: all(identifier in self.routine(target, role).results
                                    for (target, role), identifier in zip(pairs, (sleep_a, sleep_b))))
        await self.settled()
        for target, role in pairs:
            status = await self.status(target, role)
            self.assertEqual(status["journals"], saved[(target, role)])
            self.assertEqual({r["state"] for r in status["receipts"] if r["operation_id"]}, {"written"})
            self.assertEqual({a["state"] for a in status["activities"]}, {"completed"})
            self.assertIsNone(status["failure_code"])
        self.assertEqual(len(self.native.provider.client.state.calls), calls)
        self.assertEqual({r["generation"] for r in app.runtime.read_all(
            "SELECT generation FROM configuration_applications WHERE group_id = 'role.life'", ())}, {3})
        self.assertEqual(len(app.journal_schedule._schedules), 2)

    async def test_stopping_dispatched_reader_preserves_unknown_and_other_target_can_progress(self):
        app = await self.initialize()
        await self.enable(reading_enabled=True)
        await self.enable("second")
        await self.book()
        await self.book("second")
        entered = asyncio.Event()

        async def held(payload, tools):
            entered.set()
            await asyncio.Event().wait()

        self.native.provider.client.state.behavior = held
        await self.start()
        await asyncio.wait_for(entered.wait(), 2)
        stopped = (await self.controller.stop(grace_seconds=0.05)).unwrap()
        self.assertEqual((stopped.state, stopped.pending_handles), ("stopped", ()))
        self.assertEqual(app.life_runtime.active_handles, ())
        book = (await self.status())["activities"][0]
        self.assertEqual((book["state"], book["task"]["state"], book["reflection"]), ("paused", "unknown", None))
        self.native.provider.client.state.behavior = self.model
        app = await self.reload()
        await self.settled()
        book = (await self.status())["activities"][0]
        denied = await self.request(data=await self.body("read", item=book, key="unknown-retry"))
        self.assertEqual(denied["data"]["code"], "life_reading_unresolved")
        self.assertEqual(len(self.native.provider.client.state.calls), 1)
        await self.command("read", "second", item=(await self.status("second"))["activities"][0])
        await self.settled()
        self.assertEqual((await self.status("second"))["activities"][0]["state"], "completed")
        self.assertEqual((await self.status())["activities"][0]["state"], "paused")
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        self.assertTrue(all(not p.client._api._wsr_api.calls for p in self.native.platforms.values()))


if __name__ == "__main__":
    unittest.main()
