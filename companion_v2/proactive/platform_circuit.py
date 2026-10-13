"""Persistent account-level pause after repeated QQ proactive send refusals."""

from datetime import datetime, timedelta
import json

from companion_v2.execution.models import digest, stamp
from companion_v2.foundation.refs import normalize_utc


FAILURE_CODE = "qq_eventchecker_1200"
FAILURE_WINDOW = timedelta(minutes=10)
COOLDOWN = timedelta(hours=2)
THRESHOLD = 2
class ProactivePlatformCircuit:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def _key(context):
        scope = context.scope
        return digest([
            scope.installation_id, context.actor.principal.host_id, scope.platform,
            scope.bot_id, scope.account_id,
        ])

    @staticmethod
    def _read(connection, key):
        row = connection.execute(
            "SELECT failures_json, cooldown_until FROM proactive_platform_circuits WHERE account_key = ?",
            (key,)).fetchone()
        if row is None:
            return {"failures": [], "cooldown_until": None}
        try:
            failures = json.loads(row["failures_json"])
            if type(failures) is not list or any(type(item) is not str for item in failures):
                raise ValueError("invalid proactive circuit failures")
            for item in failures:
                datetime.fromisoformat(item)
            until = row["cooldown_until"]
            if until is not None:
                if type(until) is not str:
                    raise ValueError("invalid proactive circuit cooldown")
                datetime.fromisoformat(until)
            return {"failures": failures, "cooldown_until": until}
        except (TypeError, ValueError):
            connection.execute("DELETE FROM proactive_platform_circuits WHERE account_key = ?", (key,))
            return {"failures": [], "cooldown_until": None}

    def cooldown_until(self, context, *, at):
        at = normalize_utc(at, field="proactive platform circuit time")
        key = self._key(context)
        row = self.runtime.read_one(
            "SELECT failures_json, cooldown_until FROM proactive_platform_circuits WHERE account_key = ?",
            (key,))
        if row is None:
            return None
        try:
            failures = json.loads(row["failures_json"])
            if type(failures) is not list or any(type(item) is not str for item in failures):
                raise ValueError("invalid proactive circuit failures")
            for item in failures:
                datetime.fromisoformat(item)
            until = row["cooldown_until"]
            if until is not None:
                if type(until) is not str:
                    raise ValueError("invalid proactive circuit cooldown")
                until = normalize_utc(datetime.fromisoformat(until), field="proactive platform cooldown")
        except (TypeError, ValueError):
            with self.runtime.transaction() as connection:
                connection.execute("DELETE FROM proactive_platform_circuits WHERE account_key = ?", (key,))
            return None
        if until is None:
            return None
        if until > at:
            return until
        with self.runtime.transaction() as connection:
            connection.execute("DELETE FROM proactive_platform_circuits WHERE account_key = ? AND cooldown_until = ?",
                               (key, row["cooldown_until"]))
        return None

    def record(self, context, *, at, failure_code=None, reset_failures=False):
        at = normalize_utc(at, field="proactive platform circuit time")
        if failure_code != FAILURE_CODE and not reset_failures:
            return
        key = self._key(context)
        with self.runtime.transaction() as connection:
            state = self._read(connection, key)
            until = state["cooldown_until"]
            if until is not None and normalize_utc(
                    datetime.fromisoformat(until), field="proactive platform cooldown") > at:
                return
            if reset_failures:
                connection.execute("DELETE FROM proactive_platform_circuits WHERE account_key = ?", (key,))
                return
            failures = []
            for value in state["failures"]:
                previous = normalize_utc(datetime.fromisoformat(value), field="proactive platform rejection")
                if timedelta(0) <= at - previous <= FAILURE_WINDOW:
                    failures.append(stamp(previous))
            failures.append(stamp(at))
            cooldown_until = stamp(at + COOLDOWN) if len(failures) >= THRESHOLD else None
            connection.execute("INSERT INTO proactive_platform_circuits "
                               "(account_key, failures_json, cooldown_until, updated_at) VALUES (?, ?, ?, ?) "
                               "ON CONFLICT(account_key) DO UPDATE SET failures_json = excluded.failures_json, "
                               "cooldown_until = excluded.cooldown_until, updated_at = excluded.updated_at",
                               (key, json.dumps([] if cooldown_until else failures), cooldown_until, stamp(at)))
