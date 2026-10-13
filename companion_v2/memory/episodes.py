"""Periodic private-dialogue episodes, folded into the existing memory chain.

V1 kept a per-user ``dialogue_episodes`` list refreshed when either enough new
messages had arrived or enough minutes had passed, and fed the result back into
that conversation. V2 deliberately has no second memory and no second timer: a
private episode is the same abstract the group slice (``episode_settings.py``)
already uses -- a periodic, bounded *material* offered to the existing memory
reflection, recorded as governed atoms/views, and read back through the existing
recall chain. This module owns no store, no table and no read path of its own.

The only durable state is a cursor in ``runtime_metadata``: it records how far
this owner's private conversation has already been summarised, so a restart or a
repeated window never summarises the same span twice. It is advanced only after a
reflection batch actually landed, never while material is being prepared.

Thresholds keep V1's names and meaning: ``dialogue_episode_refresh_messages`` is
the "or" message-count trigger, ``dialogue_episode_refresh_minutes`` is both the
time trigger and the re-arm interval (V1 read the same key twice: the due check at
``user_memory.py:9594-9598`` and ``refresh_seconds`` at ``:9744``), and
``max_dialogue_episodes`` bounds how many prior episodes one pass may see.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.foundation.refs import ScopeKind
from companion_v2.conversation.reset import batch_current

from . import codec
from .models import owner_key


GROUP = "memory"
CURSOR_PREFIX = "memory.episode.v1:"

DEFAULTS = {"dialogue_episode_memory_enabled": True,
            "dialogue_episode_refresh_messages": 8,
            "dialogue_episode_refresh_minutes": 90,
            "max_dialogue_episodes": 12}

LIMITS = {"dialogue_episode_refresh_messages": (1, 64),
          "dialogue_episode_refresh_minutes": (5, 1440),
          "max_dialogue_episodes": (1, 32)}

MAX_SOURCE_LINES = 40
MAX_LINE_CHARS = 200
MAX_SUMMARY_CHARS = 1200
# V1 refused to summarise a pass with less than 80 characters of recent dialogue
# (``user_memory.py:9600``); the same floor keeps a two-word window from becoming
# a "shared experience".
MIN_SOURCE_CHARS = 80

GUIDANCE = (
    "把最近这段私聊整理成一段简短的共同经历描述，可以覆盖上一版，不要复述聊天记录。",
    "严格区分说话人：user 行是对方真实说过的事；bot 行是角色当时自己的回复，只能当作当时的状态或语气，",
    "不要写成对方的事实、承诺或共同经历。",
    "send_returned 只记录 AstrBot 发送调用返回，不证明平台送达或对方收到；不能把发送状态整理成已读或共同经历。",
    "只为确实有延续价值的内容写条目；玩笑、反讽、一时情绪不要写成长期事实，不确定就写得轻一点。",
    "没有新内容时不要产出条目，也不要引用本轮没有提供的行。",
)


def dialogue_settings(values):
    """Validate the registered private-episode settings out of one group read."""
    settings = {name: values.get(GROUP + "." + name, default) for name, default in DEFAULTS.items()}
    if type(settings["dialogue_episode_memory_enabled"]) is not bool:
        raise TaskError("episode_configuration", "the dialogue episode switch must be boolean")
    for name, (minimum, maximum) in LIMITS.items():
        value = settings[name]
        if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
            raise TaskError("episode_configuration", "dialogue episode bounds are outside their declared range")
    return settings


def settings_for(settings_reader, context):
    """Read the effective private-episode settings for this exact owner window."""
    if context.scope.kind is not ScopeKind.PRIVATE:
        raise TaskError("episode_private_required", "dialogue episode settings need a private conversation")
    if settings_reader is None:
        raise TaskError("episode_configuration_unavailable", "memory settings are not configured")
    return dialogue_settings(settings_reader.read(context)[0])


def episode_namespace(context):
    """One namespace per private owner, so a dialogue digest never mixes with facts."""
    return "dialogue.episode:" + digest(owner_key(context))[:32]


def cursor_key(context):
    return CURSOR_PREFIX + owner_key(context)


def episode_cursor(runtime, context):
    """The durable "how far has this owner been summarised" cursor, or blanks."""
    row = runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (cursor_key(context),))
    if row is None:
        return {"covered_through": None, "updated_at": None}
    try:
        saved = json.loads(row["value"])
    except (TypeError, ValueError):
        return {"covered_through": None, "updated_at": None}
    if not isinstance(saved, dict) or not isinstance(saved.get("covered_through"), str):
        return {"covered_through": None, "updated_at": saved.get("updated_at") if isinstance(saved, dict) else None}
    return {"covered_through": saved["covered_through"], "updated_at": saved.get("updated_at")}


def mark_covered(runtime, context, manifest, *, now=None):
    """Advance the cursor to the end of a window whose batch actually landed."""
    if context.scope.kind is not ScopeKind.PRIVATE or not isinstance(manifest, dict):
        return None
    end = manifest.get("end")
    if not isinstance(end, str) or not end:
        return None
    current = episode_cursor(runtime, context)["covered_through"]
    covered = max([value for value in (current, end) if isinstance(value, str)])
    try:
        observed = stamp(now or datetime.fromisoformat(end))
    except (TypeError, ValueError):
        observed = end
    with runtime.transaction() as connection:
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (cursor_key(context), json.dumps({"covered_through": covered, "updated_at": observed},
                                             sort_keys=True, separators=(",", ":"))))
    return covered


def recent_dialogue_lines(runtime, access, context, manifest, *, limit=MAX_SOURCE_LINES):
    """Both sides of this owner's private dialogue inside the window, oldest first.

    Human lines are read back through the original authorized source reader, so a
    withdrawn or unreadable input simply drops out. Bot lines are the confirmed
    delivered replies the rest of the memory chain already trusts.
    """
    if context.scope.kind is not ScopeKind.PRIVATE:
        raise TaskError("episode_private_required", "dialogue episode material needs a private conversation")
    start, end = manifest["start"], manifest["end"]
    scope = context.scope
    identity = (scope.installation_id, scope.account_id, scope.bot_id,
                context.role_binding.role.subject_id, context.actor.subject.subject_id)
    rows = runtime.read_all("""SELECT i.batch_id, i.event_key, i.event_json
        FROM conversation_inputs i JOIN conversation_batches b ON b.batch_id = i.batch_id
        WHERE i.withdrawn = 0
        AND json_extract(i.event_json, '$.received_at') >= ? AND json_extract(i.event_json, '$.received_at') < ?
        AND json_extract(b.context_json, '$.audience.scope.installation_id') = ?
        AND json_extract(b.context_json, '$.audience.scope.account_id') = ?
        AND json_extract(b.context_json, '$.audience.scope.bot_id') = ?
        AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
        AND json_extract(b.context_json, '$.actor.subject.subject_id') = ?
        ORDER BY json_extract(i.event_json, '$.received_at') DESC LIMIT ?""",
        (start, end, *identity, limit))
    lines = []
    for row in reversed(rows):
        if not batch_current(runtime, row["batch_id"]):
            continue
        try:
            stored = json.loads(row["event_json"])
            reference = codec.source(stored["source"])
            text = access.source(context, reference).payload
        except (TaskError, KeyError, TypeError, ValueError):
            continue  # an unreadable original is never replaced by a guess
        plain = " ".join(str(text or "").split())
        if plain:
            lines.append({"speaker": "user", "at": stored.get("received_at", ""), "text": plain[:MAX_LINE_CHARS]})
    parts = runtime.read_all("""SELECT p.batch_id, p.text, p.delivered_at
        FROM conversation_parts p
        JOIN conversation_batches b ON b.batch_id = p.batch_id
        JOIN conversation_delivery_receipts r ON r.part_id = p.part_id AND r.receipt_ref = p.receipt_ref
        WHERE p.state = 'delivered' AND p.delivered_at >= ? AND p.delivered_at < ?
        AND json_extract(b.context_json, '$.audience.scope.installation_id') = ?
        AND json_extract(b.context_json, '$.audience.scope.account_id') = ?
        AND json_extract(b.context_json, '$.audience.scope.bot_id') = ?
        AND json_extract(b.context_json, '$.role_binding.role.subject_id') = ?
        AND json_extract(b.context_json, '$.actor.subject.subject_id') = ?
        ORDER BY p.delivered_at DESC LIMIT ?""", (start, end, *identity, limit))
    for row in reversed(parts):
        if not batch_current(runtime, row["batch_id"]):
            continue
        plain = " ".join(str(row["text"] or "").split())
        if plain:
            lines.append({"speaker": "bot", "at": row["delivered_at"], "text": plain[:MAX_LINE_CHARS]})
    from companion_v2.conversation.native_observations import rows_for_context, validate_observation
    for row in rows_for_context(runtime, context, start=start, end=end, limit=limit):
        try:
            reference = codec.source(json.loads(row["source_json"]))
            _, source_kind = validate_observation(runtime, row, context, reference)
            text = access.source(context, reference).payload
        except (TaskError, KeyError, TypeError, ValueError):
            continue
        plain = " ".join(str(text or "").split())
        if plain:
            lines.append({"speaker": "user" if source_kind == "human_message" else "bot",
                          "at": row["sent_at"] or row["observed_at"], "text": plain[:MAX_LINE_CHARS],
                          "delivery_state": row["delivery_state"]})
    lines.sort(key=lambda item: (item["at"], item["speaker"]))
    return tuple(lines[-limit:])


def dialogue_episode_material(runtime, settings_reader, access, context, manifest):
    """The bounded private-episode material for one window, or None.

    Additive material only: a group scope, a disabled switch, an unusable cursor,
    too few new messages inside the re-arm interval or too little text all simply
    produce nothing, so no reflection pass is ever blocked by this setting.
    """
    if context.scope.kind is not ScopeKind.PRIVATE:
        return None
    try:
        settings = settings_for(settings_reader, context)
        if not settings["dialogue_episode_memory_enabled"]:
            return None
        cursor = episode_cursor(runtime, context)
        if not episode_due(cursor, (), settings, manifest, window_only=True):
            return None
        lines = recent_dialogue_lines(runtime, access, context, manifest)
    except (TaskError, ValueError, KeyError, TypeError):
        return None
    due = episode_due(cursor, lines, settings, manifest)
    if due is None:
        return None
    fresh, trigger = due
    return {"start": manifest["start"], "end": manifest["end"], "namespace": episode_namespace(context),
            "covered_through": cursor["covered_through"], "new_lines": len(fresh), "trigger": trigger,
            "refresh_messages": settings["dialogue_episode_refresh_messages"],
            "refresh_minutes": settings["dialogue_episode_refresh_minutes"],
            "max_dialogue_episodes": settings["max_dialogue_episodes"],
            "max_summary_chars": MAX_SUMMARY_CHARS,
            "recent_dialogue": [dict(line) for line in fresh], "guidance": list(GUIDANCE)}


def episode_due(cursor, lines, settings, manifest, *, window_only=False):
    """V1's "messages or minutes" gate over lines newer than the durable cursor.

    ``window_only`` answers the cheap question first: a window whose end the
    cursor already covers is never summarised again, which is what keeps a
    restart (or a repeated/repair pass) from organising the same span twice.
    """
    covered = cursor["covered_through"]
    if covered is not None and isinstance(manifest.get("end"), str) and covered >= manifest["end"]:
        return None
    if window_only:
        return True
    fresh = [line for line in lines if covered is None or str(line["at"]) > covered]
    if not fresh or len("".join(str(line["text"]) for line in fresh)) < MIN_SOURCE_CHARS:
        return None
    enough_messages = len(fresh) >= settings["dialogue_episode_refresh_messages"]
    elapsed = _elapsed_minutes(covered or manifest["start"], manifest["end"])
    if not enough_messages and (elapsed is None or elapsed < settings["dialogue_episode_refresh_minutes"]):
        return None
    return fresh, "messages" if enough_messages else "minutes"


def _elapsed_minutes(begin, end):
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(begin)) / timedelta(minutes=1)
    except (TypeError, ValueError):
        return None
