"""Twitch runtime, moderation-free auto reply, and output integration."""

from __future__ import annotations
from .native_context import live_private_persona_prompt
from ..usage import tracked_text_chat

import asyncio
import re
import time
import uuid
from collections import deque
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain

from .bilibili_live import LiveDanmakuEvent
from .twitch_live import TwitchIrcClient, normalize_twitch_channel

KV_KEY_TWITCH_REPLY_SESSION = "twitch_live_reply_session"


class TwitchMixin:
    """Keep Twitch state and output handling separate from Bilibili."""

    def _init_twitch_runtime(self, cache_size: int = 200) -> None:
        twitch_cache_size = max(
            20,
            min(
                5000,
                self._safe_parse_int(
                    self.config.get("twitch_live_cache_size"), cache_size
                ),
            ),
        )
        self._twitch_client: TwitchIrcClient | None = None
        self._twitch_live_task: asyncio.Task | None = None
        self._twitch_channel_name = ""
        self._twitch_events: deque[LiveDanmakuEvent] = deque(maxlen=twitch_cache_size)
        self._twitch_pending_reply_events: deque[LiveDanmakuEvent] = deque(maxlen=50)
        self._twitch_auto_reply_task: asyncio.Task | None = None
        self._twitch_last_auto_reply_at = 0.0
        self._twitch_auto_reply_minute_marks: deque[float] = deque(maxlen=120)
        self._twitch_auto_reply_history: deque[dict[str, Any]] = deque(maxlen=30)
        self._twitch_session_started_at = 0.0
        self._twitch_session_id = ""
        self._twitch_summary_written_for_session = False

    def _is_twitch_enabled(self) -> bool:
        return bool(self.config.get("twitch_enabled", False))

    def _get_twitch_channel(self) -> str:
        try:
            return normalize_twitch_channel(self.config.get("twitch_channel") or "")
        except ValueError:
            return str(self.config.get("twitch_channel") or "").strip().lower().lstrip("#")

    def _is_twitch_live_running(self) -> bool:
        return bool(self._twitch_live_task and not self._twitch_live_task.done())

    def _is_twitch_connected(self) -> bool:
        return bool(self._twitch_client and self._twitch_client.is_connected)

    async def _start_twitch_live(self, channel: str = "") -> str:
        if not self._is_twitch_enabled():
            return "Twitch 直播功能未启用，请先在插件配置中开启 twitch_enabled。"
        raw_target = str(channel or "").strip() or self._get_twitch_channel()
        try:
            target = normalize_twitch_channel(raw_target)
        except ValueError as exc:
            return f"Twitch 频道名无效：{exc}"
        if not target:
            return "未配置 Twitch 频道名。请填写 twitch_channel 或使用 /twitch_live_start <频道名>。"
        if self._is_twitch_live_running():
            if self._twitch_channel_name == target:
                return f"Twitch 直播弹幕监听已在运行（频道：{target}）。"
            await self._stop_twitch_live(log=False)
        client = TwitchIrcClient(
            target,
            self._on_twitch_live_event,
            debug_log=bool(self.config.get("twitch_live_debug_log", False)),
        )
        self._twitch_client = client
        self._twitch_channel_name = target
        self._twitch_session_started_at = time.time()
        self._twitch_session_id = uuid.uuid4().hex[:24]
        self._twitch_summary_written_for_session = False
        self._twitch_events.clear()
        self._twitch_live_task = await client.start()
        logger.info("[Twitch] 已启动弹幕监听，频道：%s", target)
        return f"已启动 Twitch 直播弹幕监听（频道：{target}）"

    async def _stop_twitch_live(self, *, log: bool = True) -> str:
        client = self._twitch_client
        task = self._twitch_live_task
        self._twitch_client = None
        self._twitch_live_task = None
        auto_reply_task = self._twitch_auto_reply_task
        self._twitch_auto_reply_task = None
        if auto_reply_task and not auto_reply_task.done():
            auto_reply_task.cancel()
            await asyncio.gather(auto_reply_task, return_exceptions=True)
        self._twitch_pending_reply_events.clear()
        if client:
            await client.stop()
        elif task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._write_private_companion_live_summary(platform="twitch")
        self._twitch_session_started_at = 0.0
        self._twitch_session_id = ""
        self._twitch_events.clear()
        if log and (client or task):
            logger.info("[Twitch] 已停止弹幕监听")
        return "已停止 Twitch 直播弹幕监听。"

    async def _sync_twitch_runtime(self) -> None:
        """Apply Twitch page-config changes without restarting AstrBot."""
        enabled = self._is_twitch_enabled()
        channel = self._get_twitch_channel()
        running = self._is_twitch_live_running()
        if enabled and channel:
            if not running or self._twitch_channel_name != channel:
                if running:
                    await self._stop_twitch_live(log=False)
                await self._start_twitch_live(channel)
        elif running:
            await self._stop_twitch_live(log=False)

    async def _on_twitch_live_event(self, event: LiveDanmakuEvent) -> None:
        event.raw = {**event.raw, "platform": "twitch"}
        self._twitch_events.append(event)
        await self._write_private_companion_live_event(event)
        if self.config.get("twitch_live_log_events", True):
            logger.info("[Twitch] 弹幕 %s: %s", event.username, event.content)
        elif getattr(self, "_debug_mode", False):
            logger.debug("[Twitch] 弹幕 %s: %s", event.username, event.content)
        if self.config.get("twitch_auto_reply_enabled", False):
            self._twitch_pending_reply_events.append(event)
            self._schedule_twitch_auto_reply()

    def _schedule_twitch_auto_reply(self) -> None:
        if not self.config.get("twitch_auto_reply_enabled", False):
            return
        if self._twitch_auto_reply_task and not self._twitch_auto_reply_task.done():
            return
        self._twitch_auto_reply_task = asyncio.create_task(
            self._twitch_auto_reply_worker()
        )

    async def _wait_twitch_reply_window(self, cooldown: float) -> None:
        while True:
            remaining = cooldown - (time.time() - self._twitch_last_auto_reply_at)
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.25, remaining))

    def _twitch_reply_retry_after(self, max_per_minute: int) -> float:
        if max_per_minute <= 0:
            return 0.0
        now = time.time()
        while (
            self._twitch_auto_reply_minute_marks
            and now - self._twitch_auto_reply_minute_marks[0] >= 60
        ):
            self._twitch_auto_reply_minute_marks.popleft()
        if len(self._twitch_auto_reply_minute_marks) < max_per_minute:
            return 0.0
        return max(0.1, 60.0 - (now - self._twitch_auto_reply_minute_marks[0]))

    async def _twitch_auto_reply_worker(self) -> None:
        batch_drained = False
        try:
            cooldown = max(
                1.0,
                self._safe_parse_float(
                    self.config.get("twitch_auto_reply_cooldown_seconds"), 12.0
                ),
            )
            min_events = max(
                1,
                self._safe_parse_int(
                    self.config.get("twitch_auto_reply_min_events"), 1
                ),
            )
            max_events = max(
                min_events,
                self._safe_parse_int(
                    self.config.get("twitch_auto_reply_max_events"), 5
                ),
            )
            while self.config.get("twitch_auto_reply_enabled", False):
                if len(self._twitch_pending_reply_events) < min_events:
                    return
                await self._wait_twitch_reply_window(cooldown)
                max_per_minute = self._safe_parse_int(
                    self.config.get("twitch_auto_reply_max_per_minute"), 6
                )
                retry_after = self._twitch_reply_retry_after(max_per_minute)
                if retry_after:
                    logger.debug(
                        "[Twitch] 自动回应已达到每分钟上限，%.1fs 后重试。",
                        retry_after,
                    )
                    await asyncio.sleep(min(1.0, retry_after))
                    continue
                events = [
                    self._twitch_pending_reply_events.popleft()
                    for _ in range(min(max_events, len(self._twitch_pending_reply_events)))
                ]
                batch_drained = True
                if len(events) < min_events:
                    return
                should_reply, reason = await self._should_reply_to_twitch_events(events)
                if not should_reply:
                    logger.info(
                        "[Twitch] 读空气判定本批弹幕无需自动回应: reason=%s events=%s",
                        reason,
                        len(events),
                    )
                    continue
                await self._reply_to_twitch_live_events(events)
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Twitch] 自动回应 worker 异常: %s", exc)
        finally:
            self._twitch_auto_reply_task = None
            current_task = asyncio.current_task()
            is_cancelling = bool(
                current_task
                and callable(getattr(current_task, "cancelling", None))
                and current_task.cancelling()
            )
            if batch_drained and self._twitch_pending_reply_events and not is_cancelling:
                asyncio.get_running_loop().call_soon(self._schedule_twitch_auto_reply)

    def _twitch_auto_reply_rate_limited(self, _events: list[LiveDanmakuEvent]) -> bool:
        return bool(
            self._twitch_reply_retry_after(
                self._safe_parse_int(
                    self.config.get("twitch_auto_reply_max_per_minute"), 6
                )
            )
        )

    def _record_twitch_auto_reply_sent(
        self, events: list[LiveDanmakuEvent], reply_text: str
    ) -> None:
        now = time.time()
        self._twitch_last_auto_reply_at = now
        max_per_minute = self._safe_parse_int(
            self.config.get("twitch_auto_reply_max_per_minute"), 6
        )
        if max_per_minute > 0:
            self._twitch_auto_reply_minute_marks.append(now)
        self._twitch_auto_reply_history.append(
            {
                "ts": now,
                "reply": self._single_line_text(reply_text, 160),
                "events": [
                    {
                        "type": event.event_type,
                        "username": self._single_line_text(event.username, 40),
                        "content": self._single_line_text(event.content, 120),
                    }
                    for event in events[-5:]
                ],
            }
        )

    async def _get_twitch_reply_session(self) -> str:
        configured = str(
            self.config.get("twitch_auto_reply_session_id")
            or self.config.get("twitch_live_auto_reply_session_id")
            or ""
        ).strip()
        if configured:
            return configured
        bound = str(
            await self.get_kv_data(KV_KEY_TWITCH_REPLY_SESSION, "") or ""
        ).strip()
        if bound:
            return bound
        fallback = await self._get_bili_reply_session()
        return str(fallback or "").strip()

    async def _bind_twitch_reply_session(self, session_id: str) -> None:
        await self.put_kv_data(KV_KEY_TWITCH_REPLY_SESSION, session_id)

    def _twitch_silent_markers(self) -> set[str]:
        return {
            "你好", "在吗", "有人吗", "来了", "路过", "看看", "哈哈", "hh",
            "666", "顶", "早上好", "中午好", "晚上好", "晚安", "早", "贴贴",
            "围观", "吃瓜", "插眼", "沙发", "第一", "hi", "hello", "lol", "lmao",
        }

    def _twitch_air_guard_local_decision(
        self, events: list[LiveDanmakuEvent]
    ) -> dict[str, Any]:
        texts = [
            re.sub(r"\s+", " ", str(event.content or "").strip()).lower()
            for event in events
            if event.event_type == "danmaku" and str(event.content or "").strip()
        ]
        if not texts:
            return {"reply": False, "reason": "no_danmaku", "score": 0.0}
        compact = " ".join(texts)
        score = 0.0
        if len(compact) >= 10:
            score += 1.5
        if len({str(event.username or "") for event in events}) >= 2:
            score += 1.0
        if re.search(
            r"[?？]|吗|怎么|什么|为什么|多少|如何|能不能|可以吗|求|帮|\b(?:what|why|how|when|where|can|could)\b",
            compact,
        ):
            score += 3.0
        silent_hits = sum(1 for text in texts if text in self._twitch_silent_markers())
        if silent_hits:
            score -= 2.0 * silent_hits
        if len(compact.replace(" ", "")) < 3:
            score -= 1.0
        threshold = self._safe_parse_float(
            self.config.get("twitch_auto_reply_air_guard_threshold"), 2.0
        )
        return {
            "reply": score >= threshold,
            "reason": f"score={score:.1f}",
            "score": score,
        }

    async def _should_reply_to_twitch_events(
        self, events: list[LiveDanmakuEvent]
    ) -> tuple[bool, str]:
        if not self.config.get("twitch_auto_reply_air_guard_enabled", True):
            return True, "air_guard_disabled"
        decision = self._twitch_air_guard_local_decision(events)
        return bool(decision.get("reply")), str(decision.get("reason") or "unknown")

    def _build_twitch_live_prompt(self, events: list[LiveDanmakuEvent]) -> str:
        now = time.time()
        lines = [
            f"[{max(0, int(now - event.ts))}秒前] {event.username}: {event.content}"
            for event in events[-8:]
        ]
        identity = ""
        identity_builder = getattr(self, "_bili_live_reply_identity_prompt_line", None)
        if callable(identity_builder):
            identity = f"\n{identity_builder()}"
        return (
            "Twitch 直播间最近的观众弹幕：\n"
            + ("\n".join(lines) if lines else "（暂无弹幕）")
            + identity
            + "\n\n请用与观众相同的主要语言自然回应，像直播中的即时聊天。"
            "优先回答具体问题或反馈，不要逐条复读，不要声称已经在 Twitch 聊天室发言。"
            "只输出要发给观众的话，不要描述处理过程。"
        )

    async def _reply_to_twitch_live_events(
        self, events: list[LiveDanmakuEvent]
    ) -> bool:
        session_id = await self._get_twitch_reply_session()
        if not session_id:
            logger.warning(
                "[Twitch] 已收到弹幕，但未绑定自动回应会话。请在目标聊天发送 /twitch_live_bind_here。"
            )
            return False
        provider = None
        try:
            provider = self.context.get_using_provider(session_id)
        except Exception:
            try:
                provider = self.context.get_using_provider()
            except Exception:
                provider = None
        if not provider:
            logger.warning("[Twitch] 自动回应弹幕失败：未找到可用 LLM Provider")
            return False
        system_prompt = str(
            self.config.get("twitch_auto_reply_system_prompt")
            or "延续当前选定的人格和直播身份，结合最近的 Twitch 弹幕自然接话。使用观众主要使用的语言，优先回应具体问题或有意思的反馈；不逐条复读，也不必每条都回应。不要声称已在 Twitch 聊天室发言。"
        )
        persona_prompt = await live_private_persona_prompt(self, session_id)
        if persona_prompt:
            system_prompt += "\n\n" + persona_prompt
        auxiliary = [self._build_live_reply_experience_guard(events),
                     self._build_live_stream_memory_context(events),
                     self._build_native_live_relationship_context(events)]
        system_prompt += "\n\n" + "\n\n".join(part for part in auxiliary if part)
        try:
            response = await tracked_text_chat(
                self, provider, task="live_twitch_reply",
                prompt=self._build_twitch_live_prompt(events),
                system_prompt=system_prompt,
                session_id=f"{session_id}:twitch_live_auto_reply",
                persist=False,
            )
        except Exception as exc:
            logger.warning("[Twitch] LLM 自动回应失败: %s", exc)
            return False
        reply_text = self._extract_provider_text(response)
        reply_text = self._handle_soullink_response(reply_text)
        tags, reply_text = self._parse_l2d_tags(reply_text)
        if tags:
            self._create_l2d_task(self._trigger_l2d_tags(tags))
        reply_text = self._clean_auto_reply_text(reply_text)
        max_length = max(
            1,
            self._safe_parse_int(self.config.get("twitch_auto_reply_max_length"), 80),
        )
        if len(reply_text) > max_length:
            reply_text = reply_text[:max_length].rstrip() + "..."
        if not reply_text:
            return False
        return await self._send_twitch_reply(session_id, reply_text, events)

    async def _send_twitch_reply(
        self,
        session_id: str,
        reply_text: str,
        events: list[LiveDanmakuEvent],
    ) -> bool:
        """Send text/TTS to the bound session and the configured live outputs."""
        chain: list[Any] = [Plain(reply_text)]
        audio_path = ""
        if bool(self.config.get("twitch_auto_reply_tts_enabled", True)):
            try:
                payload = await self._build_bili_live_tts_payload(
                    session_id,
                    reply_text,
                    push_subtitle=False,
                    schedule_local_playback=False,
                )
            except Exception as exc:
                logger.warning("[Twitch] TTS 生成失败，回退纯文字: %s", exc)
                payload = {}
            if payload:
                records = list(payload.get("chain") or [])
                if records:
                    chain = [*records, Plain(reply_text)]
                audio_path = str(payload.get("audio_path") or "")
        sent = False
        try:
            await self.context.send_message(session_id, MessageChain(chain))
            sent = True
        except Exception as exc:
            logger.warning("[Twitch] 发送自动回应失败: %s", exc)
        try:
            await self._push_subtitle(reply_text, source="twitch_live")
        except Exception as exc:
            logger.warning("[Twitch] 推送 OBS 打字机字幕失败: %s", exc)
        if audio_path:
            await self._start_bili_live_mouth_sync_for_chain(chain)
            self._schedule_bili_live_tts_local_playback(audio_path)
        if sent:
            self._record_twitch_auto_reply_sent(events, reply_text)
            logger.info("[Twitch] 已自动回应弹幕 -> %s: %s", session_id, reply_text)
        return sent

    def _recent_twitch_events(self, limit: int = 8) -> list[LiveDanmakuEvent]:
        return list(self._twitch_events)[-max(1, min(50, int(limit or 8))) :]

    def _twitch_status(self) -> dict[str, Any]:
        client = self._twitch_client
        marks = list(self._twitch_auto_reply_minute_marks)
        now = time.time()
        return {
            "enabled": self._is_twitch_enabled(),
            "running": self._is_twitch_live_running(),
            "connected": self._is_twitch_connected(),
            "channel": self._twitch_channel_name or self._get_twitch_channel(),
            "cache_count": len(self._twitch_events),
            "pending": len(self._twitch_pending_reply_events),
            "session_started_at": self._twitch_session_started_at,
            "duration_seconds": int(now - self._twitch_session_started_at)
            if self._twitch_session_started_at
            else 0,
            "last_error": getattr(client, "last_error", "") if client else "",
            "auto_reply_enabled": bool(
                self.config.get("twitch_auto_reply_enabled", False)
            ),
            "last_reply_at": self._twitch_last_auto_reply_at,
            "used_this_minute": len([item for item in marks if now - item < 60]),
            "max_per_minute": self._safe_parse_int(
                self.config.get("twitch_auto_reply_max_per_minute"), 6
            ),
        }
