"""Conservative, source-bound journal material from trusted role and conversation records."""

from dataclasses import dataclass
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import ReferenceValidationError, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.role_work.models import (RoleActivityState, RoleArtifactJournalMeaning,
                                         RoleArtifactKind)
from companion_v2.sources.repositories import SourceRepository

from .materials import JournalMaterial, MaterialKind, source_origin
from .models import JournalContext


_STATUS = {
    RoleActivityState.PLANNED: "计划中",
    RoleActivityState.ACTIVE: "进行中",
    RoleActivityState.PAUSED: "已暂停",
    RoleActivityState.COMPLETED: "已完成",
    RoleActivityState.CANCELLED: "已取消",
}


@dataclass(frozen=True)
class JournalMaterialPage:
    materials: tuple[JournalMaterial, ...]
    next_cursor: str | None

    @property
    def activity_refs(self) -> tuple[VersionRef, ...]:
        return tuple(dict.fromkeys(item.activity for item in self.materials if item.activity is not None))

    @property
    def source_refs(self) -> tuple[SourceRef, ...]:
        return tuple(dict.fromkeys(item.source for item in self.materials if item.source is not None))


class RoleActivityJournalMaterialProducer:
    """Project current role-activity records into dated, typed writing material.

    This producer reads no conversation history and makes no claim about activity
    beyond its explicit lifecycle state. Paging is over the owner's stable
    inventory; only records from the exact journal scope and local date survive.
    """

    def __init__(self, role_life):
        self.role_life = role_life

    def for_day(self, target: JournalContext, *, limit=50, after_id=None) -> JournalMaterialPage:
        if not isinstance(target, JournalContext):
            raise ValueError("journal materials need an explicit dated scope")
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ReferenceValidationError("journal material page size must be between 1 and 64")
        records = self.role_life.activities_for_role(target.key.owner, limit=limit, after_id=after_id)
        zone = ZoneInfo(target.timezone)
        materials = []
        for activity in records:
            if activity.scope != target.scope:
                continue
            occurred_at = activity.updated_at or activity.started_at
            local_date = occurred_at.astimezone(zone).date().isoformat()
            if local_date != target.key.local_date:
                continue
            detail = "；".join(value for value in (activity.description, activity.checkpoint) if value.strip())
            source = activity.reading.source if activity.reading is not None else None
            if activity.reading is not None:
                receipt = activity.reading
                extent = ("本次提供的原文" if receipt.covers_source else
                          f"原文第 {receipt.start_offset + 1} 至 {receipt.end_offset} 个字符的片段")
                detail = f"已完成一次阅读，实际读过{extent}；只证明该范围已读，不推断整本书读完或已经理解。"
            if not detail:
                continue
            kind = (MaterialKind.PLAN if activity.state in
                    (RoleActivityState.PLANNED, RoleActivityState.CANCELLED) else MaterialKind.ACTION)
            materials.append(JournalMaterial(
                material_id="role-activity-" + digest([activity.activity_id, activity.revision]),
                kind=kind,
                text=f"活动状态：{_STATUS[activity.state]}；{detail}",
                origin=source_origin(source) if source is not None else "role-activity-" + digest(activity.activity_id),
                local_date=local_date,
                source=source,
                activity=VersionRef(activity.activity_id, activity.revision),
            ))
        next_cursor = records[-1].activity_id if len(records) == limit else None
        return JournalMaterialPage(tuple(materials), next_cursor)


