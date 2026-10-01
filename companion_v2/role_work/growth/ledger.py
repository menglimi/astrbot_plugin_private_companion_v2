"""Persistent role-owned growth records with explicit revisions and receipts."""

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
    SubjectRef,
    VersionRef,
)
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.runtime import StorageRuntime

from .codec import record_from_json, record_json
from .models import (
    GrowthKind,
    GrowthState,
    RoleGrowthRecord,
    apply_growth_progress,
    confirm_growth,
    revise_growth,
    transition_growth,
)


class PersistentRoleGrowthLedger:
    """Trusted storage primitive; inventory does not grant audience permission.

    Consumers must resolve the current human/role route and recheck every source
    before projecting a record into a prompt, tool result, or management view.
    """

    OPERATION_OWNER = "role.growth"

    def __init__(self, runtime: StorageRuntime, *, now=None) -> None:
        self.runtime = runtime
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.operations = OperationRepository(runtime)

    def _owner_key(self, owner: RoleOwnerRef) -> str:
        if not isinstance(owner, RoleOwnerRef) or owner.installation_id != self.runtime.installation_id:
            raise ReferenceValidationError("growth owner belongs to another installation")
        return digest(owner)

    @staticmethod
    def _scope(owner: RoleOwnerRef, scope: ScopeRef) -> None:
        if (not isinstance(scope, ScopeRef) or not scope.is_resolved
                or scope.kind is not ScopeKind.PRIVATE
                or scope.installation_id != owner.installation_id or scope.bot_id != owner.bot_id):
            raise ReferenceValidationError("growth operation needs this role's resolved private scope")

    @staticmethod
    def _page(limit: int, after_id: str | None) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReferenceValidationError("growth page size must be between 1 and 100")
        if after_id is not None and (
            not isinstance(after_id, str) or not after_id or after_id != after_id.strip() or len(after_id) > 512
        ):
            raise ReferenceValidationError("growth cursor must be an original record ID")

    def add(self, record: RoleGrowthRecord) -> RoleGrowthRecord:
        key = self._owner_key(record.owner)
        self._scope(record.owner, record.scope)
        if (record.revision != 1 or record.state is not GrowthState.PROPOSED
                or record.confirmed_by is not None or record.proposed_by is None):
            raise ReferenceValidationError("new growth starts as an attributed proposal")
        encoded = record_json(record)
        with self.runtime.transaction() as connection:
            row = connection.execute(
                "SELECT record_json FROM role_growth_items WHERE owner_key = ? AND growth_id = ?",
                (key, record.growth_id),
            ).fetchone()
            if row is not None:
                existing = record_from_json(row["record_json"])
                if existing != record:
                    raise ReferenceValidationError("growth ID is already bound to another record")
                return existing
            connection.execute(
                """INSERT INTO role_growth_items(
                    owner_key, growth_id, revision, kind, state, updated_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (key, record.growth_id, record.revision, record.kind.value, record.state.value,
                 stamp(record.updated_at), encoded),
            )
            connection.execute(
                "INSERT INTO role_growth_revisions VALUES (?, ?, ?, ?)",
                (key, record.growth_id, record.revision, encoded),
            )
        return record

    def record(self, growth_id: str, *, owner: RoleOwnerRef) -> RoleGrowthRecord:
        key = self._owner_key(owner)
        row = self.runtime.read_one(
            "SELECT record_json FROM role_growth_items WHERE owner_key = ? AND growth_id = ?",
            (key, growth_id),
        )
        if row is None:
            raise KeyError(growth_id)
        record = record_from_json(row["record_json"])
        if record.owner != owner or record.growth_id != growth_id:
            raise ReferenceValidationError("stored growth identity does not match its owner index")
        return record

    def revision(self, growth_id: str, revision: int, *, owner: RoleOwnerRef) -> RoleGrowthRecord:
        """Retrieve an exact historical revision without granting read authority."""
        key = self._owner_key(owner)
        if type(revision) is not int or revision < 1:
            raise ReferenceValidationError("growth revision must be positive")
        row = self.runtime.read_one(
            "SELECT record_json FROM role_growth_revisions WHERE owner_key = ? AND growth_id = ? AND revision = ?",
            (key, growth_id, revision),
        )
        if row is None:
            raise KeyError((growth_id, revision))
        record = record_from_json(row["record_json"])
        if (record.owner, record.growth_id, record.revision) != (owner, growth_id, revision):
            raise ReferenceValidationError("growth revision identity does not match its index")
        return record

    def propose(self, record: RoleGrowthRecord, *, operation_id: str) -> RoleGrowthRecord:
        """Create with a durable receipt; retries retain the first proposal's time."""
        key = self._owner_key(record.owner)
        self._scope(record.owner, record.scope)
        if record.revision != 1 or record.state is not GrowthState.PROPOSED or record.confirmed_by is not None:
            raise ReferenceValidationError("new growth starts as an attributed proposal")
        operation = OperationRef(operation_id, self.OPERATION_OWNER, record.scope,
                                 VersionRef(operation_id, 1), operation_id)
        parameters = ("propose", key, record.growth_id, record.scope, record.kind, record.title,
                      record.description, record.progress_note, record.sources,
                      record.proposed_by, record.changed_by)
        with self.runtime.transaction() as connection:
            receipt = require(self.operations.reserve(operation, parameter_hash=digest(parameters),
                                                       observed_at=record.updated_at))
            if receipt.replayed:
                row = connection.execute(
                    "SELECT result_json FROM role_growth_operations WHERE operation_id = ? AND owner_key = ?",
                    (operation_id, key),
                ).fetchone()
                if row is None or receipt.state is not OperationState.COMPLETED:
                    raise ReferenceValidationError("original growth proposal is incomplete")
                return record_from_json(row["result_json"])
            saved = self.add(record)
            connection.execute("INSERT INTO role_growth_operations VALUES (?, ?, ?, ?)",
                               (operation_id, key, record.growth_id, record_json(saved)))
            require(self.operations.transition(operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=record.updated_at))
            return saved

    def revisions(self, growth_id: str, *, owner: RoleOwnerRef) -> tuple[RoleGrowthRecord, ...]:
        key = self._owner_key(owner)
        rows = self.runtime.read_all(
            """SELECT record_json FROM role_growth_revisions
               WHERE owner_key = ? AND growth_id = ? ORDER BY revision""",
            (key, growth_id),
        )
        if not rows:
            raise KeyError(growth_id)
        values = tuple(record_from_json(row["record_json"]) for row in rows)
        if any(item.owner != owner or item.growth_id != growth_id for item in values):
            raise ReferenceValidationError("growth revision history crosses its owner")
        return values

    def for_role(
        self,
        owner: RoleOwnerRef,
        *,
        kind: GrowthKind | None = None,
        state: GrowthState | None = None,
        scope: ScopeRef | None = None,
        limit: int = 50,
        after_id: str | None = None,
    ) -> tuple[RoleGrowthRecord, ...]:
        key = self._owner_key(owner)
        self._page(limit, after_id)
        if kind is not None and not isinstance(kind, GrowthKind):
            raise ReferenceValidationError("growth kind filter must be explicit")
        if state is not None and not isinstance(state, GrowthState):
            raise ReferenceValidationError("growth state filter must be explicit")
        if scope is not None:
            self._scope(owner, scope)
        rows = self.runtime.read_all(
            """SELECT record_json FROM role_growth_items
               WHERE owner_key = ? AND (? IS NULL OR kind = ?) AND (? IS NULL OR state = ?)
                 AND (? IS NULL OR growth_id > ?) AND (? IS NULL OR json_extract(record_json, '$.scope') = json(?))
               ORDER BY growth_id LIMIT ?""",
            (key, kind.value if kind else None, kind.value if kind else None,
             state.value if state else None, state.value if state else None,
             after_id, after_id, encode(scope) if scope else None, encode(scope) if scope else None, limit),
        )
        values = tuple(record_from_json(row["record_json"]) for row in rows)
        if any(item.owner != owner for item in values):
            raise ReferenceValidationError("stored growth inventory crosses its owner")
        return values

    def revise(
        self,
        growth_id: str,
        *,
        owner: RoleOwnerRef,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        title: str,
        description: str,
        progress_note: str,
        sources: tuple[SourceRef, ...],
        actor: SubjectRef,
        observed_at: datetime | None = None,
    ) -> RoleGrowthRecord:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        return self._change(
            growth_id, owner=owner, scope=scope, operation_id=operation_id,
            parameters=("revise", expected_revision, title, description, progress_note, tuple(sources), actor),
            observed_at=at,
            transform=lambda current: revise_growth(
                current, expected_revision=expected_revision, title=title, description=description,
                progress_note=progress_note, sources=tuple(sources), observed_at=at,
                scope=scope, actor=actor,
            ),
        )

    def transition(
        self,
        growth_id: str,
        *,
        owner: RoleOwnerRef,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        state: GrowthState,
        actor: SubjectRef,
        observed_at: datetime | None = None,
    ) -> RoleGrowthRecord:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        return self._change(
            growth_id, owner=owner, scope=scope, operation_id=operation_id,
            parameters=("transition", expected_revision, state, actor), observed_at=at,
            transform=lambda current: transition_growth(
                current, state=state, expected_revision=expected_revision,
                observed_at=at, scope=scope, actor=actor,
            ),
        )

    def apply_progress(
        self, growth_id: str, *, owner: RoleOwnerRef, scope: ScopeRef,
        expected_revision: int, operation_id: str, progress_note: str,
        sources: tuple[SourceRef, ...], actor: SubjectRef,
        observed_at: datetime | None = None,
    ) -> RoleGrowthRecord:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        return self._change(
            growth_id, owner=owner, scope=scope, operation_id=operation_id,
            parameters=("progress", expected_revision, progress_note, tuple(sources), actor),
            observed_at=at,
            transform=lambda current: apply_growth_progress(
                current, expected_revision=expected_revision, progress_note=progress_note,
                sources=tuple(sources), observed_at=at, scope=scope, actor=actor,
            ),
        )

    def confirm(
        self,
        growth_id: str,
        *,
        owner: RoleOwnerRef,
        scope: ScopeRef,
        expected_revision: int,
        operation_id: str,
        actor: SubjectRef,
        observed_at: datetime | None = None,
    ) -> RoleGrowthRecord:
        at = self.now() if observed_at is None else observed_at
        self._scope(owner, scope)
        return self._change(
            growth_id, owner=owner, scope=scope, operation_id=operation_id,
            parameters=("confirm", expected_revision, actor), observed_at=at,
            transform=lambda current: confirm_growth(
                current, expected_revision=expected_revision,
                observed_at=at, scope=scope, actor=actor,
            ),
        )

    def _change(self, growth_id, *, owner, scope, operation_id, parameters, observed_at, transform):
        key = self._owner_key(owner)
        operation = OperationRef(operation_id, self.OPERATION_OWNER, scope,
                                 VersionRef(operation_id, 1), operation_id)
        with self.runtime.transaction() as connection:
            receipt = require(self.operations.reserve(
                operation, parameter_hash=digest((key, growth_id, parameters)), observed_at=observed_at,
            ))
            if receipt.replayed:
                saved = connection.execute(
                    "SELECT result_json FROM role_growth_operations WHERE operation_id = ? AND owner_key = ?",
                    (operation_id, key),
                ).fetchone()
                if saved is None or receipt.state is not OperationState.COMPLETED:
                    raise ReferenceValidationError("original growth operation is incomplete")
                return record_from_json(saved["result_json"])
            row = connection.execute(
                "SELECT record_json FROM role_growth_items WHERE owner_key = ? AND growth_id = ?",
                (key, growth_id),
            ).fetchone()
            if row is None:
                raise KeyError(growth_id)
            current = record_from_json(row["record_json"])
            if current.owner != owner or current.growth_id != growth_id:
                raise ReferenceValidationError("stored growth identity does not match its index")
            updated = transform(current)
            encoded = record_json(updated)
            changed = connection.execute(
                """UPDATE role_growth_items SET revision = ?, kind = ?, state = ?, updated_at = ?, record_json = ?
                   WHERE owner_key = ? AND growth_id = ? AND revision = ?""",
                (updated.revision, updated.kind.value, updated.state.value, stamp(updated.updated_at),
                 encoded, key, growth_id, current.revision),
            )
            if changed.rowcount != 1:
                raise ReferenceValidationError("growth revision conflict")
            connection.execute(
                "INSERT INTO role_growth_revisions VALUES (?, ?, ?, ?)",
                (key, growth_id, updated.revision, encoded),
            )
            connection.execute(
                "INSERT INTO role_growth_operations VALUES (?, ?, ?, ?)",
                (operation_id, key, growth_id, encoded),
            )
            require(self.operations.transition(
                operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=observed_at,
            ))
            return updated
