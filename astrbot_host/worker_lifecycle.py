"""AstrBot process and event-loop evidence for local supervised worker recovery."""

import asyncio
from datetime import datetime, timezone
import os

import psutil

from companion_v2.execution.models import SideEffect, WorkerOwnership


class AstrBotWorkerLifecycle:
    def __init__(self):
        self.process_id = os.getpid()
        self.process_started_at = datetime.fromtimestamp(psutil.Process().create_time(), timezone.utc)

    def capture(self):
        return WorkerOwnership(self.process_id, self.process_started_at, str(id(asyncio.get_running_loop())))

    def stopped_proof(self, attempt):
        owner = attempt.ownership
        if owner is None:
            # Older AstrBot attempts have no PID. Only local drafts predating
            # this host process can be recovered without claiming a send stopped.
            if (attempt.side_effect in (SideEffect.NONE, SideEffect.LOCAL)
                    and attempt.started_at < self.process_started_at):
                return "legacy_host_process_exited"
            return None
        try:
            started_at = datetime.fromtimestamp(psutil.Process(owner.process_id).create_time(), timezone.utc)
        except psutil.NoSuchProcess:
            return "worker_process_exited"
        except (psutil.AccessDenied, OSError):
            return None
        if started_at != owner.process_started_at:
            return "worker_process_exited"
        if (owner.process_id != self.process_id or owner.loop_id != str(id(asyncio.get_running_loop()))):
            return None
        if any(not worker.done() and worker.get_name() == attempt.worker_name for worker in asyncio.all_tasks()):
            return None
        return "supervised_worker_absent"
