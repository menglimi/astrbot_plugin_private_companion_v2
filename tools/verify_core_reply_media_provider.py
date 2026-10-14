"""Opt-in real Provider media probe; synthesize locally and never send a message."""

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from tempfile import TemporaryDirectory
import time
import traceback
from types import SimpleNamespace as NS


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


async def probe(args):
    from astrbot import logger
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.astr_main_agent_resources import LLM_SAFETY_MODE_SYSTEM_PROMPT, TOOL_CALL_PROMPT
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
    from astrbot.core.provider.sources.fishaudio_tts_api_source import ProviderFishAudioTTSAPI
    from astrbot_host.core_reply import CORE_REPLY_CONTEXT_EXTRA
    from astrbot_host.core_reply_context import BACKGROUND_INSTRUCTION
    from astrbot_host.core_reply_media_prompt import finalize_core_reply_media_prompt
    from astrbot_host.core_reply_voice_authoring import bind_core_voice_authoring, restore_core_voice_authoring
    from astrbot_host.core_reply_reaction_delivery import observe_core_reaction_response
    from astrbot_host.multi_settings import MultiHostSettings
    from astrbot_host.voice import NativeVoiceReply
    from companion_v2.conversation.voice_reply import separate_spoken, speech_chunks
    from companion_v2.expression.reply_intent import authored_reply_decision, extract_reply_intent
    from companion_v2.foundation.refs import ScopeKind

    logger.setLevel("WARNING")
    cfg = read_json(args.host_config)
    item = next(p for p in cfg["provider"] if p["id"] == args.provider)
    source = next(p for p in cfg["provider_sources"] if p["id"] == item["provider_source_id"])
    merged = {**source, **item}
    if merged["type"] != "openai_chat_completion":
        raise ValueError("this probe requires a configured chat-completion Provider")
    provider = ProviderOpenAIOfficial(merged, cfg.get("provider_settings", {}))
    policy = MultiHostSettings.parse(read_json(args.plugin_config)).common.voice_reply_policy
    connection = sqlite3.connect(Path(args.persona_db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT system_prompt FROM personas WHERE persona_id=?", (args.persona,)).fetchone()
        if row is None:
            raise ValueError("the selected native persona was not found")
        persona = row[0]
        history = []
        if args.conversation:
            row = connection.execute("SELECT content FROM conversations WHERE conversation_id=?", (args.conversation,)).fetchone()
            for message in json.loads(row[0]) if row else ():
                if message.get("role") not in {"user", "assistant"}:
                    continue
                content = message.get("content", "")
                text = content if isinstance(content, str) else "".join(
                    part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
                if text.strip():
                    history.append({"role": message["role"], "content": text})
            history = history[-8:]
    finally:
        connection.close()

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    tool_set = (ToolSet(tools=[FunctionTool(**spec) for spec in read_json(args.tool_catalog)])
                if args.tool_catalog else None)
    safety = args.safety_mode or cfg.get("provider_settings", {}).get("llm_safety_mode", False)
    system = ((LLM_SAFETY_MODE_SYSTEM_PROMPT + "\n\n") if safety else "") + persona
    system += "\n\n" + BACKGROUND_INSTRUCTION + "\n\n" + TOOL_CALL_PROMPT
    report = {"provider": args.provider, "voice_mode": policy.trigger_mode, "language": policy.language,
              "native_safety_prompt": bool(safety),
              "generation_mode": policy.generation_mode, "cases": [], "platform_messages_sent": 0,
              "tool_count": len(tool_set.tools) if tool_set else 0,
              "core_voice_authoring": args.core_voice_authoring}
    tts = None
    try:
        for index, prompt in enumerate(args.prompt or ("笨笨的", "晚安，今天辛苦啦", "早上好呀"), 1):
            event = LocalEvent()
            event.set_extra(CORE_REPLY_CONTEXT_EXTRA, {"prepared": {"voice_reply_policy": policy,
                "native_input": NS(text=prompt)},
                "_reaction_reply": {"enabled": True}})
            request = ProviderRequest(prompt=prompt, system_prompt=system,
                                      contexts=history, func_tool=tool_set)
            runner = ToolLoopAgentRunner()
            run = NS(context=NS(event=event), messages=[])
            await runner.reset(provider=provider, request=request, run_context=run,
                               tool_executor=None, agent_hooks=None)
            finalize_core_reply_media_prompt(event, run)
            if args.core_voice_authoring:
                bind_core_voice_authoring(event, runner)
            started = time.monotonic()
            responses = runner._iter_llm_responses_with_fallback()
            try:
                response = await anext(responses)
            finally:
                await responses.aclose()
                restore_core_voice_authoring(event)
            elapsed = round((time.monotonic() - started) * 1000)
            raw = response.completion_text or ""
            text, intent = extract_reply_intent(raw)
            visible, spans = separate_spoken(text, policy)
            core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
            if args.core_voice_authoring:
                spans = core.get("_voice_authored", {}).get("spans", spans)
            speech = "".join(value for _, value in spans)
            observe_core_reaction_response(event, response)
            reaction = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["_reaction_reply"]
            case = {"case": index, "model_ms": elapsed, "role": response.role,
                    "speech_spans": len(spans), "speech_chars": len(speech), "visible_chars": len(visible),
                    "japanese_speech": bool(re.search(r"[\u3040-\u30ff]", speech)),
                    "reaction_intent": bool(intent), "reaction_decision": authored_reply_decision(raw),
                    "reaction_lookup_intent": bool(reaction.get("intent")),
                    "reaction_reason": reaction.get("reason", "not_observed"),
                    "tool_calls": list(getattr(response, "tools_call_name", ()) or ()),
                    "voice_authoring_repair": core.get("_voice_authoring_repair", {}).get("state", "not_needed"),
                    "protocol_hidden": "<pc_" not in visible and "<tts" not in visible}
            (output / f"reply-{index}.txt").write_text(raw + "\n", encoding="utf-8", newline="\n")
            report["cases"].append(case)
            if spans and tts is None:
                tts_item = next(p for p in cfg["provider"] if p["id"] == policy.provider_for_language())
                tts = ProviderFishAudioTTSAPI(tts_item, cfg.get("provider_tts_settings", {}))
                context = NS(get_provider_by_id=lambda _: tts, get_all_tts_providers=lambda: [tts])
                task = NS(scope=NS(kind=ScopeKind.PRIVATE, platform="probe", session_id="local-only"))
                started = time.monotonic()
                record = await NativeVoiceReply(context).render(task, speech_chunks(spans[0][1], policy.max_speech_chars)[0],
                    provider_id=policy.provider_for_language(), timeout_seconds=policy.timeout_seconds)
                audio = base64.b64decode(record["data"]["file"].removeprefix("base64://")) if record else b""
                audio_path = output / "generated-reply.wav"
                audio_path.write_bytes(audio)
                report["tts"] = {"bytes": len(audio), "ms": round((time.monotonic() - started) * 1000),
                                 "valid_header": audio.startswith((b"RIFF", b"ID3", b"OggS", b"\xff"))}
            save_json(output / "provider-probe.json", report)
    finally:
        await provider.client.close()
    report["passed"] = all(c["role"] == "assistant" and c["speech_spans"] and c["protocol_hidden"]
        and (c["japanese_speech"] or policy.language != "ja") for c in report["cases"])
    report["passed"] = bool(report["passed"] and report["cases"]
                            and all(c["reaction_lookup_intent"] or c["reaction_reason"] == "model_declined"
                                    for c in report["cases"])
                            and report.get("tts", {}).get("valid_header"))
    save_json(output / "provider-probe.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


class LocalEvent:
    """No platform client or send method exists in this probe."""

    def __init__(self):
        self.extra = {}

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("astrbot-app", "host-config", "plugin-config", "persona-db", "persona", "provider", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--conversation")
    parser.add_argument("--safety-mode", action="store_true")
    parser.add_argument("--tool-catalog", help="JSON schemas from the configured native and V2 tools; never execute them")
    parser.add_argument("--core-voice-authoring", action="store_true", help="Exercise the actual main-chain voice authoring wrapper")
    parser.add_argument("--prompt", action="append")
    args = parser.parse_args()
    sys.path[:0] = [str(Path(__file__).resolve().parents[1]), args.astrbot_app]
    with TemporaryDirectory(prefix="companion-real-media-sdk-") as root:
        os.environ["ASTRBOT_ROOT"] = root
        try:
            return asyncio.run(probe(args))
        except Exception as error:
            # Provider exception strings may contain credentials or prompts.
            print(json.dumps({"passed": False, "error_type": type(error).__name__,
                "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                           for frame in traceback.extract_tb(error.__traceback__)[-6:]]}))
            return 1


if __name__ == "__main__":
    sys.exit(main())
