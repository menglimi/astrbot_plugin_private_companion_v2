"""Role-owned physical sleep receipts; private activity prose stays in its window."""

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.role_work.codec import activity_from_json
from companion_v2.role_work.models import RoleActivityState as State
from companion_v2.role_work.state.ownership import role_owner


class RoleBodyClock:
    def __init__(self, tasks, life):
        self.tasks, self.life, self.runtime = tasks, life, tasks.runtime

    def active(self, context, kind):
        return tuple(activity_from_json(row["record_json"]) for row in self.runtime.read_all("""SELECT record_json
            FROM role_activities WHERE owner_key = ? AND state = 'active'
              AND json_extract(record_json, '$.scope.kind') = 'private'
              AND json_extract(record_json, '$.work.kind') = ?
            ORDER BY updated_at, activity_id""", (digest(role_owner(context)), kind)))

    def latest(self, context):
        row = self.runtime.read_one("""SELECT record_json FROM role_activities WHERE owner_key = ?
            AND json_extract(record_json, '$.scope.kind') = 'private'
            AND json_extract(record_json, '$.work.kind') = 'sleep'
            ORDER BY (state = 'active') DESC, updated_at DESC, activity_id DESC LIMIT 1""",
            (digest(role_owner(context)),))
        return activity_from_json(row["record_json"]) if row else None

    def reference(self, context):
        activity = self.latest(context)
        return {"id": activity.activity_id, "revision": activity.revision} if activity else None

    def read(self, context, *, reference=None, historical=False):
        if historical:
            if reference is None:
                return None
            if type(reference) is not dict or set(reference) != {"id", "revision"}:
                raise TaskError("body_sleep_reference", "invalid physical sleep reference")
            try:
                activity = self.life.activity_revision(reference["id"], reference["revision"], owner=role_owner(context))
            except (KeyError, ValueError, TypeError) as error:
                raise TaskError("body_sleep_reference", "original physical sleep is unavailable") from error
            if not activity.work or activity.work.kind != "sleep" or activity.scope.kind.value != "private":
                raise TaskError("body_sleep_reference", "reference is not a private role sleep")
        else:
            activity = self.latest(context)
        if activity is None:
            return None
        return {"basis": "execution_receipt", "state": "sleeping" if activity.state is State.ACTIVE else
            "awake" if activity.state is State.COMPLETED else "interrupted",
            "started_at": stamp(activity.started_at), "planned_wake_at": stamp(activity.work.due_at),
            "ended_at": stamp(activity.updated_at) if activity.state in (State.COMPLETED, State.CANCELLED) else None}

    def finish_due(self, context):
        # The caller has checked the current role.life.run authority. Only a due
        # physical timer may be completed here; dream writing remains window-owned.
        with self.runtime.transaction():
            for activity in self.active(context, "sleep"):
                if activity.work.due_at <= self.tasks.now():
                    self.life.transition_activity(activity.activity_id, owner=role_owner(context),
                        expected_revision=activity.revision, state=State.COMPLETED,
                        operation_id="body-wake-" + digest([activity.activity_id, activity.revision]),
                        observed_at=self.tasks.now(), checkpoint="睡眠计时结束；未执行其他醒后动作")
