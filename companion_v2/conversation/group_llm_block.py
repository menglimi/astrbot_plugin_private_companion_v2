"""Temporary per-group halt of model replies.

V1 的「关闭 LLM」是群内一条可恢复的临时封锁，不是配置项：它不改变群回复设置，
重启后仍应保持，直到有人开启。这里只保存这一条运行时状态，读取时不做别的事。

状态存在 `runtime_metadata`，键按群四元组派生，与角色和会话无关——封锁的是
「这个群里的模型回复」，换人格或换会话仍视为同一个群。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from companion_v2.execution.models import digest, encode, stamp

PREFIX = "conversation.group_llm_block.v1:"


def group_block_key(*, platform_id, account_id, bot_id, group_id):
    if not all(type(value) is str and value for value in (platform_id, account_id, bot_id, group_id)):
        raise ValueError("group block key requires the four native route values")
    return PREFIX + digest([platform_id, account_id, bot_id, group_id])


class GroupLLMBlock:
    """Read, set and clear one group's temporary reply block."""

    def __init__(self, runtime, now=None):
        self.runtime = runtime
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _read(self, key):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
        if row is None:
            return None
        value = json.loads(row["value"])
        return value if isinstance(value, dict) else None

    def status(self, key):
        value = self._read(key)
        return value if value is not None and value.get("state") == "blocked" else None

    def status_for_target(self, target):
        """Return the block for a real group target; tolerate non-group stubs."""
        values = tuple(getattr(target, name, None)
                       for name in ("platform_id", "account_id", "bot_id", "group_id"))
        if not all(type(value) is str and value for value in values):
            return None
        return self.status(group_block_key(
            platform_id=values[0], account_id=values[1], bot_id=values[2], group_id=values[3]))

    def block(self, key, *, operator, reason=""):
        current = self.status(key)
        if current is not None:
            return {**current, "replayed": True}
        previous = self._read(key) or {}
        value = {
            "state": "blocked",
            "started_at": stamp(self.now()),
            "operator": str(operator)[:128],
            "reason": " ".join(str(reason).split())[:256],
            "revision": int(previous.get("revision") or 0) + 1,
        }
        with self.runtime.transaction() as connection:
            connection.execute(
                "INSERT INTO runtime_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, encode(value)))
        return {**value, "replayed": False}

    def release(self, key, *, operator):
        current = self.status(key)
        if current is None:
            return None
        previous = self._read(key) or {}
        value = {
            "state": "released",
            "released_at": stamp(self.now()),
            "operator": str(operator)[:128],
            "reason": "released after " + str(current.get("started_at") or ""),
            "revision": int(previous.get("revision") or 0) + 1,
        }
        with self.runtime.transaction() as connection:
            connection.execute(
                "INSERT INTO runtime_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, encode(value)))
        return current


def minutes_since(started_at, now):
    """Bounded whole minutes for the release receipt; never invents a duration."""
    try:
        started = datetime.fromisoformat(str(started_at))
    except (TypeError, ValueError):
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    delta = now - started
    return max(0, int(delta.total_seconds() // 60))
