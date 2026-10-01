"""Opaque EvidenceRef handles backed by the original bounded query session."""

from companion_v2.execution.models import digest, stamp

from .models import owner_key, timestamp
from .wire_binding import _TOKEN, _WireIssue, _token


class MemoryWireEvidence:
    def __init__(self, memory):
        self.memory = memory

    @staticmethod
    def _reference(evidence, handle, expires_at):
        source = evidence.source
        if source.expires_at:
            expires_at = min(expires_at, source.expires_at)
        return {
            "id": handle,
            "source_id": source.source_id if len(source.source_id) <= 256 and _TOKEN.fullmatch(source.source_id)
                else "source-" + digest([source.source_id, source.version]),
            "source_type": source.owner if len(source.owner) <= 256 and _TOKEN.fullmatch(source.owner)
                else "companion_v2.source",
            "evidence_kind": evidence.source_kind,
            "observed_at": stamp(source.issued_at),
            "expires_at": stamp(expires_at),
            "source_revision": "source-revision-" + digest(source.version),
        }

    def offer(self, context, session_id, evidence):
        session = self.memory.query._session(context, session_id)
        handle = self.memory.query.offer(context, session_id, evidence)
        return self._reference(evidence, handle, timestamp(session["expires_at"]))

    def resolve(self, context, reference):
        required = {"id", "source_id", "source_type", "evidence_kind", "observed_at", "expires_at"}
        if (type(reference) is not dict or not required.issubset(reference)
                or set(reference) - required - {"source_revision"}):
            raise _WireIssue("invalid_evidence_ref")
        handle = _token(reference["id"], "evidence_id")
        row = self.memory.runtime.read_one("""SELECT s.* FROM memory_handles h
            JOIN memory_sessions s ON s.session_id = h.session_id
            WHERE h.handle = ? AND s.context_key = ? AND s.owner_key = ?""",
            (handle, context.key, owner_key(context)))
        if row is None:
            raise _WireIssue("evidence_unavailable")
        evidence = self.memory.query.resolve(context, row["session_id"], handle)
        expected = self._reference(evidence, handle, timestamp(row["expires_at"]))
        if any(expected[name] != value for name, value in reference.items()):
            raise _WireIssue("evidence_ref_mismatch")
        return evidence
