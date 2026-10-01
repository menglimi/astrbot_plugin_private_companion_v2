"""Authorized relationship-memory operations for the current private role route."""

from __future__ import annotations

from datetime import datetime, timezone

from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import (
    ReferenceValidationError,
    RoleOwnerRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    normalize_utc,
)
from companion_v2.identity_policy.models import ResolvedIdentity
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.personas import PersonaDirectory
from companion_v2.relationships.ledger import PersistentRelationshipMemoryLedger
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.runtime import StorageRuntime

from .models import (
    RelationshipMemory,
    RelationshipMemoryKind,
    RelationshipMemoryState,
)


class RelationshipMemoryService:
    """Recheck human identity, private route, role, action access and source governance.

    The ledger remains a trusted storage primitive. This service is the boundary
    for current chat or management consumers that read or change relationship
    records.
    """

    _STATE_ACTIONS = {
        RelationshipMemoryState.REVIEWED: "relationship.memory.review",
        RelationshipMemoryState.ADOPTED: "relationship.memory.adopt",
        RelationshipMemoryState.RETRACTED: "relationship.memory.retract",
    }

    def __init__(self, runtime: StorageRuntime, *, now=None) -> None:
        self.runtime = runtime
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._ledger = PersistentRelationshipMemoryLedger(runtime, now=self.now)
        self._personas = PersonaDirectory(runtime)
        self._access = ObjectAccessPolicy(runtime)
        self._sources = SourceRepository(runtime)

    def _time(self, observed_at: datetime | None) -> datetime:
        return normalize_utc(self.now() if observed_at is None else observed_at, field="relationship operation time")

    def _authorize(
        self,
        actor: ResolvedIdentity,
        *,
        scope: ScopeRef,
        action: str,
        observed_at: datetime,
    ) -> Outcome[RoleOwnerRef]:
        if not isinstance(actor, ResolvedIdentity) or actor.subject.kind is not SubjectKind.HUMAN:
            return Outcome.failed("relationship_human_required", "relationship memory requires the current human participant")
        if (not isinstance(scope, ScopeRef) or not scope.is_resolved or scope.kind is not ScopeKind.PRIVATE
                or scope.installation_id != self.runtime.installation_id or not scope.bot_id):
            return Outcome.failed("relationship_private_scope_required", "relationship memory requires this installation's resolved private scope")
        if actor.subject.installation_id != scope.installation_id:
            return Outcome.failed("relationship_identity_mismatch", "human identity belongs to another installation")

        persona = self._personas.resolve(scope, observed_at=observed_at)
        if not persona.is_success:
            return Outcome(failure=persona.failure)
        current = persona.unwrap()
        if current.route.scene_kind is not ScopeKind.PRIVATE or current.route.user != actor.subject:
            return Outcome.failed("relationship_private_route_mismatch", "current private route does not belong to this human")

        access = self._access.scope_access(
            actor,
            scope=scope,
            action=action,
            observed_at=observed_at,
            owner=actor.subject,
            allow_private_owner=True,
        )
        if not access.is_success:
            return Outcome(failure=access.failure)
        return Outcome.success(RoleOwnerRef(scope.installation_id, scope.bot_id, current.binding.role.subject_id))

    def _validate_sources(
        self,
        references: tuple[SourceRef, ...],
        *,
        recipient: SubjectRef,
        observed_at: datetime,
    ) -> Outcome[bool]:
        if (not isinstance(references, tuple) or not references
                or any(not isinstance(reference, SourceRef) for reference in references)
                or len(set(references)) != len(references)):
            return Outcome.failed("relationship_sources_invalid", "sources must be a non-empty tuple of unique references")
        for reference in references:
            checked = self._sources.validate_reference_for_audience(
                reference,
                recipient=recipient,
                observed_at=observed_at,
            )
            if not checked.is_success:
                return Outcome(failure=checked.failure)
        return Outcome.success(True)

    @staticmethod
    def _check_attribution(memory: RelationshipMemory) -> Outcome[bool]:
        if (memory.state in (RelationshipMemoryState.REVIEWED, RelationshipMemoryState.ADOPTED)
                and memory.reviewed_by is None):
            return Outcome.failed("relationship_review_unattributed", "relationship review has no recorded human reviewer")
        if memory.state is RelationshipMemoryState.ADOPTED and memory.adopted_by is None:
            return Outcome.failed("relationship_adoption_unattributed", "relationship adoption has no recorded human confirmer")
        if memory.state is RelationshipMemoryState.RETRACTED and memory.retracted_by is None:
            return Outcome.failed("relationship_retraction_unattributed", "relationship retraction has no recorded human actor")
        return Outcome.success(True)

    def validate_material(self, memory: RelationshipMemory, *, actor: ResolvedIdentity,
                          scope: ScopeRef, observed_at: datetime, operator=None) -> Outcome[bool]:
        """Recheck every original route without rebasing historical evidence."""
        if memory.subject != actor.subject or memory.updated_at > observed_at:
            return Outcome.failed("relationship_source_scope", "relationship material has another subject or time")
        for original in dict.fromkeys((memory.scope, *(source.scope for source in memory.sources))):
            if (original.kind is not ScopeKind.PRIVATE or not original.is_resolved
                    or original.installation_id != scope.installation_id or original.bot_id != scope.bot_id):
                return Outcome.failed("relationship_source_scope", "relationship material requires its original private bot")
            persona = self._personas.resolve(original, observed_at=observed_at)
            if not persona.is_success:
                return Outcome(failure=persona.failure)
            resolved = persona.unwrap()
            if (resolved.route.user != actor.subject
                    or resolved.binding.role.subject_id != memory.owner.persona_id):
                return Outcome.failed("relationship_source_scope", "original source belongs to another human or role")
            if original != scope:
                access = self._access.scope_access(operator or actor, scope=original,
                    action="relationship.memory.read", observed_at=observed_at, owner=actor.subject,
                    allow_private_owner=operator is None, core_only=operator is not None)
                if not access.is_success:
                    return Outcome(failure=access.failure)
        return self._validate_sources(memory.sources, recipient=actor.subject, observed_at=observed_at)

    @staticmethod
    def _not_found() -> Outcome:
        return Outcome.failed("relationship_memory_not_found", "relationship memory does not exist for the current role and human")

    @staticmethod
    def _valid_memory_id(memory_id: str) -> bool:
        return isinstance(memory_id, str) and bool(memory_id) and memory_id == memory_id.strip() and len(memory_id) <= 512

    def propose(self, memory: RelationshipMemory, *, actor: ResolvedIdentity,
                observed_at: datetime | None = None, operation_id: str | None = None) -> Outcome[RelationshipMemory]:
        if not isinstance(memory, RelationshipMemory):
            return Outcome.failed("relationship_memory_invalid", "proposal must be a relationship memory record")
        at = self._time(observed_at)
        with self.runtime.transaction():
            authorization = self._authorize(actor, scope=memory.scope,
                action="relationship.memory.propose", observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            if memory.owner != authorization.unwrap() or memory.subject != actor.subject:
                return Outcome.failed("relationship_owner_mismatch", "proposal owner must be the current role and human pair")
            sources = self.validate_material(memory, actor=actor, scope=memory.scope, observed_at=at)
            if not sources.is_success:
                return Outcome(failure=sources.failure)
            try:
                return Outcome.success(self._ledger.add(memory) if operation_id is None else
                                       self._ledger.propose(memory, operation_id=operation_id))
            except (ReferenceValidationError, TaskError) as error:
                return Outcome.failed(error.code if isinstance(error, TaskError) else "relationship_memory_invalid", str(error))

    def read(self, memory_id: str, *, actor: ResolvedIdentity, scope: ScopeRef,
             observed_at: datetime | None = None) -> Outcome[RelationshipMemory]:
        if not self._valid_memory_id(memory_id):
            return Outcome.failed("relationship_memory_invalid", "memory ID must be an explicit opaque identifier")
        at = self._time(observed_at)
        with self.runtime.read_snapshot():
            authorization = self._authorize(actor, scope=scope,
                action="relationship.memory.read", observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            try:
                memory = self._ledger.memory(memory_id, owner=authorization.unwrap(), subject=actor.subject)
            except KeyError:
                return self._not_found()
            attributed = self._check_attribution(memory)
            if not attributed.is_success:
                return Outcome(failure=attributed.failure)
            sources = self.validate_material(memory, actor=actor, scope=scope, observed_at=at)
            if not sources.is_success:
                return Outcome(failure=sources.failure)
            return Outcome.success(memory)

    def for_relationship(
        self,
        *,
        actor: ResolvedIdentity,
        scope: ScopeRef,
        state: RelationshipMemoryState | None = None,
        kind: RelationshipMemoryKind | None = None,
        limit: int = 50,
        after_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> Outcome[tuple[RelationshipMemory, ...]]:
        at = self._time(observed_at)
        with self.runtime.read_snapshot():
            authorization = self._authorize(actor, scope=scope,
                action="relationship.memory.read", observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            try:
                values = self._ledger.for_relationship(authorization.unwrap(), actor.subject,
                    state=state, kind=kind, route=scope, limit=limit, after_id=after_id)
            except ReferenceValidationError as error:
                return Outcome.failed("relationship_query_invalid", str(error))
            for memory in values:
                attributed = self._check_attribution(memory)
                if not attributed.is_success:
                    return Outcome(failure=attributed.failure)
                sources = self.validate_material(memory, actor=actor, scope=scope, observed_at=at)
                if not sources.is_success:
                    return Outcome(failure=sources.failure)
            return Outcome.success(values)

    def adopted_for_relationship(
        self,
        *,
        actor: ResolvedIdentity,
        scope: ScopeRef,
        kind: RelationshipMemoryKind | None = None,
        limit: int = 50,
        after_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> Outcome[tuple[RelationshipMemory, ...]]:
        """Return only currently supported adopted material for a consumer.

        This is an authorized data projection, not a prompt formatter. Callers
        must preserve the role/persona and human audience boundary when using it.
        """
        return self.for_relationship(
            actor=actor,
            scope=scope,
            state=RelationshipMemoryState.ADOPTED,
            kind=kind,
            limit=limit,
            after_id=after_id,
            observed_at=observed_at,
        )

    def revisions(self, memory_id: str, *, actor: ResolvedIdentity, scope: ScopeRef,
                  observed_at: datetime | None = None) -> Outcome[tuple[RelationshipMemory, ...]]:
        if not self._valid_memory_id(memory_id):
            return Outcome.failed("relationship_memory_invalid", "memory ID must be an explicit opaque identifier")
        at = self._time(observed_at)
        with self.runtime.read_snapshot():
            authorization = self._authorize(actor, scope=scope,
                action="relationship.memory.read", observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            try:
                values = self._ledger.revisions(memory_id, owner=authorization.unwrap(), subject=actor.subject)
            except KeyError:
                return self._not_found()
            for memory in values:
                attributed = self._check_attribution(memory)
                if not attributed.is_success:
                    return Outcome(failure=attributed.failure)
                sources = self.validate_material(memory, actor=actor, scope=scope, observed_at=at)
                if not sources.is_success:
                    return Outcome(failure=sources.failure)
            return Outcome.success(values)

    def revise(
        self,
        memory_id: str,
        *,
        actor: ResolvedIdentity,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        interpretation: str,
        sources: tuple[SourceRef, ...],
        observed_at: datetime | None = None,
    ) -> Outcome[RelationshipMemory]:
        if not self._valid_memory_id(memory_id):
            return Outcome.failed("relationship_memory_invalid", "memory ID must be an explicit opaque identifier")
        at = self._time(observed_at)
        with self.runtime.transaction():
            authorization = self._authorize(actor, scope=scope,
                action="relationship.memory.revise", observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            try:
                current = self._ledger.memory(memory_id, owner=authorization.unwrap(), subject=actor.subject)
            except KeyError:
                return self._not_found()
            checked = self._validate_sources(sources, recipient=actor.subject, observed_at=at)
            if not checked.is_success:
                return Outcome(failure=checked.failure)
            try:
                updated = self._ledger.revise(
                    memory_id,
                    owner=current.owner,
                    subject=current.subject,
                    scope=scope,
                    expected_revision=expected_revision,
                    operation_id=operation_id,
                    interpretation=interpretation,
                    sources=sources,
                    observed_at=at,
                    actor=actor.subject,
                )
            except (ReferenceValidationError, TaskError) as error:
                code = error.code if isinstance(error, TaskError) else "relationship_memory_conflict"
                return Outcome.failed(code, str(error))
            return Outcome.success(updated)

    def transition(
        self,
        memory_id: str,
        *,
        actor: ResolvedIdentity,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        state: RelationshipMemoryState,
        observed_at: datetime | None = None,
    ) -> Outcome[RelationshipMemory]:
        if not self._valid_memory_id(memory_id):
            return Outcome.failed("relationship_memory_invalid", "memory ID must be an explicit opaque identifier")
        action = self._STATE_ACTIONS.get(state) if isinstance(state, RelationshipMemoryState) else None
        if action is None:
            return Outcome.failed("relationship_transition_invalid", "requested relationship state is not a review action")
        at = self._time(observed_at)
        with self.runtime.transaction():
            authorization = self._authorize(actor, scope=scope, action=action, observed_at=at)
            if not authorization.is_success:
                return Outcome(failure=authorization.failure)
            try:
                current = self._ledger.memory(memory_id, owner=authorization.unwrap(), subject=actor.subject)
            except KeyError:
                return self._not_found()
            if state in (RelationshipMemoryState.REVIEWED, RelationshipMemoryState.ADOPTED):
                sources = self.validate_material(current, actor=actor, scope=scope, observed_at=at)
                if not sources.is_success:
                    return Outcome(failure=sources.failure)
            if state is RelationshipMemoryState.ADOPTED:
                attributed = self._check_attribution(current)
                if not attributed.is_success:
                    return Outcome(failure=attributed.failure)
            try:
                updated = self._ledger.transition(
                    memory_id,
                    owner=current.owner,
                    subject=current.subject,
                    scope=scope,
                    expected_revision=expected_revision,
                    operation_id=operation_id,
                    state=state,
                    actor=actor.subject,
                    observed_at=at,
                )
            except (ReferenceValidationError, TaskError) as error:
                code = error.code if isinstance(error, TaskError) else "relationship_memory_conflict"
                return Outcome.failed(code, str(error))
            return Outcome.success(updated)
