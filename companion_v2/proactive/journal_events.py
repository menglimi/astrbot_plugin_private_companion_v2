"""Private diary and dream contact candidates from committed journal receipts."""

from collections import OrderedDict
from datetime import timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SourceRef, VersionRef
from companion_v2.role_work.journal import codec as journal_codec
from companion_v2.role_work.journal.models import JournalKey, JournalKind, JournalState
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from companion_v2.storage.models import OperationState

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


JOURNAL_SOURCE_OWNER = "proactive.journal"
JOURNAL_PAGE_SIZE = 16
JOURNAL_POLL_INTERVAL = timedelta(seconds=30)


class JournalContactEvents:
    """Time-bounded private-writing candidates tied to the exact saved revision."""

    def __init__(self, contacts, journal):
        if contacts.runtime is not journal.runtime:
            raise ValueError("journal contacts must share the original journal ledger")
        self.contacts, self.journal, self.runtime = contacts, journal, journal.runtime
        self.tasks = contacts.tasks
        self._scans = OrderedDict()
        self.guard = bind(self.runtime, JOURNAL_SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self._scans.clear()

    @staticmethod
    def _owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def _receipt(self, context, operation_id, at):
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise TaskError("contact_journal_scope", "private writing cannot be shared outside its original private window")
        row = self.runtime.read_one("SELECT result_json FROM role_journal_operations WHERE operation_id = ? AND owner_key = ?",
            (operation_id, digest(self._owner(context))))
        if row is None:
            raise TaskError("contact_journal_receipt_required", "journal contact needs its original committed write receipt")
        receipt = journal_codec.receipt_from_json(row["result_json"])
        operation = require(self.journal.operations.get(operation_id))
        if (operation.state is not OperationState.COMPLETED or operation.operation.owner != "role.journal"
                or operation.operation.scope != context.scope or operation.operation.operation_id != operation_id
                or operation.operation.version.lineage_id != operation_id or operation.operation.version.revision != 1
                or operation.operation.idempotency_key != operation_id
                or receipt.operation_id != operation_id or receipt.action not in ("save", "restore")
                or receipt.head.key.owner != self._owner(context) or receipt.head.state is not JournalState.ACTIVE
                or receipt.head.updated_at > at):
            raise TaskError("contact_journal_receipt_changed", "journal operation no longer attests an active private entry")
        require(self.tasks.authorize_context(context, action="role.journal.write", observed_at=at))
        if self.journal.head(receipt.head.key) != receipt.head:
            raise TaskError("contact_journal_changed", "journal changed after its original save receipt")
        if context.actor.subject not in context.audience.recipients:
            raise TaskError("contact_journal_audience", "original journal author is outside the candidate audience")
        entry = None
        for recipient in context.audience.recipients:
            entry = self.journal.get_for_audience(receipt.head.key, scope=context.scope,
                recipient=recipient, observed_at=at)
        if (entry.reference.revision != receipt.head.revision or entry.updated_at != receipt.head.updated_at
                or entry.draft.context.scope != context.scope or entry.draft.context.key.owner != self._owner(context)):
            raise TaskError("contact_journal_changed", "journal no longer matches its original private conversation")
        expected_hash = digest([entry.draft.context, journal_codec.draft_parameters(entry.draft),
                                receipt.action, receipt.head.revision - 1])
        if operation.parameter_hash != expected_hash:
            raise TaskError("contact_journal_receipt_changed", "journal write receipt does not attest this saved content")
        return receipt, entry

    @staticmethod
    def _material(entry):
        draft = entry.draft
        if draft.summary.strip():
            passage, basis = draft.summary.strip(), "summary"
        elif draft.afterglow.strip():
            passage, basis = draft.afterglow.strip(), "afterglow"
        else:
            passage, basis = draft.body.strip(), "remembered_excerpt"
        kind = entry.reference.key.kind
        if kind is JournalKind.DREAM:
            meaning = "这是角色对梦的主观记忆，不是用户经历、现实事件或预示；不得补写没有记住的情节。"
        else:
            meaning = "这是角色日记中的主观回顾，不证明其中内容是用户说过或做过的事。"
        return {"event": "private_journal_saved", "kind": kind.value,
            "local_date": entry.reference.key.local_date, "revision": entry.reference.revision,
            "origin": draft.origin.value, "recall": draft.recall.value if draft.recall else None,
            "meaning": meaning, "passage_basis": basis, "passage": passage[:2048],
            "passage_truncated": len(passage) > 2048}

    @staticmethod
    def _source_ref(context, entry):
        key = entry.reference.key
        identifier = "contact-journal-source-" + digest(
            [context.key, key.kind.value, key.local_date, entry.reference.revision])
        return SourceRef(identifier, JOURNAL_SOURCE_OWNER, context.scope, VersionRef(identifier, 1), entry.updated_at)

    def _project(self, context, receipt, entry, at):
        body = self._material(entry)
        reference = self._source_ref(context, entry)
        marker = {"context": json.loads(encode(context)), "kind": entry.reference.key.kind.value,
            "local_date": entry.reference.key.local_date, "revision": entry.reference.revision,
            "operation_id": receipt.operation_id, "journal_hash": digest(entry)}
        payload = json.dumps({**body, "_receipt": marker}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
        return reference

    def _validate_source(self, record, at):
        try:
            payload = json.loads(record.payload)
            marker = payload.pop("_receipt")
            if type(payload) is not dict or type(marker) is not dict or set(marker) != {
                    "context", "kind", "local_date", "revision", "operation_id", "journal_hash"}:
                raise ValueError("invalid journal source receipt")
            context = TaskContext.restore(marker["context"])
            key = JournalKey(self._owner(context), JournalKind(marker["kind"]), marker["local_date"])
            receipt, entry = self._receipt(context, marker["operation_id"], at)
            expected_ref = self._source_ref(context, entry)
            if (entry.reference.key != key or receipt.head.revision != marker["revision"]
                    or digest(entry) != marker["journal_hash"] or record.reference != expected_ref
                    or record.audience != context.audience or payload != self._material(entry)
                    or record.content_hash != digest(record.payload)):
                raise ValueError("original journal source changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_journal_source_changed", "original private journal cannot attest this source") from error

    @staticmethod
    def _event_key(context, entry):
        reference = entry.reference
        return digest([context.key, reference.key.kind.value, reference.key.local_date, reference.revision])

    def _known(self, context, opportunity):
        identifier = self.contacts.task_id(context, opportunity)
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (identifier,)) or self.runtime.read_one(
            "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (identifier,))

    def select(self, context, preferences, at):
        """Read one indexed page and expose only a short, revision-bound passage."""
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
        if preferences.reason("life"):
            self._scans[context.key] = (token, None, at + JOURNAL_POLL_INTERVAL)
            return None, False
        lifetime = timedelta(seconds=preferences.values["event_max_age_seconds"])
        params = [digest(self._owner(context)), stamp(at - lifetime), stamp(at)]
        continuation = ""
        if cursor is not None:
            continuation = " AND (json_extract(result_json, '$.head.updated_at'), operation_id) < (?, ?)"
            params.extend(cursor)
        rows = self.runtime.read_all("""SELECT operation_id,
                json_extract(result_json, '$.head.updated_at') AS updated_at
            FROM role_journal_operations WHERE owner_key = ?
            AND json_extract(result_json, '$.head.updated_at') > ?
            AND json_extract(result_json, '$.head.updated_at') <= ?
            AND json_extract(result_json, '$.action') IN ('save', 'restore')""" + continuation + """
            ORDER BY json_extract(result_json, '$.head.updated_at') DESC, operation_id DESC LIMIT ?""",
            (*params, JOURNAL_PAGE_SIZE))
        for row in rows:
            cursor = (row["updated_at"], row["operation_id"])
            self._scans[context.key] = (token, cursor, at)
            try:
                receipt, entry = self._receipt(context, row["operation_id"], at)
            except (TaskError, KeyError):
                continue
            opportunity = Opportunity("journal-" + self._event_key(context, entry), context.scope,
                entry.updated_at, entry.updated_at + lifetime)
            if self._known(context, opportunity):
                continue
            source = self._project(context, receipt, entry, at)
            marker = {"kind": entry.reference.key.kind.value, "local_date": entry.reference.key.local_date,
                "revision": entry.reference.revision, "operation_id": receipt.operation_id,
                "journal_hash": digest(entry), "purpose": "life", "expires_at": stamp(opportunity.expires_at)}
            label = "一则新保存的梦境片段" if entry.reference.key.kind is JournalKind.DREAM else "一篇新保存的日记"
            summary = f"{label}或许能带来一句带余韵的角色近况或碎碎念；这是私密主观书写，只取最想顺口提到的一点，不合适就跳过，不把梦当成现实。"
            thought = Thought("journal-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION, summary,
                              EvidenceSnapshot(context.scope, at, (source,)), 1.0)
            return (opportunity, (ContactIntent("life", thought),), marker), True
        more = len(rows) == JOURNAL_PAGE_SIZE
        self._scans[context.key] = (token, cursor if more else None, at if more else at + JOURNAL_POLL_INTERVAL)
        return None, more

    def validate(self, context, marker, at):
        if not isinstance(marker, dict) or set(marker) != {
                "kind", "local_date", "revision", "operation_id", "journal_hash", "purpose", "expires_at"}:
            raise TaskError("contact_journal_invalid", "automatic journal contact needs its exact original event")
        key = JournalKey(self._owner(context), JournalKind(marker["kind"]), marker["local_date"])
        receipt, entry = self._receipt(context, marker["operation_id"], at)
        if entry.reference.key != key or entry.reference.revision != marker["revision"] or digest(entry) != marker["journal_hash"]:
            raise TaskError("contact_journal_changed", "private journal changed after candidate selection")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        expires = entry.updated_at + timedelta(seconds=preferences.values["event_max_age_seconds"])
        if marker["purpose"] != "life" or marker["expires_at"] != stamp(expires) or at >= expires:
            raise TaskError("contact_journal_expired", "the original private-writing opportunity is no longer current")
        preferences.require_contact("life")
