# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger
from quart import request

from .page_config import PageConfigManager

PLUGIN_NAME = "astrbot_plugin_private_companion.live"
PAGE_API_PREFIX = f"/{PLUGIN_NAME}/page"

SMART_EXPRESSION_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "smart-happy-sparkling",
        "name": "开心星光",
        "emotion": "开心",
        "keywords": ("sparkling", "sparkle", "star", "星光", "星星", "闪", "闪亮", "高光", "キラ"),
        "preferred": ("EXP - Sparkling.exp3.json",),
        "trigger": 0.42,
        "release": 0.24,
        "priority": 34,
    },
    {
        "id": "smart-excited-exclamation",
        "name": "兴奋感叹",
        "emotion": "兴奋，惊讶",
        "keywords": ("exclamation", "surprise", "surprised", "shock", "感叹", "惊叹", "惊讶", "震惊", "叹号"),
        "preferred": ("EXP - Exclamation.exp3.json",),
        "trigger": 0.48,
        "release": 0.26,
        "priority": 40,
    },
    {
        "id": "smart-excited-round-eyes",
        "name": "圆眼高能",
        "emotion": "兴奋，惊讶",
        "keywords": ("round eyes", "roundeyes", "wide eyes", "wideeyes", "圆眼", "睁大", "豆豆眼"),
        "preferred": ("EXP - Round Eyes.exp3.json",),
        "trigger": 0.56,
        "release": 0.32,
        "priority": 36,
    },
    {
        "id": "smart-shy-blush",
        "name": "害羞脸红",
        "emotion": "害羞，喜欢",
        "keywords": ("face blush", "blush", "red face", "脸红", "害羞", "羞涩", "照れ"),
        "preferred": ("EXP - Face Blush.exp3.json",),
        "trigger": 0.42,
        "release": 0.24,
        "priority": 32,
    },
    {
        "id": "smart-love",
        "name": "喜爱爱心",
        "emotion": "喜欢，开心",
        "keywords": ("love", "heart", "affection", "喜欢", "喜爱", "爱心", "贴贴", "ハート"),
        "preferred": ("EXP - Love.exp3.json",),
        "trigger": 0.62,
        "release": 0.36,
        "priority": 38,
    },
    {
        "id": "smart-curious-question",
        "name": "好奇问号",
        "emotion": "好奇，疑惑",
        "keywords": ("question", "question mark", "疑问", "问号", "好奇", "？"),
        "preferred": ("EXP - Question.exp3.json",),
        "trigger": 0.42,
        "release": 0.24,
        "priority": 33,
    },
    {
        "id": "smart-confused-loading",
        "name": "困惑加载",
        "emotion": "困惑",
        "keywords": ("loading", "confused", "thinking", "加载", "读取", "思考", "困惑", "迷茫"),
        "preferred": ("EXP - Loading.exp3.json",),
        "trigger": 0.62,
        "release": 0.34,
        "priority": 34,
    },
    {
        "id": "smart-concerned-anxious",
        "name": "担心焦虑",
        "emotion": "担心，焦虑",
        "keywords": ("anxious", "anxiety", "nervous", "worried", "担心", "担忧", "焦虑", "紧张"),
        "preferred": ("EXP - Anxious.exp3.json",),
        "trigger": 0.45,
        "release": 0.26,
        "priority": 34,
    },
    {
        "id": "smart-sad-tear",
        "name": "难过泪光",
        "emotion": "难过",
        "keywords": ("tear", "tears", "泪", "眼泪", "泪光"),
        "preferred": ("EXP - Tear.exp3.json",),
        "trigger": 0.43,
        "release": 0.24,
        "priority": 34,
    },
    {
        "id": "smart-sad-cry",
        "name": "大哭",
        "emotion": "伤心",
        "keywords": ("cry", "crying", "sob", "哭", "大哭", "哭泣"),
        "preferred": ("EXP - Cry.exp3.json",),
        "trigger": 0.68,
        "release": 0.4,
        "priority": 38,
    },
    {
        "id": "smart-anger-angry",
        "name": "生气",
        "emotion": "生气",
        "keywords": ("angry", "anger", "mad", "furious", "生气", "愤怒", "怒", "恼火"),
        "preferred": ("EXP - Angry.exp3.json",),
        "negative": ("shadow", "nose shadow", "鼻影", "阴影"),
        "trigger": 0.42,
        "release": 0.24,
        "priority": 38,
    },
    {
        "id": "smart-anger-shadow",
        "name": "鼻影压迫",
        "emotion": "生气，愤怒",
        "keywords": ("nose shadow", "shadow", "dark", "黑脸", "脸黑", "鼻影", "阴影", "压迫"),
        "preferred": ("EXP - Nose Shadow.exp3.json",),
        "trigger": 0.56,
        "release": 0.32,
        "priority": 36,
    },
    {
        "id": "smart-tired",
        "name": "疲惫",
        "emotion": "疲惫",
        "keywords": ("tired", "sleepy", "sleep", "疲惫", "疲劳", "累", "困"),
        "preferred": ("EXP - Tired.exp3.json",),
        "trigger": 0.42,
        "release": 0.24,
        "priority": 30,
    },
)

SMART_SCENE_EXPRESSION_TEMPLATES: tuple[dict[str, Any], ...] = (
    {"id": "smart-pose-mic", "name": "麦克风", "keywords": ("mic", "microphone", "麦克风", "话筒"), "preferred": ("POSE - Mic.exp3.json",)},
    {"id": "smart-pose-heart", "name": "爱心", "keywords": ("heart", "love", "爱心", "比心"), "preferred": ("POSE - Heart.exp3.json",)},
    {"id": "smart-pose-lightsticks", "name": "荧光棒", "keywords": ("lightstick", "lightsticks", "荧光棒", "应援棒"), "preferred": ("POSE - Lightsticks.exp3.json",)},
    {"id": "smart-pose-coffee", "name": "咖啡", "keywords": ("coffee", "咖啡"), "preferred": ("POSE - Coffee.exp3.json",)},
    {"id": "smart-pose-phone", "name": "手机", "keywords": ("phone", "mobile", "手机"), "preferred": ("POSE - Phone.exp3.json",)},
    {"id": "smart-pose-money", "name": "撒钱", "keywords": ("money", "coin", "钱", "撒钱"), "preferred": ("POSE - Money.exp3.json",)},
    {"id": "smart-pose-book", "name": "书本", "keywords": ("book", "read", "书", "书本"), "preferred": ("POSE - Book.exp3.json",)},
    {"id": "smart-pose-bowl", "name": "碗", "keywords": ("bowl", "碗"), "preferred": ("POSE - Bowl.exp3.json",)},
    {"id": "smart-pose-game", "name": "游戏手", "keywords": ("game", "gaming", "controller", "游戏手", "手柄", "游戏"), "preferred": ("POSE - Game.exp3.json", "游戏手.exp3.json")},
    {"id": "smart-pose-draw", "name": "画手", "keywords": ("draw", "drawing", "pen", "paint", "画手", "绘画", "画笔"), "preferred": ("POSE - Draw.exp3.json", "画手.exp3.json")},
)


