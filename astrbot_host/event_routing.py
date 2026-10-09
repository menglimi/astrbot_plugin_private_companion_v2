"""Small host-side routing helpers for sharing AstrBot message events.

Other plugins may recognize actions inside ordinary message listeners rather
than command filters.  Let those listeners run before companion reply intake,
and suppress only AstrBot's default model fallback when V2 owns a reply.  The
event must remain available to later listeners, including activity counters.

AstrBot puts matched commands into ``activated_handlers`` before dispatch.
Use that parsed information instead of maintaining another command registry.
"""

from __future__ import annotations

from typing import Any


_COMMAND_FILTER_NAMES = frozenset({"CommandFilter", "CommandGroupFilter"})
COMPANION_INTAKE_PRIORITY = -230000


def suppress_default_reply(event: Any) -> None:
    """Keep plugin dispatch open while preventing a second default reply.

    In AstrBot 4.27.2, ``call_llm=True`` means the default LLM request is
    forbidden: ``ProcessStage`` checks ``not event.call_llm``.  The SDK method
    retains that flag's polarity despite its name.  Explicit plugin replies
    and plugin-issued model requests remain available.
    """

    setter = getattr(event, "should_call_llm", None)
    if callable(setter):
        setter(True)
    else:
        event.call_llm = True


def _belongs_to_module(module_path: object, module_name: str | None) -> bool:
    """Return whether a handler module is part of ``module_name``'s plugin.

    AstrBot loads a plugin entry point as ``<plugin package>.main`` while a
    plugin may keep additional handlers in sibling modules.  Comparing the
    package prefix keeps the helper usable in both the installed entry point
    and the isolated test import used by this repository.
    """

    if not isinstance(module_path, str) or not module_name:
        return False
    package = module_name.rsplit(".", 1)[0] if "." in module_name else module_name
    return module_path == module_name or module_path.startswith(package + ".")


def _is_command_filter(event_filter: object) -> bool:
    filter_type = type(event_filter)
    return (
        filter_type.__name__ in _COMMAND_FILTER_NAMES
        and filter_type.__module__.startswith("astrbot.")
    )


def competing_command_handler(event: object, *, own_module: str | None = None) -> Any | None:
    """Find a different plugin command already matched for this event.

    ``WakingCheckStage`` has already run when an adapter message handler is
    called, so a command filter in ``activated_handlers`` represents a command
    that AstrBot will dispatch.  Returning that handler lets the caller leave
    the event untouched.  A missing/foreign event shape simply means no
    competing command, preserving direct calls and older AstrBot runtimes.
    """

    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return None
    handlers = getter("activated_handlers", ())
    if not isinstance(handlers, (list, tuple)):
        return None
    for handler in handlers:
        if _belongs_to_module(getattr(handler, "handler_module_path", None), own_module):
            continue
        filters = getattr(handler, "event_filters", ())
        if any(_is_command_filter(event_filter) for event_filter in filters or ()):
            return handler
    return None


def has_competing_command(event: object, *, own_module: str | None = None) -> bool:
    """Whether another plugin has a parsed command handler for this event."""

    return competing_command_handler(event, own_module=own_module) is not None
