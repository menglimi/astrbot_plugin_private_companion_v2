"""One role's recorded history; no elapsed-time simulation or invented past."""

import json
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import ScopeKind, SubjectKind
from companion_v2.role_work.journal import codec as journal_codec
from companion_v2.role_work.growth.models import GrowthState
from companion_v2.storage.models import OperationState

from .pagination import KINDS, TimelineCursors, terms
from .query import SCAN_LIMIT, candidates, ceilings, position


class RoleTimeline:
    def __init__(self, life, growth):
        if life.tasks is not growth.tasks:
            raise ValueError("timeline must share its original life, growth and task owners")
        self.life, self.growth, self.tasks = life, growth, life.tasks
        self.runtime = life.runtime
        self.cursors = TimelineCursors()

    @staticmethod
    def _private(context):
        if (context.scope.kind is not ScopeKind.PRIVATE or context.actor.subject.kind is not SubjectKind.HUMAN
                or context.audience.recipients != (context.actor.subject,)):
            raise TaskError("timeline_private_required", "timeline requires this participant's exact private audience")

    def authorize(self, context, kinds, at, *, preflight=False):
        self._private(context)
        actions = {"role.growth.read" if kind == "growth" else "role.life.read" for kind in kinds}
        for action in sorted(actions):
            check = self.tasks.check_context_access if preflight else self.tasks.authorize_context
            require(check(context, action=action, observed_at=at))

    def available(self, context, at, *, preflight=False):
        available = []
        for kinds in (("activity", "diary", "dream"), ("growth",)):
            try:
                self.authorize(context, kinds, at, preflight=preflight)
            except TaskError:
                continue
            available.extend(kinds)
        return available

    def query(self, context, *, kinds=None, time_start=None, time_end=None, limit=8, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("timeline page size must be between 1 and 20")
        with self.runtime.read_snapshot():
            at = self.tasks.now()
            owner = self.life.owner(context)
            if cursor is None:
                query = terms(kinds, time_start, time_end)
                available = self.available(context, at)
                included = [k for k in query["kinds"] if k in available]
                if not included:
                    raise TaskError("timeline_read_denied", "no requested timeline domain is available")
                snapshot = {"context_key": context.key, "query": query, "captured_at": stamp(at),
                    "included_kinds": included, "ceilings": ceilings(self.runtime, owner, context.scope, included)}
            else:
                snapshot = self.cursors.restore(cursor, context, at, kinds=kinds, time_start=time_start, time_end=time_end)
                self.authorize(context, snapshot["included_kinds"], at)
            rows = candidates(self.runtime, owner, context.scope, snapshot)
            items, skipped, consumed, used = [], 0, 0, 0
            for row in rows[:SCAN_LIMIT]:
                if len(items) >= limit:
                    break
                try:
                    item, _ = self._project(dict(row), context, at)
                except TaskError:
                    skipped += 1
                else:
                    size = len(encode(item).encode("utf-8"))
                    if used + size > 40000:
                        break
                    items.append(item)
                    used += size
                consumed += 1
            more = consumed < len(rows)
            if more and consumed == 0:
                raise TaskError("timeline_item_too_large", "original timeline metadata exceeds its read budget")
            unavailable = sorted(set(snapshot["query"]["kinds"]) - set(snapshot["included_kinds"]))
            return {"items": items, "captured_at": snapshot["captured_at"], "query": snapshot["query"],
                "included_kinds": snapshot["included_kinds"], "unavailable_kinds": unavailable,
                "skipped": skipped, "selection_partial": bool(skipped or more or unavailable),
                "coverage": "recorded_versions_and_journal_operations_only",
                "next_cursor": self.cursors.seal(snapshot, position(rows[consumed - 1])) if more else None}

    @staticmethod
    def _clip(payload):
        truncated = []
        for name in ("description", "checkpoint", "title", "progress_note"):
            if name in payload and len(payload[name]) > 512:
                payload[name] = payload[name][:512]
                truncated.append(name)
        if "reading" in payload and len(payload["reading"]["reflection"]) > 512:
            payload["reading"]["reflection"] = payload["reading"]["reflection"][:512]
            truncated.append("reading.reflection")
        payload["truncated_fields"] = truncated
        return payload

    def _activity(self, ref, context, at):
        activity = self.life.life.activity_revision(ref["identifier"], ref["revision"], owner=self.life.owner(context))
        payload = json.loads(self.life._activity(activity, context, at).payload)
        row = self.runtime.read_one("""SELECT provenance, updated_at,
            (SELECT COUNT(*) FROM role_activity_revisions p WHERE p.owner_key = r.owner_key
             AND p.activity_id = r.activity_id AND p.revision < r.revision) AS prior_count
            FROM role_activity_revisions r WHERE owner_key = ? AND activity_id = ? AND revision = ?""",
            (digest(activity.owner), activity.activity_id, activity.revision))
        if stamp(activity.updated_at) != ref["occurred_at"] or row["updated_at"] != ref["occurred_at"]:
            raise TaskError("timeline_record_invalid", "activity time differs from its original record")
        missing = activity.revision - 1 - row["prior_count"]
        payload.update(content_form="historical_version", provenance=row["provenance"],
                       missing_prior_revisions=missing, history_incomplete=missing != 0)
        sources = []
        if activity.work is not None and activity.work.source is not None:
            sources.append(activity.work.source)
        if activity.reading is not None:
            sources.append(activity.reading.source)
        return payload, tuple(sources)

    def _growth(self, ref, context, at):
        record = self.growth.ledger.revision(ref["identifier"], ref["revision"], owner=self.growth.owner(context))
        if record.scope != context.scope or record.updated_at > at or stamp(record.updated_at) != ref["occurred_at"]:
            raise TaskError("timeline_record_invalid", "growth record differs from its original scope or time")
        for source in record.sources:
            if source.scope != context.scope:
                raise TaskError("timeline_source_scope", "growth source belongs to another private scope")
            require(self.growth.sources.validate_reference_for_audience(source, recipient=context.actor.subject, observed_at=at))
        return {"basis": "subjective_role_growth", "content_form": "historical_version", "kind": record.kind.value,
            "state": record.state.value, "title": record.title, "description": record.description,
            "progress_note": record.progress_note, "requires_human_confirmation": record.state is GrowthState.PROPOSED}, record.sources

    def _journal(self, ref, context, at):
        row = self.runtime.read_one("SELECT result_json FROM role_journal_operations WHERE owner_key = ? AND operation_id = ?",
                                   (digest(self.life.owner(context)), ref["identifier"]))
        if row is None:
            raise TaskError("timeline_record_unavailable", "original journal receipt is unavailable")
        receipt = journal_codec.receipt_from_json(row["result_json"])
        head, operation = receipt.head, require(self.life.journal.operations.get(ref["identifier"]))
        stored = self.life.journal._row(head.key)
        if stored is None:
            raise TaskError("timeline_record_unavailable", "original journal context is unavailable")
        original = journal_codec.context(json.loads(stored["context_json"]))
        if (receipt.operation_id != ref["identifier"] or receipt.action not in ("save", "delete", "restore")
                or operation.state is not OperationState.COMPLETED or operation.operation.owner != "role.journal"
                or operation.operation.scope != context.scope or original.scope != context.scope
                or original.key != head.key or head.key.owner != self.life.owner(context)
                or head.key.kind.value != ref["kind"] or head.revision != ref["revision"]
                or stamp(head.updated_at) != ref["occurred_at"] or head.updated_at > at
                or head.key.local_date > at.astimezone(ZoneInfo(original.timezone)).date().isoformat()):
            raise TaskError("timeline_record_invalid", "journal receipt does not match its original authority or time")
        return {"basis": "subjective_journal_operation", "content_form": "operation_metadata_only",
            "action": receipt.action, "state": head.state.value, "local_date": head.key.local_date,
            "timezone": original.timezone, "body_history": "not_retained"}, ()

    def _project(self, ref, context, at):
        if (type(ref) is not dict or set(ref) != {"kind", "identifier", "revision", "occurred_at"}
                or ref["kind"] not in KINDS or type(ref["revision"]) is not int or ref["revision"] < 1
                or type(ref["identifier"]) is not str or not 1 <= len(ref["identifier"]) <= 512):
            raise TaskError("timeline_reference_invalid", "select an original timeline record")
        self.authorize(context, (ref["kind"],), at)
        reader = self._activity if ref["kind"] == "activity" else self._growth if ref["kind"] == "growth" else self._journal
        try:
            detail, sources = reader(ref, context, at)
        except KeyError:
            raise TaskError("timeline_record_unavailable", "original timeline revision is unavailable") from None
        return {"reference": ref, "detail": self._clip(detail)}, sources

    def validate(self, context, result):
        """Reread the sealed selection, never substitute newer states or new bodies."""
        with self.runtime.read_snapshot():
            at = self.tasks.now()
            self.authorize(context, result["included_kinds"], at)
            sources = set()
            for item in result["items"]:
                current, dependencies = self._project(item["reference"], context, at)
                if current != item:
                    raise TaskError("timeline_result_changed", "selected historical material changed")
                sources.update(dependencies)
            return tuple(sources)
