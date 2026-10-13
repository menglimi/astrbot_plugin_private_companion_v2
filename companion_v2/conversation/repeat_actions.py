"""V1-style literal repeat actions, durably decided before native sending."""

import json
import random

from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.memory.group.access import owner_key
from .group_interjection import day_key
from .group_observation import parse_moment
from .reset import boundary


PREFIX = "conversation.group_repeat_actions.v1:"


class GroupRepeatActions:
    """Only follow or interrupt; a skipped draw never opens a model reply."""

    def __init__(self, runtime):
        self.runtime = runtime

    def _key(self, context, event_id=None):
        key = PREFIX + owner_key(context)
        return key if event_id is None else key + ":event:" + digest(event_id)

    @staticmethod
    def _load(connection, key):
        row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    @staticmethod
    def _save(connection, key, record):
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, json.dumps(record, ensure_ascii=False, sort_keys=True)))

    def read(self, context, event_id):
        with self.runtime.transaction() as connection:
            return self._load(connection, self._key(context, event_id))

    def plan(self, context, event_id, text, *, at, burst, settings, used_today, timezone_name):
        """Draw once per event; used_today counts other autonomous replies.

        Successful and uncertain repeat sends reserve their own shared daily
        quota. Separate durable event rows prevent observation eviction from
        making an old uncertain send eligible for replay.
        """
        fingerprint = digest([context.key, event_id, text])
        with self.runtime.transaction() as connection:
            key, operation_key = self._key(context), self._key(context, event_id)
            saved = self._load(connection, operation_key)
            if saved is not None:
                if saved["fingerprint"] != fingerprint:
                    raise TaskError("group_repeat_event_changed", "the original repeat event changed")
                return dict(saved)
            state = self._load(connection, key) or {"day": "", "used_today": 0, "burst": {}, "reset": None}
            reset = boundary(self.runtime, context.scope)
            reset_at = reset["reset_at"] if reset else None
            if state["reset"] != reset_at:
                state.update(used_today=0, burst={}, reset=reset_at)
            day = day_key(at, timezone_name)
            if state["day"] != day:
                state["day"], state["used_today"] = day, 0
            operation = {"event_id": event_id, "fingerprint": fingerprint, "day": day, "reset": reset_at,
                         "action": "", "text": "", "image_path": "", "signature": "",
                         "state": "skipped", "reason": "repeat_no_burst"}
            count = (burst["distinct"] if settings["group_repeat_count_distinct_users_only"] else burst["count"]) if burst else 0
            if settings["enable_group_repeat_follow"] and burst and count >= settings["group_repeat_trigger_threshold"]:
                previous = state["burst"]
                last = parse_moment(previous.get("last_at"))
                same = (previous.get("signature") == burst["signature"] and last is not None
                        and 0 <= (at - last).total_seconds() <= settings["group_repeat_window_seconds"]
                        and burst["first_at"] <= last
                        and (not previous.get("last_event_id")
                             or previous["last_event_id"] in burst.get("event_ids", ())))
                if not same:
                    previous = {"signature": burst["signature"], "acted": False, "speakers": [],
                                "follow": settings["group_repeat_follow_probability"],
                                "interrupt": settings["group_repeat_interrupt_probability"]}
                new_speaker = context.actor.principal.native_account_id not in previous["speakers"]
                previous.update(last_at=stamp(at), last_event_id=event_id, speakers=list(burst["speakers"]))
                state["burst"] = previous
                operation["signature"] = burst["signature"]
                limit = settings["group_interject_max_daily"]
                if previous["acted"]:
                    operation["reason"] = "repeat_already_acted"
                elif limit <= 0 or state["used_today"] + used_today >= limit:
                    operation["reason"] = "repeat_daily_cap"
                else:
                    follow, interrupt = min(0.85, previous["follow"]), min(0.85, previous["interrupt"])
                    roll = random.random()
                    if roll >= min(0.95, follow + interrupt):
                        if not settings["group_repeat_count_distinct_users_only"] or new_speaker:
                            step = settings["group_repeat_interrupt_probability_step"]
                            previous["follow"], previous["interrupt"] = min(0.85, follow + step), min(0.85, interrupt + step)
                        operation["reason"] = "repeat_probability_skip"
                    else:
                        previous["acted"] = True
                        action = "interrupt" if roll < interrupt else "follow"
                        operation.update(action=action, state="planned", reason="repeat_" + action,
                            text=settings["group_repeat_interrupt_text"] if action == "interrupt" else text,
                            image_path=settings["group_repeat_interrupt_image_path"] if action == "interrupt" else "")
            self._save(connection, key, state)
            self._save(connection, operation_key, operation)
            return dict(operation)

    def begin(self, context, event_id, *, used_today, limit):
        """Claim once and reserve quota; started or unknown sends never replay."""
        with self.runtime.transaction() as connection:
            key, operation_key = self._key(context), self._key(context, event_id)
            state, saved = self._load(connection, key), self._load(connection, operation_key)
            if saved is None or saved["state"] != "planned":
                return False
            reset = boundary(self.runtime, context.scope)
            reset_at = reset["reset_at"] if reset else None
            if (state["day"] != saved["day"] or reset_at != saved["reset"]
                    or limit <= 0 or state["used_today"] + used_today >= limit):
                saved.update(state="skipped", reason="repeat_budget_or_window_changed")
                self._save(connection, operation_key, saved)
                return False
            saved["state"] = "started"
            state["used_today"] += 1
            self._save(connection, key, state)
            self._save(connection, operation_key, saved)
            return True

    def finish(self, context, event_id, *, state):
        if state not in ("returned", "unknown"):
            raise ValueError("invalid repeat send outcome")
        with self.runtime.transaction() as connection:
            key = self._key(context, event_id)
            saved = self._load(connection, key)
            if saved is not None and saved["state"] == "started":
                saved["state"] = state
                self._save(connection, key, saved)
