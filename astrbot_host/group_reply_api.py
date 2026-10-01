"""Dashboard-only reply preferences for one configured group, role and native session."""

import json

from astrbot.api.web import request
from companion_v2.adapters.astrbot.native import account_number
from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef

from .group_settings import GroupTarget
from .management_identity import dashboard_operator
from .web_api import outcome_response


class GroupReplyWebAPI:
    def __init__(self, controller, target_id, role_id):
        self.controller, self.target_id, self.role_id = controller, target_id, role_id

    def routes(self, prefix):
        return [(prefix, self.status, ["GET"], "Read this group's reply preferences"),
                (prefix + "/preview", self.preview, ["POST"], "Preview this group's reply without model access"),
                (prefix + "/configure", self.configure, ["POST"], "Save this group's reply preferences")]

    @staticmethod
    def _session(group_id):
        query = request.query
        if set(query.keys()) - {"session_id"} or any(len(query.getlist(key)) != 1 for key in query.keys()):
            raise ValueError("unexpected group reply query")
        session_id = query.get("session_id", group_id)
        parts = session_id.split("_") if type(session_id) is str else ()
        if (len(parts) not in (1, 2) or parts[-1] != group_id
                or any(account_number(part) != part for part in parts)):
            raise TaskError("group_reply_session_invalid", "select this group's shared or per-member native session")
        return session_id

    @staticmethod
    async def _body(action):
        raw = await request.body()
        if len(raw) > (300000 if action == "preview" else 8192):
            raise ValueError("group reply request is too large")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        def finite(value):
            raise ValueError("nonfinite value")

        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=finite)
        expected = {"settings", "text"} if action == "preview" else {"operation_key", "edit_token", "changes"}
        optional = {"image_count"} if action == "preview" else set()
        if type(data) is not dict or not expected <= set(data) or set(data) - expected - optional:
            raise ValueError("unexpected or missing group reply fields")
        return data

    async def _run(self, action, data=None):
        async with self.controller._control_lock:
            try:
                controller = self.controller
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                username = request.username
                if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                    raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load the V2 profile first")
                selected = controller.settings.target(self.target_id)
                if not isinstance(selected, GroupTarget) or not any(
                        p.bot_id == selected.bot_id and p.role_id == self.role_id for p in controller.settings.personas):
                    raise TaskError("group_reply_target_required", "the configured group/role is unavailable")
                session_id = self._session(selected.group_id)
                operator = dashboard_operator(controller.runtime, username, at=controller.now())
                bridge = session.bridge.groups
                account = bridge.accounts[(selected.platform_id, selected.account_id)]
                conversation_id, role, _ = await bridge._role(account, session_id)
                if role.subject_id != self.role_id or role.installation_id != controller.runtime.installation_id:
                    raise TaskError("group_reply_role_changed", "the native group session selected another role")
                scope = ScopeRef(controller.runtime.installation_id, selected.platform_id, ScopeKind.GROUP,
                                 selected.group_id, selected.bot_id, selected.account_id, conversation_id, session_id)
                if bridge.target_for_scope(scope) != selected:
                    raise TaskError("group_reply_target_required", "the native group target changed")
                target = ConfigTarget(scope.installation_id, ConfigLayer.WINDOW, role, scope)
                manager = ReplyManagement(session.application, target=target)
                if action == "status":
                    result = manager.status(operator)
                elif action == "preview":
                    result = manager.preview(operator, data["settings"], data["text"], data.get("image_count", 0))
                else:
                    result = manager.configure(operator, data)
                if result.is_success and action != "preview":
                    status = result.value if action == "status" else result.value["status"]
                    status.update(target_id=self.target_id, role_id=self.role_id, session_id=session_id,
                                  scope_kind="group")
                return outcome_response(result)
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
                return outcome_response(Outcome.failed("group_reply_request_invalid", "invalid group reply settings request"))

    async def status(self):
        return await self._run("status")

    async def preview(self):
        try:
            data = await self._body("preview")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("group_reply_request_invalid", "invalid UTF-8 group reply preview request"))
        return await self._run("preview", data)

    async def configure(self):
        try:
            data = await self._body("configure")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return outcome_response(Outcome.failed("group_reply_request_invalid", "invalid UTF-8 group reply settings request"))
        return await self._run("configure", data)
