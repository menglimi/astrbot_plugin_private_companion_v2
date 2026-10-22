"""Durable Content retractions and bounded read-only owner observations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from companion_v2.storage.sqlite_path import readonly_uri

from .models import ContentError, WorkOwner, canonical, identifier, integer


def append_retraction(connection: sqlite3.Connection, owner: dict, receipt: dict) -> None:
    event_id = "content-retraction:" + receipt["operation_id"]
    event = dict(event_id=event_id, owner=owner, work_id=receipt["work_id"],
                 revision=receipt["revision"], operation_id=receipt["operation_id"], state="retracted")
    connection.execute(
        """INSERT INTO content_v2_events
           (event_id, installation_id, owner_key, work_id, revision, operation_id, event_json)
           VALUES (?,?,?,?,?,?,?)""",
        (event_id, owner["installation_id"], WorkOwner(**owner).key,
         receipt["work_id"], receipt["revision"], receipt["operation_id"], canonical(event)),
    )


def _query(value: dict, schema: str, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys | {"schema"} or value["schema"] != schema:
        raise ContentError("invalid_governance_query")
    return json.loads(canonical(value))


class ContentGovernance:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connection(self):
        # Never acquire the writer's lock while the host may hold its own lock.
        # WAL gives this short independent reader a committed snapshot.
        connection = sqlite3.connect(readonly_uri(self.path), uri=True, timeout=1)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    def events(self, request: dict, guard) -> dict:
        value = _query(request, "content.governance-query.v1", {"installation_id", "after_seq", "limit"})
        identifier(value["installation_id"])
        integer(value["after_seq"])
        integer(value["limit"], 1, 100)
        guard()
        connection = self._connection()
        try:
            rows = connection.execute(
                """SELECT seq, event_json FROM content_v2_events
                   WHERE installation_id=? AND seq>? ORDER BY seq LIMIT ?""",
                (value["installation_id"], value["after_seq"], value["limit"]),
            ).fetchall()
            result = dict(schema="content.governance-page.v1",
                          installation_id=value["installation_id"], after_seq=value["after_seq"],
                          events=[dict(seq=row["seq"], **json.loads(row["event_json"])) for row in rows],
                          next_after=rows[-1]["seq"] if rows else value["after_seq"])
            guard()
            return result
        finally:
            connection.close()

    def state(self, request: dict, guard) -> dict:
        value = _query(request, "content.state-query.v1", {"owner", "work_id", "version_id"})
        try:
            owner = WorkOwner(**value["owner"])
        except (TypeError, ValueError) as exc:
            raise ContentError("invalid_owner") from exc
        identifier(value["work_id"])
        if value["version_id"] is not None:
            identifier(value["version_id"])
        guard()
        connection = self._connection()
        try:
            if value["version_id"] is None:
                row = connection.execute(
                    """SELECT state, revision, NULL AS content_hash, '[]' AS sources_json
                       FROM content_v2_works WHERE owner_key=? AND work_id=?""",
                    (owner.key, value["work_id"]),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT w.state, w.revision, v.content_hash, v.sources_json
                       FROM content_v2_works w JOIN content_v2_versions v USING(owner_key, work_id)
                       WHERE w.owner_key=? AND w.work_id=? AND v.version_id=?""",
                    (owner.key, value["work_id"], value["version_id"]),
                ).fetchone()
            result = dict(schema="content.work-state.v1", state=row["state"] if row else "unavailable",
                          owner=owner.value(), work_id=value["work_id"],
                          revision=row["revision"] if row else None, version_id=value["version_id"],
                          content_hash=row["content_hash"] if row else None,
                          sources=json.loads(row["sources_json"]) if row and row["state"] == "active" else [])
            guard()
            return result
        finally:
            connection.close()
