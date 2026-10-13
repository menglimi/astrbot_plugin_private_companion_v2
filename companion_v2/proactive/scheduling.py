"""Bounded automatic opportunities from the latest accepted private conversation.

The original conversation owns identity and persona. Existing task IDs are the
durable occurrence ledger, so restart never replays a decision or a missed slot.
"""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json

from companion_v2.conversation.busy_gate import (SettingsReader, busy_context, busy_exempt_source,
                                                proactive_defer_until, readable_items)
from companion_v2.conversation.messages import event_from_document
from companion_v2.execution.models import QUEUED, TaskContext, TaskError, digest, require, stamp
from companion_v2.foundation.outcome import Outcome
from companion_v2.delivery.history import VERSION as HISTORY_VERSION

from .contact_models import ContactIntent
from .configuration import GROUP, PURPOSES
from .calendar_events import CalendarContactEvents
from .date_events import DateContactEvents
from .events import ActivityContactEvents
from .greetings import GreetingContactEvents
from .journal_events import JournalContactEvents
from .meal_events import MealContactEvents
from .rhythm import ContactRhythm
from .weather_events import WeatherContactEvents
from .weather_change_events import WeatherChangeContactEvents
from .official_alert_events import OfficialAlertContactEvents
from .balance_events import BalanceContactEvents
from .news_events import NewsContactEvents
from .screen_events import ScreenContactEvents
from .relationship_events import RelationshipContactEvents
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind
from .persona_judge import KIND as JUDGE_KIND
from .preferences import ContactPreferences
from .service import CONTACT_KIND


DIAGNOSTIC_ENVIRONMENT_VARIANTS = {
    "weather": ("weather_events", "weather_event", "天气观测生产器"),
    "weather_change": ("weather_change_events", "weather_change_event", "天气变化生产器"),
    "official_alert": ("official_alert_events", "official_alert_event", "官方预警生产器"),
    "service_balance": ("balance_events", "balance_event", "服务余额生产器"),
    "external_news": ("news_events", "news_event", "外部资讯生产器"),
}


