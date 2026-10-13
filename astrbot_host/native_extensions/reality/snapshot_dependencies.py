"""Durable withdrawal receipts for volatile snapshots; never stores bodies."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


class SnapshotDependencies:
    def __init__(self, directory, generation):
        self.path = Path(directory) / "snapshot_dependencies.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._deadlines = {}
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS dependencies (
                ticket TEXT PRIMARY KEY, binding TEXT NOT NULL, source TEXT NOT NULL,
                generation TEXT NOT NULL, expires REAL NOT NULL, pin TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'current', receipt TEXT NOT NULL DEFAULT '')""")
            db.execute("CREATE INDEX IF NOT EXISTS dependencies_source ON dependencies(source,state)")
            db.execute("CREATE INDEX IF NOT EXISTS dependencies_expiry ON dependencies(state,expires)")
            # The old volatile owner and originals did not survive this boot.
            db.execute("UPDATE dependencies SET state='revoked',pin='{}',receipt=? WHERE generation!=? AND state='current'",
                       ("withdrawal:" + uuid4().hex, generation))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def bind(self, binding, source, generation, expires, pin):
        self._deadlines = {key: expiry for key, expiry in self._deadlines.items() if expiry > time.monotonic()}
        ticket = "reality-dependency:" + uuid4().hex
        with self.connect() as db:
            db.execute("UPDATE dependencies SET state='revoked',pin='{}',receipt=? WHERE expires<=? AND state='current'",
                       ('withdrawal:' + uuid4().hex, time.time()))
            db.execute("INSERT INTO dependencies(ticket,binding,source,generation,expires,pin) VALUES (?,?,?,?,?,?)",
                       (ticket, binding, source, generation, expires,
                        json.dumps(pin, ensure_ascii=False, sort_keys=True)))
        self._deadlines[ticket] = time.monotonic() + max(0, expires - time.time())
        return ticket

    def revoke(self, *, source=None, ticket=None):
        field, value = ("source", source) if source is not None else ("ticket", ticket)
        with self.connect() as db:
            db.execute(f"UPDATE dependencies SET state='revoked',pin='{{}}',receipt=? WHERE {field}=? AND state='current'",
                       ("withdrawal:" + uuid4().hex, value))

    def acknowledge(self, binding, tickets):
        with self.connect() as db:
            for ticket in tickets:
                db.execute("UPDATE dependencies SET pin='{}',source='' WHERE ticket=? AND binding=? AND state='revoked'",
                           (ticket, binding))
                self._deadlines.pop(ticket, None)

    def check(self, binding, tickets, identity_state):
        items = []
        for ticket in tickets:
            with self.connect() as db:
                row = db.execute("SELECT * FROM dependencies WHERE ticket=? AND binding=?", (ticket, binding)).fetchone()
            item = {"ticket": ticket, "state": "unavailable"}
            if row:
                state = row["state"]
                if state == "current":
                    expired = time.time() >= row["expires"] or time.monotonic() >= self._deadlines.get(ticket, 0)
                    state = "revoked" if expired else identity_state(json.loads(row["pin"]))
                    if state == "revoked":
                        self.revoke(ticket=ticket)
                        with self.connect() as db:
                            row = db.execute("SELECT * FROM dependencies WHERE ticket=?", (ticket,)).fetchone()
                item.update(state=state)
                if state == "revoked":
                    item["receipt"] = row["receipt"]
            items.append(item)
        return {"items": items}
