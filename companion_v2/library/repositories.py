"""Transactional repository for the reading archive.

Writes are CAS-versioned on the entry so two racing writers cannot silently overwrite
each other. A provider entry outranks a manual one: a manual write can neither create
nor replace an entry that a provider owns, which keeps the provider the single source
for the works it supplies.
"""

from __future__ import annotations

from datetime import datetime
import json

from companion_v2.execution.models import TaskError
from companion_v2.storage.runtime import StorageRuntime

from .models import (ArchiveConsent, ArchiveEntry, ArchiveReview, AssetReference,
                     ConsentState, EntryKind, EntryOrigin, EntryState,
                     ReadingProgress)


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _pairs(value):
    return tuple(sorted(value.items())) if isinstance(value, dict) else tuple(value)


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _entry_from_row(row):
    """Rebuild an entry from its row, rejecting anything the value objects refuse."""
    source = None
    if row["origin"] == EntryOrigin.PROVIDER.value:
        source = AssetReference(row["provider_id"], row["provider_version"], row["asset_ref"])
    return ArchiveEntry(
        entry_id=row["entry_id"], kind=EntryKind(row["kind"]), title=row["title"], author=row["author"],
        origin=EntryOrigin(row["origin"]), state=EntryState(row["state"]), revision=row["revision"],
        created_at=_parse(row["created_at"]), updated_at=_parse(row["updated_at"]),
        source=source, metadata=_pairs(json.loads(row["metadata_json"])),
    )


