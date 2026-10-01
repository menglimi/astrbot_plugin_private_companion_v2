"""Backfill only activity versions actually present in the V2 store."""

import json
import sqlite3

from .codec import scope_from_row


def backfill(connection):
    from companion_v2.execution.models import digest, stamp
    from companion_v2.role_work.codec import activity_from_json

    def remember(owner, text, provenance, operation_id=None, operation_scope=None):
        try:
            data = json.loads(text)
            identifier, revision, at = data["activity_id"], data["revision"], data["updated_at"]
            if type(revision) is not int or revision < 1 or type(at) is not str:
                raise ValueError("invalid activity revision")
            activity = activity_from_json(text)
            if digest(activity.owner) != owner or stamp(activity.updated_at) != at:
                raise ValueError("activity history identity or timestamp is invalid")
            if operation_scope is not None and activity.scope != operation_scope:
                raise ValueError("activity history differs from its original operation scope")
            head = connection.execute("SELECT revision, record_json FROM role_activities WHERE owner_key = ? AND activity_id = ?",
                                      (owner, identifier)).fetchone()
            if head is None or revision > head["revision"]:
                raise ValueError("activity history has no matching head")
            current = json.loads(head["record_json"])
            if (data["scope"] != current["scope"] or data["role_id"] != current["role_id"]
                    or at > current["updated_at"] or current["revision"] != head["revision"]):
                raise ValueError("activity history crosses its original owner or scope")
            previous = connection.execute("SELECT record_json FROM role_activity_revisions WHERE owner_key = ? AND activity_id = ? AND revision = ?",
                                           (owner, identifier, revision)).fetchone()
            if previous is not None:
                if json.loads(previous["record_json"]) != data:
                    raise ValueError("conflicting activity revision records")
                return
            connection.execute("INSERT INTO role_activity_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (owner, identifier, revision, at, provenance, operation_id, text))
        except (ValueError, TypeError, KeyError) as error:
            raise sqlite3.IntegrityError("invalid persisted activity history") from error

    # Receipts retain historical versions even when the mutable head moved on.
    for row in connection.execute("""SELECT r.*, o.* FROM role_life_operations r
                                     JOIN operations o ON o.operation_id = r.operation_id ORDER BY r.operation_id"""):
        if row["state"] != "completed" or row["owner"] != "role.life":
            raise sqlite3.IntegrityError("activity history requires completed owner receipts")
        remember(row["owner_key"], row["result_json"], "legacy_receipt", row["operation_id"], scope_from_row(row))
    for row in connection.execute("SELECT owner_key, record_json FROM role_activities"):
        remember(row["owner_key"], row["record_json"], "legacy_head")
