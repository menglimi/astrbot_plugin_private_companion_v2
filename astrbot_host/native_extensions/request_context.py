"""Own native hook material without rewriting the shared conversation prefix."""

from __future__ import annotations

import re
from collections.abc import Mapping


_TURN_PREFIX = "<companion_v2_native_"


def _text(part):
    if isinstance(part, Mapping):
        return part.get("text") if part.get("type") == "text" else None
    return getattr(part, "text", None) if getattr(part, "type", None) == "text" else None


def clear_turn_contexts(request):
    """Drop only our prior turn material, including material from paused services."""
    parts = getattr(request, "extra_user_content_parts", None)
    if isinstance(parts, list):
        parts[:] = [part for part in parts
                    if not (isinstance(_text(part), str) and _text(part).startswith(_TURN_PREFIX))]


def set_turn_context(request, name, text=""):
    """Replace one service's live facts; AstrBot sends but does not persist them."""
    prefix = f"{_TURN_PREFIX}{name}>\n"
    parts = getattr(request, "extra_user_content_parts", None)
    if isinstance(parts, list):
        parts[:] = [part for part in parts
                    if not (isinstance(_text(part), str) and _text(part).startswith(prefix))]
    elif text:
        parts = []
        request.extra_user_content_parts = parts
    if not text:
        return

    from astrbot.core.agent.message import TextPart

    parts.append(TextPart(text=prefix + text.strip() + f"\n</companion_v2_native_{name}>").mark_as_temp())


def set_system_instruction(request, name, text=""):
    """Keep configuration guidance stable and replace only its complete owned block."""
    start = f"<!-- companion_v2_native_{name}:start -->"
    end = f"<!-- companion_v2_native_{name}:end -->"
    block = f"\n\n{start}\n{text.strip()}\n{end}" if text else ""
    prompt = str(getattr(request, "system_prompt", "") or "")
    pattern = re.compile(r"\n\n" + re.escape(start) + r"\n.*?\n" + re.escape(end), re.DOTALL)
    replaced = False

    def replace_owned(match):
        nonlocal replaced
        value = "" if replaced else block
        replaced = True
        return value

    prompt = pattern.sub(replace_owned, prompt)
    request.system_prompt = prompt if replaced else prompt + block
