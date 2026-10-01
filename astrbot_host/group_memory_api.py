"""Fixed group/role Dashboard governance; never a private-member memory view."""

import json

from astrbot.api.web import request
from companion_v2.adapters.astrbot.native import account_number
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.memory.group.management import GroupMemoryManagement, GroupMemoryTarget
from .group_settings import GroupTarget
from .management_identity import dashboard_operator
from .web_api import outcome_response


class GroupMemoryWebAPI:
    def __init__(self, controller, target_id, role_id):
        self.controller, self.target_id, self.role_id = controller, target_id, role_id

    def routes(self, prefix):
        return [(prefix, self.list, ["GET"], "List this collective group memory archive"),
                (prefix + "/detail", self.detail, ["POST"], "Read one group statement and its governed original"),
                (prefix + "/retract", self.retract, ["POST"], "Retract one exact group statement as administrator"),
                (prefix + "/operation", self.operation, ["GET"], "Read this administrator's group memory receipt"),
                (prefix + "/safety", self.safety, ["GET"], "List deterministic group member safety evidence"),
                (prefix + "/safety/review", self.review_safety, ["POST"], "Review one group member safety hit")]

    def _manager(self, session_id):
        controller = self.controller
        if controller._terminated:
            raise TaskError("staging_host_terminated", "plugin is stopped")
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        session = controller.session or controller.last_session
        if session is None or controller.runtime is None:
            raise TaskError("staging_not_initialized", "load the V2 profile before managing group memory")
        selected = controller.settings.target(self.target_id)
        if not isinstance(selected, GroupTarget) or not any(
                p.bot_id == selected.bot_id and p.role_id == self.role_id for p in controller.settings.personas):
            raise TaskError("group_memory_target_required", "the configured group/role is unavailable")
        native_session = selected.group_id if session_id is None else session_id
        parts = native_session.split("_") if type(native_session) is str else ()
        if (len(parts) not in (1, 2) or parts[-1] != selected.group_id
                or any(account_number(part) != part for part in parts)):
            raise TaskError("group_memory_session_invalid", "choose this group's shared or per-member native session")
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        target = GroupMemoryTarget(controller.runtime.installation_id, selected.platform_id, selected.bot_id,
            selected.account_id, selected.group_id, native_session, self.role_id)
        return GroupMemoryManagement(session.application.messages.group_memory, operator), target, session.application

    async def _run(self, method, arguments):
        async with self.controller._control_lock:
            try:
                manager, target, application = self._manager(arguments.pop("session_id", None))
                result = getattr(manager, method)(target, **arguments)
                if method == "retract" and result.is_success:
                    application.notify()
                return outcome_response(result)
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))
            except (ValueError, TypeError, KeyError):
                return self._invalid()

    @staticmethod
    def _invalid():
        return outcome_response(Outcome.failed("group_memory_request_invalid", "invalid group memory management arguments"))

    @staticmethod
    def _query(allowed, required=()):
        query = request.query
        if (set(query.keys()) - set(allowed) or set(required) - set(query.keys())
                or any(len(query.getlist(key)) != 1 for key in query.keys())):
            raise ValueError("unexpected or duplicate query fields")
        return dict(query)

    @staticmethod
    async def _body(allowed, required):
        raw = await request.body()
        if len(raw) > 8192 or request.query:
            raise ValueError("bounded JSON body required")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate body field")
                result[key] = value
            return result

        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if type(data) is not dict or set(data) - set(allowed) or set(required) - set(data):
            raise ValueError("unexpected or missing body fields")
        return data

    async def list(self):
        try:
            data = self._query(("session_id", "after_id", "limit", "state"))
            data["limit"] = int(data.get("limit", "20"))
            return await self._run("list", data)
        except (ValueError, TypeError):
            return self._invalid()

    async def detail(self):
        try:
            data = await self._body(("session_id", "memory_id", "revision", "start", "chars"), ("memory_id", "revision"))
            return await self._run("detail", data)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return self._invalid()

    async def retract(self):
        try:
            required = ("memory_id", "expected_revision", "view_token", "operation_key")
            data = await self._body((*required, "session_id", "reason"), required)
            return await self._run("retract", data)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return self._invalid()

    async def operation(self):
        try:
            return await self._run("operation", self._query(("operation_id", "session_id"), ("operation_id",)))
        except (ValueError, TypeError):
            return self._invalid()

    async def safety(self):
        try:
            data = self._query(("session_id", "after_id", "limit", "member_id", "review_state"))
            data["limit"] = int(data.get("limit", "20"))
            return await self._run("safety_hits", data)
        except (ValueError, TypeError):
            return self._invalid()

    async def review_safety(self):
        try:
            required = ("hit_id", "review_state", "operation_key")
            data = await self._body((*required, "session_id", "note"), required)
            return await self._run("review_safety_hit", data)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return self._invalid()
