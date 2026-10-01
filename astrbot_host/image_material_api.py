"""Authenticated Dashboard API for the native image album, references and wardrobe."""

from __future__ import annotations

import json

from astrbot.api.web import request

from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.references.management import ReferenceMaterialManagement

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2/image-materials"
MAX_BODY = 8192


class ImageMaterialsWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [
            (PREFIX, self.inventory, ["GET"], "Read one role's native image materials"),
            (PREFIX + "/album", self.album, ["GET"], "Read the role-scoped generated image album"),
            (PREFIX + "/references", self.register_reference, ["POST"], "Register one explicit album image reference"),
            (PREFIX + "/references/withdraw", self.withdraw_reference, ["POST"], "Withdraw one role image reference"),
            (PREFIX + "/wardrobe", self.register_wardrobe, ["POST"], "Add one role wardrobe item"),
            (PREFIX + "/wardrobe/withdraw", self.withdraw_wardrobe, ["POST"], "Withdraw one role wardrobe item"),
            (PREFIX + "/daily-outfit", self.select_daily_outfit, ["POST"], "Choose today's role outfit"),
        ]

    async def _operator_context(self, *, allow_cursor=False):
        controller = self.controller
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        if set(request.query) - ({"cursor"} if allow_cursor else set()) or any(
                len(request.query.getlist(key)) != 1 for key in request.query):
            raise TaskError("image_material_request_invalid", "unexpected query fields")
        if controller._terminated:
            raise TaskError("staging_host_terminated", "the plugin has stopped")
        session = controller.session or controller.last_session
        if session is None or controller.runtime is None:
            raise TaskError("staging_not_initialized", "load the V2 profile before managing image materials")
        at = controller.now()
        operator = dashboard_operator(controller.runtime, username, at=at)
        require(ObjectAccessPolicy(controller.runtime).feature_access(
            operator,
            scope=ScopeRef(controller.runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
            action="memory.manage",
            observed_at=at,
        ))
        context = session.profile.target
        if getattr(context, "scope", None) is None or context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("reference_scope_invalid", "select a configured private target and role")
        if session.application.runtime is not controller.runtime:
            raise TaskError("staging_profile_changed", "the selected profile no longer owns this V2 data root")
        return operator, context, at, ReferenceMaterialManagement(session.application)

    @staticmethod
    def _document(raw, expected):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite value")))
        if type(value) is not dict or set(value) != set(expected):
            raise ValueError("unexpected or missing fields")
        return value

    async def _run(self, action, *, query=None, body=None):
        from .web_api import outcome_response

        controller = self.controller
        try:
            async with controller._control_lock:
                operator, context, at, manager = await self._operator_context()
                if action == "inventory":
                    value = manager.inventory(operator, context, at=at)
                elif action == "album":
                    value = manager.album(operator, context, at=at, cursor=query.get("cursor"))
                elif action == "register_reference":
                    value = manager.register_from_album(operator, context, at=at, **body)
                elif action == "withdraw_reference":
                    value = manager.withdraw_reference(operator, context, body["asset_id"], at=at)
                elif action == "register_wardrobe":
                    value = manager.register_wardrobe_item(operator, context, at=at, **body)
                elif action == "withdraw_wardrobe":
                    value = manager.withdraw_wardrobe_item(operator, context, body["item_id"], at=at)
                else:
                    value = manager.select_daily_outfit(operator, context, body["item_id"], at=at)
                return outcome_response(Outcome.success(value))
        except (TaskError, ConfigurationError) as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError):
            return outcome_response(Outcome.failed(
                "image_material_request_invalid",
                "image material values are invalid",
            ))

    async def inventory(self):
        if request.query:
            from .web_api import outcome_response
            return outcome_response(Outcome.failed("image_material_request_invalid", "unexpected query fields"))
        return await self._run("inventory")

    async def album(self):
        from .web_api import outcome_response

        query = request.query
        if set(query) - {"cursor"} or any(len(query.getlist(key)) != 1 for key in query):
            return outcome_response(Outcome.failed("image_material_request_invalid", "unknown or repeated album query fields"))
        cursor = query.get("cursor")
        if cursor is not None and (type(cursor) is not str or not 8 <= len(cursor) <= 1024):
            return outcome_response(Outcome.failed("generated_album_cursor_invalid", "the album cursor is invalid"))
        # The cursor is passed separately; the authenticated manager is fixed by the route.
        try:
            controller = self.controller
            async with controller._control_lock:
                operator, context, at, manager = await self._operator_context(allow_cursor=True)
                return outcome_response(Outcome.success(manager.album(operator, context, at=at, cursor=cursor)))
        except (TaskError, ConfigurationError) as error:
            return outcome_response(Outcome.failed(error.code, str(error)))

    async def _post(self, action, expected):
        from .web_api import outcome_response

        try:
            raw = await request.body()
            if len(raw) > MAX_BODY or request.query:
                raise ValueError("request is too large or has query fields")
            body = self._document(raw, expected)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("image_material_request_invalid", "invalid UTF-8 image material request"))
        return await self._run(action, body=body)

    async def register_reference(self):
        return await self._post("register_reference", {"image_id", "label", "roles", "operation_key"})

    async def withdraw_reference(self):
        return await self._post("withdraw_reference", {"asset_id"})

    async def register_wardrobe(self):
        return await self._post("register_wardrobe", {"operation_key", "name", "description", "tags", "asset_id"})

    async def withdraw_wardrobe(self):
        return await self._post("withdraw_wardrobe", {"item_id"})

    async def select_daily_outfit(self):
        return await self._post("select_daily_outfit", {"item_id"})
