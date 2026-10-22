"""Dashboard-authorized configuration bridge to the two perception owners."""

from __future__ import annotations

import inspect
import json
from typing import Any

from astrbot.api.web import request

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion/perception"
PROVIDERS = {"reality": "astrbot_plugin_private_companion.reality"}


class PerceptionWebAPI:
    def __init__(self, controller: Any):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.get, ["GET"], "Read perception provider settings"),
                (PREFIX, self.post, ["POST"], "Save perception provider settings")]

    def _authorize(self) -> None:
        controller = self.controller
        if controller._terminated:
            raise TaskError("staging_host_terminated", "plugin is stopped")
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        if controller.runtime is None:
            raise TaskError("staging_not_initialized", "load the V2 profile first")
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        require(ObjectAccessPolicy(controller.runtime).feature_access(
            operator,
            scope=ScopeRef(controller.runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
            action="memory.manage", observed_at=controller.now(),
        ))

    def _provider(self, provider_id: str):
        plugin_id = PROVIDERS.get(provider_id)
        if plugin_id is None:
            raise ValueError("unknown perception provider")
        registry = getattr(self.controller, "native_extensions", None)
        api = registry.api(provider_id) if registry is not None else None
        if api is None:
            raise TaskError("perception_provider_unavailable", "感知提供方尚未加载")
        if api is None or not callable(getattr(api, "companion_v2_perception_settings", None)):
            raise TaskError("perception_provider_unavailable", "感知提供方需要更新后才能在此配置")
        return api

    @staticmethod
    def _ok(data):
        return {"status": "ok", "message": "", "data": data}

    @staticmethod
    def _error(error):
        from companion_v2.foundation.outcome import Outcome
        from .web_api import outcome_response

        code = error.code if isinstance(error, TaskError) else "perception_request_invalid"
        return outcome_response(Outcome.failed(code, str(error)))

    async def get(self):
        try:
            if request.query:
                raise ValueError("unexpected query fields")
            async with self.controller._control_lock:
                self._authorize()
                providers = {}
                for provider_id in PROVIDERS:
                    try:
                        providers[provider_id] = {"available": True,
                                                  "settings": self._provider(provider_id).companion_v2_perception_settings()}
                    except (TaskError, ValueError, RuntimeError) as error:
                        providers[provider_id] = {"available": False, "reason": str(error)}
                    except Exception:
                        providers[provider_id] = {"available": False, "reason": "提供方配置暂不可读取"}
                return self._ok({"providers": providers})
        except (TaskError, ValueError) as error:
            return self._error(error)

    async def post(self):
        try:
            raw = await request.body()
            if request.query or len(raw) > 64 * 1024:
                raise ValueError("bounded JSON body required")

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON field")
                    result[key] = value
                return result

            payload = json.loads(raw, object_pairs_hook=unique)
            if (type(payload) is not dict or set(payload) != {"provider", "section", "updates"}
                    or type(payload["provider"]) is not str or type(payload["section"]) is not str
                    or type(payload["updates"]) is not dict):
                raise ValueError("invalid perception settings request")
            async with self.controller._control_lock:
                self._authorize()
                api = self._provider(payload["provider"])
                method = getattr(api, "companion_v2_update_perception_settings", None)
                if not callable(method):
                    raise TaskError("perception_provider_unavailable", "感知提供方尚不支持在此保存")
                if payload["provider"] == "screen":
                    if payload["section"] != "settings":
                        raise ValueError("invalid screen section")
                    result = method(payload["updates"])
                else:
                    if payload["section"] not in {"global", "camera", "mobile", "health"}:
                        raise ValueError("invalid reality section")
                    result = method(payload["section"], payload["updates"])
                if inspect.isawaitable(result):
                    result = await result
                return self._ok({"provider": payload["provider"], "settings": result})
        except (TaskError, ValueError, TypeError, json.JSONDecodeError) as error:
            return self._error(error)
        except Exception:
            return self._error(TaskError("perception_save_failed", "提供方保存失败，请刷新核对"))
