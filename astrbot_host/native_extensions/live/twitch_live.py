"""Twitch read-only chat listener built on the anonymous IRC endpoint."""

from __future__ import annotations

import asyncio
import re
import secrets
import ssl
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from astrbot.api import logger

from .bilibili_live import LiveDanmakuEvent

TWITCH_IRC_HOST = "irc.chat.twitch.tv"
TWITCH_IRC_PORT = 6697
TWITCH_ANON_PASSWORD = "SCHMOOPIIE"
TWITCH_CONNECT_TIMEOUT_SECONDS = 15.0
TWITCH_READ_TIMEOUT_SECONDS = 240.0

_PRIVMSG_RE = re.compile(
    r"^(?:@([^ ]+) )?:([^! ]+)!([^ ]+) PRIVMSG #([^ ]+) :(.*)$",
    re.DOTALL,
)
_TAG_ESCAPE_RE = re.compile(r"\\([sn:r\\])")
_TAG_ESCAPES = {"s": " ", ":": ";", "r": "\r", "n": "\n", "\\": "\\"}


def normalize_twitch_channel(value: str) -> str:
    """Accept a channel name or Twitch URL and return the IRC channel login."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text and text.lower().startswith(("twitch.tv/", "www.twitch.tv/")):
        text = "https://" + text
    if "://" in text:
        parsed = urlparse(text)
        if parsed.netloc.lower() not in {"twitch.tv", "www.twitch.tv"}:
            raise ValueError("Twitch 频道地址必须来自 twitch.tv")
        text = parsed.path.strip("/").split("/", 1)[0]
    channel = text.strip().lstrip("#@").lower()
    if not re.fullmatch(r"[a-z0-9_]{1,25}", channel):
        raise ValueError("Twitch 频道名只能包含英文字母、数字和下划线")
    return channel


def _unescape_tag(value: str) -> str:
    """Decode Twitch IRCv3 tag escapes without corrupting escaped slashes."""
    return _TAG_ESCAPE_RE.sub(lambda match: _TAG_ESCAPES[match.group(1)], str(value or ""))


def _parse_tags(tags_text: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for item in str(tags_text or "").split(";"):
        if not item:
            continue
        key, separator, value = item.partition("=")
        tags[key] = _unescape_tag(value) if separator else ""
    return tags


class TwitchIrcClient:
    """Anonymous Twitch IRC listener with quiet exponential reconnects."""

    def __init__(
        self,
        channel: str,
        on_event: Callable[[LiveDanmakuEvent], Awaitable[None]] | None,
        *,
        reconnect_interval: float = 5.0,
        max_reconnect_interval: float = 60.0,
        warning_interval: float = 60.0,
        debug_log: bool = False,
    ) -> None:
        self.channel = normalize_twitch_channel(channel)
        self.on_event = on_event
        self.reconnect_interval = max(1.0, float(reconnect_interval))
        self.max_reconnect_interval = max(
            self.reconnect_interval, float(max_reconnect_interval)
        )
        self.warning_interval = max(10.0, float(warning_interval))
        self.debug_log = bool(debug_log)
        self.last_error = ""
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._writer: Any | None = None
        self._is_connected = False
        self._ever_connected = False
        self._consecutive_failures = 0
        self._last_warning_at = 0.0
        self._last_connected_log_at = 0.0
        self._nickname = f"justinfan{secrets.randbelow(90000) + 10000}"

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    @property
    def is_connected(self) -> bool:
        return bool(self._is_connected)

    async def start(self) -> asyncio.Task:
        if not self.channel:
            raise ValueError("未配置 Twitch 频道名")
        if self.is_running:
            return self._task
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        stop_event = self._stop_event
        if stop_event:
            stop_event.set()
        writer = self._writer
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        task = self._task
        self._task = None
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            except asyncio.CancelledError:
                pass
        self._is_connected = False
        self._writer = None

    def _log_connection_failure(self, exc: Exception, retry_delay: float) -> None:
        now = time.monotonic()
        message = (
            f"[Twitch] 弹幕监听连接异常，将在 {retry_delay:g}s 后重连: {exc}"
        )
        if not self._last_warning_at or now - self._last_warning_at >= self.warning_interval:
            logger.warning(message)
            self._last_warning_at = now
        else:
            logger.debug(message)

    async def _wait_for_retry(self, delay: float) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            await asyncio.sleep(delay)
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _run(self) -> None:
        while not (self._stop_event and self._stop_event.is_set()):
            retry_delay = min(
                self.max_reconnect_interval,
                self.reconnect_interval * (2 ** min(self._consecutive_failures, 4)),
            )
            try:
                await self._connect_once()
                self._consecutive_failures = 0
                retry_delay = self.reconnect_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self._consecutive_failures += 1
                retry_delay = min(
                    self.max_reconnect_interval,
                    self.reconnect_interval
                    * (2 ** min(self._consecutive_failures - 1, 4)),
                )
                self._log_connection_failure(exc, retry_delay)
            if self._stop_event and self._stop_event.is_set():
                break
            await self._wait_for_retry(retry_delay)

    def _log_connected(self, recovered: bool) -> None:
        now = time.monotonic()
        should_log = not self._ever_connected or (
            recovered and now - self._last_connected_log_at >= self.warning_interval
        )
        if should_log:
            suffix = "，连接已恢复" if recovered else ""
            logger.info(f"[Twitch] 已连接频道 #{self.channel}（匿名只读 IRC{suffix}）")
            self._last_connected_log_at = now
        self._ever_connected = True

    async def _connect_once(self) -> None:
        context = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                TWITCH_IRC_HOST,
                TWITCH_IRC_PORT,
                ssl=context,
            ),
            timeout=TWITCH_CONNECT_TIMEOUT_SECONDS,
        )
        self._writer = writer
        self._is_connected = True
        recovered = bool(self.last_error)
        self.last_error = ""
        self._log_connected(recovered)
        try:
            writer.write(b"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
            writer.write(f"PASS {TWITCH_ANON_PASSWORD}\r\n".encode("utf-8"))
            writer.write(f"NICK {self._nickname}\r\n".encode("utf-8"))
            writer.write(f"JOIN #{self.channel}\r\n".encode("utf-8"))
            await writer.drain()

            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    line = await asyncio.wait_for(
                        reader.readline(), timeout=TWITCH_READ_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    writer.write(b"PING :tmi.twitch.tv\r\n")
                    await writer.drain()
                    continue
                if not line:
                    if self._stop_event and self._stop_event.is_set():
                        return
                    raise ConnectionError("Twitch IRC 连接被服务器关闭")
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if self.debug_log:
                    logger.debug(f"[Twitch] << {text}")
                if text.startswith("PING"):
                    payload = text.partition(":")[2] or "tmi.twitch.tv"
                    writer.write(f"PONG :{payload}\r\n".encode("utf-8"))
                    await writer.drain()
                    continue
                if text == ":tmi.twitch.tv RECONNECT":
                    raise ConnectionError("Twitch IRC 要求客户端重新连接")
                if " NOTICE " in text and "authentication failed" in text.lower():
                    raise ConnectionError("Twitch 匿名 IRC 认证失败")
                event = self._parse_line(text)
                if event is not None and self.on_event is not None:
                    try:
                        await self.on_event(event)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(f"[Twitch] 弹幕事件处理失败: {exc}")
        finally:
            self._is_connected = False
            if self._writer is writer:
                self._writer = None
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _parse_line(self, line: str) -> LiveDanmakuEvent | None:
        if not line or " PRIVMSG " not in line:
            return None
        match = _PRIVMSG_RE.match(line)
        if not match:
            return None
        tags_text, login, _identity, channel, message = match.groups()
        tags = _parse_tags(tags_text)
        display_name = tags.get("display-name") or login
        content = str(message or "").strip()
        is_action = content.startswith("\x01ACTION ") and content.endswith("\x01")
        if is_action:
            content = content[len("\x01ACTION ") : -1].strip()
        if not content:
            return None
        return LiveDanmakuEvent(
            event_type="danmaku",
            username=display_name,
            content=content,
            raw={
                "platform": "twitch",
                "channel": channel,
                "login": login,
                "user_id": tags.get("user-id", ""),
                "is_action": is_action,
                "tags": tags,
            },
        )
