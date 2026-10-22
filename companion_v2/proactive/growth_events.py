"""Bounded automatic contact candidates from confirmed role growth receipts.

When a skill or long-term goal gains a new confirmed progress note or transitions
to ``achieved``, the role can naturally share that small breakthrough, practice
feel, or milestone in its private window. The durable contact task serves as the
deduplication ledger so each (growth_id, revision) is considered at most once.
"""

from collections import OrderedDict
from datetime import timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SourceRef, SubjectKind, VersionRef
from companion_v2.role_work.growth.codec import record_from_json
from companion_v2.role_work.growth.models import GrowthKind, GrowthState
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from companion_v2.storage.models import OperationState

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


PAGE_SIZE = 16
POLL_INTERVAL = timedelta(seconds=30)
SOURCE_OWNER = "proactive.growth"


class GrowthContactEvents:
    """Time-bounded growth progress and achievement candidates tied to exact revisions."""

    def __init__(self, contacts, role_growth):
        if contacts.runtime is not role_growth.runtime:
            raise ValueError("growth contacts must share the original role growth ledger")
        self.contacts, self.growth, self.runtime = contacts, role_growth, role_growth.runtime
        self.tasks = contacts.tasks
        self._scans = OrderedDict()
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self._scans.clear()

    @staticmethod
    def _owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def _authorize(self, context, at):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)
                or context.actor.subject.kind is not SubjectKind.HUMAN):
            raise TaskError("contact_growth_scope", "growth sharing requires the exact private participant")
        require(self.tasks.authorize_context(context, action="role.growth.read", observed_at=at))

    def _receipt(self, context, operation_id, at):
        self._authorize(context, at)
        owner = self._owner(context)
        row = self.runtime.read_one(
            "SELECT growth_id, result_json FROM role_growth_operations WHERE operation_id = ? AND owner_key = ?",
            (operation_id, digest(owner)),
        )
        if row is None:
            raise TaskError("contact_growth_receipt_required", "growth contact needs its committed operation receipt")
        record = record_from_json(row["result_json"])
        operation = require(self.growth.operations.get(operation_id))
        if (operation.state is not OperationState.COMPLETED
                or operation.operation.owner != "role.growth"
                or operation.operation.scope != context.scope
                or operation.operation.operation_id != operation_id
                or record.owner != owner or record.scope != context.scope
                or record.growth_id != row["growth_id"]
                or record.state not in (GrowthState.ACTIVE, GrowthState.ACHIEVED)
                or record.confirmed_by is None or record.updated_at > at):
            raise TaskError("contact_growth_receipt_changed", "growth operation no longer attests a shareable revision")
        if (record.state is GrowthState.ACTIVE and not record.progress_note.strip()):
            raise TaskError("contact_growth_note_required", "active growth sharing requires a confirmed progress note")
        try:
            current = self.growth.record(record.growth_id, owner=owner)
        except KeyError as error:
            raise TaskError("contact_growth_unavailable", "growth record is no longer available") from error
        if current != record:
            raise TaskError("contact_growth_changed", "growth record changed after its operation receipt")
        for source in record.sources:
            if source.scope != context.scope:
                raise TaskError("contact_growth_source_scope", "growth evidence belongs to another private window")
            require(self.contacts.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))
        return record

    @staticmethod
    def _purpose(record):
        return "creation" if record.kind is GrowthKind.SKILL else "life"

    @staticmethod
    def _material(record):
        event_kind = "goal_achieved" if record.state is GrowthState.ACHIEVED else "growth_progress_recorded"
        if record.state is GrowthState.ACHIEVED:
            meaning = ("这是角色长期目标已确认达成的记录；可以自然分享达成这一步的轻松或欣喜，"
                       "不编造现实考级、外部奖项或未经证据支持的具体成果。")
        elif record.kind is GrowthKind.SKILL:
            meaning = ("这是角色练习或摸索技能时经确认记录下的一点定性进展；像平时练完顺口和熟人聊起"
                       "刚找到的手感、小窍门或仍有点生疏的地方，不汇报经验值或等级，也不说成已经彻底精通。")
        else:
            meaning = ("这是角色推进长期目标时经确认记录下的一点阶段性进展；用日常聊天语气带出这点小推进"
                       "或心头感受，不写成行政工作汇报，也不把阶段进展说成已经全部完成。")
        return {
            "event": event_kind,
            "growth_id": record.growth_id,
            "kind": record.kind.value,
            "state": record.state.value,
            "revision": record.revision,
            "title": record.title[:256],
            "description": record.description[:1024],
            "progress_note": record.progress_note[:2048],
            "updated_at": stamp(record.updated_at),
            "meaning": meaning,
        }

    @staticmethod
    def _source_ref(context, record):
        identifier = "contact-growth-source-" + digest(
            [context.key, record.growth_id, record.revision])
        return SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), record.updated_at)

    def _project(self, context, operation_id, record, at):
        body = self._material(record)
        reference = self._source_ref(context, record)
        receipt = {
            "context": json.loads(encode(context)),
            "growth_id": record.growth_id,
            "revision": record.revision,
            "operation_id": operation_id,
            "record_hash": digest(record),
        }
        payload = json.dumps({**body, "_receipt": receipt}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(
                SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
            link(self.runtime, reference, record.sources, at)
        require(self.contacts.sources.validate_reference_for_audience(
            reference, recipient=context.actor.subject, observed_at=at))
        return reference

    def _validate_source(self, source, at):
        try:
            payload = json.loads(source.payload)
            receipt = payload.pop("_receipt")
            if type(payload) is not dict or type(receipt) is not dict or set(receipt) != {
                    "context", "growth_id", "revision", "operation_id", "record_hash"}:
                raise ValueError("invalid growth source receipt")
            context = TaskContext.restore(receipt["context"])
            record = self._receipt(context, receipt["operation_id"], at)
            expected_ref = self._source_ref(context, record)
            if (record.growth_id != receipt["growth_id"] or record.revision != receipt["revision"]
                    or digest(record) != receipt["record_hash"] or source.reference != expected_ref
                    or source.audience != context.audience or payload != self._material(record)
                    or source.content_hash != digest(source.payload)):
                raise ValueError("original growth source changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_growth_source_changed", "original growth record cannot attest this source") from error

    @staticmethod
    def _event_key(context, record):
        return digest([context.key, record.growth_id, record.revision])

    def _known(self, context, opportunity):
        identifier = self.contacts.task_id(context, opportunity)
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (identifier,)) or self.runtime.read_one(
            "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (identifier,))

    def select(self, context, preferences, at, *, purpose=None):
        """Scan one page of committed growth operations; each revision is offered at most once."""
        token = preferences.snapshot.resolution_token
        state = self._scans.get(context.key)
        if state is None or state[0] != token:
            state = (token, None, at)
        self._scans[context.key] = state
        self._scans.move_to_end(context.key)
        while len(self._scans) > 1024:
            self._scans.popitem(last=False)
        _, cursor, ready_at = state
        if ready_at > at:
            return None, False
        if all(preferences.reason(candidate) for candidate in ("creation", "life")):
            self._scans[context.key] = (token, None, at + POLL_INTERVAL)
            return None, False
        try:
            self._authorize(context, at)
        except TaskError as error:
            if error.code in ("supervisor_fenced", "supervisor_generation_conflict"):
                raise
            self._scans[context.key] = (token, None, at + POLL_INTERVAL)
            return None, False
        lifetime = timedelta(seconds=preferences.values["event_max_age_seconds"])
        params = [digest(self._owner(context)), stamp(at - lifetime), stamp(at)]
        continuation = ""
        if cursor is not None:
            continuation = " AND (json_extract(result_json, '$.updated_at'), operation_id) < (?, ?)"
            params.extend(cursor)
        rows = self.runtime.read_all("""SELECT operation_id,
                json_extract(result_json, '$.updated_at') AS updated_at
            FROM role_growth_operations WHERE owner_key = ?
            AND json_extract(result_json, '$.updated_at') > ?
            AND json_extract(result_json, '$.updated_at') <= ?
            AND json_extract(result_json, '$.state') IN ('active', 'achieved')""" + continuation + """
            ORDER BY json_extract(result_json, '$.updated_at') DESC, operation_id DESC LIMIT ?""",
            (*params, PAGE_SIZE))
        for row in rows:
            cursor = (row["updated_at"], row["operation_id"])
            self._scans[context.key] = (token, cursor, at)
            try:
                record = self._receipt(context, row["operation_id"], at)
            except (TaskError, KeyError):
                continue
            candidate_purpose = self._purpose(record)
            if purpose is not None and purpose != candidate_purpose:
                continue
            if preferences.reason(candidate_purpose):
                continue
            opportunity = Opportunity("growth-" + self._event_key(context, record),
                context.scope, record.updated_at, record.updated_at + lifetime)
            if self._known(context, opportunity):
                continue
            try:
                source = self._project(context, row["operation_id"], record, at)
            except (TaskError, KeyError, TypeError, ValueError):
                continue
            marker = {
                "growth_id": record.growth_id,
                "revision": record.revision,
                "operation_id": row["operation_id"],
                "record_hash": digest(record),
                "purpose": candidate_purpose,
                "expires_at": stamp(opportunity.expires_at),
            }
            if record.state is GrowthState.ACHIEVED:
                summary = ("角色一项长期目标刚刚确认达成，可以像跟知心熟人报喜那样自然分享这份踏实或高兴，"
                           "不夸大未经记录的成果，不合适就跳过。")
            elif record.kind is GrowthKind.SKILL:
                summary = ("角色在练习的技能上刚记下一条真实进展，可以随口和对方分享刚摸索到的一点手感、"
                           "小突破或还在琢磨的地方，像日常闲聊一样自然，不写生硬汇报。")
            else:
                summary = ("角色的长期目标刚记下一点新进展，可以顺手和对方聊聊往前迈出的这一小步与当下心情，"
                           "不说成已经彻底完成，不合适就跳过。")
            thought = Thought("growth-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION, summary,
                              EvidenceSnapshot(context.scope, at, (source,)), 1.0)
            return (opportunity, (ContactIntent(candidate_purpose, thought),), marker), True
        more = len(rows) == PAGE_SIZE
        self._scans[context.key] = (token, cursor if more else None, at if more else at + POLL_INTERVAL)
        return None, more

    def validate(self, context, marker, at):
        if not isinstance(marker, dict) or set(marker) != {
                "growth_id", "revision", "operation_id", "record_hash", "purpose", "expires_at"}:
            raise TaskError("contact_growth_invalid", "automatic growth contact requires its exact original event")
        record = self._receipt(context, marker["operation_id"], at)
        if (record.growth_id != marker["growth_id"] or record.revision != marker["revision"]
                or digest(record) != marker["record_hash"]):
            raise TaskError("contact_growth_changed", "growth record changed after candidate selection")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        expires = record.updated_at + timedelta(seconds=preferences.values["event_max_age_seconds"])
        purpose = self._purpose(record)
        if marker["purpose"] != purpose or marker["expires_at"] != stamp(expires) or at >= expires:
            raise TaskError("contact_growth_expired", "the original growth opportunity is no longer current")
        preferences.require_contact(purpose)
