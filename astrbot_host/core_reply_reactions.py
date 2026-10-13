"""Observe real native reaction cache entries and successful send returns."""

import hashlib
import json
from pathlib import Path

from astrbot.core.message.components import Image

from companion_v2.execution.models import encode
from .core_reply import CORE_REPLY_CONTEXT_EXTRA


def _state(event):
    core = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if not isinstance(core, dict):
        return None
    return core.setdefault("_reaction_media", {"offers": {}, "cached": {}})


def offer_core_reactions(event, session, call_id, payload, images):
    state = _state(event)
    if state is None or not images:
        return
    state["offers"][call_id] = {"session": session, "call_id": call_id,
        "payload": json.loads(encode(payload)), "hashes": {image.descriptor.content_hash for image in images}}


def observe_core_cached_image(event, cached_image):
    """Use the native runner's actual cache result, without deriving cache paths."""
    state = _state(event)
    if state is None or getattr(cached_image, "tool_name", "") != "companion_v2_reaction_search":
        return False
    offer = state["offers"].get(getattr(cached_image, "tool_call_id", ""))
    path = getattr(cached_image, "file_path", None)
    if offer is None or not isinstance(path, str):
        return False
    original = Path(path).resolve(strict=False)
    cached = {**offer, "path": original}
    state["cached"][str(original)] = state["cached"][original.as_uri()] = cached
    return True


def observe_core_media_send_returned(event, message, *, submit):
    """Schedule usage only for offered originals in an actual returned send.

    ``submit`` is the session's thread-backed observation queue. No file or
    database work runs on the native reply or send path.
    """
    state = _state(event)
    if state is None or not callable(submit):
        return False
    cached = []
    for part in getattr(message, "chain", ()):
        if not isinstance(part, Image):
            continue
        original = state["cached"].get(getattr(part, "path", None)) or state["cached"].get(getattr(part, "file", None))
        if original is not None and original not in cached:
            cached.append(original)
    if not cached:
        return False
    observed_at = cached[0]["session"].application.now()

    def record():
        for original in cached:
            content_hash = hashlib.sha256(original["path"].read_bytes()).hexdigest()
            if content_hash not in original["hashes"]:
                continue
            session = original["session"]
            semantic = session.application.tools.semantic
            semantic.reactions.mark_native_returned(session.context, session.turn_id,
                original["call_id"], original["payload"], content_hash, observed_at)

    return submit(record) is not None
