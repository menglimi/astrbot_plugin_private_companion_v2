"""Explicit core operations for state, schedules and presentation of one private role."""

from datetime import timedelta
import json

from companion_v2.execution.models import TaskError, digest, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, VersionRef
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from companion_v2.delivery.presence_diagnostics import describe_presentation
from companion_v2.role_work.life.management import RoleLifeManagement
from .configuration import DEFAULTS, GROUP, OWNER, PERMISSIONS, target_for


class StateManagement:
    def __init__(self, app, context):
        self.app, self.context = app, context
        self.life = RoleLifeManagement(app, context)

    def token(self, operator, access, identifier, revision):
        basis = ["state-management.v1", operator.subject, operator.binding_id, operator.binding_revision,
                 self.context.key, access.policy_revision, identifier, revision]
        if identifier == "current":
            records = self.app.role_state.records
            try:
                original = records.version(self.context, "current", revision) if revision else None
            except TaskError:
                original = None
            basis.append(digest(original))
        return digest(basis)

    @staticmethod
    def key(value):
        if type(value) is not str or not value.strip() or len(value) > 128:
            raise TaskError("state_command_invalid", "provide a stable operation key")

    @outcome
    def status(self, operator, *, after_id="", limit=30):
        with self.app.runtime.read_snapshot():
            access = self.life.authorize(operator)
            snapshot = require(self.app.configuration.read(operator, target=target_for(self.context),
                               group_id=GROUP, observed_at=self.app.now()))
            effective = {}
            for option, actions in PERMISSIONS.items():
                try:
                    for action in actions:
                        self.app.role_state.access.check(self.context, action)
                    effective[option] = {"allowed": bool(snapshot.values[GROUP + "." + option]), "reason": None}
                except TaskError as error:
                    effective[option] = {"allowed": False, "reason": error.code}
            try:
                state = self.app.role_state.read(self.context, operator=operator)
            except TaskError as error:
                original = self.app.role_state.records.get(self.context, "current")
                state = {"state": "unavailable", "revision": original["revision"] if original else 0, "code": error.code}
            state["view_token"] = self.token(operator, access, "current", state["revision"])
            calendar = self.app.calendar.inventory(self.context, after_id=after_id, limit=limit, operator=operator)
            for item in calendar["items"]:
                item["view_token"] = self.token(operator, access, item["id"], item["revision"])
            schedule = self.app.runtime.read_one("SELECT next_at, enabled, result_json FROM role_state_schedules WHERE context_key = ?",
                                                 (self.context.key,))
            sleep = self.life.sleep_status(operator, access=access)
            settings = {name: snapshot.values[GROUP + "." + name] for name in DEFAULTS}
            settings["mood_cross_window"] = True
            return {"settings": settings,
                "body_scope": {"installation_id": self.context.scope.installation_id,
                    "bot_id": self.context.scope.bot_id, "role_id": self.context.role_binding.role.subject_id,
                    "settings": [name for name in DEFAULTS if name in ("hunger_enabled", "health_enabled") or name.startswith("cycle_")]},
                "edit_token": snapshot.edit_token, "cycle_settings_token": self.app.role_state.cycle_settings_token(settings),
                "effective": effective, "state": state, "calendar": calendar,
                "planning": self.app.calendar_planning.status(self.context),
                "create_token": self.token(operator, access, "calendar:new", 0),
                "occurrences": self.app.calendar.occurrences(self.context, start=self.app.now(),
                    end=self.app.now() + timedelta(days=7), operator=operator),
                **sleep,
                "maintenance": {"next_at": schedule["next_at"], "enabled": bool(schedule["enabled"]),
                    "result": json.loads(schedule["result_json"]) if schedule["result_json"] else None} if schedule else None,
                "presentation": self.app.presence.results_for(self.context) if self.app.presence else {"state": "preview"},
                "presentation_diagnostics": describe_presentation(self.app, self.context, settings=settings, effective=effective),
                "host_state": self.app.state}

    def _configure(self, operator, data):
        changes = data["changes"]
        if (type(changes) is not dict or not changes or set(changes) - set(DEFAULTS)
                or any(type(value) is not type(DEFAULTS[name]) for name, value in changes.items())
                or type(data["edit_token"]) is not str):
            raise TaskError("state_configuration_invalid", "use explicit state settings with the declared types")
        op_id = "state-config:" + digest([operator.subject, self.context.key, data["operation_key"]])
        receipt = require(self.app.configuration.patch(operator, target=target_for(self.context), group_id=GROUP,
            operation=OperationRef(op_id, OWNER, self.context.scope, VersionRef(op_id, 1), op_id),
            expected_edit_token=data["edit_token"], changes={GROUP + "." + k: v for k, v in changes.items()},
            observed_at=self.app.now()))
        from .ownership import role_owner
        for bound in tuple(self.app.state_maintenance.bindings.values()):
            if role_owner(bound[0]) == role_owner(self.context):
                try:
                    self.app.state_maintenance.bind(*bound[:2], guard=bound[2])
                except TaskError:
                    continue  # A retired window cannot invalidate the current configuration.
        if self.app.presence is not None:
            self.app.presence.bind(self.context)
        self.app.calendar_planning.next_checks.pop(self.context.key, None)
        return {"operation_id": op_id, "replayed": receipt.replayed}

    def _maintain(self, operator, data):
        self.app.require_running()
        service = self.app.state_maintenance
        settings, _ = self.app.role_state.settings(self.context)
        if not settings["enabled"] or self.context.key not in service.bindings:
            raise TaskError("state_not_enabled", "enable state and bind the current host persona first")
        self.app.role_state.access.check(self.context, "role.state.maintain")
        op_id = "state-request:" + digest([operator.subject, self.context.key, data["operation_key"]])
        operations = OperationRepository(self.app.runtime)
        reserved = require(operations.reserve(OperationRef(op_id, GROUP, self.context.scope, VersionRef(op_id, 1), op_id),
            parameter_hash=digest(data), observed_at=self.app.now()))
        if not reserved.replayed:
            current = self.app.role_state.records.get(self.context, "current")
            if (current["revision"] if current else 0) != data["expected_revision"]:
                raise TaskError("record_revision_conflict", "read the current state first")
            with self.app.runtime.transaction() as connection:
                connection.execute("UPDATE role_state_schedules SET next_at = ?, revision = revision + 1 WHERE context_key = ?",
                                   (stamp(self.app.now()), self.context.key))
            require(operations.transition(op_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=self.app.now()))
        return {"operation_id": op_id, "replayed": reserved.replayed, "state": "scheduled"}

    def _calendar_request(self, operator, data):
        # Registering a reminder changes the object policy revision and therefore
        # the view token. Persist the exact authorized management request in the
        # same transaction, so receipt recovery can survive its own policy change.
        # command() rechecks current operator/target access before this lookup.
        op_id = "state-calendar-request:" + digest([operator.subject, self.context.key, data["operation_key"]])
        receipt = require(OperationRepository(self.app.runtime).reserve(
            OperationRef(op_id, GROUP, self.context.scope, VersionRef(op_id, 1), op_id),
            parameter_hash=digest([data, operator.binding_id, operator.binding_revision]),
            observed_at=self.app.now()))
        if receipt.replayed and receipt.state is not OperationState.COMPLETED:
            raise TaskError("state_receipt_incomplete", "original calendar request has no completed receipt")
        return receipt

    @outcome
    def command(self, operator, data):
        self.key(data["operation_key"])
        with self.app.runtime.transaction():
            access = self.life.authorize(operator)
            action = data["action"]
            if action == "configure":
                result = self._configure(operator, data)
            else:
                revision = data["expected_revision"]
                if type(revision) is not int or revision < 0:
                    raise TaskError("state_command_invalid", "provide the original record revision")
                identifier = "current" if action in ("state.write", "cycle.align", "maintain") else data["id"]
                token_id = "calendar:new" if action == "calendar.create" else identifier
                calendar_request = self._calendar_request(operator, data) if action.startswith("calendar.") else None
                if not (calendar_request and calendar_request.replayed) and data["view_token"] != self.token(operator, access, token_id, revision):
                    raise TaskError("state_view_stale", "refresh the view before applying this change")
                key = digest([operator.subject, data["operation_key"]])
                if action == "state.write":
                    result = self.app.role_state.write(self.context, data=data["data"], expected_revision=revision,
                        operation_key=key, sources=data.get("sources", ()), operator=operator, reason="human_edit")
                elif action == "cycle.align":
                    if "settings_token" in data and type(data["settings_token"]) is not str:
                        raise TaskError("state_command_invalid", "provide the original settings token")
                    result = self.app.role_state.align_cycle(self.context, data=data["data"], expected_revision=revision,
                        operation_key=key, operator=operator, expected_settings_token=data.get("settings_token"))
                elif action == "maintain":
                    result = self._maintain(operator, data)
                elif action == "calendar.remind":
                    result = self.app.calendar.remind(self.context, identifier=identifier, expected_revision=revision,
                        operation_key=key, sequence=data["sequence"], operator=operator)
                elif action.startswith("calendar."):
                    result = self.app.calendar.command(self.context, identifier=identifier, action=action.split(".")[1],
                        expected_revision=revision, operation_key=key, data=data.get("data"),
                        sources=data.get("sources", ()), operator=operator)
                else:
                    raise TaskError("state_command_invalid", "unknown state command")
                if calendar_request and not calendar_request.replayed:
                    require(OperationRepository(self.app.runtime).transition(calendar_request.operation.operation_id,
                        expected_state=OperationState.ACCEPTED, next_state=OperationState.COMPLETED,
                        observed_at=self.app.now()))
        self.app.notify()
        return result
