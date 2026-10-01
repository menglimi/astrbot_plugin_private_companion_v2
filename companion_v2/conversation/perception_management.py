"""Authorized editor for private conversation perception prompts."""

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.role_work.life.management import RoleLifeManagement

from .perception_settings import DEFAULTS, GROUP, OWNER, target_for, validate


class PerceptionManagement:
    def __init__(self, app, context):
        self.app, self.context = app, context
        self.access = RoleLifeManagement(app, context)

    def _status(self, operator):
        self.access.authorize(operator)
        snapshot = self.app.perception_settings.snapshot(operator, self.context, self.app.now())
        return {"settings": validate({key.removeprefix(GROUP + "."): value
                                      for key, value in snapshot.values.items()}),
                "edit_token": snapshot.edit_token, "apply_mode": "next_sealed_reply"}

    @outcome
    def status(self, operator):
        with self.app.runtime.read_snapshot():
            return self._status(operator)

    @outcome
    def configure(self, operator, data):
        if (type(data) is not dict or set(data) != {"operation_key", "edit_token", "changes"}
                or type(data["operation_key"]) is not str or not data["operation_key"].strip()
                or len(data["operation_key"]) > 128 or type(data["edit_token"]) is not str
                or type(data["changes"]) is not dict or not data["changes"]
                or set(data["changes"]) - set(DEFAULTS)
                or any(type(value) is not type(DEFAULTS[name]) for name, value in data["changes"].items())):
            raise TaskError("perception_configuration_invalid", "provide explicit perception changes")
        with self.app.runtime.transaction():
            self.access.authorize(operator)
            op_id = "perception-config:" + digest([operator.subject, self.context.key, data["operation_key"]])
            receipt = require(self.app.configuration.patch(operator, target=target_for(self.context), group_id=GROUP,
                operation=OperationRef(op_id, OWNER, self.context.scope, VersionRef(op_id, 1), op_id),
                expected_edit_token=data["edit_token"],
                changes={GROUP + "." + name: value for name, value in data["changes"].items()},
                observed_at=self.app.now()))
            return {"operation_id": op_id, "replayed": receipt.replayed,
                    "status": self._status(operator)}
