"""Bounded automatic contact candidates from committed role activity receipts.

The cursor is a polling optimization. The existing durable contact task is the
deduplication ledger, including skips and interrupted model decisions.
"""

from collections import OrderedDict
from datetime import timedelta
import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import RoleOwnerRef, SourceRef, VersionRef
from companion_v2.role_work.codec import activity_from_json
from companion_v2.role_work.models import RoleActivityState, RoleArtifactJournalMeaning, RoleArtifactKind
from companion_v2.sharing.models import ShareMaterial
from companion_v2.sharing.planner import ShareCatalog, SharePlanner
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import AssetRepository
from companion_v2.storage.models import OperationState

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


PAGE_SIZE = 16
POLL_INTERVAL = timedelta(seconds=30)
SOURCE_OWNER = "proactive.activity"


class ActivityContactEvents:
    def __init__(self, contacts, role_life):
        if contacts.runtime is not role_life.runtime:
            raise ValueError("activity contacts must share the original role ledger")
        self.contacts, self.life, self.runtime = contacts, role_life, role_life.runtime
        self._scans = OrderedDict()
        self.share_catalog = ShareCatalog()
        self.share_planner = SharePlanner(
            sources=self.contacts.sources,
            assets=AssetRepository(self.runtime),
            catalog=self.share_catalog,
        )
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def close(self):
        self.guard.close()
        self._scans.clear()

    @staticmethod
    def _owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def _artifact_for_activity(self, context, activity):
        owner = self._owner(context)
        for artifact in self.life.artifacts_for_scope(context.scope, owner=owner):
            if (artifact.activity_id == activity.activity_id
                    and artifact.kind is RoleArtifactKind.TEXT
                    and artifact.journal_meaning is RoleArtifactJournalMeaning.CREATIVE_TEXT):
                return artifact
        return None

    def _receipt(self, context, activity, at, *, has_artifact=False):
        if (activity.owner != self._owner(context) or activity.scope != context.scope
                or activity.state is not RoleActivityState.COMPLETED or activity.updated_at > at):
            raise TaskError("contact_activity_unavailable", "contact needs a completion in its original role and window")
        if activity.work is not None:
            if activity.work.context_key != context.key:
                raise TaskError("contact_activity_unavailable", "contact needs a completion in its original role and window")
        elif not has_artifact:
            raise TaskError("contact_activity_unavailable", "contact needs a completion in its original role and window")
        if activity != self.life.activity(activity.activity_id, owner=activity.owner):
            raise TaskError("contact_activity_changed", "contact activity no longer matches its original receipt")
        row = self.runtime.read_one("""SELECT provenance, operation_id FROM role_activity_revisions
            WHERE owner_key = ? AND activity_id = ? AND revision = ?""",
            (digest(activity.owner), activity.activity_id, activity.revision))
        if row is None or row["provenance"] != "recorded" or not row["operation_id"]:
            raise TaskError("contact_activity_receipt_required", "a completed label alone is not an execution receipt")
        operation = require(self.contacts.operations.get(row["operation_id"]))
        saved = self.runtime.read_one("SELECT result_json FROM role_life_operations WHERE operation_id = ? AND owner_key = ?",
                                      (row["operation_id"], digest(activity.owner)))
        if (operation.state is not OperationState.COMPLETED or operation.operation.owner != "role.life"
                or operation.operation.scope != context.scope or saved is None
                or activity_from_json(saved["result_json"]) != activity):
            raise TaskError("contact_activity_receipt_required", "the original role operation must confirm this exact completion")
        return row["operation_id"]

    def _material(self, context, activity, at):
        work_kind = activity.work.kind if activity.work is not None else ""
        if work_kind == "reading":
            receipt = activity.reading
            if (receipt is None or receipt.source != activity.work.source
                    or receipt.content_hash != activity.work.content_hash
                    or (receipt.start_offset, receipt.end_offset) != (activity.work.start_offset, activity.work.end_offset)):
                raise TaskError("contact_reading_receipt_required", "reading needs the actual consumed original span")
            record, = self.contacts._records(context, (receipt.source,), at)
            if (record.content_hash != receipt.content_hash or receipt.text_length != len(record.payload)):
                raise TaskError("contact_reading_changed", "reading original no longer matches its completion")
            excerpt = record.payload[receipt.start_offset:receipt.end_offset]
            body = {"event": "reading_completed", "completed_at": stamp(receipt.completed_at),
                "meaning": "角色确实读过下面的片段；这不证明整本书读完、理解掌握或书中事情在现实发生。",
                "consumed_character_range": [receipt.start_offset, receipt.end_offset],
                "excerpt": excerpt[:4096], "excerpt_truncated": len(excerpt) > 4096,
                "subjective_reflection": receipt.reflection[:2048],
                "reflection_meaning": "角色读后的主观联想，不是原文事实或用户经历。"}
            return "creation", body, (receipt.source,)
        if work_kind == "sleep" and activity.reading is None and activity.updated_at > activity.started_at:
            return "life", {"event": "sleep_completed", "started_at": stamp(activity.started_at),
                "completed_at": stamp(activity.updated_at),
                "meaning": "生活执行端确认角色这一段睡眠已经结束；不证明做过梦、梦见什么、已经起床或完成其他活动。"}, ()
        artifact = self._artifact_for_activity(context, activity) if activity.reading is None else None
        if artifact is not None:
            record, = self.contacts._records(context, (artifact.source,), at)
            if record.content_hash != digest(record.payload) or not record.payload.strip():
                raise TaskError("contact_artifact_changed", "artifact text no longer matches its source hash")
            excerpt = record.payload.strip()
            body = {"event": "creative_artifact_completed", "completed_at": stamp(activity.updated_at),
                "artifact_id": artifact.artifact_id,
                "activity_title": activity.description[:256],
                "meaning": "角色刚刚完成了一段创作文本作品；这是角色自己的随笔或小创作，不是现实发生的事件或用户经历。",
                "excerpt": excerpt[:4096], "excerpt_truncated": len(excerpt) > 4096}
            return "creation", body, (artifact.source,)
        raise TaskError("contact_activity_unsupported", "this activity has no supported factual contact projection")

    def _project(self, context, activity, operation_id, at):
        purpose, body, dependencies = self._material(context, activity, at)
        identifier = "contact-activity-source-" + digest([context.key, activity.activity_id, activity.revision])
        reference = SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), activity.updated_at)
        receipt = {"context": json.loads(encode(context)), "activity_id": activity.activity_id,
                   "revision": activity.revision, "operation_id": operation_id, "activity_hash": digest(activity)}
        payload = json.dumps({**body, "_receipt": receipt}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction():
            require(self.contacts.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
            link(self.runtime, reference, dependencies, at)
        return purpose, reference

    def _validate_source(self, record, at):
        try:
            body = json.loads(record.payload)
            receipt = body.pop("_receipt")
            if type(body) is not dict or type(receipt) is not dict or set(receipt) != {
                    "context", "activity_id", "revision", "operation_id", "activity_hash"}:
                raise ValueError("invalid activity source receipt")
            context = TaskContext.restore(receipt["context"])
            activity = self.life.activity(receipt["activity_id"], owner=self._owner(context))
            artifact = self._artifact_for_activity(context, activity) if activity.reading is None else None
            operation_id = self._receipt(context, activity, at, has_artifact=artifact is not None)
            purpose, expected_body, _ = self._material(context, activity, at)
            identifier = "contact-activity-source-" + digest([context.key, activity.activity_id, activity.revision])
            reference = SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1), activity.updated_at)
            if (record.reference != reference or record.audience != context.audience
                    or receipt["revision"] != activity.revision or receipt["operation_id"] != operation_id
                    or receipt["activity_hash"] != digest(activity) or body != expected_body
                    or record.content_hash != digest(record.payload)):
                raise ValueError("original activity source changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_activity_source_changed", "original activity cannot attest this source") from error

    @staticmethod
    def _event_key(context, activity):
        receipt = activity.reading
        # Re-reading the same original span is not a new automatic topic.
        evidence = ([receipt.source, receipt.start_offset, receipt.end_offset] if receipt is not None
                    else [activity.activity_id, activity.revision])
        return digest([context.key, evidence])

    def _known(self, context, opportunity):
        identifier = self.contacts.task_id(context, opportunity)
        return self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (identifier,)) or self.runtime.read_one(
            "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (identifier,))

    def select(self, context, preferences, at, *, purpose=None):
        """Return (candidate, more_pages); scan at most one indexed page per call."""
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
        if all(preferences.reason(purpose) for purpose in ("creation", "life")):
            self._scans[context.key] = (token, None, at + POLL_INTERVAL)
            return None, False
        lifetime = timedelta(seconds=preferences.values["event_max_age_seconds"])
        params = [digest(self._owner(context)), stamp(at - lifetime), stamp(at)]
        continuation = ""
        if cursor is not None:
            continuation = " AND (updated_at, activity_id, revision) < (?, ?, ?)"
            params.extend(cursor)
        rows = self.runtime.read_all("""SELECT * FROM role_activity_revisions
            WHERE owner_key = ? AND updated_at > ? AND updated_at <= ?""" + continuation + """
            ORDER BY updated_at DESC, activity_id DESC, revision DESC LIMIT ?""", (*params, PAGE_SIZE))
        for row in rows:
            cursor = (row["updated_at"], row["activity_id"], row["revision"])
            self._scans[context.key] = (token, cursor, at)
            activity = activity_from_json(row["record_json"])
            if activity.state is not RoleActivityState.COMPLETED:
                continue
            work_kind = activity.work.kind if activity.work is not None else ""
            artifact = (self._artifact_for_activity(context, activity)
                        if work_kind not in ("reading", "sleep") and activity.reading is None else None)
            if activity.work is None and artifact is None:
                continue
            candidate_purpose = ("creation" if work_kind == "reading" or artifact is not None else "life")
            if purpose is not None and purpose != candidate_purpose:
                continue
            if preferences.reason(candidate_purpose):
                continue
            opportunity = Opportunity("activity-" + self._event_key(context, activity),
                context.scope, activity.updated_at, activity.updated_at + lifetime)
            if self._known(context, opportunity):
                continue
            try:
                operation_id = self._receipt(context, activity, at, has_artifact=artifact is not None)
                candidate_purpose, source = self._project(context, activity, operation_id, at)
            except (TaskError, KeyError):
                continue
            if artifact is not None:
                prepared = self.share_planner.prepare(
                    ShareMaterial.from_role_artifact(artifact),
                    resolved=context.actor,
                    capability="text",
                    observed_at=at,
                    authorizer=self.contacts.tasks.identity,
                    role_owner=self._owner(context),
                )
                if not prepared.is_success:
                    continue
            marker = {"activity_id": activity.activity_id, "revision": activity.revision,
                "operation_id": operation_id, "activity_hash": digest(activity), "purpose": candidate_purpose,
                "expires_at": stamp(opportunity.expires_at)}
            if artifact is not None:
                summary = ("角色刚写完一段自己的小作品或随笔，想顺手递给对方看看、分享一点创作时的念头；"
                           "不夸大篇幅或外部发表事实，不合适就跳过。")
            elif candidate_purpose == "creation":
                summary = ("刚完成了一段真实阅读，像合上书随手跟熟人念叨一句最触动或好玩的点，自然带出自己的感受，不写读书报告；不合适就跳过。")
            else:
                summary = ("角色的一段睡眠确实结束了，可以像刚缓过神来那样自然带一句此刻的状态或近况；不要凭空补出梦或醒后经历。")
            thought = Thought("activity-event-" + digest(marker), opportunity, ThoughtKind.CONVERSATION, summary,
                              EvidenceSnapshot(context.scope, at, (source,)), 1.0)
            return (opportunity, (ContactIntent(candidate_purpose, thought),), marker), True
        more = len(rows) == PAGE_SIZE
        self._scans[context.key] = (token, cursor if more else None, at if more else at + POLL_INTERVAL)
        return None, more

    def validate(self, context, marker, at):
        if not isinstance(marker, dict) or set(marker) != {
                "activity_id", "revision", "operation_id", "activity_hash", "purpose", "expires_at"}:
            raise TaskError("contact_activity_invalid", "automatic activity requires its exact original event")
        try:
            activity = self.life.activity(marker["activity_id"], owner=self._owner(context))
        except KeyError as error:
            raise TaskError("contact_activity_unavailable", "contact activity is no longer available") from error
        if activity.revision != marker["revision"] or digest(activity) != marker["activity_hash"]:
            raise TaskError("contact_activity_changed", "contact activity changed after selection")
        artifact = self._artifact_for_activity(context, activity) if activity.reading is None else None
        operation_id = self._receipt(context, activity, at, has_artifact=artifact is not None)
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        expires = activity.updated_at + timedelta(seconds=preferences.values["event_max_age_seconds"])
        if operation_id != marker["operation_id"] or marker["expires_at"] != stamp(expires) or at >= expires:
            raise TaskError("contact_activity_expired", "the original activity opportunity is no longer current")
        purpose, _, _ = self._material(context, activity, at)
        if marker["purpose"] != purpose:
            raise TaskError("contact_activity_changed", "contact cannot change its factual purpose")
        preferences.require_contact(purpose)
