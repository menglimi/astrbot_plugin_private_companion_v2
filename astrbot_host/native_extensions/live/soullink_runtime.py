"""Async JSONL bridge to the vendored Soullink Emotion engine."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable

from astrbot.api import logger


class SoullinkRuntimeBridge:
    ENGINE_VERSION = "0.1.0-beta.1"

    def __init__(
        self,
        *,
        fps: int = 20,
        node_path: str = "",
        on_frame: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.fps = max(5, min(30, int(fps or 20)))
        self.node_path = str(node_path or "").strip()
        self.on_frame = on_frame
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self.started_at = 0.0
        self.frames_received = 0
        self.last_frame_at = 0.0
        self.last_snapshot: dict[str, Any] = {}
        self.last_error = ""
        self.engine_info: dict[str, Any] = {}
        self.resolved_node = ""

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.returncode is None and self._ready.is_set())

    @property
    def script_path(self) -> Path:
        return Path(__file__).with_name("soullink_bridge.mjs")

    async def start(self, options: dict[str, Any] | None = None) -> bool:
        if self.running:
            if options:
                await self.configure(**options)
            return True
        await self.stop()
        node = self.node_path or shutil.which("node") or ""
        if not node:
            self.last_error = "未找到 Node.js 18+，Soullink 已回退到原有 Live2D 热键模式。"
            return False
        if not self.script_path.is_file():
            self.last_error = f"Soullink 运行脚本不存在: {self.script_path}"
            return False
        self.resolved_node = node
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self._ready.clear()
            self.process = await asyncio.create_subprocess_exec(
                node,
                str(self.script_path),
                str(self.fps),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
            )
            self.started_at = time.time()
            self._reader_task = asyncio.create_task(self._read_stdout())
            self._stderr_task = asyncio.create_task(self._read_stderr())
            await asyncio.wait_for(self._ready.wait(), timeout=5.0)
            if options:
                await self.configure(**options)
            self.last_error = ""
            logger.info(f"[Soullink] Emotion engine {self.ENGINE_VERSION} 已启动")
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"[Soullink] 启动失败，继续使用原有 Live2D 链路: {exc}")
            await self.stop()
            return False

    async def stop(self) -> None:
        process = self.process
        if process and process.returncode is None:
            try:
                await self.send({"op": "shutdown"})
                await asyncio.wait_for(process.wait(), timeout=1.5)
            except Exception:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.5)
                except Exception:
                    process.kill()
                    await process.wait()
        current = asyncio.current_task()
        tasks = [task for task in (self._reader_task, self._stderr_task) if task and task is not current]
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.process = None
        self._reader_task = None
        self._stderr_task = None
        self._ready.clear()

    async def send(self, payload: dict[str, Any]) -> bool:
        process = self.process
        if not process or process.returncode is not None or not process.stdin:
            return False
        data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(data)
            await process.stdin.drain()
        return True

    async def trigger(self, intent: dict[str, Any]) -> bool:
        return await self.send({"op": "trigger", "intent": intent})

    async def react_to_text(self, text: str) -> bool:
        return await self.send({"op": "message", "text": str(text or "")[:1000]})

    async def reset(self) -> bool:
        return await self.send({"op": "reset"})

    async def configure(self, **options: Any) -> bool:
        return await self.send({"op": "configure", **options})

    async def _read_stdout(self) -> None:
        process = self.process
        if not process or not process.stdout:
            return
        try:
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self.last_error = f"Soullink 输出解析失败: {exc}"
                    continue
                message_type = message.get("type")
                if message_type == "ready":
                    self.engine_info = message
                    self._ready.set()
                elif message_type == "frame":
                    self.frames_received += 1
                    self.last_frame_at = time.time()
                    self.last_snapshot = message
                    if self.on_frame:
                        try:
                            self.on_frame(message)
                        except Exception as exc:
                            self.last_error = str(exc)
                            logger.debug(f"[Soullink] 帧回调失败: {exc}")
                elif message_type == "error":
                    self.last_error = str(message.get("error") or "Soullink 未知错误")
        except asyncio.CancelledError:
            raise
        finally:
            if process is self.process and process.returncode is not None:
                self._ready.clear()

    async def _read_stderr(self) -> None:
        process = self.process
        if not process or not process.stderr:
            return
        try:
            while True:
                raw = await process.stderr.readline()
                if not raw:
                    return
                text = raw.decode("utf-8", errors="replace").strip()
                if text:
                    self.last_error = text[:500]
                    logger.debug(f"[Soullink/Node] {text}")
        except asyncio.CancelledError:
            raise

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "engine": "@soullink-emotion/engine",
            "version": self.ENGINE_VERSION,
            "fps": self.fps,
            "node": self.resolved_node,
            "pid": self.process.pid if self.process and self.process.returncode is None else None,
            "uptime_seconds": max(0.0, time.time() - self.started_at) if self.running else 0.0,
            "frames_received": self.frames_received,
            "last_frame_at": self.last_frame_at,
            "last_error": self.last_error,
            "snapshot": self.last_snapshot,
        }
