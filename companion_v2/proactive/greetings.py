"""Day anchors and one bounded insomnia window, in the relationship's local time.

V1 produced one morning, noon and evening greeting window per local day and kept
one low-pressure message for nights the role was awake. V2 keeps the same anchors
as explicit local windows, computed on the relationship's existing
``quiet_timezone``, and routes both through the single automatic contact
opportunity: one durable decision per anchor and local day, and one per night
slot.

Neither path can bypass a rule: an anchor or night message is still a voluntary
contact that answers to its purpose switch, the pause, the quiet hours, the
24-hour allowance and every send-boundary recheck. The configured night window in
particular does **not** exempt a message from quiet hours -- a night message is
only possible where the relationship's quiet hours leave room for it.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskError, digest, require, stamp

from .configuration import anchor_window, local_time
from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


ANCHOR_PURPOSE = "greeting"
INSOMNIA_PURPOSE = "care"
DAY_ANCHORS = ("morning_greeting", "noon_greeting", "evening_greeting")
ANCHOR_MEANING = {
    "morning_greeting": ("刚睡醒，想打个招呼", "刚醒"),
    "noon_greeting": ("中午有些犯困，想打个招呼", "午饭后那会儿"),
    "evening_greeting": ("晚上闲下来时，想打个招呼", "天暗下来那会儿")}


def window_bounds(value):
    """A configured anchor window as two validated local times."""
    start, _, end = anchor_window(value).partition("-")
    return local_time(start), local_time(end)


def _minutes(wall):
    return wall.hour * 60 + wall.minute


class GreetingContactEvents:
    """Morning/noon/evening anchors plus the bounded insomnia night slot."""

    def __init__(self, contacts, role_state=None):
        if role_state is not None and contacts.runtime is not role_state.runtime:
            raise ValueError("greeting contacts must share the original role runtime")
        self.contacts, self.role_state, self.runtime = contacts, role_state, contacts.runtime

    # ---- shared helpers --------------------------------------------------
    @staticmethod
    def _zone(preferences):
        return ZoneInfo(preferences.values["quiet_timezone"])

    def _idle_ok(self, preferences, at, interaction):
        """The shorter anchor idle gate; a very recent input postpones the greeting."""
        minutes = preferences.values["greeting_idle_minutes"]
        if minutes <= 0 or interaction is None:
            return True
        last = interaction.get("last_input_at")
        if not last:
            return True
        return at >= datetime.fromisoformat(last) + timedelta(minutes=minutes)

    def _sleep_hint(self, context, at):
        """The role's own live sleep condition as a hint only, when it is readable."""
        if self.role_state is None:
            return ""
        try:
            state = self.role_state.read(context, at=at)
        except (TaskError, ValueError, TypeError, KeyError):
            return ""
        conditions = (state.get("values") or {}).get("conditions") or []
        texts = [item.get("text", "") for item in conditions
                 if isinstance(item, dict) and item.get("kind") == "sleep" and item.get("text")]
        return texts[0][:200] if texts else ""

    # ---- day anchors -----------------------------------------------------
    def _anchor_slot(self, context, preferences, at):
        if not preferences.values["enable_daily_greetings"] or preferences.reason(ANCHOR_PURPOSE):
            return None
        zone = self._zone(preferences)
        local = at.astimezone(zone)
        day, minute = local.date(), local.hour * 60 + local.minute
        midnight = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        for name in DAY_ANCHORS:
            start, end = window_bounds(preferences.values["greeting_" + name.split("_")[0] + "_window"])
            if not _minutes(start) <= minute < _minutes(end):
                continue
            opened = midnight + timedelta(minutes=_minutes(start))
            expires = midnight + timedelta(minutes=_minutes(end))
            opportunity = Opportunity("greeting-" + digest([context.key, name, day.isoformat()]),
                context.scope, opened.astimezone(timezone.utc), expires.astimezone(timezone.utc))
            marker = {"kind": "day_anchor", "anchor": name, "local_date": day.isoformat(),
                      "timezone": zone.key, "opened_at": stamp(opportunity.opened_at),
                      "expires_at": stamp(opportunity.expires_at)}
            return opportunity, marker
        return None

    # ---- insomnia night --------------------------------------------------
    def _night(self, preferences, at):
        """The current night slot: a bounded, evenly divided window around local midnight."""
        limit = preferences.values["insomnia_night_daily_limit"]
        if limit <= 0:
            return None
        zone = self._zone(preferences)
        local = at.astimezone(zone)
        start = local_time(preferences.values["insomnia_night_start"])
        end = local_time(preferences.values["insomnia_night_end"])
        if start == end:
            return None
        wall = local.time().replace(tzinfo=None)
        if start < end:
            if not start <= wall < end:
                return None
            night = local.date()
        elif wall >= start:
            night = local.date()
        elif wall < end:
            night = local.date() - timedelta(days=1)
        else:
            return None
        midnight = datetime.combine(night, datetime.min.time(), tzinfo=zone)
        opened = midnight + timedelta(hours=start.hour, minutes=start.minute)
        closed = midnight + timedelta(days=1, hours=end.hour, minutes=end.minute)
        width = (closed - opened) / limit
        index = min(limit - 1, max(0, int((local.astimezone(zone) - opened) / width)))
        return {"night_key": night.isoformat(), "slot": index, "limit": limit, "zone": zone.key,
                "opened": (opened + width * index).astimezone(timezone.utc),
                "expires": (opened + width * (index + 1)).astimezone(timezone.utc)}

    def _insomnia_slot(self, context, preferences, at):
        if not preferences.values["allow_insomnia_night_message"] or preferences.reason(INSOMNIA_PURPOSE):
            return None
        night = self._night(preferences, at)
        if night is None:
            return None
        if preferences.values["insomnia_require_sleep_state"] and not self._sleep_hint(context, at):
            return None
        opportunity = Opportunity("insomnia-" + digest([context.key, night["night_key"], night["slot"]]),
            context.scope, night["opened"], night["expires"])
        marker = {"kind": "insomnia_night", "night_key": night["night_key"], "slot": night["slot"],
                  "slot_limit": night["limit"], "timezone": night["zone"],
                  "opened_at": stamp(opportunity.opened_at), "expires_at": stamp(opportunity.expires_at)}
        return opportunity, marker

    # ---- selection and validation ---------------------------------------
    def _slot(self, context, preferences, at, interaction=None):
        slot = self._insomnia_slot(context, preferences, at)
        if slot is None:
            slot = self._anchor_slot(context, preferences, at)
        if slot is None or not self._idle_ok(preferences, at, interaction):
            return None
        return slot

    def select(self, context, preferences, at, interaction=None):
        slot = self._slot(context, preferences, at, interaction=interaction)
        if slot is None:
            return None
        opportunity, marker = slot
        task_id = self.contacts.task_id(context, opportunity)
        if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
            return None
        if marker["kind"] == "insomnia_night":
            hint = self._sleep_hint(context, at)
            summary = ("角色此刻处在夜里还醒着的时段，可以留一句低压力的话；不报时、不追问、不要求回应。"
                       + ("角色状态里有一条睡眠相关的临时状况：" + hint if hint else ""))
            purpose = INSOMNIA_PURPOSE
        else:
            why, topic = ANCHOR_MEANING[marker["anchor"]]
            summary = (f"按已配置时区，现在的本地日期是{marker['local_date']}，这是「{topic}」的问候窗口：{why}。"
                       "这是低压力问候，不代表对方刚醒、刚吃完饭或已经空闲；没有自然说法就跳过。")
            purpose = ANCHOR_PURPOSE
        thought = Thought("greeting-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
                          summary, EvidenceSnapshot(context.scope, at), 1.0)
        return opportunity, (ContactIntent(purpose, thought),), marker

    def validate(self, context, marker, at, interaction=None):
        if type(marker) is not dict or marker.get("kind") not in ("day_anchor", "insomnia_night"):
            raise TaskError("contact_greeting_invalid", "greeting contact requires its original local slot")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        current = self._slot(context, preferences, at, interaction=interaction)
        if current is None or current[1] != marker:
            raise TaskError("contact_greeting_expired", "original greeting slot is no longer current")
        preferences.require_contact(INSOMNIA_PURPOSE if marker["kind"] == "insomnia_night" else ANCHOR_PURPOSE)
