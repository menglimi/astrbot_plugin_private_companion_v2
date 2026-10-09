"""Bounded, source-governed samples for expression learning.

New learning runs use authorized inbound text from the exact private
relationship or group. The older confirmed-reply sample path remains readable
so existing rules can still be reviewed and their evidence rechecked.

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

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, stamp
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SourceRef, SubjectKind, VersionRef
from companion_v2.identity_policy.group_audience import group_audience

from .sample_review import ExpressionSampleReviewStore


READ_ACTION = "role.expression.read"
REPLY_OWNER = "conversation.confirmed_reply"
REPLY_SAMPLE_SOURCE = "confirmed_reply"
INPUT_SAMPLE_SOURCE = "conversation_input"
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
    sender_id: str | None = None
    received_at: datetime | None = None
    input_sequence: int = 0
    content_hash: str | None = None


@dataclass(frozen=True)
class SampleSet:
    opened_at: datetime
    closed_at: datetime
    samples: tuple[StyleSample, ...]
    source_kind: str = REPLY_SAMPLE_SOURCE

    @property
    def material_hash(self):
        return digest([self.source_kind, *({"handle": item.handle, "text": item.text} for item in self.samples)])


def sample_handles(samples):
    return {item.handle for item in samples.samples}


def sample_document(samples):
    return {"opened_at": stamp(samples.opened_at), "closed_at": stamp(samples.closed_at),
            "handles": [item.handle for item in samples.samples],
            "characters": sum(len(item.text) for item in samples.samples),
            "source_kind": samples.source_kind}


def _trim(value, maximum=DEFAULT_SAMPLE_CHARS):
    value = value.strip()
    return value if len(value) <= maximum else value[:maximum]


class ExpressionSampleCatalog:
    """Recheckable expression samples from one exact private or group scope."""

    def __init__(self, runtime, *, window_hours=168):
        if type(window_hours) is not int or not 1 <= window_hours <= MAX_WINDOW_HOURS:
            raise ValueError("expression sample window must stay inside its bounded range")
        self.runtime = runtime
        self.messages = None
        self.window = timedelta(hours=window_hours)
        self.reviews = ExpressionSampleReviewStore(runtime)

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

    @staticmethod
    def input_handle(event):
        return "input:" + digest([event.scope, event.scoped_key])

    def _input_rows(self, context, opened_at, at, *, limit):
        clause = ""
        values = [stamp(opened_at), stamp(at), context.scope.kind.value]
        if context.scope.kind is ScopeKind.PRIVATE:
            clause = "AND b.origin_key = ? "
            values.append(context.key)
        else:
            clause = "AND json_extract(b.context_json, '$.role_binding') = ? "
            values.append(encode(context.role_binding))
        values.append(limit)
        return self.runtime.read_all("""SELECT i.rowid AS input_sequence, i.event_key, i.event_json, b.context_json
            FROM conversation_inputs i JOIN conversation_batches b ON b.batch_id = i.batch_id
            WHERE i.withdrawn = 0 AND json_extract(i.event_json, '$.received_at') >= ?
              AND json_extract(i.event_json, '$.received_at') <= ?
              AND json_extract(i.event_json, '$.scope.kind') = ?
              """ + clause + "ORDER BY json_extract(i.event_json, '$.received_at') DESC, i.rowid DESC LIMIT ?",
            tuple(values))

    def _input_text(self, row, context, at):
        from companion_v2.conversation.messages import event_from_document

        try:
            original = TaskContext.restore(json.loads(row["context_json"]))
            event = event_from_document(json.loads(row["event_json"]), original)
        except (TypeError, ValueError, KeyError):
            raise TaskError("expression_sample_changed", "original conversation sample is invalid") from None
        if (original.scope != context.scope or original.role_binding != context.role_binding
                or event.scope != context.scope or event.principal != original.actor.principal
                or (context.scope.kind is ScopeKind.PRIVATE and
                    (original.actor.principal != context.actor.principal
                     or original.actor.subject != context.actor.subject))):
            raise TaskError("expression_sample_changed", "original conversation sample belongs to another scope")
        self._authorize(original, at)
        messages = self._owner()
        messages.authorize(original, at)
        record = messages._read_source(event.source, original, event.capability, at)
        if record.content_hash != event.input_hash:
            raise TaskError("expression_sample_changed", "original conversation sample changed")
        return event, record.payload

    def _collect_inputs(self, context, opened_at, at, *, sample_limit, sample_chars, member_ids=None,
                        review_enabled=None):
        rows = self._input_rows(context, opened_at, at, limit=512)
        samples = []
        for row in rows:
            try:
                event, text = self._input_text(row, context, at)
            except TaskError:
                continue
            if member_ids is not None and event.principal.native_account_id not in member_ids:
                continue
            content_hash = digest(text)
            text = _trim(text, sample_chars)
            if text:
                sample = StyleSample(self.input_handle(event), text, event.principal.native_account_id,
                                     event.received_at, row["input_sequence"], content_hash)
                if review_enabled is not None and not self.reviews.eligible(
                        context, sample, review_enabled=review_enabled):
                    continue
                samples.append(sample)
                if len(samples) == sample_limit:
                    break
        return tuple(samples)

    def _rows(self, context, opened_at, at, *, scope_kind, sample_limit):
        # This query is retained for already-created role-reply evidence.
        actor_clause, actor_values = "", ()
        if scope_kind is ScopeKind.PRIVATE:
            actor_clause = "AND json_extract(b.context_json, '$.actor.subject.subject_id') = ? "
            actor_values = (context.actor.subject.subject_id,)
        return self.runtime.read_all(f"""SELECT h.part_id, h.history_sequence, b.context_json
            FROM conversation_sent_history h
            JOIN conversation_parts p ON p.part_id = h.part_id
            JOIN conversation_batches b ON b.batch_id = h.batch_id
            JOIN conversation_delivery_receipts r ON r.part_id = h.part_id AND r.receipt_ref = h.receipt_ref
            WHERE p.state = 'delivered' AND p.delivered_at > ? AND p.delivered_at <= ?
            AND json_extract(b.context_json, '$.audience.scope.kind') = ?
            AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
            AND json_extract(b.context_json, '$.role_binding.scope.bot_id') = ?
            AND json_extract(b.context_json, '$.audience.scope.account_id') = ?
            {actor_clause}
            ORDER BY h.history_sequence DESC LIMIT ?""",
            (stamp(opened_at), stamp(at), scope_kind.value, context.role_binding.role.subject_id,
             context.scope.bot_id, context.scope.account_id, *actor_values, sample_limit))

    def collect(self, context, at, *, window_hours=None, sample_limit=DEFAULT_SAMPLE_LIMIT,
                sample_chars=DEFAULT_SAMPLE_CHARS, source_kind=REPLY_SAMPLE_SOURCE, member_ids=None,
                review_enabled=None):
        """Read one bounded set and recheck each item's original governed source."""
        scope_kind = self._authorize(context, at)
        window = self.window if window_hours is None else timedelta(hours=window_hours)
        if (type(sample_limit) is not int or not 1 <= sample_limit <= MAX_SAMPLE_LIMIT
                or type(sample_chars) is not int or not 1 <= sample_chars <= MAX_SAMPLE_CHARS):
            raise TaskError("expression_sample_bounds_invalid", "sample bounds are outside their range")
        if source_kind not in (REPLY_SAMPLE_SOURCE, INPUT_SAMPLE_SOURCE):
            raise TaskError("expression_sample_source_invalid", "unknown expression sample source")
        opened_at = at - window
        with self.runtime.read_snapshot():
            self._owner().authorize(context, at)
            if source_kind == INPUT_SAMPLE_SOURCE:
                samples = self._collect_inputs(context, opened_at, at, sample_limit=sample_limit,
                    sample_chars=sample_chars, member_ids=member_ids, review_enabled=review_enabled)
                return SampleSet(opened_at, at, samples, source_kind)
            samples = []
            for row in self._rows(context, opened_at, at, scope_kind=scope_kind, sample_limit=sample_limit):
                try:
                    text = _trim(self._text(row, self._original(row), at), sample_chars)
                except TaskError:
                    continue
                if text:
                    samples.append(StyleSample(self.sample_handle(context, row["part_id"]), text))
            return SampleSet(opened_at, at, tuple(samples), source_kind)

    def new_inputs(self, context, at, *, after_sequence=0, window_hours=168, member_ids=None):
        """Count source-readable new messages, before the smaller learning sample cap."""
        rows = self._input_rows(context, at - timedelta(hours=window_hours), at, limit=512)
        count, latest = 0, after_sequence
        for row in rows:
            if row["input_sequence"] <= after_sequence:
                continue
            try:
                event, text = self._input_text(row, context, at)
            except TaskError:
                continue
            if text.strip() and (member_ids is None or event.principal.native_account_id in member_ids):
                count += 1
                latest = max(latest, row["input_sequence"])
        return count, latest

    def inspect_inputs(self, context, at, *, window_hours, sample_chars, member_ids=None):
        """Expose the bounded source pool, independently of the smaller learning batch."""
        self._authorize(context, at)
        opened_at = at - timedelta(hours=window_hours)
        with self.runtime.read_snapshot():
            self._owner().authorize(context, at)
            samples = self._collect_inputs(context, opened_at, at, sample_limit=512,
                sample_chars=sample_chars, member_ids=member_ids)
        return SampleSet(opened_at, at, samples, INPUT_SAMPLE_SOURCE)

    def resolve_handles(self, handles, opened_at, closed_at, context, at, *, source_kind=REPLY_SAMPLE_SOURCE):
        """Recheck a named set of sample handles inside one closed window."""
        self.describe_handles(handles, opened_at, closed_at, context, at, source_kind=source_kind)
        return True

    def describe_handles(self, handles, opened_at, closed_at, context, at, *, source_kind=REPLY_SAMPLE_SOURCE):
        """Return named samples only after rechecking their original source."""
        scope_kind = self._authorize(context, at)
        requested = tuple(handles)
        known = set(requested)
        if not known:
            raise TaskError("expression_sample_unavailable", "this run has no samples to recheck")
        if len(known) != len(requested):
            raise TaskError("expression_sample_unavailable", "this run has duplicate sample handles")
        if source_kind not in (REPLY_SAMPLE_SOURCE, INPUT_SAMPLE_SOURCE):
            raise TaskError("expression_sample_changed", "stored expression sample source is invalid")
        if source_kind == INPUT_SAMPLE_SOURCE:
            with self.runtime.read_snapshot():
                self._owner().authorize(context, at)
                descriptions = {}
                for row in self._input_rows(context, opened_at, closed_at, limit=512):
                    try:
                        event, text = self._input_text(row, context, at)
                    except TaskError:
                        continue
                    handle = self.input_handle(event)
                    if handle in known:
                        descriptions[handle] = text
                        known.discard(handle)
                if known:
                    raise TaskError("expression_sample_changed", "original conversation samples are no longer available")
                return [descriptions[handle] for handle in requested]
        # The run stored its own batch size, so rechecking never depends on the
        # current configuration and a narrowed batch cannot invalidate a run.
        limit = min(MAX_SAMPLE_LIMIT, max(len(known) * 2, len(known) + 8))
        descriptions = {}
        with self.runtime.read_snapshot():
            self._owner().authorize(context, at)
            for row in self._rows(context, opened_at, closed_at, scope_kind=scope_kind, sample_limit=limit):
                handle = self.sample_handle(context, row["part_id"])
                if handle not in known:
                    continue
                descriptions[handle] = self._text(row, self._original(row), at)
                known.discard(handle)
        if known:
            raise TaskError("expression_sample_changed",
                            "original expression samples are no longer available")
        return [descriptions[handle] for handle in requested]

    def catalogue(self, samples):
        return [{"handle": item.handle, "text": item.text} for item in samples.samples]

    def evidence_context(self, window, context):
        key = window.get("context_key")
        if key is None:
            if context.scope.kind is ScopeKind.PRIVATE:
                return context
            raise TaskError("expression_sample_changed", "original group sample context is unavailable")
        row = self.runtime.read_one("""SELECT context_json FROM conversation_batches
            WHERE origin_key = ? ORDER BY rowid DESC LIMIT 1""", (key,))
        try:
            original = TaskContext.restore(json.loads(row["context_json"])) if row else None
        except (TypeError, ValueError, KeyError):
            original = None
        if (original is None or original.key != key or original.scope != context.scope
                or original.role_binding != context.role_binding):
            raise TaskError("expression_sample_changed", "original sample belongs to another role or window")
        return original
