"""Explicit daily registrations driven by the application's existing wake loop.

Registration is a live host binding, not a persisted persona or authority cache.
The host must re-register after restart; elapsed dates are never backfilled.
"""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone as utc_timezone
from zoneinfo import ZoneInfo

from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.execution.service import outcome
from companion_v2.foundation.outcome import Outcome


def next_daily(now, timezone, local_time):
    zone = ZoneInfo(timezone)
    day = now.astimezone(zone).date()
    candidate = datetime.combine(day, local_time, zone).astimezone(utc_timezone.utc)
    if candidate < now:
        candidate = datetime.combine(day + timedelta(days=1), local_time, zone).astimezone(utc_timezone.utc)
    return candidate


@dataclass(frozen=True)
class DailyJournalSchedule:
    schedule_id: str
    context: TaskContext
    event: InboundConversationEvent
    role_instruction: str
    timezone: str
    local_time: time
    next_at: datetime


class JournalScheduleDriver:
    def __init__(self, triggers, *, notify):
        self.triggers, self.notify = triggers, notify
        self._schedules, self._workers, self.results = {}, {}, {}
        self.invoke = None

    @outcome
    def register_daily(self, schedule_id, context, event, *, role_instruction, timezone, local_time="23:50"):
        if not isinstance(schedule_id, str) or not schedule_id.strip() or len(schedule_id) > 256:
            raise ValueError("daily registration needs a bounded stable identity")
        at = time.fromisoformat(local_time)
        if at.tzinfo is not None:
            raise ValueError("daily local time uses the explicit IANA timezone")
        self.triggers.authorize(context, event, role_instruction=role_instruction)
        scheduled = DailyJournalSchedule(schedule_id, context, event, role_instruction, timezone, at,
                                         next_daily(self.triggers.tasks.now(), timezone, at))
        prior = self._schedules.get(schedule_id)
        if prior is not None:
            if replace(prior, next_at=scheduled.next_at) != scheduled:
                raise TaskError("journal_schedule_conflict", "remove the prior registration before changing its authority or time")
            return prior
        self._schedules[schedule_id] = scheduled
        self.notify()
        return scheduled

    def remove(self, schedule_id):
        """Trusted host disarms future dates and cancels an in-flight invocation."""
        self.triggers.require_running()
        removed = self._schedules.pop(schedule_id, None)
        worker = self._workers.get(schedule_id)
        if worker is not None:
            worker.cancel()
        self.results.pop(schedule_id, None)
        self.notify()
        return removed is not None

    def advance(self):
        for key, worker in tuple(self._workers.items()):
            if worker.done():
                del self._workers[key]
                if not worker.cancelled():
                    self.results[key] = worker.result()
        capacity = self.triggers.tasks.limits.background_slots - len(self._workers)
        now = self.triggers.tasks.now()
        for key, schedule in sorted(tuple(self._schedules.items()), key=lambda pair: pair[1].next_at):
            if capacity <= 0:
                break
            if schedule.next_at > now or key in self._workers:
                continue
            local_now = now.astimezone(ZoneInfo(schedule.timezone))
            # A delayed tick may run today's due occurrence; never a backlog of missed dates.
            due_day = schedule.next_at.astimezone(ZoneInfo(schedule.timezone)).date()
            self._schedules[key] = replace(schedule, next_at=next_daily(
                now + timedelta(microseconds=1), schedule.timezone, schedule.local_time))
            if due_day != local_now.date():
                # If today's configured time already passed, prepare only today's occurrence.
                today = datetime.combine(local_now.date(), schedule.local_time, ZoneInfo(schedule.timezone))
                if today.astimezone(utc_timezone.utc) > now:
                    continue
            worker = asyncio.create_task(self._run(schedule, local_now.date().isoformat()),
                                         name="companion:journal-daily:" + key)
            self._workers[key] = worker
            worker.add_done_callback(lambda done: self.notify())
            capacity -= 1

    async def _run(self, schedule, day):
        try:
            if self.invoke is not None:
                return await self.invoke(schedule, day)
            return await self.triggers.daily(schedule.context, schedule.event, local_date=day,
                timezone=schedule.timezone, role_instruction=schedule.role_instruction)
        except Exception:
            return Outcome.failed("journal_schedule_failed", "daily invocation stopped; no implicit replay is scheduled")

    def next_wake(self):
        if len(self._workers) >= self.triggers.tasks.limits.background_slots:
            return None
        deadlines = [item.next_at for key, item in self._schedules.items() if key not in self._workers]
        return min(deadlines) if deadlines else None

    @property
    def active_handles(self):
        return tuple("journal-daily-" + key for key in self._workers)

    def cancel_running(self):
        for worker in tuple(self._workers.values()):
            worker.cancel()

    async def close(self):
        self._schedules.clear()
        self.cancel_running()
        if self._workers:
            await asyncio.wait(tuple(self._workers.values()), timeout=0.25)
        for key, worker in tuple(self._workers.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.exception()
                del self._workers[key]
