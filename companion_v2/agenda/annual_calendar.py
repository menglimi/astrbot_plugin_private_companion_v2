"""Read-only parser for explicitly supplied annual holiday and solar-term data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from typing import Mapping


SCHEMA = "companion.annual-calendar.v1"


@dataclass(frozen=True)
class CalendarDay:
    date: date
    holiday: str | None
    makeup_workday: str | None
    solar_terms: tuple[str, ...]


@dataclass(frozen=True)
class AnnualCalendar:
    year: int
    holiday_days: tuple[tuple[date, str], ...]
    makeup_workdays: tuple[tuple[date, str], ...]
    solar_terms: tuple[tuple[date, str], ...]

    def on(self, day: date) -> CalendarDay:
        if not isinstance(day, date) or day.year != self.year:
            raise ValueError("date must belong to this annual calendar")
        holiday = next((name for item_day, name in self.holiday_days if item_day == day), None)
        makeup = next((name for item_day, name in self.makeup_workdays if item_day == day), None)
        terms = tuple(name for item_day, name in self.solar_terms if item_day == day)
        return CalendarDay(day, holiday, makeup, terms)


def _day(value: object, year: int, field: str) -> date:
    if type(value) is not str:
        raise ValueError(field)
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(field) from error
    if result.year != year or result.isoformat() != value:
        raise ValueError(field)
    return result


def _name(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(field)
    return value.strip()


def _decode(payload: object) -> Mapping[str, object]:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if type(payload) is str:
        value = json.loads(payload)
        if isinstance(value, Mapping):
            return value
    raise ValueError("annual calendar must be a JSON object")


def parse_annual_calendar(payload: object) -> AnnualCalendar:
    """Parse the versioned canonical feed shape; performs no network or file I/O."""
    raw = _decode(payload)
    year = raw.get("year")
    if type(year) is not int or not 1 <= year <= 9999:
        raise ValueError("year")
    if raw.get("schema") != SCHEMA:
        raise ValueError("schema")

    holiday_map: dict[date, str] = {}
    holidays = raw.get("holidays", [])
    if not isinstance(holidays, list):
        raise ValueError("holidays")
    for item in holidays:
        if not isinstance(item, Mapping):
            raise ValueError("holiday")
        name = _name(item.get("name"), "holiday.name")
        start, end = _day(item.get("start"), year, "holiday.start"), _day(item.get("end"), year, "holiday.end")
        if end < start:
            raise ValueError("holiday.range")
        day = start
        while day <= end:
            previous = holiday_map.setdefault(day, name)
            if previous != name:
                raise ValueError("holiday.overlap")
            day += timedelta(days=1)

    makeup_map: dict[date, str] = {}
    workdays = raw.get("makeup_workdays", [])
    if not isinstance(workdays, list):
        raise ValueError("makeup_workdays")
    for item in workdays:
        if not isinstance(item, Mapping):
            raise ValueError("makeup_workday")
        day = _day(item.get("date"), year, "makeup_workday.date")
        name = _name(item.get("name", "调休上班"), "makeup_workday.name")
        if day in holiday_map or day in makeup_map:
            raise ValueError("makeup_workday.conflict")
        makeup_map[day] = name

    terms = raw.get("solar_terms", [])
    if not isinstance(terms, list):
        raise ValueError("solar_terms")
    term_rows, seen_terms = [], set()
    for item in terms:
        if not isinstance(item, Mapping):
            raise ValueError("solar_term")
        day = _day(item.get("date"), year, "solar_term.date")
        name = _name(item.get("name"), "solar_term.name")
        if (day, name) in seen_terms:
            raise ValueError("solar_term.duplicate")
        seen_terms.add((day, name))
        term_rows.append((day, name))

    return AnnualCalendar(year, tuple(sorted(holiday_map.items())), tuple(sorted(makeup_map.items())),
                          tuple(sorted(term_rows)))
