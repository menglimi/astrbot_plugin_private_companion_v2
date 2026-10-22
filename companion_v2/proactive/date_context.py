"""Private, forward-only context for explicitly configured recurring dates."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from companion_v2.conversation.date_context import lunar_date_parts

from .configuration import important_dates


INSTRUCTION = (
    "近期日期仅来自当前私聊明确配置的标签，只说明日期临近，不证明用户与日期的关系、活动已发生或安排了庆祝；相关时自然提及，不为显得熟悉而强行开场，也不把标签写入长期记忆。"
)


def project_important_dates(at: datetime, settings: dict[str, object]) -> dict[str, object]:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("important dates require a timezone-aware datetime")
    if type(settings) is not dict or set(settings) != {"important_dates", "lookahead_days", "timezone"}:
        raise ValueError("important date settings are invalid")
    lookahead = settings["lookahead_days"]
    if type(lookahead) is not int or not 0 <= lookahead <= 30:
        raise ValueError("important date lookahead is invalid")
    timezone_name = settings["timezone"]
    if type(timezone_name) is not str or not timezone_name.strip():
        raise ValueError("important date timezone is invalid")
    try:
        zone = ZoneInfo(timezone_name)
        configured = important_dates(settings["important_dates"])
    except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
        raise ValueError("important date settings are invalid") from error

    local_day = at.astimezone(zone).date()
    lunar_items = tuple(item for item in configured if item.calendar == "lunar")
    entries = []
    for offset in range(lookahead + 1):
        day = local_day + timedelta(days=offset)
        for item in configured:
            matches = ((item.month, item.day) == (day.month, day.day)
                       if item.calendar == "gregorian" else False)
            if item.calendar == "lunar" and lunar_items:
                lunar = lunar_date_parts(day)
                matches = bool(lunar and (item.month, item.day, item.leap_month) == lunar[1:])
            if matches:
                entries.append({"label": item.label, "date": day.isoformat(), "days_until": offset,
                                "calendar": item.calendar})
    entries.sort(key=lambda item: (item["days_until"], item["label"]))
    return {"basis": "operator_configured_recurring_dates", "timezone": zone.key, "entries": entries}


__all__ = ["INSTRUCTION", "project_important_dates"]
