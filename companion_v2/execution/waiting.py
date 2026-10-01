"""Fair, live waiting for original background tasks; SQLite owns every slot.

Only callers still holding their original input may wait here. The queue never
reconstructs jobs, renews deadlines or retries an attempt after it has started.
"""

import asyncio
from time import monotonic

from companion_v2.foundation.outcome import Outcome
from .models import Lane, QUEUED, require


class BackgroundTaskQueue:
    def __init__(self, supervisor, *, interval=0.05):
        self.supervisor = supervisor
        self.interval = interval
        self._pending = {}
        self._next_poll = 0.0
        self._kinds = set()

    def register(self, kinds):
        if any(self.supervisor.registrations[kind].definition.lane is not Lane.BACKGROUND for kind in kinds):
            raise ValueError("only background owners may register for waiting")
        self._kinds.update(kinds)

    def recover(self, *, limit=32):
        """Retire never-started jobs whose in-memory input died with an old host."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("recovery requires a bounded page")
        generation = require(self.supervisor.check_generation())
        if not self._kinds:
            return ()
        kinds = tuple(sorted(self._kinds))
        with self.supervisor.runtime.transaction():
            rows = self.supervisor.runtime.read_all("""SELECT task_id FROM execution_tasks
                WHERE state = 'created' AND attempt_no = 0 AND generation < ? AND kind IN ("""
                + ",".join("?" for _ in kinds) + ") ORDER BY task_id LIMIT ?", (generation, *kinds, limit))
            for row in rows:
                require(self.supervisor.discard_queued(row["task_id"], reason="owner_unavailable"))
        return tuple(row["task_id"] for row in rows)

    def _advance(self):
        if monotonic() < self._next_poll:
            return
        self._next_poll = monotonic() + self.interval
        # Insertion order gives older eligible work first refusal. A blocked
        # kind/scope does not prevent other eligible kinds from using a slot.
        for task_id, (context, future) in tuple(self._pending.items()):
            if future.done():
                continue
            result = self.supervisor.claim_task(context, task_id)
            if result.failure or result.unwrap().claim is not None:
                future.set_result(result)
                continue
            current = self.supervisor.read(context, task_id)
            if current.failure:
                future.set_result(current)
            elif current.unwrap().state not in QUEUED:
                future.set_result(result)

    async def claim(self, context, task_id):
        current = self.supervisor.read(context, task_id)
        if current.failure:
            return current
        if self.supervisor.registrations[current.unwrap().spec.kind].definition.lane is not Lane.BACKGROUND:
            return Outcome.failed("task_lane_mismatch", "only background tasks may wait in this queue")
        if task_id in self._pending:
            return Outcome.failed("task_already_waiting", "the original task already has a live waiter")
        future = asyncio.get_running_loop().create_future()
        self._pending[task_id] = (context, future)
        self._next_poll = 0.0
        handed_off = False
        try:
            while not future.done():
                self._advance()
                if not future.done():
                    await asyncio.wait((future,), timeout=self.interval)
            result = future.result()
            handed_off = result.is_success and result.unwrap().claim is not None
            return result
        finally:
            self._pending.pop(task_id, None)
            self._next_poll = 0.0
            if not handed_off:
                result = future.result() if future.done() else None
                claim = result.unwrap().claim if result is not None and result.is_success else None
                if claim is not None:
                    # Cancellation can arrive after another waiter allocated our
                    # claim, before our runner begins it. No worker exists yet.
                    self.supervisor.abandon(claim, reason="runner_cancelled")
                else:
                    self.supervisor.discard_queued(task_id, reason="owner_unavailable")
