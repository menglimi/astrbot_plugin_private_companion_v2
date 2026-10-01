"""Durable bounded subscription sessions, on the existing memory session journal."""

from functools import wraps
import hashlib
import hmac
import json
import sqlite3
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.execution.service import outcome
from companion_v2.storage.runtime import StorageTransactionNestingError
from .models import owner_key, timestamp
from .wire_binding import _WireIssue


PREFIX = "memory-stream-"
CLIENT_PREFIX = "memory-view-"
MAX_SESSIONS = 64
CONTRACT_FINGERPRINT = "3a41420f40fcd7dc8b8e2d990c8c5b3bd47cde8a998c88339daa9c71dadaaee2"
LIMITS = dict(max_batch_items=64, max_batch_bytes=65536, max_inflight_bytes=65536,
              max_inflight_batches=1, lease_ms=30000, max_retry_attempts=3,
              max_snapshot_bytes=1048576, max_staging_bytes=2097152, max_retained_log_bytes=1048576)


def size(value):
    return len(encode(value).encode("utf-8"))


def token(prefix):
    return prefix + uuid4().hex


def fail(code):
    raise TaskError(code, code)


def stream_outcome(method):
    """Native stream APIs report invalid input and unknown commits through Outcome."""
    @outcome
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except _WireIssue as issue:
            fail(issue.reason_code)
        except StorageTransactionNestingError:
            fail("outer_transaction_required")
        except sqlite3.Error:
            fail("subscription_state_uncertain")
        except TaskError:
            raise
        except (TypeError, ValueError, KeyError, RecursionError):
            fail("invalid_request")
    return call


class StreamStore:
    def __init__(self, memory):
        self.memory, self.runtime = memory, memory.runtime

    def keys(self):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", ("memory.stream.v1",))
        if row is None:
            value = dict(lineage=token("memory-lineage-"), secret=uuid4().hex + uuid4().hex)
            with self.runtime.transaction() as connection:
                connection.execute("INSERT OR IGNORE INTO runtime_metadata VALUES (?, ?)", ("memory.stream.v1", encode(value)))
            return self.keys()
        return json.loads(row["value"])

    def cursor(self, binding, sequence):
        content = str(sequence) + ":" + digest(binding)
        signature = hmac.new(self.keys()["secret"].encode(), content.encode(), hashlib.sha256).hexdigest()
        return "mc." + str(sequence) + "." + signature

    def position(self, binding, cursor):
        if type(cursor) is not str:
            fail("stream_cursor_invalid")
        try:
            prefix, sequence, signature = cursor.split(".")
            value = int(sequence)
        except (ValueError, TypeError):
            fail("stream_cursor_invalid")
        if prefix != "mc" or value < 0 or not hmac.compare_digest(self.cursor(binding, value), cursor):
            fail("stream_cursor_invalid")
        return value

    def load(self, context, identifier, *, prefix=PREFIX, allow_expired=False):
        row = self.runtime.read_one("SELECT * FROM memory_sessions WHERE session_id = ? AND context_key = ? AND owner_key = ?",
                                    (identifier, context.key, owner_key(context)))
        if row is None or not identifier.startswith(prefix):
            fail("subscription_unavailable")
        if not allow_expired and timestamp(row["expires_at"]) <= self.memory.tasks.now():
            fail("subscription_expired")
        return json.loads(row["state_json"])

    def save(self, context, state, *, prefix=PREFIX):
        identifier = state["id"]
        if not identifier.startswith(prefix):
            raise ValueError("invalid memory session namespace")
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO memory_sessions VALUES (?, ?, ?, ?, 0, 0, ?)
                ON CONFLICT(session_id) DO UPDATE SET state_json = excluded.state_json, expires_at = excluded.expires_at""",
                (identifier, context.key, owner_key(context), state["expires_at"], encode(state)))

    def sessions(self, context):
        return tuple(json.loads(row["state_json"]) for row in self.runtime.read_all(
            "SELECT state_json FROM memory_sessions WHERE context_key = ? AND owner_key = ? AND session_id LIKE ? LIMIT ?",
            (context.key, owner_key(context), PREFIX + "%", MAX_SESSIONS + 1)))

    def reserve(self, *, prefix=PREFIX):
        now = stamp(self.memory.tasks.now())
        with self.runtime.transaction() as connection:
            # Subscription sessions never own evidence handles or fact bodies.
            connection.execute("DELETE FROM memory_sessions WHERE session_id LIKE ? AND expires_at <= ?", (prefix + "%", now))
            count = connection.execute("SELECT COUNT(*) FROM memory_sessions WHERE session_id LIKE ?", (prefix + "%",)).fetchone()[0]
            if count >= MAX_SESSIONS:
                fail("consumer_capacity_exceeded" if prefix == CLIENT_PREFIX else "subscription_capacity_exceeded")

    def revision(self, context):
        return self.memory.query.memory_revision(context)
