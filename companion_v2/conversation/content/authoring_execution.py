"""The original writing operation and its authorized Content subcalls."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from companion_v2.execution.models import TaskContext


@dataclass(frozen=True)
class AuthoringParent:
    context: TaskContext
    task_id: str
    deadline_at: datetime
    revalidate: Callable[[], None]


class LegacyAuthoringOperations:
    """Retain the original legacy operation owner without inventing a task."""

    def __init__(self, external, run, call, model_call_id):
        self.external, self.run = external, run
        self.call, self.model_call_id = call, model_call_id
        self.actions = external.actions

    async def execute(self, action, arguments, *, step):
        return await self.external.execute_internal(self.run, self.call, self.model_call_id,
                                                    action, arguments, step=step)
