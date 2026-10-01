"""Decoder integrity, public-location boundaries and child process cancellation."""

import asyncio
import base64
import struct
import unittest
from unittest.mock import AsyncMock, patch

from astrbot_host.audio.decoder import inspect_audio, wave_bytes
from astrbot_host.audio.loader import decode_audio, load_native_audio
from companion_v2.adapters.astrbot.native import NativeAudioLocator
from companion_v2.conversation.media.audio.models import MAX_AUDIO_BYTES, CapturedAudio, fits_audio_budget
from companion_v2.execution.models import TaskError
from tests.audio_support import audio_bytes, silk_bytes


class AudioDecoderTests(unittest.IsolatedAsyncioTestCase):
    async def test_pcm_and_tencent_silk_preserve_original_and_complete_listening_view(self):
        for content in (audio_bytes(), silk_bytes()):
            expected = inspect_audio(content, 3)
            actual = await load_native_audio(NativeAudioLocator(3, "base64://" + base64.b64encode(content).decode("ascii")))
            self.assertEqual(actual, expected)
            self.assertEqual(actual.content, content)
            self.assertEqual(inspect_audio(actual.waveform, 3).waveform, actual.waveform)

    async def test_all_silk_frames_are_retained_in_multi_frame_packets(self):
        for count in range(1, 6):
            with self.subTest(frames=count):
                result = inspect_audio(silk_bytes(frames_per_packet=count, packets=3), 0)
                self.assertEqual(result.descriptor.sample_count, 480 * count * 3)
                self.assertEqual(result.descriptor.duration_ms, 20 * count * 3)
                self.assertEqual((await decode_audio(result.content, 0)).waveform, result.waveform)

    def test_stereo_pcm_is_mixed_without_truncating_frames(self):
        pcm = struct.pack("<hhhh", 2000, -1000, -3000, 1000)
        mono = wave_bytes(pcm, 24000)
        stereo = bytearray(mono)
        struct.pack_into("<H", stereo, 22, 2)
        struct.pack_into("<I", stereo, 28, 96000)
        struct.pack_into("<H", stereo, 32, 4)
        result = inspect_audio(bytes(stereo), 0)
        self.assertEqual(result.waveform[44:], struct.pack("<hh", 500, -1000))
        self.assertEqual(result.descriptor.sample_count, 2)

    def test_incomplete_malformed_or_unsupported_containers_fail_without_partial_audio(self):
        silk = silk_bytes()
        wav = audio_bytes()
        corrupt = [b"", b"ID3 mp3", b"#!SILK_V3", silk[:-1], silk + b"x", silk + b"\xfe\xff",
                   wav[:-1], wav + b"extra", wav[:36] + b"data" + struct.pack("<I", 10000000) + wav[44:]]
        for value in corrupt:
            with self.subTest(length=len(value)), self.assertRaises(TaskError):
                inspect_audio(value, 0)

    def test_per_attachment_and_shared_duration_are_independent_limits(self):
        with self.assertRaises(TaskError) as caught:
            inspect_audio(audio_bytes(60.01, 8000), 0)
        self.assertEqual(caught.exception.code, "host_audio_limit")
        one = inspect_audio(audio_bytes(45, 8000), 0).descriptor
        self.assertTrue(fits_audio_budget((one, one)))
        self.assertFalse(fits_audio_budget((one, one, one)))
        with self.assertRaises(TaskError):
            CapturedAudio(one, b"changed", b"changed")

    async def test_remote_bytes_share_existing_public_dns_and_redirect_checks(self):
        with patch("astrbot_host.audio.loader.fetch_public_attachment", AsyncMock(return_value=audio_bytes())) as fetch:
            result = await load_native_audio(NativeAudioLocator(1, "https://attachment.example/voice"))
            self.assertEqual(result.descriptor.position, 1)
            fetch.assert_awaited_once()
        for value in ("C:/secret.wav", "file:///C:/secret.wav", "http://127.0.0.1/voice", "http://[::1]/voice"):
            with self.subTest(value=value), self.assertRaises(TaskError) as caught:
                await load_native_audio(NativeAudioLocator(0, value))
            self.assertEqual(caught.exception.code, "host_audio_location_invalid")

    async def test_oversized_base64_does_not_spawn_decoder(self):
        with patch("astrbot_host.audio.loader.decode_audio", AsyncMock()) as decode:
            with self.assertRaises(TaskError):
                await load_native_audio(NativeAudioLocator(0, "base64://" + "A" * ((MAX_AUDIO_BYTES + 2) // 3 * 4 + 1)))
            decode.assert_not_awaited()

    async def test_timeout_and_cancellation_kill_and_reap_decoder(self):
        class HeldProcess:
            returncode = None
            killed = False
            waited = False
            async def communicate(self, content=None):
                if self.killed:
                    self.waited = True
                    return b"", b""
                entered.set()
                await asyncio.Event().wait()
            def kill(self):
                self.killed, self.returncode = True, -1
        for cancel in (False, True):
            entered, process = asyncio.Event(), HeldProcess()
            with patch("astrbot_host.audio.loader.asyncio.create_subprocess_exec", AsyncMock(return_value=process)), \
                    patch("astrbot_host.audio.loader.DECODE_TIMEOUT", 0.03):
                task = asyncio.create_task(decode_audio(audio_bytes(), 0))
                await entered.wait()
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    with self.assertRaises(TaskError) as caught:
                        await task
                    self.assertEqual(caught.exception.code, "host_audio_decode_timeout")
            self.assertTrue(process.killed and process.waited)
