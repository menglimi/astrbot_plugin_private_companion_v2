"""Dashboard review of model-suggested self-review guidance.

Accepting an item is the only way guidance becomes active, and an accepted item
is only ever injected while it is unexpired and its original evidence still
resolves. Rejecting is always available, including when the evidence has since
been withdrawn, so an operator is never stuck with an undecidable row.
"""

from __future__ import annotations

import json
from datetime import datetime

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.execution.service import outcome

from ..growth.management import RoleGrowthManagement


class SelfReviewManagement:
    def __init__(self, app):
        self.app = app
        self.runtime = app.runtime
        self.evidence = app.role_self_review_evidence
        self.management = RoleGrowthManagement(app.role_growth)

    @staticmethod
    def _token(operator, context, row, policy_revision):
        return digest(["self-review-decision.v1", operator.subject, operator.binding_id,
            operator.binding_revision, context.key, row["item_id"], row["run_id"],
            row["expires_at"], policy_revision])

    def _row(self, item_id, owner, context):
        if (type(item_id) is not str or not item_id.strip() or len(item_id) > 512
                or item_id != item_id.strip()):
            raise TaskError("self_review_item_invalid", "select an original self-review item")
        row = self.runtime.read_one("""SELECT * FROM role_self_review_items
            WHERE item_id = ? AND owner_key = ? AND scope_key = ?""",
            (item_id, digest(owner), digest(context.scope)))
        if row is None:
            raise TaskError("self_review_item_unavailable", "self-review item is unavailable in this role")
        return row

    def _run(self, row, owner, context):
        run = self.runtime.read_one("""SELECT * FROM role_self_review_runs
            WHERE run_id = ? AND owner_key = ? AND scope_key = ?""",
            (row["run_id"], digest(owner), digest(context.scope)))
        if run is None:
            raise TaskError("self_review_item_unavailable", "self-review run is unavailable in this role")
        try:
            window = json.loads(run["window_json"])
            handles = json.loads(row["evidence_json"])
        except (TypeError, ValueError):
            raise TaskError("self_review_evidence_changed", "stored self-review evidence is invalid") from None
        if (type(window) is not dict or set(window) != {"opened_at", "closed_at", "handles", "kinds"}
                or type(handles) is not list or not handles
                or any(type(value) is not str or value not in window["handles"] for value in handles)):
            raise TaskError("self_review_evidence_changed", "stored self-review evidence is invalid")
        return run, window, handles

    def _basis(self, row, owner, context, at):
        """Recheck the cited handles; unrelated withdrawn evidence does not block this item."""
        run, window, handles = self._run(row, owner, context)
        try:
            opened_at = datetime.fromisoformat(window["opened_at"])
            closed_at = datetime.fromisoformat(window["closed_at"])
        except (TypeError, ValueError):
            raise TaskError("self_review_evidence_changed", "stored self-review window is invalid") from None
        if (opened_at.tzinfo is None or opened_at.utcoffset() is None
                or closed_at.tzinfo is None or closed_at.utcoffset() is None):
            raise TaskError("self_review_evidence_changed", "stored self-review window is invalid")
        if opened_at > closed_at or closed_at > at:
            raise TaskError("self_review_evidence_changed", "self-review window is not yet complete")
        try:
            self.evidence.resolve_handles(handles, opened_at, closed_at, context, at)
        except TaskError as error:
            raise TaskError("self_review_evidence_changed", error.reason) from None
        return run, handles

    @outcome
    def list(self, *, operator, context, limit=20, after_id=None):
        if type(limit) is not int or not 1 <= limit <= 50 or (after_id is not None and
                (type(after_id) is not str or not after_id.strip() or len(after_id) > 512)):
            raise TaskError("self_review_query_invalid", "invalid self-review page")
        at = self.management.ledger.now()
        with self.runtime.read_snapshot():
            owner, policy_revision = self.management._authorize(operator, context, at)
            rows = self.runtime.read_all("""SELECT * FROM role_self_review_items
                WHERE owner_key = ? AND scope_key = ? AND state = 'pending'
                  AND (? IS NULL OR item_id > ?) ORDER BY item_id LIMIT ?""",
                (digest(owner), digest(context.scope), after_id, after_id, limit + 1))
            items, expired = [], 0
            for row in rows[:limit]:
                unavailable, expires_at = None, None
                try:
                    self._basis(row, owner, context, at)
                    expires_at = row["expires_at"]
                except TaskError as error:
                    unavailable = error.code
                if expires_at is not None and expires_at <= stamp(at):
                    expired += 1
                items.append({"item_id": row["item_id"], "run_id": row["run_id"],
                    "kind": row["kind"], "observation": row["observation"] if unavailable is None else None,
                    "next_action": row["next_action"] if unavailable is None else None,
                    "confidence": row["confidence"], "expires_at": expires_at,
                    "created_at": row["created_at"], "unavailable_reason": unavailable,
                    "actions": ["accept", "reject"] if unavailable is None else ["reject"],
                    "view_token": self._token(operator, context, row, policy_revision)})
            return {"items": items, "expired_in_page": expired,
                "next_cursor": rows[limit - 1]["item_id"] if len(rows) > limit else None,
                "context_key": context.key, "role_id": owner.persona_id}

    @outcome
    def command(self, *, operator, context, item_id, action, view_token, operation_key):
        if action not in ("accept", "reject"):
            raise TaskError("self_review_command_invalid", "select accept or reject")
        self.management._validate_operation_key(operation_key)
        at = self.management.ledger.now()
        with self.runtime.transaction() as connection:
            owner, policy_revision = self.management._authorize(operator, context, at)
            row = self._row(item_id, owner, context)
            if type(view_token) is not str or view_token != self._token(operator, context, row, policy_revision):
                raise TaskError("self_review_view_stale", "refresh the self-review item before deciding")
            decision_key = digest([operator.subject, context.key, operation_key, item_id, action])
            if row["state"] != "pending":
                if row["state"] == ("accepted" if action == "accept" else "rejected") and row["decision_key"] == decision_key:
                    return {"item_id": item_id, "state": row["state"], "replayed": True}
                raise TaskError("self_review_decided", "self-review item has already been decided")
            if action == "accept":
                self._basis(row, owner, context, at)
                if row["expires_at"] <= stamp(at):
                    raise TaskError("self_review_expired", "this guidance has already expired")
                if row["kind"] == "no_change":
                    raise TaskError("self_review_command_invalid",
                                    "no_change is informational and cannot be accepted as guidance")
            changed = connection.execute("""UPDATE role_self_review_items
                SET state = ?, decided_at = ?, decided_by = ?, decision_key = ?
                WHERE item_id = ? AND owner_key = ? AND scope_key = ? AND state = 'pending'""",
                ("accepted" if action == "accept" else "rejected", stamp(at),
                 operator.subject.subject_id, decision_key,
                 item_id, digest(owner), digest(context.scope)))
            if changed.rowcount != 1:
                raise TaskError("self_review_decided", "self-review item changed during decision")
            self.app.notify()
            return {"item_id": item_id, "state": "accepted" if action == "accept" else "rejected",
                "replayed": False}
