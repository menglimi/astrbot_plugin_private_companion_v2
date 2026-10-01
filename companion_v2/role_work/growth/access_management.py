"""Core operator settings for one pinned participant; no model access to grants."""

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef

from .configuration import GROUP, OWNER, PERMISSIONS, target_for
from .management import RoleGrowthManagement


class RoleGrowthAccessManagement:
    def __init__(self, app):
        self.app = app
        self.management = RoleGrowthManagement(app.role_growth)

    @outcome
    def read(self, *, operator, context):
        with self.app.runtime.read_snapshot():
            now = self.app.now()
            self.management._authorize(operator, context, now)
            snapshot = require(self.app.configuration.read(operator, target=target_for(context),
                               group_id=GROUP, observed_at=now))
            effective = {}
            for name, action in PERMISSIONS.items():
                checked = self.app.tasks.check_context_access(context, action=action, observed_at=now)
                effective[name] = {"allowed": checked.is_success,
                    "reason": checked.failure.code if checked.failure else None}
            if not effective["read_enabled"]["allowed"]:
                effective["proposals_enabled"] = dict(effective["read_enabled"])
            return {"settings": {name: snapshot.values[GROUP + "." + name] for name in PERMISSIONS},
                    "effective": effective, "edit_token": snapshot.edit_token}

    @outcome
    def configure(self, *, operator, context, operation_key, edit_token, changes):
        self.management._validate_operation_key(operation_key)
        if (type(changes) is not dict or not changes or set(changes) - set(PERMISSIONS)
                or any(type(value) is not bool for value in changes.values()) or type(edit_token) is not str):
            raise TaskError("growth_configuration_invalid", "provide explicit boolean growth permissions")
        op_id = "growth-access:" + digest([operator.subject, context.key, operation_key])
        with self.app.runtime.transaction():
            self.management._authorize(operator, context, self.app.now())
            receipt = require(self.app.configuration.patch(operator, target=target_for(context), group_id=GROUP,
                operation=OperationRef(op_id, OWNER, context.scope, VersionRef(op_id, 1), op_id),
                expected_edit_token=edit_token, changes={GROUP + "." + k: v for k, v in changes.items()},
                observed_at=self.app.now()))
            access = require(self.read(operator=operator, context=context))
        self.app.notify()
        return {"operation_id": op_id, "replayed": receipt.replayed, "access": access}
