# -*- coding: utf-8 -*-
"""AstrBot entry for private conversation and explicitly authorized groups."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .astrbot_host.import_lifecycle import activate_plugin_imports, retire_plugin_imports

# AstrBot imports plugins as ``data.plugins.<directory>.main`` without adding
# the plugin directory itself to sys.path.  The isolated core intentionally
# keeps its release package name ``companion_v2``; this host entry owns that
# one import path and releases it after a clean plugin shutdown.
_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
_CORE_PATH_INSERTED = activate_plugin_imports(_PLUGIN_ROOT, __name__)

from .astrbot_host.multi_controller import AstrBotMultiController
from .astrbot_host.conversation_reset import install_native_reset_marker
from .astrbot_host.event_routing import (
    COMPANION_INTAKE_PRIORITY, competing_command_handler, suppress_default_reply,
)
from .astrbot_host.shared_host_migration import migrate_single_target_config
from .astrbot_host.storage_location import prepare_storage_root
from companion_v2.product import PRODUCT_VERSION
from companion_v2.diagnostics.inbound import InboundNoReplyLedger, SUPPRESSED, UNMET
from .astrbot_host.integration_registry import UnifiedCompanionExtensionAPI
from .astrbot_host.recalls import is_notice_event
from .astrbot_host.stranger_notice import refuse_stranger


PLUGIN_NAME = "astrbot_plugin_private_companion_v2"
PLUGIN_VERSION = PRODUCT_VERSION
# 婉拒陌生号里，只有"该发却发不出去"才算预期未回。开关关闭、冷却、当日额度、
# 权限或文案不可用，都是设计内的安静，连排障台账都不该记。
STRANGER_NOTICE_FAILURES = frozenset({
    "stranger_notice_session_unavailable",
    "stranger_notice_settings_unavailable",
    "stranger_notice_send_failed",
    "stranger_notice_processing_failed",
})
GROUP_INPUT_PASSTHROUGH_FAILURES = frozenset({
    "host_group_media_unsupported",
    "host_media_unsupported",
})


@register(
    PLUGIN_NAME,
    "menglimi",
    "我会永远陪着你 V2.0 统一陪伴宿主，整合核心生活能力与公开拓展 API。",
    PLUGIN_VERSION,
)
class PrivateCompanionV2StagingPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context, config)
        self._imports_retired = False
        self._host_start_task = None
        self.config = config if config is not None else {}
        default_data_root = Path(StarTools.get_data_dir(PLUGIN_NAME)).resolve()
        data_root = prepare_storage_root(default_data_root, self.config)
        data_root.mkdir(parents=True, exist_ok=True)
        migrated, changed = migrate_single_target_config(self.config)
        if changed:
            self.config.clear()
            self.config.update(migrated)
        self.staging = AstrBotMultiController(context, self.config, data_root)
        self._retire_context_reset_marker = install_native_reset_marker(context)
        self.staging.default_data_root = default_data_root
        config_object = config if hasattr(config, "save_config") else None
        if config_object is not None:
            self.staging.save_plugin_config = self._save_plugin_config
            if changed:
                try:
                    config_object.save_config()
                except Exception:
                    logger.warning("[CompanionV2] 旧单目标设置已在内存迁移，但持久化失败", exc_info=True)
        # This is the one public product facade. Optional plugins stay data
        # owners and are observed through their documented extension_api.
        self.extension_api = UnifiedCompanionExtensionAPI(self.staging)
        try:
            self.staging.register_routes()
        except Exception:
            logger.warning("[CompanionV2] 共享宿主管理 API 注册失败", exc_info=True)

    def _save_plugin_config(self, candidate: dict[str, Any]) -> None:
        previous = dict(self.config)
        self.config.clear()
        self.config.update(candidate)
        try:
            self.config.save_config()
        except Exception:
            self.config.clear()
            self.config.update(previous)
            raise

    def _record_no_reply(self, event, reason_code, *, origin_key=None, channel=None, event_ref=None,
                         stage="intake", turn=None, expected=True, code=None):
        """Resolve one inbound that produced no reply.

        ``expected`` is the polarity, and it is the whole contract: only a reply
        that was genuinely expected and then not delivered reaches the platform
        log. Anything outside this plugin's targets, any disabled feature and
        any deliberate silence is recorded at most in the bounded ledger.
        """
        if channel is None:
            kind = getattr(getattr(getattr(event, "message_obj", None), "type", None), "value", None)
            channel = "private" if kind == "FriendMessage" else "group" if kind == "GroupMessage" else "unknown"
        event_ref = event_ref or uuid4().hex
        runtime = getattr(self.staging, "runtime", None)
        if runtime is not None:
            try:
                InboundNoReplyLedger(runtime).emit(
                    expectation=UNMET if expected else SUPPRESSED, stage=stage,
                    turn=turn or event_ref, reason_code=reason_code, observed_at=self.staging.now(),
                    channel=channel, origin_key=origin_key, event_ref=event_ref, code=code)
            except Exception as error:
                logger.error("[CompanionV2] 未回复排障记录写入失败 event_ref=%s error_type=%s",
                             event_ref, type(error).__name__)
        return event_ref

    def _origin_key_for_event(self, event):
        target_for_event = getattr(self.staging, "target_for_event", None)
        target = target_for_event(event) if callable(target_for_event) else None
        if target is None:
            session = getattr(self.staging, "session", None)
            target = getattr(getattr(session, "profile", None), "target", None)
        key = getattr(target, "key", None)
        return key if isinstance(key, str) and key else None

    def _claims_target(self, event) -> bool:
        """Whether this exact event resolves to one of the configured targets.

        A target that resolves but is not being accepted is still the plugin's
        own message; the difference matters because only the plugin's own
        inbounds may ever produce a reply outcome at all.
        """
        target_for_event = getattr(self.staging, "target_for_event", None)
        try:
            return bool(callable(target_for_event) and target_for_event(event) is not None)
        except Exception:
            return False

    def staging_enabled(self) -> bool:
        """Whether this installation ever asked the shared host to answer.

        With the host switched off, or its settings unreadable, nothing was ever
        promised to anybody: that is a configuration state, not a missed reply.
        """
        settings = getattr(self.staging, "settings", None)
        return bool(getattr(settings, "enabled", False))

    def _admission_reason(self) -> str:
        """Why the shared host could not take a message it owns."""
        session = getattr(self.staging, "session", None)
        app_state = getattr(getattr(session, "application", None), "state", None)
        return ("staging_terminated" if getattr(self.staging, "_terminated", False) else
                "staging_not_accepting" if not getattr(self.staging, "_accepting", False) else
                "staging_session_unavailable" if session is None else
                "staging_application_not_running" if app_state != "running" else
                "staging_target_not_claimed")

    async def initialize(self) -> None:
        if self.staging.settings is None or not self.staging.settings.enabled:
            logger.info("[CompanionV2] 共享宿主已加载，等待账号与人格配置")
            return
        if not await self._try_start_host():
            self._schedule_host_start()

    async def _try_start_host(self) -> bool:
        try:
            readiness = self.staging.startup_readiness()
        except Exception as error:
            logger.warning("[CompanionV2] 保存的运行档暂不能启动 code=%s error_type=%s",
                           getattr(error, "code", "startup_readiness_failed"), type(error).__name__)
            return True
        if readiness in ("host_platform_unavailable", "host_account_unavailable"):
            return False
        if readiness is not None:
            logger.warning("[CompanionV2] 保存的运行档暂不能启动: %s", readiness)
            return True

        initialized_profile = False
        if self.staging.session is None:
            loaded = await self.staging.load_existing()
            if loaded.failure is not None:
                if loaded.failure.code in ("host_platform_unavailable", "host_account_unavailable"):
                    return False
                logger.warning("[CompanionV2] 已固定 profile 只读加载失败: %s — %s",
                               loaded.failure.code, loaded.failure.reason)
                return True
            if not loaded.unwrap()["loaded"]:
                # Account/persona mappings are sufficient to create the shared
                # installation. The old core-window binding was only a first-run bootstrap.
                initialized = await self.staging.initialize_profile()
                if initialized.failure is not None:
                    if initialized.failure.code in ("host_platform_unavailable", "host_account_unavailable"):
                        return False
                    logger.warning("[CompanionV2] staging profile 自动初始化失败: %s",
                                   initialized.failure.code)
                    return True
                initialized_profile = True

        started = await self.staging.start()
        if started.failure is not None:
            if started.failure.code in ("host_platform_unavailable", "host_account_unavailable"):
                return False
            logger.warning("[CompanionV2] staging profile 自动启动失败: %s", started.failure.code)
            return True
        logger.info("[CompanionV2] staging profile %s并开始接收入站消息",
                    "已自动初始化" if initialized_profile else "已加载")
        return True

    def _schedule_host_start(self) -> None:
        if self.staging._terminated:
            return
        session = self.staging.session
        if (self.staging._accepting and session is not None
                and session.application.state == "running"):
            return
        task = self._host_start_task
        if task is None or task.done():
            self._host_start_task = asyncio.create_task(
                self._wait_for_host_start(), name="companion:host-startup")

    async def _wait_for_host_start(self) -> None:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        delay = 0.5
        warned = False
        while not self.staging._terminated:
            try:
                finished = await self._try_start_host()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("[CompanionV2] 启动恢复失败 code=%s error_type=%s",
                               getattr(error, "code", "startup_failed"), type(error).__name__)
                return
            if finished:
                return
            if not warned and loop.time() - started_at >= 30:
                logger.warning("[CompanionV2] 正在等待配置的 OneBot 账号连接；连接就绪后会自动恢复运行")
                warned = True
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 5.0)

    @filter.on_platform_loaded()
    async def on_companion_platform_loaded(self) -> None:
        if self.staging.settings is not None and self.staging.settings.enabled:
            self._schedule_host_start()

    @filter.event_message_type(filter.EventMessageType.ALL, priority=240000)
    async def observe_companion_recall(self, event: AstrMessageEvent):
        result = await self.staging.receive_notice(event)
        if result is not None and result.failure is not None:
            logger.warning("[CompanionV2] 原生通知未受理: %s", result.failure.code)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=235000)
    async def observe_companion_group_early(self, event: AstrMessageEvent):
        """Prepare the authenticated group persona before reply admission.

        V1 captured group observations at a higher priority than its reply
        handlers.  Keep that ordering in V2 so a transient reply admission
        failure cannot prevent the group route from being established for the
        same event; this hook never sends or invokes a model.
        """
        if is_notice_event(event):
            return
        # AstrBot has already resolved command filters before invoking adapter
        # handlers.  Let another plugin's explicit group command continue down
        # the normal dispatch chain; observing it here would add work and make
        # the companion look like it owns a command it does not handle.
        if competing_command_handler(event, own_module=__name__) is not None:
            return
        result = await self.staging.observe_group_early(event)
        if result is not None and result.failure is not None:
            # Unconfigured routes and attachment-only messages are normal
            # fall-through cases.  Unexpected failures are useful for the
            # operator, but must not stop AstrBot's remaining handlers.
            if result.failure.code not in {"host_target_unavailable", "host_text_invalid", "host_group_media_unsupported",
                                           "host_not_claimed"}:
                logger.warning("[CompanionV2] 群消息早期预处理未受理: %s", result.failure.code)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=235000)
    async def receive_companion_binding(self, event: AstrMessageEvent):
        """First-run binding, handled before the staging target can claim anything.

        Runs after the notice listener and before ordinary plugin handlers:
        binding has to be seen while nothing is pinned -- ``claims``
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
                               priority=COMPANION_INTAKE_PRIORITY)
    async def receive_companion_message(self, event: AstrMessageEvent):
        if is_notice_event(event):
            return
        competing = competing_command_handler(event, own_module=__name__)
        if competing is not None:
            logger.debug("[CompanionV2] 放行其他插件指令 handler=%s",
                         getattr(competing, "handler_full_name", "unknown"))
            return
        # Ordinary listeners (e.g. prefix-free sign-in) run before intake.
        # A plugin may answer without stopping propagation; respect that reply.
        if getattr(event, "_has_send_oper", False):
            return
        if not self.staging.claims(event):
            # 不是本插件的目标：这条消息从来没有进入它的预期范围，回复与否都不是
            # 它的失败，既不写台账也不出日志——平台日志不该被别人的群消息刷屏。
            if self._claims_target(event):
                if self.staging_enabled():
                    # 目标确实是本插件的，只是这一刻没能受理（停机中、会话不在运行、
                    # 启动失败）。接不了这条本该由它回的消息，是预期未回。
                    self._record_no_reply(event, self._admission_reason(), stage="admission",
                                          origin_key=self._origin_key_for_event(event))
                return
            # 不属于任何目标（未绑定、也没配进来）的私聊：默认什么都不做，
            # 消息留给 AstrBot 自己的管线。只有配置里明确打开"婉拒陌生号"时，
            # 才由插件回一句固定文案，并关闭这一轮的默认模型回复。
            # 其他插件仍能继续检测这条消息。
            def observe_stranger_outcome(outcome):
                reason = outcome.get("reason_code", "stranger_notice_not_sent")
                if outcome.get("state") == "no_reply" and reason in STRANGER_NOTICE_FAILURES:
                    # 打开了婉拒、也确实该发：发不出去才是预期未回。
                    self._record_no_reply(event, reason, channel="private", stage="stranger_notice")
                elif outcome.get("state") == "replied":
                    logger.info("[CompanionV2] 陌生私聊婉拒已投递 event_ref=%s",
                                uuid4().hex)

            receipt = await refuse_stranger(self.staging, event, on_outcome=observe_stranger_outcome)
            if receipt is not None:
                suppress_default_reply(event)
            return
        try:
            mapping = await self.staging.persona_mapping_for_event(event)
        except Exception as error:
            logger.warning("[CompanionV2] 当前会话角色无法核验，交由 AstrBot 处理 error_type=%s",
                           type(error).__name__)
            return
        if mapping is None:
            return
        # V2 owns the default reply for this route, not the entire event.
        event_ref = uuid4().hex
        origin_key = self._origin_key_for_event(event)
        kind = getattr(getattr(getattr(event, "message_obj", None), "type", None), "value", None)
        channel = "private" if kind == "FriendMessage" else "group" if kind == "GroupMessage" else "unknown"
        group_admission = None
        if channel == "group":
            try:
                candidate = await self.staging.group_reply_candidate(event)
                if candidate.failure is not None:
                    if candidate.failure.code in GROUP_INPUT_PASSTHROUGH_FAILURES:
                        logger.info("[CompanionV2] 群消息组件暂不支持，交由 AstrBot 处理 event_ref=%s code=%s",
                                    event_ref, candidate.failure.code)
                        return
                    suppress_default_reply(event)
                    logger.warning("[CompanionV2] 群回复候选检查失败 event_ref=%s code=%s",
                                   event_ref, candidate.failure.code)
                    return
                group_admission = candidate.unwrap()
            except Exception as error:
                suppress_default_reply(event)
                logger.warning("[CompanionV2] 群回复候选检查异常 event_ref=%s error_type=%s",
                               event_ref, type(error).__name__)
                return
            if not group_admission["admitted"]:
                suppress_default_reply(event)
                return
        suppress_default_reply(event)
        logger.info("[CompanionV2] 接管入站 event_ref=%s channel=%s", event_ref, channel)
        try:
            reply_enabled = await self.staging.session_topology.reply_enabled(event)
        except Exception as error:
            self._record_no_reply(event, "session_reply_check_failed", origin_key=origin_key,
                                  channel=channel, event_ref=event_ref, turn=event_ref,
                                  code=type(error).__name__)
            logger.warning("[CompanionV2] 会话回复开关读取异常 event_ref=%s error_type=%s",
                           event_ref, type(error).__name__)
            return
        if not reply_enabled:
            self._record_no_reply(event, "session_reply_disabled", origin_key=origin_key,
                                  channel=channel, event_ref=event_ref, turn=event_ref)
            return
        await self._observe_session(event)
        refusal = {}
        try:
            result = await self.staging.receive_claimed(
                event, on_refusal=lambda receipt: refusal.update(receipt=receipt),
                group_admission=group_admission)
        except Exception as error:
            self._record_no_reply(event, "inbound_processing_failed", origin_key=origin_key,
                                  channel=channel, event_ref=event_ref, turn=event_ref,
                                  code=type(error).__name__)
            logger.error("[CompanionV2] 入站处理异常 event_ref=%s error_type=%s",
                         event_ref, type(error).__name__)
            return
        if result.failure is not None:
            refusal_receipt = refusal.get("receipt")
            if (result.failure.code == "private_access_dialogue_denied" and isinstance(refusal_receipt, dict)
                    and refusal_receipt.get("state") == "delivered"):
                logger.info("[CompanionV2] 私聊权限拒绝消息已投递 event_ref=%s",
                            event_ref)
            else:
                reason = ("private_access_refusal_not_sent"
                          if result.failure.code == "private_access_dialogue_denied"
                          else result.failure.code)
                self._record_no_reply(event, reason, origin_key=origin_key, channel=channel,
                                      event_ref=event_ref, stage="intake", turn=event_ref,
                                      code=result.failure.code)
        else:
            # 受理成功只是开了这一轮：沉默、生成失败与投递失败由 turn 对应的
            # batch 自己解析（[CompanionV2][reply] stage=... turn=<batch_ref>）。
            logger.info("[CompanionV2] 入站已受理 event_ref=%s batch_ref=%s",
                        event_ref, result.unwrap())

    async def _observe_session(self, event: AstrMessageEvent) -> None:
        try:
            await self.staging.session_topology.observe(event)
        except Exception:
            logger.warning("[CompanionV2] 会话目录更新失败", exc_info=True)

    @filter.on_llm_response()
    async def observe_companion_model_session(self, event: AstrMessageEvent, response):
        if response is not None and getattr(response, "role", None) == "assistant":
            await self._observe_session(event)

    @filter.on_decorating_result(priority=100000)
    async def observe_companion_context_reset(self, event: AstrMessageEvent):
        result = await self.staging.observe_context_reset(event)
        if result.failure is not None:
            logger.warning("[CompanionV2] 窗口临时上下文清理失败 code=%s", result.failure.code)
        elif result.unwrap().get("handled") and not result.unwrap().get("replayed"):
            logger.info("[CompanionV2] 窗口临时上下文已清理")

    async def terminate(self) -> None:
        startup_task = getattr(self, "_host_start_task", None)
        self._host_start_task = None
        if startup_task is not None and not startup_task.done():
            startup_task.cancel()
            try:
                await startup_task
            except asyncio.CancelledError:
                pass
        retire_reset_marker = getattr(self, "_retire_context_reset_marker", None)
        if retire_reset_marker is not None:
            retire_reset_marker()
            self._retire_context_reset_marker = None
        try:
            await self.staging.terminate()
            logger.info("[CompanionV2] 共享宿主已停止" if self.staging.runtime is None
                        else "[CompanionV2] 共享宿主正在收尾")
        finally:
            # Preserve the module graph during a deferred drain. Retire this
            # instance's path ownership once, even if an old stop is retried.
            if not getattr(self, "_imports_retired", False):
                retire_plugin_imports(_PLUGIN_ROOT, __name__, path_inserted=_CORE_PATH_INSERTED,
                                      entry_globals=globals(),
                                      preserve_modules=getattr(self.staging, "runtime", None) is not None)
                self._imports_retired = True
