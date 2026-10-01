"""Discover optional providers without importing plugins or reading their stores.

The only invoked contract is companion_v2_status (metadata only). A readable
provider status and its own execution readiness are deliberately separate.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from companion_v2.product import CORE_COMPONENTS, PRODUCT_DISPLAY_NAME, PRODUCT_ID, PRODUCT_VERSION
from .integration_catalog import OPTIONAL_PROVIDERS


STATUS_SCHEMA = "companion.provider-status.v1"


class IntegrationRegistry:
    def __init__(self, context: Any):
        self.context = context

    def snapshot(self, *, host_status=None, application=None, terminated=False, native_issues=()):
        discovery = "available"
        try:
            stars = self.context.get_all_stars()
        except Exception:
            stars, discovery = (), "unavailable"
        installed = {}
        for star in stars:
            # Match exact directory metadata, never a display-name substring.
            identifier = getattr(star, "root_dir_name", None) or getattr(star, "name", None)
            installed.setdefault(identifier, []).append(star)
        providers = [self._provider(spec, installed.get(spec["plugin_id"], []), discovery, terminated)
                     for spec in OPTIONAL_PROVIDERS]
        conflicts = {plugin_id for plugin_id, code in native_issues if code == "capability_descriptor_conflict"}
        for provider in providers:
            if provider["plugin_id"] in conflicts:
                provider.update(integration_state="degraded", execution_issue="capability_descriptor_conflict",
                    reason="能力声明与保留版本冲突，当前不能在对话中调用。请更新提供方的包版本后重新确认启用。")
        host = dict(host_status or {})
        core = [{**item, "routes": list(item["routes"]), "owner": "companion_v2",
                 "implementation": "included", "runtime_state": getattr(application, "state", "unloaded")}
                for item in CORE_COMPONENTS]
        return {
            "product": {"id": PRODUCT_ID, "display_name": PRODUCT_DISPLAY_NAME, "version": PRODUCT_VERSION,
                        "release_channel": "integrated", "direct_replacement": False,
                        "data_policy": "V2 独立运行库；旧版资料尚未迁移。"},
            "host": host, "core": core, "providers": providers, "discovery": discovery,
            "summary": {"core_count": len(core), "provider_count": len(providers),
                        "connected_count": sum(p["status_connected"] for p in providers),
                        "installed_count": sum(p["installed"] for p in providers),
                        "missing_count": sum(p["integration_state"] == "missing" for p in providers)},
        }

    @staticmethod
    def _provider(spec, matches, discovery, terminated):
        item = {**spec, "owner": "external", "installed": bool(matches), "activated": False,
                "version": None, "status_connected": False, "enabled": None, "runtime_ready": None,
                "execution_owner": spec["plugin_id"], "execution_integrated": False,
                "integration_state": "missing", "reason": "插件未安装", "pages": []}
        if discovery == "unavailable":
            item.update(integration_state="unknown", reason="宿主没有提供插件目录")
        if terminated:
            item.update(integration_state="stopped", reason="V2 宿主已停止")
            return item
        if not matches:
            return item
        if len(matches) != 1:
            item.update(integration_state="conflict", reason="检测到重复提供方，请重新加载插件")
            return item
        star = matches[0]
        item["dashboard_name"] = str(getattr(star, "name", None) or spec["plugin_id"])
        item["version"] = str(getattr(star, "version", "") or "unknown")[:80]
        item["activated"] = getattr(star, "activated", False) is True
        if not item["activated"]:
            item.update(integration_state="disabled", reason="插件已停用")
            return item
        for page in (getattr(star, "pages", None) or []):
            name = page.get("name") if isinstance(page, dict) else getattr(page, "name", None)
            if isinstance(name, str) and name and len(name) <= 128:
                item["pages"].append(name)
        # Read only packaged page entry names. Never inspect provider data roots.
        pages_root = Path(__file__).resolve().parents[2] / spec["plugin_id"] / "pages"
        try:
            if pages_root.is_dir():
                for page in sorted(pages_root.iterdir()):
                    if (page.name != "framework-preview-v1" and page.is_dir()
                            and page.resolve().is_relative_to(pages_root.resolve())
                            and (page / "index.html").is_file() and page.name not in item["pages"]):
                        item["pages"].append(page.name)
        except OSError:
            # A page directory may disappear during a provider update. Metadata
            # discovery remains useful even when its optional page list fails.
            pass
        # An inactive Star must not be invoked even when a stale instance remains.
        api = getattr(getattr(star, "star_cls", None), "extension_api", None)
        method = getattr(api, "companion_v2_status", None)
        if not callable(method) or inspect.iscoroutinefunction(method):
            item.update(integration_state="installed", reason="已安装；需要加载新版状态适配器")
            return item
        try:
            status = method()
            if inspect.isawaitable(status):
                if inspect.iscoroutine(status):
                    status.close()
                raise ValueError("asynchronous status is not supported")
            if (type(status) is not dict or status.get("schema") != STATUS_SCHEMA
                    or status.get("plugin_id") != spec["plugin_id"]
                    or type(status.get("enabled")) is not bool
                    or (status.get("runtime_ready") is not None and type(status["runtime_ready"]) is not bool)):
                raise ValueError("invalid status contract")
            # Only these typed scalar fields can cross into the manifest. No raw
            # configuration, private error text, paths, tokens or user data.
            item.update(status_connected=True, enabled=status["enabled"], runtime_ready=status.get("runtime_ready"))
            if status["enabled"] is False:
                item.update(integration_state="disabled", reason="提供方配置已关闭")
            elif status.get("runtime_ready") is False:
                item.update(integration_state="waiting", reason="状态已接入；提供方尚未就绪")
            else:
                item.update(integration_state="connected", reason="状态已接入；功能由原提供方执行")
        except Exception:
            item.update(integration_state="degraded", reason="提供方状态读取失败，可重新检查")
        return item


class UnifiedCompanionExtensionAPI:
    """Public metadata facade; conversation/operation authority stays in the host."""
    api_version = "companion.product.v1"

    def __init__(self, controller):
        self.controller = controller
        from .mobile_together import MobileTogetherBridge
        self._mobile_together = MobileTogetherBridge(controller)

    def companion_v2_mobile_session_user(self, session_token: str) -> dict[str, str]:
        return self._mobile_together.mobile_session_user(session_token)

    def companion_v2_mobile_together_status(self, session_token: str, *, via_mobile_gateway: bool = False):
        return self._mobile_together.status(session_token)

    async def companion_v2_mobile_together_create(self, session_token: str, request_id: str, mode: str,
                                                  *, via_mobile_gateway: bool = False):
        result = await self._mobile_together.invoke(session_token, request_id=request_id,
                                                    operation="create", arguments={"mode": mode})
        return self._mobile_together.mobile_result("create", result)

    async def companion_v2_mobile_together_invite(self, session_token: str, request_id: str,
                                                  expires_in_seconds: int | None = None,
                                                  *, via_mobile_gateway: bool = False):
        arguments = {} if expires_in_seconds is None else {"expires_in_seconds": expires_in_seconds}
        result = await self._mobile_together.invoke(session_token, request_id=request_id,
                                                    operation="invite", arguments=arguments)
        return self._mobile_together.mobile_result("invite", result)

    async def companion_v2_mobile_together_join(self, session_token: str, request_id: str,
                                                invitation_id: str,
                                                *, via_mobile_gateway: bool = False):
        result = await self._mobile_together.invoke(session_token, request_id=request_id,
            operation="join", arguments={"invitation_id": invitation_id})
        return self._mobile_together.mobile_result("join", result)

    def manifest(self):
        controller = self.controller
        session = controller.session or controller.last_session
        return controller.integration.snapshot(host_status=controller.status(),
            application=session.application if session else None, terminated=controller._terminated,
            native_issues=getattr(getattr(controller, "native_extensions", None), "issues", ()))

    def status(self):
        return self.manifest()

    def capabilities(self):
        return {"api_version": self.api_version, "product_id": PRODUCT_ID,
                "implemented_domains": [item["id"] for item in CORE_COMPONENTS],
                "lifecycle_state": "stopped" if self.controller._terminated else "ready"}

    def room_furniture_catalog(self):
        return {"items": [{**item["furniture"], "plugin_id": item["plugin_id"],
                           "integration_state": item["integration_state"]}
                          for item in self.manifest()["providers"]]}