class ContactSchedule:
    def __init__(self, contacts, messages, *, notify, role_life=None, role_journal=None, calendar=None,
                 role_state=None, weather_port=None, weather_alert_port=None, balance_port=None, news_port=None,
                 screen_peek=None):
        self.contacts, self.messages, self.notify = contacts, messages, notify
        self.tasks, self.runtime = contacts.tasks, contacts.runtime
        self.screen_peek = screen_peek
        self._maintenance_contexts = {}
        self._workers, self._cursor, self._native_cursor, self._closed = {}, 0, 0, False
        self._judges = {}
        self.rhythm = ContactRhythm(contacts.runtime)
        self.events = ActivityContactEvents(contacts, role_life) if role_life is not None else None
        self.journal_events = JournalContactEvents(contacts, role_journal) if role_journal is not None else None
        self.calendar_events = CalendarContactEvents(contacts, calendar) if calendar is not None else None
        self.date_events = DateContactEvents(contacts)
        self.greeting_events = GreetingContactEvents(contacts, role_state)
        self.meal_events = MealContactEvents(contacts)
        self.weather_events = WeatherContactEvents(contacts, role_state, weather_port) if role_state is not None else None
        self.weather_change_events = WeatherChangeContactEvents(
            contacts, role_state, weather_port) if role_state is not None else None
        self.official_alert_events = OfficialAlertContactEvents(
            contacts, role_state, weather_alert_port) if role_state is not None else None
        self.balance_events = BalanceContactEvents(contacts, balance_port)
        self.news_events = NewsContactEvents(contacts, news_port)
        self.screen_events = ScreenContactEvents(contacts)
        self.relationship_events = RelationshipContactEvents(contacts, messages)
        self._diagnostics_cleaned_at = None

    @staticmethod
    def _diagnostic_key(kind, value=""):
        return digest(["proactive-schedule", kind, value])

    @staticmethod
    def _conversation_ref(row):
        if row is None:
            return None
        keys = row.keys() if hasattr(row, "keys") else ()
        identifier = row["batch_id"] if "batch_id" in keys else row.get("batch_id")
        if identifier is None:
            identifier = row["turn_id"] if "turn_id" in keys else row.get("turn_id")
        return digest(["contact-conversation", str(identifier)]) if identifier else None

    def _write_diagnostic(self, key, at, stage, outcome, reason_code, *, conversation_ref=None,
                          purpose=None, next_at=None, minimum_interval=60):
        diagnostic_key = self._diagnostic_key(*key)
        values = (diagnostic_key, conversation_ref, stamp(at), str(stage)[:48], str(outcome),
                  str(reason_code)[:96], str(purpose)[:48] if purpose else None,
                  stamp(next_at) if next_at is not None else None)
        try:
            current = self.runtime.read_one("SELECT * FROM proactive_schedule_diagnostics WHERE diagnostic_key = ?",
                                            (diagnostic_key,))
            if current is not None and tuple(current[name] for name in (
                    "diagnostic_key", "conversation_ref", "stage", "outcome", "reason_code", "purpose", "next_at")) == (
                    values[0], values[1], values[3], values[4], values[5], values[6], values[7]):
                previous = datetime.fromisoformat(current["observed_at"])
                if at - previous < timedelta(seconds=minimum_interval):
                    return
            with self.runtime.transaction() as connection:
                connection.execute("""INSERT INTO proactive_schedule_diagnostics
                    (diagnostic_key, conversation_ref, observed_at, stage, outcome, reason_code, purpose, next_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(diagnostic_key) DO UPDATE SET conversation_ref = excluded.conversation_ref,
                        observed_at = excluded.observed_at, stage = excluded.stage, outcome = excluded.outcome,
                        reason_code = excluded.reason_code, purpose = excluded.purpose, next_at = excluded.next_at""",
                    values)
                if (self._diagnostics_cleaned_at is None
                        or at - self._diagnostics_cleaned_at >= timedelta(hours=6)):
                    connection.execute("DELETE FROM proactive_schedule_diagnostics WHERE diagnostic_key != ? AND observed_at < ?",
                        (self._diagnostic_key("coordinator"), stamp(at - timedelta(days=90))))
                    self._diagnostics_cleaned_at = at
        except Exception:
            # Diagnostic persistence must not block contact authorization or scheduling.
            return

    def _note_window(self, context, row, at, stage, outcome, reason_code, *, purpose=None, next_at=None):
        self._write_diagnostic(("window", context.key), at, stage, outcome, reason_code,
            conversation_ref=self._conversation_ref(row), purpose=purpose, next_at=next_at)

    def _note_coordinator(self, at, outcome, reason_code):
        self._write_diagnostic(("coordinator", ""), at, "scheduler", outcome, reason_code,
                               minimum_interval=15)

    def diagnostic_for(self, context, *, at=None, host_state="running"):
        at = at or self.tasks.now()
        window = self.runtime.read_one("SELECT * FROM proactive_schedule_diagnostics WHERE diagnostic_key = ?",
            (self._diagnostic_key("window", context.key),))
        coordinator = self.runtime.read_one("SELECT * FROM proactive_schedule_diagnostics WHERE diagnostic_key = ?",
            (self._diagnostic_key("coordinator"),))

        def age_seconds(row):
            if row is None:
                return None
            try:
                return max(0.0, (at - datetime.fromisoformat(row["observed_at"])).total_seconds())
            except (TypeError, ValueError):
                return None

        heartbeat_age = age_seconds(coordinator)
        if host_state != "running":
            scheduler_state, scheduler_reason = "stopped", "host_" + str(host_state)[:80]
        elif coordinator is None:
            scheduler_state, scheduler_reason = "not_seen", "scheduler_heartbeat_missing"
        elif heartbeat_age is None or heartbeat_age > 45:
            scheduler_state, scheduler_reason = "stale", "scheduler_heartbeat_stale"
        elif coordinator["outcome"] == "blocked":
            scheduler_state, scheduler_reason = "blocked", coordinator["reason_code"]
        else:
            scheduler_state, scheduler_reason = "running", coordinator["reason_code"]

        evaluation = {"outcome": "not_evaluated", "stage": "scheduler",
                      "reason_code": "never_evaluated", "purpose": None,
                      "observed_at": None, "next_at": None}
        if window is not None:
            evaluation = {"outcome": window["outcome"], "stage": window["stage"],
                          "reason_code": window["reason_code"],
                          "purpose": PURPOSES.get(window["purpose"], window["purpose"])
                          if window["purpose"] else None,
                          "observed_at": window["observed_at"], "next_at": window["next_at"]}
            latest = self.latest_conversation(context)
            if self._conversation_ref(latest) != window["conversation_ref"]:
                evaluation.update(outcome="stale", stage="conversation",
                                  reason_code="newer_conversation_not_evaluated", purpose=None, next_at=None)
        return {"scheduler": {"state": scheduler_state, "reason_code": scheduler_reason,
                               "last_seen_at": coordinator["observed_at"] if coordinator else None},
                "evaluation": evaluation}

    def bind_context(self, context):
        """Bind the active staging target for source maintenance.

        Source maintenance is intentionally tied to the current role target,
        while contact opportunities still derive their identity from the latest
        conversation.  This lets a paused contact window keep its news cache
        current without inventing a message or a send permission.
        """
        self._maintenance_contexts[context.key] = context

    def _origin(self, context, batch_id, at):
        from companion_v2.conversation.native_turns import input_event, latest_scope

        row = self.runtime.read_one("""SELECT f.state AS flow_state, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,))
        native = latest_scope(self.runtime, context.scope)
        if native is not None and (row is None or native["observed_at"] >= row["created_at"]):
            if (native["turn_id"] != batch_id or native["context_key"] != context.key
                    or native["generation_state"] != "completed" or not native["role_instruction"].strip()):
                raise TaskError("contact_conversation_changed", "automatic opportunity requires the latest completed native conversation")
            self.messages.authorize(context, at)
            event = input_event(self.messages, native, at)
            return {"batch_id": batch_id, "event_key": event.scoped_key, "event_hash": digest(event),
                    "role_hash": digest(native["role_instruction"])}, native, event
        if (row is None or row["batch_id"] != batch_id or row["origin_key"] != context.key
                or row["flow_state"] != "complete" or row["state"] != "ready" or not row["role_instruction"].strip()):
            raise TaskError("contact_conversation_changed", "automatic opportunity requires the latest completed conversation")
        self.messages.authorize(context, at)
        item = self.runtime.read_one("""SELECT * FROM conversation_inputs WHERE batch_id = ? AND withdrawn = 0
            ORDER BY position DESC LIMIT 1""", (batch_id,))
        if item is None:
            raise TaskError("contact_input_unavailable", "automatic opportunity has no active original input")
        event = event_from_document(json.loads(item["event_json"]), context)
        if (event.scope != context.scope or event.principal != context.actor.principal
                or event.scoped_key != item["event_key"] or event.received_at > at):
            raise TaskError("contact_context_mismatch", "automatic input must retain its original author and window")
        source = self.messages._read_source(event.source, context, event.capability, at)
        if source.content_hash != event.input_hash or digest(source.payload) != source.content_hash:
            raise TaskError("contact_input_changed", "automatic input no longer matches its original evidence")
        origin = {"batch_id": batch_id, "event_key": item["event_key"], "event_hash": item["event_hash"],
                  "role_hash": digest(row["role_instruction"])}
        return origin, row, event

    def latest_conversation(self, context):
        """Select the actual latest input; an older completed turn is no fallback."""
        from companion_v2.conversation.native_turns import latest_scope

        legacy = self.runtime.read_one("""SELECT f.state AS flow_state, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,))
        native = latest_scope(self.runtime, context.scope)
        return native if native is not None and (legacy is None or native["observed_at"] >= legacy["created_at"]) else legacy

    def validate_origin(self, context, origin, at):
        current, row, event = self._origin(context, origin["batch_id"], at)
        event_markers = {"activity_event", "journal_event", "calendar_event", "date_event",
                         "meal_event", "weather_event", "weather_change_event", "official_alert_event",
                         "balance_event", "news_event", "screen_event", "greeting_event", "burst_event",
                         "relationship_event", "followup_event"}
        if current != {key: value for key, value in origin.items() if key not in event_markers}:
            raise TaskError("contact_conversation_changed", "automatic opportunity lost its original conversation")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        if not preferences.values["automatic_enabled"]:
            raise TaskError("contact_automatic_disabled", "automatic opportunities are disabled")
        idle = self.rhythm.idle_seconds(preferences)
        if at < max(event.received_at, datetime.fromisoformat(row["created_at"])) + timedelta(seconds=idle):
            raise TaskError("contact_conversation_active", "original conversation has not reached its configured idle time")
        interaction = None
        if ("greeting_event" in origin or "burst_event" in origin or "followup_event" in origin
                or not event_markers.intersection(origin)):
            if self.contacts.history is None:
                raise TaskError("delivery_history_unavailable", "automatic contact requires confirmed communication history")
            interaction = self.contacts.history.interaction(context, at, action=GROUP)
        if "greeting_event" in origin:
            self.greeting_events.validate(context, origin["greeting_event"], at, interaction=interaction)
        if "burst_event" in origin:
            if not self.rhythm.validate_burst(context, preferences, origin["burst_event"], at,
                    interaction=interaction):
                raise TaskError("contact_burst_changed", "original burst round changed after selection")
        if not event_markers.intersection(origin):
            if preferences.unanswered_paused(interaction["contacts_since_last_input"]):
                raise TaskError("contact_unanswered_paused", "ordinary contact is paused until the next user input")
        if "activity_event" in origin:
            if self.events is None:
                raise TaskError("contact_activity_unavailable", "automatic activity requires its original producer")
            self.events.validate(context, origin["activity_event"], at)
        if "journal_event" in origin:
            if self.journal_events is None:
                raise TaskError("contact_journal_unavailable", "automatic journal sharing requires its original producer")
            self.journal_events.validate(context, origin["journal_event"], at)
        if "calendar_event" in origin:
            if self.calendar_events is None:
                raise TaskError("contact_calendar_unavailable", "automatic reminder requires its original calendar")
            self.calendar_events.validate(context, origin["calendar_event"], at)
        if "date_event" in origin:
            self.date_events.validate(context, origin["date_event"], at)
        if "meal_event" in origin:
            self.meal_events.validate(context, origin["meal_event"], at)
        if "weather_event" in origin:
            if self.weather_events is None:
                raise TaskError("contact_weather_unavailable", "automatic weather needs its original producer")
            self.weather_events.validate(context, origin["weather_event"], at)
        if "weather_change_event" in origin:
            if self.weather_change_events is None:
                raise TaskError("contact_weather_change_unavailable", "automatic weather change needs its original producer")
            self.weather_change_events.validate(context, origin["weather_change_event"], at)
        if "official_alert_event" in origin:
            if self.official_alert_events is None:
                raise TaskError("contact_official_alert_unavailable", "official alert needs its original producer")
            self.official_alert_events.validate(context, origin["official_alert_event"], at)
        if "balance_event" in origin:
            self.balance_events.validate(context, origin["balance_event"], at)
        if "news_event" in origin:
            self.news_events.validate(context, origin["news_event"], at)
        if "screen_event" in origin:
            self.screen_events.validate(context, origin["screen_event"], at)
        if "relationship_event" in origin:
            self.relationship_events.validate(context, event, origin["relationship_event"], at)
        if "followup_event" in origin:
            self._validate_followup(context, event, origin["followup_event"], preferences, at, interaction)

    def _plan(self, row, at):
        context = TaskContext.restore(json.loads(row["context_json"]))
        # 主动权限：操作员收回 proactive.contact 之后，这一轮直接不做。
        # 刻意**不写任何状态**——写进 proactive_contacts 会被判成"已退休"，
        # 等于把这个人永久封死；这里只是这一轮不联系，下一轮重新评估。
        if self.contacts.proactive_denied(context, at=at):
            self._note_window(context, row, at, "permission", "skipped", "proactive_permission_denied")
            return None
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        self.contacts._adopt(context, preferences)
        if not preferences.values["automatic_enabled"]:
            self._note_window(context, row, at, "settings", "skipped", "automatic_contact_disabled")
            return None
        origin, batch, event = self._origin(context, row["batch_id"], at)
        first = max(event.received_at, datetime.fromisoformat(batch["created_at"])) + timedelta(
            seconds=self.rhythm.idle_seconds(preferences))
        if at < first:
            self._note_window(context, row, at, "rhythm", "skipped", "idle_period_not_elapsed", next_at=first)
            return None
        if self.contacts.history is None:
            raise TaskError("delivery_history_unavailable", "automatic contact requires confirmed communication history")
        interaction = self.contacts.history.interaction(context, at, action=GROUP)
        unanswered = interaction["contacts_since_last_input"]
        self.contacts.budget.attempts(context, preferences, at)
        self.contacts.budget.contacts(context, preferences, at)
        last_contact = self.rhythm.last_contact(context)
        # A burst continuation is timed from its own round, not from the ordinary
        # slot grid, so the coarse interval gate does not consume its slot. The
        # gate keeps its original meaning: one admitted attempt per base interval,
        # with the unanswered slowdown reserved for the ordinary slot pacing.
        burst = self.rhythm.burst_slot(context, preferences, at, interaction=interaction,
                                       last_contact=last_contact)
        base_interval = timedelta(seconds=self.rhythm.base_interval_seconds(preferences))
        if self.calendar_events is not None:
            candidate, more = self.calendar_events.select(context, preferences, at)
            if candidate is not None:
                opportunity, intents, marker = candidate
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
                return context, opportunity, intents, batch["role_instruction"], {**origin, "calendar_event": marker}
            if more:
                self._note_window(context, row, at, "sources", "pending", "calendar_source_pending")
                return None
        if self._appointment_silence(context, preferences, at):
            self._note_window(context, row, at, "rhythm", "skipped", "appointment_silence")
            return None
        candidate = self.greeting_events.select(context, preferences, at, interaction=interaction)
        if candidate is not None:
            opportunity, intents, marker = candidate
            intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                context.scope, at, (event.source,)))) for intent in intents)
            return context, opportunity, intents, batch["role_instruction"], {**origin, "greeting_event": marker}
        if self.events is not None:
            candidate, more = self.events.select(context, preferences, at)
            candidate = self._share_candidate(context, preferences, candidate)
            if candidate is not None:
                opportunity, intents, marker = candidate
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
                return context, opportunity, intents, batch["role_instruction"], {**origin, "activity_event": marker}
            if more:
                self._note_window(context, row, at, "sources", "pending", "activity_source_pending")
                return None
        if self.journal_events is not None:
            candidate, more = self.journal_events.select(context, preferences, at)
            candidate = self._share_candidate(context, preferences, candidate)
            if candidate is not None:
                opportunity, intents, marker = candidate
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
                return context, opportunity, intents, batch["role_instruction"], {**origin, "journal_event": marker}
            if more:
                self._note_window(context, row, at, "sources", "pending", "journal_source_pending")
                return None
        candidate = self.screen_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
            return context, opportunity, intents, batch["role_instruction"], {**origin, "screen_event": marker}
        candidate = self.relationship_events.select(context, preferences, event, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            return context, opportunity, intents, batch["role_instruction"], {**origin, "relationship_event": marker}
        candidate = self.date_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                context.scope, at, (event.source,)))) for intent in intents)
            return context, opportunity, intents, batch["role_instruction"], {**origin, "date_event": marker}
        candidate = self.meal_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                context.scope, at, (event.source,)))) for intent in intents)
            return context, opportunity, intents, batch["role_instruction"], {**origin, "meal_event": marker}
        if self.official_alert_events is not None:
            candidate = self.official_alert_events.select(context, preferences, at)
            if candidate is not None:
                opportunity, marker = candidate
                return context, opportunity, (), batch["role_instruction"], {**origin, "official_alert_pending": marker}
        candidate = self.balance_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, marker = candidate
            return context, opportunity, (), batch["role_instruction"], {**origin, "balance_pending": marker}
        candidate = self.news_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, marker = candidate
            return context, opportunity, (), batch["role_instruction"], {**origin, "news_pending": marker}
        if self.weather_events is not None:
            candidate = self.weather_events.select(context, preferences, at)
            if candidate is not None:
                opportunity, marker = candidate
                return context, opportunity, (), batch["role_instruction"], {**origin, "weather_pending": marker}
        if self.weather_change_events is not None:
            candidate = self.weather_change_events.select(context, preferences, at)
            if candidate is not None:
                opportunity, marker = candidate
                return context, opportunity, (), batch["role_instruction"], {**origin, "weather_change_pending": marker}
        candidate = self._followup_candidate(context, event, interaction, preferences, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            return context, opportunity, intents, batch["role_instruction"], {**origin, "followup_event": marker}
        if burst is None and self.runtime.read_one("""SELECT 1 FROM execution_tasks WHERE origin_key = ? AND kind = ?
                AND created_at > ? LIMIT 1""", (context.key, CONTACT_KIND, stamp(at - base_interval))):
            self._note_window(context, row, at, "rhythm", "skipped", "recent_attempt_cooldown")
            return None
        if preferences.unanswered_paused(unanswered):
            self._note_window(context, row, at, "rhythm", "skipped", "unanswered_pause")
            return None
        chat_reason = preferences.reason("chat")
        if chat_reason:
            reason_code = {
                "proactive_disabled": "contact_settings_disabled" if not preferences.values["enabled"]
                else "chat_purpose_disabled",
                "proactive_paused": "contact_paused",
                "proactive_quiet_hours": "quiet_hours",
            }.get(chat_reason, "contact_conditions_blocked")
            self._note_window(context, row, at, "settings", "skipped", reason_code, purpose="chat")
            return None
        closing_hold = self.rhythm.closing_hold(preferences, at, interaction=interaction, last_contact=last_contact)
        if closing_hold is not None:
            self._note_window(context, row, at, "rhythm", "skipped", "closing_silence", next_at=closing_hold)
            return None
        if burst is not None:
            opportunity = Opportunity("burst-" + digest([context.key, stamp(burst.opened_at), burst.index]),
                context.scope, burst.opened_at, burst.expires_at)
            task_id = self.contacts.task_id(context, opportunity)
            if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                    or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
                self._note_window(context, row, at, "rhythm", "skipped", "slot_already_processed", purpose="chat")
                return None
            thought = Thought("conversation-burst-" + digest([burst.origin_contact_id, burst.index]),
                opportunity, ThoughtKind.CONVERSATION,
                f"这是同一阵念头里的第{burst.index + 1}条短消息，换一个角度，不要重复上一条，也不要求对方回应。",
                EvidenceSnapshot(context.scope, at, (event.source,)), 1.0)
            return (context, opportunity, (ContactIntent("chat", thought),), batch["role_instruction"],
                    {**origin, "burst_event": burst.document()})
        interval = timedelta(seconds=self.rhythm.interval_seconds(preferences, unanswered=unanswered))
        if self.runtime.read_one("""SELECT 1 FROM execution_tasks WHERE origin_key = ? AND kind = ?
                AND created_at > ? LIMIT 1""", (context.key, CONTACT_KIND, stamp(at - interval))):
            self._note_window(context, row, at, "rhythm", "skipped", "recent_attempt_cooldown")
            return None
        opened = first + ((at - first) // interval) * interval
        expires = opened + min(interval, timedelta(minutes=5))
        if at >= expires:
            self._note_window(context, row, at, "rhythm", "skipped", "outside_contact_slot",
                              purpose="chat", next_at=opened + interval)
            return None
        if not self.rhythm.hour_allows(context, preferences, opened):
            self._note_window(context, row, at, "rhythm", "skipped", "activity_curve_skipped",
                              purpose="chat", next_at=opened + interval)
            return None
        opportunity = Opportunity("automatic-" + digest([context.key, stamp(opened)]), context.scope, opened, expires)
        task_id = self.contacts.task_id(context, opportunity)
        if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)) or self.runtime.read_one(
                "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)):
            self._note_window(context, row, at, "rhythm", "skipped", "slot_already_processed", purpose="chat")
            return None
        thought = Thought("conversation-check-in", opportunity, ThoughtKind.CONVERSATION,
            "距离最近一轮对话已有一段时间，可以看看是否有自然值得说的话；没有合适内容就跳过，不要求对方回应。",
            EvidenceSnapshot(context.scope, at, (event.source,)), 1.0)
        return context, opportunity, (ContactIntent("chat", thought),), batch["role_instruction"], origin

    def _share_candidate(self, context, preferences, candidate):
        """Apply the configured share probability to a role-share candidate only."""
        if candidate is None:
            return None
        opportunity, intents, marker = candidate
        purpose = marker.get("purpose") if isinstance(marker, dict) else None
        purpose = purpose or (intents[0].purpose if intents else "")
        if self.rhythm.share_allowed(context, preferences, opportunity.opportunity_id, purpose=purpose):
            return candidate
        return None

    @staticmethod
    def _diagnostic_preferences(preferences):
        """Allow one explicitly confirmed test, preserving sources and purposes.

        A dashboard test may be started during quiet hours or while a purpose is
        paused.  The producer still has to find its real event, window and
        source; the master switch and time gates are lifted for this one in-memory
        selection.  The normal contact worker remains responsible for all
        authorization and delivery checks.
        """
        values = dict(preferences.values)
        values["enabled"] = True
        values["quiet_enabled"] = False
        values["pause_until"] = ""
        for purpose in PURPOSES:
            values[purpose + ".pause_until"] = ""
        return ContactPreferences(preferences.snapshot, values, preferences.observed_at)

    @staticmethod
    def _diagnostic_route(route_id, label, variant=None):
        return {"id": route_id, "label": label, "variant": variant or route_id}

    async def diagnostic_candidate(self, context, purpose, *, at=None, variant=None):
        """Select one current candidate through its real producer.

        This is the source-backed counterpart of the onboarding connection
        test.  It deliberately returns no synthetic empty-evidence intent: a
        purpose without a current producer event is reported to the dashboard
        instead of being dressed up as a generic affectionate message.
        """
        if purpose not in PURPOSES:
            raise TaskError("unknown_contact_purpose", "contact purpose must be registered")
        if variant is not None and (purpose != "environment" or variant not in DIAGNOSTIC_ENVIRONMENT_VARIANTS):
            raise TaskError("contact_diagnostic_variant_invalid", "diagnostic variant is not valid for this purpose")
        if context.scope.kind.value != "private":
            raise TaskError("setup_private_window_required", "the proactive diagnostic requires the confirmed private window")
        at = at or self.tasks.now()
        row = self.latest_conversation(context)
        if row is None:
            raise TaskError("contact_diagnostic_source_required", "the selected purpose has no completed conversation source")
        origin, batch, event = self._origin(context, row["batch_id"], at)
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        preferences = self._diagnostic_preferences(preferences)

        def finish(candidate, route):
            if candidate is None:
                return None
            opportunity, intents, marker = candidate
            # The environment panel can explicitly probe the external-news
            # source alongside weather and balance.  NewsContactEvents keeps
            # its normal ``news`` purpose for ordinary proactive scheduling;
            # only this confirmed environment diagnostic presents the same
            # source through the selected environment purpose.  Keep the
            # producer receipt as ``news_event`` so source validation and the
            # programmed attribution suffix remain unchanged.
            environment_news = purpose == "environment" and route.get("id") == "news_event"
            if not intents or any(intent.purpose != purpose and
                                  not (environment_news and intent.purpose == "news")
                                  for intent in intents):
                return None
            enriched = []
            for intent in intents:
                if environment_news and intent.purpose == "news":
                    intent = replace(intent, purpose=purpose)
                sources = list(intent.thought.evidence.sources)
                if event.source not in sources:
                    sources.insert(0, event.source)
                enriched.append(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, at, tuple(sources)))))
            diagnostic_origin = {"_diagnostic": {
                "route_id": route["id"], "purpose": purpose, "batch_id": row["batch_id"],
                "event_key": event.scoped_key, "event_hash": event.input_hash,
                "role_hash": digest(batch["role_instruction"])}}
            if route["id"] != "conversation_scheduler":
                diagnostic_origin[route["id"]] = marker
            return {"opportunity": opportunity, "intents": tuple(enriched),
                    "role_instruction": batch["role_instruction"], "route": route,
                    "diagnostic_origin": diagnostic_origin}

        def direct(candidate, route_id, label, variant=None):
            return finish(candidate, self._diagnostic_route(route_id, label, variant))

        async def pending(producer, selected, route_id, label, variant=None):
            if selected is None:
                return None
            opportunity, marker = selected
            prepared = await producer.prepare(context, marker)
            return direct(prepared, route_id, label, variant)

        if purpose == "chat":
            opportunity = Opportunity("diagnostic-chat-" + digest([context.key, stamp(at)]),
                context.scope, at, at + timedelta(minutes=4))
            thought = Thought("diagnostic-chat-thought-" + digest([context.key, stamp(at)]), opportunity,
                ThoughtKind.CONVERSATION,
                "这是当前已完成私聊的主动话题测试机会；只从当前真实对话来源自然承接一点内容，没有合适内容就跳过。",
                EvidenceSnapshot(context.scope, at, (event.source,)), 1.0)
            return finish((opportunity, (ContactIntent("chat", thought),), None),
                          self._diagnostic_route("conversation_scheduler", "日常会话调度"))

        if purpose == "greeting":
            candidate = self.greeting_events.select(context, preferences, at, interaction=None)
            result = direct(candidate, "greeting_event", "问候窗口生产器")
            if result is None:
                result = direct(self.date_events.select(context, preferences, at),
                                "date_event", "纪念日期生产器")
            if result is not None:
                return result

        if purpose in ("life", "creation") and self.events is not None:
            candidate, _ = self.events.select(context, preferences, at, purpose=purpose)
            result = direct(candidate, "activity_event", "角色活动完成回执", "reading" if purpose == "creation" else "activity")
            if result is not None:
                return result
        if purpose == "life" and self.journal_events is not None:
            candidate, _ = self.journal_events.select(context, preferences, at)
            result = direct(candidate, "journal_event", "角色日记/梦境回执", "journal")
            if result is not None:
                return result

        if purpose == "screen":
            result = direct(self.screen_events.select(context, preferences, at),
                            "screen_event", "已授权屏幕分析回执", "glance")
            if result is not None:
                return result

        if purpose in ("affection", "care", "play", "repair", "invitation"):
            result = direct(self.relationship_events.select(context, preferences, event, at, purpose=purpose),
                            "relationship_event", "明确关系表达生产器", purpose)
            if result is not None:
                return result

        if purpose == "reminder" and self.calendar_events is not None:
            candidate, _ = self.calendar_events.select(context, preferences, at)
            result = direct(candidate, "calendar_event", "已接受日历约定生产器")
            if result is not None:
                return result

        if purpose == "meal":
            result = direct(self.meal_events.select(context, preferences, at),
                            "meal_event", "本地饭点生产器")
            if result is not None:
                return result

        if purpose == "followup":
            interaction = (self.contacts.history.interaction(context, at, action=GROUP)
                           if self.contacts.history is not None else None)
            result = direct(self._followup_candidate(context, event, interaction, preferences, at),
                            "followup_event", "已确认投递跟进生产器")
            if result is not None:
                return result

        if purpose == "environment":
            for variant_id, (producer_name, route_id, label) in DIAGNOSTIC_ENVIRONMENT_VARIANTS.items():
                if variant is not None and variant != variant_id:
                    continue
                producer = getattr(self, producer_name, None)
                if producer is None:
                    continue
                selected = producer.select(context, preferences, at)
                result = await pending(producer, selected, route_id, label, variant_id)
                if result is not None:
                    return result

        if purpose == "news":
            result = await pending(self.news_events, self.news_events.select(context, preferences, at),
                                   "news_event", "外部资讯生产器", "external_news")
            if result is not None:
                return result

        raise TaskError("contact_diagnostic_source_required",
                         f"当前没有可核验的「{PURPOSES[purpose]}」真实生产器契机；本次不会使用空证据或通用文案")

    def validate_diagnostic_origin(self, context, origin, at, *, purpose=None):
        if type(origin) is not dict or type(origin.get("_diagnostic")) is not dict:
            raise TaskError("contact_diagnostic_source_changed", "diagnostic contact lost its producer receipt")
        receipt = origin["_diagnostic"]
        if set(receipt) != {"route_id", "purpose", "batch_id", "event_key", "event_hash", "role_hash"}:
            raise TaskError("contact_diagnostic_source_changed", "diagnostic producer receipt is invalid")
        route_purposes = {
            "conversation_scheduler": {"chat"}, "greeting_event": {"greeting"}, "date_event": {"greeting"},
            "activity_event": {"life", "creation"}, "journal_event": {"life"}, "screen_event": {"screen"},
            "relationship_event": {"affection", "care", "play", "repair", "invitation"},
            "calendar_event": {"reminder"}, "meal_event": {"meal"}, "followup_event": {"followup"},
            "official_alert_event": {"environment"}, "balance_event": {"environment"},
            "news_event": {"news", "environment"}, "weather_event": {"environment"},
            "weather_change_event": {"environment"},
        }
        route_id = receipt["route_id"]
        if (route_id not in route_purposes or receipt["purpose"] not in route_purposes[route_id]
                or (purpose is not None and receipt["purpose"] != purpose)):
            raise TaskError("contact_diagnostic_source_changed", "diagnostic producer does not match its selected purpose")
        expected_keys = {"_diagnostic"} if route_id == "conversation_scheduler" else {"_diagnostic", route_id}
        if set(origin) != expected_keys:
            raise TaskError("contact_diagnostic_source_changed", "diagnostic producer marker does not match its route")
        _, batch, event = self._origin(context, receipt["batch_id"], at)
        if (event.scoped_key != receipt["event_key"] or event.input_hash != receipt["event_hash"]
                or digest(batch["role_instruction"]) != receipt["role_hash"]):
            raise TaskError("contact_conversation_changed", "diagnostic contact lost its original conversation or persona")

    def _followup_candidate(self, context, event, interaction, preferences, at):
        if (context.scope.kind.value != "private" or preferences.reason("followup")
                or interaction is None or self.contacts.history is None):
            return None
        row = self.runtime.read_one("""SELECT d.*, c.contact_id, c.record_json
            FROM background_deliveries d JOIN proactive_contacts c
              ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            WHERE d.origin_key = ? AND d.owner = 'proactive.contact' AND d.state = 'delivered'
              AND d.delivered_at IS NOT NULL
              AND COALESCE(json_extract(d.request_json, '$.sequence'), 0)
                    = COALESCE(json_extract(d.request_json, '$.part_count'), 1) - 1
              AND NOT EXISTS (SELECT 1 FROM background_deliveries p
                  WHERE json_extract(p.request_json, '$.source_ref') = c.contact_id
                    AND p.owner = 'proactive.contact' AND p.state != 'delivered')
            ORDER BY d.delivered_at DESC, d.delivery_id DESC LIMIT 1""", (context.key,))
        if row is None:
            return None
        saved = json.loads(row["record_json"])
        purpose = saved.get("purpose")
        if purpose in (None, "screen", "followup"):
            return None
        delivered = datetime.fromisoformat(row["delivered_at"])
        if (not interaction or interaction.get("last_input_at") is None
                or datetime.fromisoformat(interaction["last_input_at"]) > delivered):
            return None
        opened = delivered + timedelta(minutes=preferences.values["contact_followup_after_minutes"])
        if at < opened:
            return None
        latest_followup = self.runtime.read_one("""SELECT MAX(created_at) FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = 'followup'""", (context.key,))[0]
        if latest_followup and at < datetime.fromisoformat(latest_followup) + timedelta(
                minutes=preferences.values["contact_followup_cooldown_minutes"]):
            return None
        reference = self.contacts.history.reference(row)
        snapshot = {"version": HISTORY_VERSION, "context_key": context.key, "references": [reference]}
        try:
            history = self.contacts.history.read(snapshot, context, at, action=GROUP)
        except TaskError:
            return None
        if not history or history[0]["owner"] != "proactive.contact":
            return None
        expires = opened + timedelta(seconds=preferences.values["event_max_age_seconds"])
        if at >= expires:
            return None
        opportunity = Opportunity("followup-" + digest([context.key, row["contact_id"]]),
                                  context.scope, opened, expires)
        task_id = self.contacts.task_id(context, opportunity)
        if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
            return None
        marker = {"contact_id": row["contact_id"], "delivery_id": row["delivery_id"],
                  "delivered_at": row["delivered_at"], "purpose": purpose, "expires_at": stamp(expires)}
        thought = Thought("followup-thought-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            "上一条主动消息已有一段时间。只在原话仍有自然承接价值时轻轻接一句；不知道对方是否看过，也不催促回应。",
            EvidenceSnapshot(context.scope, at, (event.source,)), 1.0)
        return opportunity, (ContactIntent("followup", thought),), marker

    def _validate_followup(self, context, event, marker, preferences, at, interaction):
        if type(marker) is not dict or set(marker) != {
                "contact_id", "delivery_id", "delivered_at", "purpose", "expires_at"}:
            raise TaskError("contact_followup_invalid", "follow-up candidate marker is invalid")
        row = self.runtime.read_one("""SELECT d.*, c.contact_id, c.record_json
            FROM background_deliveries d JOIN proactive_contacts c
              ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            WHERE d.origin_key = ? AND d.owner = 'proactive.contact' AND d.state = 'delivered'
              AND d.delivered_at IS NOT NULL
              AND COALESCE(json_extract(d.request_json, '$.sequence'), 0)
                    = COALESCE(json_extract(d.request_json, '$.part_count'), 1) - 1
              AND NOT EXISTS (SELECT 1 FROM background_deliveries p
                  WHERE json_extract(p.request_json, '$.source_ref') = c.contact_id
                    AND p.owner = 'proactive.contact' AND p.state != 'delivered')
            ORDER BY d.delivered_at DESC, d.delivery_id DESC LIMIT 1""", (context.key,))
        if row is None:
            raise TaskError("contact_followup_changed", "the original delivered contact is unavailable")
        saved = json.loads(row["record_json"])
        delivered = datetime.fromisoformat(row["delivered_at"])
        if (not interaction or interaction.get("last_input_at") is None
                or datetime.fromisoformat(interaction["last_input_at"]) > delivered):
            raise TaskError("contact_followup_superseded", "a new user input superseded the original follow-up")
        opened = delivered + timedelta(minutes=preferences.values["contact_followup_after_minutes"])
        expires = opened + timedelta(seconds=preferences.values["event_max_age_seconds"])
        if (marker != {"contact_id": row["contact_id"], "delivery_id": row["delivery_id"],
                "delivered_at": row["delivered_at"], "purpose": saved.get("purpose"), "expires_at": stamp(expires)}
                or saved.get("purpose") in (None, "screen", "followup") or at < opened or at >= expires):
            raise TaskError("contact_followup_changed", "the original follow-up window changed")
        reference = self.contacts.history.reference(row)
        self.contacts.history.read({"version": HISTORY_VERSION, "context_key": context.key,
                                    "references": [reference]}, context, at, action=GROUP)
        preferences.require_contact("followup")

    def _appointment_silence(self, context, preferences, at):
        """True while a voluntary contact is too close to an accepted appointment.

        The appointment contact itself and every other event owner keep their own
        verified timing; this only holds back the contacts that have no cause of
        their own.
        """
        if self.calendar_events is None:
            return False
        return self.calendar_events.appointments.blocked(context, preferences, at)

    def _busy_hold(self, context, origin, at):
        """Resume instant while the role's own calendar is busy, else None.

        This runs at the plan boundary: nothing is enqueued there, so a contact is
        never created with a ``not_before`` that the gate would have to move later.
        Event-driven opportunities keep their own verified timing and are exempt,
        and an ordinary opportunity that expires during the busy window is gone for
        that slot instead of arriving as a late backlog.
        """
        settings = SettingsReader(self.runtime).read(context)
        if not settings.busy_reply_gate_enabled or busy_exempt_source(origin):
            return None
        busy = busy_context(readable_items(self.runtime, context), now=at, settings=settings)
        return proactive_defer_until(settings, busy, now=at)

    def _record_worker_result(self, context, origin, result, *, purpose=None, failure_stage="task_admission"):
        if result.is_success:
            task = getattr(result.value, "task", None)
            task_state = getattr(task, "state", "accepted")
            outcome = {"created": "queued", "retry_scheduled": "queued",
                       "admitted": "running"}.get(task_state, task_state)
            stage = "task_execution"
            reason_code = "contact_task_" + str(task_state)
        else:
            outcome = "failed"
            stage = failure_stage
            reason_code = result.failure.code if result.failure is not None else "contact_task_failed"
        self._note_window(context, {"batch_id": origin.get("batch_id")}, self.tasks.now(),
                          stage, outcome, reason_code, purpose=purpose)
        return result

    async def _run(self, plan):
        context, opportunity, intents, instruction, origin = plan
        purpose = intents[0].purpose if intents else None
        try:
            if "weather_pending" in origin:
                prepared = await self.weather_events.prepare(context, origin["weather_pending"])
                if prepared is None:
                    return self._record_worker_result(context, origin,
                        Outcome.failed("contact_weather_unavailable", "current weather could not be verified"),
                        purpose=purpose, failure_stage="source_preparation")
                opportunity, intents, marker = prepared
                purpose = intents[0].purpose if intents else purpose
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "weather_pending"}
                origin["weather_event"] = marker
            if "weather_change_pending" in origin:
                prepared = await self.weather_change_events.prepare(context, origin["weather_change_pending"])
                if prepared is None:
                    return self._record_worker_result(context, origin,
                        Outcome.failed("contact_weather_change_unavailable", "weather change was not verified"),
                        purpose=purpose, failure_stage="source_preparation")
                opportunity, intents, marker = prepared
                purpose = intents[0].purpose if intents else purpose
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "weather_change_pending"}
                origin["weather_change_event"] = marker
            if "official_alert_pending" in origin:
                prepared = await self.official_alert_events.prepare(context, origin["official_alert_pending"])
                if prepared is None:
                    return self._record_worker_result(context, origin,
                        Outcome.failed("contact_official_alert_unavailable", "official alert was not verified"),
                        purpose=purpose, failure_stage="source_preparation")
                opportunity, intents, marker = prepared
                purpose = intents[0].purpose if intents else purpose
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "official_alert_pending"}
                origin["official_alert_event"] = marker
            if "balance_pending" in origin:
                prepared = await self.balance_events.prepare(context, origin["balance_pending"])
                if prepared is None:
                    return self._record_worker_result(context, origin,
                        Outcome.failed("contact_balance_unavailable", "service balance did not create a current contact"),
                        purpose=purpose, failure_stage="source_preparation")
                opportunity, intents, marker = prepared
                purpose = intents[0].purpose if intents else purpose
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "balance_pending"}
                origin["balance_event"] = marker
            if "news_pending" in origin:
                prepared = await self.news_events.prepare(context, origin["news_pending"])
                if prepared is None:
                    return self._record_worker_result(context, origin,
                        Outcome.failed("contact_news_unavailable", "no current news item was verified"),
                        purpose=purpose, failure_stage="source_preparation")
                opportunity, intents, marker = prepared
                purpose = intents[0].purpose if intents else purpose
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "news_pending"}
                origin["news_event"] = marker
            purpose = intents[0].purpose if intents else purpose
            result = await self.contacts.contact(context, opportunity, intents, role_instruction=instruction,
                selection_seed=opportunity.opportunity_id, automatic_origin=origin)
            return self._record_worker_result(context, origin, result, purpose=purpose)
        except TaskError as error:
            self._note_window(context, {"batch_id": origin.get("batch_id")}, self.tasks.now(),
                              "contact_worker", "failed", error.code, purpose=purpose)
            return Outcome.failed("contact_schedule_failed", "automatic opportunity stopped without replaying its model task")
        except Exception:
            self._note_window(context, {"batch_id": origin.get("batch_id")}, self.tasks.now(),
                              "contact_worker", "failed", "contact_schedule_failed", purpose=purpose)
            return Outcome.failed("contact_schedule_failed", "automatic opportunity stopped without replaying its model task")

    def _advance_judges(self, at, available):
        """Run the outstanding persona judgements on this tick's free background slots.

        A judgement is its own supervised task, submitted when the draft was
        sealed, so it needs one background slot of its own rather than a slot
        nested inside the contact worker. A draft whose judgement can never
        complete (an attempt that died, an expired window) is archived as
        withheld instead of waiting forever or being sent unjudged.
        """
        if self.contacts.judge_runner is None or JUDGE_KIND not in self.contacts.gateway.router.profiles:
            return
        for row in self.contacts.outstanding_judgements(limit=4):
            if len(self._judges) >= available:
                return
            task_id = row["judge_task_id"]
            if task_id is None or task_id in self._judges:
                continue
            if row["judge_state"] in QUEUED:
                spec = json.loads(row["judge_record"])["spec"]
                context = TaskContext.restore(spec["context"])
                # A queued judgement past its own deadline can never be claimed.
                if datetime.fromisoformat(spec["deadline_at"]) <= at:
                    self._withhold(row, "judge_expired", "主动人格判定已过期，未判定的草稿不发送")
                    continue
                worker = asyncio.create_task(self.contacts.judge_runner.run(context, task_id),
                                             name="companion:contact-judge:" + task_id)
                self._judges[task_id] = worker
                worker.add_done_callback(lambda done: self.notify())
                continue
            self._withhold(row, "judge_unknown", "主动人格判定没有可用结果，未判定的草稿不发送")

    def _withhold(self, row, failure, reason):
        with self.runtime.transaction():
            self.contacts.persona_judge.withheld(row["origin_key"], row["contact_id"], failure, reason=reason)

    def _peek(self, row, at):
        """Schedule one autonomous Screen peek for this window, if one is due.

        A peek is its own supervised device call, so nothing here waits for the
        camera: the plan for this tick simply stays empty until the interpretation
        of the adopted original exists.
        """
        service = self.screen_peek
        if service is None:
            return False
        try:
            context = TaskContext.restore(json.loads(row["context_json"]))
            if not service.ready(context, at):
                return False
            preferences = require(self.contacts.preferences.read(context, observed_at=at))
            decision = self.screen_events.peek_due(context, preferences, at)
            if decision is None:
                return False
            return service.request(context, decision, request_ref=row["batch_id"]) is not None
        except TaskError:
            return False

    def _legacy_rows(self, cursor):
        return self.runtime.read_all("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.sequence > ?
            AND json_extract(b.context_json, '$.audience.scope.kind') = 'private'
            AND NOT EXISTS (SELECT 1 FROM conversation_flows newer WHERE newer.route_key = f.route_key AND newer.sequence > f.sequence)
            ORDER BY f.sequence LIMIT 16""", (cursor,))

    def advance(self):
        if self._closed:
            return
        now = self.tasks.now()
        for context in tuple(self._maintenance_contexts.values()):
            try:
                preferences = self.contacts.preferences.read(context, observed_at=self.tasks.now())
                if preferences.is_success:
                    self.news_events.maintain(context, preferences.unwrap())
            except (TaskError, ValueError, TypeError, AttributeError):
                # A source status must never take down the contact coordinator.
                pass
        for key, worker in tuple(self._workers.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.result()
                del self._workers[key]
        for key, worker in tuple(self._judges.items()):
            if worker.done():
                if not worker.cancelled():
                    worker.result()
                del self._judges[key]
        require(self.tasks.check_generation())
        if CONTACT_KIND not in self.contacts.gateway.router.profiles:
            self._note_coordinator(self.tasks.now(), "blocked", "contact_model_unregistered")
            return
        held = self.runtime.read_one("SELECT COUNT(*) FROM execution_attempts WHERE lane = 'background' AND slot_held = 1", ())[0]
        available = self.tasks.limits.background_slots - held - len(self._workers) - len(self._judges)
        self._advance_judges(self.tasks.now(), max(0, available))
        held = self.runtime.read_one("SELECT COUNT(*) FROM execution_attempts WHERE lane = 'background' AND slot_held = 1", ())[0]
        available = self.tasks.limits.background_slots - held - len(self._workers) - len(self._judges)
        if available <= 0:
            self._note_coordinator(self.tasks.now(), "blocked", "background_capacity_exhausted")
            return
        retained = self.runtime.read_one("SELECT COUNT(*) FROM execution_tasks", ())[0]
        if retained >= self.tasks.limits.retained_tasks:
            self._note_coordinator(self.tasks.now(), "blocked", "task_storage_full")
            return
        rows = self._legacy_rows(self._cursor)
        legacy_count = len(rows)
        from companion_v2.conversation.native_turns import project, turns_available
        native_rows = self.runtime.read_all("""SELECT n.rowid AS sequence, n.* FROM conversation_native_turns n
            WHERE n.rowid > ? AND json_extract(n.context_json, '$.audience.scope.kind') = 'private'
            AND NOT EXISTS (SELECT 1 FROM conversation_native_turns newer
                WHERE newer.context_key = n.context_key
                AND (newer.observed_at > n.observed_at OR newer.observed_at = n.observed_at AND newer.rowid > n.rowid))
            ORDER BY n.rowid LIMIT 16""", (self._native_cursor,)) if turns_available(self.runtime) else ()
        rows = (*rows, *(project(row) for row in native_rows))
        for row in rows:
            if isinstance(row, dict) and row.get("execution_path") == "astrbot_core":
                self._native_cursor = row["sequence"]
            else:
                self._cursor = row["sequence"]
            if row["origin_key"] in self._workers:
                continue
            now = self.tasks.now()
            if self._peek(row, now):
                context = TaskContext.restore(json.loads(row["context_json"]))
                self._note_window(context, row, now, "sources", "pending", "screen_observation_pending")
                continue
            try:
                with self.runtime.transaction():
                    plan = self._plan(row, now)
            except TaskError as error:
                context = TaskContext.restore(json.loads(row["context_json"]))
                self._note_window(context, row, now, "validation", "failed", error.code)
                if error.code in ("supervisor_fenced", "supervisor_generation_conflict"):
                    raise
                continue
            if plan is not None:
                context, _, intents, _, origin = plan
                purpose = intents[0].purpose if intents else None
                circuit_until = self.contacts.platform_circuit.cooldown_until(context, at=now)
                if circuit_until is not None:
                    self._note_window(context, row, now, "delivery_admission", "skipped", "platform_circuit_open",
                                      purpose=purpose, next_at=circuit_until)
                    continue
                busy_until = self._busy_hold(context, origin, now)
                if busy_until is not None:
                    self._note_window(context, row, now, "busy_gate", "skipped", "conversation_busy",
                                      purpose=purpose, next_at=busy_until)
                    continue
                worker = asyncio.create_task(self._run(plan), name="companion:automatic-contact:" + row["origin_key"])
                self._workers[row["origin_key"]] = worker
                self._note_window(context, row, now, "task_queue", "queued", "candidate_queued", purpose=purpose)
                worker.add_done_callback(lambda done: self.notify())
                available -= 1
                if available == 0:
                    self._note_coordinator(self.tasks.now(), "running", "contact_schedule_running")
                    return
        if legacy_count < 16:
            self._cursor = 0
        if len(native_rows) < 16:
            self._native_cursor = 0
        self._note_coordinator(self.tasks.now(), "running", "contact_schedule_running")

    @property
    def active_handles(self):
        return tuple("automatic-contact-" + key for key in self._workers) + tuple(
            "contact-judge-" + key for key in self._judges)

    def cancel_running(self):
        self._closed = True
        for worker in tuple(self._workers.values()):
            worker.cancel()
        for worker in tuple(self._judges.values()):
            worker.cancel()
        if self.events is not None:
            self.events.close()
        if self.journal_events is not None:
            self.journal_events.close()
        if self.calendar_events is not None:
            self.calendar_events.close()
        if self.weather_events is not None:
            self.weather_events.close()
        if self.weather_change_events is not None:
            self.weather_change_events.close()
        if self.official_alert_events is not None:
            self.official_alert_events.close()
        self.balance_events.close()
        self.news_events.close()
        self.screen_events.close()

    async def close(self):
        self.cancel_running()
        workers = tuple(self._workers.values()) + tuple(self._judges.values())
        if workers:
            await asyncio.wait(workers, timeout=0.25)
        for table in (self._workers, self._judges):
            for key, worker in tuple(table.items()):
                if worker.done():
                    if not worker.cancelled():
                        worker.exception()
                    del table[key]
