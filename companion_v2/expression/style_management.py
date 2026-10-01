"""Dashboard review of model-suggested expression-style signals.

Adopting a signal is the only way it can influence later replies, and it is
always reversible: `retire` returns an adopted signal to inactive without
deleting the record or its evidence, so the history of what was once adopted
stays auditable. Rejecting is available even when the sampled writing has since
been withdrawn, so an operator is never left with an undecidable row.
"""

from __future__ import annotations

import json
from datetime import datetime

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.execution.service import outcome

from ..role_work.growth.management import RoleGrowthManagement
from . import style_rotation
from .learning import DIMENSIONS


class ExpressionStyleManagement:
    def __init__(self, app):
        self.app = app
        self.runtime = app.runtime
        self.samples = app.expression_samples
        self.management = RoleGrowthManagement(app.role_growth)

    @staticmethod
    def _token(operator, context, row, policy_revision):
        return digest(["expression-style-decision.v1", operator.subject, operator.binding_id,
            operator.binding_revision, context.key, row["signal_id"], row["run_id"],
            row["state"], policy_revision])

    def _row(self, signal_id, owner, context):
        if (type(signal_id) is not str or not signal_id.strip() or len(signal_id) > 512
                or signal_id != signal_id.strip()):
            raise TaskError("expression_signal_invalid", "select an original style signal")
        row = self.runtime.read_one("""SELECT * FROM expression_style_signals
            WHERE signal_id = ? AND owner_key = ? AND scope_key = ?""",
            (signal_id, digest(owner), digest(context.scope)))
        if row is None:
            raise TaskError("expression_signal_unavailable", "style signal is unavailable in this role")
        return row

    def _run(self, row, owner, context):
        run = self.runtime.read_one("""SELECT * FROM expression_style_runs
            WHERE run_id = ? AND owner_key = ? AND scope_key = ?""",
            (row["run_id"], digest(owner), digest(context.scope)))
        if run is None:
            raise TaskError("expression_signal_unavailable", "style run is unavailable in this role")
        try:
            window = json.loads(run["sample_json"])
            handles = json.loads(row["evidence_json"])
        except (TypeError, ValueError):
            raise TaskError("expression_sample_changed", "stored style samples are invalid") from None
        if (type(window) is not dict or set(window) != {"opened_at", "closed_at", "handles", "characters"}
                or type(handles) is not list or not handles
                or any(type(value) is not str or value not in window["handles"] for value in handles)):
            raise TaskError("expression_sample_changed", "stored style samples are invalid")
        return run, window, handles

    def _window(self, window, at):
        try:
            opened_at = datetime.fromisoformat(window["opened_at"])
            closed_at = datetime.fromisoformat(window["closed_at"])
        except (TypeError, ValueError):
            raise TaskError("expression_sample_changed", "stored style window is invalid") from None
        if (opened_at.tzinfo is None or opened_at.utcoffset() is None
                or closed_at.tzinfo is None or closed_at.utcoffset() is None):
            raise TaskError("expression_sample_changed", "stored style window is invalid")
        if opened_at > closed_at or closed_at > at:
            raise TaskError("expression_sample_changed", "style window is not yet complete")
        return opened_at, closed_at

    def _basis(self, row, owner, context, at):
        """Recheck only the samples this signal cites."""
        _, window, handles = self._run(row, owner, context)
        opened_at, closed_at = self._window(window, at)
        try:
            self.samples.resolve_handles(handles, opened_at, closed_at, context, at)
        except TaskError as error:
            raise TaskError("expression_sample_changed", error.reason) from None
        return handles

    @outcome
    def list(self, *, operator, context, state="pending", dimension=None, limit=20, after_id=None):
        if state not in ("pending", "adopted", "rejected", "retired"):
            raise TaskError("expression_query_invalid", "unknown style signal state")
        if dimension is not None and dimension not in DIMENSIONS:
            raise TaskError("expression_query_invalid", "unknown style dimension")
        if type(limit) is not int or not 1 <= limit <= 50 or (after_id is not None and
                (type(after_id) is not str or not after_id.strip() or len(after_id) > 512)):
            raise TaskError("expression_query_invalid", "invalid style page")
        at = self.management.ledger.now()
        with self.runtime.read_snapshot():
            owner, policy_revision = self.management._authorize(operator, context, at)
            rows = self.runtime.read_all("""SELECT * FROM expression_style_signals
                WHERE owner_key = ? AND scope_key = ? AND state = ?
                  AND (? IS NULL OR dimension = ?)
                  AND (? IS NULL OR signal_id > ?) ORDER BY signal_id LIMIT ?""",
                (digest(owner), digest(context.scope), state, dimension, dimension,
                 after_id, after_id, limit + 1))
            items = []
            # Adopted rules rotate by how recently they were injected, so the
            # review view reports that ledger: a rule used on every turn while
            # others wait is exactly the distribution this page has to show.
            usage_map = style_rotation.usage(self.runtime, digest(owner), digest(context.scope)) \
                if state == "adopted" else {}
            for row in rows[:limit]:
                unavailable = None
                if state in ("pending", "adopted"):
                    try:
                        self._basis(row, owner, context, at)
                    except TaskError as error:
                        unavailable = error.code
                actions = ["reject"]
                if unavailable is None:
                    actions.append("adopt")
                if state == "adopted":
                    actions.append("retire")
                injections, last = usage_map.get(row["signal_id"], (0, None))
                items.append({"signal_id": row["signal_id"], "run_id": row["run_id"],
                    "dimension": row["dimension"],
                    "observation": row["observation"] if unavailable is None else None,
                    "proposal": row["proposal"] if unavailable is None else None,
                    "confidence": row["confidence"], "state": row["state"],
                    "created_at": row["created_at"], "decided_at": row["decided_at"],
                    "injections": injections,
                    "last_injected_at": last.isoformat() if last is not None else None,
                    "unavailable_reason": unavailable, "actions": actions,
                    "view_token": self._token(operator, context, row, policy_revision)})
            return {"items": items, "state": state,
                "next_cursor": rows[limit - 1]["signal_id"] if len(rows) > limit else None,
                "context_key": context.key, "role_id": owner.persona_id}

    @outcome
    def command(self, *, operator, context, signal_id, action, view_token, operation_key):
        if action not in ("adopt", "reject", "retire"):
            raise TaskError("expression_command_invalid", "select adopt, reject or retire")
        self.management._validate_operation_key(operation_key)
        at = self.management.ledger.now()
        with self.runtime.transaction() as connection:
            owner, policy_revision = self.management._authorize(operator, context, at)
            row = self._row(signal_id, owner, context)
            if type(view_token) is not str or view_token != self._token(operator, context, row, policy_revision):
                raise TaskError("expression_view_stale", "refresh the style signal before deciding")
            decision_key = digest([operator.subject, context.key, operation_key, signal_id, action])
            if row["decision_key"] == decision_key and row["state"] == self._target(action):
                return {"signal_id": signal_id, "state": row["state"], "replayed": True}
            if row["state"] != "pending" and action in ("adopt", "reject"):
                raise TaskError("expression_decided", "style signal has already been decided")
            if action == "retire" and row["state"] != "adopted":
                raise TaskError("expression_command_invalid", "only an adopted signal can be retired")
            if action == "adopt":
                self._basis(row, owner, context, at)
            changed = connection.execute("""UPDATE expression_style_signals
                SET state = ?, decided_at = ?, decided_by = ?, decision_key = ?
                WHERE signal_id = ? AND owner_key = ? AND scope_key = ? AND state = ?""",
                (self._target(action), stamp(at), operator.subject.subject_id, decision_key,
                 signal_id, digest(owner), digest(context.scope), row["state"]))
            if changed.rowcount != 1:
                raise TaskError("expression_decided", "style signal changed during decision")
            self.app.notify()
            return {"signal_id": signal_id, "state": self._target(action), "replayed": False}

    @staticmethod
    def _target(action):
        return {"adopt": "adopted", "reject": "rejected", "retire": "retired"}[action]