class ReadingArchiveRepository:
    def __init__(self, runtime: StorageRuntime):
        self._runtime = runtime

    # --- entries -----------------------------------------------------------------

    def get(self, owner, entry_id):
        row = self._runtime.read_one(
            "SELECT * FROM reading_archive_entries WHERE owner_key = ? AND entry_id = ?", (owner, entry_id))
        return _entry_from_row(row) if row else None

    def list(self, owner, *, after_id="", limit=64, state=None, kind=None):
        if type(limit) is not int or not 1 <= limit <= 200 or type(after_id) is not str:
            raise TaskError("archive_page_invalid", "invalid archive page")
        clauses = ["owner_key = ?", "entry_id > ?"]
        parameters = [owner, after_id]
        if state is not None:
            clauses.append("state = ?")
            parameters.append(EntryState(state).value)
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(EntryKind(kind).value)
        rows = self._runtime.read_all(
            f"SELECT * FROM reading_archive_entries WHERE {' AND '.join(clauses)} ORDER BY entry_id LIMIT ?",
            (*parameters, limit))
        return tuple(_entry_from_row(row) for row in rows)

    def put_entry(self, owner, entry, *, expected=None):
        """Create or replace one entry, refusing a manual write over a provider entry."""
        current = self.get(owner, entry.entry_id)
        revision = current.revision if current else 0
        if expected is not None and expected != revision:
            raise TaskError("archive_conflict", "the archive entry changed; refresh before saving")
        if current is not None and entry.origin is EntryOrigin.MANUAL and current.origin is EntryOrigin.PROVIDER:
            raise TaskError("archive_entry_provider_owned",
                            "a provider-owned entry cannot be replaced by a manual one")
        source = entry.source
        with self._runtime.transaction() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO reading_archive_entries
                   (owner_key, entry_id, kind, title, author, origin, source_json, provider_id,
                    provider_version, asset_ref, metadata_json, state, revision, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (owner, entry.entry_id, entry.kind.value, entry.title, entry.author, entry.origin.value,
                 _json({"provider_id": source.provider_id, "provider_version": source.provider_version,
                        "asset_ref": source.asset_ref}) if source else None,
                 source.provider_id if source else None, source.provider_version if source else None,
                 source.asset_ref if source else None, _json(dict(entry.metadata)), entry.state.value,
                 revision + 1, entry.created_at.isoformat(), entry.updated_at.isoformat()))
        return self.get(owner, entry.entry_id)

    def set_state(self, owner, entry_id, state, *, expected, updated_at):
        entry = self.get(owner, entry_id)
        if entry is None:
            raise TaskError("archive_entry_missing", "the archive entry is unavailable")
        if entry.revision != expected:
            raise TaskError("archive_conflict", "the archive entry changed; refresh before saving")
        with self._runtime.transaction() as connection:
            changed = connection.execute(
                "UPDATE reading_archive_entries SET state = ?, revision = revision + 1, updated_at = ? "
                "WHERE owner_key = ? AND entry_id = ? AND revision = ?",
                (EntryState(state).value, updated_at.isoformat(), owner, entry_id, expected))
            if changed.rowcount != 1:
                raise TaskError("archive_conflict", "the archive entry changed; refresh before saving")
        return self.get(owner, entry_id)

    def withdraw_provider(self, owner, provider_id, *, updated_at):
        """Mark every entry of one provider withdrawn; keeps the catalog honest."""
        with self._runtime.transaction() as connection:
            rows = connection.execute(
                "UPDATE reading_archive_entries SET state = ?, revision = revision + 1, updated_at = ? "
                "WHERE owner_key = ? AND origin = ? AND provider_id = ? AND state != ?",
                (EntryState.WITHDRAWN.value, updated_at.isoformat(), owner, EntryOrigin.PROVIDER.value,
                 provider_id, EntryState.WITHDRAWN.value))
            return rows.rowcount

    # --- progress ----------------------------------------------------------------

    def progress(self, owner, entry_id):
        row = self._runtime.read_one(
            "SELECT * FROM reading_archive_progress WHERE owner_key = ? AND entry_id = ?", (owner, entry_id))
        if row is None:
            return None
        return ReadingProgress(entry_id=row["entry_id"], position=_pairs(json.loads(row["position_json"])),
                               percent=row["percent"], note=row["note"], updated_at=_parse(row["updated_at"]))

    def put_progress(self, owner, progress):
        if self.get(owner, progress.entry_id) is None:
            raise TaskError("archive_entry_missing", "the archive entry is unavailable")
        with self._runtime.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reading_archive_progress VALUES (?,?,?,?,?,?)",
                (owner, progress.entry_id, _json(dict(progress.position)), progress.percent,
                 progress.note, progress.updated_at.isoformat()))
        return self.progress(owner, progress.entry_id)

    # --- reviews -----------------------------------------------------------------

    def review(self, owner, review_id):
        row = self._runtime.read_one(
            "SELECT * FROM reading_archive_reviews WHERE owner_key = ? AND review_id = ?", (owner, review_id))
        return self._review_from_row(row) if row else None

    def reviews(self, owner, entry_id, *, limit=64):
        rows = self._runtime.read_all(
            "SELECT * FROM reading_archive_reviews WHERE owner_key = ? AND entry_id = ? "
            "ORDER BY created_at, review_id LIMIT ?", (owner, entry_id, max(1, min(200, int(limit)))))
        return tuple(self._review_from_row(row) for row in rows)

    @staticmethod
    def _review_from_row(row):
        return ArchiveReview(review_id=row["review_id"], entry_id=row["entry_id"], body=row["body"],
                             rating=row["rating"], evidence=tuple(json.loads(row["evidence_json"])),
                             revision=row["revision"], created_at=_parse(row["created_at"]),
                             updated_at=_parse(row["updated_at"]))

    def put_review(self, owner, review, *, expected=None):
        current = self.review(owner, review.review_id)
        revision = current.revision if current else 0
        if expected is not None and expected != revision:
            raise TaskError("archive_conflict", "the review changed; refresh before saving")
        if self.get(owner, review.entry_id) is None:
            raise TaskError("archive_entry_missing", "the archive entry is unavailable")
        with self._runtime.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reading_archive_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (owner, review.review_id, review.entry_id, review.body, review.rating,
                 _json(list(review.evidence)), review.created_at.isoformat(), review.updated_at.isoformat(),
                 revision + 1))
        return self.review(owner, review.review_id)

    # --- consents ----------------------------------------------------------------

    def consent(self, owner, entry_id, subject_json):
        row = self._runtime.read_one(
            "SELECT * FROM reading_archive_consents WHERE owner_key = ? AND entry_id = ? AND subject_json = ?",
            (owner, entry_id, subject_json))
        if row is None:
            return None
        return ArchiveConsent(entry_id=row["entry_id"], subject_json=row["subject_json"],
                              state=ConsentState(row["state"]), revision=row["revision"],
                              updated_at=_parse(row["updated_at"]))

    def put_consent(self, owner, consent):
        current = self.consent(owner, consent.entry_id, consent.subject_json)
        revision = (current.revision if current else 0) + 1
        with self._runtime.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reading_archive_consents VALUES (?,?,?,?,?,?)",
                (owner, consent.entry_id, consent.subject_json, consent.state.value, revision,
                 consent.updated_at.isoformat()))
        return self.consent(owner, consent.entry_id, consent.subject_json)

    # --- trigger cursors ---------------------------------------------------------

    def trigger_cursor(self, owner, action):
        """When this action last fired, or None. Stored, so a restart cannot bypass it."""
        row = self._runtime.read_one(
            "SELECT * FROM reading_archive_triggers WHERE owner_key = ? AND action = ?", (owner, action))
        return _parse(row["last_at"]) if row else None

    def put_trigger_cursor(self, owner, action, *, at):
        current = self._runtime.read_one(
            "SELECT revision FROM reading_archive_triggers WHERE owner_key = ? AND action = ?",
            (owner, action))
        revision = (current["revision"] if current else 0) + 1
        with self._runtime.transaction() as connection:
            connection.execute("INSERT OR REPLACE INTO reading_archive_triggers VALUES (?,?,?,?)",
                               (owner, action, at.isoformat(), revision))
        return self.trigger_cursor(owner, action)
