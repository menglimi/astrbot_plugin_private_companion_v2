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
MAX_FEED_ITEMS = 32
MEANING = ("这是外部资讯源提供的标题和摘要，未经角色独立核实；"
           "不要把它说成亲历、刚刚发生或已阅读完整原文。只有自然相关时才分享；"
           "来源、链接和发布日期由程序留存，主动正文不附出处页脚，待对方追问时再给。")


def news_provenance(material):
    """Capture attribution from verified input, separately from the visible body."""
    if (type(material) is not dict or material.get("event") != "external_news_item"
            or type(material.get("source")) is not str or type(material.get("published_at")) is not str
            or type(material.get("url")) is not str):
        raise ValueError("news attribution is incomplete")
    source = " ".join(material["source"].split())
    published = datetime.fromisoformat(material["published_at"])
    url = canonical_news_url(material["url"])
    title, summary = material.get("title", ""), material.get("summary", "")
    if (not source or len(source) > 100 or published.tzinfo is None or published.utcoffset() is None
            or not url or type(title) is not str or len(title) > 240
            or type(summary) is not str or len(summary) > 1000):
        raise ValueError("news attribution is invalid")
    return {"source": source, "published_at": published.isoformat(), "url": url,
            "title": title, "summary": summary}


def attribution_suffix(material):
    """Legacy formatter retained for diagnostics; proactive delivery no longer appends it."""
    provenance = news_provenance(material)
    return (f"\n\n来源：{provenance['source']} · "
            f"{datetime.fromisoformat(provenance['published_at']).date().isoformat()}\n"
            f"原文：{provenance['url']}")


