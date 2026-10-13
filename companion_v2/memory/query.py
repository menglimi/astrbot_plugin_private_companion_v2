"""Bounded query sessions with current owner reads and original source spans."""

from datetime import timedelta
import json
import math
import sqlite3

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome

from . import codec
from .models import AtomRef, Evidence, integer, owner_key, text, timestamp
from .search import SearchIndex, index_failure
from .fact_index import FactIndex
from .fact_query import FactQuery
from .experiences import MemoryExperiences
from .recall_objects import RecallObjects
from .recall_index import RecallIndex
from .recall_query import RecallQuery
from .legacy_materials import LegacyMemoryMaterials


class MemoryQuery:
    def __init__(self, writer):
        self.writer, self.runtime, self.tasks = writer, writer.runtime, writer.tasks
        self.policy, self.access = writer.policy, writer.access
        self.index = SearchIndex(self.runtime.data_root)
        self.fact_index = FactIndex(writer, self.index)
        self.facts = FactQuery(self, self.fact_index)
        self.experiences = MemoryExperiences(writer)
        self.objects = RecallObjects(self)
        self.recall_index = RecallIndex(self, self.objects)
        self.recall = RecallQuery(self, self.recall_index, self.objects)
        self.legacy = LegacyMemoryMaterials(writer)

    def begin(self, context, session_id, *, expires_at=None):
        self.access.check(context)
        text(session_id, "session_id", 512)
        expires_at = expires_at or self.tasks.now() + timedelta(minutes=10)
        if expires_at <= self.tasks.now():
            raise TaskError("memory_session_expired", "query session has expired")
        with self.runtime.transaction() as connection:
            old = connection.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if old:
                if old["context_key"] != context.key:
                    raise TaskError("memory_session_mismatch", "query session belongs to another original context")
                if timestamp(old["expires_at"]) <= self.tasks.now():
                    raise TaskError("memory_session_expired", "query session has expired")
            else:
                connection.execute("INSERT INTO memory_sessions VALUES (?, ?, ?, ?, 0, 0, ?)",
                                   (session_id, context.key, owner_key(context), stamp(expires_at), encode({"reads": [], "notes": [], "pages": {}})))
        return session_id

    def _session(self, context, session_id):
        self.access.check(context)
        row = self.runtime.read_one("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,))
        if row is None or row["context_key"] != context.key:
            raise TaskError("memory_session_mismatch", "query session is unavailable")
        if timestamp(row["expires_at"]) <= self.tasks.now():
            raise TaskError("memory_session_expired", "query session has expired")
        return row

    def memory_revision(self, context):
        """Return the current owner-local change sequence under normal read authority."""
        self.access.check(context)
        row = self.runtime.read_one(
            "SELECT COALESCE(MAX(sequence), 0) AS revision FROM memory_changes WHERE owner_key = ?",
            (owner_key(context),),
        )
        return int(row["revision"])

    def _charge(self, context, session_id, result, *, read=None):
        policy = self.access.policy_for(context)
        row = self._session(context, session_id)
        chars = len(encode(result))
        if row["calls"] >= policy.turn_calls or row["chars"] + chars > policy.turn_chars:
            raise TaskError("memory_query_budget_exhausted", "this turn's memory budget is exhausted")
        state = json.loads(row["state_json"])
        if read and read not in state["reads"]:
            state["reads"].append(read)
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE memory_sessions SET calls = calls + 1, chars = chars + ?, state_json = ? WHERE session_id = ?",
                               (chars, encode(state), session_id))
        return result

    def offer(self, context, session_id, evidence):
        self._session(context, session_id)
        self.access.evidence(context, evidence)
        handle = "memory-source-" + digest([session_id, evidence])
        with self.runtime.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO memory_handles VALUES (?, ?, ?, ?)",
                               (handle, session_id, encode(evidence), stamp(self.tasks.now())))
        return handle

    def resolve(self, context, session_id, handle):
        self._session(context, session_id)
        row = self.runtime.read_one("SELECT evidence_json FROM memory_handles WHERE handle = ? AND session_id = ?", (handle, session_id))
        if row is None:
            raise TaskError("memory_source_unavailable", "use an original source handle from this query session")
        evidence = codec.evidence(json.loads(row["evidence_json"]))
        self.access.evidence(context, evidence)
        return evidence

    def _documents(self, context, namespace, kind, *, at_time=None):
        documents, values, unavailable = [], {}, False
        if kind in ("facts", "all"):
            for row in self.runtime.read_all("SELECT * FROM memory_atoms WHERE owner_key = ? AND namespace = ? AND state = 'active' ORDER BY atom_id",
                                            (owner_key(context), namespace)):
                reference = AtomRef(row["atom_id"], row["revision"])
                result = self.writer.read(context, reference, at=at_time)
                if not result.is_success:
                    unavailable = True
                    continue
                item = result.unwrap()
                identifier = "atom:" + reference.atom_id
                document = {"id": identifier, "kind": "fact", "revision": reference.revision,
                    "text": " ".join((item["predicate"], item["object"], item["representation"], encode(item["qualifiers"])))}
                documents.append(document)
                values[identifier] = item
        if kind in ("sources", "all"):
            for row in self.runtime.read_all("""SELECT i.event_json, b.context_json FROM conversation_inputs i
                JOIN conversation_batches b ON b.batch_id = i.batch_id WHERE i.withdrawn = 0
                AND json_extract(b.context_json, '$.actor.subject.subject_id') = ?
                AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
                AND json_extract(b.context_json, '$.role_binding.scope.bot_id') = ? ORDER BY i.event_key""",
                (context.actor.subject.subject_id, context.role_binding.role.subject_id, context.scope.bot_id)):
                event = json.loads(row["event_json"])
                ref = codec.source(event["source"])
                try:
                    original = self.access.source(context, ref)
                except TaskError:
                    unavailable = True
                    continue
                for start in range(0, len(original.payload), 1900):
                    end = min(start + 2000, len(original.payload))
                    evidence = Evidence(ref, original.content_hash, start, end, digest(original.payload[start:end]),
                                        context.actor.subject.subject_id, "human_message")
                    identifier = "source:" + digest(evidence)
                    documents.append({"id": identifier, "kind": "source", "revision": ref.version.revision,
                                      "text": original.payload[evidence.start:evidence.end]})
                    values[identifier] = {"evidence": evidence, "observed_at": stamp(ref.issued_at), "message_time": event["received_at"]}
            if self.access.sent_sources is not None:
                for ref in self.access.sent_sources.rows(context):
                    try:
                        self.access.sent_sources.materialize(context, ref)
                        original = self.access.source(context, ref)
                    except TaskError:
                        unavailable = True
                        continue
                    for start in range(0, len(original.payload), 1900):
                        end = min(start + 2000, len(original.payload))
                        evidence = Evidence(
                            ref, original.content_hash, start, end,
                            digest(original.payload[start:end]),
                            context.role_binding.role.subject_id, "bot_message",
                        )
                        identifier = "source:" + digest(evidence)
                        documents.append({
                            "id": identifier, "kind": "source", "revision": 1,
                            "text": original.payload[start:end],
                        })
                        values[identifier] = {
                            "evidence": evidence,
                            "observed_at": stamp(ref.issued_at),
                            "message_time": stamp(ref.issued_at),
                        }
            from companion_v2.conversation.native_observations import rows_for_context
            for row in rows_for_context(self.runtime, context):
                producer = "native_human" if row["kind"] == "input" else "native_reply"
                try:
                    captured = self.objects.source(context, producer, row["observation_id"], authoritative=True)
                    if captured is None:
                        continue
                    for start in range(0, len(captured[1]), 1900):
                        document, metadata, value = self.objects.span(captured, start, row["observation_id"])
                        documents.append(document)
                        values[document["id"]] = {**value, **metadata, "delivery_state": row["delivery_state"]}
                except TaskError:
                    unavailable = True
        if kind in ("experiences", "all"):
            for row in self.runtime.read_all("SELECT view_id FROM memory_views WHERE owner_key = ? AND kind = 'experience' AND state = 'active' ORDER BY view_id", (owner_key(context),)):
                result = self.experiences.read(context, row["view_id"])
                if not result.is_success:
                    unavailable = True
                    continue
                value = result.unwrap()
                identifier = "experience:" + value["view_id"]
                documents.append({"id": identifier, "kind": "experience", "revision": value["revision"],
                    "text": " ".join([value["title"], *value["entities"], *(s["text"] for s in value["statements"])])})
                values[identifier] = {**value, "observed_at": value["occurred_at"] or value["source"]["issued_at"]}
        return documents, values, unavailable

    @outcome
    def query(self, context, session_id, *, query_intent, namespace="personal", kind="facts", limit=None,
              cursor=None, time_start=None, time_end=None, subjects=(), at_time=None, allowed_retention=(),
              confidence_floor=None, vector=None, model=None, candidate_limit=None):
        policy = self.access.policy_for(context)
        text(query_intent, "query_intent", 2000, empty=True)
        text(namespace, "namespace", 128)
        if cursor is not None:
            text(cursor, "cursor", 512)
        if kind not in ("facts", "sources", "experiences", "all"):
            raise ValueError("query kind must be facts, sources, experiences or all")
        limit = policy.query_items if limit is None else integer(limit, "limit", 1, policy.query_items)
        candidate_items = (self.fact_index if kind == "facts" and vector is None else self.recall_index).candidate_items
        candidate_limit = candidate_items if candidate_limit is None else integer(
            candidate_limit, "candidate_limit", 1, candidate_items)
        start, end, at = timestamp(time_start), timestamp(time_end), timestamp(at_time)
        if start and end and start >= end:
            raise ValueError("invalid time range")
        if not isinstance(subjects, (tuple, list)) or len(subjects) > 32 or any(type(s) is not str for s in subjects):
            raise ValueError("subjects must be a bounded list")
        if (not isinstance(allowed_retention, (tuple, list)) or len(allowed_retention) > 4
                or any(type(value) is not str or value not in ("session", "short", "durable", "protected")
                       for value in allowed_retention)
                or len(set(allowed_retention)) != len(allowed_retention)):
            raise ValueError("allowed_retention must be a unique bounded list of supported values")
        if confidence_floor is not None and (type(confidence_floor) not in (int, float)
                or not math.isfinite(confidence_floor) or not 0 <= confidence_floor <= 1):
            raise ValueError("confidence_floor must be null or a finite number in 0..1")
        with self.runtime.transaction():
            session = self._session(context, session_id)
            if session["calls"] >= policy.turn_calls:
                raise TaskError("memory_query_budget_exhausted", "this turn's memory query budget is exhausted")
            if kind == "facts" and vector is None:
                try:
                    return self.facts.run(context, session_id, session, intent=query_intent,
                        namespace=namespace, limit=limit, cursor=cursor, start=start, end=end,
                        at=at, subjects=subjects, retention=allowed_retention,
                        confidence=confidence_floor, model=model, candidate_limit=candidate_limit)
                except sqlite3.DatabaseError as error:
                    raise index_failure(error) from None
            try:
                return self.recall.run(context, session_id, session, intent=query_intent,
                    namespace=namespace, kind=kind, limit=limit, cursor=cursor, start=start, end=end,
                    at=at, subjects=subjects, retention=allowed_retention, confidence=confidence_floor,
                    vector=vector, model=model, candidate_limit=candidate_limit)
            except sqlite3.DatabaseError as error:
                raise index_failure(error) from None

    @outcome
    def legacy_materials(self, context, session_id, *, query_intent="", material_kind="all", limit=None,
                         cursor=None, time_start=None, time_end=None):
        """Read imported V1 history under this query session's access and budget.

        This result is explicitly historical: it contains no V2 evidence handle
        and cannot be submitted as a source-backed memory mutation.
        """
        policy = self.access.policy_for(context)
        with self.runtime.transaction():
            self._session(context, session_id)
            result = require(self.legacy.query(context, query_intent=query_intent,
                material_kind=material_kind, limit=limit, cursor=cursor,
                time_start=time_start, time_end=time_end))
            result["remaining_calls"] = max(0, policy.turn_calls - self._session(context, session_id)["calls"] - 1)
            return self._charge(context, session_id, result,
                                read={"profile": result["profile"], "count": len(result["items"])})

    @outcome
    def source(self, context, session_id, *, handle, start=None, max_chars=None):
        policy = self.access.policy_for(context)
        with self.runtime.transaction():
            evidence = self.resolve(context, session_id, handle)
            original = self.access.source(context, evidence.source)
            offset = evidence.start if start is None else integer(start, "start", 0, len(original.payload))
            maximum = policy.source_chars if max_chars is None else integer(max_chars, "max_chars", 1, policy.source_chars)
            end = min(offset + maximum, len(original.payload))
            if end <= offset:
                raise ValueError("source span is empty")
            span = self.access.capture(context, evidence.source, start=offset, end=end)
            offered = self.offer(context, session_id, span)
            result = {"handle": offered, "text": original.payload[offset:end], "start": offset, "end": end,
                "next_offset": end if end < len(original.payload) else None, "total_chars": len(original.payload),
                "source": json.loads(encode(evidence.source)), "speaker_id": span.speaker_id, "source_kind": span.source_kind}
            return self._charge(context, session_id, result, read={"handle": offered, "start": offset, "end": end})

    @outcome
    def status(self, context, session_id):
        policy = self.access.policy_for(context)
        with self.runtime.transaction():
            session = self._session(context, session_id)
            state = json.loads(session["state_json"])
            reads = []
            for entry in state["reads"]:
                try:
                    self.resolve(context, session_id, entry["handle"])
                    reads.append(entry)
                except TaskError:
                    continue
            return self._charge(context, session_id, {"reads": reads, "remaining_calls": max(0, policy.turn_calls - session["calls"] - 1),
                "remaining_chars_before_this_result": max(0, policy.turn_chars - session["chars"]), "expires_at": session["expires_at"]})
