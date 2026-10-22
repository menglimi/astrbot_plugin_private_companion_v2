"""Count automatic group continuations by reply event, never by message part."""

from .group_observation import parse_moment


FOLLOW_UP_REASONS = frozenset({"active_follow_up", "reply_follow_up"})


def progress(turns, *, at, seconds):
    sent = [turn for turn in turns
            if turn.get("send_state") == "returned" and turn.get("send_returns", 0) > 0
            and (when := parse_moment(turn.get("returned_at"))) is not None and when <= at]
    sent.sort(key=lambda turn: turn["admitted_at"])
    used, anchor, start = 0, None, None
    for turn in sent:
        admitted = parse_moment(turn.get("admitted_at"))
        continuing = turn.get("reason") in FOLLOW_UP_REASONS
        expired = anchor is not None and admitted is not None and (admitted - anchor).total_seconds() > seconds
        if not continuing or expired:
            used = 0
            start = admitted
        if continuing:
            # Snapshots keep the count after older observations are evicted.
            # Only a first send return writes one; tool loops reuse the event.
            saved = turn.get("followup_turns")
            used = saved if anchor is None and type(saved) is int and saved > 0 else used + 1
        returned = parse_moment(turn["returned_at"])
        anchor = max(anchor, returned) if continuing and anchor is not None else returned
    active = anchor is not None and 0 <= (at - anchor).total_seconds() <= seconds
    pending = sum(turn.get("reason") in FOLLOW_UP_REASONS
                  and turn.get("state") in ("admitted", "inflight")
                  and turn.get("send_state") not in ("unknown", "denied", "failed")
                  and turn.get("send_returns", 0) == 0
                  and (when := parse_moment(turn.get("admitted_at"))) is not None
                  and (start is None or when >= start)
                  and 0 <= (at - when).total_seconds() <= seconds for turn in turns)
    return {"used_turns": used if active else 0, "pending_turns": pending,
            "anchor_at": anchor.isoformat() if anchor is not None else None, "active": active}
