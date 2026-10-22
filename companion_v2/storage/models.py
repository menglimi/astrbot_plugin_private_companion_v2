"""Small persistence result objects shared by the initial V2 repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from companion_v2.foundation.refs import OperationRef, ScopeRef


class CommitState(str, Enum):
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"


class OperationState(str, Enum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StorageNamespace:
    namespace_id: str
    owner: str
    scope: ScopeRef
    revision: int
    created_at: datetime


@dataclass(frozen=True)
class OperationReceipt:
    operation: OperationRef
    parameter_hash: str
    state: OperationState
    commit_state: CommitState
    created_at: datetime
    updated_at: datetime
    replayed: bool


@dataclass(frozen=True)
class OutboxRecord:
    outbox_id: str
    operation: OperationRef
    part_id: str
    payload_hash: str
    state: str
    created_at: datetime
    receipt_ref: str | None = None


@dataclass(frozen=True)
class InboxReceipt:
    consumer: str
    event_id: str
    payload_hash: str
    commit_state: CommitState
    replayed: bool


@dataclass(frozen=True)
class MigrationCheckpoint:
    checkpoint_id: str
    owner: str
    source_fingerprint: str
    cursor: str
    revision: int
    state: str
    updated_at: datetime
