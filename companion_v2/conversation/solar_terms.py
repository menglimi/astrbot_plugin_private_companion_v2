"""Optional, host supplied solar-term lookup used by date context.

The conversation layer never discovers a provider or performs network I/O. A
host may inject a small synchronous lookup object for a year; absent that
object the source is explicitly unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SolarTermLookup:
    status: str
    terms: tuple[tuple[date, tuple[str, ...]], ...] = ()


def lookup_solar_terms(provider, year: int) -> SolarTermLookup:
    if provider is None:
        return SolarTermLookup("unavailable")
    try:
        value = provider.lookup(year) if callable(getattr(provider, "lookup", None)) else provider(year)
    except Exception:
        return SolarTermLookup("unavailable")
    if value is None:
        return SolarTermLookup("unknown")
    if hasattr(value, "solar_terms") and hasattr(value, "year"):
        if value.year != year:
            return SolarTermLookup("unknown")
        rows = value.solar_terms
    elif isinstance(value, Mapping):
        rows = value.items()
    else:
        rows = value
    try:
        grouped: dict[date, list[str]] = {}
        for item in rows:
            if isinstance(item, Mapping):
                raw_day, raw_name = item.get("date"), item.get("name")
            else:
                raw_day, raw_name = item
            day = raw_day if isinstance(raw_day, date) else date.fromisoformat(raw_day)
            if day.year != year or type(raw_name) is not str or not raw_name.strip():
                return SolarTermLookup("unknown")
            grouped.setdefault(day, []).append(raw_name.strip())
        return SolarTermLookup("available", tuple((day, tuple(names)) for day, names in sorted(grouped.items())))
    except (TypeError, ValueError, AttributeError):
        return SolarTermLookup("unknown")


def names_on(lookup: SolarTermLookup, day: date) -> tuple[str, ...]:
    return next((names for item_day, names in lookup.terms if item_day == day), ())
