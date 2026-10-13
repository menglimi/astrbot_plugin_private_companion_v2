"""Merge real-time parameter layers before sending them to VTube Studio."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from astrbot.api import logger


class VTSParameterScheduler:
    """A latest-frame mixer shared by Soullink and TTS mouth sync."""

    def __init__(
        self,
        vts: Any,
        ensure_connection: Callable[[], Awaitable[bool]],
        *,
        fps: int = 30,
    ) -> None:
        self.vts = vts
        self.ensure_connection = ensure_connection
        self.fps = max(5, min(30, int(fps or 30)))
        self._layers: dict[str, dict[str, dict[str, float]]] = {}
        self._source_fps: dict[str, int] = {}
        self._layer_updated_at: dict[str, float] = {}
        self._layer_ttl: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self.frames_sent = 0
        self.last_sent_at = 0.0
        self.last_error = ""
        self.connection_retry_seconds = 4.0
        self._next_connection_attempt_at = 0.0
        self.connection_error = ""
        self.stale_layers_dropped = 0
        self.max_send_gap_seconds = 0.0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._layers.clear()
        self._source_fps.clear()
        self._layer_updated_at.clear()
        self._layer_ttl.clear()

    def set_fps(self, fps: int) -> None:
        self.fps = max(5, min(30, int(fps or 30)))
        self._wake.set()

    def set_source_fps(self, source: str, fps: int) -> None:
        self._source_fps[str(source)] = max(5, min(30, int(fps or self.fps)))
        self._wake.set()

    def set_layer(
        self,
        source: str,
        parameters: list[dict[str, Any]],
        *,
        ttl: float | None = None,
    ) -> None:
        source = str(source)
        normalized: dict[str, dict[str, float]] = {}
        for item in parameters:
            parameter_id = str(item.get("id") or "").strip()
            if not parameter_id:
                continue
            try:
                value = float(item.get("value", 0.0))
            except (TypeError, ValueError):
                continue
            row = {"value": value}
            if item.get("weight") is not None:
                try:
                    row["weight"] = max(0.0, min(1.0, float(item["weight"])))
                except (TypeError, ValueError):
                    pass
            normalized[parameter_id] = row
        if normalized:
            self._layers[source] = normalized
            self._layer_updated_at[source] = time.monotonic()
            if ttl is not None:
                self._layer_ttl[source] = max(0.1, float(ttl))
        else:
            self.clear_layer(source)
            return
        self._wake.set()

    def clear_layer(self, source: str) -> None:
        source = str(source)
        self._layers.pop(source, None)
        self._source_fps.pop(source, None)
        self._layer_updated_at.pop(source, None)
        self._layer_ttl.pop(source, None)
        self._wake.set()

    def effective_fps(self) -> int:
        active_rates = [
            self._source_fps[source]
            for source in self._layers
            if source in self._source_fps
        ]
        return max(active_rates, default=self.fps)

    def _drop_stale_layers(self) -> None:
        now = time.monotonic()
        stale = [
            source
            for source, ttl in self._layer_ttl.items()
            if source in self._layers
            and now - self._layer_updated_at.get(source, now) > ttl
        ]
        for source in stale:
            self._layers.pop(source, None)
            self._layer_updated_at.pop(source, None)
            self._layer_ttl.pop(source, None)
            self.stale_layers_dropped += 1
        if stale:
            self._wake.set()

    def merged_parameters(self) -> list[dict[str, float | str]]:
        self._drop_stale_layers()
        merged: dict[str, dict[str, float]] = {}
        # Mouth sync deliberately wins when both layers target the same input.
        for source in sorted(self._layers, key=lambda item: (item == "mouth", item)):
            merged.update(self._layers[source])
        return [{"id": key, **value} for key, value in merged.items()]

    async def flush(self) -> bool:
        parameters = self.merged_parameters()
        if not parameters:
            return False
        async with self._send_lock:
            now = time.monotonic()
            if not getattr(self.vts, "is_connected", False) and now < self._next_connection_attempt_at:
                return False
            try:
                connected = await self.ensure_connection()
            except Exception as exc:
                connected = False
                self.connection_error = str(exc)
            if not connected:
                self._next_connection_attempt_at = time.monotonic() + self.connection_retry_seconds
                if not self.connection_error:
                    self.connection_error = "VTube Studio 未连接"
                return False
            self._next_connection_attempt_at = 0.0
            self.connection_error = ""
            try:
                await self.vts.inject_parameters(parameters=parameters, mode="set")
                self.frames_sent += 1
                if self.last_sent_at:
                    self.max_send_gap_seconds = max(
                        self.max_send_gap_seconds,
                        time.time() - self.last_sent_at,
                    )
                self.last_sent_at = time.time()
                self.last_error = ""
                return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.debug(f"[VTS参数] 实时参数帧发送失败: {exc}")
                return False

    async def _run(self) -> None:
        while True:
            try:
                if not self._layers:
                    self._wake.clear()
                    await self._wake.wait()
                    continue
                started = time.monotonic()
                await self.flush()
                delay = max(
                    0.005,
                    1.0 / self.effective_fps() - (time.monotonic() - started),
                )
                self._wake.clear()
                # Layer producers may run at different rates. Keep only their
                # newest values and enforce one combined VTS frame interval.
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.debug(f"[VTS参数] 调度循环异常: {exc}")
                await asyncio.sleep(0.5)

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._task and not self._task.done()),
            "fps": self.effective_fps(),
            "source_fps": dict(self._source_fps),
            "layers": sorted(self._layers),
            "parameter_count": len(self.merged_parameters()),
            "frames_sent": self.frames_sent,
            "last_sent_at": self.last_sent_at,
            "last_error": self.last_error,
            "stale_layers_dropped": self.stale_layers_dropped,
            "max_send_gap_seconds": self.max_send_gap_seconds,
            "vts_connected": bool(
                getattr(
                    self.vts,
                    "is_authenticated",
                    getattr(self.vts, "is_connected", False),
                )
            ),
            "connection_error": self.connection_error,
            "retry_in": max(0.0, self._next_connection_attempt_at - time.monotonic()),
        }
