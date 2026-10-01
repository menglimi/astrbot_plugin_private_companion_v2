"""Best-effort native TTS for an already sealed conversation part."""

import asyncio
import base64
import inspect
import logging
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from companion_v2.foundation.refs import ScopeKind


logger = logging.getLogger(__name__)
MAX_VOICE_BYTES = 8_000_000


def _read_audio(path_value):
    if not isinstance(path_value, (str, Path)) or not str(path_value):
        return None
    path = Path(path_value).resolve(strict=True)
    if not path.is_relative_to(Path(get_astrbot_temp_path()).resolve()) or not path.is_file():
        return None
    with path.open("rb") as stream:
        audio = stream.read(MAX_VOICE_BYTES + 1)
    return audio if 0 < len(audio) <= MAX_VOICE_BYTES else None


class NativeVoiceReply:
    def __init__(self, context):
        self.context = context

    async def render(self, task_context, text, *, provider_id="", timeout_seconds=30):
        scope = task_context.scope
        kind = "GroupMessage" if scope.kind is ScopeKind.GROUP else "FriendMessage"
        umo = f"{scope.platform}:{kind}:{scope.session_id}"
        try:
            if provider_id:
                provider = self.context.get_provider_by_id(provider_id)
                if provider is None or provider not in self.context.get_all_tts_providers():
                    return None
            else:
                provider = self.context.get_using_tts_provider(umo)
            if provider is None:
                return None
            async def synthesize():
                method = provider.get_audio
                result = method(text.strip()) if inspect.iscoroutinefunction(method) else await asyncio.to_thread(method, text.strip())
                path = await result if inspect.isawaitable(result) else result
                if isinstance(path, (list, tuple)):
                    path = path[0] if path else None
                return await asyncio.to_thread(_read_audio, path)

            audio = await asyncio.wait_for(synthesize(), timeout=timeout_seconds)
            if audio is not None:
                return {"type": "record", "data": {"file": "base64://" + base64.b64encode(audio).decode("ascii")}}
        except Exception as error:
            logger.warning("V2 voice synthesis unavailable: %s", type(error).__name__)
        return None
