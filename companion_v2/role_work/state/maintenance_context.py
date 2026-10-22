"""Time-bounded dialogue and simulation history for one authorized state round."""

from datetime import timedelta
import json

from companion_v2.conversation.native_history import dialogue
from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.identity_policy.private_domain import source_ref


DIALOGUE_LOOKBACK = timedelta(days=3)


def cursor_key(context):
    return "role.state.dialogue-cursor.v1:" + context.key


def dialogue_start(maintenance, context, at):
    row = maintenance.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (cursor_key(context),))
    return max(stamp(at - DIALOGUE_LOOKBACK), json.loads(row["value"])["through"] if row else "")


def recent_dialogue(maintenance, context, at, *, start, end):
    # Each window is read with its own authority; raw private text is never pooled
    # into a different window's model request or shared state.
    return tuple(item for item in dialogue(maintenance.app.messages, context, at,
        start=start, end=end, limit=32, max_chars=10000) if item["at"] > start)


def fingerprint(items):
    return digest([(item["observation_id"], item["content_hash"], item["speaker"]) for item in items])


def dialogue_sources(maintenance, items):
    return tuple(source_ref(json.loads(row["source_json"])) for item in items
        if (row := maintenance.runtime.read_one(
            "SELECT source_json FROM conversation_native_observations WHERE observation_id = ?",
            (item["observation_id"],))) is not None)


def settle_dialogue(maintenance, context, at):
    key, through = cursor_key(context), stamp(at)
    row = maintenance.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
    if row is not None and json.loads(row["value"])["through"] >= through:
        return
    with maintenance.runtime.transaction() as connection:
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (key, encode({"through": through})))


def simulation_history(service, context, at):
    """Show repeated old simulations as history, rather than fresh corroboration."""
    records = service.records
    owner = (records.owner_key(context) if records.storage(context) == "role"
             else records.legacy.owner_key(context))
    result, seen = [], set()
    settings = service.settings(context)[0]
    for days in (3, 2, 1):
        row = service.runtime.read_one("""SELECT record_json FROM role_state_history
            WHERE owner_key = ? AND record_id = 'current'
              AND json_extract(record_json, '$.updated_at') <= ? ORDER BY revision DESC LIMIT 1""",
            (owner, stamp(at - timedelta(days=days))))
        if row is None:
            continue
        record = json.loads(row["record_json"])
        if record["revision"] in seen:
            continue
        try:
            service.evidence.validate(context, record["sources"], at=at, control=True)
            projected = service._project(record, settings, at, context=context)
        except TaskError:
            continue
        seen.add(record["revision"])
        result.append({"updated_at": record["updated_at"], "basis": "previous_simulation",
            "values": {key: projected["values"].get(key) for key in ("energy", "health", "hunger", "sleep")}})
    return tuple(result)
