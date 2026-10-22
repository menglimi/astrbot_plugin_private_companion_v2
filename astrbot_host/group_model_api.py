"""Dashboard model routing overrides for one configured group and role."""

from types import SimpleNamespace

from astrbot.api.web import request
from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.model_gateway.management import ModelManagement

from .group_settings import GroupTarget
from .management_identity import dashboard_operator
from .model_api import PREFIX as MODEL_PREFIX, _document_optional
from .web_api import outcome_response


class GroupModelWebAPI:
    def __init__(self, controller, target_id, role_id):
        self.controller, self.target_id, self.role_id = controller, target_id, role_id

    def routes(self, prefix):
        return [(prefix, self.status, ["GET"], "Read this group's model routing"),
                (prefix + "/configure", self.configure, ["POST"], "Save this group's model routing")]

    async def _prepare(self, layer):
        controller = self.controller
        if controller._terminated:
            raise TaskError("staging_host_terminated", "plugin is stopped")
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        session = controller.session or controller.last_session
        if session is None or controller.runtime is None:
            raise TaskError("staging_not_initialized", "load the V2 profile first")
        target = controller.settings.target(self.target_id)
        if not isinstance(target, GroupTarget) or not any(
                item.bot_id == target.bot_id and item.role_id == self.role_id
                for item in controller.settings.personas):
            raise TaskError("group_model_target_required", "the configured group and role are unavailable")
        bridge = session.bridge.groups
        account = bridge.accounts.get((target.platform_id, target.account_id))
        if account is None:
            raise TaskError("group_model_target_required", "the configured group account is unavailable")
        conversation_id, role, _instruction = await bridge._role(account, target.group_id)
        if role.subject_id != self.role_id or role.installation_id != controller.runtime.installation_id:
            raise TaskError("group_model_role_changed", "the configured group now selects another role")
        scope = ScopeRef(controller.runtime.installation_id, target.platform_id, ScopeKind.GROUP,
                         target.group_id, target.bot_id, target.account_id, conversation_id, target.group_id)
        if bridge.target_for_scope(scope) != target:
            raise TaskError("group_model_target_required", "the configured group route changed")
        resolved = session.application.tasks.identity.resolve_role(scope, observed_at=controller.now())
        if resolved.failure is not None:
            if resolved.failure.code not in ("role_binding_missing", "scope_unresolved"):
                require(resolved)
            # Admin model settings may be opened before this group has produced
            # its first authenticated turn. The native persona was verified
            # above; this management-only context does not create a runtime
            # identity binding for a group without an authenticated speaker.
            binding = SimpleNamespace(role=role, revision=0)
        else:
            binding = resolved.unwrap()
        if binding.role != role:
            raise TaskError("group_model_role_changed", "the registered group role changed")
        context = SimpleNamespace(scope=scope, role_binding=binding,
            key=digest(["group-model-context.v1", scope.document(), binding.revision]))
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        manager = ModelManagement(session.application, context)
        return operator, manager, layer

    @staticmethod
    def _layer_query():
        query = request.query
        if set(query.keys()) - {"layer"} or any(len(query.getlist(key)) != 1 for key in query.keys()):
            raise TaskError("model_request_invalid", "model routes do not accept target overrides")
        layer = query.get("layer", "role")
        if layer not in ("role", "window"):
            raise TaskError("model_request_invalid", "select role defaults or this conversation window")
        return layer

    async def status(self):
        try:
            layer = self._layer_query()
            async with self.controller._control_lock:
                operator, manager, _ = await self._prepare(layer)
                result = require(manager.status(operator, layer=layer))
                result["scope_kind"] = "group"
                return outcome_response(Outcome.success(result))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except ConfigurationError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, AttributeError):
            return outcome_response(Outcome.failed("group_model_unavailable", "group model settings are unavailable"))

    async def configure(self):
        try:
            data = _document_optional(await request.body(),
                {"kind", "operation_key", "edit_token", "changes", "reset"},
                optional=("section", "layer"))
            layer = data.get("layer", "role")
            if layer not in ("role", "window"):
                raise TaskError("model_request_invalid", "select role defaults or this conversation window")
            if (data.get("kind") == "conversation.reply" and not data.get("section")
                    and ({*(data.get("changes") or {}), *(data.get("reset") or [])}
                         & {"provider", "fallback", "max_output_tokens", "timeout_seconds"})):
                raise TaskError("model_configuration_host_managed",
                                "AstrBot manages the active group reply model; only V2 task routes are editable here")
            async with self.controller._control_lock:
                operator, manager, _ = await self._prepare(layer)
                result = require(manager.configure(operator, data))
                result["task"]["scope_kind"] = "group"
                return outcome_response(Outcome.success(result))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except ConfigurationError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, AttributeError):
            return outcome_response(Outcome.failed("group_model_request_invalid", "invalid group model settings request"))
