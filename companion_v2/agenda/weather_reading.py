"""Reuse located weather observations for the cottage's read-only view."""

import asyncio
from datetime import timedelta

from .weather_material import planning_weather_material


REFRESH_INTERVAL = timedelta(minutes=5)
MINIMUM_REFRESH_INTERVAL = timedelta(seconds=30)


class WeatherReading:
    """One role page keeps one observation and shares overlapping reads."""

    def __init__(self):
        self.key = None
        self.material = None
        self.fetched_at = None
        self.attempted_at = None
        self.failed = False
        self.pending = None

    async def read(self, port, location, *, max_age, now, force=False):
        key = (port, location, max_age)
        if key != self.key:
            self.key, self.material, self.fetched_at, self.attempted_at = key, None, None, None
            self.failed, self.pending = False, None
        at = now()
        refresh_interval = timedelta(minutes=getattr(port, "refresh_minutes", 5))
        interval = MINIMUM_REFRESH_INTERVAL if force else refresh_interval
        throttled = bool(force and self.attempted_at is not None
                         and timedelta(0) <= at - self.attempted_at < MINIMUM_REFRESH_INTERVAL)
        if (not throttled and (self.attempted_at is None or at - self.attempted_at >= interval
                or at < self.attempted_at)):
            if self.pending is None:
                self.pending = asyncio.create_task(self._fetch(port, location, max_age, now, key, force))
            pending = self.pending
            try:
                await pending
            finally:
                if self.pending is pending:
                    self.pending = None
        at = now()
        if key != self.key or self.material is None:
            return {"state": "unavailable", "location": location.name}
        from datetime import datetime
        expired = datetime.fromisoformat(self.material["valid_until"]) <= at
        if expired:
            return {"state": "unavailable", "location": location.name}
        return {"state": "stale" if self.failed else "live", "location": location.name,
                "condition": self.material["condition"], "temperature_c": self.material["temperature_c"],
                "provider": self.material["provider"], "observed_at": self.material["observed_at"],
                "valid_until": self.material["valid_until"], "fetched_at": self.fetched_at.isoformat(),
                "refresh_after": (self.attempted_at + refresh_interval).isoformat(),
                **({"refresh_throttled": True} if throttled else {})}

    async def _fetch(self, port, location, max_age, now, key, force):
        material = None
        try:
            if port is not None:
                fetch = getattr(port, "refresh", port.fetch) if force else port.fetch
                snapshot = await asyncio.wait_for(fetch(location), timeout=6)
                material = planning_weather_material(snapshot, location, now(), max_age=max_age)
        except Exception:
            pass
        if key != self.key:
            return
        at = now()
        self.attempted_at = at
        self.failed = material is None
        if material is not None:
            self.material, self.fetched_at = material, at
