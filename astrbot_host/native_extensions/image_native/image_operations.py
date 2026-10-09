"""Durable native operations and original images, scoped and idempotent."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .image_preparation_task import PreparationError, json_bytes


TERMINAL = frozenset({"completed", "failed", "cancelled", "partial", "withheld", "expired"})


def inspect_image(raw: bytes) -> dict:
    if not 0 < len(raw) <= 50 * 1024 * 1024:
        raise PreparationError("output_size_limit")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(image.format)
            if not mime or image.width * image.height > 40_000_000:
                raise ValueError()
            width, height = image.size
            image.verify()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
                "media_type": mime, "width": width, "height": height}
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise PreparationError("output_invalid") from exc


class ImageOperationStore:
    def __init__(self, directory: Path, generation: str):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets = self.root / "originals"
        self.assets.mkdir(exist_ok=True)
        self.path = self.root / "operations.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, persona TEXT NOT NULL,
                    idem TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
                    generation TEXT NOT NULL, task TEXT NOT NULL, artifact TEXT NOT NULL,
                    plan TEXT NOT NULL, locator TEXT NOT NULL DEFAULT '{}',
                    evidence TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                    cancelled INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
                    expires REAL NOT NULL, UNIQUE(owner, idem));
                CREATE TABLE IF NOT EXISTS parts (
                    job TEXT NOT NULL, part INTEGER NOT NULL, metadata TEXT NOT NULL,
                    PRIMARY KEY(job, part));
                CREATE TABLE IF NOT EXISTS deliveries (
                    job TEXT NOT NULL, part INTEGER NOT NULL, audience TEXT NOT NULL,
                    state TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(job,part,audience));
            """)
            # A restart never replays a generation POST. Known ComfyUI tasks
            # can be reconciled by their real locator; no-locator work is unknown.
            db.execute("UPDATE jobs SET state=CASE WHEN state='queued' THEN 'cancelled' "
                       "WHEN locator!='{}' THEN 'waiting' ELSE 'unknown' END, "
                       "error='runtime_restarted' WHERE generation!=? AND state IN "
                       "('queued','uploading','submitting','running','saving')", (generation,))
            db.execute("UPDATE deliveries SET state='unknown' WHERE state='sending'")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def begin(self, access: dict, key: str, task: dict, artifact: dict, plan: dict,
              *, generation: str, daily_limit: int, retention_days: int, max_bytes: int) -> tuple[dict, bool]:
        if not isinstance(key, str) or not 1 <= len(key) <= 160 or any(ord(c) < 32 for c in key):
            raise PreparationError("invalid_idempotency_key")
        stable = {k: v for k, v in artifact.items() if k not in {"preparation_ref", "fingerprint"}}
        fingerprint = hashlib.sha256(json_bytes({"task": task, "artifact": stable})).hexdigest()
        now = time.time()
        with self.db() as db:
            previous = db.execute("SELECT * FROM jobs WHERE owner=? AND idem=?", (access["owner_key"], key)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise PreparationError("operation_conflict")
                return dict(previous), False
            if db.execute("SELECT count(*) FROM jobs WHERE created>=?", (now - 86400,)).fetchone()[0] >= daily_limit:
                raise PreparationError("daily_budget_exceeded")
            used = sum(json.loads(r[0])["size_bytes"] for r in db.execute("SELECT metadata FROM parts"))
            if used >= max_bytes:
                raise PreparationError("storage_capacity")
            job_id = "imageop_" + uuid4().hex
            db.execute("INSERT INTO jobs(id,owner,persona,idem,fingerprint,state,generation,task,artifact,plan,"
                       "created,updated,expires) VALUES(?,?,?,?,?,'queued',?,?,?,?,?,?,?)",
                       (job_id, access["owner_key"], access["persona_key"], key, fingerprint, generation,
                        json_bytes(task).decode(), json_bytes(artifact).decode(), json_bytes(plan).decode(),
                        now, now, now + retention_days * 86400))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()), True

    def get(self, job_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def by_key(self, owner: str, key: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE owner=? AND idem=?', (owner, key)).fetchone()
            return dict(row) if row else None

    def recent(self, access: dict) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE persona=? AND (? OR owner=?) ORDER BY created DESC LIMIT 40",
                              (access["persona_key"], int(access["manage_all"]), access["owner_key"])).fetchall()
            return [dict(r) for r in rows]

    def update(self, job_id: str, state: str, *, error: str = "", locator: dict | None = None,
               evidence: dict | None = None) -> None:
        with self.db() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row[0] == "expired":
                return
            db.execute("UPDATE jobs SET state=?,error=?,updated=? WHERE id=?", (state, error, time.time(), job_id))
            for field, value in (("locator", locator), ("evidence", evidence)):
                if value is not None:
                    db.execute(f"UPDATE jobs SET {field}=? WHERE id=?", (json_bytes(value).decode(), job_id))

    def cancel_requested(self, job_id: str) -> None:
        with self.db() as db:
            db.execute("UPDATE jobs SET cancelled=1 WHERE id=?", (job_id,))

    def part_path(self, job_id: str, index: int) -> Path:
        if not job_id.startswith("imageop_") or len(job_id) != 40 or any(c not in "0123456789abcdef" for c in job_id[8:]):
            raise PreparationError("access_denied")
        if type(index) is not int or not 0 <= index < 16:
            raise PreparationError("access_denied")
        return self.assets / f"{job_id}_{index}.image"

    def save_part(self, job_id: str, index: int, raw: bytes, *, max_bytes: int) -> dict:
        metadata = {"part_id": str(index), **inspect_image(raw)}
        path = self.part_path(job_id, index)
        with self.db() as db:
            job = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job[0] == "expired":
                raise PreparationError("output_unavailable")
            previous = db.execute("SELECT metadata FROM parts WHERE job=? AND part=?", (job_id, index)).fetchone()
            if previous:
                stored = json.loads(previous[0])
                if stored != metadata:
                    raise PreparationError("output_changed")
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]:
                    return stored
            used = sum(json.loads(r[0])["size_bytes"] for r in db.execute("SELECT metadata FROM parts"))
            if used + (0 if previous else len(raw)) > max_bytes:
                raise PreparationError("storage_capacity")
            tmp = path.with_suffix(".part")
            try:
                with tmp.open("wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
            db.execute("INSERT OR REPLACE INTO parts(job,part,metadata) VALUES(?,?,?)",
                       (job_id, index, json_bytes(metadata).decode()))
        return metadata

    def parts(self, job_id: str) -> list[dict]:
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT metadata FROM parts WHERE job=? ORDER BY part", (job_id,))]

    def read_part(self, job_id: str, index: int) -> tuple[bytes, str]:
        matches = [p for p in self.parts(job_id) if p["part_id"] == str(index)]
        if len(matches) != 1:
            raise PreparationError("output_unavailable")
        try:
            path = self.part_path(job_id, index)
            if path.stat().st_size != matches[0]["size_bytes"]:
                raise PreparationError("output_unavailable")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != matches[0]["sha256"]:
                raise PreparationError("output_unavailable")
            return raw, matches[0]["media_type"]
        except OSError as exc:
            raise PreparationError("output_unavailable") from exc

    def cleanup(self) -> None:
        with self.db() as db:
            for row in db.execute("SELECT id FROM jobs WHERE expires<? AND state!='expired'", (time.time(),)).fetchall():
                for part in db.execute("SELECT part FROM parts WHERE job=?", (row[0],)).fetchall():
                    self.part_path(row[0], part[0]).unlink(missing_ok=True)
                db.execute("DELETE FROM parts WHERE job=?", (row[0],))
                db.execute("UPDATE jobs SET state='expired',task='{}',artifact='{}',plan='{}',locator='{}',evidence='{}' WHERE id=?", (row[0],))

    def claim_delivery(self, job_id: str, index: int, audience: str, retry_failed: bool) -> tuple[bool, dict]:
        with self.db() as db:
            row = db.execute("SELECT * FROM deliveries WHERE job=? AND part=? AND audience=?",
                             (job_id, index, audience)).fetchone()
            if row and not (row["state"] == "failed" and retry_failed):
                return False, {"status": row["state"], **json.loads(row["receipt"]), "sent": row["state"] == "sent"}
            db.execute("INSERT OR REPLACE INTO deliveries(job,part,audience,state) VALUES(?,?,?,'sending')",
                       (job_id, index, audience))
        return True, {}

    def delivery_receipts(self, job_id: str) -> list[dict]:
        with self.db() as db:
            return [{"part_id": str(row["part"]), **json.loads(row["receipt"]),
                     "status": row["state"], "sent": row["state"] == "sent"}
                    for row in db.execute("SELECT part,state,receipt FROM deliveries WHERE job=? ORDER BY part", (job_id,))]

    def finish_delivery(self, job_id: str, index: int, audience: str, receipt: dict) -> dict:
        state = "sent" if receipt.get("sent") is True else "unknown" if receipt.get("uncertain") else "failed"
        safe = {k: receipt[k] for k in ("sent", "uncertain", "destination", "message_id") if k in receipt}
        with self.db() as db:
            db.execute("UPDATE deliveries SET state=?,receipt=? WHERE job=? AND part=? AND audience=?",
                       (state, json_bytes(safe).decode(), job_id, index, audience))
        return {"status": state, **safe}
