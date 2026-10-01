"""A clock whose value changes only when a test or caller advances it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class DeterministicClock:
    """UTC-only clock for replayable state and migration tests."""

    _current: datetime

    def __post_init__(self) -> None:
        if self._current.tzinfo is None or self._current.utcoffset() is None:
            raise ValueError("DeterministicClock requires an aware datetime")
        self._current = self._current.astimezone(timezone.utc)

    @classmethod
    def at(cls, value: datetime) -> "DeterministicClock":
        return cls(value)

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise ValueError("DeterministicClock cannot move backwards")
        self._current += delta
        return self._current

    def set(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("DeterministicClock requires an aware datetime")
        normalized = value.astimezone(timezone.utc)
        if normalized < self._current:
            raise ValueError("DeterministicClock cannot move backwards")
        self._current = normalized
        return self._current
