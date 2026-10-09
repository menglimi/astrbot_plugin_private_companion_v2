"""Decisions on source-bound writing samples; never stores conversation text."""

from __future__ import annotations

import json

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.foundation.refs import RoleOwnerRef


PREFIX = "expression.sample_review.v1:"


class ExpressionSampleReviewStore:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def key(context, handle):
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        return PREFIX + digest([owner, context.scope]) + ":" + digest(handle)

    def read(self, context, handle):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                    (self.key(context, handle),))
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
            if (value["handle"] != handle or value["state"] not in ("pending", "approved", "rejected")
                    or type(value["revision"]) is not int or value["revision"] < 1):
                raise ValueError
            return value
        except (ValueError, TypeError, KeyError):
            raise TaskError("expression_sample_review_invalid", "stored sample decision is invalid") from None

    def observe(self, context, sample, at):
        value = self.read(context, sample.handle)
        content_hash = sample.content_hash or digest(sample.text)
        if value is not None and value["content_hash"] == content_hash:
            return value
        value = {"handle": sample.handle, "content_hash": content_hash, "state": "pending",
                 "revision": value["revision"] + 1 if value else 1, "seen_at": stamp(at),
                 "decided_at": None, "decided_by": None, "decision_key": None}
        self.write(context, value)
        return value

    def write(self, context, value):
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (self.key(context, value["handle"]), encode(value)))

    def eligible(self, context, sample, *, review_enabled):
        value = self.read(context, sample.handle)
        if value is None:
            return not review_enabled
        if value["content_hash"] != (sample.content_hash or digest(sample.text)):
            return not review_enabled and value["state"] != "rejected"
        return value["state"] == "approved" or not review_enabled and value["state"] == "pending"

    def allows_handles(self, context, handles):
        """Revoked samples also retire their influence without deleting audit history."""
        return all((value := self.read(context, handle)) is None or value["state"] != "rejected"
                   for handle in handles)