class RoleConversationJournalMaterialProducer:
    """Project authorized, non-withdrawn inbound messages as attributed dialogue."""

    def __init__(self, conversations):
        self.conversations = conversations

    def for_day(
        self, task_context: TaskContext, target: JournalContext, *, limit=50, after_id=None
    ) -> JournalMaterialPage:
        if not isinstance(task_context, TaskContext) or not isinstance(target, JournalContext):
            raise ValueError("conversation materials need an authorized task and dated journal scope")
        owner = RoleOwnerRef(target.scope.installation_id, target.scope.bot_id,
                             task_context.role_binding.role.subject_id)
        if (task_context.scope != target.scope or task_context.role_binding.scope != target.scope
                or target.key.owner != owner):
            raise ReferenceValidationError("conversation material must retain its exact role and scope")
        native_prefix = "native-observation:"
        if isinstance(after_id, str) and after_id.startswith(native_prefix):
            return self._native_page(task_context, target, limit=limit, after_id=after_id[len(native_prefix):])
        page = self.conversations.journal_inputs(task_context, limit=limit, after_id=after_id)
        zone = ZoneInfo(target.timezone)
        materials = []
        for item in page.items:
            event = item.event
            if event.scope != target.scope:
                continue
            local_date = event.received_at.astimezone(zone).date().isoformat()
            if local_date != target.key.local_date:
                continue
            payload = item.source.payload.strip()
            detail = payload if payload else "收到了一条没有可读取文本的消息。"
            if len(detail) > 8192:
                detail = detail[:8192] + "……（消息较长，仅保留开头）"
            materials.append(JournalMaterial(
                material_id="conversation-message-" + digest(event.scoped_key),
                kind=MaterialKind.CONVERSATION,
                text="对方当时表达：" + detail,
                origin="conversation-input-" + digest(event.scoped_key),
                local_date=local_date,
                source=event.source,
            ))
        if page.next_cursor is None and len(page.items) < limit:
            native = self._native_page(task_context, target, limit=limit - len(page.items))
            return JournalMaterialPage(tuple(materials) + native.materials, native.next_cursor)
        return JournalMaterialPage(tuple(materials), page.next_cursor)

    def _native_page(self, context, target, *, limit, after_id=None):
        from companion_v2.conversation.native_observations import observations_available, validate_observation
        from companion_v2.memory.codec import source

        runtime = self.conversations.runtime
        self.conversations.authorize(context)
        if not observations_available(runtime):
            return JournalMaterialPage((), None)
        values = [context.key]
        condition = ""
        if after_id is not None:
            cursor = runtime.read_one("""SELECT observed_at FROM conversation_native_observations
                WHERE context_key = ? AND kind = 'input' AND observation_id = ?""", (context.key, after_id))
            if cursor is None:
                raise TaskError("message_cursor_invalid", "native writing cursor belongs to another conversation")
            condition = " AND (observed_at > ? OR (observed_at = ? AND observation_id > ?))"
            values.extend((cursor["observed_at"], cursor["observed_at"], after_id))
        values.append(limit)
        rows = runtime.read_all("""SELECT * FROM conversation_native_observations
            WHERE context_key = ? AND kind = 'input' AND delivery_state = 'input_observed'""" + condition
            + " ORDER BY observed_at, observation_id LIMIT ?", tuple(values))
        zone, materials = ZoneInfo(target.timezone), []
        for row in rows:
            try:
                reference = source(json.loads(row["source_json"]))
                validate_observation(runtime, row, context, reference)
                if reference.scope != target.scope:
                    continue
                local_date = datetime.fromisoformat(row["observed_at"]).astimezone(zone).date().isoformat()
                if local_date != target.key.local_date:
                    continue
                record = self.conversations._read_source(reference, context, "text", self.conversations.tasks.now())
                if record.content_hash != row["content_hash"]:
                    raise TaskError("message_input_changed", "native journal input no longer matches its source")
            except TaskError:
                continue
            detail = record.payload.strip()
            if len(detail) > 8192:
                detail = detail[:8192] + "……（消息较长，仅保留开头）"
            materials.append(JournalMaterial(
                material_id="conversation-message-" + digest(row["observation_id"]),
                kind=MaterialKind.CONVERSATION, text="对方当时表达：" + detail,
                origin="native-conversation-input-" + digest(row["observation_id"]),
                local_date=local_date, source=reference))
        cursor = "native-observation:" + rows[-1]["observation_id"] if len(rows) == limit else None
        return JournalMaterialPage(tuple(materials), cursor)


