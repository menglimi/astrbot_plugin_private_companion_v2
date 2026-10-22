"""Dashboard management routes for the pinned profile's core relationship records."""

from __future__ import annotations

import json

from astrbot.api.web import request

from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.relationships.management import RelationshipMemoryManagement

from .management_identity import dashboard_operator


MANAGEMENT_PREFIX = "/astrbot_plugin_private_companion/relationships"


class RelationshipWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [
            (MANAGEMENT_PREFIX, self.list, ["GET"], "Read Companion V2 relationship memories"),
            (MANAGEMENT_PREFIX + "/command", self.command, ["POST"], "Review Companion V2 relationship memories"),
        ]

    async def _run(self, arguments, *, mutation=False):
        from .web_api import outcome_response
        controller = self.controller
        async with controller._control_lock:
            try:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "the plugin has stopped")
                # Authentication is checked even when no profile is loaded.
                username = request.username
                if type(username) is not str or not username.strip():
                    raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load an initialized V2 profile before managing its memories")
                operator = dashboard_operator(controller.runtime, username, at=controller.now())
                manager = RelationshipMemoryManagement(session.application.relationship_memories)
                method = manager.command if mutation else manager.list
                result = method(operator=operator, context=session.profile.target, **arguments)
                response = outcome_response(result)
                if result.is_success and not mutation:
                    response["data"]["operator_name"] = username
                    response["data"]["profile_id"] = (getattr(controller, "target_id", None)
                                                       or controller.settings.profile_id)
                return response
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))

    async def list(self):
        from .web_api import outcome_response
        query = request.query
        if set(query.keys()) - {"state", "after_id", "limit"} or any(len(query.getlist(k)) != 1 for k in query.keys()):
            return outcome_response(Outcome.failed("relationship_query_invalid", "unknown or repeated query fields"))
        try:
            limit = int(query.get("limit", "20"))
        except (TypeError, ValueError):
            return outcome_response(Outcome.failed("relationship_query_invalid", "invalid page size"))
        return await self._run({"state": query.get("state") or None, "after_id": query.get("after_id") or None,
                                "limit": limit})

    async def command(self):
        from .web_api import outcome_response
        required = {"memory_id", "action", "expected_revision", "view_token", "operation_key"}
        try:
            raw = await request.body()
            if len(raw) > 100000:
                raise ValueError()
            def unique(pairs):
                values = {}
                for key, value in pairs:
                    if key in values:
                        raise ValueError()
                    values[key] = value
                return values
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
            if type(data) is not dict or not required.issubset(data) or set(data) - required - {"interpretation"}:
                raise ValueError()
        except (ValueError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("relationship_command_invalid", "invalid relationship command"))
        return await self._run(data, mutation=True)
