"""Install reviewed V1 person-private records in the historical read model."""

from datetime import datetime, timezone
import json

from companion_v2.execution.models import digest, encode
from .legacy_materials import _database, _target_document, _utc


def import_private_memory(store, plan, records, target, *, preview=False):
    target = _target_document(target)
    if target["scope_kind"] != "private":
        raise ValueError("legacy_private_memory_private_target_required")
    selection = sorted(r["person_id"] for r in records)
    if not selection or not set(selection).issubset({r["person_id"] for r in plan.records}):
        raise ValueError("legacy_private_memory_selection_invalid")
    # Each destination has its own lineage; importing a second role never erases the first.
    lineage = digest([plan.lineage_id, target])
    generation = digest([plan.source_fingerprint, target, selection])
    binding = digest([selection, target])
    rows = []
    for record in records:
        for item in record["materials"]:
            rows.append((generation, digest([generation, item["key"]]), item["kind"],
                target["installation_id"], target["bot_id"], target["role_id"], target["actor_id"],
                "private", target["native_scope_id"], target["platform"], target["account_id"],
                _utc(item["occurred_at"]), item["text"], encode(item["attributes"])))
    result = {"source_id": "private.authoritative_memory", "source_fingerprint": generation,
        "selected_person_count": len(selection), "imported": {"memories": sum(r[2] == "memories" for r in rows),
        "timeline": sum(r[2] == "timeline" for r in rows)}, "historical_only": True,
        "execution_restored": False, "already_present": False}
    if preview:
        return result
    connection = _database(store.runtime)
    try:
        connection.execute("BEGIN IMMEDIATE")
        prior = connection.execute("SELECT stats_json FROM legacy_memory_imports WHERE source_fingerprint=?",
                                   (generation,)).fetchone()
        if prior:
            connection.execute("ROLLBACK")
            return {**json.loads(prior["stats_json"]), "already_present": True}
        old = [r[0] for r in connection.execute("SELECT source_fingerprint FROM legacy_memory_imports WHERE lineage_id=?", (lineage,))]
        for value in old:
            connection.execute("DELETE FROM legacy_memory_materials WHERE source_fingerprint=?", (value,))
            connection.execute("DELETE FROM legacy_memory_imports WHERE source_fingerprint=?", (value,))
        connection.execute("INSERT INTO legacy_memory_imports VALUES (?,?,?,?,?,?)",
            (generation, plan.source_fingerprint, binding, datetime.now(timezone.utc).isoformat(), encode(result), lineage))
        connection.executemany("INSERT INTO legacy_memory_materials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        connection.execute("COMMIT")
        return result
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
