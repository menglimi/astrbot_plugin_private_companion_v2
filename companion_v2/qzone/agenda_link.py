"""Pending agenda suggestions carried by a public help request.

A public help post may carry a suggestion for the agenda ("that item is stuck,
here is what I would change"). Publishing records it here as evidence; nothing
in this module writes to the agenda domain, because the agenda change itself
belongs to ``CalendarService`` -- that service owns the evidence checks and the
receipts of its own domain. What this module adds is the missing link: the
suggestion stays queryable, the character is told it is still open, and the
calendar operation that finally closed it is recorded here.

Records live in one ``memory_views`` row each, keyed by the role owner, so the
same post can never create the suggestion twice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import json
from typing import Mapping

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.storage.runtime import StorageRuntime


KIND = "qzone.agenda_proposal.v1"
PENDING = "pending"
APPLIED = "applied"
DISMISSED = "dismissed"
STATES = (PENDING, APPLIED, DISMISSED)
MAX_PENDING = 5
MAX_RECENT = 20


@dataclass(frozen=True)
class AgendaSuggestion:
    """One suggestion, its evidence, and how it was closed (if it was)."""

    suggestion_id: str
    owner_key: str
    operation_id: str
    agenda_id: str
    expected_revision: int
    intent: str
    source_refs: tuple = ()
    topic: str = ""
    scene: str = ""
    created_at: str = ""
    state: str = PENDING
    resolved_at: str = ""
    calendar_operation_id: str = ""
    result_refs: tuple = ()

    @classmethod
    def restore(cls, value: Mapping) -> AgendaSuggestion:
        if not isinstance(value, Mapping):
            raise ValueError("suggestion document must be an object")
        return cls(str(value.get("suggestion_id") or ""), str(value.get("owner_key") or ""),
                   str(value.get("operation_id") or ""), str(value.get("agenda_id") or ""),
                   int(value.get("expected_revision") or 0), str(value.get("intent") or ""),
                   tuple(str(item) for item in (value.get("source_refs") or ())),
                   str(value.get("topic") or ""), str(value.get("scene") or ""),
                   str(value.get("created_at") or ""), str(value.get("state") or PENDING),
                   str(value.get("resolved_at") or ""), str(value.get("calendar_operation_id") or ""),
                   tuple(str(item) for item in (value.get("result_refs") or ())))

    def document(self):
        return asdict(self)

    def summary(self):
        """The bounded view the model and the page both read."""
        return {"suggestion_id": self.suggestion_id, "agenda_id": self.agenda_id,
                "expected_revision": self.expected_revision, "intent": self.intent,
                "state": self.state, "created_at": self.created_at,
                "calendar_operation_id": self.calendar_operation_id,
                "source_refs": list(self.source_refs)}


class SuggestionStore:
    UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
        ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision,
            document_json = excluded.document_json, updated_at = excluded.updated_at"""

    def __init__(self, runtime: StorageRuntime):
        self.runtime = runtime

    @staticmethod
    def suggestion_id(owner_key, operation_id, agenda_id):
        return digest(["qzone-agenda", owner_key, operation_id, agenda_id])[:32]

    def _view_id(self, suggestion_id):
        return "qzone-agenda:" + suggestion_id

    def record(self, *, owner_key, operation_id, agenda_id, expected_revision, intent, source_refs=(),
               topic="", scene="", at) -> AgendaSuggestion:
        """Record once per (owner, operation, agenda item); a replay keeps the first."""
        suggestion_id = self.suggestion_id(owner_key, operation_id, agenda_id)
        existing = self.read(owner_key, suggestion_id)
        if existing is not None:
            return existing
        suggestion = AgendaSuggestion(suggestion_id=suggestion_id, owner_key=owner_key,
            operation_id=str(operation_id), agenda_id=str(agenda_id),
            expected_revision=int(expected_revision), intent=str(intent),
            source_refs=tuple(source_refs), topic=str(topic), scene=str(scene), created_at=stamp(at))
        self._write(owner_key, suggestion, at=at)
        return suggestion

    def read(self, owner_key, suggestion_id):
        row = self.runtime.read_one("SELECT document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                    (self._view_id(suggestion_id), KIND))
        if row is None:
            return None
        try:
            suggestion = AgendaSuggestion.restore(json.loads(row["document_json"]))
        except (ValueError, TypeError):
            return None
        return suggestion if suggestion.owner_key == owner_key else None

    def list(self, owner_key, *, limit=MAX_RECENT):
        if type(limit) is not int or limit < 1:
            raise ValueError("suggestion limit must be a positive integer")
        rows = self.runtime.read_all("""SELECT document_json FROM memory_views
            WHERE owner_key = ? AND kind = ? AND state = 'active' ORDER BY updated_at DESC LIMIT ?""",
            (owner_key, KIND, limit))
        result = []
        for row in rows:
            try:
                suggestion = AgendaSuggestion.restore(json.loads(row["document_json"]))
            except (ValueError, TypeError):
                continue
            if suggestion.owner_key == owner_key:
                result.append(suggestion)
        return tuple(result)

    def pending(self, owner_key, *, limit=MAX_PENDING):
        return tuple(item for item in self.list(owner_key, limit=MAX_RECENT) if item.state == PENDING)[:limit]

    def resolve(self, owner_key, suggestion_id, *, state, calendar_operation_id="", result_refs=(), at):
        if state not in (APPLIED, DISMISSED):
            raise TaskError("qzone_suggestion_state_invalid", "建议只能标记为已写回或已忽略")
        current = self.read(owner_key, suggestion_id)
        if current is None:
            raise TaskError("qzone_suggestion_unavailable", "这条日程建议不存在或不属于当前角色")
        if current.state != PENDING:
            return current
        if state == APPLIED and not str(calendar_operation_id or "").strip():
            raise TaskError("qzone_suggestion_receipt_required", "标记已写回时必须带上日历回执编号")
        resolved = replace(current, state=state, resolved_at=stamp(at),
                           calendar_operation_id=str(calendar_operation_id or ""),
                           result_refs=tuple(str(item) for item in result_refs))
        self._write(owner_key, resolved, at=at)
        return resolved

    def material(self, owner_key, *, limit=MAX_PENDING):
        """The open questions, as the model reads them; empty string when none."""
        pending = self.pending(owner_key, limit=limit)
        if not pending:
            return ""
        return json.dumps({"open_agenda_suggestions": [item.summary() for item in pending]},
                          ensure_ascii=False, sort_keys=True)

    def _write(self, owner_key, suggestion, *, at):
        view_id = self._view_id(suggestion.suggestion_id)
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT revision FROM memory_views WHERE view_id = ?",
                                     (view_id,)).fetchone()
            revision = int(row["revision"]) + 1 if row is not None else 1
            connection.execute(self.UPSERT, (view_id, owner_key, KIND, revision,
                json.dumps(suggestion.document(), ensure_ascii=False, sort_keys=True),
                encode({"owner_key": owner_key}), stamp(at)))


__all__ = ["APPLIED", "AgendaSuggestion", "DISMISSED", "KIND", "MAX_PENDING", "MAX_RECENT", "PENDING",
           "STATES", "SuggestionStore"]
