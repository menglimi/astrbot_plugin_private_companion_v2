"""Dashboard review of model-suggested growth progress."""

from __future__ import annotations

import json

from companion_v2.execution.models import TaskError, digest, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ReferenceValidationError

from .management import RoleGrowthManagement
from .models import GrowthState
from .progress import receipt_fingerprint


class GrowthProgressManagement:
    def __init__(self, app):
        self.app = app
        self.ledger = app.role_growth
        self.runtime = self.ledger.runtime
        self.growth = RoleGrowthManagement(self.ledger)
        self.receipts = app.growth_progress.receipts

    @staticmethod
    def _token(operator, context, row, policy_revision):
        return digest(["growth-progress-review.v1", operator.subject, operator.binding_id,
            operator.binding_revision, context.key, row["review_id"], row["base_revision"],
            row["source_json"], policy_revision])

    def _row(self, review_id, owner, context):
        if (type(review_id) is not str or not review_id.strip() or len(review_id) > 512
                or review_id != review_id.strip()):
            raise TaskError("growth_progress_review_invalid", "select an original progress review")
        row = self.runtime.read_one("""SELECT * FROM role_growth_progress_reviews
            WHERE review_id = ? AND owner_key = ? AND scope_key = ?""",
            (review_id, digest(owner), digest(context.scope)))
        if row is None:
            raise TaskError("growth_progress_review_unavailable", "progress review is unavailable in this role")
        return row

    def _basis(self, row, owner, context, at):
        try:
            source = json.loads(row["source_json"])
            if (type(source) is not dict or set(source) != {"stream", "operation_id", "receipt_hash"}
                    or source["operation_id"] != row["receipt_operation_id"]
                    or type(source["receipt_hash"]) is not str):
                raise ValueError("invalid stored receipt identity")
            experience = self.receipts.read(context, source["stream"], source["operation_id"], at)
            if experience is None or receipt_fingerprint(experience) != source["receipt_hash"]:
                raise TaskError("growth_progress_receipt_changed", "completed receipt changed or was withdrawn")
            record = self.growth._record(row["growth_id"], owner, context)
            if (record.revision != row["base_revision"] or record.state not in
                    (GrowthState.ACTIVE, GrowthState.PAUSED) or record.created_at > experience.occurred_at):
                raise TaskError("growth_revision_conflict", "growth target changed after the suggestion")
            unavailable = self.growth._unavailable(record, context, at)
            if unavailable:
                raise TaskError(unavailable, "original growth evidence is no longer available")
            for item in experience.sources:
                if item.scope != context.scope:
                    raise TaskError("source_scope_mismatch", "receipt evidence belongs to another private scope")
                require(self.growth.sources.validate_reference_for_audience(
                    item, recipient=context.actor.subject, observed_at=at))
            return source, experience, record
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise TaskError("growth_progress_receipt_changed", "stored receipt identity is invalid") from error

    @outcome
    def list(self, *, operator, context, limit=20, after_id=None):
        if type(limit) is not int or not 1 <= limit <= 50 or (after_id is not None and
                (type(after_id) is not str or not after_id.strip() or len(after_id) > 512)):
            raise TaskError("growth_progress_query_invalid", "invalid review page")
        at = self.ledger.now()
        with self.runtime.read_snapshot():
            owner, policy_revision = self.growth._authorize(operator, context, at)
            rows = self.runtime.read_all("""SELECT * FROM role_growth_progress_reviews
                WHERE owner_key = ? AND scope_key = ? AND state = 'pending'
                  AND (? IS NULL OR review_id > ?) ORDER BY review_id LIMIT ?""",
                (digest(owner), digest(context.scope), after_id, after_id, limit + 1))
            items = []
            for row in rows[:limit]:
                unavailable, evidence = None, []
                try:
                    source, experience, record = self._basis(row, owner, context, at)
                    evidence = [value[:2000] for value in (experience.title, *experience.statements)[:8]]
                except TaskError as error:
                    unavailable = error.code
                    source = None
                    record = None
                items.append({"review_id": row["review_id"], "growth_id": row["growth_id"],
                    "base_revision": row["base_revision"], "growth_title": record.title if record else None,
                    "progress_note": row["progress_note"] if unavailable is None else None,
                    "evidence": evidence if unavailable is None else [],
                    "receipt_stream": source["stream"] if source else None,
                    "created_at": row["created_at"], "unavailable_reason": unavailable,
                    "actions": ["accept", "reject"] if unavailable is None else ["reject"],
                    "view_token": self._token(operator, context, row, policy_revision)})
            return {"items": items, "next_cursor": rows[limit - 1]["review_id"] if len(rows) > limit else None,
                "context_key": context.key, "role_id": owner.persona_id}

    @outcome
    def command(self, *, operator, context, review_id, action, expected_revision,
                view_token, operation_key):
        if action not in ("accept", "reject") or type(expected_revision) is not int or expected_revision < 1:
            raise TaskError("growth_progress_command_invalid", "select accept or reject and its base revision")
        self.growth._validate_operation_key(operation_key)
        at = self.ledger.now()
        with self.runtime.transaction() as connection:
            owner, policy_revision = self.growth._authorize(operator, context, at)
            row = self._row(review_id, owner, context)
            if (row["base_revision"] != expected_revision or type(view_token) is not str
                    or view_token != self._token(operator, context, row, policy_revision)):
                raise TaskError("growth_view_stale", "refresh the progress review before deciding")
            decision_key = digest([operator.subject, context.key, operation_key, review_id, action])
            if row["state"] != "pending":
                if (row["state"] == "accepted" if action == "accept" else row["state"] == "rejected") and row["decision_key"] == decision_key:
                    return {"review_id": review_id, "state": row["state"],
                        "applied_revision": row["applied_revision"], "replayed": True}
                raise TaskError("growth_progress_decided", "progress review has already been decided")
            applied_revision = None
            if action == "accept":
                _, experience, record = self._basis(row, owner, context, at)
                operation_id = "growth-progress-accept:" + digest([review_id, decision_key])
                try:
                    updated = self.ledger.apply_progress(row["growth_id"], owner=owner,
                        scope=context.scope, expected_revision=record.revision,
                        operation_id=operation_id, progress_note=row["progress_note"],
                        sources=experience.sources, actor=operator.subject, observed_at=at)
                except ReferenceValidationError:
                    raise TaskError("growth_revision_conflict", "growth target changed during review") from None
                applied_revision = updated.revision
            changed = connection.execute("""UPDATE role_growth_progress_reviews
                SET state = ?, decided_at = ?, decided_by = ?, decision_key = ?, applied_revision = ?
                WHERE review_id = ? AND owner_key = ? AND scope_key = ? AND state = 'pending'""",
                ("accepted" if action == "accept" else "rejected", stamp(at),
                 operator.subject.subject_id, decision_key, applied_revision,
                 review_id, digest(owner), digest(context.scope)))
            if changed.rowcount != 1:
                raise TaskError("growth_progress_decided", "progress review changed during decision")
            self.app.notify()
            return {"review_id": review_id, "state": "accepted" if action == "accept" else "rejected",
                "applied_revision": applied_revision, "replayed": False}
