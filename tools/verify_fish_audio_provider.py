"""Opt-in Fish Audio local synthesis probe; never save config or send messages."""

import argparse
import asyncio
import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace as NS
import wave


async def probe(args):
    from astrbot import logger
    from astrbot.core.provider.sources.fishaudio_tts_api_source import ProviderFishAudioTTSAPI
    from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
    from astrbot_host.fish_audio import provider_direction
    from astrbot_host.voice import NativeVoiceReply
    from companion_v2.conversation.voice_reply import VoiceReplyPolicy
    from companion_v2.foundation.refs import ScopeKind

    logger.setLevel("WARNING")
    Path(get_astrbot_temp_path()).mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.host_config).read_text(encoding="utf-8-sig"))
    selected = next(item for item in config["provider"] if item["id"] == args.provider)
    if selected.get("type") != "fishaudio_tts_api":
        raise ValueError("the probe requires a Fish Audio TTS Provider")
    sources = {item["id"]: item for item in config.get("provider_sources", ())}
    merged = deepcopy({**sources.get(selected.get("provider_source_id"), {}), **selected})
    # Override a local copy only. Installed providers and saved configuration
    # are not changed even if the real request fails.
    merged["model"] = args.model
    provider = ProviderFishAudioTTSAPI(merged, config.get("provider_tts_settings", {}))
    report = {"provider": args.provider, "model": provider.get_model(), "model_header": provider.headers["model"],
              "platform_messages_sent": 0, "saved_config_changed": False}
    original = provider.get_audio

    async def captured_audio(text):
        try:
            return await original(text)
        except Exception as error:
            report["error_type"] = type(error).__name__
            status = re.search(r"(?:状态码|status(?:\s+code)?)\s*[:=]?\s*(\d{3})", str(error), re.I)
            if status:
                report["http_status"] = int(status.group(1))
            raise

    provider.get_audio = captured_audio
    context = NS(get_provider_by_id=lambda _: provider, get_all_tts_providers=lambda: [provider])
    policy = VoiceReplyPolicy(generation_mode="model_tag", provider_id=args.provider)
    report["direction_available"] = bool(await provider_direction(context, policy, "probe:FriendMessage:local"))
    task = NS(scope=NS(kind=ScopeKind.PRIVATE, platform="probe", session_id="local-only"))
    started = monotonic()
    record = await NativeVoiceReply(context).render(task, args.text, provider_id=args.provider,
                                                   timeout_seconds=args.timeout)
    audio = base64.b64decode(record["data"]["file"].removeprefix("base64://")) if record else b""
    report.update(bytes=len(audio), elapsed_ms=round((monotonic() - started) * 1000))
    if audio:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            report.update(sample_rate=wav.getframerate(), channels=wav.getnchannels(),
                          duration_seconds=round(wav.getnframes() / wav.getframerate(), 3))
        (args.output / "drama-3-preview.wav").write_bytes(audio)
    report["passed"] = bool(record and report["direction_available"] == (args.model == "drama-3"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("astrbot-app", "host-config", "provider"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="drama-3")
    parser.add_argument("--timeout", default=45, type=int)
    parser.add_argument("--text", default="[轻声，像在说晚安]おやすみ。<soft>ゆっくり休んでね。</soft>")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(Path(__file__).resolve().parents[1]), args.astrbot_app]
    with TemporaryDirectory(prefix="companion-fish-provider-") as root:
        os.environ["ASTRBOT_ROOT"] = root
        try:
            report = asyncio.run(probe(args))
        except Exception as error:
            # Never output exceptions containing request credentials or text.
            report = {"passed": False, "error_type": type(error).__name__, "platform_messages_sent": 0}
    (args.output / "fish-audio-probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
