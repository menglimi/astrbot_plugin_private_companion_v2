"""V2-only semantic catalog. Originals are versioned; vectors are disposable."""

from contextlib import contextmanager
import json
import math
import sqlite3

from companion_v2.execution.models import TaskError, digest, encode


DEFAULTS = {"enabled": True, "embedding_provider": "", "rerank_provider": "", "analysis_provider": "",
            "memory_enabled": True, "reactions_enabled": True,
            "reactions_private_enabled": True, "reactions_group_enabled": False,
            "reactions_collection_private_enabled": False, "reactions_collection_group_enabled": False,
            "reactions_collection_private_probability": 0.1, "reactions_collection_group_probability": 0.1,
            "reactions_collection_mode": "automatic",
            "reactions_proactive_enabled": False,
            "reactions_trigger_probability": 0.2, "reactions_cooldown_seconds": 180,
            "reactions_delivery_mode": "separate_after", "reactions_image_format": "image",
            "slang_enabled": True,
            "slang_learning": True, "slang_web_search_enabled": False,
            "slang_web_search_candidates": 4, "slang_web_search_results": 2,
            "vision_review": True, "timeout_seconds": 8,
            "batch_size": 24, "learning_interval_seconds": 900}
INTEGER_LIMITS = {"timeout_seconds": (1, 30), "batch_size": (1, 64),
                  "learning_interval_seconds": (60, 86400), "slang_web_search_candidates": (1, 12),
                  "slang_web_search_results": (1, 5), "reactions_cooldown_seconds": (0, 3600)}
PROBABILITY_FIELDS = frozenset(("reactions_trigger_probability", "reactions_collection_private_probability",
                               "reactions_collection_group_probability"))
SETTING_OPTIONS = {
    "reactions_collection_mode": ("automatic", "confirm"),
    "reactions_delivery_mode": ("separate_after", "same_message", "separate_before"),
    "reactions_image_format": ("image", "qq_emoji"),
}


