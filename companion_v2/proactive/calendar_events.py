"""Upcoming accepted commitments as revision-bound private contact candidates."""

from collections import OrderedDict
from datetime import datetime, timedelta
import json

from companion_v2.agenda.appointments import AppointmentSilence, occurrence_at, upcoming_occurrences
from companion_v2.agenda.models import AgendaError, Schedule
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import SourceRef, SubjectKind, VersionRef
from companion_v2.identity_policy.private_domain import source_ref
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


SOURCE_OWNER = "proactive.calendar"
PAGE_SIZE = 32
POLL_INTERVAL = timedelta(seconds=30)


class CalendarContactEvents:
    def __init__(self, contacts, calendar):
        if contacts.runtime is not calendar.runtime:
            raise ValueError("calendar contacts must share the original calendar ledger")
        self.contacts, self.calendar, self.runtime = contacts, calendar, calendar.runtime
        self._scans = OrderedDict()
        self.appointments = AppointmentSilence(calendar)
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self._scans.clear()
        self.appointments.close()

    def _record(self, context, identifier, at):
        self.calendar.access.check(context, "calendar.read", at=at)
        record = self.calendar.records.get(context, identifier)
        if record is None:
            raise TaskError("contact_calendar_unavailable", "original commitment is unavailable")
        self.calendar.access.evidence(context, record["sources"], at=at)
        if (record["kind"] != "commitment" or record["state"] != "accepted"
                or record.get("reminder_id") or not any(
                    type(item) is dict and item.get("kind") == SubjectKind.HUMAN.value
                    for item in record.get("accepted_by", ()))):
            raise TaskError("contact_calendar_unconfirmed", "only a human-accepted commitment without a separate reminder qualifies")
        return record

    @staticmethod
    def _window(preferences):
        """The appointment lead and lag this relationship configured.

        ``lead`` may be 0, which means the contact opens exactly at the
        appointment instant ("到点开口"); an opportunity always stays open for at
        least one minute so the send is still possible. ``lag`` bounds how long
        after the appointment the contact may still be generated; a longer
        outage drops the slot instead of replaying a stale appointment.
        """
        lead = timedelta(minutes=preferences.values["appointment_lead_minutes"])
        lag = timedelta(minutes=preferences.values["appointment_lag_minutes"])
        return lead, lag

    @classmethod
    def _upcoming(cls, record, start, end):
        return upcoming_occurrences(record, start, end)

    @staticmethod
    def _opportunity(context, record, sequence, due, lead, lag):
        opened = due - lead
        expires = max(due + lag, opened + timedelta(minutes=1))
        return Opportunity("calendar-" + digest([context.key, record["id"], sequence, stamp(due)]),
            context.scope, opened, expires)

    @staticmethod
    def _material(record, sequence, due):
        schedule = Schedule.restore(record["schedule"])
        return {"event": "accepted_commitment_upcoming", "title": record["title"],
            "detail": record["detail"], "sequence": sequence,
            "starts_at": stamp(due), "local_start": due.astimezone(schedule.zone()).isoformat(),
            "timezone": schedule.timezone_name, "duration_minutes": record["duration_minutes"],
            "meaning": "这是人类明确接受、尚未开始的约定；不能据此声称已经见面、出席或完成。"}

    @staticmethod
    def _source_ref(context, record, sequence, due):
        identifier = "contact-calendar-source-" + digest(
            [context.key, record["id"], record["revision"], sequence, stamp(due)])
        return SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1),
            datetime.fromisoformat(record["updated_at"]))

    def _project(self, context, record, sequence, due, at):
        reference = self._source_ref(context, record, sequence, due)
        receipt = {"context": json.loads(encode(context)), "id": record["id"],
            "revision": record["revision"], "sequence": sequence, "starts_at": stamp(due),
            "record_hash": digest(record)}
        payload = json.dumps({**self._material(record, sequence, due), "_receipt": receipt},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(
                SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
            link(self.runtime, reference, tuple(source_ref(item) for item in record["sources"]), at)
        require(self.contacts.sources.validate_reference_for_audience(
            reference, recipient=context.actor.subject, observed_at=at))
        return reference

    def _validate_source(self, source, at):
        try:
            payload = json.loads(source.payload)
            receipt = payload.pop("_receipt")
            if type(payload) is not dict or type(receipt) is not dict or set(receipt) != {
                    "context", "id", "revision", "sequence", "starts_at", "record_hash"}:
                raise ValueError("invalid calendar source receipt")
            context = TaskContext.restore(receipt["context"])
            record = self._record(context, receipt["id"], at)
            due = occurrence_at(record, receipt["sequence"])
            if (due is None or source.reference != self._source_ref(context, record, receipt["sequence"], due)
                    or source.audience != context.audience or record["revision"] != receipt["revision"]
                    or digest(record) != receipt["record_hash"] or stamp(due) != receipt["starts_at"]
                    or payload != self._material(record, receipt["sequence"], due)
                    or source.content_hash != digest(source.payload)):
                raise ValueError("original calendar commitment changed")
        except TaskError:
            raise
        except (AgendaError, KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_calendar_source_changed", "original commitment cannot attest this source") from error

    def _known(self, context, opportunity):
        identifier = self.contacts.task_id(context, opportunity)
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (identifier,)) or self.runtime.read_one(
            "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (identifier,))

    def select(self, context, preferences, at):
        """Scan one calendar page; the durable contact task prevents repeat decisions."""
        token = preferences.snapshot.resolution_token
        state = self._scans.get(context.key)
        if state is None or state[0] != token:
            state = (token, "", at)
        self._scans[context.key] = state
        self._scans.move_to_end(context.key)
        while len(self._scans) > 1024:
            self._scans.popitem(last=False)
        _, cursor, ready_at = state
        if ready_at > at:
            return None, False
        if preferences.reason("reminder"):
            self._scans[context.key] = (token, "", at + POLL_INTERVAL)
            return None, False
        try:
            self.calendar.access.check(context, "calendar.read", at=at)
        except TaskError as error:
            if error.code in ("supervisor_fenced", "supervisor_generation_conflict"):
                raise
            self._scans[context.key] = (token, "", at + POLL_INTERVAL)
            return None, False
        page_cursor = cursor
        page = self.calendar.inventory(context, after_id=cursor, limit=PAGE_SIZE)
        next_cursor = page["next_cursor"] or ""
        lead, lag = self._window(preferences)
        # The scan only has to reach occurrences that could be open right now; the
        # opportunity itself decides, so "到点" (lead 0) opens exactly at the instant.
        scan_start, scan_end = at - lag - timedelta(seconds=1), at + max(lead, timedelta(minutes=1)) + lag
        for record in page["items"]:
            cursor = record["id"]
            if record["kind"] != "commitment" or record["state"] != "accepted" or record.get("reminder_id"):
                continue
            try:
                self._record(context, record["id"], at)
                occurrences = self._upcoming(record, scan_start, scan_end)
            except (TaskError, AgendaError, KeyError, TypeError, ValueError):
                continue
            for sequence, due in occurrences:
                opportunity = self._opportunity(context, record, sequence, due, lead, lag)
                if not opportunity.opened_at <= at < opportunity.expires_at:
                    continue
                if self._known(context, opportunity):
                    continue
                try:
                    source = self._project(context, record, sequence, due, at)
                except (TaskError, AgendaError, KeyError, TypeError, ValueError):
                    continue
                marker = {"id": record["id"], "revision": record["revision"],
                    "sequence": sequence, "starts_at": stamp(due), "record_hash": digest(record),
                    "purpose": "reminder"}
                thought = Thought("calendar-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
                    "一项已被人类明确接受的约定即将开始，可以自然地简短提醒；不合适就跳过，不说成已经发生。",
                    EvidenceSnapshot(context.scope, at, (source,)), 1.0)
                self._scans[context.key] = (token, page_cursor, at)
                return (opportunity, (ContactIntent("reminder", thought),), marker), True
        more = next_cursor != ""
        self._scans[context.key] = (token, next_cursor, at if more else at + POLL_INTERVAL)
        return None, more

    def validate(self, context, marker, at):
        if not isinstance(marker, dict) or set(marker) != {
                "id", "revision", "sequence", "starts_at", "record_hash", "purpose"}:
            raise TaskError("contact_calendar_invalid", "automatic reminder requires its exact original occurrence")
        record = self._record(context, marker["id"], at)
        try:
            due = occurrence_at(record, marker["sequence"])
        except (AgendaError, KeyError, TypeError, ValueError) as error:
            raise TaskError("contact_calendar_changed", "original occurrence changed") from error
        if (due is None or record["revision"] != marker["revision"] or digest(record) != marker["record_hash"]
                or stamp(due) != marker["starts_at"] or marker["purpose"] != "reminder"):
            raise TaskError("contact_calendar_changed", "original commitment changed after selection")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        lead, lag = self._window(preferences)
        if not due - lead <= at < max(due + lag, due - lead + timedelta(minutes=1)):
            raise TaskError("contact_calendar_expired", "commitment is no longer approaching")
        preferences.require_contact("reminder")
