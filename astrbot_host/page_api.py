"""Authenticated page directory; the host supplies every target and API path."""

from astrbot.api.web import request
from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2"


class PageWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX + "/page/targets", self.targets, ["GET"], "Read authorized Companion page targets"),
                (PREFIX + "/page/ownership", self.ownership, ["GET"],
                 "Read which plugin currently provides model-facing memory")]

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
                operator = dashboard_operator(runtime, username, at=controller.now())
                require(ObjectAccessPolicy(runtime).feature_access(operator,
                    scope=ScopeRef(runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
                    action="memory.manage", observed_at=controller.now()))
                inventory = getattr(controller.web_api, "target_inventory", None)
                if callable(inventory):
                    mode, targets = "multi", inventory()
                else:
                    settings = controller.settings
                    mode = "single"
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
                                   # QQ 空间拓展按角色安装与授权，所以它的地址也跟角色走。
                                   "qzone_extension_api": PREFIX + "/qzone-extension",
                                   "image_material_api": PREFIX + "/image-materials"}]}]
                # A directory is navigation, not delivery authorization or a configuration dump.
                public = [{key: target.get(key) for key in
                    ("target_id", "scope_kind", "platform_id", "account_id", "bot_id", "participant_id", "group_id")}
                    | {"roles": [{"role_id": role["role_id"],
                                 **({"group_memory_api": role["group_memory_api"]} if role.get("group_memory_api") else {}),
                                 **{name + "_api": role.get(name + "_api") for name in
                                    ("memory", "state", "life", "relationships", "growth", "reply", "model",
                                     "config", "perception_native", "reality_access", "screen_access", "persona", "legacy",
                                     "qzone_extension", "image_material")}}
                                 for role in target["roles"]]} for target in targets]
                return outcome_response(Outcome.success({"mode": mode, "installation_id": runtime.installation_id,
                    # Backups cover the whole installation, not one relationship, so the
                    # endpoint sits beside the target list rather than inside a role.
                    "backup_api": PREFIX + "/backup",
                    "acquaintance_api": PREFIX + "/acquaintance",
                    "operator_id": operator.subject.subject_id, "targets": public}))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
