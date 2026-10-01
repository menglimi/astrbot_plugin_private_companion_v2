"""Accepted calendar commitments as appointment timing facts.

The agenda already owns the commitment, its revision and its human acceptance,
and ``proactive.calendar`` already turns an upcoming accepted commitment into a
contact opportunity. This module adds the two appointment facts the delivery
chain still lacked and keeps them in the same original calendar records:

* when an appointment contact may open (an explicit lead, and an explicit lag
  after the appointment instant, so "开口" can mean "到点" instead of "提前");
* the silence window directly before an accepted appointment, during which a
  voluntary contact without a cause is held back.
"""

from collections import OrderedDict
from datetime import datetime, timedelta

from companion_v2.execution.models import TaskError

from .models import AgendaError, Schedule


POLL_INTERVAL = timedelta(seconds=30)
MAX_TRACKED_WINDOWS = 1024
APPOINTMENT_KIND = "commitment"
APPOINTMENT_STATE = "accepted"


def upcoming_occurrences(record, start, end):
    """Occurrence instants of one record inside ``(start, end)``, closed exceptions included.

    Month-end, leap-day and DST arithmetic stays in ``Schedule``; this only picks
    the instants that fall strictly inside the caller's window.
    """
    schedule = Schedule.restore(record["schedule"])
    occurrences = {}
    try:
        sequence = schedule.first_at_or_after(start)
        while sequence is not None:
            original = schedule.at(sequence)
            if original is None or original >= end:
                break
            due = occurrence_at(record, sequence)
            if due is not None and start < due < end:
                occurrences[sequence] = due
            sequence += 1
    except AgendaError:
        pass
    for key, value in record["exceptions"].items():
        if not value:
            continue
        due = datetime.fromisoformat(value)
        if start < due < end:
            occurrences[int(key)] = due
    return sorted(occurrences.items(), key=lambda item: (item[1], item[0]))


def occurrence_at(record, sequence):
    """One occurrence instant, honoring a moved exception; ``None`` when closed."""
    schedule = Schedule.restore(record["schedule"])
    due = schedule.at(sequence)
    if str(sequence) in record["exceptions"]:
        value = record["exceptions"][str(sequence)]
        due = datetime.fromisoformat(value) if value else None
    return due


class AppointmentSilence:
    """The pre-appointment silence window of one relationship, read from its own calendar.

    The scan is throttled per window exactly like the appointment contact scan,
    so a one-second scheduler tick never turns into a full calendar walk. A
    calendar that cannot be read is reported as "no known appointment": silence
    is a courtesy bound, not an authorization, so an unreadable calendar must not
    be turned into a new blocker for a contact that has its own authorization.
    """

    def __init__(self, calendar):
        self.calendar, self.runtime = calendar, calendar.runtime
        self._scans = OrderedDict()

    def close(self):
        self._scans.clear()

    def hold(self, context, preferences, at):
        """The next appointment instant inside the configured window, or ``None``."""
        minutes = preferences.values["appointment_pre_silence_minutes"]
        if minutes <= 0:
            return None
        token = preferences.snapshot.resolution_token
        state = self._scans.get(context.key)
        if state is None or state[0] != token:
            state = (token, None, at)
        if state[2] > at:
            return state[1] if state[1] is not None and at < state[1] else None
        hold = self._scan(context, at, minutes)
        self._scans[context.key] = (token, hold, at + POLL_INTERVAL)
        self._scans.move_to_end(context.key)
        while len(self._scans) > MAX_TRACKED_WINDOWS:
            self._scans.popitem(last=False)
        return hold if hold is not None and at < hold else None

    def _scan(self, context, at, minutes):
        end = at + timedelta(minutes=minutes)
        try:
            self.calendar.access.check(context, "calendar.read", at=at)
            page = self.calendar.occurrences(context, start=at, end=end)
        except (TaskError, AgendaError, KeyError, TypeError, ValueError):
            return None
        upcoming = []
        for item in page["items"]:
            if item["kind"] != APPOINTMENT_KIND or item["state"] != APPOINTMENT_STATE:
                continue
            try:
                start = datetime.fromisoformat(item["start"])
            except (TypeError, ValueError):
                continue
            if at < start <= end:
                upcoming.append(start)
        return min(upcoming) if upcoming else None

    def blocked(self, context, preferences, at):
        return self.hold(context, preferences, at) is not None
