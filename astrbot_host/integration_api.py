"""Authenticated read-only product manifest route shared by both V2 hosts."""

from __future__ import annotations

from typing import Any

from astrbot.api.web import request

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy

from .management_identity import dashboard_operator
from .integration_registry import UnifiedCompanionExtensionAPI


PREFIX = "/astrbot_plugin_private_companion_v2"


class IntegrationWebAPI:
    def __init__(self, controller: Any):
        self.controller = controller

    def routes(self):
        return [(
            PREFIX + "/integration/manifest",
            self.manifest,
            ["GET"],
            "Read the integrated Companion V2 product manifest",
        )]

    async def manifest(self) -> dict[str, Any]:
        try:
            username = request.username
            if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            if request.query:
                raise TaskError("integration_request_invalid", "the integration manifest does not accept query overrides")
            controller = self.controller
            async with controller._control_lock:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "the V2 host has stopped")
                runtime = controller.runtime
                if runtime is not None:
                    operator = dashboard_operator(runtime, username, at=controller.now())
                    require(ObjectAccessPolicy(runtime).feature_access(
                        operator,
                        scope=ScopeRef(runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
                        action="memory.manage",
                        observed_at=controller.now(),
                    ))
                return {"status": "ok", "message": "", "data": UnifiedCompanionExtensionAPI(controller).manifest()}
        except TaskError as error:
            return {
                "status": "error",
                "message": str(error),
                "data": {"code": error.code},
            }
