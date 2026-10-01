"""Experiences and navigation are sourced projections, never a second fact store."""

import json

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.dependencies import link
from companion_v2.sources.privacy import redact_text

from . import codec
from .models import AtomRef, owner_key, text, timestamp


class MemoryExperiences:
    candidate_items = 128

    def __init__(self, writer):
        self.writer, self.runtime = writer, writer.runtime

    @outcome
    def save(self, context, *, view_id, expected_revision, title, statements, entities=(), links=(), occurred_at=None, operation_key=None):
        """Trusted adapter resolves handles before constructing statement evidence.

        Each statement has its own evidence or original fact revisions. Labels of
        mentioned people are local navigation hints and cannot bind platform IDs.
        """
        self.writer.access.check(context, "memory.propose")
        text(view_id, "view_id", 512)
        text(title, "title", 512)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected revision must be explicit")
        if not isinstance(statements, tuple) or not 1 <= len(statements) <= 32:
            raise ValueError("experience requires bounded sourced statements")
        if not isinstance(entities, tuple) or len(entities) > 32 or any(type(e) is not str or len(e) > 512 for e in entities):
            raise ValueError("entities must be source-scoped navigation labels")
        if not isinstance(links, tuple) or len(links) > 32:
            raise ValueError("links must be bounded")
        title = redact_text(title)
        entities = tuple(redact_text(item) for item in entities)
        statements = tuple({**s, "text": redact_text(s["text"])} if isinstance(s, dict) and "text" in s else s for s in statements)
        links = tuple({**edge, "relation": redact_text(edge["relation"])}
                      if isinstance(edge, dict) and "relation" in edge else edge for edge in links)
        originals, body, serialized = [], [], []
        with self.runtime.transaction() as connection:
            operation_id = None
            request_hash = digest([view_id, expected_revision, title, statements, entities, links, occurred_at])
            if operation_key is not None:
                text(operation_key, "operation_key", 512)
                operation_id = "memory-view-op-" + digest([owner_key(context), self.writer.caller(context), operation_key])
                existing = connection.execute("SELECT * FROM memory_operations WHERE operation_id = ?", (operation_id,)).fetchone()
                if existing:
                    if existing["payload_hash"] != request_hash:
                        raise TaskError("memory_operation_conflict", "the experience operation already has different content")
                    return self.writer._receipt(existing)
            for statement in statements:
                if type(statement) is not dict or set(statement) != {"text", "evidence", "atoms"}:
                    raise ValueError("each statement names text, evidence and atoms")
                text(statement["text"], "statement", 4096)
                if not statement["evidence"] and not statement["atoms"]:
                    raise ValueError("each experience statement requires a source")
                for evidence in statement["evidence"]:
                    self.writer.access.evidence(context, evidence)
                    originals.append(evidence.source)
                for reference in statement["atoms"]:
                    fact = require(self.writer.read(context, reference))
                    originals.append(codec.source(fact["source"]))
                serialized.append(json.loads(encode(statement)))
                body.append(statement["text"])
            for edge in links:
                if type(edge) is not dict or set(edge) != {"view_id", "revision", "relation"}:
                    raise ValueError("a navigation edge needs an exact view and explicit relation")
                text(edge["relation"], "relation", 128)
                if edge["view_id"] == view_id:
                    raise ValueError("an experience cannot link to itself")
                target = require(self.read(context, edge["view_id"], expected_revision=edge["revision"]))
                originals.append(codec.source(target["source"]))
            document = {"title": title, "statements": serialized, "entities": entities, "links": links,
                        "occurred_at": stamp(timestamp(occurred_at)) if occurred_at else None,
                        "perspective": "sourced_experience_summary"}
            head = connection.execute("SELECT * FROM memory_views WHERE view_id = ?", (view_id,)).fetchone()
            if head and head["owner_key"] != owner_key(context):
                raise TaskError("memory_view_unavailable", "experience is unavailable")
            if head and head["revision"] == expected_revision + 1 and head["document_json"] == encode(document):
                return {"view_id": view_id, "revision": head["revision"], "state": "saved"}
            if (head["revision"] if head else 0) != expected_revision:
                raise TaskError("memory_view_conflict", "experience has a different version")
            if head:
                self.writer._revoke(codec.source(json.loads(head["source_json"])))
            revision, now = expected_revision + 1, self.writer.tasks.now()
            source = SourceRef("experience:" + view_id, "memory.experience", context.scope, VersionRef(view_id, revision), now)
            payload = "\n".join(body)
            require(self.writer.sources.publish(SourceRecord(source, context.audience, digest(payload), payload), observed_at=now))
            link(self.runtime, source, tuple(set(originals)), now)
            connection.execute("""INSERT INTO memory_views VALUES (?, ?, 'experience', ?, 'active', ?, ?, ?)
                ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision, state = 'active', document_json = excluded.document_json,
                source_json = excluded.source_json, updated_at = excluded.updated_at""",
                (view_id, owner_key(context), revision, encode(document), encode(source), stamp(now)))
            result = {"view_id": view_id, "revision": revision, "state": "saved"}
            if operation_id:
                self.writer._reserve(context, operation_id, request_hash)
                result["operation_id"] = operation_id
                connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, NULL, ?, 'persisted', ?, ?, ?)",
                    (operation_id, owner_key(context), self.writer.caller(context), "experiences", request_hash, encode(context), encode(result), stamp(now), stamp(now)))
                self.writer._complete(operation_id)
            return result

    @outcome
    def read(self, context, view_id, *, expected_revision=None):
        self.writer.access.check(context)
        with self.runtime.read_snapshot():
            row = self.runtime.read_one("SELECT * FROM memory_views WHERE view_id = ? AND owner_key = ? AND state = 'active'",
                                        (view_id, owner_key(context)))
            if row is None:
                raise TaskError("memory_view_unavailable", "experience is unavailable")
            if expected_revision is not None and row["revision"] != expected_revision:
                raise TaskError("memory_view_conflict", "experience has a different version")
            reference = codec.source(json.loads(row["source_json"]))
            require(self.writer.sources.validate_reference(reference, observed_at=self.writer.tasks.now()))
            document = json.loads(row["document_json"])
            for statement in document["statements"]:
                for raw in statement["evidence"]:
                    self.writer.access.evidence(context, codec.evidence(raw))
                for raw in statement["atoms"]:
                    require(self.writer.read(context, AtomRef(**raw)))
            return {"view_id": view_id, "revision": row["revision"], "source": json.loads(row["source_json"]), **document}

    @outcome
    def list(self, context, *, entity=None, after_id="", limit=20):
        self.writer.access.check(context)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("invalid experience page size")
        condition = "" if entity is None else " AND EXISTS (SELECT 1 FROM json_each(document_json, '$.entities') WHERE value = ?)"
        parameters = (owner_key(context), after_id) + (() if entity is None else (entity,))
        rows = self.runtime.read_all("SELECT view_id FROM memory_views WHERE owner_key = ? AND kind = 'experience' AND state = 'active' AND view_id > ?"
            + condition + " ORDER BY view_id LIMIT ?", (*parameters, self.candidate_items + 1))
        items, consumed, unavailable = [], 0, False
        for row in rows[:self.candidate_items]:
            if len(items) == limit:
                break
            consumed += 1
            result = self.read(context, row["view_id"])
            if not result.is_success:
                unavailable = True
                continue
            value = result.unwrap()
            if entity is not None and entity not in value["entities"]:
                continue
            items.append(value)
        more = consumed < len(rows)
        return {"items": items, "next_cursor": rows[consumed - 1]["view_id"] if more else None,
                "candidates_examined": consumed, "scan_limited": more and len(items) < limit,
                "unavailable_sources": unavailable, "complete": not more and not unavailable}