class LiveStreamCompanionPageApi:
    """AstrBot 插件拓展页面 API。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.config_manager = PageConfigManager(plugin, PLUGIN_NAME, logger)

    def register_routes(self) -> None:
        register = getattr(self.plugin.context, "register_web_api", None)
        if not callable(register):
            logger.debug("[B站直播] 当前 AstrBot 版本不支持拓展页 API 注册。")
            return
        routes = [
            ("/overview", self.get_overview, ["GET"], "Live Stream Companion overview"),
            ("/memory", self.get_memory, ["GET"], "Live Stream Companion live memory"),
            ("/config/schema", self.get_config_schema, ["GET"], "Live Stream Companion config schema"),
            ("/config/save", self.save_config, ["POST"], "Live Stream Companion save config"),
            ("/subtitle/preview", self.preview_subtitle, ["POST"], "Live Stream Companion subtitle preview"),
            ("/soullink/status", self.get_soullink_status, ["GET"], "Soullink Emotion status"),
            ("/soullink/control", self.soullink_control, ["POST"], "Soullink Emotion control"),
            ("/soullink/vts-parameters", self.get_soullink_vts_parameters, ["GET"], "Soullink VTS parameters"),
            ("/soullink/mapping", self.get_soullink_mapping, ["GET"], "Soullink advanced mapping"),
            ("/soullink/mapping/apply", self.apply_soullink_mapping, ["POST"], "Soullink mapping preview and save"),
            ("/control/start", self.start_live, ["POST"], "Live Stream Companion start live"),
            ("/control/stop", self.stop_live, ["POST"], "Live Stream Companion stop live"),
            ("/control/obs/status", self.get_obs_control_status, ["GET"], "Live Stream Companion OBS control status"),
            ("/control/obs/action", self.obs_control_action, ["POST"], "Live Stream Companion OBS control action"),
        ]
        for path, handler, methods, desc in routes:
            register(f"{PAGE_API_PREFIX}{path}", handler, methods, desc)

    async def get_overview(self) -> dict[str, Any]:
        try:
            plugin = self.plugin
            companion = plugin._get_v2_live_state_owner()
            store = plugin._v2_live_state_store(companion) if companion else {}
            events = list(getattr(plugin, "_bili_events", []))
            session_events = list(getattr(plugin, "_bili_session_events", []))
            twitch_events = list(getattr(plugin, "_twitch_events", []))
            recent_events = [
                (item, "bilibili") for item in events[-20:]
            ] + [
                (item, "twitch") for item in twitch_events[-20:]
            ]
            recent_events.sort(key=lambda row: float(getattr(row[0], "ts", 0.0) or 0.0), reverse=True)
            return self._ok(
                {
                    "plugin": {
                        "name": PLUGIN_NAME,
                        "display_name": "我会直播圈米养你",
                        "version": "1.8.1",
                    },
                    "live": self._live_summary(events, session_events),
                    "twitch": plugin._twitch_status(),
                    "obs_control": await self._obs_control_status(check_obs_ws=True),
                    "vts": self._vts_summary(),
                    "subtitle": self._subtitle_summary(),
                    "mouth_sync": self._mouth_sync_summary(),
                    "soullink": plugin._soullink_status(),
                    "auto_reply": self._auto_reply_summary(),
                    "companion": self._companion_summary(companion, store),
                    "memory": self._memory_summary(store),
                    "living_memory": plugin._live_memory_status(),
                    "integration": self._integration_summary(companion, store),
                    "viewers": self._viewer_summary(store),
                    "recent_events": [
                        self._event_payload(item, platform=platform)
                        for item, platform in recent_events[:20]
                    ],
                    "config": self._config_summary(),
                }
            )
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页概览读取失败: {exc}")
            return self._error(str(exc))

    async def get_memory(self) -> dict[str, Any]:
        try:
            companion = self.plugin._get_v2_live_state_owner()
            if companion is None:
                return self._ok({"available": False, "message": "V2 直播状态库尚未初始化。"})
            store = self.plugin._v2_live_state_store(companion)
            return self._ok(
                {
                    "available": True,
                    "overview": self.plugin._format_live_memory_overview(companion, limit=12),
                    "memory": self._memory_summary(store, detailed=True),
                    "viewers": self._viewer_summary(store, limit=50),
                }
            )
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页记忆读取失败: {exc}")
            return self._error(str(exc))

    async def get_config_schema(self) -> dict[str, Any]:
        try:
            return self._ok(self.config_manager.schema_payload())
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页配置结构读取失败: {exc}")
            return self._error(str(exc))

    async def save_config(self) -> dict[str, Any]:
        try:
            payload = await request.get_json(silent=True) or {}
            values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
            updates = self.config_manager.build_updates(values)
            if not updates:
                return self._ok({"message": "没有可保存的配置变更。", "values": self._config_summary()})

            persisted = await self.config_manager.apply_updates(updates)
            return self._ok(
                {
                    "message": "配置已保存。" if persisted else "配置已应用到当前运行实例，但未确认持久化。",
                    "persisted": persisted,
                    "values": self._config_summary(),
                }
            )
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页配置保存失败: {exc}")
            return self._error(str(exc))

    async def preview_subtitle(self) -> dict[str, Any]:
        try:
            payload = await request.get_json(silent=True) or {}
            text = str(payload.get("text") or "谢谢喜欢，今天也一起把直播间热起来吧。")
            server = getattr(self.plugin, "_subtitle_server", None)
            if server is None:
                return self._ok(
                    {
                        "sent": False,
                        "message": "字幕服务未运行，已在页面内播放本地预览。",
                        "style": self.plugin._get_subtitle_style(),
                    }
                )
            await self.plugin._push_subtitle(text, source="preview")
            return self._ok(
                {
                    "sent": True,
                    "message": "已发送到字幕 overlay，同时页面内播放预览。",
                    "style": self.plugin._get_subtitle_style(),
                }
            )
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页字幕预览失败: {exc}")
            return self._error(str(exc))

    async def get_soullink_status(self) -> dict[str, Any]:
        try:
            return self._ok(self.plugin._soullink_status())
        except Exception as exc:
            logger.warning(f"[Soullink] 拓展页状态读取失败: {exc}")
            return self._error(str(exc))

    async def soullink_control(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        action = self._single_line(payload.get("action"), 40)
        try:
            if action == "start":
                if not self.plugin._is_soullink_enabled():
                    return self._error("Soullink 尚未启用，请先在配置页开启并保存")
                success = await self.plugin._start_soullink_runtime()
                message = "Soullink 已启动。" if success else "Soullink 启动失败。"
            elif action == "stop":
                await self.plugin._stop_soullink_runtime()
                success = True
                message = "Soullink 已停止，原有 L2D 热键仍可使用。"
            elif action == "reset":
                runtime = getattr(self.plugin, "_soullink_runtime", None)
                success = bool(runtime and runtime.running and await runtime.reset())
                message = "情绪状态已回到中性。" if success else "Soullink 未运行。"
            elif action == "configure":
                runtime = getattr(self.plugin, "_soullink_runtime", None)
                if not runtime or not runtime.running:
                    return self._error("Soullink 未运行")
                style = self._single_line(payload.get("style"), 20)
                if style not in {"natural", "lively", "calm", "shy"}:
                    return self._error("未知动作风格")
                success = await runtime.configure(style=style)
                message = f"实时预览已切换到 {style} 风格。"
            elif action == "test":
                vad = payload.get("vad") if isinstance(payload.get("vad"), dict) else {}
                raw_emotion = self._single_line(payload.get("emotion") or "happy", 40)
                normalizer = getattr(self.plugin, "_normalize_soullink_emotion", None)
                emotion = (
                    normalizer(raw_emotion)
                    if callable(normalizer)
                    else raw_emotion.lower()
                ) or "happy"
                intent = {
                    "emotion": emotion,
                    "variant": self._single_line(payload.get("variant"), 60),
                    "intensity": max(0.0, min(1.0, self._float(payload.get("intensity"), 0.8))),
                    "vad": {
                        "valence": max(-1.0, min(1.0, self._float(vad.get("valence"), 0.0))),
                        "arousal": max(-1.0, min(1.0, self._float(vad.get("arousal"), 0.0))),
                        "dominance": max(-1.0, min(1.0, self._float(vad.get("dominance"), 0.0))),
                    },
                    "contextTags": ["page_test_bench"],
                    "sourceMessage": "Soullink 实时测试台",
                }
                success = await self.plugin._test_soullink_intent(intent)
                message = f"已触发 {raw_emotion or intent['emotion']} 表演。" if success else "Soullink 触发失败。"
            else:
                return self._error("未知 Soullink 控制动作")
            return self._ok(
                {
                    "success": success,
                    "message": message,
                    "status": self.plugin._soullink_status(),
                }
            )
        except Exception as exc:
            logger.warning(f"[Soullink] 拓展页控制失败: {exc}")
            return self._error(str(exc))

    async def get_soullink_vts_parameters(self) -> dict[str, Any]:
        try:
            catalog = await self._soullink_vts_catalog()
            if not catalog.get("connected"):
                return self._error("VTube Studio 未连接")
            return self._ok(
                {
                    **catalog,
                    "mapped": list(getattr(self.plugin, "_soullink_last_vts_parameters", [])),
                }
            )
        except Exception as exc:
            logger.warning(f"[Soullink] VTS 参数读取失败: {exc}")
            return self._error(str(exc))

    async def get_soullink_mapping(self) -> dict[str, Any]:
        try:
            mapping = self.plugin._soullink_mapping_editor_payload()
            catalog = await self._soullink_vts_catalog(allow_disconnected=True)
            mapping.update(catalog)
            mapping["validation"] = self._validate_soullink_mapping(
                mapping.get("activeMapping"),
                catalog.get("inputs", []),
                catalog.get("live2d", []),
                catalog.get("expressions", []),
            )
            return self._ok(mapping)
        except Exception as exc:
            logger.warning(f"[Soullink] 高级映射读取失败: {exc}")
            return self._error(str(exc))

    async def apply_soullink_mapping(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        action = self._single_line(payload.get("action"), 30).lower()
        try:
            persisted = False
            auto_summary = None
            catalog = await self._soullink_vts_catalog(
                allow_disconnected=True,
                refresh=action == "auto",
            )
            if action == "discard":
                self.plugin._clear_soullink_mapping_preview()
                message = "已撤销未保存的映射预览。"
            elif action == "reset":
                self.plugin._clear_soullink_mapping_preview()
                persisted = await self.config_manager.apply_updates(
                    {"soullink_vts_mapping": "{}"}
                )
                message = "已恢复跟随插件内置映射。"
            elif action == "auto":
                if not catalog.get("connected"):
                    return self._error("请先连接 VTube Studio 并加载模型，再使用智能映射")
                mapping, auto_summary = self._build_smart_soullink_mapping(catalog)
                self.plugin._set_soullink_mapping_preview(mapping)
                message = (
                    "智能映射已生成并进入预览："
                    f"{auto_summary['rules']} 条连续规则、"
                    f"{auto_summary['accessories']} 个情绪挂件、"
                    f"{auto_summary['scenes']} 个姿势候选。"
                )
            elif action in {"preview", "save"}:
                mapping = self.plugin._normalize_soullink_mapping(
                    payload.get("mapping"),
                    strict=True,
                )
                if action == "preview":
                    self.plugin._set_soullink_mapping_preview(mapping)
                    message = "高级映射预览已应用，120 秒内未保存会自动恢复。"
                else:
                    self.plugin._clear_soullink_mapping_preview()
                    serialized = json.dumps(
                        mapping,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    persisted = await self.config_manager.apply_updates(
                        {"soullink_vts_mapping": serialized}
                    )
                    message = "高级映射已保存。"
            else:
                return self._error("未知映射操作")

            refresh = getattr(self.plugin, "_refresh_soullink_mapping_outputs", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception as exc:
                    logger.debug(f"[Soullink] 映射更新后的即时刷新失败，将等待下一帧: {exc}")
            mapping_payload = self.plugin._soullink_mapping_editor_payload()
            mapping_payload.update(catalog)
            mapping_payload["persisted"] = persisted
            mapping_payload["message"] = message
            if auto_summary:
                mapping_payload["autoMapping"] = auto_summary
            mapping_payload["validation"] = self._validate_soullink_mapping(
                mapping_payload.get("activeMapping"),
                catalog.get("inputs", []),
                catalog.get("live2d", []),
                catalog.get("expressions", []),
            )
            return self._ok(mapping_payload)
        except Exception as exc:
            logger.warning(f"[Soullink] 高级映射操作失败: {exc}")
            return self._error(str(exc))

    async def _soullink_vts_catalog(
        self,
        *,
        allow_disconnected: bool = False,
        refresh: bool = True,
    ) -> dict[str, Any]:
        cached = getattr(self, "_soullink_catalog_cache", None)
        if (
            not refresh
            and isinstance(cached, dict)
            and time.monotonic() - self._float(cached.get("at")) < 30.0
            and bool(getattr(getattr(self.plugin, "vts", None), "is_authenticated", False))
        ):
            return cached.get("data", {})
        if not await self.plugin._check_and_reconnect():
            if allow_disconnected:
                input_setter = getattr(self.plugin, "_set_soullink_vts_input_catalog", None)
                if callable(input_setter):
                    try:
                        input_setter([])
                    except Exception as exc:
                        logger.debug(f"[Soullink] 清空 VTS 输入目录缓存失败: {exc}")
                expression_setter = getattr(
                    self.plugin,
                    "_set_soullink_vts_expression_catalog",
                    None,
                )
                if callable(expression_setter):
                    try:
                        expression_setter([])
                    except Exception as exc:
                        logger.debug(f"[Soullink] 清空 VTS 表情目录缓存失败: {exc}")
                return {
                    "connected": False,
                    "model": {},
                    "inputs": [],
                    "live2d": [],
                    "expressions": [],
                    "hotkeys": [],
                    "bindingsAvailable": False,
                }
            return {"connected": False}
        model_info, input_parameters, live2d_parameters = await asyncio.gather(
            self.plugin.vts.get_model_info(),
            self.plugin.vts.get_input_parameters(),
            self.plugin.vts.get_live2d_parameters(),
        )
        model_info = model_info if isinstance(model_info, dict) else {}
        input_parameters = input_parameters if isinstance(input_parameters, list) else []
        live2d_parameters = live2d_parameters if isinstance(live2d_parameters, list) else []
        async def optional_catalog(method_name: str) -> list[dict[str, Any]]:
            method = getattr(self.plugin.vts, method_name, None)
            if not callable(method):
                return []
            try:
                result = await method()
                return result if isinstance(result, list) else []
            except Exception as exc:
                logger.debug(f"[Soullink] VTS {method_name} 读取失败: {exc}")
                return []

        hotkeys, raw_expressions = await asyncio.gather(
            optional_catalog("get_hotkeys"),
            optional_catalog("get_expressions"),
        )
        expressions_by_target: dict[str, dict[str, Any]] = {}
        for raw_expression in raw_expressions:
            if not isinstance(raw_expression, dict):
                continue
            target = str(
                raw_expression.get("file")
                or raw_expression.get("expressionFile")
                or raw_expression.get("File")
                or ""
            ).strip()
            if not target:
                continue
            expressions_by_target[target] = {
                **raw_expression,
                "target": target,
                "label": str(
                    raw_expression.get("name")
                    or raw_expression.get("Name")
                    or target
                ).strip(),
                "toggleHotkeys": [],
            }
        for raw_hotkey in hotkeys:
            if not isinstance(raw_hotkey, dict):
                continue
            file_name = str(
                raw_hotkey.get("file")
                or raw_hotkey.get("expressionFile")
                or raw_hotkey.get("File")
                or ""
            ).strip()
            action = str(raw_hotkey.get("type") or raw_hotkey.get("Action") or "").lower()
            if not file_name or (action and "expression" not in action):
                continue
            item = expressions_by_target.setdefault(
                file_name,
                {
                    "target": file_name,
                    "label": file_name,
                    "toggleHotkeys": [],
                },
            )
            item.setdefault("toggleHotkeys", []).append(
                {
                    "id": str(raw_hotkey.get("hotkeyID") or raw_hotkey.get("HotkeyID") or ""),
                    "name": str(raw_hotkey.get("name") or raw_hotkey.get("Name") or "").strip(),
                }
            )
        expressions = list(expressions_by_target.values())
        bindings = self._soullink_model_bindings(model_info)
        bindings_available = bool(bindings)
        enriched_inputs: list[dict[str, Any]] = []
        for item in input_parameters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            enriched_inputs.append(
                {
                    **item,
                    "usedByModel": name in bindings if bindings_available else None,
                    "mappedOutputs": bindings.get(name, []),
                }
            )
        input_setter = getattr(self.plugin, "_set_soullink_vts_input_catalog", None)
        if callable(input_setter):
            input_setter(enriched_inputs)
        setter = getattr(self.plugin, "_set_soullink_vts_expression_catalog", None)
        if callable(setter):
            setter(expressions)
        catalog = {
            "connected": True,
            "model": {
                "loaded": bool(model_info.get("modelLoaded")),
                "id": str(model_info.get("modelID") or ""),
                "name": str(model_info.get("modelName") or ""),
                "vtsModelName": str(model_info.get("vtsModelName") or ""),
            },
            "inputs": enriched_inputs,
            "live2d": live2d_parameters,
            "expressions": expressions,
            "hotkeys": hotkeys,
            "bindingsAvailable": bindings_available,
        }
        self._soullink_catalog_cache = {"at": time.monotonic(), "data": catalog}
        return catalog

    def _soullink_model_bindings(
        self,
        model_info: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        vts_model_name = str(model_info.get("vtsModelName") or "").strip()
        model_id = str(model_info.get("modelID") or "").strip()
        if not vts_model_name:
            return {}
        cache = getattr(self, "_soullink_binding_cache", None)
        cache_key = f"{model_id}:{vts_model_name}"
        if isinstance(cache, dict) and cache.get("key") == cache_key:
            return cache.get("bindings", {})
        try:
            from .vts_discovery import get_install_info

            install_path = str(get_install_info().get("install_path") or "")
            models_root = (
                Path(install_path)
                / "VTube Studio_Data"
                / "StreamingAssets"
                / "Live2DModels"
            )
            model_path = next(models_root.glob(f"*/{vts_model_name}"), None)
            if model_path is None:
                return {}
            with model_path.open("r", encoding="utf-8") as handle:
                model_config = json.load(handle)
            settings = (
                model_config.get("ParameterSettings")
                if isinstance(model_config, dict)
                and isinstance(model_config.get("ParameterSettings"), list)
                else []
            )
            bindings: dict[str, list[dict[str, Any]]] = {}
            for setting in settings:
                if not isinstance(setting, dict):
                    continue
                input_name = str(setting.get("Input") or "").strip()
                output_name = str(setting.get("OutputLive2D") or "").strip()
                if not input_name or not output_name:
                    continue
                bindings.setdefault(input_name, []).append(
                    {
                        "id": output_name,
                        "inputMin": self._float(setting.get("InputRangeLower")),
                        "inputMax": self._float(setting.get("InputRangeUpper")),
                        "outputMin": self._float(setting.get("OutputRangeLower")),
                        "outputMax": self._float(setting.get("OutputRangeUpper")),
                        "smoothing": self._float(setting.get("Smoothing")),
                        "clampInput": bool(setting.get("ClampInput", False)),
                        "clampOutput": bool(setting.get("ClampOutput", False)),
                    }
                )
            self._soullink_binding_cache = {"key": cache_key, "bindings": bindings}
            return bindings
        except Exception as exc:
            logger.debug(f"[Soullink] 读取本地 VTS 模型映射失败: {exc}")
            return {}

    def _build_smart_soullink_mapping(
        self,
        catalog: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        default_mapping = self.plugin._normalize_soullink_mapping({})
        inputs = catalog.get("inputs") if isinstance(catalog.get("inputs"), list) else []
        input_by_name = {
            str(item.get("name") or "").strip(): item
            for item in inputs
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        rules: list[dict[str, Any]] = []
        for rule in default_mapping.get("rules", []):
            if not isinstance(rule, dict):
                continue
            target = str(rule.get("target") or "").strip()
            if input_by_name and target not in input_by_name:
                continue
            next_rule = dict(rule)
            if target in input_by_name:
                self._fit_smart_rule_to_input(next_rule, input_by_name[target])
            rules.append(next_rule)

        expressions = (
            catalog.get("expressions")
            if isinstance(catalog.get("expressions"), list)
            else []
        )
        accessories, unmatched = self._smart_soullink_expression_accessories(expressions)
        scene_groups = self._smart_soullink_scene_groups(expressions)
        mapping = {
            "version": 2,
            "composites": default_mapping.get("composites") or {},
            "rules": rules,
            "emotionAccessories": accessories,
            "sceneGroups": scene_groups,
        }
        normalized = self.plugin._normalize_soullink_mapping(mapping, strict=True)
        summary = {
            "rules": len(normalized.get("rules") or []),
            "accessories": len(normalized.get("emotionAccessories") or []),
            "sceneGroups": len(normalized.get("sceneGroups") or []),
            "scenes": sum(
                len(group.get("scenes") or [])
                for group in normalized.get("sceneGroups") or []
                if isinstance(group, dict)
            ),
            "unmatchedExpressions": unmatched[:8],
        }
        return normalized, summary

    def _fit_smart_rule_to_input(
        self,
        rule: dict[str, Any],
        input_meta: dict[str, Any],
    ) -> None:
        minimum = self._float(input_meta.get("min"), self._float(rule.get("outputMin"), -1.0))
        maximum = self._float(input_meta.get("max"), self._float(rule.get("outputMax"), 1.0))
        if minimum > maximum:
            minimum, maximum = maximum, minimum

        def clamp(value: Any) -> float:
            return max(minimum, min(maximum, self._float(value, 0.0)))

        for field in ("outputMin", "outputNeutral", "outputMax"):
            rule[field] = clamp(rule.get(field))
        current = input_meta.get("value", input_meta.get("defaultValue"))
        try:
            neutral = float(current)
        except (TypeError, ValueError):
            return
        if minimum <= neutral <= maximum:
            rule["outputNeutral"] = neutral

    def _smart_soullink_expression_accessories(
        self,
        expressions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        accessories: list[dict[str, Any]] = []
        unmatched: list[str] = []
        used_targets: set[str] = set()
        for template in SMART_EXPRESSION_TEMPLATES:
            expression = self._find_smart_expression_match(
                expressions,
                template,
                used_targets,
                threshold=10,
            )
            if not expression:
                unmatched.append(str(template.get("name") or template.get("id")))
                continue
            target = self._catalog_expression_target(expression)
            used_targets.add(target)
            accessories.append(
                {
                    "id": template["id"],
                    "name": f"智能映射 {template['name']}",
                    "enabled": True,
                    "emotion": template["emotion"],
                    "targetType": "expression",
                    "target": target,
                    "triggerThreshold": template["trigger"],
                    "releaseThreshold": template["release"],
                    "fadeIn": 0.16,
                    "fadeOut": 0.34,
                    "priority": template["priority"],
                    "minHold": 0.45,
                    "cooldown": 0.12,
                    "debounceIn": 0.04,
                    "debounceOut": 0.1,
                }
            )
        return accessories, unmatched

    def _smart_soullink_scene_groups(
        self,
        expressions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scenes = [
            {
                "id": "smart-pose-none",
                "name": "无道具",
                "conditions": [],
                "matchMode": "all",
                "priority": 0,
                "enterDelay": 0.0,
                "exitDelay": 0.0,
                "minHold": 0.0,
                "values": [],
            }
        ]
        used_targets: set[str] = set()
        for template in SMART_SCENE_EXPRESSION_TEMPLATES:
            expression = self._find_smart_expression_match(
                expressions,
                template,
                used_targets,
                threshold=10,
            )
            if not expression:
                continue
            target = self._catalog_expression_target(expression)
            used_targets.add(target)
            scenes.append(
                {
                    "id": template["id"],
                    "name": template["name"],
                    "conditions": [],
                    "matchMode": "all",
                    "priority": 0,
                    "enterDelay": 0.0,
                    "exitDelay": 0.0,
                    "minHold": 0.0,
                    "values": [
                        {
                            "targetType": "expression",
                            "target": target,
                            "value": 1.0,
                            "offValue": 0.0,
                            "active": True,
                        }
                    ],
                }
            )
        if len(scenes) <= 1:
            return []
        return [
            {
                "id": "smart-expression-poses",
                "name": "智能姿势道具",
                "enabled": False,
                "selectionMode": "manual",
                "defaultScene": "smart-pose-none",
                "activeScene": "smart-pose-none",
                "exclusive": True,
                "priority": 120,
                "fadeTime": 0.35,
                "scenes": scenes,
            }
        ]

    def _find_smart_expression_match(
        self,
        expressions: list[dict[str, Any]],
        template: dict[str, Any],
        used_targets: set[str],
        *,
        threshold: int,
    ) -> dict[str, Any] | None:
        preferred = {
            str(item or "").strip().lower()
            for item in template.get("preferred", ())
            if str(item or "").strip()
        }
        best_score = 0
        best_expression: dict[str, Any] | None = None
        for expression in expressions:
            if not isinstance(expression, dict):
                continue
            target = self._catalog_expression_target(expression)
            if not target or target in used_targets:
                continue
            text, compact = self._smart_expression_search_text(expression)
            score = 0
            target_lower = target.lower()
            if target_lower in preferred:
                score += 100
            elif any(Path(item).name.lower() == Path(target_lower).name for item in preferred):
                score += 60
            for keyword in template.get("keywords", ()):
                if self._smart_text_contains(text, compact, str(keyword)):
                    score += 12 if self._smart_text_contains(target_lower, target_lower.replace(" ", ""), str(keyword)) else 8
            for keyword in template.get("negative", ()):
                if self._smart_text_contains(text, compact, str(keyword)):
                    score -= 24
            if score > best_score:
                best_score = score
                best_expression = expression
        return best_expression if best_score >= threshold else None

    def _catalog_expression_target(self, expression: dict[str, Any]) -> str:
        return str(
            expression.get("target")
            or expression.get("file")
            or expression.get("expressionFile")
            or expression.get("File")
            or ""
        ).strip()

    def _smart_expression_search_text(self, expression: dict[str, Any]) -> tuple[str, str]:
        parts = [
            self._catalog_expression_target(expression),
            str(expression.get("label") or expression.get("name") or expression.get("Name") or ""),
        ]
        hotkeys = expression.get("toggleHotkeys")
        if isinstance(hotkeys, list):
            for hotkey in hotkeys:
                if isinstance(hotkey, dict):
                    parts.append(str(hotkey.get("name") or hotkey.get("id") or ""))
        text = " ".join(parts)
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        text = text.lower()
        text = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text, text.replace(" ", "")

    def _smart_text_contains(self, text: str, compact: str, keyword: str) -> bool:
        keyword = re.sub(r"([a-z])([A-Z])", r"\1 \2", keyword)
        keyword = keyword.lower()
        keyword = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", " ", keyword)
        keyword = re.sub(r"\s+", " ", keyword).strip()
        if not keyword:
            return False
        return keyword in text or keyword.replace(" ", "") in compact

    def _validate_soullink_mapping(
        self,
        mapping: Any,
        inputs: list[dict[str, Any]],
        live2d: list[dict[str, Any]],
        expressions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rules = mapping.get("rules") if isinstance(mapping, dict) and isinstance(mapping.get("rules"), list) else []
        input_by_name = {
            str(item.get("name") or ""): item
            for item in inputs
            if isinstance(item, dict) and item.get("name")
        }
        live2d_names = {
            str(item.get("name") or "")
            for item in live2d
            if isinstance(item, dict) and item.get("name")
        }
        expression_names = {
            str(
                item.get("target")
                or item.get("file")
                or item.get("expressionFile")
                or item.get("name")
                or ""
            )
            for item in (expressions or [])
            if isinstance(item, dict)
        }
        issues: list[dict[str, Any]] = []
        target_rules: dict[str, list[dict[str, Any]]] = {}
        active_count = 0
        for rule in rules:
            if not isinstance(rule, dict) or not bool(rule.get("enabled", True)):
                continue
            active_count += 1
            rule_id = str(rule.get("id") or "")
            target = str(rule.get("target") or "")
            target_rules.setdefault(target, []).append(rule)
            if not target:
                issues.append({"ruleId": rule_id, "level": "error", "message": "缺少 VTS 目标输入"})
                continue
            input_meta = input_by_name.get(target)
            if input_meta is None:
                if target in live2d_names:
                    issues.append(
                        {
                            "ruleId": rule_id,
                            "level": "error",
                            "message": f"{target} 是 Live2D 输出，不能通过 VTS API 注入；当前会安全跳过",
                        }
                    )
                elif inputs:
                    issues.append(
                        {
                            "ruleId": rule_id,
                            "level": "warning",
                            "message": f"{target} 不在当前 VTS 输入目录；当前模型会跳过，可保留给其他模型或自定义输入",
                        }
                    )
                continue
            if input_meta.get("usedByModel") is False:
                issues.append(
                    {
                        "ruleId": rule_id,
                        "level": "warning",
                        "message": f"{target} 可写，但当前模型没有绑定任何 Live2D 输出",
                    }
                )
            input_min = self._float(input_meta.get("min"), -1000000.0)
            input_max = self._float(input_meta.get("max"), 1000000.0)
            output_values = [
                self._float(rule.get("outputMin")),
                self._float(rule.get("outputNeutral")),
                self._float(rule.get("outputMax")),
            ]
            if min(output_values) < input_min or max(output_values) > input_max:
                issues.append(
                    {
                        "ruleId": rule_id,
                        "level": "warning",
                        "message": f"输出锚点超出 {target} 的 VTS 范围 {input_min:g} ~ {input_max:g}",
                    }
                )
        for target, duplicates in target_rules.items():
            if target and len(duplicates) > 1 and all(
                str(item.get("blend") or "replace") == "replace" for item in duplicates[1:]
            ):
                issues.append(
                    {
                        "ruleId": str(duplicates[-1].get("id") or ""),
                        "level": "warning",
                        "message": f"{target} 被多条 replace 规则占用，最后一条会覆盖前面的值",
                    }
                )
        accessories = mapping.get("emotionAccessories") if isinstance(mapping, dict) and isinstance(mapping.get("emotionAccessories"), list) else []
        scene_groups = mapping.get("sceneGroups") if isinstance(mapping, dict) and isinstance(mapping.get("sceneGroups"), list) else []
        active_accessories = 0
        active_scene_groups = 0
        for index, rule in enumerate(accessories):
            if not isinstance(rule, dict) or not bool(rule.get("enabled", True)):
                continue
            active_accessories += 1
            rule_id = str(rule.get("id") or f"accessory-{index + 1}")
            target = str(rule.get("target") or "").strip()
            target_type = str(rule.get("targetType") or "").strip().lower()
            if target_type not in {"parameter", "expression"}:
                target_type = "expression" if target.lower().endswith(".exp3.json") else "parameter"
            if not target:
                issues.append({"ruleId": rule_id, "level": "error", "message": "情绪挂件缺少目标"})
                continue
            if target_type == "expression":
                if expressions and target not in expression_names:
                    issues.append({"ruleId": rule_id, "level": "warning", "message": f"表情 {target} 不在当前 VTS 目录；可保留给其他模型"})
            elif target not in input_by_name:
                if target in live2d_names:
                    issues.append({"ruleId": rule_id, "level": "error", "message": f"{target} 是只读 Live2D 输出；请使用表情或 VTS 输入"})
                elif inputs:
                    issues.append({"ruleId": rule_id, "level": "warning", "message": f"{target} 不在当前 VTS 输入目录；当前模型会跳过"})
            trigger = self._float(rule.get("triggerThreshold"), 0.45)
            release = self._float(rule.get("releaseThreshold"), 0.28)
            if release > trigger:
                issues.append({"ruleId": rule_id, "level": "warning", "message": "释放阈值高于触发阈值，运行时会自动收窄为滞回范围"})
        for group_index, group in enumerate(scene_groups):
            if not isinstance(group, dict) or not bool(group.get("enabled", True)):
                continue
            active_scene_groups += 1
            group_id = str(group.get("id") or f"scene-group-{group_index + 1}")
            scenes = group.get("scenes") if isinstance(group.get("scenes"), list) else []
            scene_ids = {str(scene.get("id") or "") for scene in scenes if isinstance(scene, dict)}
            selection_mode = str(group.get("selectionMode") or "manual").strip().lower()
            if selection_mode in {"auto", "automatic", "rule"}:
                selection_mode = "rules"
            rules_mode = selection_mode == "rules"
            default_scene = str(group.get("defaultScene") or "")
            selected = str(
                (
                    group.get("activeScene")
                    if "activeScene" in group
                    else default_scene
                )
                or ""
            )
            if selected and selected not in scene_ids:
                issues.append({"ruleId": group_id, "level": "warning", "message": f"场景组未找到当前场景 {selected}，运行时会使用默认场景"})
            if rules_mode and not default_scene:
                issues.append({"ruleId": group_id, "level": "warning", "message": "自动场景组没有默认姿势，无规则命中时会关闭本组目标"})
            elif rules_mode and default_scene not in scene_ids:
                issues.append({"ruleId": group_id, "level": "warning", "message": "自动场景组的默认姿势无效，无规则命中时会关闭本组目标"})
            for scene_index, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    continue
                scene_id = str(scene.get("id") or f"scene-{scene_index + 1}")
                scene_name = str(scene.get("name") or scene_id)
                values = scene.get("values") if isinstance(scene.get("values"), list) else []
                expression_count = sum(
                    1
                    for value in values
                    if isinstance(value, dict)
                    and bool(value.get("active", True))
                    and str(value.get("target") or "").strip()
                    and (
                        str(value.get("targetType") or "").strip().lower() == "expression"
                        or (
                            not str(value.get("targetType") or "").strip()
                            and str(value.get("target") or "").strip().lower().endswith(".exp3.json")
                        )
                    )
                )
                if expression_count > 1:
                    issues.append(
                        {
                            "ruleId": scene_id,
                            "level": "warning",
                            "message": f"{scene_name} 会组合启用 {expression_count} 个模型表情，请确认模型支持叠加",
                        }
                    )

                conditions = scene.get("conditions") if isinstance(scene.get("conditions"), list) else []
                enabled_conditions = [
                    condition
                    for condition in conditions
                    if isinstance(condition, dict) and bool(condition.get("enabled", True))
                ]
                if rules_mode and scene_id != default_scene and not enabled_conditions:
                    issues.append(
                        {
                            "ruleId": scene_id,
                            "level": "warning",
                            "message": f"{scene_name} 没有自动条件，只能手动测试",
                        }
                    )
                known_condition_types = {"manual", "always", "emotion", "obs_scene", "stream_state"}
                for condition_index, condition in enumerate(enabled_conditions):
                    condition_id = f"{scene_id}:condition-{condition_index + 1}"
                    condition_type = str(condition.get("type") or "manual").strip().lower()
                    condition_value = condition.get("value")
                    if isinstance(condition_value, list):
                        has_value = any(str(item or "").strip() for item in condition_value)
                    else:
                        has_value = bool(str(condition_value or "").strip())
                    if condition_type not in known_condition_types:
                        issues.append(
                            {
                                "ruleId": condition_id,
                                "level": "warning",
                                "message": f"{scene_name} 使用未知条件 {condition_type or '空类型'}，当前版本不会自动命中",
                            }
                        )
                    elif condition_type in {"emotion", "obs_scene", "stream_state"} and not has_value:
                        issues.append(
                            {
                                "ruleId": condition_id,
                                "level": "warning",
                                "message": f"{scene_name} 有一条空条件，运行时不会命中",
                            }
                        )
                    elif rules_mode and scene_id != default_scene and condition_type == "manual":
                        issues.append(
                            {
                                "ruleId": condition_id,
                                "level": "warning",
                                "message": f"{scene_name} 的“仅手动测试”条件不会参与自动选择",
                            }
                        )
                    elif condition_type == "always" and scene_id != default_scene:
                        issues.append(
                            {
                                "ruleId": condition_id,
                                "level": "warning",
                                "message": f"{scene_name} 含“始终满足”条件，可能长期占用当前姿势",
                            }
                        )
                for value_index, value in enumerate(values):
                    if not isinstance(value, dict):
                        continue
                    target = str(value.get("target") or "").strip()
                    if not target:
                        issues.append({"ruleId": f"{group_id}:{scene_index + 1}:{value_index + 1}", "level": "warning", "message": "场景动作尚未选择目标，运行时会跳过"})
                        continue
                    target_type = str(value.get("targetType") or "").strip().lower()
                    if target_type not in {"parameter", "expression"}:
                        target_type = "expression" if target.lower().endswith(".exp3.json") else "parameter"
                    rule_id = f"{group_id}:{scene_index + 1}:{value_index + 1}"
                    if target_type == "expression":
                        if expressions and target not in expression_names:
                            issues.append({"ruleId": rule_id, "level": "warning", "message": f"场景表情 {target} 不在当前 VTS 目录；可保留给其他模型"})
                    elif target not in input_by_name:
                        if target in live2d_names:
                            issues.append({"ruleId": rule_id, "level": "error", "message": f"场景目标 {target} 是只读 Live2D 输出；请改用表情或 VTS 输入"})
                        elif inputs:
                            issues.append({"ruleId": rule_id, "level": "warning", "message": f"场景目标 {target} 不在当前 VTS 输入目录；当前模型会跳过"})
        return {
            "activeRules": active_count,
            "activeAccessories": active_accessories,
            "activeSceneGroups": active_scene_groups,
            "errors": sum(1 for item in issues if item["level"] == "error"),
            "warnings": sum(1 for item in issues if item["level"] == "warning"),
            "issues": issues,
        }

    async def start_live(self) -> dict[str, Any]:
        try:
            payload = await request.get_json(silent=True) or {}
            room_id = self._int(payload.get("room_id")) or self.plugin._get_config_room_id()
            message = await self.plugin._start_bili_live(room_id)
            return self._ok({"message": message})
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页启动监听失败: {exc}")
            return self._error(str(exc))

    async def stop_live(self) -> dict[str, Any]:
        try:
            message = await self.plugin._stop_bili_live()
            return self._ok({"message": message})
        except Exception as exc:
            logger.warning(f"[B站直播] 拓展页停止监听失败: {exc}")
            return self._error(str(exc))

    async def get_obs_control_status(self) -> dict[str, Any]:
        try:
            return self._ok(await self._obs_control_status(check_obs_ws=True))
        except Exception as exc:
            logger.warning(f"[B站直播] OBS 控制状态读取失败: {exc}")
            return self._error(str(exc))

    async def obs_control_action(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        action = self._single_line(payload.get("action"), 40)
        if not action:
            return self._error("缺少 OBS 控制动作")
        if not bool(self.plugin.config.get("obs_control_enabled", False)):
            return self._error("OBS 开播控制未启用")
        try:
            messages: list[str] = []
            if action == "open_obs":
                messages.append(self._start_configured_app("obs"))
            elif action == "open_l2dstudio":
                messages.append(self._start_configured_app("l2dstudio"))
            elif action == "start_apps":
                messages.append(self._start_configured_app("obs"))
                messages.append(self._start_configured_app("l2dstudio"))
            elif action == "check":
                pass
            elif action == "debug":
                messages.append(self._start_configured_app("obs"))
                messages.append(self._start_configured_app("l2dstudio"))
                wait_seconds = max(0, min(20, self._int(self.plugin.config.get("obs_startup_wait_seconds"), 3)))
                if wait_seconds:
                    await asyncio.sleep(wait_seconds)
                scene = self._single_line(self.plugin.config.get("obs_live_scene_name"), 120)
                if scene:
                    await self._obs_request("SetCurrentProgramScene", {"sceneName": scene})
                    messages.append(f"OBS 已切换到场景：{scene}")
                if bool(self.plugin.config.get("obs_debug_start_virtual_camera", True)):
                    try:
                        await self._obs_request("StartVirtualCam")
                        messages.append("OBS 虚拟摄像机已开启")
                    except Exception as exc:
                        messages.append(f"OBS 虚拟摄像机未重复开启：{self._single_line(exc, 80)}")
            elif action == "switch_scene":
                scene = self._single_line(payload.get("scene") or self.plugin.config.get("obs_live_scene_name"), 120)
                if not scene:
                    return self._error("未配置 OBS 场景名")
                await self._obs_request("SetCurrentProgramScene", {"sceneName": scene})
                messages.append(f"OBS 已切换到场景：{scene}")
            elif action == "start_virtual_camera":
                await self._obs_request("StartVirtualCam")
                messages.append("OBS 虚拟摄像机已开启")
            elif action == "stop_virtual_camera":
                await self._obs_request("StopVirtualCam")
                messages.append("OBS 虚拟摄像机已关闭")
            elif action == "start_record":
                await self._obs_request("StartRecord")
                messages.append("OBS 录制已开始")
            elif action == "stop_record":
                await self._obs_request("StopRecord")
                messages.append("OBS 录制已停止")
            elif action == "start_stream":
                if not bool(self.plugin.config.get("obs_allow_stream_start", False)):
                    return self._error("未允许从插件启动推流，请先开启“允许插件开始推流”")
                if not bool(payload.get("confirm")):
                    return self._error("开播需要二次确认")
                scene = self._single_line(payload.get("scene") or self.plugin.config.get("obs_live_scene_name"), 120)
                if scene:
                    await self._obs_request("SetCurrentProgramScene", {"sceneName": scene})
                    messages.append(f"OBS 已切换到场景：{scene}")
                await self._obs_request("StartStream")
                messages.append("OBS 推流已开始")
            elif action == "stop_stream":
                await self._obs_request("StopStream")
                messages.append("OBS 推流已停止")
            else:
                return self._error(f"未知 OBS 控制动作：{action}")
            return self._ok(
                {
                    "message": "；".join(item for item in messages if item) or "OBS 控制检查完成",
                    "obs_control": await self._obs_control_status(check_obs_ws=True),
                }
            )
        except Exception as exc:
            logger.warning(f"[B站直播] OBS 控制动作失败: {exc}")
            return self._error(str(exc))

    async def _obs_control_status(self, *, check_obs_ws: bool = True) -> dict[str, Any]:
        settings = self._obs_control_settings()
        obs_process = self._configured_app_process_status("obs")
        l2d_process = self._configured_app_process_status("l2dstudio")
        obs = {
            "configured": bool(settings.get("obs_exe_path")),
            "running": obs_process.get("running", False),
            "process": obs_process,
            "websocket": {
                "configured": bool(settings.get("obs_ws_host") and settings.get("obs_ws_port")),
                "connected": False,
                "error": "",
            },
            "current_scene": "",
            "streaming": False,
            "recording": False,
            "virtual_camera": False,
        }
        if check_obs_ws and obs["websocket"]["configured"] and obs["running"]:
            try:
                responses = await self._obs_requests(
                    [
                        ("GetVersion", {}),
                        ("GetCurrentProgramScene", {}),
                        ("GetStreamStatus", {}),
                        ("GetRecordStatus", {}),
                        ("GetVirtualCamStatus", {}),
                    ],
                    timeout=3.0,
                )
                obs["websocket"]["connected"] = True
                version = responses.get("GetVersion", {})
                obs["websocket"]["obs_version"] = self._single_line(version.get("obsVersion"), 40)
                obs["websocket"]["websocket_version"] = self._single_line(version.get("obsWebSocketVersion"), 40)
                scene = responses.get("GetCurrentProgramScene", {})
                obs["current_scene"] = self._single_line(scene.get("currentProgramSceneName"), 120)
                obs["streaming"] = bool((responses.get("GetStreamStatus", {}) or {}).get("outputActive"))
                obs["recording"] = bool((responses.get("GetRecordStatus", {}) or {}).get("outputActive"))
                obs["virtual_camera"] = bool((responses.get("GetVirtualCamStatus", {}) or {}).get("outputActive"))
            except Exception as exc:
                obs["websocket"]["error"] = self._single_line(exc, 180)
        return {
            "enabled": bool(self.plugin.config.get("obs_control_enabled", False)),
            "settings": settings,
            "obs": obs,
            "l2dstudio": {
                "configured": bool(settings.get("l2dstudio_exe_path")),
                "running": l2d_process.get("running", False),
                "process": l2d_process,
            },
            "safety": {
                "stream_start_allowed": bool(self.plugin.config.get("obs_allow_stream_start", False)),
                "stream_start_requires_confirm": True,
            },
        }

    def _obs_control_settings(self) -> dict[str, Any]:
        return {
            "obs_control_enabled": bool(self.plugin.config.get("obs_control_enabled", False)),
            "obs_exe_path": self._single_line(self.plugin.config.get("obs_exe_path"), 500),
            "l2dstudio_exe_path": self._single_line(self.plugin.config.get("l2dstudio_exe_path"), 500),
            "obs_ws_host": self._single_line(self.plugin.config.get("obs_ws_host") or "127.0.0.1", 120) or "127.0.0.1",
            "obs_ws_port": self._int(self.plugin.config.get("obs_ws_port"), 4455) or 4455,
            "obs_live_scene_name": self._single_line(self.plugin.config.get("obs_live_scene_name"), 120),
            "obs_startup_wait_seconds": max(0, min(20, self._int(self.plugin.config.get("obs_startup_wait_seconds"), 3))),
            "obs_debug_start_virtual_camera": bool(self.plugin.config.get("obs_debug_start_virtual_camera", True)),
            "obs_allow_stream_start": bool(self.plugin.config.get("obs_allow_stream_start", False)),
            "obs_ws_password_configured": bool(str(self.plugin.config.get("obs_ws_password") or "")),
        }

    def _configured_app_process_status(self, app: str) -> dict[str, Any]:
        raw_path = self._app_path(app)
        exe = Path(raw_path).expanduser() if raw_path else None
        name = exe.name if exe else ""
        exists = bool(exe and exe.exists())
        return {
            "path": str(exe) if exe else "",
            "name": name,
            "exists": exists,
            "running": self._process_name_running(name) if name else False,
        }

    def _app_path(self, app: str) -> str:
        if app == "obs":
            return str(self.plugin.config.get("obs_exe_path") or "").strip()
        if app == "l2dstudio":
            return str(self.plugin.config.get("l2dstudio_exe_path") or "").strip()
        return ""

    def _start_configured_app(self, app: str) -> str:
        raw_path = self._app_path(app)
        label = "OBS" if app == "obs" else "L2DStudio"
        if not raw_path:
            raise RuntimeError(f"未配置 {label} 程序路径")
        exe = Path(raw_path).expanduser()
        if not exe.exists():
            raise RuntimeError(f"{label} 程序不存在：{exe}")
        if self._process_name_running(exe.name):
            return f"{label} 已在运行"
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        return f"{label} 已启动"

    @staticmethod
    def _process_name_running(name: str) -> bool:
        process_name = str(name or "").strip()
        if not process_name:
            return False
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return process_name.casefold() in (result.stdout or "").casefold()
            result = subprocess.run(["pgrep", "-f", process_name], capture_output=True, text=True, timeout=3)
            return result.returncode == 0
        except Exception:
            return False

    async def _obs_request(self, request_type: str, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
        responses = await self._obs_requests([(request_type, request_data or {})], timeout=5.0)
        return responses.get(request_type, {})

    async def _obs_requests(self, requests: list[tuple[str, dict[str, Any]]], *, timeout: float = 5.0) -> dict[str, Any]:
        try:
            import websockets
        except Exception as exc:
            raise RuntimeError("缺少 websockets 依赖，无法连接 OBS WebSocket") from exc
        host = self._single_line(self.plugin.config.get("obs_ws_host") or "127.0.0.1", 120) or "127.0.0.1"
        port = self._int(self.plugin.config.get("obs_ws_port"), 4455) or 4455
        password = str(self.plugin.config.get("obs_ws_password") or "")
        uri = f"ws://{host}:{port}"
        responses: dict[str, Any] = {}
        try:
            connector = websockets.connect(uri, open_timeout=timeout, close_timeout=timeout)
        except TypeError:
            connector = websockets.connect(uri)
        async with connector as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            hello_data = hello.get("d") if isinstance(hello, dict) else {}
            auth = hello_data.get("authentication") if isinstance(hello_data, dict) else None
            identify_data: dict[str, Any] = {"rpcVersion": 1}
            if isinstance(auth, dict):
                if not password:
                    raise RuntimeError("OBS WebSocket 需要密码")
                secret = base64.b64encode(hashlib.sha256((password + str(auth.get("salt", ""))).encode("utf-8")).digest()).decode()
                identify_data["authentication"] = base64.b64encode(
                    hashlib.sha256((secret + str(auth.get("challenge", ""))).encode("utf-8")).digest()
                ).decode()
            await ws.send(json.dumps({"op": 1, "d": identify_data}, ensure_ascii=False))
            while True:
                packet = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if packet.get("op") == 2:
                    break
                if packet.get("op") == 9:
                    raise RuntimeError(self._single_line(packet.get("d"), 180) or "OBS WebSocket 鉴权失败")
            for index, (request_type, request_data) in enumerate(requests):
                request_id = f"live-stream-companion-{int(time.time() * 1000)}-{index}"
                await ws.send(
                    json.dumps(
                        {
                            "op": 6,
                            "d": {
                                "requestType": request_type,
                                "requestId": request_id,
                                "requestData": request_data or {},
                            },
                        },
                        ensure_ascii=False,
                    )
                )
                while True:
                    packet = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if packet.get("op") != 7:
                        continue
                    data = packet.get("d") if isinstance(packet.get("d"), dict) else {}
                    if data.get("requestId") != request_id:
                        continue
                    status = data.get("requestStatus") if isinstance(data.get("requestStatus"), dict) else {}
                    if not status.get("result", False):
                        comment = self._single_line(status.get("comment"), 180) or request_type
                        raise RuntimeError(f"OBS 请求失败：{comment}")
                    responses[request_type] = data.get("responseData") if isinstance(data.get("responseData"), dict) else {}
                    break
        return responses

    def _live_summary(self, events: list[Any], session_events: list[Any]) -> dict[str, Any]:
        plugin = self.plugin
        running = bool(plugin._is_bili_live_running())
        latest = events[-1] if events else None
        counts: dict[str, int] = {}
        viewers: dict[str, int] = {}
        for item in session_events:
            event_type = str(getattr(item, "event_type", "") or "")
            counts[event_type] = counts.get(event_type, 0) + 1
            username = plugin._single_line_text(getattr(item, "username", ""), 40)
            if username and username != "系统":
                viewers[username] = viewers.get(username, 0) + 1
        top_viewers = sorted(viewers.items(), key=lambda item: item[1], reverse=True)[:8]
        started = float(getattr(plugin, "_bili_session_started_at", 0.0) or 0.0)
        return {
            "enabled": bool(plugin._is_bili_live_enabled()),
            "running": running,
            "type": plugin._get_bili_live_type(),
            "backend": plugin._get_bili_web_backend(),
            "room_id": getattr(getattr(plugin, "_bili_live_client", None), "real_room_id", None) or plugin._get_config_room_id(),
            "cache_count": len(events),
            "session_count": len(session_events),
            "session_started_at": started,
            "duration_seconds": int(time.time() - started) if started else 0,
            "latest": self._event_payload(latest) if latest else None,
            "counts": counts,
            "top_viewers": [{"name": name, "count": count} for name, count in top_viewers],
            "last_error": getattr(getattr(plugin, "_bili_live_client", None), "last_error", "") or plugin._get_bili_live_task_error(),
        }

    def _vts_summary(self) -> dict[str, Any]:
        plugin = self.plugin
        return {
            "connected": bool(getattr(plugin, "_connected", False)),
            "url": getattr(getattr(plugin, "vts", None), "url", ""),
            "auto_connect": bool(plugin.config.get("auto_connect", True)),
            "auto_discover": bool(plugin.config.get("auto_discover", True)),
        }

    def _subtitle_summary(self) -> dict[str, Any]:
        server = getattr(self.plugin, "_subtitle_server", None)
        return {
            "enabled": bool(self.plugin.config.get("subtitle_enabled", False)),
            "running": server is not None,
            "url": getattr(server, "url", "") if server else "",
            "scope": self.plugin._subtitle_scope(),
        }

    def _mouth_sync_summary(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.plugin.config.get("mouth_sync_enabled", False)),
            "fps": self._int(self.plugin.config.get("mouth_sync_fps"), 30),
            "parameter": str(self.plugin.config.get("mouth_sync_open_parameter") or "MouthOpen"),
        }

    def _auto_reply_summary(self) -> dict[str, Any]:
        marks = list(getattr(self.plugin, "_bili_auto_reply_minute_marks", []))
        now = time.time()
        recent_marks = [item for item in marks if now - float(item) < 60]
        return {
            "enabled": bool(self.plugin.config.get("bili_live_auto_reply_enabled", False)),
            "mode": str(self.plugin.config.get("bili_live_auto_reply_mode") or "native"),
            "identity_mode": self.plugin._bili_live_reply_identity_mode(),
            "identity_label": self.plugin._bili_live_reply_identity_label(),
            "streamer": self.plugin._bili_live_streamer_identity(),
            "pending": len(getattr(self.plugin, "_bili_pending_reply_events", [])),
            "cooldown_seconds": self._float(self.plugin.config.get("bili_live_auto_reply_cooldown_seconds"), 12.0),
            "max_per_minute": self._int(self.plugin.config.get("bili_live_auto_reply_max_per_minute"), 6),
            "used_this_minute": len(recent_marks),
            "last_reply_at": float(getattr(self.plugin, "_bili_last_auto_reply_at", 0.0) or 0.0),
            "exempt_event_types": list(self.plugin._bili_auto_reply_priority_types()),
            "skip_rich_danmaku": bool(
                self.plugin.config.get(
                    "bili_live_auto_reply_skip_emoticon_danmaku", True
                )
            ),
            "air_guard": bool(self.plugin.config.get("bili_live_auto_reply_air_guard_enabled", True)),
            "air_guard_model": bool(self.plugin.config.get("bili_live_auto_reply_air_guard_model_enabled", True)),
            "air_guard_threshold": self._float(self.plugin.config.get("bili_live_auto_reply_air_guard_threshold"), 2.5),
            "force_full_tts": bool(self.plugin.config.get("bili_live_auto_reply_force_full_tts", True)),
            "sync_tts_subtitle": bool(self.plugin.config.get("bili_live_auto_reply_sync_tts_subtitle", True)),
            "local_playback": bool(self.plugin.config.get("bili_live_tts_local_playback_enabled", True)),
        }

    def _companion_summary(self, companion: Any | None, store: dict[str, Any]) -> dict[str, Any]:
        return {
            "available": companion is not None,
            "context_enabled": bool(self.plugin.config.get("live_relationship_context_enabled", self.plugin.config.get("private_companion_live_context_enabled", True))),
            "writeback_enabled": bool(self.plugin.config.get("live_state_writeback_enabled", self.plugin.config.get("private_companion_writeback_enabled", True))),
            "viewer_activity_enabled": bool(self.plugin.config.get("live_viewer_activity_enabled", self.plugin.config.get("private_companion_viewer_activity_enabled", True))),
            "summary_count": len(store.get("summaries") if isinstance(store.get("summaries"), list) else []),
        }

    def _integration_summary(self, companion: Any | None, store: dict[str, Any]) -> dict[str, Any]:
        living = self.plugin._live_memory_status()
        subtitle_server = getattr(self.plugin, "_subtitle_server", None)
        checks = [
            {
                "id": "bili_live",
                "label": "B站监听",
                "ok": bool(self.plugin._is_bili_live_running()),
                "note": "正在接收直播事件" if self.plugin._is_bili_live_running() else "未运行",
            },
            {
                "id": "twitch_live",
                "label": "Twitch 监听",
                "ok": bool(self.plugin._is_twitch_connected()),
                "note": (
                    f"已连接 {self.plugin._get_twitch_channel()}（只读）"
                    if self.plugin._is_twitch_connected()
                    else "重连中"
                    if self.plugin._is_twitch_live_running()
                    else "未运行"
                ),
            },
            {
                "id": "auto_reply",
                "label": "自动回应",
                "ok": bool(self.plugin.config.get("bili_live_auto_reply_enabled", False)),
                "note": str(self.plugin.config.get("bili_live_auto_reply_mode") or "native"),
            },
            {
                "id": "twitch_auto_reply",
                "label": "Twitch 自动回应",
                "ok": bool(self.plugin.config.get("twitch_auto_reply_enabled", False)),
                "note": "输出到绑定会话/OBS，不回写 Twitch",
            },
            {
                "id": "subtitle",
                "label": "打字机字幕",
                "ok": subtitle_server is not None,
                "note": getattr(subtitle_server, "url", "") if subtitle_server else "未运行",
            },
            {
                "id": "v2_live_state",
                "label": "V2 直播状态",
                "ok": companion is not None,
                "note": "关系资料与状态可用" if companion is not None else "状态库未初始化",
            },
            {
                "id": "live_memory",
                "label": "直播专用记忆",
                "ok": bool(self.plugin.config.get("live_memory_enabled", True)) and companion is not None,
                "note": f"{len(store.get('memory_items') if isinstance(store.get('memory_items'), list) else [])} 条可承接记忆",
            },
            {
                "id": "native_live_memory",
                "label": "V2 直播记忆库",
                "ok": bool(living.get("ready")),
                "note": living.get("message") or "",
            },
        ]
        return {
            "checks": checks,
            "ok_count": sum(1 for item in checks if item.get("ok")),
            "total": len(checks),
        }

    def _memory_summary(self, store: dict[str, Any], detailed: bool = False) -> dict[str, Any]:
        memory_items = store.get("memory_items") if isinstance(store.get("memory_items"), list) else []
        highlights = store.get("highlight_events") if isinstance(store.get("highlight_events"), list) else []
        open_threads = store.get("open_threads") if isinstance(store.get("open_threads"), list) else []
        summaries = store.get("summaries") if isinstance(store.get("summaries"), list) else []
        topics = store.get("topic_memory") if isinstance(store.get("topic_memory"), dict) else {}
        topic_rows = []
        for topic, item in topics.items():
            if not isinstance(item, dict):
                continue
            topic_rows.append(
                {
                    "topic": str(topic),
                    "count": self._int(item.get("count")),
                    "last_seen": self._float(item.get("last_seen")),
                    "samples": item.get("samples") if isinstance(item.get("samples"), list) else [],
                }
            )
        topic_rows.sort(key=lambda item: (item["count"], item["last_seen"]), reverse=True)
        payload = {
            "enabled": bool(self.plugin.config.get("live_memory_enabled", True)),
            "context_enabled": bool(self.plugin.config.get("live_memory_context_enabled", True)),
            "memory_count": len(memory_items),
            "highlight_count": len(highlights),
            "topic_count": len(topic_rows),
            "open_thread_count": len(open_threads),
            "summary_count": len(summaries),
            "topics": topic_rows[:12],
            "recent_items": memory_items[:8],
            "highlights": highlights[:8],
            "open_threads": open_threads[:8],
            "summaries": list(reversed(summaries[-5:])),
        }
        if detailed:
            payload["all_recent_items"] = memory_items[:30]
        return payload

    def _viewer_summary(self, store: dict[str, Any], limit: int = 20) -> dict[str, Any]:
        activity = store.get("viewer_activity") if isinstance(store.get("viewer_activity"), dict) else {}
        rows = []
        for key, item in activity.items():
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "key": str(key),
                    "display_name": self._single_line(item.get("display_name") or item.get("live_username"), 40),
                    "live_username": self._single_line(item.get("live_username"), 40),
                    "user_id": self._single_line(item.get("user_id"), 40),
                    "total_events": self._int(item.get("total_events")),
                    "event_counts": item.get("event_counts") if isinstance(item.get("event_counts"), dict) else {},
                    "recent_danmaku": item.get("recent_danmaku") if isinstance(item.get("recent_danmaku"), list) else [],
                    "last_seen": self._float(item.get("last_seen")),
                }
            )
        rows.sort(key=lambda item: (item["total_events"], item["last_seen"]), reverse=True)
        observations = store.get("viewer_observations") if isinstance(store.get("viewer_observations"), dict) else {}
        return {
            "count": len(rows),
            "candidate_count": len(observations),
            "items": rows[:limit],
        }

    def _config_summary(self) -> dict[str, Any]:
        return self.config_manager.summary()

    def _event_payload(self, event: Any, *, platform: str = "") -> dict[str, Any]:
        if event is None:
            return {}
        raw = getattr(event, "raw", None)
        raw_platform = raw.get("platform") if isinstance(raw, dict) else ""
        return {
            "platform": str(platform or raw_platform or "bilibili"),
            "type": str(getattr(event, "event_type", "") or ""),
            "dm_type": self._int(getattr(event, "dm_type", 0)),
            "username": self._single_line(getattr(event, "username", ""), 60),
            "content": self._single_line(getattr(event, "content", ""), 180),
            "display": self._single_line(event.display_text() if hasattr(event, "display_text") else "", 220),
            "ts": self._float(getattr(event, "ts", 0.0)),
        }

    @staticmethod
    def _single_line(value: Any, limit: int = 120) -> str:
        text = " ".join(str(value or "").strip().split())
        if limit > 0 and len(text) > limit:
            return text[:limit].rstrip() + "..."
        return text

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _ok(data: Any = None) -> dict[str, Any]:
        return {"success": True, "data": data, "ts": int(time.time())}

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"success": False, "error": str(message), "ts": int(time.time())}
