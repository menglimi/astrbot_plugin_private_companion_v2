"""Strictly normalize OneBot peer-history response wrappers.

The installed SDK unwraps the action's data. Injected readers may also keep an
envelope. The caller still validates the exact private peer, message id and
component contract; this helper only removes a single transport wrapper.
"""

from __future__ import annotations


def extract_history_messages(result):
    """Return one unwrapped ``messages`` list, or ``None`` for an unknown shape.

    Normalize these explicit container forms, without inferring platform support:
    a direct list, ``{"messages": [...]}``, ``{"data": [...]}``, or
    ``{"data": {"messages": [...]}}``.  Ambiguous envelopes are rejected so a
    stale or mixed response cannot silently select a different message list.
    """

    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return None
    for depth in range(2):
        if "status" in result and result["status"] != "ok":
            return None
        if "retcode" in result and (
                type(result["retcode"]) not in (int, str) or result["retcode"] not in (0, "0")):
            return None
        if "messages" in result:
            # Even a malformed second payload is ambiguous, not a fallback.
            messages = result["messages"]
            return messages if "data" not in result and isinstance(messages, list) else None
        if depth:
            return None
        result = result.get("data")
        if isinstance(result, list):
            return result
        if not isinstance(result, dict):
            return None
    return None
