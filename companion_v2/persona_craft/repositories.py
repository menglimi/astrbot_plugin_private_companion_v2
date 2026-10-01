"""Storage access for persona draft versions: append and read, never rewrite.

读取方向只有「最新在前的一页」和「按 ID 取一版」两种，写入方向只有一条 INSERT。
没有 UPDATE，也没有 DELETE —— 不是因为调用方不会写，而是因为历史可改写的话，
「撤回」就只剩删除这一种实现，而用户要的撤回是**再加一版**。
"""

from __future__ import annotations

from datetime import datetime, timezone

from companion_v2.execution.models import TaskError, stamp
from companion_v2.persona_craft.models import (DRAFT_KIND, DraftVersion, MAX_PAGE, RESTORE_KIND,
                                               clean_draft, clean_note, version_id)


_COLUMNS = ("version_id", "sequence", "kind", "draft_text", "original_text",
            "persona_name", "note", "restored_from", "created_at")


def _parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _row_to_version(row) -> DraftVersion:
    return DraftVersion(row["version_id"], row["sequence"], row["kind"], row["draft_text"],
                        row["original_text"], row["persona_name"], row["note"], row["restored_from"],
                        _parse_stamp(row["created_at"]))


class PersonaDraftRepository:
    """One owner's version history, on the shared V2 transaction."""

    def __init__(self, runtime):
        self.runtime = runtime

    def latest(self, owner: str) -> DraftVersion | None:
        row = self.runtime.read_one(
            "SELECT * FROM persona_draft_versions WHERE owner_key = ? ORDER BY sequence DESC LIMIT 1",
            (owner,))
        return _row_to_version(row) if row is not None else None

    def version(self, owner: str, identifier: str) -> DraftVersion:
        row = self.runtime.read_one(
            "SELECT * FROM persona_draft_versions WHERE owner_key = ? AND version_id = ?",
            (owner, identifier))
        if row is None:
            raise TaskError("persona_version_unavailable", "that version is not part of this persona's history")
        return _row_to_version(row)

    def history(self, owner: str, *, limit: int = 30) -> tuple[DraftVersion, ...]:
        if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE:
            raise TaskError("persona_workshop_request_invalid", f"ask for between 1 and {MAX_PAGE} versions")
        rows = self.runtime.read_all(
            "SELECT * FROM persona_draft_versions WHERE owner_key = ? ORDER BY sequence DESC LIMIT ?",
            (owner, limit))
        return tuple(_row_to_version(row) for row in rows)

    def count(self, owner: str) -> int:
        row = self.runtime.read_one(
            "SELECT COUNT(*) AS n FROM persona_draft_versions WHERE owner_key = ?", (owner,))
        return int(row["n"]) if row is not None else 0

    def append(self, owner: str, *, draft_text, note, original_text, persona_name, at,
               kind: str = DRAFT_KIND, restored_from: str | None = None) -> DraftVersion:
        """Append exactly one version; this is the only write this domain performs."""
        text = clean_draft(draft_text)
        label = clean_note(note)
        if type(original_text) is not str:
            raise TaskError("persona_workshop_request_invalid", "the original persona must be the host's own text")
        if type(persona_name) is not str:
            raise TaskError("persona_workshop_request_invalid", "the persona display name must be text")
        if kind == RESTORE_KIND:
            if type(restored_from) is not str or not restored_from:
                raise TaskError("persona_workshop_request_invalid", "a restore names the version it revives")
        elif kind != DRAFT_KIND or restored_from is not None:
            raise TaskError("persona_workshop_request_invalid", "only a restore names its source version")
        created_at = stamp(at)
        with self.runtime.transaction() as connection:
            row = connection.execute(
                "SELECT MAX(sequence) AS last FROM persona_draft_versions WHERE owner_key = ?",
                (owner,)).fetchone()
            sequence = int(row["last"] or 0) + 1
            identifier = version_id(sequence)
            connection.execute(
                "INSERT INTO persona_draft_versions(owner_key, " + ", ".join(_COLUMNS)
                + ") VALUES (" + ", ".join("?" for _ in range(len(_COLUMNS) + 1)) + ")",
                (owner, identifier, sequence, kind, text, original_text, persona_name, label, restored_from,
                 created_at))
        return DraftVersion(identifier, sequence, kind, text, original_text, persona_name, label,
                            restored_from, _parse_stamp(created_at))


__all__ = ["PersonaDraftRepository"]
