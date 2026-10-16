"""Forward one body's AstrBot hooks to current, running internal services."""

from __future__ import annotations

import logging

from .request_context import clear_turn_contexts, set_system_instruction


logger = logging.getLogger(__name__)


def _active(controller, name):
    registry = getattr(controller, "native_extensions", None)
    lookup = getattr(registry, "active_service", None)
    return lookup(name) if callable(lookup) else None


def _events(controller, name):
    runtime = _active(controller, name)
    if runtime is None:
        return None
    owner = getattr(runtime, "_host_event_owner", None)
    if owner is None:
        if name == "live":
            from .live.host_events import LiveHostEvents as EventOwner
        elif name == "game":
            from .game.host_events import GameHostEvents as EventOwner
        else:
            from .reality.host_events import RealityHostEvents as EventOwner
        owner = EventOwner(runtime, lambda: _active(controller, name) is runtime)
        runtime._host_event_owner = owner
    return owner


def _dispatch(controller, method, *args):
    for name in ("game", "reality", "live"):
        try:
            owner = _events(controller, name)
            callback = getattr(owner, method, None)
            if callable(callback):
                callback(*args)
        except Exception as error:
            logger.warning("[CompanionV2] 内部能力事件暂不可用 domain=%s phase=%s error_type=%s",
                           name, method, type(error).__name__)


def prepare_native_host_request(controller, event, req):
    clear_turn_contexts(req)
    if _active(controller, "live") is None:
        set_system_instruction(req, "soullink")
        set_system_instruction(req, "live2d")
    _dispatch(controller, "request", event, req)


def observe_native_host_response(controller, event, response):
    _dispatch(controller, "response", event, response)


def observe_native_host_result(controller, event):
    _dispatch(controller, "decorating", event)
