"""One role, one foreground mouth: a bounded process-local attention lease.

This is intentionally not a durable task or a delivery permission.  It only
coordinates *this process's* concurrent windows for one role so a private turn
and a group turn do not both generate a complete reply as if they were two
separate companions.  The wait is short and bounded; a slow window may still be
contended after the timeout, in which case the prompt gets an explicit transfer
note instead of being blocked indefinitely.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from companion_v2.execution.models import digest


@dataclass(frozen=True)
class AttentionLease:
    key: str
    turn_id: str
    window: str
    waited_ms: int
    contended: bool = False
    other_window: str = ""


class RoleAttention:
    def __init__(self, *, wait_seconds: float = 3.0, settings=None):
        if type(wait_seconds) not in (int, float) or wait_seconds < 0:
            raise ValueError("role attention wait must be a non-negative interval")
        self.wait_seconds = float(wait_seconds)
        self.settings = settings
        self._locks: dict[str, asyncio.Lock] = {}
        self._active: dict[str, AttentionLease] = {}

    def _wait_seconds(self, context) -> float:
        reader = getattr(self.settings, "read", None)
        if callable(reader):
            try:
                values = reader(context)
                value = values.get("person.cross_window_attention_wait_seconds") if isinstance(values, dict) else None
                if type(value) is int and 0 <= value <= 10:
                    return float(value)
            except Exception:
                pass
        return self.wait_seconds

    @staticmethod
    def key(context) -> str:
        scope, role = context.scope, context.role_binding.role
        return digest(["role.attention.v1", scope.installation_id, scope.bot_id, role.subject_id])

    def active(self, context):
        return self._active.get(self.key(context))

    async def acquire(self, context, turn_id: str, *, window: str = "") -> AttentionLease:
        key = self.key(context)
        lock = self._locks.setdefault(key, asyncio.Lock())
        started = time.monotonic()
        contended, other_window = False, ""
        wait_seconds = self._wait_seconds(context)
        try:
            if wait_seconds <= 0:
                if lock.locked():
                    active = self._active.get(key)
                    contended, other_window = True, active.window if active is not None else ""
                else:
                    await lock.acquire()
            else:
                await asyncio.wait_for(lock.acquire(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            active = self._active.get(key)
            contended = True
            other_window = active.window if active is not None else ""
        waited_ms = max(0, int((time.monotonic() - started) * 1000))
        lease = AttentionLease(key, turn_id, window, waited_ms, contended, other_window)
        if not contended:
            self._active[key] = lease
        return lease

    @staticmethod
    def note(lease: AttentionLease | None, *, min_wait_ms: int = 250) -> str:
        if lease is None:
            return ""
        if lease.contended:
            other = "群聊" if lease.other_window == "group" else "私聊" if lease.other_window == "private" else "另一个窗口"
            return ("【注意力转场】" + other + "那边仍在生成回复；你刚被叫到这边。"
                    "可以先用一句自然的话接住，或说明稍后细说；不要假装同时看见两边，也不要提及内部窗口、排队或精确时间。")
        if lease.waited_ms < min_wait_ms:
            return ""
        return ("【注意力转场】你刚在另一个窗口说话，随后才轮到这边；可以自然表现出一瞬间的转场感，"
                "但不要提及内部窗口、排队或精确时间，也不要因此敷衍。")

    def finish(self, lease: AttentionLease | None) -> None:
        if lease is None or lease.contended:
            return
        if self._active.get(lease.key) is not lease:
            return
        self._active.pop(lease.key, None)
        lock = self._locks.get(lease.key)
        if lock is not None and lock.locked():
            lock.release()


__all__ = ["AttentionLease", "RoleAttention"]
