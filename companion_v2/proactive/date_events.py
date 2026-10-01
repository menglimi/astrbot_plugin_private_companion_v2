"""Opt-in greetings for explicit recurring dates and fixed Gregorian holidays."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from companion_v2.conversation.date_context import FIXED_HOLIDAYS, lunar_date_parts
from companion_v2.execution.models import TaskError, digest, require, stamp

from .configuration import important_dates, local_time
from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


WINDOW = timedelta(minutes=45)


def _gregorian_days_until(day, month, day_of_month):
    """Whole days from ``day`` to the next occurrence of month/day, or None.

    Four years are searched so 29 February reaches its real next occurrence rather
    than being dropped. A date that exists in no searched year (30 February) is
    skipped rather than guessed at.
    """
    for year in range(day.year, day.year + 5):
        try:
            candidate = day.replace(year=year, month=month, day=day_of_month)
        except ValueError:
            continue
        ahead = (candidate - day).days
        if ahead >= 0:
            return ahead
    return None


class DateContactEvents:
    def __init__(self, contacts):
        self.contacts, self.runtime = contacts, contacts.runtime

    def _entries_for(self, day, configured, lookahead):
        """Date labels for this day, plus any the lookahead window reaches.

        With ``lookahead`` at 0 this is exactly the V1 behaviour: only today's own
        labels, and no extra key in the marker. Above 0 an approaching date is
        included with ``days_until``, so the role may mention it *before* the day
        rather than only on it. ``days_until`` appears only on upcoming entries, so
        a same-day greeting keeps its original shape. The window looks forward only.
        """
        entries = []
        fixed = FIXED_HOLIDAYS.get((day.month, day.day))
        if fixed:
            entries.append({"basis": "fixed_gregorian_holiday", "label": fixed})
        lunar = lunar_date_parts(day) if any(item.calendar == "lunar" for item in configured) else None
        for item in configured:
            if item.calendar == "gregorian":
                if (item.month, item.day) == (day.month, day.day):
                    entries.append({"basis": "operator_configured_recurring_date", "label": item.label})
                elif lookahead:
                    ahead = _gregorian_days_until(day, item.month, item.day)
                    if ahead is not None and 0 < ahead <= lookahead:
                        entries.append({"basis": "operator_configured_recurring_date",
                                        "label": item.label, "days_until": ahead})
            elif (item.calendar == "lunar" and lunar is not None
                    and (item.month, item.day, item.leap_month) == (lunar[1], lunar[2], lunar[3])):
                entries.append({"basis": "operator_configured_lunar_date", "label": item.label,
                                "lunar_year": lunar[0], "leap_month": lunar[3]})
        return entries

    def _slot(self, context, preferences, at):
        if not preferences.values["date_checkin_enabled"] or preferences.reason("greeting"):
            return None
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        day = at.astimezone(zone).date()
        configured = important_dates(preferences.values["important_dates"])
        entries = self._entries_for(
            day, configured, int(preferences.values.get("important_date_lookahead_days") or 0))
        if not entries:
            return None
        wall = local_time(preferences.values["date_checkin_time"])
        opened = datetime.combine(day, wall, tzinfo=zone).astimezone(timezone.utc)
        resolved = opened.astimezone(zone)
        if (resolved.date() != day or resolved.time().replace(tzinfo=None) != wall
                or not opened <= at < opened + WINDOW):
            return None
        opportunity = Opportunity("date-" + digest([context.key, day.isoformat()]),
            context.scope, opened, opened + WINDOW)
        marker = {"local_date": day.isoformat(), "timezone": zone.key,
                  "opened_at": stamp(opened), "expires_at": stamp(opportunity.expires_at),
                  "entries": entries}
        return opportunity, marker

    def select(self, context, preferences, at):
        slot = self._slot(context, preferences, at)
        if slot is None:
            return None
        opportunity, marker = slot
        task_id = self.contacts.task_id(context, opportunity)
        if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
            return None
        labels = "、".join(("固定公历节日" if item["basis"] == "fixed_gregorian_holiday" else
                            "管理员配置农历日期" if item["basis"] == "operator_configured_lunar_date" else
                            "管理员配置公历日期") + "「" + item["label"] + "」" for item in marker["entries"])
        thought = Thought("date-greeting-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            f"按已配置时区，今天是{marker['local_date']}，日期标签有：{labels}。"
            "固定公历节日与管理员设置的公历或农历纪念日期只提供问候语境；不知道这是否与对方个人有关，"
            "也不代表放假或约定已经发生。合适时自然问候，否则跳过。",
            EvidenceSnapshot(context.scope, at), 1.0)
        return opportunity, (ContactIntent("greeting", thought),), marker

    def validate(self, context, marker, at):
        if type(marker) is not dict or set(marker) != {
                "local_date", "timezone", "opened_at", "expires_at", "entries"}:
            raise TaskError("contact_date_invalid", "date greeting requires its original local day")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        current = self._slot(context, preferences, at)
        if current is None or current[1] != marker:
            raise TaskError("contact_date_expired", "original date greeting is no longer current")
