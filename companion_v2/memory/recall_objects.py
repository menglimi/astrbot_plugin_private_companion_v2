"""Owner object projections and per-hit reads; cached metadata never grants access."""

import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import ScopeKind, SourceRef, VersionRef
from companion_v2.sources.privacy import redact_text
from companion_v2.conversation.reset import batch_current

from . import codec
from .models import AtomRef, Evidence, owner_key, timestamp
from .reflection_inputs import span_key


def conversation_key(context):
    # Match SQLite json_array, including non-ASCII identifiers. The generic
    # record encoder intentionally uses ASCII escapes and is not this key.
    return json.dumps([context.scope.installation_id, context.scope.bot_id,
                       context.role_binding.role.subject_id, context.actor.subject.subject_id],
                      ensure_ascii=False, separators=(",", ":"))


class RecallObjects:
    def __init__(self, query):
        self.query, self.runtime = query, query.runtime

    def feeds(self, context, kind):
        feeds = []
        if kind in ("facts", "all"):
            feeds.append((owner_key(context), "fact"))
        if kind in ("experiences", "all"):
            feeds.append((owner_key(context), "experience"))
        if kind in ("sources", "all"):
            feeds.extend((conversation_key(context), value)
                         for value in ("human", "reply", "native_human", "native_reply"))
        return feeds

    def _forgotten(self, context, reference):
        return self.runtime.read_one("""SELECT 1 FROM memory_guards
            WHERE owner_key = ? AND evidence_key = ? AND reason = 'forgotten' LIMIT 1""",
            (owner_key(context), digest(reference))) is not None

    def source(self, context, kind, identifier, *, authoritative=False):
        if kind in ("native_human", "native_reply"):
            return self._native_source(context, kind, identifier, authoritative=authoritative)
        if kind == "human":
            row = self.runtime.read_one("""SELECT i.batch_id, i.event_json, b.context_json FROM conversation_inputs i
                JOIN conversation_batches b ON b.batch_id = i.batch_id
                WHERE i.event_key = ? AND i.withdrawn = 0""", (identifier,))
            if row is None:
                return None
            event = json.loads(row["event_json"])
            reference, message_time = codec.source(event["source"]), event["received_at"]
            speaker, source_kind = context.actor.subject.subject_id, "human_message"
        else:
            row = self.runtime.read_one("""SELECT h.*, b.context_json, p.text FROM conversation_sent_history h
                JOIN conversation_batches b ON b.batch_id = h.batch_id
                JOIN conversation_parts p ON p.part_id = h.part_id
                WHERE h.part_id = ? AND p.state = 'delivered'""", (identifier,))
            if row is None:
                return None
            from .sent_sources import OWNER
            original = TaskContext.restore(json.loads(row["context_json"]))
            reference = SourceRef("sent:" + identifier, OWNER, original.scope,
                                  VersionRef(identifier, 1), timestamp(row["delivered_at"]))
            message_time = stamp(reference.issued_at)
            speaker, source_kind = context.role_binding.role.subject_id, "bot_message"
        original_context = TaskContext.restore(json.loads(row["context_json"]))
        if (original_context.scope.kind is not ScopeKind.PRIVATE or owner_key(original_context) != owner_key(context)
                or self._forgotten(context, reference)
                or not batch_current(self.runtime, row["batch_id"], original_context.scope)):
            return None
        if authoritative:
            if kind == "reply":
                if self.query.access.sent_sources is None:
                    raise TaskError("memory_source_unavailable", "confirmed reply owner is unavailable")
                self.query.access.sent_sources.materialize(context, reference)
            original = self.query.access.source(context, reference)
            payload, content_hash = original.payload, original.content_hash
        else:
            raw = self.runtime.read_one("""SELECT payload_json, content_hash, state FROM sources
                WHERE source_id = ? AND lineage_id = ? AND source_revision = ?""",
                (reference.source_id, reference.version.lineage_id, reference.version.revision))
            if raw is None:
                if kind != "reply":
                    raise TaskError("memory_source_unavailable", "captured original is unavailable for indexing")
                payload = redact_text(row["text"])
                content_hash = digest(payload)
            else:
                if raw["state"] != "active":
                    raise TaskError("memory_source_unavailable", "captured original was revoked before indexing")
                payload, content_hash = json.loads(raw["payload_json"]), raw["content_hash"]
        return reference, payload, content_hash, message_time, speaker, source_kind

    def _native_source(self, context, kind, identifier, *, authoritative):
        from companion_v2.conversation.native_observations import observation_row, validate_observation

        row = observation_row(self.runtime, identifier)
        if row is None or row["delivery_state"] not in ("input_observed", "send_returned"):
            return None
        if (kind == "native_human") != (row["kind"] == "input"):
            raise TaskError("memory_source_unavailable", "native source feed changed its attribution")
        reference = codec.source(json.loads(row["source_json"]))
        if self._forgotten(context, reference):
            return None
        try:
            speaker, source_kind = validate_observation(self.runtime, row, context, reference)
        except TaskError:
            return None
        if authoritative:
            record = self.query.access.source(context, reference)
            payload, content_hash = record.payload, record.content_hash
        else:
            raw = self.runtime.read_one("""SELECT payload_json, content_hash, state FROM sources
                WHERE source_id = ? AND lineage_id = ? AND source_revision = ?""",
                (reference.source_id, reference.version.lineage_id, reference.version.revision))
            if raw is None or raw["state"] != "active" or raw["content_hash"] != row["content_hash"]:
                raise TaskError("memory_source_unavailable", "native source is unavailable for indexing")
            payload, content_hash = json.loads(raw["payload_json"]), raw["content_hash"]
        return reference, payload, content_hash, row["observed_at"], speaker, source_kind

    @staticmethod
    def span(source, start, identifier):
        reference, payload, content_hash, message_time, speaker, source_kind = source
        end = min(start + 2000, len(payload))
        evidence = Evidence(reference, content_hash, start, end, digest(payload[start:end]), speaker, source_kind)
        # A staged reply's governed hash is established when its source owner
        # first publishes it. The safe text, exact reference and event identity
        # already define a stable cache key; the issued handle uses the real hash.
        document = {"id": "source:" + digest([identifier, reference, start, end, evidence.span_hash, speaker, source_kind]), "kind": "source",
                    "revision": reference.version.revision, "text": payload[start:end]}
        metadata = {"observed_at": stamp(reference.issued_at), "message_time": message_time,
                    "source_id": reference.source_id, "start": start, "reflection_key": span_key(evidence)}
        return document, metadata, {"evidence": evidence, **metadata}

    def project(self, context, namespace, kind, identifier, *, offset=0):
        """Yield chunks from one changed object, without scanning its neighbours."""
        if kind in ("human", "reply", "native_human", "native_reply"):
            source = self.source(context, kind, identifier)
            if source:
                for start in range(offset * 1900, len(source[1]), 1900):
                    document, metadata, _ = self.span(source, start, identifier)
                    yield document, metadata
        elif kind == "fact":
            row = self.runtime.read_one("""SELECT * FROM memory_atoms
                WHERE atom_id = ? AND owner_key = ? AND namespace = ? AND state = 'active'""",
                (identifier, owner_key(context), namespace))
            if row is None or offset:
                return
            record = json.loads(row["record_json"])
            proposal = record["proposal"]
            metadata = {key: proposal[key] for key in ("subject", "retention", "confidence", "valid_from", "valid_to")}
            metadata.update(observed_at=record["observed_at"], scope=json.loads(row["scope_json"]))
            yield {"id": "atom:" + identifier, "kind": "fact", "revision": row["revision"],
                   "text": " ".join((proposal["predicate"], proposal["object"], proposal["representation"], encode(proposal["qualifiers"])))}, metadata
        else:
            row = self.runtime.read_one("""SELECT * FROM memory_views
                WHERE view_id = ? AND owner_key = ? AND kind = 'experience' AND state = 'active'""",
                (identifier, owner_key(context)))
            if row is None or offset:
                return
            value = json.loads(row["document_json"])
            # A forget clears this owner's cache; do not recreate its erased
            # evidence terms through a surviving derived view on the next build.
            for statement in value["statements"]:
                if any(self._forgotten(context, codec.evidence(e).source) for e in statement["evidence"]):
                    return
                for raw in statement["evidence"]:
                    evidence = codec.evidence(raw)
                    if evidence.source.owner == "memory.role_activity_receipt":
                        try:
                            self.query.access.evidence(context, evidence)
                        except TaskError as error:
                            if error.code == "memory_evidence_forgotten":
                                # A life receipt can depend on the original
                                # reading material the participant has forgotten.
                                return
                            # Temporary source/permission loss is rechecked on
                            # each hit; it must not erase the recoverable index.
                for raw in statement["atoms"]:
                    head = self.runtime.read_one("SELECT record_json FROM memory_atoms WHERE atom_id = ? AND owner_key = ?",
                                                 (raw["atom_id"], owner_key(context)))
                    if head is None:
                        raise TaskError("memory_source_unavailable", "experience fact is unavailable for indexing")
                    if json.loads(head["record_json"]).get("forgotten"):
                        return
            reference = codec.source(json.loads(row["source_json"]))
            yield {"id": "experience:" + identifier, "kind": "experience", "revision": row["revision"],
                   "text": " ".join([value["title"], *value["entities"], *(s["text"] for s in value["statements"])])}, {
                       "entities": value["entities"], "observed_at": value["occurred_at"] or stamp(reference.issued_at)}

    def read(self, context, candidate, *, at=None):
        kind, identifier = candidate["producer"], candidate["object_id"]
        if kind == "fact":
            return require(self.query.writer.read(context, AtomRef(identifier, candidate["revision"]), at=at))
        if kind == "experience":
            value = require(self.query.experiences.read(context, identifier, expected_revision=candidate["revision"]))
            return {**value, "observed_at": value["occurred_at"] or value["source"]["issued_at"]}
        source = self.source(context, kind, identifier, authoritative=True)
        if source is None:
            raise TaskError("memory_source_unavailable", "original message is no longer available")
        start = json.loads(candidate["metadata_json"])["start"]
        if type(start) is not int or not 0 <= start < len(source[1]):
            raise TaskError("memory_evidence_changed", "original source span changed")
        document, _, value = self.span(source, start, identifier)
        if (document["id"] != candidate["id"] or document["revision"] != candidate["revision"]
                or digest(document) != candidate["hash"]):
            raise TaskError("memory_evidence_changed", "original source span changed")
        return value

    def visible(self, context, session_id, candidate, value):
        query = self.query
        if candidate["producer"] == "fact":
            visible = {k: v for k, v in value.items() if k not in ("evidence", "source")}
            visible.update(kind="fact", sources=[query.offer(context, session_id, codec.evidence(e)) for e in value["evidence"]])
            return visible
        if candidate["producer"] == "experience":
            visible = {key: value[key] for key in ("view_id", "revision", "title", "entities", "links", "occurred_at")}
            visible.update(kind="experience", statements=[], meaning="derived_summary_not_independent_evidence")
            for statement in value["statements"]:
                evidence = list(statement["evidence"])
                for raw in statement["atoms"]:
                    evidence.extend(require(query.writer.read(context, AtomRef(**raw)))["evidence"])
                handles = [query.offer(context, session_id, codec.evidence(e)) for e in evidence]
                visible["statements"].append({"text": statement["text"], "sources": list(dict.fromkeys(handles))})
            return visible
        evidence = value["evidence"]
        result = {"kind": "source", "handle": query.offer(context, session_id, evidence),
                "message_time": value["message_time"], "start": evidence.start, "end": evidence.end,
                "speaker_id": evidence.speaker_id, "source_kind": evidence.source_kind,
                "excerpt": query.access.evidence(context, evidence)}
        if candidate["producer"] in ("native_human", "native_reply"):
            from companion_v2.conversation.native_observations import observation_row
            row = observation_row(self.runtime, candidate["object_id"])
            if row is not None:
                result["delivery_state"] = row["delivery_state"]
                result["delivery_basis"] = "native_observation_without_platform_delivery_receipt"
        return result
