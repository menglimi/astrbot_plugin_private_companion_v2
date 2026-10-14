"""Source-stage results for a confirmed proactive functionality test."""

from companion_v2.execution.models import TaskError


class DiagnosticSourceError(TaskError):
    """Keep completed source work and unresolved effects visible to the dashboard."""

    def __init__(self, code, reason, *, stage, stages=(), state="failed", task_id=None):
        super().__init__(code, reason)
        self.stage = stage
        self.state = state
        self.task_id = task_id
        self.stages = [*stages, {"stage": stage, "state": state}]
