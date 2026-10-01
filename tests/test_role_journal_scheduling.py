"""The shared host timer owns daily wakeups and cancellation; no catch-up loop."""

import asyncio
from datetime import datetime, time, timedelta, timezone
import unittest

from companion_v2.role_work.journal import JournalKind, JournalState
from companion_v2.role_work.journal.scheduling import next_daily
from tests.test_management_access import NOW
from tests.test_role_journal_triggers import JournalTriggerFixture
from tests.test_role_tool_loop import answered


class JournalSchedulingTests(JournalTriggerFixture, unittest.IsolatedAsyncioTestCase):
    def register(self, identifier="daily", local_time="08:01"):
        return self.app.journal_schedule.register_daily(identifier, self.task_context, self.trigger,
            role_instruction="原角色人格", timezone="Asia/Shanghai", local_time=local_time).unwrap()

    async def test_explicit_daily_registration_runs_on_shared_wakeup_once_per_date(self):
        await self.setup_triggers()
        registered = self.register()
        self.assertEqual(registered.next_at, NOW + timedelta(minutes=1))
        self.assertEqual(self.app.journal_schedule.next_wake(), registered.next_at)
        self.advance(self.app, 59)
        await asyncio.sleep(0.01)
        self.assertEqual(self.called, [])
        self.advance(self.app, 1)
        await self.until(lambda: "daily" in self.app.journal_schedule.results)
        first = self.app.journal_schedule.results["daily"].unwrap()
        self.assertEqual(first.state, "written")
        self.assertEqual(self.app.journal_schedule.next_wake(), NOW + timedelta(days=1, minutes=1))
        self.app.notify()
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.called), 1)
        self.advance(self.app, 86400)
        await self.until(lambda: self.app.role_journal.head(self.target("2026-09-22").key).state is JournalState.ACTIVE)
        self.assertEqual(len(self.called), 2)
        self.assertEqual(self.app.role_journal.head(self.target(kind=JournalKind.DREAM).key).state, JournalState.ABSENT)
        self.assertEqual(self.sent, [])

    async def test_real_timer_requires_no_manual_tick_and_repeated_registration_keeps_deadline(self):
        current = lambda: datetime.now(timezone.utc)
        await self.setup_triggers(now=current)
        from zoneinfo import ZoneInfo
        local_at = (current() + timedelta(seconds=0.08)).astimezone(ZoneInfo("Asia/Shanghai")).time().isoformat()
        registered = self.register(local_time=local_at)
        self.assertEqual(self.register(local_time=local_at), registered)
        await self.until(lambda: "daily" in self.app.journal_schedule.results)
        self.assertEqual(self.app.journal_schedule.results["daily"].unwrap().state, "written")
        self.assertEqual(len(self.called), 1)

    async def test_restart_requires_fresh_registration_and_does_not_backfill_missed_days(self):
        await self.setup_triggers()
        self.register()
        await self.reopen()
        self.advance(self.app, 2 * 86400 + 120)
        await asyncio.sleep(0.01)
        self.assertEqual(self.called, [])
        self.assertIsNone(self.app.journal_schedule.next_wake())
        registered = self.register()
        self.assertEqual(registered.next_at, NOW + timedelta(days=3, minutes=1))
        self.assertEqual(self.called, [])

    async def test_delayed_wakeup_handles_current_day_only_without_backlog(self):
        await self.setup_triggers()
        self.register()
        self.advance(self.app, 2 * 86400 + 120)
        await self.until(lambda: "daily" in self.app.journal_schedule.results)
        self.assertEqual(self.app.role_journal.head(self.target("2026-09-23").key).state, JournalState.ACTIVE)
        self.assertEqual(self.app.role_journal.head(self.target("2026-09-21").key).state, JournalState.ABSENT)
        self.assertEqual(self.app.role_journal.head(self.target("2026-09-22").key).state, JournalState.ABSENT)
        self.assertEqual(len(self.called), 1)

    async def test_remove_before_due_disarms_and_repeated_id_cannot_change_binding(self):
        await self.setup_triggers()
        self.register()
        changed = self.app.journal_schedule.register_daily("daily", self.task_context, self.trigger,
            role_instruction="changed", timezone="Asia/Shanghai", local_time="08:01")
        self.assertEqual(changed.failure.code, "journal_schedule_conflict")
        self.assertTrue(self.app.journal_schedule.remove("daily"))
        self.advance(self.app, 120)
        await asyncio.sleep(0.01)
        self.assertEqual(self.called, [])
        self.assertIsNone(self.app.journal_schedule.next_wake())

    async def test_foreground_still_runs_during_daily_writing_and_shutdown_owns_all_handles(self):
        await self.setup_triggers()
        entered = asyncio.Event()
        async def model(envelope):
            if envelope.original.output_format == "conversation":
                return answered("我在。")
            entered.set()
            await asyncio.Event().wait()
        self.model_behavior = model
        self.register(local_time="08:00")
        await asyncio.wait_for(entered.wait(), 2)
        batch = self.host_instance.receive(self.event("foreground")).unwrap()
        self.advance(self.app, 1)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual(len(self.sent), 1)
        report = await self.app.close()
        self.assertEqual(report.state, "stopped")
        self.assertEqual(self.app.active_handles, ())
        self.assertEqual(self.app.role_journal.head(self.target().key).state, JournalState.ABSENT)


class DailyTimezoneTests(unittest.TestCase):
    def test_dst_fold_is_one_occurrence_and_gap_is_normalized_to_a_real_instant(self):
        before_fold = datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)
        first = next_daily(before_fold, "America/New_York", time(1, 30))
        self.assertEqual(first, datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))
        following = next_daily(first + timedelta(microseconds=1), "America/New_York", time(1, 30))
        self.assertEqual(following, datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc))
        before_gap = datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(next_daily(before_gap, "America/New_York", time(2, 30)),
                         datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
