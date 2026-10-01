"""Optional local meal-time opportunities for the original private conversation."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskError, digest, stamp

from .configuration import local_time
from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


WINDOW = timedelta(minutes=45)


class MealContactEvents:
    def __init__(self, contacts):
        self.contacts = contacts
        self.runtime = contacts.runtime

    def _window(self, preferences):
        """How long the meal slot stays open, from the configured follow-up width.

        Defaults to the original hard-coded 45 minutes, so an installation that
        never touches the field behaves exactly as before.
        """
        minutes = int(preferences.values.get("meal_care_followup_minutes") or 45)
        return timedelta(minutes=minutes)

    def _slots(self, context, preferences, at):
        if not preferences.values["meal_checkin_enabled"] or preferences.reason("meal"):
            return ()
        zone = ZoneInfo(preferences.values["quiet_timezone"])
        day = at.astimezone(zone).date()
        window = self._window(preferences)
        slots = []
        for name, field, label in (("lunch", "meal_lunch_time", "午餐"),
                                   ("dinner", "meal_dinner_time", "晚餐")):
            wall_time = local_time(preferences.values[field])
            opened = datetime.combine(day, wall_time, tzinfo=zone).astimezone(timezone.utc)
            resolved_local = opened.astimezone(zone)
            if resolved_local.date() != day or resolved_local.time().replace(tzinfo=None) != wall_time:
                continue
            if opened <= at < opened + window:
                opportunity = Opportunity("meal-" + digest([context.key, day.isoformat(), name]),
                    context.scope, opened, opened + window)
                marker = {"slot": name, "local_date": day.isoformat(),
                          "opened_at": stamp(opportunity.opened_at), "expires_at": stamp(opportunity.expires_at)}
                slots.append((opportunity, marker, label))
        return tuple(slots)

    def select(self, context, preferences, at):
        for opportunity, marker, label in self._slots(context, preferences, at):
            task_id = self.contacts.task_id(context, opportunity)
            if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)) or self.runtime.read_one(
                    "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)):
                continue
            thought = Thought("meal-checkin-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
                f"当前是对方当地{label}时段。可以视原对话自然问候，也可以跳过；不知道对方是否吃饭，"
                "不要催促或将时段说成对方已用餐的事实。",
                EvidenceSnapshot(context.scope, at), 1.0)
            return opportunity, (ContactIntent("meal", thought),), marker
        return None

    def validate(self, context, marker, at):
        if type(marker) is not dict or set(marker) != {"slot", "local_date", "opened_at", "expires_at"}:
            raise TaskError("contact_meal_invalid", "meal opportunity requires its original local slot")
        preferences = self.contacts.preferences.read(context, observed_at=at).unwrap()
        if not any(candidate == marker for _, candidate, _ in self._slots(context, preferences, at)):
            raise TaskError("contact_meal_expired", "the original meal slot is no longer current")
