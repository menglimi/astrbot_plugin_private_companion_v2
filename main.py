# -*- coding: utf-8 -*-
"""AstrBot 4.27.2 entry for private conversation and explicitly authorized groups."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

# AstrBot imports plugins as ``data.plugins.<directory>.main`` without adding
# the plugin directory itself to sys.path.  The isolated core intentionally
# keeps its release package name ``companion_v2``; this host entry owns that
# one import path and releases it after a clean plugin shutdown.
_PLUGIN_ROOT = str(Path(__file__).resolve().parent)


def _module_belongs_to_plugin(module: object) -> bool:
    source = getattr(module, "__file__", None)
    if not isinstance(source, str):
        return False
    try:
        return Path(source).resolve().is_relative_to(Path(_PLUGIN_ROOT))
    except (OSError, ValueError):
        return False


_existing_core = sys.modules.get("companion_v2")
if _existing_core is not None and not _module_belongs_to_plugin(_existing_core):
    raise RuntimeError("another companion_v2 package is already loaded from a different source root")
_CORE_PATH_INSERTED = _PLUGIN_ROOT not in sys.path
if _CORE_PATH_INSERTED:
    sys.path.insert(0, _PLUGIN_ROOT)

from .astrbot_host.controller import AstrBotStagingController
from .astrbot_host.multi_controller import AstrBotMultiController
from companion_v2.product import PRODUCT_VERSION
from .astrbot_host.integration_registry import UnifiedCompanionExtensionAPI
from .astrbot_host.recalls import is_notice_event
from .astrbot_host.stranger_notice import refuse_stranger


PLUGIN_NAME = "astrbot_plugin_private_companion_v2"
PLUGIN_VERSION = PRODUCT_VERSION


@register(
    PLUGIN_NAME,
    "menglimi",
    "我会永远陪着你 V2.0 统一陪伴宿主，整合核心生活能力与公开拓展 API。",
    PLUGIN_VERSION,
)
class PrivateCompanionV2StagingPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context, config)
        self.config = config if config is not None else {}
        data_root = Path(StarTools.get_data_dir(PLUGIN_NAME))
        data_root.mkdir(parents=True, exist_ok=True)
        multi = self.config.get("multi_host", {})
        controller = AstrBotMultiController if isinstance(multi, dict) and multi.get("enabled", False) else AstrBotStagingController
        self.staging = controller(context, self.config, data_root)
        config_object = config if hasattr(config, "save_config") else None
        if config_object is not None:
            self.staging.save_plugin_config = self._save_plugin_config
        # This is the one public product facade. Optional plugins stay data
        # owners and are observed through their documented extension_api.
        self.extension_api = UnifiedCompanionExtensionAPI(self.staging)
        try:
            self.staging.register_routes()
        except Exception:
            logger.warning("[CompanionV2] staging 管理 API 注册失败", exc_info=True)

    def _save_plugin_config(self, candidate: dict[str, Any]) -> None:
        self.config.clear()
        self.config.update(candidate)
        self.config.save_config()

    async def initialize(self) -> None:
        if self.staging.settings is None or not self.staging.settings.enabled:
            logger.info("[CompanionV2] staging 宿主已加载，等待启用和显式初始化")
            return
        result = await self.staging.load_existing()
        if result.failure is not None:
            # The code alone is not actionable: a pinned-profile conflict lists which
            # fields moved in its reason, and that is the only place the operator can
            # see it. Environment drift no longer lands here -- it loads with a warning.
            logger.warning("[CompanionV2] 已固定 profile 只读加载失败: %s — %s",
                           result.failure.code, result.failure.reason)
            return
        state = result.unwrap()
        if state["loaded"]:
            started = await self.staging.start()
            if started.failure is not None:
                logger.warning("[CompanionV2] staging profile 已加载，但接管启动失败: %s",
                               started.failure.code)
                return
            logger.info("[CompanionV2] staging profile 已加载并开始接收入站消息")
        else:
            logger.info("[CompanionV2] staging profile 尚未初始化")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=240000)
    async def observe_companion_recall(self, event: AstrMessageEvent):
        result = await self.staging.receive_notice(event)
        if result is not None and result.failure is not None:
            logger.warning("[CompanionV2] 原生通知未受理: %s", result.failure.code)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=235000)
    async def receive_companion_binding(self, event: AstrMessageEvent):
        """First-run binding, handled before the staging target can claim anything.

        Sits between the notice listener (240000) and the intake listener (230000)
        deliberately: binding has to be seen while nothing is pinned -- ``claims``
        refuses every message until a target exists, so a bind command read at the
        intake priority would never be reached. Only the literal command is taken;
        ordinary private messages fall through to normal handling untouched.

        The reply is logged, never sent. Binding happens before any session exists,
        and the delivery boundary does not permit private sends without one, so the
        operator reads the outcome on the「开始使用」page instead. That ordering is
        what keeps this role's first real message the draft they reviewed.
        """
        if not self.staging.handles_binding(event):
            return
        event.stop_event()
        result = await self.staging.receive_binding(event)
        if result.get("handled"):
            logger.info("[CompanionV2] 首次绑定: %s", result.get("reason") or "ok")
        else:
            logger.warning("[CompanionV2] 绑定命令未被受理")

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE | filter.EventMessageType.GROUP_MESSAGE,
                               priority=230000)
    async def receive_companion_message(self, event: AstrMessageEvent):
        if is_notice_event(event):
            return
        if not self.staging.claims(event):
            # 不属于任何目标（未绑定、也没配进来）的私聊：默认什么都不做，
            # 消息留给 AstrBot 自己的管线。只有配置里明确打开"婉拒陌生号"时，
            # 才由插件回一句固定文案，并把这一轮从默认管线里拿走——
            # 已经答过话，就不该让对方收到两条回复。
            receipt = await refuse_stranger(self.staging, event)
            if receipt is not None:
                event.stop_event()
                logger.info("[CompanionV2] 陌生号婉拒: %s@%s 今日第 %s 条",
                            receipt["peer"], receipt["platform_id"], receipt["count_today"])
            return
        # Once the exact staging target is armed, never let AstrBot's ordinary
        # reply pipeline bypass the V2 delivery boundary.
        event.stop_event()
        result = await self.staging.receive_claimed(event)
        if result.failure is not None:
            logger.warning("[CompanionV2] staging 入站未受理: %s", result.failure.code)

    async def terminate(self) -> None:
        try:
            await self.staging.terminate()
            logger.info("[CompanionV2] staging 宿主已停止")
        finally:
            if _CORE_PATH_INSERTED:
                try:
                    sys.path.remove(_PLUGIN_ROOT)
                except ValueError:
                    pass
            for module_name in tuple(sys.modules):
                module = sys.modules.get(module_name)
                belongs = (
                    module_name == "companion_v2"
                    or module_name.startswith("companion_v2.")
                    or module_name == "astrbot_host"
                    or module_name.startswith("astrbot_host.")
                )
                if belongs and module is not None and _module_belongs_to_plugin(module):
                    sys.modules.pop(module_name, None)
