"""Authenticated page directory; the host supplies every target and API path."""

from urllib.parse import parse_qs, urlsplit

from astrbot.api import logger
from astrbot.api.web import request
from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy

from .management_identity import dashboard_operator
from .display_names import display_names
from .identity_derivation import role_display_name
from .settings import HostControlError


PREFIX = "/astrbot_plugin_private_companion"


class PageWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX + "/page/targets", self.targets, ["GET"], "Read authorized Companion page targets"),
                (PREFIX + "/page/workspace-entry", self.workspace_entry, ["GET"],
                 "Refresh the authenticated Companion workspace asset entry"),
                (PREFIX + "/page/ownership", self.ownership, ["GET"],
                 "Read which plugin currently provides model-facing memory")]

    async def workspace_entry(self):
        """Refresh the current page's short-lived resource token through AstrBot.

        Plugin pages run in an opaque-origin iframe, so their own fetch calls cannot
        read Dashboard endpoints. The registered plugin API bridge supplies the
        authenticated request context needed by AstrBot's page service.
        """

        from .web_api import outcome_response

        try:
            username = request.username
            if (
                type(username) is not str
                or not username.strip()
                or username.startswith("api_key:")
            ):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            plugin_name = PREFIX.lstrip("/")
            if request.plugin_name != plugin_name:
                raise TaskError("page_request_invalid", "the page entry is only available to this plugin")
            if request.query:
                raise TaskError("page_request_invalid", "the page entry does not accept query overrides")

            current_request = request._get_current()
            raw_request = getattr(current_request, "_request", None)
            app_state = getattr(getattr(raw_request, "app", None), "state", None)
            services = getattr(app_state, "services", None)
            page_service = getattr(services, "plugin_pages", None)
            get_entry = getattr(page_service, "get_plugin_page_entry_config", None)
            if not callable(get_entry):
                raise TaskError("page_entry_unavailable", "AstrBot page service is unavailable")

            locale = request.headers.get("accept-language", "").split(",", 1)[0].split(";", 1)[0].strip()
            if not locale or len(locale) > 32:
                locale = "zh-CN"
            entry = await get_entry(
                plugin_name=plugin_name,
                page_name="陪伴小屋",
                username=username,
                locale=locale,
            )
            content_path = entry.get("content_path") if isinstance(entry, dict) else None
            token = (
                parse_qs(urlsplit(content_path).query).get("asset_token", [""])[0]
                if isinstance(content_path, str)
                else ""
            )
            if not isinstance(content_path, str) or not content_path.strip() or not token:
                raise TaskError("page_entry_unavailable", "AstrBot returned an invalid page entry")
            return {"status": "ok", "message": "", "data": entry}
        except TaskError as error:
            if error.code == "page_entry_unavailable":
                logger.warning("[CompanionV2] 工作区授权刷新失败 code=%s", error.code)
            return outcome_response(Outcome.failed(error.code, str(error)))
        except Exception as error:
            logger.warning("[CompanionV2] 工作区授权刷新暂不可用 error_type=%s", type(error).__name__)
            return outcome_response(Outcome.failed(
                "page_entry_unavailable", "AstrBot could not refresh the workspace entry"))

    async def ownership(self):
        """这段时期记忆由谁对外提供，以及为什么不是 V2。

        这个回答是**安装级**的（判定读的是进程里别家插件公开的声明），所以它挂在
        页面目录旁边，而不是某一个会话目标下面——同一个安装下所有角色共享同一个
        回答，按目标重复一遍只会让页面以为它们可以不一样。

        页面据此写出「记忆由〈我会牢牢记住你〉提供」，所以判定失败时也必须给出
        原因码：宁可说「句柄读不到、暂时由 V2 自己提供」，也不能两边都不说话。
        """

        from .web_api import outcome_response

        try:
            controller = self.controller
            if controller._terminated:
                raise TaskError("staging_host_terminated", "plugin is stopped")
            session = controller.session or controller.last_session
            if session is None:
                raise TaskError("staging_not_initialized", "load the explicit V2 profile first")
            return outcome_response(Outcome.success(session.application.memory.context.ownership()))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))

    async def targets(self):
        from .web_api import outcome_response

        try:
            username = request.username
            if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            if request.query:
                raise TaskError("page_request_invalid", "the page directory does not accept identity overrides")
            async with self.controller._control_lock:
                controller = self.controller
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                if controller.runtime is None or controller.settings is None:
                    raise TaskError("staging_not_initialized", "load the explicit V2 profile first")
                runtime = controller.runtime
                settings_snapshot = controller.settings
                operator = dashboard_operator(runtime, username, at=controller.now())
                require(ObjectAccessPolicy(runtime).feature_access(operator,
                    scope=ScopeRef(runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
                    action="memory.manage", observed_at=controller.now()))
                inventory = getattr(controller.web_api, "target_inventory", None)
                if callable(inventory):
                    targets = inventory()
                else:
                    settings = controller.resolved_settings()
                    targets = [{"target_id": settings.profile_id, "scope_kind": "private",
                        **{key: getattr(settings, key) for key in ("platform_id", "account_id", "bot_id", "participant_id")},
                        "roles": [{"role_id": settings.role_id, "persona_ids": [settings.persona_id],
                                   **{name + "_api": PREFIX + "/" + name for name in
                                      ("memory", "state", "life", "relationships", "growth", "reply", "model", "config",
                                       # V1 迁移写的是角色设置，所以它的地址跟着角色走；
                                       # 多目标下同一个键由 target_inventory 给每个角色各生成一份。
                                       "legacy",
                                       # 人格工坊按角色挂在同一张目录上：草稿属于「角色 + 宿主人格」，
                                       # 会话窗口重绑不应该让它消失。
                                       "persona")},
                                   "perception_native_api": PREFIX + "/perception-native",
                                   "reality_access_api": PREFIX + "/reality-access",
                                   "screen_access_api": PREFIX + "/screen-access",
                                   "game_access_api": PREFIX + "/game-access",
                                   # QQ 空间拓展按角色安装与授权，所以它的地址也跟角色走。
                                   "qzone_extension_api": PREFIX + "/qzone-extension",
                                   "image_material_api": PREFIX + "/image-materials"}]}]
                # A directory is navigation, not delivery authorization or a configuration dump.
                public = [{key: target.get(key) for key in
                    ("target_id", "scope_kind", "platform_id", "account_id", "bot_id", "participant_id", "group_id",
                     "display_name", "group_name", "account_name")}
                    | {"roles": [{"role_id": role["role_id"],
                                 "role_name": role.get("role_name") or role_display_name(
                                     role["role_id"], role.get("persona_ids", [])),
                                 **({"group_memory_api": role["group_memory_api"]} if role.get("group_memory_api") else {}),
                                 **({"legacy_group_data_api": role["legacy_group_data_api"]}
                                    if role.get("legacy_group_data_api") else {}),
                                 **{name + "_api": role.get(name + "_api") for name in
                                    ("memory", "state", "life", "relationships", "growth", "reply", "model",
                                     "config", "perception_native", "reality_access", "screen_access", "game_access", "persona", "legacy",
                                     "qzone_extension", "image_material")}}
                                 for role in target["roles"]]} for target in targets]
            public = await display_names(controller).targets(public)
            async with controller._control_lock:
                if controller.runtime is not runtime or controller.settings is not settings_snapshot:
                    raise TaskError("staging_not_initialized", "the profile changed while reading display names")
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                require(ObjectAccessPolicy(runtime).feature_access(operator,
                    scope=ScopeRef(runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
                    action="memory.manage", observed_at=controller.now()))
                return outcome_response(Outcome.success({"installation_id": runtime.installation_id,
                    # Backups cover the whole installation, not one relationship, so the
                    # endpoint sits beside the target list rather than inside a role.
                    "backup_api": PREFIX + "/backup",
                    "acquaintance_api": PREFIX + "/acquaintance",
                    "accounts_api": PREFIX + "/accounts",
                    "operator_id": operator.subject.subject_id, "operator_name": username, "targets": public}))
        except (TaskError, HostControlError) as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
