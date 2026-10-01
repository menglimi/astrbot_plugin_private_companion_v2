"""Durable, finite selection steps before a reflection may dispatch its model."""

from datetime import timedelta
import json
import sqlite3

from companion_v2.execution.models import TaskError, digest, encode, require, stamp

from . import codec
from .models import owner_key, timestamp
from .reflection_inputs import HELD_SQL, reservation, span_key
from .search import index_failure


ORDER = ("json_extract(d.metadata_json, '$.message_time')", "json_extract(d.metadata_json, '$.source_id')",
         "json_extract(d.metadata_json, '$.start')", "d.id")


class ReflectionSelection:
    candidate_items = 128

    def __init__(self, reflection):
        self.reflection, self.runtime = reflection, reflection.runtime

    def continuation_needed(self, context, manifest):
        # Selection freezes at its last source snapshot. New arrivals during
        # fact preparation or model execution belong to a following batch.
        query = self.reflection.memory.query
        return (manifest.get("remaining_sources") is None or
                manifest.get("selection", {}).get("source_anchor") !=
                query.recall_index._anchor(query.objects.feeds(context, "sources")))

    def candidates(self, context, batch_id, manifest, snapshot):
        query = self.reflection.memory.query
        selection = manifest["selection"]
        where = "d.owner = ? AND " + ORDER[0] + " >= ? AND " + ORDER[0] + " < ?"
        arguments = (snapshot["partition"], manifest["start"], manifest["end"])
        prefix = """SELECT 1 FROM reflection_owner.memory_reflection_inputs i
            JOIN reflection_owner.memory_reflections r ON r.batch_id = i.batch_id
            WHERE i.owner_key = ? AND i.batch_id != ?
            AND i.input_key = json_extract(d.metadata_json, '$.reflection_key') AND """
        complete = "EXISTS (" + prefix + "i.kind = 'evidence' AND r.state = 'complete')"
        held = "EXISTS (" + prefix + "i.kind IN ('evidence', 'pending_evidence') AND r.state IN " + HELD_SQL + ")"
        membership = (owner_key(context), batch_id)
        with query.index.reflection_snapshot(self.runtime.database_path) as db:
            query.recall_index.check(db, snapshot)
            deferred = db.execute("SELECT COUNT(*) FROM recall_documents d WHERE " + where + " AND NOT " + complete + " AND " + held,
                                  (*arguments, *membership, *membership)).fetchone()[0]
            where += " AND NOT " + complete + " AND NOT " + held
            arguments += (*membership, *membership)
            where += " AND (" + ", ".join(ORDER) + ") > (?, ?, ?, ?) AND d.id NOT IN (SELECT value FROM json_each(?))"
            arguments += (*selection["after"], encode(selection["ids"]))
            remaining = db.execute("SELECT COUNT(*) FROM recall_documents d WHERE " + where, arguments).fetchone()[0]
            rows = db.execute("SELECT d.* FROM recall_documents d WHERE " + where + " ORDER BY " + ", ".join(ORDER) + " LIMIT ?",
                              (*arguments, self.candidate_items)).fetchall()
        return rows, remaining, deferred

    def _sources(self, context, batch_id, manifest):
        query = self.reflection.memory.query
        selection = manifest["selection"]
        snapshot = query.recall_index.advance(context, "personal", "sources")
        manifest["unavailable_sources"] |= snapshot.get("unavailable", False)
        if not snapshot["ready"]:
            selection["phase"] = "source_index"
            return False
        # Other relationships can update the cache's global epoch between
        # wakes. Only this source partition's history should reset our seek.
        fingerprint = digest([snapshot["generation"], snapshot["anchor"]])
        if selection.get("fingerprint") != fingerprint:
            selection["after"] = ["", "", -1, ""]
        selection.update(phase="sources", fingerprint=fingerprint, source_anchor=snapshot["anchor"])
        rows, remaining, deferred = self.candidates(context, batch_id, manifest, snapshot)
        manifest["deferred_sources"] = max(manifest["deferred_sources"], deferred)
        used = sum(e["end"] - e["start"] for e in manifest["evidence"])
        selected_keys = {span_key(codec.evidence(e)) for e in manifest["evidence"]}
        stopped = False
        for row in rows:
            if len(manifest["evidence"]) >= selection["maximum_sources"]:
                stopped = True
                break
            metadata = json.loads(row["metadata_json"])
            current = reservation(self.runtime, context, metadata["reflection_key"], batch_id)
            if metadata["reflection_key"] in selected_keys:
                pass
            elif current is not None:
                manifest["deferred_sources"] = max(manifest["deferred_sources"], int(current != "complete"))
            else:
                try:
                    value = query.objects.read(context, row)
                    evidence = value["evidence"]
                    self.reflection.memory.writer.access.evidence(context, evidence, action="memory.reflect")
                    if span_key(evidence) != metadata["reflection_key"]:
                        raise TaskError("memory_evidence_changed", "selection metadata differs from the original span")
                    if not timestamp(manifest["start"]) <= timestamp(value["message_time"]) < timestamp(manifest["end"]):
                        raise TaskError("memory_evidence_changed", "original message is outside the selection window")
                    if used + evidence.end - evidence.start > selection["maximum_chars"]:
                        stopped = True
                        break
                    manifest["evidence"].append(json.loads(encode(evidence)))
                    selection["ids"].append(row["id"])
                    selected_keys.add(metadata["reflection_key"])
                    used += evidence.end - evidence.start
                except TaskError:
                    manifest["unavailable_sources"] = True
            remaining -= 1
            selection["after"] = [metadata["message_time"], metadata["source_id"], metadata["start"], row["id"]]
            selection["examined"] += 1
        manifest["remaining_sources"] = remaining
        manifest["source_count_basis"] = "projected_candidates_before_current_authority_checks"
        return stopped or remaining == 0 or len(manifest["evidence"]) >= selection["maximum_sources"]

    def _facts(self, context, batch_id, manifest):
        reflection, query = self.reflection, self.reflection.memory.query
        if manifest["evidence"]:
            snapshot = query.fact_index.advance(context, "personal")
            if not snapshot["ready"]:
                return False
            intent = " ".join(reflection.memory.writer.access.evidence(context, codec.evidence(raw), action="memory.reflect")
                              for raw in manifest["evidence"])[-240:]
            session = batch_id + ":preparation"
            query.begin(context, session, expires_at=reflection.tasks.now() + timedelta(minutes=10))
            related = require(query.query(context, session, query_intent=intent,
                limit=min(8, reflection.memory.writer.access.policy_for(context).query_items)))
            manifest["facts"] = [{"atom_id": item["atom_id"], "revision": item["revision"]} for item in related["items"]]
            manifest["fact_selection_complete"] = related["complete"]
        total = self.runtime.read_one("SELECT COUNT(*) n FROM memory_atoms WHERE owner_key = ? AND state = 'active'",
                                      (owner_key(context),))["n"]
        manifest["unexamined_fact_count"] = max(0, total - len(manifest["facts"]))
        manifest["fact_count_basis"] = "active_heads_not_individually_read"
        return True

    def advance(self, context, row):
        reflection, batch_id = self.reflection, row["batch_id"]
        with self.runtime.transaction() as db:
            row = reflection._row(context, batch_id)
            if row["state"] != "selecting":
                return row
            manifest = json.loads(row["manifest_json"])
            reflection._validate_selection(context, manifest)
            selection = manifest["selection"]
            try:
                if selection["phase"] in ("source_index", "sources"):
                    if self._sources(context, batch_id, manifest):
                        selection["phase"] = "facts"
                if selection["phase"] == "facts" and self._facts(context, batch_id, manifest):
                    selection["phase"] = "ready"
                selection.pop("blocked_code", None)
            except sqlite3.DatabaseError as error:
                # An optional index lock must preserve the batch and selected
                # original inputs. No provider has been dispatched at this stage.
                selection["blocked_code"] = index_failure(error).code
            except TaskError as error:
                if error.code not in ("memory_cursor_stale", "memory_index_busy", "memory_index_unavailable"):
                    raise
                selection["blocked_code"] = error.code
            state = "selecting"
            if selection["phase"] == "ready":
                reflection._validate_selection(context, manifest)
                manifest["memory_sequence"] = reflection._sequence(context)
                state = "prepared" if manifest["evidence"] or manifest["pending"] or manifest.get("retry_of") else "empty"
            receipts = json.loads(row["receipts_json"])
            receipts["sequence"] = manifest["memory_sequence"]
            db.execute("UPDATE memory_reflections SET state = ?, manifest_json = ?, receipts_json = ?, updated_at = ? WHERE batch_id = ?",
                       (state, encode(manifest), encode(receipts), stamp(reflection.tasks.now()), batch_id))
        return reflection._row(context, batch_id)
