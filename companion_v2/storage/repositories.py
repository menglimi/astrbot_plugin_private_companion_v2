"""Transactional namespace, operation, queue, and checkpoint repositories."""

from __future__ import annotations

from datetime import datetime
import hashlib
import sqlite3

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import OperationRef, ReferenceValidationError, ScopeRef, VersionRef

from .codec import decode_timestamp, encode_timestamp, scope_from_row, scope_values
from .models import (
    CommitState,
    InboxReceipt,
    MigrationCheckpoint,
    OperationReceipt,
    OperationState,
    OutboxRecord,
    StorageNamespace,
)
from .runtime import StorageRuntime


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


class NamespaceRepository:
    def __init__(self, runtime: StorageRuntime) -> None:
        self._runtime = runtime

    def ensure(
        self,
        *,
        owner: str,
        scope: ScopeRef,
        created_at: datetime,
    ) -> StorageNamespace:
        _opaque(owner, field="owner")
        _ensure_runtime_scope(self._runtime, scope)
        values = scope_values(scope)
        existing = self._runtime.read_one(
            """
            SELECT * FROM namespaces
            WHERE owner = ? AND installation_id = ? AND platform = ?
              AND scope_kind = ? AND native_scope_id = ? AND bot_id = ? AND account_id = ? AND conversation_id = ? AND session_id = ?
            """,
            (owner, *values),
        )
        if existing is not None:
            return _namespace_from_row(existing)

        namespace_id = _namespace_id(owner, scope)
        with self._runtime.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO namespaces(
                    namespace_id, owner, installation_id, platform, scope_kind,
                    native_scope_id, bot_id, account_id, conversation_id, session_id, revision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    owner,
                    *values,
                    1,
                    encode_timestamp(created_at),
                ),
            )
            row = connection.execute(
                "SELECT * FROM namespaces WHERE namespace_id = ?",
                (namespace_id,),
            ).fetchone()
        assert row is not None
        return _namespace_from_row(row)


