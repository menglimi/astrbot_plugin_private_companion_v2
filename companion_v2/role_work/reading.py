"""Record a trusted reader's completion without simulating reading from a timer.

The reader supplies the original hash, consumed character range and completion
time. This endpoint checks the report and commits it with the activity and its
existing operation receipt. It neither performs reading nor infers comprehension.
"""

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import RoleOwnerRef, SourceRef, normalize_utc
from companion_v2.sources.repositories import SourceRepository

from .models import RoleActivityState, RoleReadingReceipt


READING_RECORD = "role.reading.record"


class RoleReadingService:
    def __init__(self, role_life, tasks, *, require_running=None):
        if role_life.runtime is not tasks.runtime:
            raise ValueError("reading must share its original activity and task runtime")
        self.life, self.tasks, self.runtime = role_life, tasks, role_life.runtime
        self.sources = SourceRepository(self.runtime)
        self.require_running = require_running

    @outcome
    def record_completion(self, context: TaskContext, *, activity_id, source: SourceRef,
                          content_hash, start_offset, end_offset, completed_at,
                          expected_revision, operation_id, reflection=""):
        """Trusted completion port; repeated requests retain their original timestamp."""
        if not isinstance(context, TaskContext) or not isinstance(source, SourceRef):
            raise ValueError("reading completion requires its task context and source")
        if self.require_running is not None:
            self.require_running()
        now = normalize_utc(self.tasks.now(), field="reading observed time")
        at = normalize_utc(completed_at, field="reading completion")
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        with self.runtime.transaction():
            require(self.tasks.authorize_context(context, action=READING_RECORD, observed_at=now))
            try:
                activity = self.life.activity(activity_id, owner=owner)
            except KeyError as error:
                raise TaskError("reading_activity_unavailable", "reading activity is unavailable for this role") from error
            if activity.scope != context.scope or source.scope != context.scope:
                raise TaskError("reading_context_mismatch", "reading must retain its original scope and role")
            if at > now or at < activity.started_at:
                raise TaskError("reading_time_invalid", "completion must lie between the activity start and now")
            require(self.sources.validate_reference(source, observed_at=now))
            record = require(self.sources.read(source, resolved=context.actor, capability=READING_RECORD,
                                               observed_at=now, authorizer=self.tasks.identity))
            if not set(context.audience.recipients).issubset(record.audience.recipients):
                raise TaskError("source_audience_mismatch", "reading original is not available to this audience")
            if content_hash != record.content_hash or content_hash != digest(record.payload):
                raise TaskError("reading_source_changed", "completion must identify the original text that was read")
            receipt = RoleReadingReceipt(source, content_hash, len(record.payload), start_offset, end_offset, at, reflection)
            if not record.payload[start_offset:end_offset].strip():
                raise TaskError("reading_span_empty", "completion cannot report only blank text")
            return self.life.transition_activity(activity_id, owner=owner, expected_revision=expected_revision,
                state=RoleActivityState.COMPLETED, operation_id=operation_id, observed_at=at, reading=receipt)
