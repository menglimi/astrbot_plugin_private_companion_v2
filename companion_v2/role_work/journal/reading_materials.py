"""Dated excerpts limited to the exact text span in a trusted reading receipt."""

from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import RoleOwnerRef, VersionRef
from companion_v2.role_work.models import RoleActivityState
from companion_v2.sources.repositories import SourceRepository

from .material_producer import JournalMaterialPage
from .materials import JournalMaterial, MaterialKind, source_origin
from .models import JournalContext


class RoleReadingJournalMaterialProducer:
    def __init__(self, role_life, tasks):
        if role_life.runtime is not tasks.runtime:
            raise ValueError("reading materials must use the original V2 runtime")
        self.life, self.tasks = role_life, tasks
        self.sources = SourceRepository(role_life.runtime)

    def for_day(self, context: TaskContext, target: JournalContext, *, limit=50, after_id=None):
        if not isinstance(context, TaskContext) or not isinstance(target, JournalContext):
            raise ValueError("reading materials need their task context and dated journal scope")
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("reading material page size must be between 1 and 64")
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        if target.key.owner != owner or context.scope != target.scope:
            raise TaskError("reading_context_mismatch", "reading material must retain its original role and scope")
        with self.life.runtime.read_snapshot():
            at = self.tasks.now()
            require(self.tasks.authorize_context(context, action="role.journal.write", observed_at=at))
            records = self.life.activities_for_role(owner, state=RoleActivityState.COMPLETED,
                                                     limit=limit, after_id=after_id)
            zone = ZoneInfo(target.timezone)
            materials = []
            for activity in records:
                receipt = activity.reading
                if receipt is None or activity.scope != target.scope:
                    continue
                day = receipt.completed_at.astimezone(zone).date().isoformat()
                if day != target.key.local_date:
                    continue
                require(self.sources.validate_reference(receipt.source, observed_at=at))
                record = require(self.sources.read(receipt.source, resolved=context.actor,
                    capability="role.journal.write", observed_at=at, authorizer=self.tasks.identity))
                if not set(context.audience.recipients).issubset(record.audience.recipients):
                    raise TaskError("source_audience_mismatch", "reading original is not available to this audience")
                if (receipt.content_hash != record.content_hash or receipt.content_hash != digest(record.payload)
                        or receipt.text_length != len(record.payload)):
                    raise TaskError("reading_source_changed", "reading receipt no longer matches its original text")
                detail = record.payload[receipt.start_offset:receipt.end_offset].strip()
                if len(detail) > 8192:
                    detail = detail[:8192] + "……（已读片段较长，仅保留开头）"
                materials.append(JournalMaterial(
                    "role-reading-content-" + digest([activity.activity_id, activity.revision]),
                    MaterialKind.READING, "本次已读原文（以完成回执的阅读范围为准）：" + detail,
                    source_origin(receipt.source), day, receipt.source,
                    VersionRef(activity.activity_id, activity.revision)))
                if receipt.reflection:
                    materials.append(JournalMaterial(
                        "role-reading-reflection-" + digest([activity.activity_id, activity.revision]),
                        MaterialKind.REFLECTION, "读后主观联想（不是原文事实）：" + receipt.reflection,
                        source_origin(receipt.source), day, receipt.source,
                        VersionRef(activity.activity_id, activity.revision)))
            next_cursor = records[-1].activity_id if len(records) == limit else None
            return JournalMaterialPage(tuple(materials), next_cursor)
