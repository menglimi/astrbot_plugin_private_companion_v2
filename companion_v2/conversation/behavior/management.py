"""Administrator review of a role's learned group habits, with stale-edit protection."""

from companion_v2.execution.models import TaskError, digest, stamp
from .store import BehaviorStore


class BehaviorManagement:
    def __init__(self, app, context):
        self.app, self.context = app, context
        self.store = BehaviorStore(app.runtime)

    def authorize(self, operator, action):
        from companion_v2.configuration.management import GroupParticipationManagement
        GroupParticipationManagement(self.app, self.context)._authorize(operator, action)

    def status(self, operator):
        self.authorize(operator, "configuration.read")
        groups = []
        with self.app.runtime.read_snapshot():
            for key, document in self.store.groups(self.context):
                habits = []
                for item in document["habits"]:
                    attempts = [row for row in document["attempts"] if row["habit_id"] == item["habit_id"]]
                    habits.append({**item, "revision": digest(item), "attempts": attempts[-4:]})
                groups.append({"group_key": key, **document["owner"], "habits": habits})
        return {"role_id": self.context.role_binding.role.subject_id, "groups": groups}

    def command(self, operator, data):
        self.authorize(operator, "configuration.write")
        if (set(data) != {"group_key", "habit_id", "enabled", "revision"}
                or type(data["enabled"]) is not bool
                or any(type(data[key]) is not str or not data[key] for key in ("group_key", "habit_id", "revision"))):
            raise TaskError("group_behavior_command_invalid", "provide a habit and explicit enabled state")
        with self.app.runtime.transaction() as connection:
            selected = next((document for key, document in self.store.groups(self.context) if key == data["group_key"]), None)
            habit = next((item for item in selected["habits"] if item["habit_id"] == data["habit_id"]), None) if selected else None
            if habit is None:
                raise TaskError("group_behavior_habit_missing", "the habit belongs to another role or group")
            if digest(habit) != data["revision"] and habit["enabled"] != data["enabled"]:
                raise TaskError("group_behavior_revision_changed", "the habit changed; read the latest record")
            habit["enabled"] = data["enabled"]
            habit["reviewed_at"] = stamp(self.app.now())
            self.store.write_owner(connection, data["group_key"], selected)
        return {"habit_id": data["habit_id"], "enabled": data["enabled"], "saved": True}
