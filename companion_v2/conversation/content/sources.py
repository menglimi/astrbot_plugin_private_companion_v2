"""Governed Content work/version anchors and durable withdrawal consumption."""

import json

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.dependencies import link
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import _source_from_row
from companion_v2.storage.repositories import InboxRepository

from .access import document, owner_for


OWNER = "content.governance"
SCHEMA = "companion.content-source.v1"


class ContentSources:
    def __init__(self, access, *, state, events, admit, live, binding):
        self.access, self.runtime = access, access.runtime
        self.repository = access.messages.sources
        self.state, self.events, self.admit, self.live = state, events, admit, live
        self.binding = binding
        self.guard = bind(self.runtime, OWNER, self.validate)
        self.consumer = "content.governance:" + digest([self.runtime.installation_id, binding])
        self.cursor_key = "content-governance-cursor:" + self.consumer

    def close(self):
        self.guard.close()

    @staticmethod
    def _active(state):
        if state["state"] != "active":
            raise TaskError("content_work_unavailable", "the original Content work is no longer readable")

    def validate(self, record, at):
        self.live()
        try:
            value = json.loads(record.payload)
            if (set(value) not in ({"schema", "owner", "work_id", "version_id", "content_hash", "sources",
                                    "context", "binding"},
                                   {"schema", "owner", "work_id", "version_id", "content_hash", "sources",
                                    "context", "binding", "request"})
                    or value["schema"] != SCHEMA or record.content_hash != digest(record.payload)):
                raise ValueError("invalid Content anchor")
            context = TaskContext.restore(value["context"])
            if (owner_for(context) != value["owner"] or record.reference.scope != context.scope
                    or record.audience != context.audience):
                raise ValueError("changed Content audience")
            self.admit(value["binding"], context, at)
            current = self.state(value["owner"], value["work_id"], value["version_id"])
            self._active(current)
            if (current["content_hash"], current["sources"]) != (value["content_hash"], value["sources"]):
                raise TaskError("content_version_changed", "the fixed Content version or its provenance changed")
            for source in current["sources"]:
                self.access.reference(source, context, observed_at=at)
        except TaskError:
            raise
        except (TypeError, KeyError, ValueError) as error:
            raise TaskError("content_source_changed", "the original Content anchor has changed") from error

    def anchor(self, context, binding, work_id, version_id=None, *, expected_hash=None, request=None):
        """Seal one governed work/version anchor.

        ``request`` records the host-side authoring request that produced this version
        (a continuation's fixed base version, a review round's feedback reference). It
        travels with the anchor so a later cover or share decision can check what the
        version was actually written against without re-reading the conversation.
        """
        owner = owner_for(context)
        current = self.state(owner, work_id, version_id)
        self._active(current)
        if expected_hash is not None and current["content_hash"] != expected_hash:
            raise TaskError("content_version_changed", "the returned page differs from its immutable original")
        references = tuple(self.access.reference(value, context) for value in current["sources"])
        payload = encode({"schema": SCHEMA, "owner": owner, "work_id": work_id, "version_id": version_id,
                          "content_hash": current["content_hash"], "sources": current["sources"],
                          "context": context, "binding": binding, "request": request})
        identifier = "content-work:" + digest([owner, work_id, version_id, context, binding])
        with self.runtime.transaction():
            old = self.runtime.read_one("SELECT * FROM sources WHERE source_id=? AND lineage_id=? AND source_revision=1",
                                        (identifier, identifier))
            if old is not None:
                record = _source_from_row(old)
                if record.payload != payload or record.audience != context.audience:
                    raise TaskError("content_source_changed", "Content anchor is already bound to another original")
                require(self.repository.validate_reference(record.reference, observed_at=self.access.messages.tasks.now()))
                return record.reference
            root = () if version_id is None else (self.anchor(context, binding, work_id),)
            at = self.access.messages.tasks.now()
            reference = SourceRef(identifier, OWNER, context.scope, VersionRef(identifier, 1), at)
            require(self.repository.publish(SourceRecord(reference, context.audience, digest(payload), payload), observed_at=at))
            link(self.runtime, reference, (*root, *references), at)
            return reference

    def synchronize(self, *, max_pages=4):
        """Consume bounded outbox pages; per-use state checks cover any backlog."""
        self.live()
        accepted = 0
        for _ in range(max_pages):
            with self.runtime.transaction() as connection:
                saved = connection.execute("SELECT value FROM runtime_metadata WHERE key=?", (self.cursor_key,)).fetchone()
                cursor = int(saved["value"]) if saved else 0
                page = self.events(cursor, 100)
                for event in page["events"]:
                    if event["owner"]["installation_id"] != self.runtime.installation_id or event["state"] != "retracted":
                        raise TaskError("content_event_invalid", "Content withdrawal crossed its original installation")
                    receipt = require(InboxRepository(self.runtime).accept(consumer=self.consumer,
                        event_id=event["event_id"], payload_hash=digest(event), observed_at=self.access.messages.tasks.now()))
                    if receipt.replayed:
                        continue
                    rows = self.runtime.read_all("""SELECT * FROM sources WHERE owner=? AND state='active'
                        AND json_extract(json_extract(payload_json, '$'), '$.work_id')=?
                        AND json_extract(json_extract(payload_json, '$'), '$.owner')=?""",
                        (OWNER, event["work_id"], encode(event["owner"])))
                    for row in rows:
                        current = self.runtime.read_one("""SELECT * FROM sources WHERE source_id=?
                            AND lineage_id=? AND source_revision=?""",
                            (row["source_id"], row["lineage_id"], row["source_revision"]))
                        if current["state"] != "active":
                            continue
                        record = _source_from_row(current)
                        require(self.repository.revoke(record.reference,
                            expected_governance_revision=record.governance_revision,
                            observed_at=self.access.messages.tasks.now()))
                    accepted += 1
                connection.execute("INSERT INTO runtime_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                   (self.cursor_key, str(page["next_after"])))
            if len(page["events"]) < 100:
                break
        return accepted
