"""
打字机字幕 overlay 相关逻辑。

该 mixin 只依赖主插件提供的 config、_safe_parse_int/_safe_parse_float
以及 Live2D 标签清理方法，避免把字幕实现继续堆在 main.py 中。
"""

import asyncio
import re
import uuid
from typing import Any

from astrbot.api import logger
from astrbot.api.message_components import Plain, Record

from .subtitle_server import SubtitleServer


class SubtitleMixin:
    """打字机字幕 overlay 的配置、清理和推送能力。"""

    def _is_subtitle_enabled(self) -> bool:
        return bool(self.config.get("subtitle_enabled", False))

    def _subtitle_scope(self) -> str:
        scope = str(self.config.get("subtitle_scope") or "bili_live").strip().lower()
        return scope if scope in {"all", "live", "bili_live", "twitch_live"} else "bili_live"

    def _event_should_push_subtitle(self, event: Any) -> bool:
        scope = self._subtitle_scope()
        if scope == "all":
            return True
        is_bili = bool(event.get_extra("bili_live_auto_reply"))
        is_twitch = bool(event.get_extra("twitch_live_auto_reply"))
        if scope == "live":
            return is_bili or is_twitch
        if scope == "twitch_live":
            return is_twitch
        return is_bili

    def _source_should_push_subtitle(self, source: str = "") -> bool:
        scope = self._subtitle_scope()
        if scope == "all":
            return True
        normalized = str(source or "").strip().lower()
        if normalized == "together_companion":
            checkers = []
            if scope in {"live", "bili_live"}:
                checkers.append(getattr(self, "_is_bili_live_running", None))
            if scope in {"live", "twitch_live"}:
                checkers.append(getattr(self, "_is_twitch_live_running", None))
            return any(callable(checker) and checker() for checker in checkers)
        if normalized in {"manual", "preview"}:
            return True
        if scope == "live":
            return normalized in {"bili_live", "twitch_live"}
        if scope == "twitch_live":
            return normalized == "twitch_live"
        return normalized in {"bili_live", "manual", "preview"}

    def _get_subtitle_style(self) -> dict[str, Any]:
        return {
            "typing_speed_ms": max(
                1, self._safe_parse_int(self.config.get("subtitle_typing_speed_ms"), 45)
            ),
            "hold_seconds": max(
                0.0,
                self._safe_parse_float(self.config.get("subtitle_hold_seconds"), 4.0),
            ),
            "font_size": max(
                12, self._safe_parse_int(self.config.get("subtitle_font_size"), 42)
            ),
            "font_weight": self._safe_parse_int(
                self.config.get("subtitle_font_weight"), 700
            ),
            "text_color": str(self.config.get("subtitle_text_color") or "#ffffff"),
            "stroke_color": str(self.config.get("subtitle_stroke_color") or "#111111"),
            "stroke_size": max(
                0, self._safe_parse_int(self.config.get("subtitle_stroke_size"), 4)
            ),
            "cursor_color": str(
                self.config.get("subtitle_cursor_color")
                or self.config.get("subtitle_text_color")
                or "#ffffff"
            ),
            "show_cursor": bool(self.config.get("subtitle_show_cursor", True)),
            "fade_out": bool(self.config.get("subtitle_fade_out", True)),
            "position": str(self.config.get("subtitle_position") or "bottom"),
            "padding": max(
                0, self._safe_parse_int(self.config.get("subtitle_padding"), 48)
            ),
            "max_width": max(
                200, self._safe_parse_int(self.config.get("subtitle_max_width"), 1100)
            ),
        }

    async def _start_subtitle_server_if_enabled(self) -> None:
        if not self._is_subtitle_enabled():
            return
        start_lock = getattr(self, "_subtitle_start_lock", None)
        if start_lock is None:
            start_lock = asyncio.Lock()
            self._subtitle_start_lock = start_lock
        async with start_lock:
            if not self._is_subtitle_enabled() or self._subtitle_server:
                return
            host = str(self.config.get("subtitle_host") or "127.0.0.1")
            port = self._safe_parse_int(self.config.get("subtitle_port"), 18081)
            server = SubtitleServer(host, port, self._get_subtitle_style())
            self._subtitle_server = server
            try:
                await server.start()
            except Exception as e:
                logger.error(f"[字幕] 启动字幕 overlay 失败: {e}")
                if self._subtitle_server is server:
                    self._subtitle_server = None

    async def _stop_subtitle_server(self) -> None:
        start_lock = getattr(self, "_subtitle_start_lock", None)
        if start_lock is None:
            start_lock = asyncio.Lock()
            self._subtitle_start_lock = start_lock
        async with start_lock:
            server = self._subtitle_server
            if server:
                await server.stop()
                if self._subtitle_server is server:
                    self._subtitle_server = None

    def _clean_subtitle_text(self, text: str) -> str:
        cleaned = text or ""
        if self.config.get("subtitle_strip_l2d_tags", True):
            _tags, cleaned = self._parse_l2d_tags(cleaned)
        if self.config.get("subtitle_strip_tts_blocks", True):
            cleaned = re.sub(r"(?is)<tts>.*?</tts>", "", cleaned)
        if self.config.get("subtitle_strip_html_tags", True):
            cleaned = re.sub(r"<[^>\n]{1,80}>", "", cleaned)
        cleaned = re.sub(r"\[CQ:[^\]]+\]", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        max_length = self._safe_parse_int(self.config.get("subtitle_max_length"), 120)
        if max_length > 0 and len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip() + "..."
        return cleaned

    async def _push_subtitle(self, text: str, *, source: str = "") -> None:
        if not self._is_subtitle_enabled():
            return
        if not self._source_should_push_subtitle(source):
            logger.debug(
                "[字幕] 当前 subtitle_scope=%s，已跳过不匹配的字幕来源。",
                self._subtitle_scope(),
            )
            return
        if not self._subtitle_server:
            await self._start_subtitle_server_if_enabled()
        if not self._subtitle_server:
            return
        cleaned = self._clean_subtitle_text(text)
        if cleaned:
            self._subtitle_server.style = self._get_subtitle_style()
            await self._subtitle_server.show(cleaned)

    async def _push_tts_audio_to_overlay(self, audio_path: str) -> bool:
        """把直播 TTS 音频交给字幕 overlay 页面播放。"""
        if not self._is_subtitle_enabled():
            return False
        path = str(audio_path or "").strip()
        if not path:
            return False
        if not self._subtitle_server:
            await self._start_subtitle_server_if_enabled()
        if not self._subtitle_server:
            return False
        try:
            self._subtitle_server.style = self._get_subtitle_style()
            return await self._subtitle_server.register_audio(uuid.uuid4().hex, path)
        except Exception as e:
            logger.warning(f"[字幕] 推送直播 TTS 音频到 overlay 失败: {e}")
            return False

    def _extract_subtitle_text_from_result(self, result) -> str:
        chain = getattr(result, "chain", None)
        if not chain:
            return ""

        has_voice = any(isinstance(comp, Record) for comp in chain)
        plain_parts: list[str] = []
        seen_voice = False

        for comp in chain:
            if isinstance(comp, Record):
                seen_voice = True
                continue
            if not isinstance(comp, Plain):
                continue
            text = (comp.text or "").strip()
            if not text:
                continue
            if has_voice and self.config.get("subtitle_voice_use_following_plain", True):
                if seen_voice:
                    plain_parts.append(text)
            else:
                plain_parts.append(text)

        if (
            has_voice
            and self.config.get("subtitle_voice_use_following_plain", True)
            and not plain_parts
        ):
            for comp in chain:
                if isinstance(comp, Plain) and (comp.text or "").strip():
                    text = comp.text.strip()
                    if not re.search(r"[\u3040-\u30ff]", text):
                        plain_parts.append(text)

        text = "\n".join(plain_parts).strip()
        return self._prefer_subtitle_display_text(text, voice_context=has_voice)

    def _prefer_subtitle_display_text(self, text: str, voice_context: bool = False) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"(?is)<tts>.*?</tts>", "", text).strip()
        cleaned = re.sub(r"\[[^\]\n]{1,40}\]", "", cleaned).strip()
        cleaned = re.sub(r"^[\s.。…!！?？,，、~～-]+", "", cleaned)

        prefer_chinese = voice_context or bool(
            self.config.get("subtitle_prefer_chinese_text", True)
        )
        if not prefer_chinese:
            return cleaned

        has_kana = bool(re.search(r"[\u3040-\u30ff]", cleaned))
        if has_kana and re.search(r"[\u4e00-\u9fff]", cleaned):
            kana_matches = list(re.finditer(r"[\u3040-\u30ff]", cleaned))
            tail = cleaned[kana_matches[-1].end() :]
            tail = re.sub(r"^[\s.。…!！?？,，、~～-]+", "", tail)
            first_tail_chinese = re.search(r"[\u4e00-\u9fff]", tail)
            if first_tail_chinese:
                return tail[first_tail_chinese.start() :].strip()

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        chinese_lines = [
            line for line in lines if re.search(r"[\u4e00-\u9fff]", line)
        ]
        if chinese_lines:
            best_lines = []
            for line in chinese_lines:
                first_chinese = re.search(r"[\u4e00-\u9fff]", line)
                if not first_chinese:
                    continue
                best_lines.append(line[first_chinese.start() :].strip())
            if best_lines:
                return "\n".join(best_lines)

        first_chinese = re.search(r"[\u4e00-\u9fff]", cleaned)
        if first_chinese:
            return cleaned[first_chinese.start() :].strip()

        if voice_context and re.search(r"[\u3040-\u30ff]", cleaned):
            return ""
        return cleaned
