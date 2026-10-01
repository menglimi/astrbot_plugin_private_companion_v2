"""Agenda rows share the V2 transaction and operation authority."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import sqlite3

from companion_v2.storage.runtime import StorageRuntime

from .models import AgendaError, AgendaTarget, Memo, Reminder, Schedule, encode, fingerprint, restore_identity, stamp


class AgendaRepository:
    def __init__(self, runtime: StorageRuntime) -> None:
        self.runtime = runtime

    def memo(self, memo_id: str) -> Memo | None:
        row = self.runtime.read_one("SELECT * FROM agenda_memos WHERE memo_id = ?", (memo_id,))
        if row is None:
            return None
        data = json.loads(row["record_json"])
        return Memo(memo_id, AgendaTarget.restore(json.loads(row["target_json"])), row["revision"], row["state"],
                    data["title"], data["body"], bool(row["pinned"]), Schedule.restore(data["schedule"]),
                    data["sequence"], data["completion_count"], restore_identity(data["creator"]), data["content_revision"])

    def reminder(self, reminder_id: str) -> Reminder | None:
        row = self.runtime.read_one("SELECT * FROM agenda_reminders WHERE reminder_id = ?", (reminder_id,))
        if row is None:
            return None
        data = json.loads(row["record_json"])
        return Reminder(reminder_id, AgendaTarget.restore(json.loads(row["target_json"])), row["revision"], row["state"],
                        row["memo_id"], data["message"], Schedule.restore(data["schedule"]),
                        restore_identity(data["requester"]), data["role_binding_revision"],
                        data["authorization_action"], data["sequence"])

    def linked_reminder(self, memo_id: str) -> Reminder | None:
        row = self.runtime.read_one("SELECT reminder_id FROM agenda_reminders WHERE memo_id = ?", (memo_id,))
        return self.reminder(row["reminder_id"]) if row else None

    def save_memo(self, memo: Memo, *, expected_revision: int, now: datetime) -> None:
        with self.runtime.transaction() as connection:
            if expected_revision == 0:
                connection.execute("INSERT INTO agenda_memos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    memo.memo_id, memo.target.key, encode(memo.target), memo.revision, memo.state,
                    int(memo.pinned), encode(memo), stamp(now), stamp(now),
                ))
            else:
                result = connection.execute(
                    "UPDATE agenda_memos SET revision = ?, state = ?, pinned = ?, record_json = ?, updated_at = ? WHERE memo_id = ? AND revision = ?",
                    (memo.revision, memo.state, int(memo.pinned), encode(memo), stamp(now), memo.memo_id, expected_revision),
                )
                if result.rowcount != 1:
                    raise AgendaError("agenda_revision_conflict", "memo changed before commit")

    def save_reminder(self, reminder: Reminder, *, expected_revision: int, now: datetime) -> None:
        with self.runtime.transaction() as connection:
            if expected_revision == 0:
                connection.execute("INSERT INTO agenda_reminders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    reminder.reminder_id, reminder.target.key, encode(reminder.target), reminder.memo_id,
                    reminder.revision, reminder.state, encode(reminder), stamp(now), stamp(now),
                ))
            else:
                result = connection.execute(
                    "UPDATE agenda_reminders SET revision = ?, state = ?, record_json = ?, updated_at = ? WHERE reminder_id = ? AND revision = ?",
                    (reminder.revision, reminder.state, encode(reminder), stamp(now), reminder.reminder_id, expected_revision),
                )
                if result.rowcount != 1:
                    raise AgendaError("agenda_revision_conflict", "reminder changed before commit")

    def schedule(self, reminder: Reminder, *, sequence: int, now: datetime) -> str | None:
        due = reminder.schedule.at(sequence)
        if due is None:
            return None
        occurrence_id = fingerprint([reminder.reminder_id, reminder.revision, sequence])
        with self.runtime.transaction() as connection:
            connection.execute(
                """INSERT INTO agenda_occurrences VALUES (?, ?, ?, ?, ?, 'scheduled', 1, NULL, NULL, ?)
                   ON CONFLICT(occurrence_id) DO NOTHING""",
                (occurrence_id, reminder.reminder_id, reminder.revision, sequence, stamp(due), stamp(now)),
            )
        return occurrence_id

    def replace_schedule(self, reminder: Reminder, *, previous_revision: int, now: datetime) -> None:
        with self.runtime.transaction() as connection:
            self.save_reminder(reminder, expected_revision=previous_revision, now=now)
            # Prepared data remains as historical evidence but no longer authorizes handoff.
            connection.execute(
                """UPDATE agenda_occurrences SET state = 'cancelled', revision = revision + 1, updated_at = ?
                   WHERE reminder_id = ? AND state != 'cancelled'""", (stamp(now), reminder.reminder_id),
            )
            if reminder.state == "active":
                self.schedule(reminder, sequence=reminder.sequence, now=now)

    def sync_memo(self, memo: Memo, *, now: datetime) -> Reminder | None:
        reminder = self.linked_reminder(memo.memo_id)
        if reminder is None or reminder.state != "active":
            return reminder
        updated = replace(reminder, revision=reminder.revision + 1, sequence=memo.sequence,
                          schedule=memo.schedule or reminder.schedule,
                          state="active" if memo.state == "active" and memo.schedule is not None else "cancelled")
        self.replace_schedule(updated, previous_revision=reminder.revision, now=now)
        return updated

    def invalidate_memo_content(self, memo_id: str, *, now: datetime) -> None:
        """Rebuild the same unsubmitted preparation; editing prose does not create another appointment."""
        with self.runtime.transaction() as connection:
            connection.execute(
                """UPDATE agenda_occurrences SET state = 'scheduled', revision = revision + 1,
                   memo_revision = NULL, prepared_json = NULL, updated_at = ?
                   WHERE reminder_id IN (SELECT reminder_id FROM agenda_reminders WHERE memo_id = ? AND state = 'active')
                   AND state IN ('accepted', 'prepared')""", (stamp(now), memo_id),
            )

    def erase_memo_preparations(self, memo_id: str) -> None:
        with self.runtime.transaction() as connection:
            connection.execute(
                """UPDATE agenda_occurrences SET prepared_json = NULL
                   WHERE reminder_id IN (SELECT reminder_id FROM agenda_reminders WHERE memo_id = ?)""", (memo_id,),
            )

    def occurrence(self, occurrence_id: str) -> sqlite3.Row | None:
        return self.runtime.read_one("SELECT * FROM agenda_occurrences WHERE occurrence_id = ?", (occurrence_id,))
