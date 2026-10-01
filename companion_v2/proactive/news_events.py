"""Opt-in, source-backed sharing of recent administrator-configured news."""

import asyncio
from datetime import datetime, timedelta
import json

from companion_v2.conversation.messages import source_from_document
from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import ScopeKind, SourceRef, VersionRef
from companion_v2.sources.governance import bind
from companion_v2.sources.models import SourceRecord
from .news_sources import news_failure

from .contact_models import ContactIntent
from .external_materials import ParseBatch, canonical_news_url
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


SOURCE_OWNER = "proactive.news"
EVENT_WINDOW = timedelta(minutes=30)
MAX_AGE = timedelta(hours=24)
RETRY = timedelta(minutes=5)
MAX_SEEN = 128
MEANING = ("这是外部资讯源提供的标题和摘要，未经角色独立核实；"
           "不要把它说成亲历、刚刚发生或已阅读完整原文。只有自然相关时才分享，保留来源、链接和可用日期。")


class NewsContactEvents:
    def __init__(self, contacts, port):
        self.contacts, self.port = contacts, port
        self.runtime = contacts.runtime
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)

    def _port(self, preferences):
        resolver = getattr(self.port, "for_settings", None)
        return resolver(preferences.values) if callable(resolver) else self.port

    def close(self):
        self.guard.close()

    def _settings(self, context, preferences):
        port = self._port(preferences) if self.port is not None else None
        kind = preferences.values["news_source_kind"]
        source_enabled = (preferences.values["web_exploration_enabled"] if kind == "search" else
                          preferences.values["news_daily_hot_read_enabled"] if kind == "hot" else
                          preferences.values["news_share_enabled"])
        if (port is None or context.scope.kind is not ScopeKind.PRIVATE
                or not preferences.values["automatic_enabled"] or not source_enabled
                or preferences.reason("news")):
            return None
        return digest([port.fingerprint, preferences.values["news_source_kind"],
                       preferences.values["news_source_uid"], preferences.values["news_source_url"],
                       preferences.values["news_check_interval_minutes"],
                       preferences.values["web_exploration_min_interval_hours"],
                       preferences.values["web_exploration_interests"],
                       preferences.values["news_hot_sources"],
                       preferences.values["external_event_self_link_enabled"],
                       preferences.values["external_event_self_link_weight"],
                       preferences.values["external_event_self_link_cooldown_hours"],
                       preferences.snapshot.change_sequence])

    @staticmethod
    def _poll_interval(preferences):
        configured = timedelta(minutes=preferences.values["news_check_interval_minutes"])
        kind = preferences.values["news_source_kind"]
        if kind == "search":
            return max(configured, timedelta(hours=preferences.values["web_exploration_min_interval_hours"]))
        if kind == "hot":
            return max(configured, timedelta(days=1))
        return configured

    def _self_link_cooled_down(self, context, preferences, at):
        if not preferences.values["external_event_self_link_enabled"]:
            return False
        hours = preferences.values["external_event_self_link_cooldown_hours"]
        if not hours:
            return False
        row = self.runtime.read_one("""SELECT MAX(created_at) AS latest FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = 'news'""", (context.key,))
        return bool(row and row["latest"] and at < datetime.fromisoformat(row["latest"]) + timedelta(hours=hours))

    def _row(self, context):
        return self.runtime.read_one("SELECT * FROM proactive_news_polls WHERE origin_key = ?", (context.key,))

    def _source(self, preferences):
        resolver = getattr(self.port, "for_settings", None)
        return resolver(preferences.values) if callable(resolver) else self.port

    def diagnostic(self, context, preferences):
        """Return only bounded, non-secret fetch state for the management page."""
        try:
            port = self._source(preferences)
            source = {"ready": port is not None,
                      "kind": getattr(port, "kind", "") if port is not None else "",
                      "label": getattr(port, "source_label", "") if port is not None else ""}
        except (ValueError, TypeError):
            port, source = None, {"ready": False, "kind": "", "label": ""}
        key = "proactive.news.status:" + context.key
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
        status = {}
        if row is not None:
            try:
                value = json.loads(row["value"])
                if type(value) is dict:
                    status = value
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        failure = status.get("failure")
        if type(failure) is not dict:
            failure = None
        item_count = status.get("item_count", 0)
        if type(item_count) is not int or item_count < 0:
            item_count = 0
        return {"source": source, "last_attempt_at": status.get("last_attempt_at"),
                "last_checked_at": status.get("last_checked_at"),
                "failure": failure, "item_count": item_count,
                "candidate": bool(status.get("candidate", False))}

    def _save_diagnostic(self, context, value):
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                ("proactive.news.status:" + context.key, payload))

    async def probe(self, context, preferences):
        """Fetch a source for diagnostics without changing polling or contact state."""
        attempt_at = self.contacts.tasks.now()
        try:
            port = self._source(preferences)
            if port is None:
                value = {"last_attempt_at": stamp(attempt_at), "last_checked_at": None,
                         "failure": {"code": "news_source_disabled", "http_status": None,
                                     "provider_code": None}, "item_count": 0, "candidate": False}
            else:
                batch = await asyncio.wait_for(port.fetch(), timeout=10)
                if type(batch) is not ParseBatch:
                    raise ValueError("news port returned an invalid batch")
                checked_at = self.contacts.tasks.now()
                value = {"last_attempt_at": stamp(attempt_at), "last_checked_at": stamp(checked_at),
                         "failure": None, "item_count": len(batch.items), "candidate": False}
        except Exception as error:
            value = {"last_attempt_at": stamp(attempt_at), "last_checked_at": None,
                     "failure": news_failure(error), "item_count": 0, "candidate": False}
        self._save_diagnostic(context, value)
        return self.diagnostic(context, preferences)

    @staticmethod
    def _opportunity(context, event):
        return Opportunity(event["id"], context.scope,
            datetime.fromisoformat(event["opened_at"]), datetime.fromisoformat(event["expires_at"]))

    def _candidate(self, context, row, settings_hash, at):
        if row is None or row["settings_hash"] != settings_hash or row["event_json"] is None:
            return None
        event = json.loads(row["event_json"])
        opportunity = self._opportunity(context, event)
        if not opportunity.opened_at <= at < opportunity.expires_at:
            return None
        task_id = self.contacts.task_id(context, opportunity)
        if (self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,))
                or self.runtime.read_one("SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,))):
            return None
        return opportunity, event

    def select(self, context, preferences, at):
        settings_hash = self._settings(context, preferences)
        if settings_hash is None:
            return None
        row = self._row(context)
        pending = self._candidate(context, row, settings_hash, at)
        if pending is not None:
            return pending[0], {"settings_hash": settings_hash}
        if row is not None and row["settings_hash"] == settings_hash:
            if row["retry_after"] and at < datetime.fromisoformat(row["retry_after"]):
                return None
            if row["checked_at"] and at < datetime.fromisoformat(row["checked_at"]) + self._poll_interval(preferences):
                return None
        opportunity = Opportunity("news-poll-" + digest([context.key, stamp(at)]),
            context.scope, at, at + EVENT_WINDOW)
        return opportunity, {"settings_hash": settings_hash}

    def _save(self, context, settings_hash, at, *, checked, retry_after=None, seen=(), event=None):
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO proactive_news_polls
                (origin_key, settings_hash, checked_at, retry_after, seen_json, event_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(origin_key) DO UPDATE SET settings_hash=excluded.settings_hash,
                    checked_at=excluded.checked_at, retry_after=excluded.retry_after,
                    seen_json=excluded.seen_json, event_json=excluded.event_json""",
                (context.key, settings_hash, stamp(at) if checked else None,
                 stamp(retry_after) if retry_after else None, encode(tuple(seen)[-MAX_SEEN:]),
                 encode(event) if event is not None else None))

    def _record(self, context, event):
        opportunity = self._opportunity(context, event)
        article = event["article"]
        body = {"event": "external_news_item", "feed": event.get("feed", ""),
                "source": article["source"], "title": article["title"], "summary": article["summary"],
                "url": article["url"], "published_at": article["published_at"],
                "retrieved_at": event["opened_at"], "meaning": MEANING}
        payload = encode({**body, "_receipt": {"context": json.loads(encode(context)),
                                             "event_id": event["id"], "settings_hash": event["settings_hash"]}})
        identifier = "contact-news-source-" + digest([context.key, event["id"]])
        source = SourceRef(identifier, SOURCE_OWNER, context.scope, VersionRef(identifier, 1),
                           opportunity.opened_at, opportunity.expires_at)
        return SourceRecord(source, context.audience, digest(payload), payload)

    def _project(self, context, event, at):
        record = self._record(context, event)
        require(self.contacts.sources.publish(record, observed_at=at))
        require(self.contacts.sources.validate_reference_for_audience(
            record.reference, recipient=context.actor.subject, observed_at=at))
        opportunity = self._opportunity(context, event)
        marker = {"event_id": event["id"], "settings_hash": event["settings_hash"],
                  "source": json.loads(encode(record.reference))}
        settings = require(self.contacts.preferences.read(context, observed_at=at)).values
        weight = 1.0
        if settings["external_event_self_link_enabled"]:
            interests = [item.casefold() for item in settings["web_exploration_interests"].replace("，", ",").split(",")
                         if len(item.strip()) >= 2]
            article_text = (event["article"]["title"] + " " + event["article"]["summary"]).casefold()
            matches = sum(1 for item in interests if item.strip() in article_text)
            if matches:
                weight = min(settings["external_event_self_link_weight"], 1.0 + 0.25 * matches)
        thought = Thought("news-thought-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
            "有一条带出处和日期的新资讯。先仅依据来源提供的标题和摘要整理一两句简明内容，"
            "再判断它是否和自己的兴趣、身份或近况自然相关；可以跳过。不要补写来源中没有的事实，"
            "分享时保留出处、链接和可用日期，并说明这是资讯材料而非亲历或完整阅读。",
            EvidenceSnapshot(context.scope, at, (record.reference,)), weight)
        return opportunity, (ContactIntent("news", thought),), marker

    async def prepare(self, context, marker):
        if type(marker) is not dict or set(marker) != {"settings_hash"}:
            return None
        at = self.contacts.tasks.now()
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        settings_hash = self._settings(context, preferences)
        if settings_hash is None or settings_hash != marker["settings_hash"]:
            return None
        row = self._row(context)
        pending = self._candidate(context, row, settings_hash, at)
        if pending is not None:
            return self._project(context, pending[1], at)
        if self.select(context, preferences, at) is None:
            return None
        try:
            port = self._port(preferences)
            if port is None:
                return None
            batch = await asyncio.wait_for(port.fetch(), timeout=10)
            if type(batch) is not ParseBatch:
                raise ValueError("news port returned an invalid batch")
        except Exception as error:
            at = self.contacts.tasks.now()
            preferences = require(self.contacts.preferences.read(context, observed_at=at))
            if self._settings(context, preferences) == settings_hash:
                seen = json.loads(row["seen_json"]) if row is not None else ()
                self._save(context, settings_hash, at, checked=False, retry_after=at + RETRY, seen=seen)
                self._save_diagnostic(context, {"last_attempt_at": stamp(at), "last_checked_at": None,
                    "failure": news_failure(error), "item_count": 0, "candidate": False})
            return None
        at = self.contacts.tasks.now()
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        if self._settings(context, preferences) != settings_hash:
            return None
        row = self._row(context)
        seen = json.loads(row["seen_json"]) if row is not None else []
        candidates = []
        for item in batch.items[:100]:
            try:
                published = item.published_at
                url = canonical_news_url(item.url)
                if (not url
                        or published is not None and not timedelta(0) <= at - published <= MAX_AGE
                        or not 1 <= len(item.title) <= 240 or len(item.summary) > 1000
                        or len(item.source) > 100 or len(url) > 2048):
                    continue
                key = digest(url)
                if key not in seen:
                    candidates.append((published, key, item, url))
            except (TypeError, ValueError, AttributeError):
                continue
        event = None
        if candidates:
            published, key, item, url = max(candidates, key=lambda candidate: (
                candidate[0] or at, candidate[1]))
            expires = min(at + EVENT_WINDOW, published + MAX_AGE) if published else at + EVENT_WINDOW
            event = {"id": "news-" + digest([context.key, settings_hash, key]),
                     "opened_at": stamp(at), "expires_at": stamp(expires),
                     "settings_hash": settings_hash, "key": key,
                     "feed": port.source_label,
                     "article": {"source": item.source or port.source_label,
                                 "title": item.title, "summary": item.summary, "url": url,
                                 "published_at": stamp(published) if published else None}}
            seen.append(key)
        self._save(context, settings_hash, at, checked=True, seen=seen, event=event)
        self._save_diagnostic(context, {"last_attempt_at": stamp(at), "last_checked_at": stamp(at),
            "failure": None, "item_count": len(batch.items), "candidate": event is not None})
        if event is not None and self._self_link_cooled_down(context, preferences, at):
            return None
        return self._project(context, event, at) if event is not None else None

    def _validate_source(self, record, at):
        try:
            receipt = json.loads(record.payload)["_receipt"]
            context = TaskContext.restore(receipt["context"])
            preferences = require(self.contacts.preferences.read(context, observed_at=at))
            row = self._row(context)
            if (self._settings(context, preferences) != receipt["settings_hash"] or row is None
                    or row["settings_hash"] != receipt["settings_hash"] or row["event_json"] is None):
                raise ValueError("news settings or event changed")
            event = json.loads(row["event_json"])
            opportunity = self._opportunity(context, event)
            if (event["id"] != receipt["event_id"] or not opportunity.opened_at <= at < opportunity.expires_at
                    or record != self._record(context, event) or record.content_hash != digest(record.payload)):
                raise ValueError("news source changed")
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_news_changed", "original news source is no longer current") from error

    def validate(self, context, marker, at):
        if type(marker) is not dict or set(marker) != {"event_id", "settings_hash", "source"}:
            raise TaskError("contact_news_invalid", "news marker is invalid")
        try:
            source = source_from_document(marker["source"])
            row = self._row(context)
            event = json.loads(row["event_json"]) if row is not None and row["event_json"] else None
            if (source.owner != SOURCE_OWNER or source.scope != context.scope or event is None
                    or event["id"] != marker["event_id"] or event["settings_hash"] != marker["settings_hash"]
                    or source != self._record(context, event).reference):
                raise ValueError("news marker changed")
            require(self.contacts.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_news_changed", "news marker is no longer current") from error
