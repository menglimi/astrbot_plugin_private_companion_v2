"""Transactional work/version operations, with host-owned access checks."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from .models import (
    MAX_READ_CHARS,
    AccessPort,
    AccessRequest,
    Action,
    Call,
    Catalogue,
    Chapter,
    ContentError,
    JsonObject,
    Origin,
    Receipt,
    Segment,
    VersionPage,
    WorkOwner,
    WorkSummary,
    canonical,
    digest,
    identifier,
    integer,
    manuscript,
    source_union,
)
from .repository import ContentRepository
from .governance import append_retraction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sources(version: sqlite3.Row) -> tuple[JsonObject, ...]:
    return source_union(tuple(JsonObject.capture(item)
                              for item in json.loads(version["sources_json"])))


def _summary(work: sqlite3.Row) -> WorkSummary:
    return WorkSummary(work["work_id"], work["title"], work["work_type"],
                       work["revision"], work["head_version"], work["state"],
                       JsonObject(work["author_json"]), JsonObject(work["audience_json"]))


class ContentService:
    def __init__(self, repository: ContentRepository, access: AccessPort) -> None:
        if not callable(getattr(access, "check", None)):
            raise ContentError("access_port_required")
        self.repository = repository
        self.access = access
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self.repository.close()

    def _guard(
        self, call: Call, owner: WorkOwner, action: Action,
        work: sqlite3.Row | None = None, *, sources: tuple[JsonObject, ...] = (),
        contributor: JsonObject | None = None,
    ) -> None:
        if self._closed:
            raise ContentError("service_closed")
        if not isinstance(call, Call) or not isinstance(owner, WorkOwner):
            raise ContentError("invalid_call")
        if contributor is not None and not isinstance(contributor, JsonObject):
            raise ContentError("object_required")
        call.before_dispatch()
        request = AccessRequest(action, owner, call.origin,
                                work["work_id"] if work else None,
                                JsonObject(work["audience_json"]) if work else None,
                                sources, contributor)
        if self.access.check(request) is not None:
            raise ContentError("invalid_access_port")
        call.before_dispatch()

    @staticmethod
    def _work(connection: sqlite3.Connection, owner: WorkOwner, work_id: str,
              *, active: bool = False) -> sqlite3.Row:
        identifier(work_id)
        row = connection.execute(
            "SELECT * FROM content_v2_works WHERE owner_key=? AND work_id=?",
            (owner.key, work_id),
        ).fetchone()
        if row is None:
            raise ContentError("work_not_found")
        if row["owner_json"] != canonical(owner.value()):
            raise ContentError("owner_corrupt")
        if active and row["state"] != "active":
            raise ContentError("work_retracted")
        return row

    @staticmethod
    def _require_active(work: sqlite3.Row) -> None:
        if work["state"] != "active":
            raise ContentError("work_retracted")

    @staticmethod
    def _version(connection: sqlite3.Connection, owner: WorkOwner,
                 work_id: str, version_id: str) -> sqlite3.Row:
        identifier(version_id)
        row = connection.execute(
            """SELECT * FROM content_v2_versions
               WHERE owner_key=? AND work_id=? AND version_id=?""",
            (owner.key, work_id, version_id),
        ).fetchone()
        if row is None:
            raise ContentError("version_not_found")
        if digest(row["manuscript_json"]) != row["content_hash"]:
            raise ContentError("content_corrupt")
        return row

    @staticmethod
    def _fingerprint(action: Action, call: Call, owner: WorkOwner,
                     payload: dict) -> str:
        # Runtime generation/session details stay in the audit envelope. A new
        # process can reconcile the same operation without changing its origin.
        return digest(canonical(dict(action=action, owner=owner.value(),
                                     origin=call.origin.summary(), payload=payload)))

    def _replay(self, connection: sqlite3.Connection, call: Call,
                owner: WorkOwner, action: Action, key: str,
                fingerprint: str) -> Receipt | None:
        row = connection.execute(
            """SELECT * FROM content_v2_operations
               WHERE owner_key=? AND operation_key=?""", (owner.key, key),
        ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ContentError("idempotency_conflict")
        work = self._work(connection, owner, row["work_id"], active=False)
        # Historical metadata is still available after retraction, but never
        # bypasses current caller/capability/audience authorization.
        self._guard(call, owner, action, work)
        return Receipt.from_value(json.loads(row["receipt_json"]))

    @staticmethod
    def _insert_version(connection: sqlite3.Connection, owner: WorkOwner,
                        work_id: str, version_id: str, call: Call, text: str,
                        contributor: JsonObject, sources: tuple[JsonObject, ...],
                        base_revision: int, base_version: str | None, at: str) -> None:
        connection.execute(
            """INSERT INTO content_v2_versions
               (owner_key, work_id, version_id, base_revision, base_version,
                manuscript_json, content_hash, origin_json, contributor_json,
                sources_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (owner.key, work_id, version_id, base_revision, base_version,
             text, digest(text), canonical(call.origin.value()), contributor.encoded,
             canonical([source.value() for source in sources]), at),
        )

    @staticmethod
    def _record(connection: sqlite3.Connection, owner: WorkOwner, call: Call,
                action: Action, key: str, fingerprint: str, work_id: str,
                version_id: str | None, before: int, after: int,
                previous_version: str | None, version_origin: Origin | None,
                sources: tuple[JsonObject, ...], at: str) -> Receipt:
        receipt = Receipt("operation-" + uuid4().hex, key, action, work_id, version_id,
                          before, after, previous_version,
                          JsonObject.capture(call.origin.summary()),
                          JsonObject.capture(version_origin.summary()) if version_origin else None,
                          sources, at)
        connection.execute(
            "INSERT INTO content_v2_operations VALUES (?,?,?,?,?,?,?)",
            (owner.key, key, fingerprint, receipt.operation_id, work_id,
             canonical(call.origin.value()), canonical(receipt.value())),
        )
        return receipt

    def create(self, call: Call, owner: WorkOwner, *, operation_key: str,
               title: str, work_type: str, chapters: tuple[Chapter, ...],
               contributor: JsonObject, sources: tuple[JsonObject, ...] = ()) -> Receipt:
        """Persist an explicitly accepted first version, without generating/sending."""
        identifier(operation_key)
        if not isinstance(title, str) or len(title) > 200:
            raise ContentError("invalid_title")
        if not isinstance(work_type, str) or len(work_type) > 80:
            raise ContentError("invalid_work_type")
        text = manuscript(chapters)
        sources = source_union(sources)
        self._guard(call, owner, "create", contributor=contributor)
        fingerprint = self._fingerprint("create", call, owner, dict(
            title=title, work_type=work_type, manuscript=json.loads(text),
            contributor=contributor.value(), sources=[item.value() for item in sources]))
        with self.repository.transaction(write=True) as connection:
            self._guard(call, owner, "create", contributor=contributor)
            prior = self._replay(connection, call, owner, "create", operation_key, fingerprint)
            if prior:
                return prior
            self._guard(call, owner, "create", sources=sources, contributor=contributor)
            work_id, version_id, at = "work-" + uuid4().hex, "version-" + uuid4().hex, _now()
            connection.execute(
                "INSERT INTO content_v2_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (owner.key, work_id, canonical(owner.value()), title, work_type,
                 contributor.encoded, call.origin.audience.encoded, 1, version_id,
                 "active", canonical(call.origin.value()), at),
            )
            self._insert_version(connection, owner, work_id, version_id, call, text,
                                 contributor, sources, 0, None, at)
            connection.execute("INSERT INTO content_v2_heads VALUES (?,?,?,?)",
                               (owner.key, work_id, 1, version_id))
            result = self._record(connection, owner, call, "create", operation_key,
                                  fingerprint, work_id, version_id, 0, 1, None,
                                  call.origin, sources, at)
            self._guard(call, owner, "create", self._work(connection, owner, work_id),
                        sources=sources, contributor=contributor)
            return result

    def save_candidate(self, call: Call, owner: WorkOwner, *, operation_key: str,
                       work_id: str, base_revision: int, base_version: str,
                       chapters: tuple[Chapter, ...], contributor: JsonObject,
                       sources: tuple[JsonObject, ...] = ()) -> Receipt:
        """Keep an old task's draft, retaining its actual base and dependencies."""
        identifier(operation_key)
        integer(base_revision, 1)
        identifier(base_version)
        text, sources = manuscript(chapters), source_union(sources)
        self._guard(call, owner, "save_candidate", contributor=contributor)
        fingerprint = self._fingerprint("save_candidate", call, owner, dict(
            work_id=work_id, base_revision=base_revision, base_version=base_version,
            manuscript=json.loads(text), contributor=contributor.value(),
            sources=[item.value() for item in sources]))
        with self.repository.transaction(write=True) as connection:
            self._guard(call, owner, "save_candidate", contributor=contributor)
            prior = self._replay(connection, call, owner, "save_candidate", operation_key, fingerprint)
            if prior:
                return prior
            work = self._work(connection, owner, work_id)
            self._guard(call, owner, "save_candidate", work, contributor=contributor)
            self._require_active(work)
            head = connection.execute(
                """SELECT version_id FROM content_v2_heads
                   WHERE owner_key=? AND work_id=? AND revision=?""",
                (owner.key, work_id, base_revision),
            ).fetchone()
            if head is None or head["version_id"] != base_version:
                raise ContentError("invalid_base")
            base = self._version(connection, owner, work_id, base_version)
            sources = source_union(_sources(base), sources)
            self._guard(call, owner, "save_candidate", work, sources=sources,
                        contributor=contributor)
            version_id, at = "version-" + uuid4().hex, _now()
            self._insert_version(connection, owner, work_id, version_id, call, text,
                                 contributor, sources, base_revision, base_version, at)
            result = self._record(connection, owner, call, "save_candidate", operation_key,
                                  fingerprint, work_id, version_id, work["revision"],
                                  work["revision"], work["head_version"], call.origin, sources, at)
            self._guard(call, owner, "save_candidate", work, sources=sources,
                        contributor=contributor)
            return result

    def adopt(self, call: Call, owner: WorkOwner, *, operation_key: str,
              work_id: str, version_id: str, expected_revision: int) -> Receipt:
        """CAS the current head; a late draft cannot impersonate a fresh edit."""
        identifier(operation_key)
        integer(expected_revision, 1)
        self._guard(call, owner, "adopt")
        fingerprint = self._fingerprint("adopt", call, owner, dict(
            work_id=work_id, version_id=version_id, expected_revision=expected_revision))
        with self.repository.transaction(write=True) as connection:
            self._guard(call, owner, "adopt")
            prior = self._replay(connection, call, owner, "adopt", operation_key, fingerprint)
            if prior:
                return prior
            work = self._work(connection, owner, work_id)
            self._guard(call, owner, "adopt", work)
            self._require_active(work)
            if work["revision"] != expected_revision:
                raise ContentError("revision_conflict")
            version = self._version(connection, owner, work_id, version_id)
            if (version["base_revision"] != expected_revision
                    or version["base_version"] != work["head_version"]):
                raise ContentError("stale_candidate")
            sources = _sources(version)
            self._guard(call, owner, "adopt", work, sources=sources)
            changed = connection.execute(
                """UPDATE content_v2_works SET revision=revision+1, head_version=?
                   WHERE owner_key=? AND work_id=? AND revision=? AND state='active'""",
                (version_id, owner.key, work_id, expected_revision),
            ).rowcount
            if changed != 1:
                raise ContentError("revision_conflict")
            connection.execute("INSERT INTO content_v2_heads VALUES (?,?,?,?)",
                               (owner.key, work_id, expected_revision + 1, version_id))
            result = self._record(connection, owner, call, "adopt", operation_key, fingerprint,
                                  work_id, version_id, expected_revision, expected_revision + 1,
                                  work["head_version"], Origin.from_value(json.loads(version["origin_json"])),
                                  sources, _now())
            self._guard(call, owner, "adopt", work, sources=sources)
            return result

    def retract(self, call: Call, owner: WorkOwner, *, operation_key: str,
                work_id: str, expected_revision: int) -> Receipt:
        """Hide all versions; preserve historical writes without claiming unsend."""
        identifier(operation_key)
        integer(expected_revision, 1)
        self._guard(call, owner, "retract")
        fingerprint = self._fingerprint("retract", call, owner, dict(
            work_id=work_id, expected_revision=expected_revision))
        with self.repository.transaction(write=True) as connection:
            self._guard(call, owner, "retract")
            prior = self._replay(connection, call, owner, "retract", operation_key, fingerprint)
            if prior:
                return prior
            work = self._work(connection, owner, work_id)
            self._guard(call, owner, "retract", work)
            self._require_active(work)
            if work["revision"] != expected_revision:
                raise ContentError("revision_conflict")
            connection.execute(
                """UPDATE content_v2_works SET revision=revision+1, state='retracted'
                   WHERE owner_key=? AND work_id=? AND revision=? AND state='active'""",
                (owner.key, work_id, expected_revision),
            )
            result = self._record(connection, owner, call, "retract", operation_key,
                                  fingerprint, work_id, None, expected_revision,
                                  expected_revision + 1, work["head_version"], None, (), _now())
            append_retraction(connection, owner.value(), result.value())
            self._guard(call, owner, "retract", work)
            return result

    def lookup(self, call: Call, owner: WorkOwner, operation_id: str) -> Receipt:
        """Read only the original metadata receipt, even if the work was withdrawn."""
        identifier(operation_id)
        self._guard(call, owner, "lookup")
        with self.repository.transaction() as connection:
            self._guard(call, owner, "lookup")
            row = connection.execute(
                "SELECT * FROM content_v2_operations WHERE owner_key=? AND operation_id=?",
                (owner.key, operation_id),
            ).fetchone()
            if row is None:
                raise ContentError("operation_not_found")
            work = self._work(connection, owner, row["work_id"], active=False)
            self._guard(call, owner, "lookup", work)
            return Receipt.from_value(json.loads(row["receipt_json"]))

    def lookup_request(self, call: Call, owner: WorkOwner, operation_key: str) -> Receipt:
        """Reconcile the original request, without performing the mutation again."""
        identifier(operation_key)
        self._guard(call, owner, "lookup")
        with self.repository.transaction() as connection:
            self._guard(call, owner, "lookup")
            row = connection.execute(
                "SELECT * FROM content_v2_operations WHERE owner_key=? AND operation_key=?",
                (owner.key, operation_key),
            ).fetchone()
            if row is None:
                raise ContentError("operation_not_found")
            work = self._work(connection, owner, row["work_id"], active=False)
            self._guard(call, owner, "lookup", work)
            receipt = Receipt.from_value(json.loads(row["receipt_json"]))
            if receipt.origin.value() != call.origin.summary():
                raise ContentError("original_request_mismatch")
            return receipt

    def get_work(self, call: Call, owner: WorkOwner, work_id: str) -> WorkSummary:
        self._guard(call, owner, "read")
        with self.repository.transaction() as connection:
            self._guard(call, owner, "read")
            work = self._work(connection, owner, work_id)
            self._guard(call, owner, "read", work)
            self._require_active(work)
            version = self._version(connection, owner, work_id, work["head_version"])
            self._guard(call, owner, "read", work, sources=_sources(version))
            return _summary(work)

    def list_works(self, call: Call, owner: WorkOwner, *, after_id: str = "",
                   limit: int = 20) -> Catalogue:
        integer(limit, 1, 50)
        if after_id != "":
            identifier(after_id)
        self._guard(call, owner, "list")
        with self.repository.transaction() as connection:
            self._guard(call, owner, "list")
            rows = connection.execute(
                """SELECT * FROM content_v2_works WHERE owner_key=? AND state='active'
                   AND work_id>? ORDER BY work_id LIMIT ?""",
                (owner.key, after_id, limit + 1),
            ).fetchall()
            items, returned_sources = [], {}
            for row in rows[:limit]:
                try:
                    self._guard(call, owner, "read", row)
                    version = self._version(connection, owner, row["work_id"], row["head_version"])
                    self._guard(call, owner, "read", row, sources=_sources(version))
                except ContentError as exc:
                    if exc.code in {"permission_denied", "source_unavailable"}:
                        continue
                    raise
                items.append(_summary(row))
                returned_sources.update((source.encoded, source) for source in _sources(version))
            self._guard(call, owner, "list", sources=tuple(returned_sources.values()))
            # A sparse page is deliberate: never scan an unbounded owner's
            # archive to fill a page whose sources have been revoked.
            return Catalogue(tuple(items), rows[limit - 1]["work_id"]
                             if len(rows) > limit else None)

    def read_version(self, call: Call, owner: WorkOwner, work_id: str,
                     version_id: str, *, offset: int = 0, limit: int = 2048) -> VersionPage:
        """Read an exact immutable version using Unicode half-open ranges."""
        integer(offset)
        integer(limit, 1, MAX_READ_CHARS)
        self._guard(call, owner, "read")
        with self.repository.transaction() as connection:
            self._guard(call, owner, "read")
            work = self._work(connection, owner, work_id)
            self._guard(call, owner, "read", work)
            self._require_active(work)
            version = self._version(connection, owner, work_id, version_id)
            sources = _sources(version)
            self._guard(call, owner, "read", work, sources=sources)
            try:
                chapters = tuple(Chapter(**part) for part in json.loads(version["manuscript_json"]))
                if manuscript(chapters) != version["manuscript_json"]:
                    raise ContentError("content_corrupt")
            except (TypeError, ValueError, KeyError) as exc:
                raise ContentError("content_corrupt") from exc
            total = sum(len(chapter.text) for chapter in chapters)
            if offset > total:
                raise ContentError("invalid_range")
            position, segments = 0, []
            for chapter in chapters:
                start, end = max(offset, position), min(offset + limit, position + len(chapter.text))
                if start < end:
                    segments.append(Segment(chapter.chapter_id, start - position, start, end,
                                            chapter.text[start - position:end - position], chapter.title))
                position += len(chapter.text)
                if len(segments) >= 100:
                    break
            end = segments[-1].end if segments else offset
            result = VersionPage(
                work_id, version_id, version["content_hash"], version["base_revision"],
                version["base_version"], JsonObject(version["contributor_json"]),
                JsonObject.capture(Origin.from_value(json.loads(version["origin_json"])).summary()),
                sources, offset, end, total, end if end < total else None, tuple(segments),
            )
            self._guard(call, owner, "read", work, sources=sources)
            return result
