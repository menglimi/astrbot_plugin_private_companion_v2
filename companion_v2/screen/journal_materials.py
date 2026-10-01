"""Explicit, permission-checked Screen feedback for dated journal writing."""

from zoneinfo import ZoneInfo

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.role_work.journal.material_producer import JournalMaterialPage
from companion_v2.role_work.journal.materials import JournalMaterial, MaterialKind
from companion_v2.role_work.journal.models import JournalContext
from companion_v2.storage.codec import decode_timestamp

from .models import ScreenFeedbackKind


class ScreenJournalMaterialProducer:
    """Only a user-authorized JOURNAL feedback anchor can enter the diary.

    The fusion switch lives on the Screen group: this producer is wired into the
    existing journal chain, so it answers with an empty page whenever the window
    has not asked for screen material, and it never widens the writer's own
    authorization.
    """

    def __init__(self, tasks, screens, *, settings=None):
        if tasks.runtime is not screens.runtime:
            raise ValueError("screen journal materials must use the original V2 runtime")
        self.tasks, self.screens, self.runtime = tasks, screens, tasks.runtime
        self.settings = settings

    def for_day(self, context: TaskContext, target: JournalContext, *, limit=50, after_id=None):
        if (not isinstance(context, TaskContext) or not isinstance(target, JournalContext)
                or type(limit) is not int or not 1 <= limit <= 64):
            raise ValueError("screen journal materials need a bounded authorized dated scope")
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        if context.scope != target.scope or target.key.owner != owner:
            raise TaskError("screen_journal_context_mismatch", "screen journal material belongs to another role or scope")
        with self.runtime.read_snapshot():
            at = self.tasks.now()
            require(self.tasks.authorize_context(context, action="role.journal.write", observed_at=at))
            settings = self._settings(context, at)
            if settings is None or not settings["journal_material_enabled"]:
                return JournalMaterialPage((), None)
            max_chars = settings["journal_material_max_chars"]
            rows = self.runtime.read_all(
                """SELECT f.feedback_id, f.capture_id, c.received_at, s.scope_kind, s.native_scope_id
                   FROM screen_feedback_anchors f
                   JOIN screen_captures c ON c.capture_id = f.capture_id
                   JOIN sources s ON s.source_id = c.source_id AND s.lineage_id = c.source_lineage_id
                        AND s.source_revision = c.source_revision
                   WHERE f.feedback_kind = 'journal' AND f.feedback_id > ?
                     AND s.installation_id = ? AND s.platform = ? AND s.scope_kind = ? AND s.native_scope_id = ?
                   ORDER BY f.feedback_id LIMIT ?""",
                (after_id or "", target.scope.installation_id, target.scope.platform,
                 target.scope.kind.value, target.scope.native_scope_id, limit),
            )
            zone = ZoneInfo(target.timezone)
            materials = []
            for row in rows:
                if row["received_at"] is None:
                    continue
                if decode_timestamp(row["received_at"]).astimezone(zone).date().isoformat() != target.key.local_date:
                    continue
                reference = require(self.screens.published_reference(row["capture_id"], scope=target.scope))
                result = require(self.screens.read_feedback(row["feedback_id"], capture=reference,
                    resolved=context.actor, observed_at=at))
                if result.anchor.kind is not ScreenFeedbackKind.JOURNAL or result.analysis is None:
                    continue
                meaning = result.analysis.interpretation.strip()
                if not meaning:
                    continue
                materials.append(JournalMaterial(
                    material_id="screen-journal-" + digest([row["feedback_id"], result.analysis.version]),
                    kind=MaterialKind.REFLECTION,
                    text="用户明确标记为日记素材的屏幕观察（模型解读，不等同于屏幕原文）：" + meaning[:max_chars],
                    origin="screen-feedback-" + digest(row["feedback_id"]),
                    local_date=target.key.local_date,
                    source=reference.source,
                ))
            return JournalMaterialPage(tuple(materials), rows[-1]["feedback_id"] if len(rows) == limit else None)

    def _settings(self, context, at):
        if self.settings is None:
            return None
        try:
            return self.settings.read(context, at)
        except TaskError:
            return None
