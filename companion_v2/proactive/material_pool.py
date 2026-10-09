"""Read-only projection of current, governed sources for proactive contact."""

from datetime import timedelta
import json

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import ScopeKind

from .balance_events import SOURCE_OWNER as BALANCE_OWNER
from .calendar_events import SOURCE_OWNER as CALENDAR_OWNER
from .events import SOURCE_OWNER as ACTIVITY_OWNER
from .journal_events import JOURNAL_SOURCE_OWNER
from .news_events import SOURCE_OWNER as NEWS_OWNER
from .official_alert_events import SOURCE_OWNER as ALERT_OWNER
from .screen_events import SOURCE_OWNER as SCREEN_OWNER
from .weather_change_events import SOURCE_OWNER as WEATHER_CHANGE_OWNER
from .weather_events import SOURCE_OWNER as WEATHER_OWNER


SOURCE_CATEGORIES = {
    ACTIVITY_OWNER: ("生活记录", "生活分享"),
    JOURNAL_SOURCE_OWNER: ("生活记录", "生活分享"),
    CALENDAR_OWNER: ("约定", "约定与提醒"),
    WEATHER_OWNER: ("环境与状态", "环境与状态变化"),
    WEATHER_CHANGE_OWNER: ("环境与状态", "环境与状态变化"),
    ALERT_OWNER: ("环境与状态", "环境与状态变化"),
    BALANCE_OWNER: ("环境与状态", "环境与状态变化"),
    NEWS_OWNER: ("资讯", "外部资讯"),
    SCREEN_OWNER: ("屏幕观察", "已授权屏幕观察"),
}
SOURCE_LABELS = {
    ACTIVITY_OWNER: "角色活动回执",
    JOURNAL_SOURCE_OWNER: "角色日记",
    CALENDAR_OWNER: "已接受约定",
    WEATHER_OWNER: "天气观测",
    WEATHER_CHANGE_OWNER: "天气变化",
    ALERT_OWNER: "官方气象预警",
    BALANCE_OWNER: "服务余额",
    NEWS_OWNER: "资讯源",
    SCREEN_OWNER: "授权屏幕回执",
}


def _text(value, limit=480):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _weather(value):
    if not isinstance(value, dict):
        return _text(value, 160)
    parts = [_text(value.get("condition"), 64)]
    temperature = value.get("temperature_c")
    if type(temperature) in (int, float):
        parts.append(f"{temperature:g}°C")
    humidity = value.get("humidity_pct")
    if type(humidity) in (int, float):
        parts.append(f"湿度 {humidity:g}%")
    return " · ".join(part for part in parts if part)


