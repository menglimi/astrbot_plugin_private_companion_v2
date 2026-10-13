"""Pure normalization and deduplication for provider-supplied weather/news JSON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Mapping


@dataclass(frozen=True)
class ParseIssue:
    index: int
    code: str


@dataclass(frozen=True)
class ParseBatch:
    items: tuple[object, ...]
    issues: tuple[ParseIssue, ...]


@dataclass(frozen=True)
class WeatherAlert:
    identifier: str
    title: str
    severity: str
    starts_at: datetime
    ends_at: datetime
    description: str


@dataclass(frozen=True)
class WeatherSnapshot:
    provider: str
    location: str
    observed_at: datetime
    temperature_c: float
    condition: str
    humidity_pct: float | None
    wind_kph: float | None
    alerts: tuple[WeatherAlert, ...]
    weather_code: int | None = None


@dataclass(frozen=True)
class NewsItem:
    source: str
    identifier: str
    title: str
    url: str
    summary: str
    published_at: datetime | None
    category: str = ""


def _text(value: object, field: str, *, optional: bool = False) -> str:
    if value is None and optional:
        return ""
    if type(value) is not str or (not optional and not value.strip()):
        raise ValueError(field)
    return value.strip()


def _timestamp(value: object, field: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise ValueError(field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(field) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(field)
    return parsed


def _number(value: object, field: str, *, optional: bool = False, minimum: float | None = None,
            maximum: float | None = None) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(field)
    number = float(value)
    if minimum is not None and number < minimum or maximum is not None and number > maximum:
        raise ValueError(field)
    return number


def _alert(raw: object) -> WeatherAlert:
    if not isinstance(raw, Mapping):
        raise ValueError("alert")
    starts = _timestamp(raw.get("starts_at"), "alert.starts_at")
    ends = _timestamp(raw.get("ends_at"), "alert.ends_at")
    if ends < starts:
        raise ValueError("alert.range")
    identifier = _text(raw.get("id"), "alert.id", optional=True)
    return WeatherAlert(identifier, _text(raw.get("title"), "alert.title"),
                        _text(raw.get("severity"), "alert.severity"), starts, ends,
                        _text(raw.get("description"), "alert.description", optional=True))


def parse_weather_response(payload: object) -> tuple[WeatherSnapshot, tuple[ParseIssue, ...]]:
    """Parse the provider-neutral JSON envelope after a provider adapter maps its response."""
    if not isinstance(payload, Mapping):
        raise ValueError("weather response must be an object")
    current, location = payload.get("current"), payload.get("location")
    if not isinstance(current, Mapping):
        raise ValueError("current")
    if isinstance(location, Mapping):
        location = location.get("name")
    alerts_raw = payload.get("alerts", [])
    if not isinstance(alerts_raw, list):
        raise ValueError("alerts")
    alerts, issues, seen = [], [], set()
    for index, item in enumerate(alerts_raw):
        try:
            alert = _alert(item)
        except (TypeError, ValueError):
            issues.append(ParseIssue(index, "invalid_alert"))
            continue
        key = ("id", alert.identifier) if alert.identifier else (
            "title_time", _fold(alert.title), alert.starts_at.isoformat())
        if key in seen:
            issues.append(ParseIssue(index, "duplicate_alert"))
            continue
        seen.add(key)
        alerts.append(alert)
    snapshot = WeatherSnapshot(
        provider=_text(payload.get("provider"), "provider"),
        location=_text(location, "location"),
        observed_at=_timestamp(payload.get("observed_at"), "observed_at"),
        temperature_c=_number(current.get("temperature_c"), "temperature_c"),
        condition=_text(current.get("condition"), "condition"),
        humidity_pct=_number(current.get("humidity_pct"), "humidity_pct", optional=True, minimum=0, maximum=100),
        wind_kph=_number(current.get("wind_kph"), "wind_kph", optional=True, minimum=0),
        alerts=tuple(alerts),
        weather_code=current.get("weather_code"),
    )
    if snapshot.weather_code is not None and (type(snapshot.weather_code) is not int or
                                              not 0 <= snapshot.weather_code <= 99):
        raise ValueError("current.weather_code")
    return snapshot, tuple(issues)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("url")
    host = parts.hostname.lower()
    if parts.port:
        host += f":{parts.port}"
    query = sorted((key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True)
                   if not key.casefold().startswith("utm_") and key.casefold() not in {"gclid", "fbclid"})
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def canonical_news_url(value: str) -> str:
    return _canonical_url(value)


def _news_row(raw: object, default_source: str) -> tuple[NewsItem, str, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("row")
    title = _text(raw.get("title", raw.get("headline")), "title")
    source_value = raw.get("source", raw.get("publisher", default_source))
    if isinstance(source_value, Mapping):
        source_value = source_value.get("name", "")
    source = _text(source_value, "source", optional=True)
    identifier = _text(raw.get("id", raw.get("guid")), "id", optional=True)
    url = _text(raw.get("url", raw.get("link")), "url", optional=True)
    canonical = _canonical_url(url)
    summary = _text(raw.get("summary", raw.get("snippet", raw.get("description", raw.get("content_text")))),
                    "summary", optional=True)
    published = _timestamp(raw.get("published_at", raw.get("published", raw.get("date_published"))),
                           "published_at", optional=True)
    category_value = raw.get("category", raw.get("section", raw.get("categories", "")))
    if isinstance(category_value, Mapping):
        category_value = category_value.get("name", "")
    elif isinstance(category_value, (list, tuple)):
        category_value = next((value for value in category_value if type(value) is str and value.strip()), "")
    category = " ".join(category_value.split())[:48] if type(category_value) is str else ""
    item = NewsItem(source, identifier, title, url, summary, published, category)
    source_key = source.casefold()
    url_key = canonical
    fallback = _fold(title) + "|" + (published.date().isoformat() if published else source_key)
    return item, source_key + "|" + identifier.casefold() if identifier else "", url_key or fallback


def parse_news_response(payload: object) -> ParseBatch:
    """Normalize common JSON news item aliases and keep the first item per stable key."""
    if isinstance(payload, list):
        rows, default_source = payload, ""
    elif isinstance(payload, Mapping):
        rows = next((payload[key] for key in ("items", "articles", "results") if key in payload), None)
        default_source = _text(payload.get("source", payload.get("publisher")), "source", optional=True)
    else:
        raise ValueError("news response must be an object or list")
    if not isinstance(rows, list):
        raise ValueError("news response must contain items, articles or results")
    items, issues, seen_ids, seen_urls = [], [], set(), set()
    for index, raw in enumerate(rows):
        try:
            item, id_key, content_key = _news_row(raw, default_source)
        except (TypeError, ValueError):
            issues.append(ParseIssue(index, "invalid_news_item"))
            continue
        if id_key and id_key in seen_ids or content_key and content_key in seen_urls:
            issues.append(ParseIssue(index, "duplicate_news_item"))
            continue
        if id_key:
            seen_ids.add(id_key)
        if content_key:
            seen_urls.add(content_key)
        items.append(item)
    return ParseBatch(tuple(items), tuple(issues))
