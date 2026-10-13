"""Send literal group repeat actions through the authorized AstrBot event."""

import asyncio
from io import BytesIO
import logging
from pathlib import Path

from astrbot.api.event import MessageEventResult
from astrbot.core.message.components import Image, Plain
from PIL import Image as PillowImage

from companion_v2.conversation.group_interjection import REPEAT_FOLLOW, REPEAT_INTERRUPT
from companion_v2.conversation.group_timing import clean_group_text, repeat_burst, repeat_signature
from companion_v2.conversation.native_participation import _speech_record
from companion_v2.conversation.participation import group_participation_settings
from companion_v2.conversation.repeat_actions import GroupRepeatActions
from companion_v2.execution.models import TaskError, require, stamp


logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def interrupt_image(path):
    """Use only the administrator's configured, readable local image."""
    if not path:
        return None
    try:
        source = Path(path.strip()).expanduser()
        with source.open("rb") as stream:
            payload = stream.read(MAX_IMAGE_BYTES + 1)
        if not payload or len(payload) > MAX_IMAGE_BYTES:
            return None
        with PillowImage.open(BytesIO(payload)) as image:
            if image.format not in {"PNG", "JPEG", "GIF", "WEBP", "BMP"}:
                return None
            image.verify()
        return Image.fromBytes(payload)
    except (OSError, ValueError, SyntaxError, PillowImage.DecompressionBombError):
        return None


def _observe(operation, *args, **kwargs):
    """Optional receipts must not prevent an already authorized literal send."""
    try:
        return operation(*args, **kwargs)
    except Exception as error:
        logger.warning("[CompanionV2] 群复读记录降级 error_type=%s", type(error).__name__)
        return None


def _other_speech_count(participation, context, native, settings, at):
    visible, turns = participation.admission.native_participation_history(
        context, native.instruction, at=at, max_age_hours=max(48, settings["group_context_max_age_hours"]))
    # The action store reserves repeat sends, including unknown outcomes. Count
    # other native replies here so successful repeats do not consume quota twice.
    record = _speech_record(tuple(turn for turn in turns if turn.get("reason") != "repeat"), visible, at=at,
        policy=participation._interjection_policy(settings, {}), timezone_name=participation.messages.timezone_name)
    return visible, record["used_today"]


async def receive_group_repeat(controller, event, target, admission, *, prepared=None):
    """No LLM request: send one original line or one configured interruption."""
    if prepared is None:
        prepared = require(await controller.prepare_core_reply(event, target, group_admission=admission))
    context, native = prepared["context"], prepared["native_input"]
    session = controller.session
    participation = session.application.tools.group_participation
    settings = group_participation_settings(participation.runtime, context)
    visible, used_today = _other_speech_count(participation, context, native, settings, native.at)
    text = clean_group_text(native.text)
    current = {"kind": "member", "speaker_id": context.actor.principal.native_account_id,
               "received_at": stamp(native.at), "text": text, "event_id": native.event_id}
    visible = (*visible, current) if current not in visible else visible
    burst = repeat_burst(repeat_signature(text), visible, at=native.at,
                         window_seconds=settings["group_repeat_window_seconds"])
    actions = GroupRepeatActions(participation.runtime)
    operation = actions.plan(context, native.event_id, text, at=native.at, burst=burst, settings=settings,
                             used_today=used_today, timezone_name=participation.messages.timezone_name)
    if operation["state"] != "planned":
        return {"action": operation["action"], "state": operation["state"], "reason": operation["reason"]}
    image = await asyncio.to_thread(interrupt_image, operation["image_path"])
    if operation["image_path"] and image is None:
        logger.info("[CompanionV2] 群复读打断图不可用，采用配置的打断语 event_ref=%s", native.event_id)
    message = MessageEventResult(chain=[image] if image is not None else [Plain(operation["text"])])
    ledger = participation.admission
    _observe(ledger.record_core_reply, context, native.event_id, instruction=native.instruction,
             reason="repeat", mentioned=False, at=native.at)
    _observe(ledger.mark_core_participation, context, native.event_id, mode="reply", reason=operation["reason"],
        act=REPEAT_FOLLOW if operation["action"] == "follow" else REPEAT_INTERRUPT, signature=operation["signature"])
    require(await controller.authorize_core_reply(event, target, prepared))
    _, used_today = _other_speech_count(participation, context, native, settings, controller.now())
    if not actions.begin(context, native.event_id, used_today=used_today, limit=settings["group_interject_max_daily"]):
        saved = actions.read(context, native.event_id)
        return {"action": saved["action"], "state": saved["state"], "reason": saved["reason"]}
    _observe(ledger.mark_core_reply, context, native.event_id, stage="send_started", at=controller.now())
    try:
        await event.send(message)
    except BaseException as error:
        _observe(actions.finish, context, native.event_id, state="unknown")
        _observe(ledger.mark_core_reply, context, native.event_id, stage="send_unknown", at=controller.now())
        _observe(ledger.mark_core_reply, context, native.event_id, stage="completed", at=controller.now())
        if isinstance(error, Exception):
            raise TaskError("group_repeat_send_unknown", "repeat send outcome is unknown; it will not be replayed") from error
        raise
    _observe(actions.finish, context, native.event_id, state="returned")
    _observe(ledger.mark_core_reply, context, native.event_id, stage="send_returned", at=controller.now())
    _observe(ledger.mark_core_reply, context, native.event_id, stage="completed", at=controller.now())
    observer = session.core_reply_observations
    if observer is not None:
        _observe(observer.output, prepared, "" if image is not None else operation["text"], state="send_returned")
    logger.info("[CompanionV2] 群复读动作 event_ref=%s action=%s media=%s send_state=returned platform_confirmed=false",
                native.event_id, operation["action"], "image" if image is not None else "text")
    return {"action": operation["action"], "state": "returned", "reason": operation["reason"],
            "media": "image" if image is not None else "text"}
