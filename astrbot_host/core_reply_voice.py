"""Apply configured TTS to authorized AstrBot core replies."""

import logging
import re
import asyncio

from astrbot.core.message.components import Plain, Record
from astrbot.core.message.message_event_result import MessageChain

from companion_v2.conversation.voice_reply import (
    VoiceReplyPolicy,
    separate_spoken,
    speech_candidates,
)
from .core_reply import CORE_REPLY_CONTEXT_EXTRA


logger = logging.getLogger(__name__)


def voice_prompt_instruction(policy):
    if not isinstance(policy, VoiceReplyPolicy):
        return ""
    from companion_v2.conversation.voice_reply import capability_instruction

    return "\n".join(part for part in (capability_instruction(policy), policy.instruction) if part)


def _plain_text(message):
    chain = getattr(message, "chain", None)
    if isinstance(chain, (list, tuple)):
        return "".join(component.text for component in chain if isinstance(component, Plain))
    return message if isinstance(message, str) else ""


def _clean_plain_runs(message, policy):
    if isinstance(message, str):
        visible, spans = separate_spoken(message, policy)
        return visible, spans, visible

    chain = getattr(message, "chain", None)
    if not isinstance(chain, (list, tuple)):
        return "", (), message
    output, visible_parts, spans, index = [], [], [], 0
    while index < len(chain):
        component = chain[index]
        if not isinstance(component, Plain):
            output.append(component)
            index += 1
            continue
        run = []
        while index < len(chain) and isinstance(chain[index], Plain):
            run.append(chain[index].text)
            index += 1
        run_visible, run_spans = separate_spoken("".join(run), policy)
        offset = sum(map(len, visible_parts))
        spans.extend((offset + position, speech) for position, speech in run_spans)
        visible_parts.append(run_visible)
        if run_visible:
            output.append(Plain(run_visible))
    visible = "".join(visible_parts)
    derive = getattr(message, "derive", None)
    cleaned = derive(output) if callable(derive) else MessageChain(chain=output)
    return visible, tuple(spans), cleaned


def _message_with_voice(message, visible, record, policy, *, hide_text):
    chain = getattr(message, "chain", None)
    if not isinstance(chain, (list, tuple)):
        chain = [Plain(message)] if isinstance(message, str) and message else []
        message = MessageChain(chain=chain)

    output = []
    first_plain = None
    last_plain = None
    for component in chain:
        if isinstance(component, Plain):
            if first_plain is None:
                first_plain = len(output)
            if not hide_text:
                output.append(component)
                last_plain = len(output) - 1
        else:
            output.append(component)

    if policy.position == "before_text":
        insert_at = first_plain if first_plain is not None else 0
    elif policy.position == "after_text":
        insert_at = last_plain + 1 if last_plain is not None else 0
    else:
        insert_at = len(output)
    output.insert(max(0, min(insert_at, len(output))), record)

    derive = getattr(message, "derive", None)
    return derive(output) if callable(derive) else MessageChain(chain=output)


async def prepare_core_reply_voice_message(
    event,
    prepared,
    message,
    *,
    renderer,
    delivery,
    authorize,
    segment_index=0,
    segment_count=1,
):
    """Synthesize one completed segment while preserving text and media order."""
    policy = prepared.get("voice_reply_policy") if hasattr(prepared, "get") else None
    if not isinstance(policy, VoiceReplyPolicy):
        return message
    if not callable(renderer) or not callable(getattr(event, "get_extra", None)):
        return message

    chain = getattr(message, "chain", None)
    if isinstance(message, Record) or (isinstance(chain, (list, tuple)) and
                                       any(isinstance(component, Record) for component in chain)):
        return message
    source = _plain_text(message)
    if not source.strip():
        return message

    visible, spans, cleaned_message = _clean_plain_runs(message, policy)
    if not visible.strip():
        return cleaned_message

    segment_index = max(0, int(segment_index))
    segment_count = max(1, int(segment_count))
    selected = (policy.segment_mode == "each" or
                policy.segment_mode == "first" and segment_index == 0 or
                policy.segment_mode == "last" and segment_index == segment_count - 1)
    if not selected:
        return cleaned_message

    candidates = speech_candidates(visible, (visible,), spans, policy)
    speech = candidates[0].strip() if candidates else ""
    if not speech or len(speech) > policy.max_speech_chars:
        return cleaned_message

    context = prepared.get("context")
    event_id = prepared.get("event_id") or prepared.get("turn_id") or "core-reply"
    claim = None
    claim_route = getattr(delivery, "claim_core_route", None)
    if callable(claim_route) and policy.cooldown_seconds:
        claim = claim_route(context, event_id, policy.cooldown_seconds)
        if claim is None:
            return cleaned_message

    try:
        await authorize()
        audio = await renderer(context, speech, provider_id=policy.provider_for_language(),
                               timeout_seconds=policy.timeout_seconds)
    except asyncio.CancelledError:
        if claim is not None:
            delivery.release(claim, claim["part_id"])
        raise
    except Exception as error:
        logger.warning("[CompanionV2] 核心回复 TTS 降级为文字 event_ref=%s error_type=%s",
                       prepared.get("event_ref", "unknown"), type(error).__name__)
        if claim is not None:
            delivery.release(claim, claim["part_id"])
        return cleaned_message
    if not isinstance(audio, dict) or audio.get("type") != "record":
        logger.warning("[CompanionV2] 核心回复 TTS 未返回音频 event_ref=%s language=%s",
                       prepared.get("event_ref", "unknown"), policy.language)
        if claim is not None:
            delivery.release(claim, claim["part_id"])
        return cleaned_message
    audio_data = audio.get("data")
    file_value = audio_data.get("file") if isinstance(audio_data, dict) else None
    if not isinstance(file_value, str) or not file_value.startswith("base64://"):
        logger.warning("[CompanionV2] 核心回复 TTS 音频格式无效 event_ref=%s",
                       prepared.get("event_ref", "unknown"))
        if claim is not None:
            delivery.release(claim, claim["part_id"])
        return cleaned_message

    record = Record(file=file_value)
    try:
        object.__setattr__(record, "_companion_v2_spoken_text", speech)
    except Exception:
        pass
    logger.info("[CompanionV2] 核心回复 TTS 已合成 event_ref=%s language=%s chars=%s segment=%s/%s",
                prepared.get("event_ref", "unknown"), policy.language, len(speech),
                segment_index + 1, segment_count)
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if isinstance(core, dict) and claim is not None:
        core["_voice_reply_pending_claim"] = (delivery, claim)
    same_text = re.sub(r"\s+", "", visible) == re.sub(r"\s+", "", speech)
    return _message_with_voice(cleaned_message, visible, record, policy,
                               hide_text=policy.delivery_mode == "voice_only" and same_text)


def prepare_core_reply_voice(event):
    """Prepare voice policy from the already captured core reply context."""
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    prepared = core.get("prepared") if isinstance(core, dict) else None
    if not isinstance(prepared, dict) or not isinstance(prepared.get("voice_reply_policy"), VoiceReplyPolicy):
        return

    setter = getattr(event, "set_extra", None)
    if callable(setter):
        setter("enable_streaming", False)


def release_pending_voice_claim(event):
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    pending = core.pop("_voice_reply_pending_claim", None) if isinstance(core, dict) else None
    if pending is not None:
        delivery, claim = pending
        delivery.release(claim, claim["part_id"])


def commit_pending_voice_claim(event):
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if isinstance(core, dict):
        core.pop("_voice_reply_pending_claim", None)