def _record_projection(record, settings, at):
    try:
        body = json.loads(record.payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    body.pop("_receipt", None)
    owner = record.reference.owner
    category, purpose = SOURCE_CATEGORIES[owner]
    expires_at = record.reference.expires_at

    if owner == ACTIVITY_OWNER:
        if at >= record.reference.issued_at + timedelta(seconds=settings.get("event_max_age_seconds", 3600)):
            return None
        title = "完成阅读" if body.get("event") == "reading_completed" else "角色生活片段"
        detail = _text(body.get("excerpt") or body.get("meaning"))
        note = _text(body.get("subjective_reflection"), 240)
        expires_at = record.reference.issued_at + timedelta(seconds=settings.get("event_max_age_seconds", 3600))
    elif owner == JOURNAL_SOURCE_OWNER:
        if at >= record.reference.issued_at + timedelta(seconds=settings.get("event_max_age_seconds", 3600)):
            return None
        title = ("梦境记录" if body.get("kind") == "dream" else "日记记录") + " · " + _text(body.get("local_date"), 32)
        detail = _text(body.get("passage") or body.get("meaning"))
        note = "梦境记录属于角色的主观记忆。" if body.get("kind") == "dream" else ""
        expires_at = record.reference.issued_at + timedelta(seconds=settings.get("event_max_age_seconds", 3600))
    elif owner == CALENDAR_OWNER:
        title = _text(body.get("title"), 160) or "已接受的约定"
        detail = " · ".join(part for part in (_text(body.get("detail"), 220),
            _text(body.get("local_start") or body.get("starts_at"), 64)) if part)
        note = ""
    elif owner == WEATHER_OWNER:
        title = "当前天气 · " + (_text(body.get("role_location"), 64) or "角色所在地")
        detail = _weather(body)
        note = "观测时间 " + _text(body.get("observed_at"), 64)
    elif owner == WEATHER_CHANGE_OWNER:
        title = "天气变化 · " + (_text(body.get("change_kind"), 80) or "观测变化")
        detail = " → ".join(part for part in (_weather(body.get("previous")), _weather(body.get("current"))) if part)
        note = ""
    elif owner == ALERT_OWNER:
        alert = body.get("alert") if isinstance(body.get("alert"), dict) else {}
        title = _text(alert.get("title") or alert.get("name"), 160) or "官方气象预警"
        severity = _text(alert.get("severity") or alert.get("level"), 40)
        detail = _text(alert.get("description") or alert.get("text"), 360)
        note = " · ".join(part for part in (_text(body.get("alert_city"), 64), severity) if part)
    elif owner == BALANCE_OWNER:
        title = "服务余额提醒"
        detail = "极低余额" if body.get("level") == "critical" else "低余额"
        if settings.get("balance_include_amount_in_message") is True and "amount" in body:
            detail += " · " + _text(str(body.get("amount")) + str(body.get("currency") or ""), 64)
        note = ""
    elif owner == NEWS_OWNER:
        title = _text(body.get("title"), 180) or "外部资讯"
        detail = _text(body.get("summary"), 360)
        note = _text(body.get("source"), 100)
    else:
        title = "已授权屏幕观察"
        detail = _text(body.get("interpretation"), 360)
        note = _text(body.get("observed_at"), 64)

    return {"id": digest([record.reference.source_id, record.reference.version.lineage_id,
                           record.reference.version.revision])[:20],
            "category": category, "purpose": purpose, "title": title, "detail": detail,
            "note": note, "source": SOURCE_LABELS[owner], "captured_at": record.reference.issued_at.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None}


def _latest_conversation(schedule, context, at, settings):
    if context.scope.kind is not ScopeKind.PRIVATE:
        return None
    row = schedule.runtime.read_one("""SELECT f.state AS flow_state, b.batch_id FROM conversation_flows f
        JOIN conversation_batches b ON b.batch_id = f.batch_id WHERE f.route_key = ?
        ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,))
    if row is None:
        return None
    try:
        _, _, event = schedule._origin(context, row["batch_id"], at)
        if any(getattr(event, name, ()) for name in ("images", "audios", "videos", "forwards", "quotes")):
            return None
        source = schedule.messages._read_source(event.source, context, event.capability, at)
        if source.content_hash != event.input_hash or digest(source.payload) != source.content_hash:
            return None
        expires_at = event.received_at + timedelta(seconds=settings.get("event_max_age_seconds", 3600))
        if at >= expires_at:
            return None
        return {"id": digest([event.scoped_key, event.input_hash])[:20], "category": "对话",
                "purpose": "日常承接、关系表达", "title": "最近私聊内容",
                "detail": _text(source.payload), "note": "",
                "source": "当前私聊", "captured_at": event.received_at.isoformat(),
                "expires_at": expires_at.isoformat()}
    except (TaskError, KeyError, TypeError, ValueError, UnicodeError, OSError, AttributeError):
        return None


def read_material_pool(schedule, context, *, observed_at, settings):
    """Return only current, recipient-readable materials for one private target."""
    if context.scope.kind is not ScopeKind.PRIVATE:
        return {"observed_at": observed_at.isoformat(), "items": [], "count": 0}
    records = schedule.contacts.sources.list_readable_current(
        context.scope,
        owners=tuple(SOURCE_CATEGORIES),
        expected_recipients=context.audience.recipients,
        resolved=context.actor,
        capability="text",
        observed_at=observed_at,
        authorizer=schedule.tasks.identity,
    )
    items = [item for record in records
             if (item := _record_projection(record, settings, observed_at)) is not None]
    conversation = _latest_conversation(schedule, context, observed_at, settings)
    if conversation is not None:
        items.append(conversation)
    items.sort(key=lambda item: (item["captured_at"], item["id"]), reverse=True)
    return {"observed_at": observed_at.isoformat(), "items": items[:128], "count": len(items[:128])}
