"""Bounded, source-governed samples of the role's own confirmed expression.

Style learning only looks at how the role actually wrote in this exact
conversation. The material is the confirmed-delivered text itself, so a sample
can never include a draft that was never sent, and a withdrawn or replaced reply
drops out of the sample set on the next read.

Two scopes are supported. A private window samples only turns addressed to the
same participant, because a private reply belongs to that relationship. A group
window samples every confirmed reply of the role in that group regardless of who
spoke first, because a group reply was delivered to the whole collective
audience; matching on the triggering speaker would drop most of the role's group
writing and is what made group learning look empty.

Samples are form only. They are never republished as facts about the role or
about anyone else, and the prompt contract forbids inferring identity,
personality, mood, health, relationships or stable preference from them.

Every bound is a default for the registered ``expression.learning`` settings;
callers pass the effective values so an operator can widen the window or the
batch without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, stamp
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SourceRef, SubjectKind, VersionRef
from companion_v2.identity_policy.group_audience import group_audience


READ_ACTION = "role.expression.read"
REPLY_OWNER = "conversation.confirmed_reply"
MAX_SAMPLE_LIMIT = 64
MAX_SAMPLE_CHARS = 4000
MAX_WINDOW_HOURS = 720
MIN_SAMPLES = 1
DEFAULT_SAMPLE_LIMIT = 24
DEFAULT_SAMPLE_CHARS = 800


@dataclass(frozen=True)
class StyleSample:
    handle: str
    text: str


@dataclass(frozen=True)
class SampleSet:
    opened_at: datetime
    closed_at: datetime
    samples: tuple[StyleSample, ...]

    @property
    def material_hash(self):
        return digest([{"handle": item.handle, "text": item.text} for item in self.samples])


def sample_handles(samples):
    return {item.handle for item in samples.samples}


def sample_document(samples):
    return {"opened_at": stamp(samples.opened_at), "closed_at": stamp(samples.closed_at),
            "handles": [item.handle for item in samples.samples],
            "characters": sum(len(item.text) for item in samples.samples)}


def _trim(value, maximum=DEFAULT_SAMPLE_CHARS):
    value = value.strip()
    return value if len(value) <= maximum else value[:maximum]


class ExpressionSampleCatalog:
    """The read boundary for one role's own recent writing in one exact scope."""

    def __init__(self, runtime, *, window_hours=168):
        if type(window_hours) is not int or not 1 <= window_hours <= MAX_WINDOW_HOURS:
            raise ValueError("expression sample window must stay inside its bounded range")
        self.runtime = runtime
        self.messages = None
        self.window = timedelta(hours=window_hours)

    def attach(self, messages):
        if messages.runtime is not self.runtime:
            raise ValueError("expression samples must share their conversation runtime")
        self.messages = messages

    def _owner(self):
        if self.messages is None:
            raise TaskError("expression_sample_owner_unavailable",
                            "the conversation owner is not attached")
        return self.messages

    @staticmethod
    def role_owner(context):
        """The role that owns these samples, in the same shape as other role ledgers."""
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    @staticmethod
    def _authorize(context, at):
        if context.scope.kind is ScopeKind.PRIVATE:
            if (context.audience.recipients != (context.actor.subject,)
                    or context.actor.subject.kind is not SubjectKind.HUMAN):
                raise TaskError("expression_private_audience_required",
                                "style learning needs the current participant's exact private audience")
            return ScopeKind.PRIVATE
        if context.scope.kind is ScopeKind.GROUP:
            if context.audience != group_audience(context.scope, context.actor.subject):
                raise TaskError("expression_group_audience_required",
                                "group style learning needs the collective audience of that group")
            return ScopeKind.GROUP
        raise TaskError("expression_scope_required",
                        "style learning reads one private or group conversation")

    @staticmethod
    def sample_handle(context, part_id):
        return "sample:" + digest([context.key, part_id])

    @staticmethod
    def _original(row):
        return TaskContext.restore(json.loads(row["context_json"]))

    def _text(self, row, original, at):
        owner = getattr(self._owner(), "confirmed_reply_sources", None)
        if owner is None:
            raise TaskError("expression_sample_owner_unavailable",
                            "the confirmed reply owner is not attached")
        reference = SourceRef("sent:" + row["part_id"], REPLY_OWNER, original.scope,
                              VersionRef(row["part_id"], 1), at)
        return owner.materialize(original, reference).payload

    def _rows(self, context, opened_at, at, *, scope_kind, sample_limit):
        # The private scope adds the current participant; a group reply belongs to
        # the whole collective audience, so matching the speaker would drop most of
        # the role's own group writing.
        actor_clause, actor_values = "", ()
        if scope_kind is ScopeKind.PRIVATE:
            actor_clause = "AND json_extract(b.context_json, '$.actor.subject.subject_id') = ? "
            actor_values = (context.actor.subject.subject_id,)
        return self.runtime.read_all(f"""SELECT h.part_id, h.history_sequence, b.context_json
            FROM conversation_sent_history h
            JOIN conversation_parts p ON p.part_id = h.part_id
            JOIN conversation_batches b ON b.batch_id = h.batch_id
            JOIN conversation_delivery_receipts r ON r.part_id = h.part_id AND r.receipt_ref = h.receipt_ref
            WHERE p.state = 'delivered' AND r.delivered_at > ? AND r.delivered_at <= ?
            AND json_extract(b.context_json, '$.audience.scope.kind') = ?
            AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
            AND json_extract(b.context_json, '$.role_binding.scope.bot_id') = ?
            AND json_extract(b.context_json, '$.audience.scope.account_id') = ?
            {actor_clause}
            ORDER BY h.history_sequence DESC LIMIT ?""",
            (stamp(opened_at), stamp(at), scope_kind.value, context.role_binding.role.subject_id,
             context.scope.bot_id, context.scope.account_id, *actor_values, sample_limit))

    def collect(self, context, at, *, window_hours=None, sample_limit=DEFAULT_SAMPLE_LIMIT,
                sample_chars=DEFAULT_SAMPLE_CHARS):
        """Read the sample set once; each sample is rechecked against its delivery receipt."""
        scope_kind = self._authorize(context, at)
        window = self.window if window_hours is None else timedelta(hours=window_hours)
        if (type(sample_limit) is not int or not 1 <= sample_limit <= MAX_SAMPLE_LIMIT
                or type(sample_chars) is not int or not 1 <= sample_chars <= MAX_SAMPLE_CHARS):
            raise TaskError("expression_sample_bounds_invalid", "sample bounds are outside their range")
        opened_at = at - window
        with self.runtime.read_snapshot():
            self._owner().authorize(context, at)
            samples = []
            for row in self._rows(context, opened_at, at, scope_kind=scope_kind, sample_limit=sample_limit):
                try:
                    text = _trim(self._text(row, self._original(row), at), sample_chars)
                except TaskError:
                    continue
                if text:
                    samples.append(StyleSample(self.sample_handle(context, row["part_id"]), text))
            return SampleSet(opened_at, at, tuple(samples))

    def resolve_handles(self, handles, opened_at, closed_at, context, at):
        """Recheck a named set of sample handles inside one closed window."""
        scope_kind = self._authorize(context, at)
        known = set(handles)
        if not known:
            raise TaskError("expression_sample_unavailable", "this run has no samples to recheck")
        # The run stored its own batch size, so rechecking never depends on the
        # current configuration and a narrowed batch cannot invalidate a run.
        limit = min(MAX_SAMPLE_LIMIT, max(len(known) * 2, len(known) + 8))
        with self.runtime.read_snapshot():
            self._owner().authorize(context, at)
            for row in self._rows(context, opened_at, closed_at, scope_kind=scope_kind, sample_limit=limit):
                self._text(row, self._original(row), at)
                known.discard(self.sample_handle(context, row["part_id"]))
        if known:
            raise TaskError("expression_sample_changed",
                            "original expression samples are no longer available")
        return True

    def catalogue(self, samples):
        return [{"handle": item.handle, "text": item.text} for item in samples.samples]
