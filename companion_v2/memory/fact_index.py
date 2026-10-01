"""Incremental fact projection; cached terms never authorize a fact or source."""

from contextlib import closing
import json
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, stamp

from .models import owner_key
from .search import terms


class FactIndex:
    # Work limits bound materialization and owner reads, not SQLite's FTS CPU.
    sync_items = 256
    candidate_items = 128

    def __init__(self, writer, index):
        self.writer, self.runtime, self.index = writer, writer.runtime, index

    def _anchor(self, owner, sequence=None):
        if sequence == 0:
            return {"sequence": 0, "token": "empty"}
        condition = "" if sequence is None else " AND c.sequence = ?"
        parameters = (owner,) if sequence is None else (owner, sequence)
        row = self.runtime.read_one("""SELECT c.sequence, c.atom_id, c.revision, c.kind,
            r.record_json AS revision_json, a.record_json AS head_json, a.revision AS head_revision
            FROM memory_changes c LEFT JOIN memory_revisions r
                ON r.atom_id = c.atom_id AND r.revision = c.revision
            LEFT JOIN memory_atoms a ON a.atom_id = c.atom_id
            WHERE c.owner_key = ?""" + condition + " ORDER BY c.sequence DESC LIMIT 1", parameters)
        if row is None:
            return {"sequence": 0, "token": "empty"} if sequence is None else None
        if row["revision_json"] is None or row["head_json"] is None:
            raise TaskError("memory_index_unavailable", "memory change history is incomplete")
        # Forgetting erases historical bodies. Its final head retains only an
        # opaque write stamp, so a rolled-back forget cannot certify a new one.
        raw = row["head_json"] if row["kind"] == "forgotten" and row["head_revision"] == row["revision"] else row["revision_json"]
        record = json.loads(raw)
        token = record.get("change_token") or digest(record)  # pre-stamp V2 rows
        return {"sequence": row["sequence"],
                "token": digest([row["atom_id"], row["revision"], row["kind"], token])}

    @staticmethod
    def expression(query):
        tokens = tuple(dict.fromkeys(terms(query)))
        if len(tokens) > 512:
            raise TaskError("memory_query_terms_exceeded", "use a more focused query; no search was performed")
        return " OR ".join('"' + token + '"' for token in tokens)

    @staticmethod
    def _remove(db, partition, identifier):
        deleted = db.execute("DELETE FROM fact_documents WHERE owner = ? AND id = ?", (partition, identifier)).rowcount
        if deleted:
            db.execute("DELETE FROM fact_lexical WHERE owner = ? AND id = ?", (partition, identifier))
        return bool(deleted)

    def _put(self, db, partition, row):
        identifier = row["atom_id"]
        if row["state"] != "active":
            return self._remove(db, partition, identifier)
        record = json.loads(row["record_json"])
        proposal = record["proposal"]
        metadata = {key: proposal[key] for key in (
            "subject", "retention", "confidence", "valid_from", "valid_to")}
        metadata.update(observed_at=record["observed_at"], scope=json.loads(row["scope_json"]))
        tokens = " ".join(terms(" ".join((proposal["predicate"], proposal["object"],
            proposal["representation"], encode(proposal["qualifiers"])))))
        fingerprint = digest([row["revision"], metadata, tokens])
        old = db.execute("SELECT hash FROM fact_documents WHERE owner = ? AND id = ?", (partition, identifier)).fetchone()
        if old is not None and old["hash"] == fingerprint:
            return False
        if old is not None:
            db.execute("DELETE FROM fact_lexical WHERE owner = ? AND id = ?", (partition, identifier))
        db.execute("""INSERT INTO fact_documents VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner, id) DO UPDATE SET revision = excluded.revision,
            hash = excluded.hash, metadata_json = excluded.metadata_json""",
            (identifier, partition, row["revision"], fingerprint, encode(metadata)))
        db.execute("INSERT INTO fact_lexical(id, owner, tokens) VALUES (?, ?, ?)", (identifier, partition, tokens))
        return True

    def advance(self, context, namespace):
        """Advance at most one finite batch inside the caller's owner snapshot.

        The checkpoint and terms commit together in the disposable database.
        Its snapshot witness is checked against an immutable owner revision on
        every call, including after restart and after an outer write rolls back.
        """
        owner = owner_key(context)
        partition = digest([owner, namespace, "incremental-facts.v1"])
        current = self._anchor(owner)
        with closing(self.index._open()) as db, db:
            db.execute("BEGIN")
            row = db.execute("SELECT state_json FROM fact_sync WHERE partition = ?", (partition,)).fetchone()
            state = json.loads(row["state_json"]) if row else None
            if (state is not None and state["bootstrap"] is None and state["after"] == current["sequence"]
                    and state["anchor"] == current):
                epoch = db.execute("SELECT revision FROM fact_epoch WHERE singleton = 1").fetchone()[0]
                return self._snapshot(state, partition, current, epoch)
            db.rollback()
            # Re-read after obtaining the write slot: another cache builder may
            # have advanced or cleared it since the read-only probe above.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state_json FROM fact_sync WHERE partition = ?", (partition,)).fetchone()
            state = json.loads(row["state_json"]) if row else None
            changed = False
            if state is not None:
                previous = current if state["anchor"]["sequence"] == current["sequence"] else self._anchor(owner, state["anchor"]["sequence"])
                if previous != state["anchor"]:
                    state = None
            if state is None:
                db.execute("DELETE FROM fact_lexical WHERE owner = ?", (partition,))
                changed = bool(db.execute("DELETE FROM fact_documents WHERE owner = ?", (partition,)).rowcount)
                state = {"generation": uuid4().hex, "after": current["sequence"], "bootstrap": "", "anchor": current}
            db.execute("""INSERT INTO partition_owners VALUES (?, ?)
                ON CONFLICT(partition) DO UPDATE SET owner = excluded.owner""", (partition, owner))
            if state["bootstrap"] is not None:
                rows = self.runtime.read_all("""SELECT * FROM memory_atoms
                    WHERE owner_key = ? AND namespace = ? AND state = 'active' AND atom_id > ?
                    ORDER BY atom_id LIMIT ?""", (owner, namespace, state["bootstrap"], self.sync_items + 1))
                for atom in rows[:self.sync_items]:
                    changed = self._put(db, partition, atom) or changed
                state["bootstrap"] = rows[self.sync_items - 1]["atom_id"] if len(rows) > self.sync_items else None
            elif state["after"] < current["sequence"]:
                rows = self.runtime.read_all("""SELECT sequence, namespace, atom_id FROM memory_changes
                    WHERE owner_key = ? AND sequence > ? AND sequence <= ? ORDER BY sequence LIMIT ?""",
                    (owner, state["after"], current["sequence"], self.sync_items + 1))
                for identifier in {r["atom_id"] for r in rows[:self.sync_items] if r["namespace"] == namespace}:
                    atom = self.runtime.read_one("SELECT * FROM memory_atoms WHERE atom_id = ? AND owner_key = ?", (identifier, owner))
                    changed = (self._put(db, partition, atom) if atom else self._remove(db, partition, identifier)) or changed
                state["after"] = rows[self.sync_items - 1]["sequence"] if len(rows) > self.sync_items else current["sequence"]
            state["anchor"] = current
            db.execute("INSERT OR REPLACE INTO fact_sync VALUES (?, ?)", (partition, encode(state)))
            if changed:
                # bm25 uses the whole FTS corpus. Another partition's edits can
                # change rank order too, so every result cursor fences this epoch.
                db.execute("UPDATE fact_epoch SET revision = revision + 1 WHERE singleton = 1")
            epoch = db.execute("SELECT revision FROM fact_epoch WHERE singleton = 1").fetchone()[0]
            return self._snapshot(state, partition, current, epoch)

    @staticmethod
    def _snapshot(state, partition, current, epoch):
        return {**state, "partition": partition, "epoch": epoch,
                "ready": state["bootstrap"] is None and state["after"] == current["sequence"],
                "fingerprint": digest([state["generation"], current, epoch])}

    def candidates(self, snapshot, expression, *, context, start, end, at, subjects,
                   retention, confidence, offset, limit):
        """Rank the entire matching corpus in SQL, then fetch one finite page."""
        where, parameters = ["d.owner = ?"], [snapshot["partition"]]
        for field, operator, value in (("observed_at", ">=", start), ("observed_at", "<", end)):
            if value is not None:
                where.append(f"json_extract(d.metadata_json, '$.{field}') {operator} ?")
                parameters.append(stamp(value))
        for field, values in (("subject", subjects), ("retention", retention)):
            if values:
                where.append(f"json_extract(d.metadata_json, '$.{field}') IN ({','.join('?' for _ in values)})")
                parameters.extend(values)
        if confidence is not None:
            where.append("json_extract(d.metadata_json, '$.confidence') >= ?")
            parameters.append(confidence)
        where.append("(json_extract(d.metadata_json, '$.retention') != 'session' OR json_extract(d.metadata_json, '$.scope') = ?)")
        parameters.append(encode(context.scope))
        # Validity is checked again by MemoryWriter using today's source grants.
        for field, operator in (("valid_from", "<="), ("valid_to", ">")):
            where.append(f"(json_extract(d.metadata_json, '$.{field}') IS NULL OR json_extract(d.metadata_json, '$.{field}') {operator} ?)")
            parameters.append(stamp(at))
        if expression:
            where.extend(("fact_lexical MATCH ?", "fact_lexical.owner = d.owner", "fact_lexical.id = d.id"))
            parameters.append(expression)
            source, ordering = "fact_lexical JOIN fact_documents d", "bm25(fact_lexical), d.id"
        else:
            source, ordering = "fact_documents d", "d.id"
        with closing(self.index._open()) as db, db:
            db.execute("BEGIN")
            epoch = db.execute("SELECT revision FROM fact_epoch WHERE singleton = 1").fetchone()[0]
            row = db.execute("SELECT state_json FROM fact_sync WHERE partition = ?", (snapshot["partition"],)).fetchone()
            if epoch != snapshot["epoch"] or row is None or json.loads(row["state_json"])["generation"] != snapshot["generation"]:
                raise TaskError("memory_cursor_stale", "memory search changed; start a fresh query")
            rows = db.execute(f"SELECT d.id, d.revision FROM {source} WHERE " + " AND ".join(where)
                + f" ORDER BY {ordering} LIMIT ? OFFSET ?",
                (*parameters, limit + 1, offset)).fetchall()
        return rows[:limit], len(rows) > limit