class SemanticStore:
    def __init__(self, root):
        self.path = root / "semantic-catalog.sqlite3"
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5):
                raise ValueError("unsupported semantic catalog version")
            db.execute("""CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                explicit TEXT NOT NULL DEFAULT '[]')""")
            if version < 5:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(settings)")}
                if "explicit" not in columns:
                    db.execute("ALTER TABLE settings ADD COLUMN explicit TEXT NOT NULL DEFAULT '[]'")
                    row = db.execute("SELECT payload FROM settings WHERE id=1").fetchone()
                    if row is not None:
                        configured = json.loads(row["payload"])
                        db.execute("UPDATE settings SET explicit=? WHERE id=1",
                                   (encode(sorted(configured)),))
            db.execute("INSERT OR IGNORE INTO settings(id, revision, payload, explicit) VALUES (1, 0, '{}', '[]')")
            db.execute("""CREATE TABLE IF NOT EXISTS items (
                owner TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, content BLOB, enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(owner, kind, id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS vectors (
                owner TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                model TEXT NOT NULL, hash TEXT NOT NULL, vector TEXT NOT NULL,
                PRIMARY KEY(owner, kind, id, model))""")
            db.execute("""CREATE TABLE IF NOT EXISTS offers (
                batch TEXT NOT NULL, call TEXT NOT NULL, owner TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(batch, call))""")
            db.execute("CREATE TABLE IF NOT EXISTS learning (owner TEXT PRIMARY KEY, checked_at REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS uses (owner TEXT, id TEXT, batch TEXT, used_at REAL, PRIMARY KEY(owner,id,batch))")
            db.execute("CREATE TABLE IF NOT EXISTS reaction_frames (owner TEXT, id TEXT, position INTEGER, content BLOB NOT NULL, PRIMARY KEY(owner,id,position))")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_preferences (
                owner TEXT NOT NULL, actor TEXT NOT NULL, auto_disabled INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(owner,actor))""")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_affinity (
                owner TEXT NOT NULL, actor TEXT NOT NULL, id TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
                positive_count INTEGER NOT NULL DEFAULT 0, negative_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(owner,actor,id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_deliveries (
                owner TEXT NOT NULL, actor TEXT NOT NULL, batch TEXT NOT NULL, id TEXT NOT NULL,
                delivered_at REAL NOT NULL, feedback_event TEXT, feedback_signal TEXT,
                PRIMARY KEY(owner,id,batch))""")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_inputs (
                owner TEXT NOT NULL, event_key TEXT NOT NULL, actor TEXT NOT NULL,
                received_at REAL, signal TEXT,
                PRIMARY KEY(owner,event_key))""")
            if version < 3:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(reaction_inputs)")}
                for column, kind in (("received_at", "REAL"), ("signal", "TEXT")):
                    if column not in columns:
                        db.execute(f"ALTER TABLE reaction_inputs ADD COLUMN {column} {kind}")
            db.execute("CREATE INDEX IF NOT EXISTS reaction_inputs_feedback ON reaction_inputs(owner,actor,received_at)")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_turns (
                batch TEXT PRIMARY KEY, owner TEXT NOT NULL, actor TEXT NOT NULL,
                explicit_request INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_collection_runs (
                owner TEXT NOT NULL, run_key TEXT NOT NULL, scope TEXT NOT NULL,
                status TEXT NOT NULL, code TEXT, item_id TEXT, updated_at REAL NOT NULL,
                PRIMARY KEY(owner,run_key))""")
            db.execute("CREATE INDEX IF NOT EXISTS reaction_collection_recent ON reaction_collection_runs(owner,updated_at DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS reaction_collection_totals (
                owner TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, count INTEGER NOT NULL,
                PRIMARY KEY(owner,scope,status))""")
            db.execute("PRAGMA user_version=5")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        snapshot = self.configuration_snapshot()
        return {"revision": snapshot["revision"], **snapshot["values"]}

    def configuration_snapshot(self):
        """Return semantic settings and which values were explicitly configured."""
        with self.db() as db:
            row = db.execute("SELECT revision, payload, explicit FROM settings WHERE id=1").fetchone()
        configured = json.loads(row["payload"])
        return {"revision": row["revision"], "values": {**DEFAULTS, **configured},
                "explicit": frozenset(json.loads(row["explicit"]))}

    @staticmethod
    def validate_changes(changes):
        """Validate and normalize a semantic-settings patch without writing it."""
        if type(changes) is not dict or set(changes) - set(DEFAULTS):
            raise ValueError("unknown semantic settings")
        normalized = dict(changes)
        for name in PROBABILITY_FIELDS:
            probability = normalized.get(name)
            if type(probability) in (int, float):
                normalized[name] = float(probability)
        for name, value in normalized.items():
            if type(value) is not type(DEFAULTS[name]):
                raise ValueError("wrong semantic setting type")
            if type(value) is str and (len(value) > 200 or value != value.strip()):
                raise ValueError("invalid provider identifier")
            if name in INTEGER_LIMITS:
                low, high = INTEGER_LIMITS[name]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError("semantic setting outside supported range")
            if name in PROBABILITY_FIELDS and not math.isfinite(value):
                raise ValueError("semantic setting outside supported range")
            if name in SETTING_OPTIONS and value not in SETTING_OPTIONS[name]:
                raise ValueError("unsupported semantic setting")
        return normalized

    def configure(self, changes, revision):
        changes = self.validate_changes(changes)
        snapshot = self.configuration_snapshot()
        settings = {"revision": snapshot["revision"], **snapshot["values"], **changes}
        if not (1 <= settings["timeout_seconds"] <= 30 and 1 <= settings["batch_size"] <= 64
                and 60 <= settings["learning_interval_seconds"] <= 86400
                and 1 <= settings["slang_web_search_candidates"] <= 12
                and 1 <= settings["slang_web_search_results"] <= 5
                and all(math.isfinite(settings[name]) and 0 <= settings[name] <= 1
                        for name in PROBABILITY_FIELDS)
                and 0 <= settings["reactions_cooldown_seconds"] <= 3600):
            raise ValueError("semantic settings outside supported range")
        settings.pop("revision")
        explicit = sorted(set(snapshot["explicit"]) | set(changes))
        with self.db() as db:
            if not db.execute("UPDATE settings SET revision=revision+1,payload=?,explicit=? WHERE id=1 AND revision=?",
                              (encode(settings), encode(explicit), revision)).rowcount:
                raise TaskError("semantic_conflict", "settings changed; refresh before saving")
        return self.settings()

    def get(self, owner, kind, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM items WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier)).fetchone()
            if row is None:
                raise TaskError("semantic_item_missing", "catalog item is unavailable")
            return {**dict(row), "payload": json.loads(row["payload"])}

    def list(self, owner, kind, *, after="", limit=64):
        with self.db() as db:
            rows = db.execute("SELECT * FROM items WHERE owner=? AND kind=? AND id>? ORDER BY id LIMIT ?",
                              (owner, kind, after, limit)).fetchall()
            return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def put(self, owner, kind, identifier, payload, *, expected=0, content=None, enabled=True, frames=None):
        with self.db() as db:
            old = db.execute("SELECT * FROM items WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier)).fetchone()
            if (old["revision"] if old else 0) != expected:
                raise TaskError("semantic_conflict", "item changed; refresh before saving")
            db.execute("INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?)", (owner, kind, identifier,
                       expected + 1, encode(payload), content if content is not None else old["content"] if old else None, int(enabled)))
            if frames is not None:
                db.execute("DELETE FROM reaction_frames WHERE owner=? AND id=?", (owner, identifier))
                db.executemany("INSERT INTO reaction_frames VALUES (?,?,?,?)",
                               ((owner, identifier, position, image) for position, image in frames))
            db.execute("DELETE FROM vectors WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier))
        return self.get(owner, kind, identifier)

    def delete(self, owner, kind, identifier, *, expected):
        with self.db() as db:
            row = db.execute("SELECT revision FROM items WHERE owner=? AND kind=? AND id=?",
                             (owner, kind, identifier)).fetchone()
            if row is None:
                raise TaskError("semantic_item_missing", "catalog item is unavailable")
            if row["revision"] != expected:
                raise TaskError("semantic_conflict", "item changed; refresh before deleting")
            db.execute("DELETE FROM vectors WHERE owner=? AND kind=? AND id=?", (owner, kind, identifier))
            if kind == "reaction":
                db.execute("DELETE FROM reaction_frames WHERE owner=? AND id=?", (owner, identifier))
                db.execute("DELETE FROM uses WHERE owner=? AND id=?", (owner, identifier))
                db.execute("DELETE FROM reaction_deliveries WHERE owner=? AND id=?", (owner, identifier))
                db.execute("DELETE FROM reaction_affinity WHERE owner=? AND id=?", (owner, identifier))
            db.execute("DELETE FROM items WHERE owner=? AND kind=? AND id=? AND revision=?",
                       (owner, kind, identifier, expected))
        return {"deleted": True}

    def record_reaction_collection(self, owner, run_key, scope, status, *, at, code=None, item_id=None):
        terminal = {"added", "pending_confirmation", "duplicate", "rejected", "failed", "cancelled"}
        if (scope not in ("private_capture", "group_capture") or status not in terminal | {"checking"}
                or type(at) not in (int, float)):
            raise ValueError("invalid reaction collection record")
        with self.db() as db:
            previous = db.execute("SELECT status FROM reaction_collection_runs WHERE owner=? AND run_key=?",
                                  (owner, run_key)).fetchone()
            was_terminal = previous is not None and previous["status"] in terminal
            db.execute("""INSERT INTO reaction_collection_runs VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(owner,run_key) DO UPDATE SET scope=excluded.scope,status=excluded.status,
                code=excluded.code,item_id=excluded.item_id,updated_at=excluded.updated_at""",
                (owner, run_key, scope, status, code, item_id, float(at)))
            if status in terminal and not was_terminal:
                db.execute("""INSERT INTO reaction_collection_totals VALUES (?,?,?,1)
                    ON CONFLICT(owner,scope,status) DO UPDATE SET count=count+1""",
                    (owner, scope, status))
            db.execute("""DELETE FROM reaction_collection_runs WHERE owner=? AND run_key NOT IN
                (SELECT run_key FROM reaction_collection_runs WHERE owner=? ORDER BY updated_at DESC LIMIT 100)""",
                (owner, owner))

    def reaction_collection_summary(self, owner):
        scopes = ("private_capture", "group_capture")
        statuses = ("added", "pending_confirmation", "duplicate", "rejected", "failed", "cancelled")
        summary = {scope: {status: 0 for status in statuses} for scope in scopes}
        with self.db() as db:
            for row in db.execute("SELECT scope,status,count FROM reaction_collection_totals WHERE owner=?", (owner,)):
                if row["scope"] in summary and row["status"] in statuses:
                    summary[row["scope"]][row["status"]] = row["count"]
            recent = [dict(row) for row in db.execute("""SELECT scope,status,code,updated_at
                FROM reaction_collection_runs WHERE owner=? ORDER BY updated_at DESC,run_key DESC LIMIT 8""",
                (owner,))]
        return {"totals": summary, "recent": recent}

    def vector(self, item, model):
        with self.db() as db:
            row = db.execute("SELECT * FROM vectors WHERE owner=? AND kind=? AND id=? AND model=?",
                             (item["owner"], item["kind"], item["id"], model)).fetchone()
            return tuple(json.loads(row["vector"])) if row and row["revision"] == item["revision"] and row["hash"] == digest(item["payload"]) else None

    def put_vector(self, item, model, vector):
        current = self.get(item["owner"], item["kind"], item["id"])
        if current["revision"] != item["revision"] or current["payload"] != item["payload"] or not current["enabled"]:
            return False
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?,?)", (item["owner"], item["kind"],
                       item["id"], item["revision"], model, digest(item["payload"]), encode(vector)))
        return True

    def offer(self, batch, call, owner, payload):
        with self.db() as db:
            old = db.execute("SELECT owner,payload FROM offers WHERE batch=? AND call=?", (batch, call)).fetchone()
            if old and tuple(old) != (owner, encode(payload)):
                raise TaskError("semantic_offer_conflict", "original semantic result cannot be replaced")
            db.execute("INSERT OR IGNORE INTO offers VALUES (?,?,?,?)", (batch, call, owner, encode(payload)))

    def offers(self, batch, owner):
        with self.db() as db:
            return [(r["call"], json.loads(r["payload"])) for r in db.execute(
                "SELECT * FROM offers WHERE batch=? AND owner=? ORDER BY call", (batch, owner))]
