"""Retire a reset window's session/short atoms without forgetting durable evidence."""

import json
from uuid import uuid4

from companion_v2.execution.models import encode, stamp


def expire_temporary(runtime, window, *, at):
    where, values = window.sql("scope_json")
    with runtime.transaction() as connection:
        rows = connection.execute("""SELECT * FROM memory_atoms WHERE state = 'active'
            AND json_extract(record_json, '$.proposal.retention') IN ('session', 'short') AND """ + where,
            values).fetchall()
        for row in rows:
            revision = row["revision"] + 1
            record = {**json.loads(row["record_json"]), "context_reset_at": stamp(at), "change_token": uuid4().hex}
            connection.execute("""UPDATE memory_atoms SET state = 'invalidated', revision = ?,
                record_json = ?, updated_at = ? WHERE atom_id = ?""",
                (revision, encode(record), stamp(at), row["atom_id"]))
            connection.execute("UPDATE memory_revisions SET state = 'invalidated' WHERE atom_id = ? AND revision = ?",
                               (row["atom_id"], row["revision"]))
            connection.execute("INSERT INTO memory_revisions VALUES (?, ?, 'invalidated', ?, ?)",
                               (row["atom_id"], revision, encode(record), row["source_json"]))
            connection.execute("""INSERT INTO memory_changes(owner_key, namespace, atom_id, revision, kind, occurred_at)
                VALUES (?, ?, ?, ?, 'context_reset', ?)""",
                (row["owner_key"], row["namespace"], row["atom_id"], revision, stamp(at)))
        # A pending temporary proposal from the old window must not land in a later turn.
        where, values = window.sql("context_json", "$.audience.scope")
        connection.execute("""UPDATE memory_operations SET state = 'discarded', proposal_json = NULL,
            result_json = json_set(result_json, '$.state', 'discarded'), updated_at = ?
            WHERE state = 'pending' AND json_extract(proposal_json, '$.retention') IN ('session', 'short')
            AND """ + where, (stamp(at), *values))
        return len(rows)
