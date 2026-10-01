"""Core administrators manage an explicit relationship without impersonating its human."""

from __future__ import annotations

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ReferenceValidationError, RoleOwnerRef, ScopeKind
from companion_v2.identity_policy.models import ResolvedIdentity

from .models import RelationshipMemoryState as State
from .provenance import same_private_route
from .service import RelationshipMemoryService


class RelationshipMemoryManagement:
    """An authorized, bounded projection over the relationship owner's primitives."""

    STATES = {"review": State.REVIEWED, "adopt": State.ADOPTED, "retract": State.RETRACTED}

    def __init__(self, service: RelationshipMemoryService):
        self.service = service
        self.runtime = service.runtime

    def _authorize(self, operator: ResolvedIdentity, context: TaskContext, action: str, at):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)):
            raise TaskError("relationship_management_scope", "select one resolved private relationship")
        current = require(self.service._access.identity.resolve_authenticated(context.actor.principal, observed_at=at))
        if (current.subject != context.actor.subject or current.binding_id != context.actor.binding_id
                or current.binding_revision != context.actor.binding_revision):
            raise TaskError("relationship_target_changed", "the selected relationship participant changed")
        persona = require(self.service._personas.resolve(context.scope, observed_at=at))
        if persona.route.user != current.subject or persona.binding != context.role_binding:
            raise TaskError("relationship_target_changed", "the selected relationship role changed")
        access = require(self.service._access.scope_access(operator, scope=context.scope,
            action="relationship.memory." + action, observed_at=at, owner=current.subject, core_only=True))
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id), access.policy_revision

    @staticmethod
    def _token(operator, context, memory_id, revision, policy_revision):
        return digest(["relationship-management.v1", operator.subject, operator.binding_id,
                       operator.binding_revision, context.key, memory_id, revision, policy_revision])

    def _memory(self, memory_id, owner, context):
        if not self.service._valid_memory_id(memory_id):
            raise TaskError("relationship_memory_invalid", "select an explicit memory")
        try:
            memory = self.service._ledger.memory(memory_id, owner=owner, subject=context.actor.subject)
        except KeyError:
            raise TaskError("relationship_memory_not_found", "memory is unavailable in the selected relationship") from None
        if not same_private_route(memory.scope, context.scope):
            raise TaskError("relationship_memory_not_found", "memory is unavailable in the selected scope")
        return memory

    def _unavailable(self, memory, context, at, operator):
        if any(not same_private_route(source.scope, context.scope) for source in memory.sources):
            return "relationship_source_scope"
        for checked in (self.service._check_attribution(memory),
                        self.service.validate_material(memory, actor=context.actor, scope=context.scope,
                                                       observed_at=at, operator=operator)):
            if not checked.is_success:
                return checked.failure.code
        return None

    def _project(self, memory, operator, context, policy_revision, at):
        unavailable = self._unavailable(memory, context, at, operator)
        actions = []
        if memory.state is not State.RETRACTED:
            if unavailable is None:
                if memory.state is State.PROPOSED:
                    actions.append("review")
                elif memory.state is State.REVIEWED:
                    actions.append("adopt")
                actions.append("revise")
            actions.append("retract")
        attribution = {name: getattr(memory, name).subject_id if getattr(memory, name) else None
                       for name in ("reviewed_by", "adopted_by", "retracted_by", "revised_by")}
        return {"memory_id": memory.memory_id, "revision": memory.revision,
                "kind": memory.kind.value, "state": memory.state.value,
                "interpretation": memory.interpretation if unavailable is None else None,
                "emotion_subject": memory.emotion_subject.value if memory.emotion_subject else None,
                "observed_at": memory.observed_at.isoformat(), "updated_at": memory.updated_at.isoformat(),
                "source_count": len(memory.sources), "unavailable_reason": unavailable,
                "attribution": attribution, "actions": actions,
                "view_token": self._token(operator, context, memory.memory_id, memory.revision, policy_revision)}

    @outcome
    def list(self, *, operator, context, state=None, limit=20, after_id=None):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise TaskError("relationship_query_invalid", "page size must be between 1 and 50")
        if after_id is not None and not self.service._valid_memory_id(after_id):
            raise TaskError("relationship_query_invalid", "use an original memory cursor")
        if state is not None:
            try:
                state = State(state)
            except (ValueError, TypeError):
                raise TaskError("relationship_query_invalid", "unknown relationship state") from None
        at = self.service._time(None)
        with self.runtime.read_snapshot():
            owner, policy_revision = self._authorize(operator, context, "read", at)
            records = self.service._ledger.for_relationship(owner, context.actor.subject,
                state=state, route=context.scope, limit=limit + 1, after_id=after_id)
            page = records[:limit]
            return {"context_key": context.key, "role_id": owner.persona_id,
                    "subject_id": context.actor.subject.subject_id, "bot_id": owner.bot_id,
                    "scope_label": context.scope.native_scope_id, "operator_id": operator.subject.subject_id,
                    "items": [self._project(m, operator, context, policy_revision, at) for m in page],
                    "next_cursor": page[-1].memory_id if len(records) > limit else None}

    @outcome
    def command(self, *, operator, context, memory_id, action, expected_revision, view_token,
                operation_key, interpretation=None):
        if action not in (*self.STATES, "revise"):
            raise TaskError("relationship_command_invalid", "unknown relationship action")
        if type(expected_revision) is not int or expected_revision < 1:
            raise TaskError("relationship_command_invalid", "the original revision is required")
        if (type(operation_key) is not str or not 1 <= len(operation_key) <= 128
                or operation_key != operation_key.strip()):
            raise TaskError("relationship_command_invalid", "an original operation key is required")
        if (action == "revise" and (type(interpretation) is not str or not interpretation.strip()
                or len(interpretation) > 16384) or action != "revise" and interpretation is not None):
            raise TaskError("relationship_command_invalid", "provide complete text only for a correction")
        at = self.service._time(None)
        with self.runtime.transaction():
            owner, policy_revision = self._authorize(operator, context, action, at)
            expected_token = self._token(operator, context, memory_id, expected_revision, policy_revision)
            if type(view_token) is not str or view_token != expected_token:
                raise TaskError("relationship_view_stale", "refresh this relationship before confirming the change")
            memory = self._memory(memory_id, owner, context)
            unavailable = self._unavailable(memory, context, at, operator)
            if action != "retract" and unavailable:
                raise TaskError(unavailable, "the original relationship material is no longer available")
            operation_id = "relationship-management:" + digest([operator.subject, operation_key])
            arguments = dict(owner=owner, subject=context.actor.subject, scope=context.scope,
                expected_revision=expected_revision, operation_id=operation_id, observed_at=at,
                actor=operator.subject)
            try:
                if action == "revise":
                    applied = self.service._ledger.revise(memory_id, interpretation=interpretation,
                                                          sources=memory.sources, **arguments)
                else:
                    applied = self.service._ledger.transition(memory_id, state=self.STATES[action], **arguments)
            except ReferenceValidationError:
                raise TaskError("relationship_memory_conflict", "the record changed or this action no longer applies") from None
            # Replayed receipts confirm the original revision but never expose an older body.
            current = self._memory(memory_id, owner, context)
            return {"applied_revision": applied.revision, "operation_id": operation_id,
                    "item": self._project(current, operator, context, policy_revision, at)}