class RoleTextArtifactJournalMaterialProducer:
    """Separate catalog evidence from authorized, explicitly classified excerpts.

    Each method scans at most `limit` original artifacts and yields at most one
    material per record. Scan both inventories independently; an empty filtered
    page can still have a continuation cursor. Their union must fit the writing
    contract, and shared source origins do not count as independent evidence.
    """

    def __init__(self, role_life, *, tasks=None):
        if tasks is not None and tasks.runtime is not role_life.runtime:
            raise ValueError("artifact contents must use the original V2 runtime")
        self.role_life = role_life
        self.tasks = tasks
        self.sources = SourceRepository(role_life.runtime) if tasks is not None else None

    def _inventory(self, target, limit, after_id):
        if not isinstance(target, JournalContext):
            raise ValueError("journal materials need an explicit dated scope")
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ReferenceValidationError("journal material page size must be between 1 and 64")
        records = self.role_life.artifacts_for_scope(
            target.scope, owner=target.key.owner, limit=limit, after_id=after_id)
        zone = ZoneInfo(target.timezone)
        selected = []
        for artifact in records:
            if artifact.kind is not RoleArtifactKind.TEXT or artifact.source.scope != target.scope:
                continue
            local_date = artifact.created_at.astimezone(zone).date().isoformat()
            if local_date != target.key.local_date:
                continue
            activity = self.role_life.activity(artifact.activity_id, owner=target.key.owner)
            if activity.scope != target.scope:
                continue
            selected.append((artifact, activity, local_date))
        next_cursor = records[-1].artifact_id if len(records) == limit else None
        return selected, next_cursor

    @staticmethod
    def _origin(artifact):
        if artifact.journal_meaning is RoleArtifactJournalMeaning.UNCLASSIFIED:
            return "role-artifact-" + digest(artifact.artifact_id)
        return source_origin(artifact.source)

    def for_day(self, target: JournalContext, *, limit=50, after_id=None) -> JournalMaterialPage:
        """Trusted catalog projection; never opens an artifact's original text."""
        records, next_cursor = self._inventory(target, limit, after_id)
        materials = []
        for artifact, activity, local_date in records:
            kind = MaterialKind.ACTION
            text = "完成了一份文本产物；正文仍保存在原来源中。"
            if artifact.journal_meaning is RoleArtifactJournalMeaning.CREATIVE_TEXT:
                text = "完成了一份创作文本；作品内容仍保存在原来源中，未提供情节细节。"
            if artifact.journal_meaning is RoleArtifactJournalMeaning.READING:
                kind = MaterialKind.READING
                text = "收存了一份阅读材料；这条目录记录不证明已经阅读或读完。原文未在此处提供。"
            materials.append(JournalMaterial(
                material_id="role-text-artifact-" + digest(artifact.artifact_id),
                kind=kind,
                text=text,
                origin=self._origin(artifact),
                local_date=local_date,
                source=artifact.source,
                activity=VersionRef(activity.activity_id, activity.revision),
            ))
        return JournalMaterialPage(tuple(materials), next_cursor)

    def contents_for_day(
        self, task_context: TaskContext, target: JournalContext, *, limit=50, after_id=None
    ) -> JournalMaterialPage:
        """Read classified originals under current writing permission and source ACL."""
        if not isinstance(task_context, TaskContext) or not isinstance(target, JournalContext):
            raise ValueError("artifact contents need an authorized task and dated journal scope")
        owner = RoleOwnerRef(task_context.scope.installation_id, task_context.scope.bot_id,
                             task_context.role_binding.role.subject_id)
        if task_context.scope != target.scope or target.key.owner != owner:
            raise ReferenceValidationError("artifact contents must retain their exact role and scope")
        if self.tasks is None:
            raise ValueError("artifact content access requires the host task authority")
        with self.role_life.runtime.read_snapshot():
            at = self.tasks.now()
            require(self.tasks.authorize_context(task_context, action="role.journal.write", observed_at=at))
            records, next_cursor = self._inventory(target, limit, after_id)
            materials = []
            for artifact, activity, local_date in records:
                if artifact.journal_meaning is RoleArtifactJournalMeaning.UNCLASSIFIED:
                    continue
                require(self.sources.validate_reference(artifact.source, observed_at=at))
                record = require(self.sources.read(artifact.source, resolved=task_context.actor,
                    capability="role.journal.write", observed_at=at, authorizer=self.tasks.identity))
                if not set(task_context.audience.recipients).issubset(record.audience.recipients):
                    raise TaskError("source_audience_mismatch", "artifact is not available to the writing audience")
                if record.content_hash != digest(record.payload):
                    raise TaskError("journal_artifact_source_changed", "artifact text no longer matches its source hash")
                detail = record.payload.strip()
                if not detail:
                    continue
                if len(detail) > 8192:
                    detail = detail[:8192] + "……（原文较长，仅保留开头）"
                if artifact.journal_meaning is RoleArtifactJournalMeaning.CREATIVE_TEXT:
                    kind, prefix = MaterialKind.CREATIVE_TEXT, "创作原文（作品内容）："
                else:
                    kind, prefix = MaterialKind.READING, "收存的阅读材料原文（不代表已阅读或读完）："
                materials.append(JournalMaterial(
                    material_id="role-text-artifact-content-" + digest(artifact.artifact_id),
                    kind=kind,
                    text=prefix + detail,
                    origin=self._origin(artifact),
                    local_date=local_date,
                    source=artifact.source,
                    activity=VersionRef(activity.activity_id, activity.revision),
                ))
            return JournalMaterialPage(tuple(materials), next_cursor)
