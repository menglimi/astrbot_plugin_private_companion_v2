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

from .contact_models import ContactIntent
from .configuration import GROUP
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
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind
from .persona_judge import KIND as JUDGE_KIND
from .service import CONTACT_KIND


class ContactSchedule:
    def __init__(self, contacts, messages, *, notify, role_life=None, role_journal=None, calendar=None,
                 role_state=None, weather_port=None, weather_alert_port=None, balance_port=None, news_port=None,
                 screen_peek=None):
        self.contacts, self.messages, self.notify = contacts, messages, notify
        self.tasks, self.runtime = contacts.tasks, contacts.runtime
        self.screen_peek = screen_peek
        self._workers, self._cursor, self._closed = {}, 0, False
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

    def _origin(self, context, batch_id, at):
        row = self.runtime.read_one("""SELECT f.state AS flow_state, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
            ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,))
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

    def validate_origin(self, context, origin, at):
        current, row, event = self._origin(context, origin["batch_id"], at)
        event_markers = {"activity_event", "journal_event", "calendar_event", "date_event",
                         "meal_event", "weather_event", "weather_change_event", "official_alert_event",
                         "balance_event", "news_event", "screen_event", "greeting_event", "burst_event"}
        if current != {key: value for key, value in origin.items() if key not in event_markers}:
            raise TaskError("contact_conversation_changed", "automatic opportunity lost its original conversation")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        if not preferences.values["automatic_enabled"]:
            raise TaskError("contact_automatic_disabled", "automatic opportunities are disabled")
        idle = self.rhythm.idle_seconds(preferences)
        if at < max(event.received_at, datetime.fromisoformat(row["created_at"])) + timedelta(seconds=idle):
            raise TaskError("contact_conversation_active", "original conversation has not reached its configured idle time")
        interaction = None
        if "greeting_event" in origin or "burst_event" in origin or not event_markers.intersection(origin):
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

    def _plan(self, row, at):
        context = TaskContext.restore(json.loads(row["context_json"]))
        # 主动权限：操作员收回 proactive.contact 之后，这一轮直接不做。
        # 刻意**不写任何状态**——写进 proactive_contacts 会被判成"已退休"，
        # 等于把这个人永久封死；这里只是这一轮不联系，下一轮重新评估。
        if self.contacts.proactive_denied(context, at=at):
            return None
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        self.contacts._adopt(context, preferences)
        if not preferences.values["automatic_enabled"]:
            return None
        origin, batch, event = self._origin(context, row["batch_id"], at)
        first = max(event.received_at, datetime.fromisoformat(batch["created_at"])) + timedelta(
            seconds=self.rhythm.idle_seconds(preferences))
        if at < first:
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
        interval = timedelta(seconds=self.rhythm.base_interval_seconds(preferences))
        if burst is None and self.runtime.read_one("""SELECT 1 FROM execution_tasks WHERE origin_key = ? AND kind = ?
                AND created_at > ? LIMIT 1""", (context.key, CONTACT_KIND, stamp(at - interval))):
            return None
        if self.calendar_events is not None:
            candidate, more = self.calendar_events.select(context, preferences, at)
            if candidate is not None:
                opportunity, intents, marker = candidate
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
                return context, opportunity, intents, batch["role_instruction"], {**origin, "calendar_event": marker}
            if more:
                return None
        if self._appointment_silence(context, preferences, at):
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
                return None
        candidate = self.screen_events.select(context, preferences, at)
        if candidate is not None:
            opportunity, intents, marker = candidate
            intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                context.scope, at, (event.source, *intent.thought.evidence.sources)))) for intent in intents)
            return context, opportunity, intents, batch["role_instruction"], {**origin, "screen_event": marker}
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
        if preferences.unanswered_paused(unanswered) or preferences.reason("chat"):
            return None
        if self.rhythm.closing_hold(preferences, at, interaction=interaction, last_contact=last_contact) is not None:
            return None
        if burst is not None:
            opportunity = Opportunity("burst-" + digest([context.key, stamp(burst.opened_at), burst.index]),
                context.scope, burst.opened_at, burst.expires_at)
            task_id = self.contacts.task_id(context, opportunity)
            if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                    or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
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
            return None
        opened = first + ((at - first) // interval) * interval
        expires = opened + min(interval, timedelta(minutes=5))
        if at >= expires:
            return None
        if not self.rhythm.hour_allows(context, preferences, opened):
            return None
        opportunity = Opportunity("automatic-" + digest([context.key, stamp(opened)]), context.scope, opened, expires)
        task_id = self.contacts.task_id(context, opportunity)
        if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)) or self.runtime.read_one(
                "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)):
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

    async def _run(self, plan):
        context, opportunity, intents, instruction, origin = plan
        try:
            if "weather_pending" in origin:
                prepared = await self.weather_events.prepare(context, origin["weather_pending"])
                if prepared is None:
                    return Outcome.failed("contact_weather_unavailable", "current weather could not be verified")
                opportunity, intents, marker = prepared
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "weather_pending"}
                origin["weather_event"] = marker
            if "weather_change_pending" in origin:
                prepared = await self.weather_change_events.prepare(context, origin["weather_change_pending"])
                if prepared is None:
                    return Outcome.failed("contact_weather_change_unavailable", "weather change was not verified")
                opportunity, intents, marker = prepared
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "weather_change_pending"}
                origin["weather_change_event"] = marker
            if "official_alert_pending" in origin:
                prepared = await self.official_alert_events.prepare(context, origin["official_alert_pending"])
                if prepared is None:
                    return Outcome.failed("contact_official_alert_unavailable", "official alert was not verified")
                opportunity, intents, marker = prepared
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "official_alert_pending"}
                origin["official_alert_event"] = marker
            if "balance_pending" in origin:
                prepared = await self.balance_events.prepare(context, origin["balance_pending"])
                if prepared is None:
                    return Outcome.failed("contact_balance_unavailable", "service balance did not create a current contact")
                opportunity, intents, marker = prepared
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "balance_pending"}
                origin["balance_event"] = marker
            if "news_pending" in origin:
                prepared = await self.news_events.prepare(context, origin["news_pending"])
                if prepared is None:
                    return Outcome.failed("contact_news_unavailable", "no current news item was verified")
                opportunity, intents, marker = prepared
                _, _, event = self._origin(context, origin["batch_id"], self.tasks.now())
                intents = tuple(replace(intent, thought=replace(intent.thought, evidence=EvidenceSnapshot(
                    context.scope, self.tasks.now(), (event.source, *intent.thought.evidence.sources))))
                    for intent in intents)
                origin = {key: value for key, value in origin.items() if key != "news_pending"}
                origin["news_event"] = marker
            return await self.contacts.contact(context, opportunity, intents, role_instruction=instruction,
                selection_seed=opportunity.opportunity_id, automatic_origin=origin)
        except Exception:
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

    def advance(self):
        if self._closed:
            return
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
            return
        held = self.runtime.read_one("SELECT COUNT(*) FROM execution_attempts WHERE lane = 'background' AND slot_held = 1", ())[0]
        available = self.tasks.limits.background_slots - held - len(self._workers) - len(self._judges)
        self._advance_judges(self.tasks.now(), max(0, available))
        held = self.runtime.read_one("SELECT COUNT(*) FROM execution_attempts WHERE lane = 'background' AND slot_held = 1", ())[0]
        available = self.tasks.limits.background_slots - held - len(self._workers) - len(self._judges)
        if available <= 0:
            return
        rows = self.runtime.read_all("""SELECT f.sequence, b.* FROM conversation_flows f
            JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.sequence > ?
            AND NOT EXISTS (SELECT 1 FROM conversation_flows newer WHERE newer.route_key = f.route_key AND newer.sequence > f.sequence)
            ORDER BY f.sequence LIMIT 16""", (self._cursor,))
        for row in rows:
            self._cursor = row["sequence"]
            if row["origin_key"] in self._workers:
                continue
            now = self.tasks.now()
            if self._peek(row, now):
                continue
            try:
                with self.runtime.transaction():
                    plan = self._plan(row, now)
            except TaskError as error:
                if error.code in ("supervisor_fenced", "supervisor_generation_conflict"):
                    raise
                continue
            if plan is not None:
                context, _, _, _, origin = plan
                if self._busy_hold(context, origin, now) is not None:
                    continue
                worker = asyncio.create_task(self._run(plan), name="companion:automatic-contact:" + row["origin_key"])
                self._workers[row["origin_key"]] = worker
                worker.add_done_callback(lambda done: self.notify())
                available -= 1
                if available == 0:
                    return
        if len(rows) < 16:
            self._cursor = 0

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
