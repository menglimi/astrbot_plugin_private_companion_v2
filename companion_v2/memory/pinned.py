"""Explicit core context selection, independent of similarity and retention."""

from companion_v2.execution.models import encode
from .models import AtomRef, owner_key


def visible_fact(item):
    return {key: value for key, value in item.items() if key not in ("evidence", "source", "sources", "kind")}


def select_pinned(writer, context, policy):
    selected, used, after, omitted = [], 0, "", False
    if not policy.core_items:
        return selected, omitted
    while True:
        rows = writer.runtime.read_all("""SELECT atom_id, revision FROM memory_atoms
            WHERE owner_key = ? AND state = 'active' AND atom_id > ?
            AND json_extract(record_json, '$.proposal.context_mode') = 'pinned'
            ORDER BY atom_id LIMIT 32""", (owner_key(context), after))
        if not rows:
            return selected, omitted
        for row in rows:
            after = row["atom_id"]
            result = writer.read(context, AtomRef(row["atom_id"], row["revision"]))
            if not result.is_success:
                continue
            item = result.unwrap()
            size = len(encode(visible_fact(item)))
            if len(selected) >= policy.core_items:
                return selected, True
            if used + size > min(policy.core_chars, policy.inclusion_chars):
                omitted = True
                continue
            selected.append({"atom_id": item["atom_id"], "revision": item["revision"]})
            used += size
