"""Private-member editors sharing the established configuration owners."""

from companion_v2.configuration.management import (
    AcquaintanceManagement, ProactiveContactManagement, RelationshipProfileManagement,
)
from companion_v2.execution.models import TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository


EDITORS = {"profile": RelationshipProfileManagement, "person": AcquaintanceManagement,
           "contact": ProactiveContactManagement}


class PrivateMemberSettings:
    def __init__(self, app, context):
        self.app, self.context = app, context

    @outcome
    def status(self, operator):
        with self.app.runtime.read_snapshot():
            return {"sections": {name: require(editor(self.app, self.context).status(operator))
                                 for name, editor in EDITORS.items()}}

    @outcome
    def configure(self, operator, command):
        if (type(command) is not dict or set(command) != {"operation_key", "sections"}
                or type(command["operation_key"]) is not str or not command["operation_key"].strip()
                or len(command["operation_key"]) > 100
                or type(command["sections"]) is not dict or not command["sections"]
                or set(command["sections"]) - set(EDITORS)):
            raise TaskError("private_member_command_invalid", "provide member settings and stable operation key")
        editors = {name: EDITORS[name](self.app, self.context) for name in command["sections"]}
        op_id = "private-member-settings:" + digest([operator.subject, self.context.key, command["operation_key"]])
        operation = OperationRef(op_id, "relationships.private-settings", self.context.scope,
                                 VersionRef(op_id, 1), op_id)
        operations = OperationRepository(self.app.runtime)
        # Validate every original token before shared owner revisions advance.
        with self.app.runtime.transaction():
            snapshots = {name: require(editor.status(operator)) for name, editor in editors.items()}
            require(self.app.tasks.check_generation())
            receipt = require(operations.reserve(operation, parameter_hash=digest([
                operator.principal, operator.subject, operator.binding_id, operator.binding_revision,
                self.context.role_binding, command["sections"]]), observed_at=self.app.now()))
            for name, data in command["sections"].items():
                if (type(data) is not dict or set(data) != {"edit_token", "changes"}
                        or type(data["edit_token"]) is not str or len(data["edit_token"]) != 64
                        or type(data["changes"]) is not dict or not data["changes"]):
                    raise TaskError("private_member_command_invalid", "provide each section's edit token and explicit changes")
                if not receipt.replayed and data["edit_token"] != snapshots[name]["edit_token"]:
                    raise TaskError("configuration_revision_conflict", "configuration, inheritance, binding, or policy changed")
            if receipt.replayed and receipt.state is not OperationState.COMPLETED:
                raise TaskError("configuration_operation_incomplete", "original member settings result is unavailable")
            results = {}
            for name, data in command["sections"].items():
                editor = editors[name]
                section_key = op_id + ":" + name
                if receipt.replayed:
                    results[name] = {"replayed": True, "operation_id": f"{editor.group}-config:" +
                        digest([operator.subject, editor._target().key, section_key]),
                        "status": require(editor.status(operator))}
                else:
                    latest = require(editor.status(operator))
                    results[name] = require(editor.configure(operator,
                        {**data, "edit_token": latest["edit_token"], "operation_key": section_key}))
            if not receipt.replayed:
                require(operations.transition(op_id, expected_state=OperationState.ACCEPTED,
                    next_state=OperationState.COMPLETED, observed_at=self.app.now()))
            status = require(self.status(operator))
        self.app.notify()
        return {"results": results, **status}
