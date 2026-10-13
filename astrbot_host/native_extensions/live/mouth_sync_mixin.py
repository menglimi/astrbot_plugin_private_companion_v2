"""
TTS 语音嘴型联动逻辑。

该 mixin 负责从语音结果中提取本地音频、生成响度包络，并驱动 VTS 参数。
"""

import asyncio
import math
import os
import re
from urllib.parse import unquote, urlparse
import wave

from astrbot.api import logger
from astrbot.api.message_components import Record


class MouthSyncMixin:
    """VTube Studio 嘴型参数联动能力。"""

    def _is_mouth_sync_enabled(self) -> bool:
        return bool(self.config.get("mouth_sync_enabled", False))

    def _create_mouth_sync_task(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._mouth_sync_tasks.add(task)
        task.add_done_callback(self._mouth_sync_tasks.discard)

    def _extract_record_audio_paths(self, result) -> list[str]:
        chain = getattr(result, "chain", None)
        if not chain:
            return []

        paths: list[str] = []
        for comp in chain:
            if not isinstance(comp, Record):
                continue
            for attr in ("file", "path", "url"):
                value = getattr(comp, attr, None)
                path = self._normalize_local_audio_path(value)
                if path and path not in paths:
                    paths.append(path)
        return paths

    def _normalize_local_audio_path(self, value) -> str:
        if not value:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"}:
            return ""
        if parsed.scheme == "file":
            text = unquote(parsed.path)
            if os.name == "nt" and re.match(r"^/[A-Za-z]:/", text):
                text = text[1:]
        return text if os.path.exists(text) else ""

    async def _start_mouth_sync_for_result(self, result) -> None:
        if not self._is_mouth_sync_enabled():
            return

        audio_paths = self._extract_record_audio_paths(result)
        if not audio_paths:
            logger.debug("[嘴型] 未找到可读取的本地语音文件，跳过嘴型联动")
            return
        if not await self._check_and_reconnect():
            logger.debug("[嘴型] VTS 未连接，跳过语音嘴型联动")
            return

        for audio_path in audio_paths[:1]:
            self._create_mouth_sync_task(self._run_mouth_sync(audio_path))

    async def _run_mouth_sync(self, audio_path: str) -> None:
        try:
            envelope, interval = await asyncio.to_thread(
                self._build_mouth_sync_envelope, audio_path
            )
            if not envelope:
                logger.debug(f"[嘴型] 暂不支持或无法读取音频文件: {audio_path}")
                return
            await self._drive_mouth_parameters(envelope, interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[嘴型] 语音嘴型联动失败: {e}")
        finally:
            await self._reset_mouth_parameters()

    async def _run_mouth_sync_envelope(self, envelope: list[float], interval: float) -> None:
        try:
            await self._drive_mouth_parameters(envelope, interval)
        finally:
            await self._reset_mouth_parameters()

    def _build_mouth_sync_envelope(self, audio_path: str) -> tuple[list[float], float]:
        fps = max(5, min(60, self._safe_parse_int(self.config.get("mouth_sync_fps"), 30)))
        gain = max(
            0.1, self._safe_parse_float(self.config.get("mouth_sync_gain"), 1.6)
        )
        noise_gate = max(
            0.0, self._safe_parse_float(self.config.get("mouth_sync_noise_gate"), 0.03)
        )
        with wave.open(audio_path, "rb") as wav:
            channels = max(1, wav.getnchannels())
            sample_width = wav.getsampwidth()
            rate = max(1, wav.getframerate())
            frames_per_step = max(1, int(rate / fps))
            max_amplitude = float((1 << (sample_width * 8 - 1)) - 1)
            values: list[float] = []

            while True:
                frame_bytes = wav.readframes(frames_per_step)
                if not frame_bytes:
                    break
                rms = self._pcm_rms(frame_bytes, sample_width, channels)
                value = min(1.0, max(0.0, (rms / max_amplitude) * gain))
                if value < noise_gate:
                    value = 0.0
                values.append(value)

        return values, 1.0 / fps

    def _pcm_rms(self, data: bytes, sample_width: int, channels: int) -> float:
        if sample_width not in {1, 2, 3, 4} or not data:
            return 0.0
        frame_width = sample_width * channels
        if frame_width <= 0:
            return 0.0

        total = 0.0
        count = 0
        for offset in range(0, len(data) - frame_width + 1, frame_width):
            channel_total = 0.0
            for channel in range(channels):
                start = offset + channel * sample_width
                sample = data[start : start + sample_width]
                if sample_width == 1:
                    value = sample[0] - 128
                else:
                    value = int.from_bytes(sample, "little", signed=True)
                channel_total += value
            mono = channel_total / channels
            total += mono * mono
            count += 1
        return math.sqrt(total / count) if count else 0.0

    async def _drive_mouth_parameters(self, envelope: list[float], interval: float) -> None:
        open_param = str(
            self.config.get("mouth_sync_open_parameter") or "MouthOpen"
        ).strip()
        form_param = str(self.config.get("mouth_sync_form_parameter") or "").strip()
        mode = str(self.config.get("mouth_sync_mode") or "set").strip() or "set"
        smoothing = min(
            0.95,
            max(0.0, self._safe_parse_float(self.config.get("mouth_sync_smoothing"), 0.45)),
        )
        form_strength = max(
            0.0,
            self._safe_parse_float(self.config.get("mouth_sync_form_strength"), 0.18),
        )

        smoothed = 0.0
        scheduler = (
            getattr(self, "_vts_parameter_scheduler", None)
            if mode == "set"
            else None
        )
        if scheduler:
            scheduler.set_source_fps(
                "mouth",
                max(5, min(30, round(1.0 / max(interval, 0.001)))),
            )
            scheduler.start()
        for index, value in enumerate(envelope):
            if not await self._check_and_reconnect():
                return
            smoothed = smoothed * smoothing + value * (1.0 - smoothing)
            parameters = [{"id": open_param, "value": smoothed}]
            if form_param and form_strength > 0:
                form_value = (
                    math.sin(index * 0.75)
                    * form_strength
                    * min(1.0, smoothed * 1.4)
                )
                parameters.append({"id": form_param, "value": form_value})
            if scheduler:
                scheduler.set_layer(
                    "mouth",
                    parameters,
                    ttl=max(0.4, interval * 4.0),
                )
            else:
                await self.vts.inject_parameters(parameters=parameters, mode=mode)
            await asyncio.sleep(interval)

    async def _reset_mouth_parameters(self) -> None:
        if not self._is_mouth_sync_enabled():
            return
        if not await self._check_and_reconnect():
            return
        open_param = str(
            self.config.get("mouth_sync_open_parameter") or "MouthOpen"
        ).strip()
        form_param = str(self.config.get("mouth_sync_form_parameter") or "").strip()
        parameters = [{"id": open_param, "value": 0.0}]
        if form_param:
            parameters.append({"id": form_param, "value": 0.0})
        try:
            mode = str(self.config.get("mouth_sync_mode") or "set").strip() or "set"
            scheduler = (
                getattr(self, "_vts_parameter_scheduler", None)
                if mode == "set"
                else None
            )
            if scheduler:
                scheduler.set_layer("mouth", parameters)
                await scheduler.flush()
                scheduler.clear_layer("mouth")
            else:
                await self.vts.inject_parameters(
                    parameters=parameters,
                    mode=mode,
                )
        except Exception as e:
            logger.debug(f"[嘴型] 重置嘴型参数失败: {e}")