class OperationRepository:
    """Local operation receipts and outbox rows with stable idempotency semantics."""

    def __init__(self, runtime: StorageRuntime) -> None:
        self._runtime = runtime

    def reserve(
        self,
        operation: OperationRef,
        *,
        parameter_hash: str,
        observed_at: datetime,
        outbox_part_id: str | None = None,
        outbox_payload_hash: str | None = None,
    ) -> Outcome[OperationReceipt]:
        _ensure_runtime_scope(self._runtime, operation.scope)
        _opaque(parameter_hash, field="parameter_hash")
        if (outbox_part_id is None) != (outbox_payload_hash is None):
            raise ReferenceValidationError("outbox part and payload hash must be supplied together")
        if outbox_part_id is not None:
            _opaque(outbox_part_id, field="outbox_part_id")
            _opaque(outbox_payload_hash or "", field="outbox_payload_hash")

        with self._runtime.transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM operations
                WHERE owner = ? AND installation_id = ? AND platform = ?
                  AND scope_kind = ? AND native_scope_id = ? AND bot_id = ? AND account_id = ? AND conversation_id = ? AND session_id = ? AND idempotency_key = ?
                """,
                (operation.owner, *scope_values(operation.scope), operation.idempotency_key),
            ).fetchone()
            if existing is not None:
                receipt = _operation_from_row(existing, replayed=True)
                if receipt.parameter_hash != parameter_hash:
                    return Outcome.failed(
                        "idempotency_key_conflict",
                        "existing operation uses the same key with different parameters",
                    )
                if outbox_part_id is not None:
                    conflict = _validate_existing_outbox(
                        connection,
                        operation_id=receipt.operation.operation_id,
                        part_id=outbox_part_id,
                        payload_hash=outbox_payload_hash or "",
                    )
                    if conflict is not None:
                        return conflict
                return Outcome.success(receipt)

            operation_id_row = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation.operation_id,),
            ).fetchone()
            if operation_id_row is not None:
                return Outcome.failed(
                    "operation_id_conflict",
                    "operation_id is already bound to another operation identity",
                )
            timestamp = encode_timestamp(observed_at)
            connection.execute(
                """
                INSERT INTO operations(
                    operation_id, owner, installation_id, platform, scope_kind,
                    native_scope_id, bot_id, account_id, conversation_id, session_id, lineage_id, operation_revision, idempotency_key,
                    parameter_hash, state, commit_state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation.operation_id,
                    operation.owner,
                    *scope_values(operation.scope),
                    operation.version.lineage_id,
                    operation.version.revision,
                    operation.idempotency_key,
                    parameter_hash,
                    OperationState.ACCEPTED.value,
                    CommitState.COMMITTED.value,
                    timestamp,
                    timestamp,
                ),
            )
            if outbox_part_id is not None:
                connection.execute(
                    """
                    INSERT INTO outbox(
                        outbox_id, operation_id, part_id, payload_hash, state, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _outbox_id(operation.operation_id, outbox_part_id),
                        operation.operation_id,
                        outbox_part_id,
                        outbox_payload_hash,
                        "pending",
                        timestamp,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation.operation_id,),
            ).fetchone()
        assert row is not None
        return Outcome.success(_operation_from_row(row, replayed=False))

    def get(self, operation_id: str) -> Outcome[OperationReceipt]:
        _opaque(operation_id, field="operation_id")
        row = self._runtime.read_one(
            "SELECT * FROM operations WHERE operation_id = ?",
            (operation_id,),
        )
        if row is None:
            return Outcome.failed("operation_not_found", "operation receipt does not exist")
        return Outcome.success(_operation_from_row(row, replayed=True))

    def transition(
        self,
        operation_id: str,
        *,
        expected_state: OperationState,
        next_state: OperationState,
        observed_at: datetime,
    ) -> Outcome[OperationReceipt]:
        _opaque(operation_id, field="operation_id")
        timestamp = encode_timestamp(observed_at)
        with self._runtime.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                return Outcome.failed("operation_not_found", "operation receipt does not exist")
            if row["state"] != expected_state.value:
                return Outcome.failed(
                    "operation_state_conflict",
                    "operation is no longer in the expected state",
                )
            connection.execute(
                "UPDATE operations SET state = ?, updated_at = ? WHERE operation_id = ?",
                (next_state.value, timestamp, operation_id),
            )
            updated = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        assert updated is not None
        return Outcome.success(_operation_from_row(updated, replayed=False))

    def outbox(self, operation_id: str, part_id: str) -> Outcome[OutboxRecord]:
        _opaque(operation_id, field="operation_id")
        _opaque(part_id, field="part_id")
        row = self._runtime.read_one(
            """SELECT outbox.*, operations.owner, operations.installation_id, operations.platform,
                      operations.scope_kind, operations.native_scope_id, operations.bot_id, operations.account_id,
                      operations.conversation_id, operations.session_id, operations.lineage_id,
                      operations.operation_revision, operations.idempotency_key
               FROM outbox JOIN operations ON outbox.operation_id = operations.operation_id
               WHERE outbox.operation_id = ? AND outbox.part_id = ?""",
            (operation_id, part_id),
        )
        if row is None:
            return Outcome.failed("outbox_not_found", "operation has no matching outbox part")
        return Outcome.success(_outbox_from_row(row))

    def transition_outbox(
        self,
        operation_id: str,
        part_id: str,
        *,
        expected_operation_state: OperationState,
        next_operation_state: OperationState,
        expected_outbox_state: str,
        next_outbox_state: str,
        observed_at: datetime,
        receipt_ref: str | None = None,
    ) -> Outcome[OperationReceipt]:
        """Advance a send operation and its outbox row in one transaction."""
        _opaque(operation_id, field="operation_id")
        _opaque(part_id, field="part_id")
        allowed = {
            (OperationState.ACCEPTED, "pending"): {(OperationState.UNKNOWN, "unknown"),
                                                       (OperationState.COMPLETED, "cancelled")},
            (OperationState.UNKNOWN, "unknown"): {(OperationState.COMPLETED, "accepted"),
                                                      (OperationState.COMPLETED, "cancelled"),
                                                      (OperationState.UNKNOWN, "unknown")},
        }
        if (next_operation_state, next_outbox_state) not in allowed.get(
                (expected_operation_state, expected_outbox_state), set()):
            return Outcome.failed("outbox_transition_invalid", "operation and outbox transition is not supported")
        if next_outbox_state == "accepted":
            if (not isinstance(receipt_ref, str) or not receipt_ref or receipt_ref != receipt_ref.strip()
                    or len(receipt_ref) > 512):
                return Outcome.failed("outbox_receipt_invalid", "accepted outbox state requires a bounded receipt")
        elif receipt_ref is not None:
            return Outcome.failed("outbox_receipt_invalid", "only accepted outbox state can store a receipt")
        timestamp = encode_timestamp(observed_at)
        with self._runtime.transaction() as connection:
            operation = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            outbox = connection.execute(
                "SELECT * FROM outbox WHERE operation_id = ? AND part_id = ?", (operation_id, part_id)
            ).fetchone()
            if operation is None or outbox is None:
                return Outcome.failed("outbox_not_found", "operation has no matching outbox part")
            if (operation["state"], outbox["state"]) != (expected_operation_state.value, expected_outbox_state):
                return Outcome.failed("outbox_state_conflict", "operation or outbox has already changed")
            connection.execute(
                "UPDATE operations SET state = ?, updated_at = ? WHERE operation_id = ?",
                (next_operation_state.value, timestamp, operation_id),
            )
            connection.execute(
                "UPDATE outbox SET state = ?, receipt_ref = ? WHERE operation_id = ? AND part_id = ?",
                (next_outbox_state, receipt_ref, operation_id, part_id),
            )
            updated = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
        assert updated is not None
        return Outcome.success(_operation_from_row(updated, replayed=False))

    def pending_outbox(self) -> tuple[OutboxRecord, ...]:
        rows = self._runtime.read_all(
            """
            SELECT outbox.*, operations.owner, operations.installation_id, operations.platform,
                   operations.scope_kind, operations.native_scope_id, operations.bot_id, operations.account_id,
                   operations.conversation_id, operations.session_id, operations.lineage_id,
                   operations.operation_revision, operations.idempotency_key
            FROM outbox JOIN operations ON outbox.operation_id = operations.operation_id
            WHERE outbox.state = 'pending' ORDER BY outbox.created_at, outbox.outbox_id
            """,
            (),
        )
        return tuple(_outbox_from_row(row) for row in rows)


class InboxRepository:
    def __init__(self, runtime: StorageRuntime) -> None:
        self._runtime = runtime

    def accept(
        self,
        *,
        consumer: str,
        event_id: str,
        payload_hash: str,
        observed_at: datetime,
    ) -> Outcome[InboxReceipt]:
        _opaque(consumer, field="consumer")
        _opaque(event_id, field="event_id")
        _opaque(payload_hash, field="payload_hash")
        with self._runtime.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM inbox WHERE consumer = ? AND event_id = ?",
                (consumer, event_id),
            ).fetchone()
            if row is not None:
                if row["payload_hash"] != payload_hash:
                    return Outcome.failed(
                        "inbox_event_conflict",
                        "event identity was previously accepted with different content",
                    )
                return Outcome.success(
                    InboxReceipt(
                        consumer=consumer,
                        event_id=event_id,
                        payload_hash=payload_hash,
                        commit_state=CommitState.COMMITTED,
                        replayed=True,
                    )
                )
            connection.execute(
                """
                INSERT INTO inbox(consumer, event_id, payload_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (consumer, event_id, payload_hash, encode_timestamp(observed_at)),
            )
        return Outcome.success(
            InboxReceipt(
                consumer=consumer,
                event_id=event_id,
                payload_hash=payload_hash,
                commit_state=CommitState.COMMITTED,
                replayed=False,
            )
        )


class MigrationLedger:
    def __init__(self, runtime: StorageRuntime) -> None:
        self._runtime = runtime

    def advance(
        self,
        *,
        checkpoint_id: str,
        owner: str,
        source_fingerprint: str,
        cursor: str,
        state: str,
        expected_revision: int,
        observed_at: datetime,
    ) -> Outcome[MigrationCheckpoint]:
        _opaque(checkpoint_id, field="checkpoint_id")
        _opaque(owner, field="owner")
        _opaque(source_fingerprint, field="source_fingerprint")
        _opaque(cursor, field="cursor")
        _opaque(state, field="state")
        if expected_revision < 0:
            raise ReferenceValidationError("expected_revision cannot be negative")
        with self._runtime.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM migration_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
            if row is None:
                if expected_revision != 0:
                    return Outcome.failed(
                        "checkpoint_revision_conflict",
                        "checkpoint does not exist at the expected revision",
                    )
                revision = 1
                connection.execute(
                    """
                    INSERT INTO migration_checkpoints(
                        checkpoint_id, owner, source_fingerprint, cursor, revision, state, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id,
                        owner,
                        source_fingerprint,
                        cursor,
                        revision,
                        state,
                        encode_timestamp(observed_at),
                    ),
                )
            else:
                if row["owner"] != owner or row["source_fingerprint"] != source_fingerprint:
                    return Outcome.failed(
                        "checkpoint_identity_conflict",
                        "checkpoint is bound to a different owner or source fingerprint",
                    )
                if int(row["revision"]) != expected_revision:
                    return Outcome.failed(
                        "checkpoint_revision_conflict",
                        "checkpoint revision no longer matches",
                    )
                revision = expected_revision + 1
                connection.execute(
                    """
                    UPDATE migration_checkpoints
                    SET cursor = ?, revision = ?, state = ?, updated_at = ?
                    WHERE checkpoint_id = ? AND revision = ?
                    """,
                    (
                        cursor,
                        revision,
                        state,
                        encode_timestamp(observed_at),
                        checkpoint_id,
                        expected_revision,
                    ),
                )
            updated = connection.execute(
                "SELECT * FROM migration_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        assert updated is not None
        return Outcome.success(_checkpoint_from_row(updated))


def _ensure_runtime_scope(runtime: StorageRuntime, scope: ScopeRef) -> None:
    if scope.installation_id != runtime.installation_id:
        raise ReferenceValidationError("reference scope belongs to another installation")


def _namespace_id(owner: str, scope: ScopeRef) -> str:
    token = "\x1f".join((owner, *scope_values(scope))).encode("utf-8")
    return f"namespace-{hashlib.sha256(token).hexdigest()[:24]}"


def _outbox_id(operation_id: str, part_id: str) -> str:
    token = f"{operation_id}\x1f{part_id}".encode("utf-8")
    return f"outbox-{hashlib.sha256(token).hexdigest()[:24]}"


def _namespace_from_row(row: sqlite3.Row) -> StorageNamespace:
    return StorageNamespace(
        namespace_id=row["namespace_id"],
        owner=row["owner"],
        scope=scope_from_row(row),
        revision=int(row["revision"]),
        created_at=decode_timestamp(row["created_at"]),
    )


def _operation_from_row(row: sqlite3.Row, *, replayed: bool) -> OperationReceipt:
    operation = OperationRef(
        operation_id=row["operation_id"],
        owner=row["owner"],
        scope=scope_from_row(row),
        version=VersionRef(
            lineage_id=row["lineage_id"],
            revision=int(row["operation_revision"]),
        ),
        idempotency_key=row["idempotency_key"],
    )
    return OperationReceipt(
        operation=operation,
        parameter_hash=row["parameter_hash"],
        state=OperationState(row["state"]),
        commit_state=CommitState(row["commit_state"]),
        created_at=decode_timestamp(row["created_at"]),
        updated_at=decode_timestamp(row["updated_at"]),
        replayed=replayed,
    )


def _validate_existing_outbox(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    part_id: str,
    payload_hash: str,
) -> Outcome[OperationReceipt] | None:
    row = connection.execute(
        "SELECT payload_hash FROM outbox WHERE operation_id = ? AND part_id = ?",
        (operation_id, part_id),
    ).fetchone()
    if row is None:
        return Outcome.failed(
            "outbox_missing_for_replayed_operation",
            "replayed operation does not have the requested outbox part",
        )
    if row["payload_hash"] != payload_hash:
        return Outcome.failed(
            "outbox_part_conflict",
            "replayed operation outbox part uses a different payload",
        )
    return None


def _outbox_from_row(row: sqlite3.Row) -> OutboxRecord:
    operation = OperationRef(
        operation_id=row["operation_id"],
        owner=row["owner"],
        scope=scope_from_row(row),
        version=VersionRef(
            lineage_id=row["lineage_id"],
            revision=int(row["operation_revision"]),
        ),
        idempotency_key=row["idempotency_key"],
    )
    return OutboxRecord(
        outbox_id=row["outbox_id"],
        operation=operation,
        part_id=row["part_id"],
        payload_hash=row["payload_hash"],
        state=row["state"],
        created_at=decode_timestamp(row["created_at"]),
        receipt_ref=row["receipt_ref"],
    )


def _checkpoint_from_row(row: sqlite3.Row) -> MigrationCheckpoint:
    return MigrationCheckpoint(
        checkpoint_id=row["checkpoint_id"],
        owner=row["owner"],
        source_fingerprint=row["source_fingerprint"],
        cursor=row["cursor"],
        revision=int(row["revision"]),
        state=row["state"],
        updated_at=decode_timestamp(row["updated_at"]),
    )
