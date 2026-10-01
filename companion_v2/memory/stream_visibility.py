"""Reference projections never bypass current source, session or identity access."""

import json

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.refs import ScopeRef
from . import codec
from .models import AtomRef, owner_key
from .stream_store import fail, size


class ResyncRequired(TaskError):
    def __init__(self, state, reason):
        super().__init__("resync_required", reason)
        self.state, self.reason = state, reason


class StreamVisibility:
    def __init__(self, memory):
        self.memory = memory

    def reference(self, context, namespace, atom_id, revision):
        row = self.memory.runtime.read_one("""SELECT a.scope_json, r.record_json FROM memory_atoms a
            JOIN memory_revisions r ON r.atom_id = a.atom_id AND r.revision = ?
            WHERE a.atom_id = ? AND a.owner_key = ? AND a.namespace = ?""",
            (revision, atom_id, owner_key(context), namespace))
        if row is None:
            fail("stream_reference_unavailable")
        record = json.loads(row["record_json"])
        if "proposal" not in record:
            fail("stream_reference_unavailable")
        item = codec.proposal(record["proposal"])
        if item.retention == "session" and ScopeRef.restore(json.loads(row["scope_json"])) != context.scope:
            fail("stream_reference_unavailable")
        now = self.memory.tasks.now()
        if (item.valid_from and now < item.valid_from) or (item.valid_to and now >= item.valid_to):
            fail("stream_reference_expired")
        for evidence in item.evidence:
            self.memory.writer.access.evidence(context, evidence)
        for dependency in item.dependencies:
            require(self.memory.writer.read(context, dependency))

    def check(self, context, state, references=None):
        try:
            for atom_id, revision in (references if references is not None else state.get("known", {})).items():
                self.reference(context, state["binding"]["namespace"], atom_id, revision)
        except TaskError:
            raise ResyncRequired(state, "stream_visibility_changed") from None

    def snapshot(self, context, state, revision):
        # Bounded read + byte checks. A large view must negotiate a larger profile,
        # never silently activate a partial replacement.
        rows = self.memory.runtime.read_all("""SELECT atom_id, revision FROM memory_atoms
            WHERE owner_key = ? AND namespace = ? AND state = 'active' ORDER BY atom_id LIMIT 8193""",
            (owner_key(context), state["binding"]["namespace"]))
        if len(rows) > 8192:
            fail("snapshot_capacity_exceeded")
        items, used = [], 0
        for row in rows:
            result = self.memory.writer.read(context, AtomRef(row["atom_id"], row["revision"]))
            if not result.is_success:
                continue
            item = dict(item_kind="fact_ref", atom_id=row["atom_id"], atom_revision=row["revision"],
                        memory_revision=revision, fact_status="active")
            used += size(item)
            if used > min(state["limits"]["max_snapshot_bytes"], state["limits"]["max_staging_bytes"]):
                fail("snapshot_capacity_exceeded")
            items.append(item)
        return items

    def next_activation(self, context, state):
        # Future validity can make a previously excluded record newly visible
        # without a write. Crossing that boundary invalidates the old view.
        row = self.memory.runtime.read_one("""SELECT MIN(json_extract(record_json, '$.proposal.valid_from')) at_time
            FROM memory_atoms WHERE owner_key = ? AND namespace = ? AND state = 'active'
            AND json_extract(record_json, '$.proposal.valid_from') > ?""",
            (owner_key(context), state["binding"]["namespace"], self.memory.tasks.now().isoformat()))
        return row["at_time"]
