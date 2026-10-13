"""Resolve every memory use through current identity, role and source authority."""

import json

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.personas import PersonaDirectory
from companion_v2.sources.repositories import SourceRepository

from .models import Evidence, owner_key


class MemoryAccess:
    def __init__(self, tasks, policy, *, operator=None, settings=None):
        self.tasks, self.runtime, self.policy = tasks, tasks.runtime, policy
        self.operator = operator
        self.settings = settings
        self.sources = SourceRepository(self.runtime)
        self.access = ObjectAccessPolicy(self.runtime)
        self.personas = PersonaDirectory(self.runtime)
        self.sent_sources = None

    def policy_for(self, context):
        return self.settings.policy(context) if self.settings else self.policy

    def check(self, context, action="memory.read", *, at=None):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)):
            raise TaskError("memory_private_context_required", "private memory requires its original private audience")
        if self.operator is None and not self.policy_for(context).enabled:
            raise TaskError("memory_disabled", "memory is disabled in this runtime")
        if self.operator is None:
            require(self.tasks.check_context_access(context, action=action, observed_at=at or self.tasks.now()))
        else:
            self.tasks._context(context, at or self.tasks.now())
            require(self.access.scope_access(self.operator, scope=context.scope, action="memory.manage",
                observed_at=at or self.tasks.now(), owner=context.actor.subject))
        return owner_key(context)

    def authorize(self, resolved, *, scope, capability, observed_at):
        # SourceRepository's authorization port. Never infer a capability from text.
        return self.access.scope_access(self.operator or resolved, scope=scope, action="memory.manage" if self.operator else capability,
            observed_at=observed_at, allow_private_owner=True)

    def source(self, context, reference, *, action="memory.read", at=None):
        at = at or self.tasks.now()
        self.check(context, action, at=at)
        if self.runtime.read_one("SELECT 1 FROM memory_guards WHERE owner_key = ? AND evidence_key = ? AND reason = 'forgotten' LIMIT 1",
                                 (owner_key(context), digest(reference))):
            raise TaskError("memory_evidence_forgotten", "this original source was excluded from memory use by a forgetting request")
        scope = reference.scope
        if not scope.is_resolved or scope.kind is not ScopeKind.PRIVATE or scope.bot_id != context.scope.bot_id:
            raise TaskError("memory_source_scope", "this memory profile requires an authorized private source")
        persona = require(self.personas.resolve(scope, observed_at=at))
        if (persona.route.user != context.actor.subject or persona.binding.role != context.role_binding.role):
            raise TaskError("memory_source_scope", "source belongs to another human or role")
        if reference.owner == "conversation.confirmed_reply":
            if self.sent_sources is None:
                raise TaskError("memory_source_unavailable", "confirmed reply owner is unavailable")
            self.sent_sources.validate(context, reference)
        from companion_v2.conversation.native_observations import NATIVE_OWNERS, source_row, validate_observation
        if reference.owner in NATIVE_OWNERS:
            observation = source_row(self.runtime, reference)
            if observation is None:
                raise TaskError("memory_source_unavailable", "native observation is unavailable")
            validate_observation(self.runtime, observation, context, reference)
        record = require(self.sources.read(reference, resolved=context.actor, capability=action,
            observed_at=at, authorizer=self))
        if not set(context.audience.recipients).issubset(record.audience.recipients):
            raise TaskError("memory_audience_denied", "source is unavailable to this audience")
        return record

    def capture(self, context, reference, *, start=0, end=None, action="memory.read"):
        record = self.source(context, reference, action=action)
        end = min(len(record.payload), start + self.policy_for(context).source_chars) if end is None else end
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(record.payload):
            raise ValueError("source span is outside the original text")
        speaker, kind = None, "source"
        if reference.owner == "conversation.confirmed_reply":
            speaker, kind = context.role_binding.role.subject_id, "bot_message"
        from companion_v2.conversation.native_observations import NATIVE_OWNERS, source_row, validate_observation
        if reference.owner in NATIVE_OWNERS:
            observation = source_row(self.runtime, reference)
            if observation is None:
                raise TaskError("memory_source_unavailable", "native observation is unavailable")
            speaker, kind = validate_observation(self.runtime, observation, context, reference)
            return Evidence(reference, record.content_hash, start, end, digest(record.payload[start:end]), speaker, kind)
        # Attribution comes from the captured host event, never a model-supplied name.
        for row in self.runtime.read_all("""SELECT i.event_json, b.context_json FROM conversation_inputs i
            JOIN conversation_batches b ON b.batch_id = i.batch_id
            WHERE json_extract(i.event_json, '$.source.source_id') = ? AND i.withdrawn = 0""", (reference.source_id,)):
            from .codec import source
            event, stored = json.loads(row["event_json"]), json.loads(row["context_json"])
            if source(event["source"]) == reference:
                speaker, kind = stored["actor"]["subject"]["subject_id"], "human_message"
                break
        return Evidence(reference, record.content_hash, start, end, digest(record.payload[start:end]), speaker, kind)

    def evidence(self, context, evidence, *, action="memory.read", at=None):
        record = self.source(context, evidence.source, action=action, at=at)
        if (record.content_hash != evidence.content_hash or evidence.end > len(record.payload)
                or digest(record.payload[evidence.start:evidence.end]) != evidence.span_hash):
            raise TaskError("memory_evidence_changed", "the exact evidence span changed")
        return record.payload[evidence.start:evidence.end]
