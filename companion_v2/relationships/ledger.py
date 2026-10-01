"""Persistent, versioned records for one stable role/person relationship."""

from __future__ import annotations

from datetime import datetime, timezone

from companion_v2.execution.models import digest, encode, require, stamp
from companion_v2.foundation.refs import (
    OperationRef,
    ReferenceValidationError,
    RoleOwnerRef,
    ScopeKind,
    ScopeRef,
    SourceRef,
    SubjectKind,
    SubjectRef,
    VersionRef,
)
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.runtime import StorageRuntime

from .codec import memory_from_json, memory_json
from .models import (
    RelationshipMemory,
    RelationshipMemoryKind,
    RelationshipMemoryState,
    revise_memory,
    transition_memory,
)


class PersistentRelationshipMemoryLedger:
    """Store role-authored context without granting a prompt or audience projection.

    This is a trusted internal repository. Callers that expose records in a chat,
    management page or another domain must recheck the current human identity,
    role binding and every source's current audience/governance first.
    """

    OPERATION_OWNER = "relationship.memory"

    def __init__(self, runtime: StorageRuntime, *, now=None) -> None:
        self.runtime = runtime
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.operations = OperationRepository(runtime)

    def _owner_key(self, owner: RoleOwnerRef, subject: SubjectRef) -> str:
        if not isinstance(owner, RoleOwnerRef) or owner.installation_id != self.runtime.installation_id:
            raise ReferenceValidationError("relationship owner belongs to another installation")
        if not isinstance(subject, SubjectRef) or subject.kind is not SubjectKind.HUMAN:
            raise ReferenceValidationError("relationship requires a resolved human subject")
        if subject.installation_id != owner.installation_id:
            raise ReferenceValidationError("relationship subject belongs to another installation")
        return digest((owner, subject))

    def _scope(self, owner: RoleOwnerRef, scope: ScopeRef) -> None:
        if (not isinstance(scope, ScopeRef) or not scope.is_resolved or scope.kind is not ScopeKind.PRIVATE
                or scope.installation_id != owner.installation_id or scope.bot_id != owner.bot_id):
            raise ReferenceValidationError("relationship operation needs this role's resolved private scope")

    @staticmethod
    def _page(limit: int, after_id: str | None) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReferenceValidationError("relationship page size must be between 1 and 100")
        if after_id is not None and (not isinstance(after_id, str) or not after_id or len(after_id) > 512):
            raise ReferenceValidationError("relationship cursor must be an original memory ID")

    def add(self, memory: RelationshipMemory) -> RelationshipMemory:
        key = self._owner_key(memory.owner, memory.subject)
        self._scope(memory.owner, memory.scope)
        if memory.revision != 1 or memory.state is not RelationshipMemoryState.PROPOSED:
            raise ReferenceValidationError("new relationship memory starts as a proposed first revision")
        encoded = memory_json(memory)
        with self.runtime.transaction() as connection:
            row = connection.execute(
                "SELECT record_json FROM relationship_memories WHERE owner_key = ? AND memory_id = ?",
                (key, memory.memory_id),
            ).fetchone()
            if row is not None:
                existing = memory_from_json(row["record_json"])
                if existing != memory:
                    raise ReferenceValidationError("relationship memory ID is already bound to another record")
                return existing
            connection.execute(
                """INSERT INTO relationship_memories(
                    owner_key, memory_id, owner_json, subject_json, revision, kind, state, updated_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, memory.memory_id, encode(memory.owner), encode(memory.subject), memory.revision,
                 memory.kind.value, memory.state.value, stamp(memory.updated_at), encoded),
            )
            connection.execute(
                "INSERT INTO relationship_memory_revisions VALUES (?, ?, ?, ?)",
                (key, memory.memory_id, memory.revision, encoded),
            )
        return memory

    def memory(self, memory_id: str, *, owner: RoleOwnerRef, subject: SubjectRef) -> RelationshipMemory:
        key = self._owner_key(owner, subject)
        row = self.runtime.read_one(
            "SELECT record_json FROM relationship_memories WHERE owner_key = ? AND memory_id = ?",
            (key, memory_id),
        )
        if row is None:
            raise KeyError(memory_id)
        memory = memory_from_json(row["record_json"])
        if memory.owner != owner or memory.subject != subject:
            raise ReferenceValidationError("stored relationship owner identity does not match its index")
        return memory

    def propose(self, memory: RelationshipMemory, *, operation_id: str) -> RelationshipMemory:
        """Commit a first revision and its immutable receipt in one transaction."""
        key = self._owner_key(memory.owner, memory.subject)
        self._scope(memory.owner, memory.scope)
        if memory.revision != 1 or memory.state is not RelationshipMemoryState.PROPOSED:
            raise ReferenceValidationError("new relationship memory starts as a proposed first revision")
        operation = OperationRef(operation_id, self.OPERATION_OWNER, memory.scope,
                                 VersionRef(operation_id, 1), operation_id)
        parameters = ("propose", key, memory.memory_id, memory.scope, memory.kind,
                      memory.interpretation, memory.sources, memory.emotion_subject)
        with self.runtime.transaction() as connection:
            receipt = require(self.operations.reserve(operation, parameter_hash=digest(parameters),
                                                       observed_at=memory.updated_at))
            if receipt.replayed:
                row = connection.execute(
                    "SELECT result_json FROM relationship_memory_operations WHERE operation_id = ? AND owner_key = ?",
                    (operation_id, key),
                ).fetchone()
                if row is None or receipt.state is not OperationState.COMPLETED:
                    raise ReferenceValidationError("original relationship proposal is incomplete")
                return memory_from_json(row["result_json"])
            saved = self.add(memory)
            connection.execute("INSERT INTO relationship_memory_operations VALUES (?, ?, ?, ?)",
                               (operation_id, key, memory.memory_id, memory_json(saved)))
            require(self.operations.transition(operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=memory.updated_at))
            return saved

    def revisions(self, memory_id: str, *, owner: RoleOwnerRef,
                  subject: SubjectRef) -> tuple[RelationshipMemory, ...]:
        key = self._owner_key(owner, subject)
        rows = self.runtime.read_all(
            """SELECT record_json FROM relationship_memory_revisions
               WHERE owner_key = ? AND memory_id = ? ORDER BY revision""",
            (key, memory_id),
        )
        if not rows:
            raise KeyError(memory_id)
        values = tuple(memory_from_json(row["record_json"]) for row in rows)
        if any(item.owner != owner or item.subject != subject for item in values):
            raise ReferenceValidationError("stored relationship history crosses its indexed identity")
        return values

    def for_relationship(
        self,
        owner: RoleOwnerRef,
        subject: SubjectRef,
        *,
        state: RelationshipMemoryState | None = None,
        kind: RelationshipMemoryKind | None = None,
        scope: ScopeRef | None = None,
        route: ScopeRef | None = None,
        limit: int = 50,
        after_id: str | None = None,
    ) -> tuple[RelationshipMemory, ...]:
        key = self._owner_key(owner, subject)
        self._page(limit, after_id)
        if state is not None and not isinstance(state, RelationshipMemoryState):
            raise ReferenceValidationError("relationship state filter must be explicit")
        if kind is not None and not isinstance(kind, RelationshipMemoryKind):
            raise ReferenceValidationError("relationship kind filter must be explicit")
        if scope is not None:
            self._scope(owner, scope)
        route_clause, route_values = "", ()
        if route is not None:
            self._scope(owner, route)
            from .provenance import ROUTE_FIELDS
            route_clause = " AND " + " AND ".join(
                "json_extract(record_json, '$.scope." + field + "') = ?" for field in ROUTE_FIELDS)
            route_values = tuple(route.kind.value if field == "kind" else getattr(route, field)
                                 for field in ROUTE_FIELDS)
        rows = self.runtime.read_all(
            """SELECT record_json FROM relationship_memories
               WHERE owner_key = ? AND (? IS NULL OR state = ?)
                 AND (? IS NULL OR kind = ?) AND (? IS NULL OR memory_id > ?)
                 AND (? IS NULL OR json_extract(record_json, '$.scope') = json(?))
               """ + route_clause + " ORDER BY memory_id LIMIT ?",
            (key, state.value if state else None, state.value if state else None,
             kind.value if kind else None, kind.value if kind else None,
             after_id, after_id, encode(scope) if scope else None, encode(scope) if scope else None,
             *route_values, limit),
        )
        values = tuple(memory_from_json(row["record_json"]) for row in rows)
        if any(item.owner != owner or item.subject != subject for item in values):
            raise ReferenceValidationError("stored relationship inventory crosses its indexed identity")
        return values

    def adopted_for_relationship(self, owner: RoleOwnerRef, subject: SubjectRef, *,
                                 limit: int = 50, after_id: str | None = None) -> tuple[RelationshipMemory, ...]:
        """Return only adopted records; this still is not an audience-authorized read."""
        return self.for_relationship(owner, subject, state=RelationshipMemoryState.ADOPTED,
                                     limit=limit, after_id=after_id)

    def revise(
        self,
        memory_id: str,
        *,
        owner: RoleOwnerRef,
        subject: SubjectRef,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        interpretation: str,
        sources: tuple[SourceRef, ...],
        observed_at: datetime | None = None,
        actor: SubjectRef | None = None,
    ) -> RelationshipMemory:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        sources = tuple(sources)
        return self._change(
            memory_id, owner=owner, subject=subject, scope=scope, operation_id=operation_id,
            parameters=("revise", expected_revision, interpretation, sources)
                + ((actor,) if actor is not None and actor != subject else ()), observed_at=at,
            transform=lambda current: revise_memory(current, expected_revision=expected_revision,
                interpretation=interpretation, sources=sources, observed_at=at, scope=scope, actor=actor),
        )

    def transition(
        self,
        memory_id: str,
        *,
        owner: RoleOwnerRef,
        subject: SubjectRef,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        state: RelationshipMemoryState,
        actor: SubjectRef,
        observed_at: datetime | None = None,
    ) -> RelationshipMemory:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        return self._change(
            memory_id, owner=owner, subject=subject, scope=scope, operation_id=operation_id,
            parameters=("transition", expected_revision, state, actor), observed_at=at,
            transform=lambda current: transition_memory(current, state=state,
                expected_revision=expected_revision, observed_at=at, scope=scope, actor=actor),
        )

    def _change(self, memory_id: str, *, owner: RoleOwnerRef, subject: SubjectRef,
                scope: ScopeRef, operation_id: str, parameters: tuple, observed_at: datetime,
                transform) -> RelationshipMemory:
        key = self._owner_key(owner, subject)
        operation = OperationRef(operation_id, self.OPERATION_OWNER, scope,
                                 VersionRef(operation_id, 1), operation_id)
        with self.runtime.transaction() as connection:
            receipt = require(self.operations.reserve(
                operation, parameter_hash=digest((key, memory_id, parameters)), observed_at=observed_at,
            ))
            if receipt.replayed:
                saved = connection.execute(
                    "SELECT result_json FROM relationship_memory_operations WHERE operation_id = ? AND owner_key = ?",
                    (operation_id, key),
                ).fetchone()
                if saved is None or receipt.state is not OperationState.COMPLETED:
                    raise ReferenceValidationError("original relationship memory operation is incomplete")
                return memory_from_json(saved["result_json"])

            row = connection.execute(
                "SELECT record_json FROM relationship_memories WHERE owner_key = ? AND memory_id = ?",
                (key, memory_id),
            ).fetchone()
            if row is None:
                raise KeyError(memory_id)
            current = memory_from_json(row["record_json"])
            if current.owner != owner or current.subject != subject:
                raise ReferenceValidationError("stored relationship owner identity does not match its index")
            updated = transform(current)
            encoded = memory_json(updated)
            changed = connection.execute(
                """UPDATE relationship_memories
                   SET revision = ?, kind = ?, state = ?, updated_at = ?, record_json = ?
                   WHERE owner_key = ? AND memory_id = ? AND revision = ?""",
                (updated.revision, updated.kind.value, updated.state.value, stamp(updated.updated_at),
                 encoded, key, memory_id, current.revision),
            )
            if changed.rowcount != 1:
                raise ReferenceValidationError("relationship memory revision conflict")
            connection.execute(
                "INSERT INTO relationship_memory_revisions VALUES (?, ?, ?, ?)",
                (key, memory_id, updated.revision, encoded),
            )
            connection.execute(
                "INSERT INTO relationship_memory_operations VALUES (?, ?, ?, ?)",
                (operation_id, key, memory_id, encoded),
            )
            require(self.operations.transition(operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=observed_at))
            return updated
