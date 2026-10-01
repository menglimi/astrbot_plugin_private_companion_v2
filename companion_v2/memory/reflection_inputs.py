"""Indexed input membership; a reservation never authorizes original text."""

import json

from .models import owner_key


HELD_STATES = ("selecting", "prepared", "running", "received", "modelled", "failed", "partial")
HELD_SQL = "(" + ",".join("'" + state + "'" for state in HELD_STATES) + ")"


def span_key(evidence):
    reference = evidence.source
    # The exact source version is immutable; the span hash is stable before and
    # after a redacted Bot quote receives its governed content hash.
    return json.dumps([reference.source_id, reference.owner, reference.version.lineage_id,
        reference.version.revision, evidence.start, evidence.end, evidence.span_hash,
        evidence.speaker_id, evidence.source_kind], ensure_ascii=False, separators=(",", ":"))


def reservation(runtime, context, key, batch_id):
    row = runtime.read_one("""SELECT r.state FROM memory_reflection_inputs i
        JOIN memory_reflections r ON r.batch_id = i.batch_id
        WHERE i.owner_key = ? AND i.input_key = ? AND i.batch_id != ?
        AND ((r.state = 'complete' AND i.kind = 'evidence')
             OR (r.state IN """ + HELD_SQL + """ AND i.kind IN ('evidence', 'pending_evidence')))
        ORDER BY r.state = 'complete' DESC LIMIT 1""", (owner_key(context), key, batch_id))
    return row["state"] if row else None
