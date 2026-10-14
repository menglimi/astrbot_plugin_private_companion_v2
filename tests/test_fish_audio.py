"""Exercise Drama 3 through AstrBot's real TTS adapter, without network IO."""

from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as _host_import
import httpx
import ormsgpack
from astrbot.core.provider.sources.fishaudio_tts_api_source import ProviderFishAudioTTSAPI
from astrbot_host.fish_audio import DRAMA_DIRECTION, provider_direction
from astrbot_host.voice import NativeVoiceReply
from companion_v2.conversation.voice_reply import VoiceReplyPolicy
from companion_v2.foundation.refs import ScopeKind


class FishAudioTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, model="drama-3"):
        return ProviderFishAudioTTSAPI({"id": "fish-test", "type": "fishaudio_tts_api",
            "provider_type": "text_to_speech", "api_key": "synthetic-key",
            "api_base": "https://api.fish.audio/v1", "model": model,
            "fishaudio-tts-reference-id": "f3a2b90078d54a65af4b95f63bc7798e"}, {})

    async def test_native_adapter_sends_exact_model_header_and_verbatim_directions(self):
        for model in ("drama-3", "s2.1-pro-free"):
            with self.subTest(model=model), TemporaryDirectory(prefix="companion-fish-wire-") as root:
                sent = []

                def handle(request):
                    sent.append(request)
                    return httpx.Response(200, headers={"content-type": "audio/wav"},
                                          content=b"RIFFsynthetic-audio")

                provider = self.provider(model)
                context = NS(get_provider_by_id=lambda _: provider, get_all_tts_providers=lambda: [provider])
                task = NS(scope=NS(kind=ScopeKind.PRIVATE, platform="test", session_id="private"))
                speech = "[像在轻声安慰]大丈夫。<soft>ゆっくり休んでね。</soft>"
                async with httpx.AsyncClient(base_url=provider.api_base,
                        transport=httpx.MockTransport(handle)) as client:
                    with patch("astrbot.core.provider.sources.fishaudio_tts_api_source.AsyncClient", return_value=client), \
                            patch("astrbot.core.provider.sources.fishaudio_tts_api_source.get_astrbot_temp_path", return_value=root), \
                            patch("astrbot_host.voice.get_astrbot_temp_path", return_value=root):
                        result = await NativeVoiceReply(context).render(task, speech, provider_id="fish-test")
                self.assertEqual(result["type"], "record")
                self.assertEqual(str(sent[0].url), "https://api.fish.audio/v1/tts")
                self.assertEqual(sent[0].headers["model"], model)
                self.assertEqual(sent[0].headers["content-type"], "application/msgpack")
                body = ormsgpack.unpackb(sent[0].content)
                self.assertEqual(body["text"], speech)
                self.assertEqual(body["reference_id"], provider.reference_id)
                self.assertEqual(body["format"], "wav")
                self.assertNotIn("model", body)

    async def test_direction_follows_selected_language_and_live_model_only(self):
        provider = self.provider()
        context = NS(get_provider_by_id=lambda identifier: provider if identifier == "ja-voice" else None,
                     get_all_tts_providers=lambda: [provider])
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="ja", ja_provider_id="ja-voice")
        self.assertEqual(await provider_direction(context, policy, "qq:FriendMessage:1"), DRAMA_DIRECTION)
        provider.set_model("s2.1-pro-free")
        self.assertEqual(await provider_direction(context, policy, "qq:FriendMessage:1"), "")
        provider.provider_config["type"] = "other_tts"
        provider.set_model("drama-3")
        self.assertEqual(await provider_direction(context, policy, "qq:FriendMessage:1"), "")
        self.assertNotIn("synthetic-key", DRAMA_DIRECTION)

    async def test_default_provider_lookup_is_async_and_optional(self):
        provider = self.provider()
        getter = AsyncMock(return_value=provider)
        context = NS(get_using_tts_provider_async=getter)
        policy = VoiceReplyPolicy(generation_mode="model_tag")
        self.assertEqual(await provider_direction(context, policy, "qq:FriendMessage:2"), DRAMA_DIRECTION)
        getter.assert_awaited_once_with("qq:FriendMessage:2")
        self.assertEqual(await provider_direction(context, VoiceReplyPolicy(), "qq:FriendMessage:2"), "")
        getter.side_effect = RuntimeError("provider unavailable")
        self.assertEqual(await provider_direction(context, policy, "qq:FriendMessage:2"), "")