class NewsContactEvents:
    def __init__(self, contacts, port):
        self.contacts, self.port = contacts, port
        self.runtime = contacts.runtime
        self.guard = bind(self.runtime, SOURCE_OWNER, self._validate_source)
        self._maintenance_workers = {}

    def _port(self, preferences):
        resolver = getattr(self.port, "for_settings", None)
        return resolver(preferences.values) if callable(resolver) else self.port

    def close(self):
        self.guard.close()
        for worker in tuple(self._maintenance_workers.values()):
            worker.cancel()
        self._maintenance_workers.clear()

    def _maintenance_allowed(self, context, preferences):
        """Whether the source should be kept warm independently of contact delivery.

        ``news_share_enabled`` and ``automatic_enabled`` govern sending.  They
        must not make the configured feed disappear from the dashboard: the
        default host source is the AI daily feed and remains useful for ordinary
        questions and review even while proactive contact is paused.
        """
        if self.port is None or context.scope.kind is not ScopeKind.PRIVATE:
            return False
        values = preferences.values
        kind = values.get("news_source_kind", "host")
        if kind == "disabled":
            return False
        if kind == "search":
            return values.get("web_exploration_enabled") is True
        if kind == "hot":
            return values.get("news_daily_hot_read_enabled") is True
        return True

    @staticmethod
    def _feed_item(item, fallback_source=""):
        """Project one fetched item into a bounded, UI-safe persisted summary."""
        try:
            title = str(item.title or "").strip()[:240]
            summary = str(item.summary or "").strip()[:1000]
            source = str(item.source or fallback_source or "").strip()[:100]
            url = canonical_news_url(item.url)
            published = item.published_at
            if (not title or not source or not url or published is None
                    or published.tzinfo is None or published.utcoffset() is None):
                return None
            return {"title": title, "summary": summary, "source": source, "url": url,
                    "published_at": stamp(published)}
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None

    def _feed_items(self, batch, port):
        items = []
        for item in batch.items[:100]:
            projected = self._feed_item(item, getattr(port, "source_label", ""))
            if projected is not None:
                items.append(projected)
        items.sort(key=lambda value: (value["published_at"], value["url"]), reverse=True)
        return items[:MAX_FEED_ITEMS]

    def _maintenance_due(self, context, preferences, at):
        if not self._maintenance_allowed(context, preferences):
            return False
        diagnostic = self.diagnostic(context, preferences)
        last = diagnostic.get("last_attempt_at") or diagnostic.get("last_checked_at")
        if not last:
            return True
        try:
            return at >= datetime.fromisoformat(last) + self._poll_interval(preferences)
        except (TypeError, ValueError):
            return True

    def maintain(self, context, preferences):
        """Schedule a durable source refresh without creating a contact opportunity."""
        worker = self._maintenance_workers.get(context.key)
        if worker is not None:
            if not worker.done():
                return
            if not worker.cancelled():
                worker.exception()
            self._maintenance_workers.pop(context.key, None)
        at = self.contacts.tasks.now()
        if not self._maintenance_due(context, preferences, at):
            return
        self._maintenance_workers[context.key] = asyncio.create_task(
            self._maintain(context, preferences.values.copy()),
            name="companion:news-maintenance:" + context.key)

    async def _maintain(self, context, values):
        preferences = type("NewsMaintenancePreferences", (), {"values": values})()
        attempted = self.contacts.tasks.now()
        port = None
        try:
            port = self._source(preferences)
            if port is None:
                self._save_diagnostic(context, {"last_attempt_at": stamp(attempted),
                    "last_checked_at": None,
                    "failure": {"code": "news_source_disabled", "http_status": None,
                                 "provider_code": None}, "item_count": 0,
                    "candidate": False}, port=port)
                return
            batch = await asyncio.wait_for(port.fetch(), timeout=10)
            if type(batch) is not ParseBatch:
                raise ValueError("news port returned an invalid batch")
            checked = self.contacts.tasks.now()
            items = self._feed_items(batch, port)
            self._save_diagnostic(context, {"last_attempt_at": stamp(attempted),
                "last_checked_at": stamp(checked), "failure": None,
                "item_count": len(batch.items), "candidate": False,
                "items": items}, port=port)
        except Exception as error:
            checked = self.contacts.tasks.now()
            self._save_diagnostic(context, {"last_attempt_at": stamp(attempted),
                "last_checked_at": None, "failure": news_failure(error),
                "item_count": 0, "candidate": False}, port=port)

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

    def _self_link_cooled_down(self, context, preferences, at, *, exclude_event_id=None):
        if not preferences.values["external_event_self_link_enabled"]:
            return False
        hours = preferences.values["external_event_self_link_cooldown_hours"]
        if not hours:
            return False
        query = """SELECT MAX(created_at) AS latest FROM proactive_contacts
            WHERE origin_key = ? AND json_extract(record_json, '$.purpose') = 'news'"""
        parameters = [context.key]
        if exclude_event_id is not None:
            query += " AND COALESCE(json_extract(record_json, '$.automatic_origin.news_event.event_id'), '') != ?"
            parameters.append(exclude_event_id)
        row = self.runtime.read_one(query, tuple(parameters))
        return bool(row and row["latest"] and at < datetime.fromisoformat(row["latest"]) + timedelta(hours=hours))

    def _row(self, context):
        return self.runtime.read_one("SELECT * FROM proactive_news_polls WHERE origin_key = ?", (context.key,))

    def _source(self, preferences):
        resolver = getattr(self.port, "for_settings", None)
        return resolver(preferences.values) if callable(resolver) else self.port

    @staticmethod
    def source_fingerprint(port):
        if port is None:
            return None
        return digest([getattr(port, "fingerprint", None), getattr(port, "kind", ""),
                       getattr(port, "source_label", "")])

    def diagnostic(self, context, preferences):
        """Return only bounded, non-secret fetch state for the management page."""
        try:
            port = self._source(preferences)
            source = {"ready": port is not None, "assembled": port is not None,
                      "kind": getattr(port, "kind", "") if port is not None else "",
                      "label": getattr(port, "source_label", "") if port is not None else ""}
        except (ValueError, TypeError):
            port, source = None, {"ready": False, "assembled": False, "kind": "", "label": ""}
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
        if status.get("source_fingerprint") != self.source_fingerprint(port):
            status = {}
        failure = status.get("failure")
        if type(failure) is not dict:
            failure = None
        item_count = status.get("item_count", 0)
        if type(item_count) is not int or item_count < 0:
            item_count = 0
        items = status.get("items", [])
        if type(items) is not list:
            items = []
        items = [item for item in items[:MAX_FEED_ITEMS]
                 if type(item) is dict and type(item.get("title")) is str
                 and type(item.get("url")) is str and type(item.get("published_at")) is str]
        last_attempt_at = status.get("last_attempt_at")
        last_checked_at = status.get("last_success_at") or status.get("last_checked_at")
        if port is None:
            network_status = "not_configured"
        elif not last_attempt_at:
            network_status = "not_checked"
        elif failure is not None:
            network_status = "failed"
        elif last_checked_at:
            network_status = "succeeded"
        else:
            network_status = "not_checked"
        return {"source": source, "network_status": network_status,
                "last_check_succeeded": network_status == "succeeded",
                "last_attempt_at": last_attempt_at, "last_checked_at": last_checked_at,
                "last_success_at": last_checked_at,
                "failure": failure, "item_count": item_count, "items": items,
                "candidate": bool(status.get("candidate", False))}

    def _save_diagnostic(self, context, value, *, port=None):
        value = dict(value)
        value["source_fingerprint"] = self.source_fingerprint(port)
        key = "proactive.news.status:" + context.key
        previous = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
        prior_status = {}
        if previous is not None:
            try:
                parsed = json.loads(previous["value"])
                if type(parsed) is dict:
                    prior_status = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if prior_status.get("source_fingerprint") != value["source_fingerprint"]:
            prior_status = {}
        if value.get("failure") is None and value.get("last_checked_at"):
            value["last_success_at"] = value["last_checked_at"]
        else:
            value["last_success_at"] = (prior_status.get("last_success_at")
                                        or prior_status.get("last_checked_at"))
            value["last_checked_at"] = value["last_success_at"]
        if "items" not in value:
            value["items"] = prior_status.get("items", []) if isinstance(prior_status.get("items", []), list) else []
        value["items"] = value["items"][:MAX_FEED_ITEMS]
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (key, payload))

    def record_lookup(self, context, attempted_at, *, port, checked_at=None, failure=None, item_count=0):
        """Record a source fetch performed for an ordinary conversation turn."""
        self._save_diagnostic(context, {
            "last_attempt_at": stamp(attempted_at),
            "last_checked_at": stamp(checked_at) if checked_at is not None else None,
            "failure": failure,
            "item_count": item_count if type(item_count) is int and item_count >= 0 else 0,
            "candidate": False,
        }, port=port)

    async def probe(self, context, preferences):
        """Fetch a source for diagnostics without changing polling or contact state."""
        attempt_at = self.contacts.tasks.now()
        port = None
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
                         "failure": None, "item_count": len(batch.items), "candidate": False,
                         "items": self._feed_items(batch, port)}
        except Exception as error:
            value = {"last_attempt_at": stamp(attempt_at), "last_checked_at": None,
                     "failure": news_failure(error), "item_count": 0, "candidate": False}
        self._save_diagnostic(context, value, port=port)
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
        if self._self_link_cooled_down(context, preferences, at):
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
            "看到一条有出处和日期的新资讯，可以挑一个让自己好奇或惊讶的亮点，"
            "像兴冲冲与对方分享新鲜事一样说一点内容和感想；与兴趣、身份或近况不自然相关时可以跳过。"
            "事实仅取标题和摘要，不补写亲历、完整阅读或未给出的事实；"
            "主动正文不附来源和原文链接，程序会留存，等对方追问时再给。",
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
        if self._self_link_cooled_down(context, preferences, at):
            return None
        row = self._row(context)
        pending = self._candidate(context, row, settings_hash, at)
        if pending is not None:
            return self._project(context, pending[1], at)
        if self.select(context, preferences, at) is None:
            return None
        port = None
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
                    "failure": news_failure(error), "item_count": 0, "candidate": False}, port=port)
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
                        or published is None or published.tzinfo is None or published.utcoffset() is None
                        or not timedelta(0) <= at - published <= MAX_AGE
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
            published, key, item, url = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
            expires = min(at + EVENT_WINDOW, published + MAX_AGE)
            event = {"id": "news-" + digest([context.key, settings_hash, key]),
                     "opened_at": stamp(at), "expires_at": stamp(expires),
                     "settings_hash": settings_hash, "key": key,
                     "feed": port.source_label,
                     "article": {"source": item.source or port.source_label,
                                 "title": item.title, "summary": item.summary, "url": url,
                                 "published_at": stamp(published)}}
            if not self._self_link_cooled_down(context, preferences, at):
                seen.append(key)
            else:
                event = None
        self._save(context, settings_hash, at, checked=True, seen=seen, event=event)
        self._save_diagnostic(context, {"last_attempt_at": stamp(at), "last_checked_at": stamp(at),
            "failure": None, "item_count": len(batch.items), "candidate": event is not None,
            "items": self._feed_items(batch, port)}, port=port)
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
            if (self._self_link_cooled_down(context, preferences, at, exclude_event_id=receipt["event_id"])
                    or event["id"] != receipt["event_id"] or not opportunity.opened_at <= at < opportunity.expires_at
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
            preferences = require(self.contacts.preferences.read(context, observed_at=at))
            row = self._row(context)
            event = json.loads(row["event_json"]) if row is not None and row["event_json"] else None
            if (source.owner != SOURCE_OWNER or source.scope != context.scope or event is None
                    or event["id"] != marker["event_id"] or event["settings_hash"] != marker["settings_hash"]
                    or self._self_link_cooled_down(context, preferences, at, exclude_event_id=event["id"])
                    or source != self._record(context, event).reference):
                raise ValueError("news marker changed")
            require(self.contacts.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))
        except TaskError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise TaskError("contact_news_changed", "news marker is no longer current") from error
