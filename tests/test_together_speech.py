"""STT settings reach native rooms without selecting another session's provider."""

import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock
import wave

from tests import astrbot_data_root  # Isolate the SDK before importing the host.
from astrbot_host.native_extensions.settings import ExtensionSettings
from astrbot_host.native_extensions.together.runtime import TogetherRuntime
from companion_v2.together.models import NativeRoomBinding, RoomSession


class TogetherSpeechTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-together-speech-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.provider = NS(meta=lambda: NS(id="synthetic-stt"), get_text=AsyncMock(return_value="一起看星星。"))
        self.context = NS(get_provider_by_id=Mock(return_value=self.provider),
            get_using_stt_provider=Mock(return_value=None),
            get_all_stt_providers=Mock(return_value=[self.provider]),
            get_using_tts_provider=Mock(return_value=None))
        self.settings = ExtensionSettings(self.root, "together")
        self.runtime = TogetherRuntime(self.context, self.settings, self.settings.root, NS(session=None))
        self.addAsyncCleanup(self.runtime.terminate)
        self.room = RoomSession("synthetic-room", "synthetic-ticket", "call", "200", None,
            native_v2=NativeRoomBinding("synthetic-scope", "bot-a", "100", "original", "角色提示词",
                                       platform="qq-main", session_id="200"))
        self.runtime.send_room_error = AsyncMock()
        self.runtime.send_room_payload = AsyncMock()
        self.runtime._correct_stt_and_reply = AsyncMock()
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 160)
        self.audio = output.getvalue()

    async def test_saved_explicit_stt_reaches_native_capabilities_and_audio_with_host_default_disabled(self):
        self.settings.update_fields({"speech": {"stt_provider_id": "synthetic-stt"}})
        self.runtime.config = ExtensionSettings(self.root, "together")
        self.runtime._sync_page_settings_runtime()
        self.context.get_provider_by_id.side_effect = lambda identity: self.provider if identity == "synthetic-stt" else None
        bootstrap = await self.runtime.room_bootstrap(self.room)
        self.assertTrue(bootstrap["stt"]["server_available"])
        self.assertEqual(bootstrap["stt"]["server_label"], "synthetic-stt")

        async def transcribe(filename):
            self.assertEqual(Path(filename).read_bytes(), self.audio)
            return "一起看星星。"
        self.provider.get_text.side_effect = transcribe
        await self.runtime._transcribe_and_reply(self.room, self.audio, "audio/wav", utterance_id="synthetic-turn")
        self.runtime._correct_stt_and_reply.assert_awaited_once_with(
            self.room, "一起看星星。", source="astrbot_stt", image_data_url="",
            utterance_id="synthetic-turn", speaker_label="")
        self.context.get_using_stt_provider.assert_not_called()
        self.context.get_all_stt_providers.assert_not_called()
        self.runtime.send_room_error.assert_not_awaited()
        self.assertFalse(Path(self.provider.get_text.call_args.args[0]).exists())

    async def test_blank_selection_follows_exact_native_room_session(self):
        self.context.get_using_stt_provider.side_effect = lambda origin=None: self.provider if origin == "qq-main:FriendMessage:200" else None
        bootstrap = await self.runtime.room_bootstrap(self.room)
        self.assertTrue(bootstrap["stt"]["server_available"])
        self.context.get_using_stt_provider.assert_called_once_with("qq-main:FriendMessage:200")
        other = RoomSession("other-room", "other-ticket", "call", "201", None,
            native_v2=NativeRoomBinding("other-scope", "bot-a", "100", "original", "角色提示词",
                                       platform="qq-main", session_id="201"))
        self.assertIsNone(self.runtime._room_stt_provider(other))
        self.context.get_all_stt_providers.assert_not_called()

    async def test_loaded_provider_does_not_override_disabled_default(self):
        self.assertIsNone(self.runtime._room_stt_provider(None))
        self.assertFalse((await self.runtime.room_bootstrap(self.room))["stt"]["server_available"])
        await self.runtime._transcribe_and_reply(self.room, self.audio, "audio/wav")
        self.assertEqual(self.runtime.send_room_error.call_args.kwargs["code"], "stt_unavailable")
        self.assertIn("一起房间", self.runtime.send_room_error.call_args.args[1])
        self.provider.get_text.assert_not_awaited()
        self.runtime._correct_stt_and_reply.assert_not_awaited()
        self.context.get_all_stt_providers.assert_not_called()

    async def test_invalid_explicit_provider_keeps_choice_without_silent_fallback(self):
        self.runtime.stt_provider_id = "invalid-stt"
        self.context.get_using_stt_provider.return_value = self.provider
        for invalid in (None, NS(get_text="wrong provider type")):
            with self.subTest(invalid=invalid):
                self.context.get_provider_by_id.return_value = invalid
                self.assertIsNone(self.runtime._room_stt_provider(self.room))
                self.assertIsNone(self.runtime._room_stt_provider(None))
        self.context.get_using_stt_provider.assert_not_called()
        self.context.get_all_stt_providers.assert_not_called()
        self.assertIn("选中的", self.runtime._stt_unavailable_message())

    async def test_failed_session_lookup_does_not_use_global_provider(self):
        self.context.get_using_stt_provider.side_effect = RuntimeError("synthetic lookup failure")
        self.assertIsNone(self.runtime._room_stt_provider(self.room))
        self.context.get_using_stt_provider.assert_called_once_with("qq-main:FriendMessage:200")
        self.context.get_all_stt_providers.assert_not_called()

    async def test_compatibility_room_follows_host_default_when_no_stt_is_pinned(self):
        self.room.native_v2 = None
        self.context.get_using_stt_provider.return_value = self.provider
        self.assertIs(self.runtime._room_stt_provider(self.room), self.provider)
        self.context.get_using_stt_provider.assert_called_once_with()

    async def test_empty_or_failed_transcription_cleans_audio_and_does_not_generate_reply(self):
        self.runtime.stt_provider_id = "synthetic-stt"
        for text, error, code in (("", None, "stt_empty"), (None, RuntimeError("synthetic STT failure"), "stt_failed")):
            with self.subTest(code=code):
                self.provider.get_text.return_value = text
                self.provider.get_text.side_effect = error
                await self.runtime._transcribe_and_reply(self.room, self.audio, "audio/wav")
                self.assertEqual(self.runtime.send_room_error.call_args.kwargs["code"], code)
                self.assertFalse(Path(self.provider.get_text.call_args.args[0]).exists())
        self.runtime._correct_stt_and_reply.assert_not_awaited()
