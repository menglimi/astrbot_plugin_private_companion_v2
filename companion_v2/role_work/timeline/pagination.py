"""Runtime-local cursors seal query bounds; they never confer read authority."""

import base64
from datetime import datetime
import hashlib
import hmac
import json
import secrets

from companion_v2.execution.models import TaskError, encode, stamp
from companion_v2.foundation.refs import normalize_utc


KINDS = ("activity", "diary", "dream", "growth")


def timestamp(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("timeline bounds require ISO timestamps with an explicit timezone")
    return stamp(normalize_utc(datetime.fromisoformat(value), field="timeline time"))


def terms(kinds, time_start, time_end):
    kinds = list(KINDS) if kinds is None else kinds
    if (type(kinds) is not list or not kinds or any(type(k) is not str or k not in KINDS for k in kinds)
            or len(set(kinds)) != len(kinds)):
        raise ValueError("choose unique timeline kinds")
    start = timestamp(time_start) if time_start is not None else None
    end = timestamp(time_end) if time_end is not None else None
    if start is not None and end is not None and start > end:
        raise ValueError("timeline start must precede its end")
    return {"kinds": sorted(kinds), "time_start": start, "time_end": end}


class TimelineCursors:
    def __init__(self):
        self._key = secrets.token_bytes(32)

    def seal(self, snapshot, after):
        payload = encode({**snapshot, "after": after}).encode("utf-8")
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature + payload).decode("ascii")

    def restore(self, token, context, at, *, kinds, time_start, time_end):
        try:
            if type(token) is not str or not 1 <= len(token) <= 8192:
                raise ValueError("invalid cursor")
            raw = base64.b64decode(token, altchars=b"-_", validate=True)
            signature, payload = raw[:32], raw[32:]
            if not hmac.compare_digest(signature, hmac.new(self._key, payload, hashlib.sha256).digest()):
                raise ValueError("expired or altered cursor")
            snapshot = json.loads(payload)
            if snapshot["context_key"] != context.key or snapshot["captured_at"] > stamp(at):
                raise ValueError("cursor belongs to another context or time")
            query = snapshot["query"]
            if terms(kinds if kinds is not None else query["kinds"],
                     time_start if time_start is not None else query["time_start"],
                     time_end if time_end is not None else query["time_end"]) != query:
                raise ValueError("cursor query changed")
            return snapshot
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise TaskError("timeline_cursor_invalid", "start a fresh query after changing filters, context or runtime") from None
