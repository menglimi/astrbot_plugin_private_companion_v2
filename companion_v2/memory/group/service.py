"""Group statements, exact revisions and atomic receipts in the shared memory store."""

import json

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import OperationRef, SourceRef, VersionRef
from companion_v2.memory import codec
from companion_v2.memory.models import integer, text
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.privacy import redact_text
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository
from .access import GroupMemoryAccess, owner_key


KIND = "group.public.statement.v1"
OWNER = "memory.group"
MAX_TEXT = 1024


class GroupMemory:
    def __init__(self, messages):
        self.messages, self.runtime, self.tasks = messages, messages.runtime, messages.tasks
        self.access = GroupMemoryAccess(messages)
        self.sources, self.operations = messages.sources, OperationRepository(self.runtime)
        from .context import GroupMemoryContext
        self.context = GroupMemoryContext(self)

    def row(self, context, identifier, revision=None):
        text(identifier, "memory_id", 512)
        row = self.runtime.read_one("SELECT * FROM memory_views WHERE view_id = ? AND owner_key = ? AND kind = ?",
                                    (identifier, owner_key(context), KIND))
        if row is None:
            raise TaskError("group_memory_unavailable", "memory is unavailable to this group and role")
        if revision is not None:
            integer(revision, "revision")
            if row["revision"] != revision:
                raise TaskError("group_memory_revision_conflict", "memory has changed; read its current revision")
        return row

    @staticmethod
    def visible(row):
        data = json.loads(row["document_json"])
        return {"memory_id": row["view_id"], "revision": row["revision"], "statement": data["statement"],
                "speaker_id": data["speaker_id"], "attribution": "member_statement", "visibility": "group",
                "said_at": data["said_at"], "updated_at": row["updated_at"]}

    def read(self, context, identifier, revision, *, at=None):
        with self.runtime.read_snapshot():
            self.access.check(context, at=at)
            row = self.row(context, identifier, revision)
            return self._read_row(row, at=at)

    def _read_row(self, row, *, at=None):
        """Revalidate a row already selected under its authorized group owner."""
        if row["state"] != "active":
            raise TaskError("group_memory_inactive", "group statement was retracted")
        data = json.loads(row["document_json"])
        _, original, event = self.access._input_for_owner(row["owner_key"], data["evidence"], at=at)
        if (data["author"] != original.actor.subject.subject_id
                or data["speaker_id"] != original.actor.principal.native_account_id
                or data["said_at"] != stamp(event.received_at)):
            raise TaskError("group_memory_attribution_changed", "statement lost its original speaker attribution")
        reference = codec.source(json.loads(row["source_json"]))
        source = self.messages._read_source(reference, original, "text", at or self.tasks.now())
        visible = self.visible(row)
        if (reference.owner != OWNER or source.payload != encode(visible)
                or source.content_hash != digest(source.payload) or source.audience != original.audience):
            raise TaskError("group_memory_changed", "stored statement no longer matches its original source")
        return visible, reference

    def query(self, context, *, query="", cursor="", limit=8):
        self.access.check(context)
        text(query, "query", 256, empty=True)
        text(cursor, "cursor", 512, empty=True)
        integer(limit, "limit", 1, 16)
        # Opaque IDs are strictly paged inside the owner; unavailable entries do
        # not conceal the fact that more of this bounded scan may remain.
        rows = self.runtime.read_all("""SELECT * FROM memory_views WHERE owner_key = ? AND kind = ?
            AND state = 'active' AND view_id > ? ORDER BY view_id LIMIT 65""", (owner_key(context), KIND, cursor))
        items, used, last = [], 0, cursor
        for row in rows[:64]:
            if len(items) == limit:
                break
            previous_cursor, last = last, row["view_id"]
            try:
                item, _ = self.read(context, row["view_id"], row["revision"])
            except TaskError:
                continue
            if query.casefold() not in item["statement"].casefold():
                continue
            size = len(encode(item).encode("utf-8"))
            if used + size > 24000:
                last = previous_cursor
                break
            used += size
            items.append(item)
        more = bool(rows and rows[-1]["view_id"] > last)
        return {"items": items, "next_cursor": last if more else None, "coverage": "partial", "has_more": more}

    def operation(self, context, identifier):
        self.access.check(context)
        text(identifier, "operation_id", 512)
        row = self.runtime.read_one("""SELECT * FROM memory_operations WHERE operation_id = ?
            AND owner_key = ? AND caller_id = ? AND namespace = ?""",
            (identifier, owner_key(context), context.actor.subject.subject_id, OWNER))
        if row is None:
            raise TaskError("group_memory_operation_unavailable", "original group operation is unavailable")
        return json.loads(row["result_json"])

    def change(self, context, batch_id, call_id, *, action, input_handle, statement=None,
               memory_id=None, expected_revision=None):
        self.access.check(context, "group.memory.write")
        text(call_id, "operation_key", 512)
        text(input_handle, "input_handle", 512)
        if action not in ("remember", "retract"):
            raise ValueError("unsupported group memory command")
        if action == "remember":
            statement = redact_text(text(statement, "statement", MAX_TEXT))
        elif statement is not None or memory_id is None:
            raise ValueError("retraction requires an exact memory revision")
        if (memory_id is None) != (expected_revision is None):
            raise ValueError("memory ID and expected revision must be supplied together")
        parameters = dict(action=action, input_handle=input_handle, statement=statement,
                          memory_id=memory_id, expected_revision=expected_revision)
        operation_id = "group-memory-op-" + digest([context.key, batch_id, call_id])
        with self.runtime.transaction() as connection:
            previous = connection.execute("SELECT payload_hash FROM memory_operations WHERE operation_id = ?",
                                          (operation_id,)).fetchone()
            if previous:
                if previous["payload_hash"] != digest(parameters):
                    raise TaskError("group_memory_operation_conflict", "original operation has different arguments")
                return self.operation(context, operation_id)
            evidence, source, original, event = self.access.current_input(context, batch_id, input_handle)
            current = self.row(context, memory_id, expected_revision) if memory_id is not None else None
            if current and json.loads(current["document_json"])["author"] != context.actor.subject.subject_id:
                raise TaskError("group_memory_author_required", "only the original speaker can revise or retract their statement")
            if current and current["state"] != "active":
                raise TaskError("group_memory_inactive", "a retracted statement cannot be restored with old evidence")
            if current and stamp(self.tasks.now()) < current["updated_at"]:
                raise TaskError("group_memory_clock_regression", "memory time cannot move backwards")
            # A new statement cannot recycle an exact withdrawn source from an
            # earlier operation under a different tool call ID.
            if self.runtime.read_one("SELECT 1 FROM memory_guards WHERE owner_key = ? AND evidence_key = ? LIMIT 1",
                                      (owner_key(context), digest(evidence))):
                raise TaskError("group_memory_evidence_retracted", "use a fresh member statement after retraction")
            reference = OperationRef(operation_id, OWNER, context.scope, VersionRef(operation_id, 1), operation_id)
            require(self.operations.reserve(reference, parameter_hash=digest(parameters), observed_at=self.tasks.now()))
            identifier = memory_id or "group-memory-" + digest(operation_id)
            revision, now = (current["revision"] + 1 if current else 1), stamp(self.tasks.now())
            if current:
                old = codec.source(json.loads(current["source_json"]))
                state = self.runtime.read_one("SELECT governance_revision FROM sources WHERE source_id = ? AND lineage_id = ? AND source_revision = ?",
                                              (old.source_id, old.version.lineage_id, old.version.revision))
                require(self.sources.revoke(old, expected_governance_revision=state[0], observed_at=self.tasks.now()))
            document = {"author": context.actor.subject.subject_id, "speaker_id": original.actor.principal.native_account_id,
                        "statement": statement, "said_at": stamp(event.received_at), "evidence": evidence}
            if action == "retract":
                document = json.loads(current["document_json"])
                connection.execute("INSERT OR IGNORE INTO memory_guards VALUES (?, ?, ?, ?, 'retracted')",
                    (owner_key(context), identifier, digest(document["evidence"]), identifier))
                reference = codec.source(json.loads(current["source_json"]))
                state = "retracted"
            else:
                visible = self.visible({"document_json": encode(document), "view_id": identifier,
                                        "revision": revision, "updated_at": now})
                reference = SourceRef(identifier, OWNER, context.scope, VersionRef(identifier, revision), self.tasks.now())
                payload = encode(visible)
                require(self.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload),
                                             observed_at=self.tasks.now()))
                link(self.runtime, reference, (source.reference,), self.tasks.now())
                state = "active"
            connection.execute("""INSERT INTO memory_views VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(view_id) DO UPDATE SET revision=excluded.revision, state=excluded.state,
                document_json=excluded.document_json, source_json=excluded.source_json, updated_at=excluded.updated_at""",
                (identifier, owner_key(context), KIND, revision, state, encode(document), encode(reference), now))
            result = {"operation_id": operation_id, "memory_id": identifier, "revision": revision,
                      "state": "saved" if action == "remember" else "retracted", "delivery": "not_started"}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (operation_id, owner_key(context), context.actor.subject.subject_id, OWNER, digest(parameters),
                 encode({"parameters": parameters, "evidence": evidence}), encode(context), result["state"], encode(result), now, now))
            require(self.operations.transition(operation_id, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=self.tasks.now()))
            self.context.after_write(context, batch_id, result)
            return result
