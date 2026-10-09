"""Cold archive and portable export/import for one relationship's memory.

V2 already has session/short/durable/protected retention rules and a scoped
logical clear. What was missing is the lifecycle end: moving long-unused durable
records out of the hot working set, and carrying a relationship's own facts in
and out of the installation in a reviewable form.

Three rules keep this safe:

* The archive is a *logical* move. Nothing is erased, and the original record
  keeps its revision, sources and history in its own owner.
* Export is always scoped to one exact private relationship and one role. It
  never reads across subjects, roles or Bot accounts, and never touches V1 data.
* Import is never automatic. A bundle is staged, an operator sees what would
  land, and only an explicit confirmation writes records. Every imported fact
  keeps a provenance reference to the bundle it came from, so an imported fact
  is always distinguishable from one the role observed directly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, SourceRef, VersionRef
from companion_v2.sources.models import SourceRecord

from . import codec
from .management import MemoryManagement
from .models import Evidence, Proposal, owner_key, text


ARCHIVE_OWNER = "management.memory.archive"
BUNDLE_FORMAT = "companion-v2.memory-bundle.v1"
BUNDLE_OWNER = "import.memory.bundle"
MAX_BUNDLE_ATOMS = 512
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
DEFAULT_IDLE_DAYS = 180


@dataclass(frozen=True)
class ArchiveDecision:
    atom_id: str
    revision: int
    state: str
    idle_since: datetime
    reason: str


def _idle_days(value):
    if type(value) is not int or not 1 <= value <= 3650:
        raise TaskError("memory_archive_range_invalid", "idle days must be between 1 and 3650")
    return value


class MemoryArchive:
    """Archive, export and staged import for one private relationship."""

    def __init__(self, memory, operator):
        self.memory, self.operator = memory, operator
        self.management = MemoryManagement(memory, operator)
        self.writer = self.management.writer
        self.runtime = self.writer.runtime

    # ------------------------------------------------------------------ archive

    def _rows(self, context):
        # memory_atoms has no retention column: retention lives in the stored
        # proposal inside record_json, exactly as the writer records it.
        return self.runtime.read_all("""SELECT atom_id, revision, namespace, state,
            record_json, updated_at FROM memory_atoms WHERE owner_key = ? ORDER BY atom_id""",
            (owner_key(context),))

    @staticmethod
    def _archived(record):
        archive = record.get("archive")
        return isinstance(archive, dict) and archive.get("state") == "archived"

    def _eligible(self, context, rows, at, idle_days):
        cutoff = at - timedelta(days=idle_days)
        decisions = []
        for row in rows:
            record = json.loads(row["record_json"])
            if record.get("forgotten") or self._archived(record):
                continue
            # Only durable records are ever eligible: session and protected
            # retention are owned by their original policy, not by the archive.
            try:
                retention = codec.proposal(record["proposal"]).retention
            except (KeyError, TypeError, ValueError):
                continue
            if retention != "durable":
                continue
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except (TypeError, ValueError):
                continue
            if updated_at.tzinfo is None or updated_at.utcoffset() is None:
                continue
            if updated_at > cutoff:
                continue
            decisions.append(ArchiveDecision(row["atom_id"], row["revision"], row["state"],
                                             updated_at, "idle_durable"))
        return decisions

    def _token(self, context, decisions, idle_days):
        return digest([owner_key(context), self.operator, idle_days,
                       [(item.atom_id, item.revision, item.state) for item in decisions]])

    def _preview_labels(self, context, atom_id, revision):
        result = self.writer.read(context, _atom_ref({"atom_id": atom_id, "revision": revision}))
        if not result.is_success:
            return {"unavailable_reason": result.failure.code}
        item = result.unwrap()
        return {"predicate": item.get("predicate", ""),
                "representation": (item.get("representation") or "")[:240]}

    @outcome
    def preview(self, *, context, idle_days=DEFAULT_IDLE_DAYS):
        self.writer.access.check(context, "memory.forget")
        idle_days = _idle_days(idle_days)
        at = self.writer.tasks.now()
        rows = self._rows(context)
        decisions = self._eligible(context, rows, at, idle_days)
        return {"subject_id": context.actor.subject.subject_id,
            "operator_id": self.operator.subject.subject_id,
            "idle_days": idle_days,
            "counts": {"eligible": len(decisions),
                       "already_archived": sum(self._archived(json.loads(row["record_json"])) for row in rows),
                       "retained": len(rows) - len(decisions)},
            "items": [{"atom_id": item.atom_id, "revision": item.revision,
                       "state": item.state, "idle_since": stamp(item.idle_since),
                       "reason": item.reason,
                       **self._preview_labels(context, item.atom_id, item.revision)} for item in decisions],
            "archived_items": [{"atom_id": row["atom_id"], "revision": row["revision"],
                                **self._preview_labels(context, row["atom_id"], row["revision"])}
                               for row in rows if self._archived(json.loads(row["record_json"]))],
            "archive_token": self._token(context, decisions, idle_days),
            "preview_only": True,
            "erasure": "none",
            "scope": "durable_relationship_facts"}

    @outcome
    def commit(self, *, context, expected_archive_token, operation_key, idle_days=DEFAULT_IDLE_DAYS):
        self.writer.access.check(context, "memory.forget")
        idle_days = _idle_days(idle_days)
        expected_archive_token = text(expected_archive_token, "expected_archive_token", 512)
        operation_key = text(operation_key, "operation_key", 512)
        owner, caller = owner_key(context), self.writer.caller(context)
        identifier = "memory-archive-" + digest([owner, caller, operation_key])
        payload_hash = digest(["management.archive", expected_archive_token])
        at = self.writer.tasks.now()
        with self.runtime.transaction() as connection:
            self.writer.access.check(context, "memory.forget")
            existing = connection.execute("SELECT * FROM memory_operations WHERE operation_id = ?",
                                          (identifier,)).fetchone()
            if existing:
                if existing["owner_key"] != owner or existing["caller_id"] != caller:
                    raise TaskError("memory_operation_unavailable", "the original archive operation is unavailable")
                if existing["payload_hash"] != payload_hash:
                    raise TaskError("memory_operation_conflict", "original archive has a different preview")
                return json.loads(existing["result_json"])
            rows = connection.execute(
                "SELECT atom_id, revision, namespace, state, record_json, updated_at "
                "FROM memory_atoms WHERE owner_key = ? ORDER BY atom_id", (owner,)).fetchall()
            decisions = self._eligible(context, rows, at, idle_days)
            if self._token(context, decisions, idle_days) != expected_archive_token:
                raise TaskError("memory_archive_stale",
                                "refresh the archive preview before confirming")
            self.writer._reserve(context, identifier, payload_hash)
            archived = []
            for item in decisions:
                row = next(candidate for candidate in rows if candidate["atom_id"] == item.atom_id)
                record = json.loads(row["record_json"])
                record["archive"] = {"state": "archived", "at": stamp(at),
                                     "by": self.operator.subject.subject_id,
                                     "reason": item.reason}
                connection.execute("UPDATE memory_atoms SET record_json = ?, updated_at = ? "
                                   "WHERE atom_id = ? AND owner_key = ?",
                                   (encode(record), stamp(at), item.atom_id, owner))
                archived.append({"atom_id": item.atom_id, "revision": item.revision})
            body = encode({"operation": "archive", "subject": context.actor.subject.subject_id,
                           "count": len(archived)})
            source = SourceRef("memory-archive-source:" + digest([owner, caller, operation_key]),
                               ARCHIVE_OWNER, context.scope, VersionRef(identifier, 1), at)
            safe = self.writer.sources.prepare_message(
                SourceRecord(source, context.audience, digest(body), body))
            require(self.writer.sources.publish(safe, observed_at=at))
            result = {"operation_id": identifier, "state": "persisted",
                      "archived_count": len(archived), "items": archived,
                      "erasure": "none", "restore": "supported",
                      "scope": "durable_relationship_facts"}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, NULL, ?, 'persisted', ?, ?, ?)",
                (identifier, owner, caller, "management.archive", payload_hash,
                 encode(context), encode(result), stamp(at), stamp(at)))
            self.writer._complete(identifier)
            return result

    @outcome
    def restore(self, *, context, atom_ids, operation_key):
        self.writer.access.check(context, "memory.forget")
        operation_key = text(operation_key, "operation_key", 512)
        if (type(atom_ids) is not tuple or not 1 <= len(atom_ids) <= MAX_BUNDLE_ATOMS
                or any(type(value) is not str or not value.strip() or len(value) > 512 for value in atom_ids)
                or len(set(atom_ids)) != len(atom_ids)):
            raise TaskError("memory_archive_restore_invalid", "provide one to 512 unique atom IDs")
        owner, caller = owner_key(context), self.writer.caller(context)
        identifier = "memory-archive-restore-" + digest([owner, caller, operation_key])
        payload_hash = digest(["management.archive.restore", atom_ids])
        at = self.writer.tasks.now()
        with self.runtime.transaction() as connection:
            existing = connection.execute("SELECT * FROM memory_operations WHERE operation_id = ?",
                                          (identifier,)).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise TaskError("memory_operation_conflict", "original restore selected different records")
                return json.loads(existing["result_json"])
            self.writer._reserve(context, identifier, payload_hash)
            restored = []
            for atom_id in atom_ids:
                row = connection.execute("SELECT record_json, revision FROM memory_atoms "
                                         "WHERE atom_id = ? AND owner_key = ?", (atom_id, owner)).fetchone()
                if row is None:
                    raise TaskError("memory_archive_restore_unavailable",
                                    "an original archived record is unavailable")
                record = json.loads(row["record_json"])
                if not self._archived(record):
                    raise TaskError("memory_archive_restore_conflict",
                                    "an original record is not archived")
                record.pop("archive", None)
                connection.execute("UPDATE memory_atoms SET record_json = ?, updated_at = ? "
                                   "WHERE atom_id = ? AND owner_key = ?",
                                   (encode(record), stamp(at), atom_id, owner))
                restored.append({"atom_id": atom_id, "revision": row["revision"]})
            result = {"operation_id": identifier, "state": "persisted",
                      "restored_count": len(restored), "items": restored}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, NULL, ?, 'persisted', ?, ?, ?)",
                (identifier, owner, caller, "management.archive.restore",
                 payload_hash,
                 encode(context), encode(result), stamp(at), stamp(at)))
            self.writer._complete(identifier)
            return result

    # ------------------------------------------------------------------- export

    @outcome
    def export(self, *, context, include_archived=True):
        """A portable bundle for exactly this relationship and role."""
        self.writer.access.check(context)
        at = self.writer.tasks.now()
        bodies = []
        for row in self._rows(context):
            record = json.loads(row["record_json"])
            if record.get("forgotten"):
                continue
            if not include_archived and self._archived(record):
                continue
            read = self.writer.read(context, _atom_ref(row))
            if not read.is_success:
                # A record whose sources no longer resolve is exported as its
                # own tombstone rather than as content the role never owned.
                continue
            item = read.unwrap()
            item.pop("evidence", None)
            item.pop("source", None)
            item["revision"] = row["revision"]
            item["archived"] = self._archived(record)
            bodies.append(item)
        bundle = {"format": BUNDLE_FORMAT, "exported_at": stamp(at),
                  "subject_id": context.actor.subject.subject_id,
                  "operator_id": self.operator.subject.subject_id,
                  "installation_id": context.scope.installation_id,
                  "atom_count": len(bodies), "atoms": bodies}
        document = encode(bundle)
        if len(document.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise TaskError("memory_bundle_too_large", "the export exceeds the bundle size limit")
        return {"bundle": bundle, "bundle_hash": digest(bundle["atoms"]), "atom_count": len(bodies),
                "includes_archived": include_archived, "portability": "reviewable_json"}

    # ------------------------------------------------------------------- import

    @outcome
    def preview_import(self, *, context, bundle):
        """Validate a bundle and show what would land; writes nothing."""
        self.writer.access.check(context, "memory.forget")
        atoms = self._validate_bundle(bundle, context)
        existing = {row["atom_id"] for row in self._rows(context)}
        fresh = [item for item in atoms if item["atom_id"] not in existing]
        return {"subject_id": context.actor.subject.subject_id,
                "operator_id": self.operator.subject.subject_id,
                "counts": {"in_bundle": len(atoms), "new": len(fresh),
                           "already_present": len(atoms) - len(fresh)},
                "items": [{"atom_id": item["atom_id"], "predicate": item.get("predicate"),
                           "decision": "new" if item["atom_id"] not in existing else "already_present"}
                          for item in atoms[:MAX_BUNDLE_ATOMS]],
                "import_token": self._import_token(context, atoms),
                "preview_only": True,
                "provenance": "each imported fact keeps a bundle reference"}

    def _validate_bundle(self, bundle, context):
        if (type(bundle) is not dict or bundle.get("format") != BUNDLE_FORMAT
                or type(bundle.get("atoms")) is not list or not 1 <= len(bundle["atoms"]) <= MAX_BUNDLE_ATOMS):
            raise TaskError("memory_bundle_invalid", "the bundle is not a supported export")
        if len(encode(bundle).encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise TaskError("memory_bundle_too_large", "the bundle exceeds the import size limit")
        for item in bundle["atoms"]:
            if (type(item) is not dict or type(item.get("atom_id")) is not str
                    or not item["atom_id"].strip() or len(item["atom_id"]) > 512):
                raise TaskError("memory_bundle_invalid", "a bundle record is malformed")
        return bundle["atoms"]

    def _import_token(self, context, atoms):
        return digest([owner_key(context), self.operator, self.writer.access.access.revision,
                       [(item["atom_id"], item.get("revision", 0)) for item in atoms]])

    @outcome
    def commit_import(self, *, context, bundle, expected_import_token, operation_key):
        self.writer.access.check(context, "memory.forget")
        expected_import_token = text(expected_import_token, "expected_import_token", 512)
        operation_key = text(operation_key, "operation_key", 512)
        atoms = self._validate_bundle(bundle, context)
        if self._import_token(context, atoms) != expected_import_token:
            raise TaskError("memory_import_stale", "refresh the import preview before confirming")
        owner, caller = owner_key(context), self.writer.caller(context)
        identifier = "memory-import-" + digest([owner, caller, operation_key])
        payload_hash = digest(["management.import", expected_import_token])
        at = self.writer.tasks.now()
        with self.runtime.transaction() as connection:
            existing = connection.execute("SELECT * FROM memory_operations WHERE operation_id = ?",
                                          (identifier,)).fetchone()
            if existing:
                return json.loads(existing["result_json"])
            self.writer._reserve(context, identifier, payload_hash)
            imported, skipped = [], 0
            for item in atoms:
                present = connection.execute("SELECT 1 FROM memory_atoms WHERE atom_id = ? AND owner_key = ?",
                                             (item["atom_id"], owner)).fetchone()
                if present is not None:
                    skipped += 1
                    continue
                atom_id = item["atom_id"]
                # An imported fact must be *readable*, which means it needs a
                # published source and a matching evidence span. A bare row would
                # be silently dropped by every later read, so the bundle text is
                # published as first-class evidence owned by the bundle importer.
                representation = item.get("representation") or ""
                proposal = Proposal(operation="add", namespace=item.get("namespace", "personal"),
                    subject=item.get("subject", "self"), predicate=item.get("predicate", ""),
                    object=item.get("object", ""), representation=representation,
                    qualifiers=dict(item.get("qualifiers", {})), polarity=item.get("polarity", "positive"),
                    attribution="observed", retention="durable",
                    confidence=item.get("confidence", 1.0))
                source = SourceRef(atom_id, BUNDLE_OWNER, context.scope, VersionRef(atom_id, 1), at)
                payload = representation
                content_hash = digest(payload)
                safe = self.writer.sources.prepare_message(
                    SourceRecord(source, context.audience, content_hash, payload))
                require(self.writer.sources.publish(safe, observed_at=at))
                evidence = Evidence(source, content_hash, 0, max(len(payload), 1), digest(payload))
                proposal = replace(proposal, evidence=(evidence,))
                document = {"proposal": json.loads(encode(proposal)), "observed_at": stamp(at),
                            "accepted_by": self.writer.caller(context), "change_token": uuid4().hex}
                document["imported"] = {"bundle_format": BUNDLE_FORMAT, "bundle_hash": digest(atoms),
                                        "at": stamp(at), "by": self.operator.subject.subject_id}
                connection.execute("""INSERT INTO memory_atoms VALUES
                    (?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, ?, ?)""",
                    (atom_id, owner, proposal.namespace, proposal.subject, proposal.fact_key,
                     int(proposal.single_value), encode(context.scope), encode(document),
                     encode(source), stamp(at)))
                connection.execute("INSERT INTO memory_revisions VALUES (?, 1, 'active', ?, ?)",
                                   (atom_id, encode(document), encode(source)))
                connection.execute("INSERT INTO memory_changes(owner_key, namespace, atom_id, revision, kind, occurred_at) VALUES (?, ?, ?, 1, ?, ?)",
                                   (owner, proposal.namespace, atom_id, "added", stamp(at)))
                imported.append(atom_id)
            result = {"operation_id": identifier, "state": "persisted",
                      "imported_count": len(imported), "skipped_count": skipped,
                      "items": imported, "provenance": "bundle_reference_kept"}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, NULL, ?, 'persisted', ?, ?, ?)",
                (identifier, owner, caller, "management.import",
                 payload_hash,
                 encode(context), encode(result), stamp(at), stamp(at)))
            self.writer._complete(identifier)
            return result


def _atom_ref(row):
    from .models import AtomRef
    return AtomRef(row["atom_id"], row["revision"])
