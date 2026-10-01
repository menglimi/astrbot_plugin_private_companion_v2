"""Authorized, source-governed reads of confirmed role growth records."""

from __future__ import annotations

from dataclasses import dataclass
import json

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import RoleOwnerRef, ScopeKind, SubjectKind
from companion_v2.sources.repositories import SourceRepository

from .models import GrowthState, ReferenceValidationError


READ_ACTION = "role.growth.read"
SCAN_LIMIT = 32
# How many earlier progress notes may accompany a skill. The history exists to show
# qualitative development, not to replay the whole ledger.
HISTORY_NOTES = 4


@dataclass(frozen=True)
class GrowthMaterial:
    reference: dict
    purpose: str
    payload: str


@dataclass(frozen=True)
class GrowthCandidates:
    items: tuple[GrowthMaterial, ...]
    truncated: bool
    skipped: int


class RoleGrowthContextReader:
    """Read one role's records only for the current, exact private participant."""

    def __init__(self, ledger, tasks, *, sources=None):
        if ledger.runtime is not tasks.runtime or (sources is not None and sources._runtime is not tasks.runtime):
            raise ValueError("growth context must share its ledger, source owner and task runtime")
        self.ledger, self.tasks = ledger, tasks
        self.runtime = tasks.runtime
        self.sources = sources or SourceRepository(self.runtime)

    @staticmethod
    def owner(context):
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def _authorize(self, context, at):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)
                or context.actor.subject.kind is not SubjectKind.HUMAN):
            raise TaskError("growth_context_private_audience_required",
                            "growth context needs the current participant's exact private audience")
        require(self.tasks.authorize_context(context, action=READ_ACTION, observed_at=at))

    def _verify(self, record, context, at):
        """Every availability rule that applies to a record, for any revision."""
        if (record.owner != self.owner(context) or record.scope != context.scope
                or record.state not in (GrowthState.ACTIVE, GrowthState.PAUSED)
                or record.updated_at > at):
            raise TaskError("growth_context_changed", "growth record is no longer available in its original scope")
        for source in record.sources:
            if source.scope != context.scope:
                raise TaskError("growth_context_scope", "growth evidence belongs to another private conversation")
            require(self.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))

    def _history(self, record, context, at):
        """Earlier progress notes whose evidence is *still* valid for this audience.

        ``ledger.revisions`` reads stored revisions without granting read authority,
        so each one is put through the same verification as the current record. A
        note whose original evidence has since been withdrawn is dropped rather than
        replayed — the reader must not learn more from history than from the record.
        """
        try:
            revisions = self.ledger.revisions(record.growth_id, owner=self.owner(context))
        except (KeyError, ReferenceValidationError):
            return ()
        notes = []
        for revision in revisions:
            if revision.revision >= record.revision or not revision.progress_note:
                continue
            try:
                self._verify(revision, context, at)
            except TaskError:
                continue
            notes.append({"revision": revision.revision, "progress_note": revision.progress_note,
                          "recorded_at": revision.updated_at.isoformat()})
        return tuple(notes[-HISTORY_NOTES:])

    def _record(self, reference, context, at):
        if (type(reference) is not dict or set(reference) != {"growth_id", "revision"}
                or type(reference["growth_id"]) is not str or not reference["growth_id"].strip()
                or len(reference["growth_id"]) > 512 or type(reference["revision"]) is not int
                or reference["revision"] < 1):
            raise TaskError("growth_context_reference_invalid", "growth reference is invalid")
        try:
            record = self.ledger.record(reference["growth_id"], owner=self.owner(context))
        except KeyError:
            raise TaskError("growth_context_unavailable", "original growth record is unavailable") from None
        if record.revision != reference["revision"]:
            raise TaskError("growth_context_changed", "original growth record changed")
        self._verify(record, context, at)
        payload = json.dumps({
            "basis": "confirmed_subjective_role_growth",
            "kind": record.kind.value,
            "state": record.state.value,
            "title": record.title,
            "description": record.description,
            "progress_note": record.progress_note,
            "progress_history": self._history(record, context, at),
            "updated_at": record.updated_at.isoformat(),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        purpose = "role_growth_" + record.kind.value
        return GrowthMaterial(reference, purpose, payload)

    def candidates(self, context, at):
        with self.runtime.read_snapshot():
            self._authorize(context, at)
            owner = self.owner(context)
            active = self.ledger.for_role(owner, scope=context.scope, state=GrowthState.ACTIVE, limit=SCAN_LIMIT)
            paused = self.ledger.for_role(owner, scope=context.scope, state=GrowthState.PAUSED, limit=SCAN_LIMIT)
            # Most recently developed first, then active before paused, then by id so
            # the order is total. Ordering by id alone could spend a limited context
            # budget on whichever record happened to sort first.
            records = sorted((*active, *paused),
                             key=lambda item: (item.state is not GrowthState.ACTIVE,
                                               -item.updated_at.timestamp(), item.growth_id))
            truncated = len(active) == SCAN_LIMIT or len(paused) == SCAN_LIMIT
            items, skipped = [], 0
            for record in records:
                reference = {"growth_id": record.growth_id, "revision": record.revision}
                try:
                    items.append(self._record(reference, context, at))
                except TaskError:
                    skipped += 1
            return GrowthCandidates(tuple(items), truncated, skipped)

    def read(self, references, context, at):
        """Reconstruct exactly the sealed records after rechecking grants and sources."""
        with self.runtime.read_snapshot():
            self._authorize(context, at)
            return tuple(self._record(reference, context, at) for reference in references)
