"""V2-only semantic catalog. Originals are versioned; vectors are disposable."""

from contextlib import contextmanager
import json
import math
import sqlite3

from companion_v2.execution.models import TaskError, digest, encode


DEFAULTS = {"enabled": True, "embedding_provider": "", "rerank_provider": "", "analysis_provider": "",
            "memory_enabled": True, "reactions_enabled": True,
            "reactions_private_enabled": True, "reactions_group_enabled": False,
            "reactions_proactive_enabled": False,
            "reactions_trigger_probability": 0.2, "reactions_cooldown_seconds": 180,
            "reactions_delivery_mode": "separate_after", "reactions_image_format": "image",
            "slang_enabled": True,
            "slang_learning": True, "slang_web_search_enabled": False,
            "slang_web_search_candidates": 4, "slang_web_search_results": 2,
            "vision_review": True, "timeout_seconds": 8,
            "batch_size": 24, "learning_interval_seconds": 900}


class SemanticStore:
    def __init__(self, root):
        self.path = root / "semantic-catalog.sqlite3"
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise ValueError("unsupported semantic catalog version")
            db.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO settings VALUES (1, 0, '{}')")
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
            db.execute("PRAGMA user_version=3")

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
        with self.db() as db:
            row = db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            return {"revision": row["revision"], **DEFAULTS, **json.loads(row["payload"])}

    def configure(self, changes, revision):
        if type(changes) is not dict or set(changes) - set(DEFAULTS):
            raise ValueError("unknown semantic settings")
        changes = dict(changes)
        probability = changes.get("reactions_trigger_probability")
        if type(probability) in (int, float):
            changes["reactions_trigger_probability"] = float(probability)
        for k, value in changes.items():
            if type(value) is not type(DEFAULTS[k]):
                raise ValueError("wrong semantic setting type")
            if type(value) is str and (len(value) > 200 or value != value.strip()):
                raise ValueError("invalid provider identifier")
        settings = {**self.settings(), **changes}
        if (settings["reactions_delivery_mode"] not in ("separate_after", "same_message", "separate_before")
                or settings["reactions_image_format"] not in ("image", "qq_emoji")):
            raise ValueError("unsupported reaction delivery setting")
        if not (1 <= settings["timeout_seconds"] <= 30 and 1 <= settings["batch_size"] <= 64
                and 60 <= settings["learning_interval_seconds"] <= 86400
                and 1 <= settings["slang_web_search_candidates"] <= 12
                and 1 <= settings["slang_web_search_results"] <= 5
                and math.isfinite(settings["reactions_trigger_probability"])
                and 0 <= settings["reactions_trigger_probability"] <= 1
                and 0 <= settings["reactions_cooldown_seconds"] <= 3600):
            raise ValueError("semantic settings outside supported range")
        settings.pop("revision")
        with self.db() as db:
            if not db.execute("UPDATE settings SET revision=revision+1,payload=? WHERE id=1 AND revision=?",
                              (encode(settings), revision)).rowcount:
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
