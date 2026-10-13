"""Recorded social impressions imported alongside a member's description."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MemberMemory:
    title: str
    content: str
    privacy: str = "internal"
    weight: int = 50
    enabled: bool = True
    source: str = ""
    updated_at: float = 0

    @property
    def document(self):
        return {"title": self.title, "content": self.content, "privacy": self.privacy,
                "weight": self.weight, "enabled": self.enabled, "source": self.source,
                "updated_at": self.updated_at}

    @classmethod
    def restore(cls, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("content"), str):
            raise ValueError("member memory must contain text")
        content = raw["content"].strip()
        if not content:
            raise ValueError("member memory content must not be blank")
        enabled = raw.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError("member memory enabled must be boolean")
        try:
            weight = int(raw.get("weight", 50))
            updated_at = float(raw.get("updated_at", 0))
        except (TypeError, ValueError, OverflowError):
            weight, updated_at = 50, 0
        if not math.isfinite(updated_at):
            updated_at = 0
        return cls(str(raw.get("title") or "").strip(), content,
                   str(raw.get("privacy") or "internal").strip().lower(), weight, enabled,
                   str(raw.get("source") or "").strip(), updated_at)


def member_memories(values):
    """A malformed observation must not discard the rest of a member profile."""
    if not isinstance(values, (list, tuple)):
        return ()
    result = []
    for value in values:
        try:
            memory = value if isinstance(value, MemberMemory) else MemberMemory.restore(value)
        except (TypeError, ValueError):
            continue
        if memory not in result:
            result.append(memory)
    return tuple(result)


__all__ = ["MemberMemory", "member_memories"]
