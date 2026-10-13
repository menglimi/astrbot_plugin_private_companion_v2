"""Confirmed reply quotes offered by the conversation owner to memory."""

import json
import threading

from companion_v2.execution.models import TaskContext, TaskError, require, stamp
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.dependencies import link
from companion_v2.sources.privacy import redact_text

from . import codec
from .models import AtomRef, owner_key, timestamp


OWNER = "conversation.confirmed_reply"


class ConfirmedReplySources:
    def __init__(self, memory, messages):
        self.memory, self.messages, self.runtime = memory, messages, messages.runtime
        self._reading = threading.local()

    def reference(self, row):
        original = TaskContext.restore(json.loads(row["context_json"]))
        return SourceRef("sent:" + row["part_id"], OWNER, original.scope,
                         VersionRef(row["part_id"], 1), timestamp(row["delivered_at"]))

    def rows(self, context):
        after = 0
        while True:
            rows = self.runtime.read_all("""SELECT h.*, b.context_json FROM conversation_sent_history h
                JOIN conversation_batches b ON b.batch_id = h.batch_id
                WHERE h.history_sequence > ?
                AND json_extract(b.context_json, '$.actor.subject.subject_id') = ?
                AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
                AND json_extract(b.context_json, '$.role_binding.scope.bot_id') = ?
                ORDER BY h.history_sequence LIMIT 32""",
                (after, context.actor.subject.subject_id, context.role_binding.role.subject_id, context.scope.bot_id))
            if not rows:
                return
            for row in rows:
                after = row["history_sequence"]
                yield self.reference(row)

    def _tool_dependencies(self, context, batch_id, request):
        """Read durable provenance without reviving an expired query session."""
        references = []
        calls = self.runtime.read_all("SELECT * FROM conversation_tool_calls WHERE batch_id = ? ORDER BY sequence", (batch_id,))
        for row in calls:
            if row["state"] != "succeeded":
                continue
            result = json.loads(row["result_json"])
            if (self.messages.tools is not None and self.messages.tools.calendar is not None
                    and row["action"] in self.messages.tools.calendar.actions):
                later = tuple(other for other in calls if other["sequence"] > row["sequence"])
                references.extend(self.messages.tools.calendar.confirmed_dependencies(row, context, result, later))
                continue
            if (self.messages.tools is not None and self.messages.tools.timeline is not None
                    and row["action"] in self.messages.tools.timeline.actions):
                references.extend(self.messages.tools.timeline.confirmed_dependencies(row, context, result))
                continue
            if (self.messages.tools is not None and self.messages.tools.growth is not None
                    and row["action"] in self.messages.tools.growth.actions):
                later = tuple(other for other in calls if other["sequence"] > row["sequence"])
                references.extend(self.messages.tools.growth.confirmed_dependencies(row, context, result, later))
                continue
            if (self.messages.tools is not None and self.messages.tools.relationships is not None
                    and row["action"] in self.messages.tools.relationships.actions):
                later = tuple(other for other in calls if other["sequence"] > row["sequence"])
                references.extend(self.messages.tools.relationships.confirmed_dependencies(row, context, result, later))
                continue
            if not row["action"].startswith("memory."):
                if self.messages.tools is None:
                    raise TaskError("tool_owner_unavailable", "original reply tool owner is unavailable")
                _, materials = self.messages.tools._validate_result(row, request, context, self.messages.tasks.now())
                if materials is not None:
                    references.extend(m.source for m in (materials if isinstance(materials, tuple) else (materials,))
                                      if m.source is not None)
                continue
            if self.messages.tools is None or self.messages.tools.memory is None:
                raise TaskError("tool_owner_unavailable", "original memory tool owner is unavailable")
            later = tuple(other for other in calls if other["sequence"] > row["sequence"])
            references.extend(self.messages.tools.memory.confirmed_dependencies(row, context, result, later))
        return references

    def materialize(self, context, reference):
        """Publish a quote during source selection, before any read-only use."""
        return self._resolve(context, reference, publish=True)

    def validate(self, context, reference):
        """Recheck the original receipt and dependencies without writing."""
        return self._resolve(context, reference, publish=False)

    def _resolve(self, context, reference, *, publish):
        if reference.owner != OWNER or reference.version.revision != 1:
            raise TaskError("memory_source_unavailable", "not an original confirmed reply")
        reading = getattr(self._reading, "source_ids", None)
        if reading is None:
            reading = set()
            self._reading.source_ids = reading
        if reference.source_id in reading or len(reading) >= 32:
            raise TaskError("memory_source_cycle", "reply provenance is cyclic or exceeds the read budget")
        reading.add(reference.source_id)
        try:
            return self._read(context, reference, publish=publish)
        finally:
            reading.remove(reference.source_id)

    def _read(self, context, reference, *, publish):
        row = self.runtime.read_one("""SELECT h.*, b.context_json, p.text, p.payload_hash, p.sequence,
            p.operation_id, p.sender_json, p.platform_ref, p.state, r.receipt_json
            FROM conversation_sent_history h JOIN conversation_parts p ON p.part_id = h.part_id
            JOIN conversation_batches b ON b.batch_id = h.batch_id
            JOIN conversation_delivery_receipts r ON r.part_id = h.part_id AND r.receipt_ref = h.receipt_ref
            WHERE h.part_id = ?""", (reference.version.lineage_id,))
        if row is None or row["state"] != "delivered" or self.reference(row) != reference:
            raise TaskError("memory_delivery_unproven", "reply has no matching confirmed delivery")
        original = TaskContext.restore(json.loads(row["context_json"]))
        if owner_key(original) != owner_key(context):
            raise TaskError("memory_source_scope", "reply belongs to another relationship")
        self.messages.recalls.check_reply(original.scope, row["platform_ref"])
        proof = json.loads(row["receipt_json"])
        expected = {"part_id": row["part_id"], "operation_id": row["operation_id"],
            "origin_key": original.key, "payload_hash": row["payload_hash"], "status": "delivered",
            "delivered_at": row["delivered_at"], "sender": json.loads(row["sender_json"]),
            "platform_ref": row["platform_ref"]}
        if any(proof.get(k) != v for k, v in expected.items()):
            raise TaskError("memory_delivery_unproven", "original reply or receipt changed")
        self.memory.writer.access.check(original)
        request = self.messages._request(self.messages.batch(row["batch_id"]), original, self.messages.tasks.now(),
                                         include_tools=False, historical=True)
        _, image_manifest = self.messages.reply_images.for_part(row, self.messages.batch(row["batch_id"]), original,
            self.messages.tasks.now(), request=request)
        dependencies = [request.event.source]
        if image_manifest is not None:
            dependencies.append(image_manifest)
        dependencies.extend(m.source for m in request.context.materials if m.source is not None)
        dependencies.extend(self._tool_dependencies(original, row["batch_id"], request))
        saved = json.loads(self.messages.batch(row["batch_id"])["contributions_json"])
        for item in saved.get("memory_context", {}).get("references", []):
            fact = require(self.memory.writer.read(original, AtomRef(**item)))
            dependencies.append(codec.source(fact["source"]))
        now = self.messages.tasks.now()
        existing = self.runtime.read_one(
            "SELECT 1 FROM sources WHERE source_id = ? AND lineage_id = ? AND source_revision = 1",
            (reference.source_id, reference.version.lineage_id),
        )
        if existing is not None:
            record = require(self.messages.sources.read(
                reference, resolved=original.actor, capability="memory.read",
                observed_at=now, authorizer=self.memory.writer.access,
            ))
            if record.payload != redact_text(row["text"]):
                raise TaskError("memory_delivery_unproven", "stored quote does not match the confirmed reply")
            return record
        if not publish:
            raise TaskError("memory_source_unavailable", "confirmed reply has not been offered by its owner")
        record = self.messages.sources.prepare_message(SourceRecord(
            reference, original.audience, row["payload_hash"], row["text"],
        ))
        with self.runtime.transaction():
            require(self.messages.sources.publish(record, observed_at=now))
            link(self.runtime, reference, tuple(set(dependencies)), now)
        return record
