"""Authorized editor for private conversation perception prompts."""

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.configuration.contract import layers_of, provenance_of
from companion_v2.configuration.models import ConfigLayer
from companion_v2.role_work.life.management import RoleLifeManagement

from .perception_settings import DEFAULTS, GROUP, OWNER, role_target_for, target_for, validate


class PerceptionManagement:
    def __init__(self, app, context, *, layer=ConfigLayer.ROLE):
        if layer not in (ConfigLayer.ROLE, ConfigLayer.WINDOW):
            raise ValueError("perception settings support role defaults or one private window")
        self.app, self.context = app, context
        self.layer = layer
        self.target = role_target_for(context) if layer is ConfigLayer.ROLE else target_for(context)
        self.access = RoleLifeManagement(app, context)

    def _status(self, operator):
        self.access.authorize(operator)
        snapshot = self.app.perception_settings.snapshot(operator, self.context, self.app.now(), target=self.target)
        return {"settings": validate({key.removeprefix(GROUP + "."): value
                                      for key, value in snapshot.values.items()}),
                "edit_token": snapshot.edit_token, "scope": self.layer.value,
                "layers": layers_of(self.target), "provenance": provenance_of(snapshot, GROUP),
                "apply_mode": "next_sealed_reply"}

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
            op_id = "perception-config:" + digest([operator.subject, self.target.key, data["operation_key"]])
            receipt = require(self.app.configuration.patch(operator, target=self.target, group_id=GROUP,
                operation=OperationRef(op_id, OWNER, self.target.authorization_scope, VersionRef(op_id, 1), op_id),
                expected_edit_token=data["edit_token"],
                changes={GROUP + "." + name: value for name, value in data["changes"].items()},
                observed_at=self.app.now()))
            return {"operation_id": op_id, "replayed": receipt.replayed,
                    "status": self._status(operator)}
