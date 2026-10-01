"""Authorized projections of recorded role life, without executing background work."""

from dataclasses import dataclass
import json
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.role_work.journal.models import JournalKey, JournalKind


READ_ACTION = "role.life.read"
SCAN_LIMIT = 32


@dataclass(frozen=True)
class LifeMaterial:
    reference: dict
    purpose: str
    payload: str


@dataclass(frozen=True)
class LifeCandidates:
    variants: tuple[tuple[LifeMaterial, ...], ...]
    truncated: bool
    skipped: int


def material(reference, purpose, payload):
    return LifeMaterial(reference, purpose, json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False))


class RoleLifeContextReader:
    """The read boundary for one private participant, current role and exact scope.

    References retain the selected representation. A summary created later cannot
    silently replace a body, and neither representation becomes factual evidence.
    """

    def __init__(self, life, journal, tasks):
        if life.runtime is not journal.runtime or life.runtime is not tasks.runtime:
            raise ValueError("life context must share its original owners and runtime")
        self.life, self.journal, self.tasks = life, journal, tasks
        self.runtime = tasks.runtime

    @staticmethod
    def owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def authorize(self, context, at):
        require(self.tasks.authorize_context(context, action=READ_ACTION, observed_at=at))

    def _source(self, source, context, at, content_hash=None):
        if source.scope != context.scope:
            raise TaskError("life_context_scope", "life source belongs to another conversation")
        require(self.journal.sources.validate_reference_for_audience(source,
            recipient=context.actor.subject, observed_at=at, expected_content_hash=content_hash))

    def _activity(self, activity, context, at):
        if (activity.owner != self.owner(context) or activity.scope != context.scope
                or activity.work is not None and activity.work.context_key != context.key):
            raise TaskError("life_context_scope", "activity belongs to another original authority")
        if activity.updated_at > at:
            raise TaskError("life_context_not_active", "activity is not available at this time")
        work, reading = activity.work, activity.reading
        if work is not None and work.source is not None:
            self._source(work.source, context, at, work.content_hash)
        if reading is not None:
            self._source(reading.source, context, at, reading.content_hash)
        payload = {"basis": "recorded_role_activity", "kind": work.kind if work else
                   ("reading" if reading else "activity"), "state": activity.state.value,
                   "description": activity.description, "checkpoint": activity.checkpoint,
                   "started_at": activity.started_at.isoformat(), "updated_at": activity.updated_at.isoformat()}
        if work is not None and work.due_at is not None:
            payload["planned_wake_at"] = work.due_at.isoformat()
        if work is not None and work.kind == "reading" and reading is None:
            payload["planned_reading_span"] = {"start_offset": work.start_offset,
                "end_offset": work.end_offset, "source_key": digest(work.source)}
        if reading is not None:
            payload["reading"] = {"basis": "completed_reading_receipt",
                "source_key": digest(reading.source), "start_offset": reading.start_offset,
                "end_offset": reading.end_offset, "text_length": reading.text_length,
                "covers_source": reading.covers_source, "completed_at": reading.completed_at.isoformat(),
                "reflection": reading.reflection, "reflection_basis": "subjective_reading_response"}
        return material({"kind": "activity", "activity_id": activity.activity_id,
            "revision": activity.revision}, "role_life_activity", payload)

    def _entry(self, key, context, at):
        entry = self.journal.get_for_audience(key, scope=context.scope,
            recipient=context.actor.subject, observed_at=at)
        if (key.owner != self.owner(context)
                or key.local_date > at.astimezone(ZoneInfo(entry.draft.context.timezone)).date().isoformat()):
            raise TaskError("life_context_scope", "journal is outside the current role or local date")
        return entry

    @staticmethod
    def _journal(entry, derived=None):
        draft, key = entry.draft, entry.reference.key
        payload = {"basis": "subjective_" + key.kind.value, "kind": key.kind.value,
            "local_date": key.local_date, "timezone": draft.context.timezone,
            "updated_at": entry.updated_at.isoformat(), "origin": draft.origin.value,
            "form": draft.form, "recall": draft.recall.value if draft.recall else None}
        if derived is None:
            payload.update(content_form="body", body=draft.body, afterglow=draft.afterglow)
        else:
            payload.update(content_form="derived", summary=derived.material.summary,
                dream_fragments=derived.material.dream_fragments, continuity=derived.material.continuity)
        return material({"kind": "journal", "journal_kind": key.kind.value,
            "local_date": key.local_date, "revision": entry.reference.revision,
            "derivative_revision": derived.revision if derived else 0}, "role_life_" + key.kind.value, payload)

    def candidates(self, context, at):
        with self.runtime.read_snapshot():
            self.authorize(context, at)
            owner = self.owner(context)
            activities = self.life.context_activities(owner, context.scope, observed_at=at, limit=SCAN_LIMIT)
            journals = self.journal.context_days(owner, context.scope, observed_at=at, limit=SCAN_LIMIT)
            variants, skipped = [], 0
            for activity in activities:
                try:
                    variants.append((self._activity(activity, context, at),))
                except TaskError:
                    skipped += 1
            for head in journals:
                try:
                    entry = self._entry(head.key, context, at)
                    derived = self.journal.derivatives(head.key, observed_at=at)
                    options = (self._journal(entry),)
                    if derived is not None and (derived.material.summary or derived.material.dream_fragments
                                                or derived.material.continuity):
                        options = (self._journal(entry, derived),) + options
                    variants.append(options)
                except TaskError:
                    skipped += 1
            return LifeCandidates(tuple(variants), len(activities) == SCAN_LIMIT or len(journals) == SCAN_LIMIT, skipped)

    def read(self, references, context, at):
        """Reconstruct only the original selection, under current source governance."""
        with self.runtime.read_snapshot():
            self.authorize(context, at)
            result = []
            for reference in references:
                if reference["kind"] == "activity":
                    try:
                        activity = self.life.activity(reference["activity_id"], owner=self.owner(context))
                    except KeyError:
                        raise TaskError("life_context_unavailable", "original activity is unavailable") from None
                    if activity.revision != reference["revision"]:
                        raise TaskError("life_context_changed", "original activity changed")
                    result.append(self._activity(activity, context, at))
                else:
                    key = JournalKey(self.owner(context), JournalKind(reference["journal_kind"]), reference["local_date"])
                    entry = self._entry(key, context, at)
                    if entry.reference.revision != reference["revision"]:
                        raise TaskError("life_context_changed", "original journal changed")
                    derived = None
                    if reference["derivative_revision"]:
                        derived = self.journal.derivatives(key, observed_at=at)
                        if derived is None or derived.revision != reference["derivative_revision"]:
                            raise TaskError("life_context_changed", "original journal summary or fragments changed")
                    result.append(self._journal(entry, derived))
            return tuple(result)
