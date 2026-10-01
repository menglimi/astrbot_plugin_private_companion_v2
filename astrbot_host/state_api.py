"""Authenticated state and calendar API for the host's original pinned target."""

import json

from astrbot.api.web import request
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.role_work.state.management import StateManagement
from .growth_api import _source
from .management_identity import dashboard_operator

PREFIX = "/astrbot_plugin_private_companion_v2/state"


class StateWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.status, ["GET"], "Read role state and calendar"),
                (PREFIX + "/command", self.command, ["POST"], "Manage role state and calendar")]

    async def _run(self, data=None, **query):
        from .web_api import outcome_response
        controller = self.controller
        async with controller._control_lock:
            try:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "the plugin has stopped")
                username = request.username
                if type(username) is not str or not username.strip():
                    raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load an initialized V2 profile first")
                operator = dashboard_operator(controller.runtime, username, at=controller.now())
                manager = StateManagement(session.application, session.profile.target)
                return outcome_response(manager.command(operator, data) if data is not None else manager.status(operator, **query))
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))
            except (ValueError, TypeError, KeyError, OverflowError):
                return outcome_response(Outcome.failed("state_command_invalid", "invalid state or calendar fields"))

    async def status(self):
        from .web_api import outcome_response
        query = request.query
        try:
            if set(query.keys()) - {"after_id", "limit"} or any(len(query.getlist(k)) != 1 for k in query.keys()):
                raise ValueError("unknown or repeated query fields")
            limit = int(query.get("limit", "30"))
            if not 1 <= limit <= 100:
                raise ValueError("invalid page size")
        except (TypeError, ValueError):
            return outcome_response(Outcome.failed("state_query_invalid", "invalid state query"))
        return await self._run(after_id=query.get("after_id", ""), limit=limit)

    async def command(self):
        from .web_api import outcome_response
        try:
            if request.query:
                raise ValueError("command route does not accept query fields")
            raw = await request.body()
            if len(raw) > 100000:
                raise ValueError("command too large")
            def unique(pairs):
                values = {}
                for key, value in pairs:
                    if key in values:
                        raise ValueError("duplicate field")
                    values[key] = value
                return values
            def finite(value):
                raise ValueError("nonfinite value")
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=finite)
            if type(data) is not dict or type(data.get("action")) is not str:
                raise ValueError("provide an explicit action")
            common = {"action", "operation_key", "view_token", "expected_revision"}
            action = data["action"]
            if action == "configure":
                required = allowed = {"action", "operation_key", "edit_token", "changes"}
            elif action == "state.write":
                required, allowed = common | {"data"}, common | {"data", "sources"}
            elif action == "cycle.align":
                required, allowed = common | {"data"}, common | {"data", "settings_token"}
            elif action == "maintain":
                required = allowed = common
            elif action in ("calendar.create", "calendar.revise"):
                required, allowed = common | {"id", "data"}, common | {"id", "data", "sources"}
            elif action == "calendar.presence":
                required = allowed = common | {"id", "data"}
            elif action in ("calendar.accept", "calendar.cancel"):
                required = allowed = common | {"id"}
            elif action == "calendar.exception":
                required = allowed = common | {"id", "data"}
            elif action == "calendar.remind":
                required = allowed = common | {"id", "sequence"}
            else:
                raise ValueError("unknown action")
            if not required.issubset(data) or set(data) - allowed:
                raise ValueError("unexpected or missing fields")
            if "sources" in data:
                if type(data["sources"]) is not list or len(data["sources"]) > 8:
                    raise ValueError("provide at most eight sources")
                data["sources"] = tuple(_source(value) for value in data["sources"])
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("state_command_invalid", "invalid UTF-8 state command"))
        return await self._run(data)
