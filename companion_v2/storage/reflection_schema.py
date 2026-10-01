"""Indexed reflection input reservations, maintained with their original manifest."""


REFLECTION_INPUT_TABLES = frozenset({"memory_reflection_inputs"})


def span_key(value):
    fields = ("source.source_id", "source.owner", "source.version.lineage_id", "source.version.revision",
              "start", "end", "span_hash", "speaker_id")
    return "json_array(" + ", ".join(f"json_extract({value}, '$.{field}')" for field in fields) + \
        f", COALESCE(json_extract({value}, '$.source_kind'), 'source'))"


def inputs(record, source=""):
    prefix = f"INSERT OR IGNORE INTO memory_reflection_inputs SELECT {record}.batch_id, {record}.owner_key, "
    join = source + (", " if source else "FROM ")
    return (
        prefix + f"'evidence', {span_key('e.value')} {join}json_each({record}.manifest_json, '$.evidence') e",
        prefix + f"'pending', json_extract(p.value, '$.operation_id') {join}"
        f"json_each({record}.manifest_json, '$.pending') p WHERE json_extract(p.value, '$.state') = 'pending'",
        prefix + f"'pending_evidence', {span_key('e.value')} {join}"
        f"json_each({record}.manifest_json, '$.pending') p, json_each(p.value, '$.proposal.evidence') e "
        "WHERE json_extract(p.value, '$.state') = 'pending'",
    )


REFLECTION_INPUT_STATEMENTS = (
    """CREATE TABLE memory_reflection_inputs (
        batch_id TEXT NOT NULL REFERENCES memory_reflections(batch_id) ON DELETE CASCADE,
        owner_key TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('evidence', 'pending', 'pending_evidence')),
        input_key TEXT NOT NULL, PRIMARY KEY(batch_id, kind, input_key)
    )""",
    "CREATE INDEX memory_reflection_input_lookup_idx ON memory_reflection_inputs(owner_key, input_key, kind, batch_id)",
    "CREATE INDEX memory_pending_selection_idx ON memory_operations(owner_key, caller_id, state, created_at, operation_id)",
) + inputs("r", "FROM memory_reflections r") + (
    "CREATE TRIGGER reflection_inputs_insert AFTER INSERT ON memory_reflections BEGIN " + "; ".join(inputs("NEW")) + "; END",
    "CREATE TRIGGER reflection_inputs_update AFTER UPDATE OF manifest_json, owner_key ON memory_reflections "
    "WHEN OLD.manifest_json IS NOT NEW.manifest_json OR OLD.owner_key IS NOT NEW.owner_key BEGIN "
    "DELETE FROM memory_reflection_inputs WHERE batch_id = OLD.batch_id; " + "; ".join(inputs("NEW")) + "; END",
)
