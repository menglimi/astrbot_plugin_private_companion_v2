"""Bounded, content-free outcomes for inbound messages that receive no reply.

Two polarities share this one owner, and keeping them apart is the whole point:
an event the plugin never owned is *not* a failure and produces no platform log
at all, while an event whose reply was genuinely expected and then not delivered
always does. Only ``UNMET`` reaches the log; ``SUPPRESSED`` stays a ledger row
so the dashboard can still explain why a message was passed over.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from logging import getLogger
import hashlib
import re
from uuid import uuid4

from companion_v2.execution.models import stamp


logger = getLogger(__name__)

_REASON_CODE = re.compile(r"[a-zA-Z0-9_.-]{1,96}\Z")
_PART_CODE = re.compile(r"[a-zA-Z0-9_.:-]{1,96}\Z")
_RETAINED_EVENTS = 500
# The one line an operator reads. Every field is a code, counter, pointer or
# duration: no admitted message body and no prompt text can reach it.
_LINE = "[CompanionV2][reply] stage=%s turn=%s expected=true reason=%s"

# ``unmet`` is the only polarity that logs. Anything the plugin never claimed,
# never targeted or was told to keep quiet about is recorded as ``suppressed``.
UNMET = "unmet"
SUPPRESSED = "suppressed"
LEVELS = ("info", "warning")
# Distinguishes "this turn was already reported" from "this window is full".
_ALREADY_REPORTED = object()

# A turn is reported once. A repeated reason inside a window keeps exactly one
# line as well and counts the rest, so a whole route failing at once cannot turn
# one diagnosis into a flood. Both windows are module constants because the
# process is the unit that floods, not one call.
_RATE_WINDOW = timedelta(seconds=60)
_RATE_KEYS = 256
_LOGGED_KEYS = 512
_WINDOWED: dict[str, tuple[datetime, int]] = {}
_LOGGED: dict[tuple[str, str], None] = {}


def reset_reply_log() -> None:
    """Forget every reply window. Only a fresh process or a test needs this."""
    _WINDOWED.clear()
    _LOGGED.clear()


class InboundNoReplyLedger:
    def __init__(self, runtime):
        self.runtime = runtime

    def record(self, *, reason_code: str, observed_at: datetime, channel: str,
               origin_key: str | None = None, event_ref: str | None = None,
               code: str | None = None) -> str:
        if not isinstance(reason_code, str) or not _REASON_CODE.fullmatch(reason_code):
            reason_code = "inbound_processing_failed"
        if not isinstance(code, str) or not _REASON_CODE.fullmatch(code):
            code = None
        if channel not in ("private", "group", "unknown"):
            channel = "unknown"
        if not isinstance(origin_key, str) or not origin_key or len(origin_key) > 512:
            origin_key = None
        if not isinstance(event_ref, str) or len(event_ref) != 32 or not event_ref.isalnum():
            event_ref = uuid4().hex
        with self.runtime.transaction() as connection:
            # Re-resolving one inbound must not overwrite or duplicate the row
            # that already carries its original outcome.
            connection.execute("""INSERT INTO inbound_no_replies
                (event_ref, origin_key, channel, reason_code, observed_at, code)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_ref) DO NOTHING""",
                (event_ref, origin_key, channel, reason_code, stamp(observed_at), code))
            connection.execute("""DELETE FROM inbound_no_replies
                WHERE event_ref NOT IN (
                    SELECT event_ref FROM inbound_no_replies
                    ORDER BY observed_at DESC, rowid DESC LIMIT ?
                )""", (_RETAINED_EVENTS,))
        return event_ref

    def emit(self, *, expectation: str, stage: str, turn: str, reason_code: str,
             observed_at: datetime, channel: str = "unknown", origin_key: str | None = None,
             event_ref: str | None = None, part: str | None = None, code: str | None = None,
             level: str = "warning", started_at: datetime | None = None,
             ms: float | None = None) -> str | None:
        """Resolve one inbound: ledger row always, platform line only when expected.

        Returns the reference of the logged line, or ``None`` when this polarity
        is deliberately silent.
        """
        if expectation not in (UNMET, SUPPRESSED):
            raise ValueError("a reply outcome is either unmet or suppressed")
        if level not in LEVELS:
            raise ValueError("a reply outcome is logged as info or warning")
        if not isinstance(turn, str) or not turn:
            raise ValueError("a reply outcome needs its turn reference")
        if not isinstance(observed_at, datetime):
            raise ValueError("a reply outcome needs the time it was observed")
        parts = None
        if expectation is UNMET:
            key = event_ref if isinstance(event_ref, str) and event_ref else turn
            parts = self._rate_limited(reason_code, key, observed_at)
        reference = self.record(reason_code=reason_code, observed_at=observed_at, channel=channel,
                                origin_key=origin_key, event_ref=event_ref, code=code)
        if expectation is SUPPRESSED:
            # Preserve the bounded dashboard record without logging intentional silence.
            self.record(reason_code=reason_code, observed_at=observed_at, channel=channel,
                        origin_key=origin_key, event_ref=event_ref, code=code)
            return None
        if parts is _ALREADY_REPORTED:
            # Do not create another ledger row when the same turn is resolved again.
            return None
        if parts is None:
            # Silent in the log, but the ledger still counted this one.
            return None
        self._log(stage=stage, turn=turn, reason_code=reason_code, parts=parts, part=part,
                  code=code, level=level, started_at=started_at, observed_at=observed_at, ms=ms)
        return reference

    def _rate_limited(self, reason_code: str, key: str, observed_at: datetime) -> dict | None:
        """Per-turn dedup, then one line plus a count per reason window.

        Returns the line's own fields, ``None`` when this window already printed
        the reason, or ``_ALREADY_REPORTED`` when this turn was reported before.
        """
        seen = (key, reason_code)
        if seen in _LOGGED:
            return _ALREADY_REPORTED
        _LOGGED[seen] = None
        if len(_LOGGED) > _LOGGED_KEYS:
            for stale in list(_LOGGED)[:-_LOGGED_KEYS]:
                _LOGGED.pop(stale, None)
        previous, hits = _WINDOWED.get(reason_code, (None, 0))
        if previous is not None and observed_at - previous < _RATE_WINDOW:
            _WINDOWED[reason_code] = (previous, hits + 1)
            return None
        _WINDOWED[reason_code] = (observed_at, 0)
        if len(_WINDOWED) > _RATE_KEYS:
            for stale in sorted(_WINDOWED, key=lambda item: _WINDOWED[item][0])[:-_RATE_KEYS]:
                _WINDOWED.pop(stale, None)
        return {"hits": hits} if hits else {}

    def _log(self, *, stage, turn, reason_code, parts, part, code, level, started_at, observed_at, ms) -> None:
        if ms is None and started_at is not None:
            ms = max(0.0, (observed_at - started_at).total_seconds() * 1000)
        line = _LINE % (stage, turn, reason_code)
        if parts.get("hits"):
            # Lines this window collapsed into the current one.
            line += " hits=%d" % (parts["hits"] + 1)
        if isinstance(part, str) and _PART_CODE.fullmatch(part):
            line += " part=" + part
        if isinstance(code, str) and _REASON_CODE.fullmatch(code):
            line += " code=" + code
        line += " ms=%.0f" % (ms if isinstance(ms, (int, float)) else 0.0)
        if level == "info":
            logger.info(line)
        else:
            logger.warning(line)
