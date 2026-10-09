"""List the personas AstrBot offers, without assuming which method exists.

The guide asks the operator to pick a voice, and the pinned ``role_id`` is derived
from that choice -- so getting the list wrong means either asking for a name that
does not exist or silently pinning the wrong one.

AstrBot versions expose different enumeration methods and record shapes. The reader
below tries the supported method names, awaits asynchronous methods, and degrades to
an empty list when the host has no usable catalog.

An empty list is a legitimate answer, not a failure: the guide renders it as
"follow whichever persona this conversation uses", which is the single-persona case
and the one most installations are in. A wrong list, by contrast, would be a
silent mistake -- the operator would choose a name from it and that name would be
pinned.
"""

from __future__ import annotations

import inspect
from typing import Any


# Tried in order. Each entry is the attribute name to look for; the first callable
# wins, so a host that adds one of these later is picked up without a code change.
ENUMERATORS = ("get_personas", "get_all_personas", "list_personas", "get_persona_list")

# The shapes a returned record may take, from the most specific to the loosest.
NAME_KEYS = ("name", "persona_id", "id")


def _name_of(item: Any) -> str:
    """The persona's identifier, from whichever shape the host returned."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in NAME_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
    for key in NAME_KEYS:
        value = getattr(item, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _from_mapping(manager: Any) -> list[str]:
    """Some AstrBot versions keep personas in a plain mapping on the manager."""
    for attribute in ("personas", "persona_map", "_personas"):
        value = getattr(manager, attribute, None)
        if isinstance(value, dict):
            return [str(key).strip() for key in value if str(key).strip()]
        if isinstance(value, (list, tuple)):
            return [name for name in (_name_of(entry) for entry in value) if name]
    return []


async def available_personas(context: Any) -> list[str]:
    """Persona names the operator may choose, sorted and free of blanks.

    Never raises. A host that exposes none of these shapes yields ``[]``, which the
    caller must treat as "no explicit choice available" rather than as an error.
    """
    manager = getattr(context, "persona_manager", None)
    if manager is None:
        return []
    # AstrBot 4.27 keeps the active dashboard personas in ``personas_v3``.
    # ``get_personas`` below is a legacy database API and can omit those choices.
    current = getattr(manager, "personas_v3", None)
    if isinstance(current, (list, tuple)):
        names = [name for name in (_name_of(entry) for entry in current) if name]
        names = sorted({name for name in names if name != "[%None]"})
        if names:
            return names
    names: list[str] = []
    for attribute in ENUMERATORS:
        method = getattr(manager, attribute, None)
        if not callable(method):
            continue
        try:
            value = method()
            if inspect.isawaitable(value):
                value = await value
        except Exception:  # noqa: BLE001 -- a host-specific failure is not fatal here.
            continue
        if isinstance(value, dict):
            value = list(value)
        if isinstance(value, (list, tuple, set)):
            names = [name for name in (_name_of(entry) for entry in value) if name]
            if names:
                break
    if not names:
        names = _from_mapping(manager)
    # The sentinel AstrBot uses for "this conversation has no persona" is not a
    # choice a person can make, so it never appears in the list.
    return sorted({name for name in names if name and name != "[%None]"})


async def persona_choices(context: Any, *, selected: str = "") -> list[dict[str, str]]:
    """The dropdown, as data the page can render without knowing AstrBot's shapes.

    ``selected`` is the persona currently resolved for the bound conversation, kept
    at the top so the common case -- "the one it already uses" -- is the default
    rather than something the operator has to re-identify in a list.
    """
    names = await available_personas(context)
    if selected and selected != "[%None]" and selected not in names:
        names = [selected] + names
    return [{"value": name, "label": name} for name in names]
