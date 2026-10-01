"""Encoding helpers for V2 SQLite rows; no repository receives raw path data."""

from __future__ import annotations

from datetime import datetime
import sqlite3

from companion_v2.foundation.refs import ScopeKind, ScopeRef, VersionRef, normalize_utc


def encode_timestamp(value: datetime) -> str:
    return normalize_utc(value, field="timestamp").isoformat()


def decode_timestamp(value: str) -> datetime:
    return normalize_utc(datetime.fromisoformat(value), field="stored_timestamp")


SCOPE_COLUMNS = ("installation_id", "platform", "scope_kind", "native_scope_id",
                 "bot_id", "account_id", "conversation_id", "session_id")


def scope_values(scope: ScopeRef) -> tuple[str, ...]:
    return (
        scope.installation_id,
        scope.platform,
        scope.kind.value,
        scope.native_scope_id,
        scope.bot_id or "",
        scope.account_id or "",
        scope.conversation_id or "",
        scope.session_id or "",
    )


def scope_from_row(row: sqlite3.Row) -> ScopeRef:
    return ScopeRef(
        installation_id=row["installation_id"],
        platform=row["platform"],
        kind=ScopeKind(row["scope_kind"]),
        native_scope_id=row["native_scope_id"],
        bot_id=row["bot_id"] or None,
        account_id=row["account_id"] or None,
        conversation_id=row["conversation_id"] or None,
        session_id=row["session_id"] or None,
    )


def version_from_row(
    row: sqlite3.Row,
    *,
    lineage_column: str,
    revision_column: str,
) -> VersionRef:
    return VersionRef(
        lineage_id=row[lineage_column],
        revision=int(row[revision_column]),
    )
