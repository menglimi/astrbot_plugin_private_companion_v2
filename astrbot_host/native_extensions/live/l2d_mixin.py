"""
自主 Live2D 标签和热键触发逻辑。

该 mixin 只承接标签解析、配置归一化和热键触发；AstrBot 的事件/命令入口
仍保留在 main.py，便于框架扫描和维护。
"""

import asyncio
import re
from typing import Any

from astrbot.api import logger

L2D_TAG_PATTERN = re.compile(
    r"<l2d\s*:\s*([^<>]+?)\s*/?>|<l2d>\s*([^<>]+?)\s*</l2d>",
    re.IGNORECASE,
)


class Live2DMixin:
    """Live2D 标签配置、解析与 VTS 热键触发能力。"""

    def _get_l2d_entries(self) -> list[dict[str, Any]]:
        entries = self.config.get("l2d_hotkeys", [])
        if not isinstance(entries, list):
            return []

        normalized: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("enabled", True):
                continue
            name = str(
                entry.get("name")
                or entry.get("expression_name")
                or entry.get("tag")
                or ""
            ).strip()
            tag = str(entry.get("tag") or name).strip()
            hotkey_id = str(entry.get("hotkey_id", "")).strip()
            if not tag or not hotkey_id:
                continue
            try:
                duration = max(0.0, float(entry.get("duration", 0) or 0))
            except (TypeError, ValueError):
                duration = 0.0
            normalized.append(
                {
                    "name": name or tag,
                    "tag": tag,
                    "hotkey_id": hotkey_id,
                    "description": str(entry.get("description", "")).strip(),
                    "duration": duration,
                    "release_after_duration": bool(
                        entry.get("release_after_duration", True)
                    ),
                }
            )
        return normalized

    def _l2d_entry_map(self) -> dict[str, dict[str, Any]]:
        return {entry["tag"].lower(): entry for entry in self._get_l2d_entries()}

    def _parse_l2d_tags(self, text: str) -> tuple[list[str], str]:
        tags: list[str] = []

        def collect(match: re.Match) -> str:
            raw = (match.group(1) or match.group(2) or "").strip()
            for item in re.split(r"[\s,，、|/]+", raw):
                tag = item.strip()
                if tag:
                    tags.append(tag)
            return ""

        cleaned = L2D_TAG_PATTERN.sub(collect, text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return tags, cleaned

    def _create_l2d_task(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._l2d_tasks.add(task)
        task.add_done_callback(self._l2d_tasks.discard)

    async def _trigger_l2d_tags(self, tags: list[str]) -> None:
        entries = self._l2d_entry_map()
        if not entries:
            return

        if not await self._check_and_reconnect():
            logger.warning("[VTS] 收到 L2D 标签，但 VTube Studio 未连接，已跳过触发")
            return

        for tag in tags:
            entry = entries.get(tag.lower())
            if not entry:
                logger.warning(f"[VTS] 未配置的 L2D 标签: {tag}")
                continue
            await self._trigger_l2d_entry(entry)

    async def _trigger_l2d_entry(self, entry: dict[str, Any]) -> None:
        hotkey_id = entry["hotkey_id"]
        try:
            await self.vts.trigger_hotkey(hotkey_id)
            logger.info(f"[VTS] L2D 标签 {entry['tag']} 已触发热键 {hotkey_id}")
        except Exception as e:
            logger.warning(f"[VTS] L2D 标签 {entry['tag']} 触发失败: {e}")
            return

        duration = entry["duration"]
        if duration > 0 and entry["release_after_duration"]:
            self._create_l2d_task(self._release_l2d_entry(entry, duration))

    async def _release_l2d_entry(self, entry: dict[str, Any], duration: float) -> None:
        try:
            await asyncio.sleep(duration)
            if not await self._check_and_reconnect():
                return
            await self.vts.trigger_hotkey(entry["hotkey_id"])
            logger.info(
                f"[VTS] L2D 标签 {entry['tag']} 持续 {duration:g} 秒后已再次触发热键"
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[VTS] L2D 标签 {entry['tag']} 自动结束失败: {e}")
