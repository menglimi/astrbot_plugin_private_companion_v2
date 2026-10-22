"""Resolve an explicit past calendar day for bounded memory recall."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo


_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUMBER = r"(?:[0-9]{1,2}|[零〇一二两三四五六七八九十廿卅]{1,3})"
_DATED = re.compile(
    rf"(?<![0-9])(?P<year>[12][0-9]{{3}})[年./-](?P<month>{_NUMBER})[月./-](?P<day>{_NUMBER})(?:日|号)?"
)
_MONTH_DAY = re.compile(rf"(?<![0-9])(?P<month>{_NUMBER})月(?P<day>{_NUMBER})(?:日|号)?")


def _number(raw: str) -> int | None:
    if raw.isdecimal():
        return int(raw)
    if raw.startswith("廿") or raw.startswith("卅"):
        base = 20 if raw[0] == "廿" else 30
        rest = raw[1:]
        return base + _DIGITS[rest] if rest in _DIGITS else base if not rest else None
    if "十" in raw:
        left, right = raw.split("十", 1)
        if left and left not in _DIGITS or right and right not in _DIGITS:
            return None
        return (10 if not left else _DIGITS[left] * 10) + (0 if not right else _DIGITS[right])
    if len(raw) == 1:
        return _DIGITS.get(raw)
    return None


def absolute_day_window(text: str, now: datetime, timezone_name: str) -> tuple[datetime, datetime] | None:
    """Return [local midnight, next midnight) for an explicit, nonfuture day."""
    if not isinstance(text, str) or not isinstance(now, datetime):
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except (KeyError, TypeError, ValueError):
        return None
    today = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(zone).date()
    match = _DATED.search(text) or _MONTH_DAY.search(text)
    if match is None:
        return None
    month, day = _number(match["month"]), _number(match["day"])
    if month is None or day is None:
        return None
    years = (int(match["year"]),) if "year" in match.re.groupindex and match["year"] else range(today.year, today.year - 5, -1)
    for year in years:
        try:
            selected = date(year, month, day)
        except ValueError:
            continue
        if selected > today:
            continue
        start = datetime.combine(selected, time.min, zone)
        end = datetime.combine(selected + timedelta(days=1), time.min, zone)
        return start, end
    return None
