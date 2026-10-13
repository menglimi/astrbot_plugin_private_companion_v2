"""Normalize Bilibili dynamic JSON and RSS/Atom into the news port contract."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from defusedxml import ElementTree as ET

from companion_v2.proactive.external_materials import parse_news_response
from companion_v2.proactive.news_sources import NewsFetchError, news_uid


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("br", "p", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def plain_text(value):
    if type(value) is not str:
        return ""
    parser = _PlainText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def parse_rss_news(raw, *, source_label):
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, TypeError, ValueError) as error:
        raise NewsFetchError("news_payload_invalid") from error
    def local(element):
        return element.tag.rsplit("}", 1)[-1].casefold()
    channel = root if local(root) == "feed" else next((item for item in root if local(item) == "channel"), root)
    feed_title = next((plain_text(item.text or "") for item in channel if local(item) == "title"), "")
    entries = [item for item in channel if local(item) in ("item", "entry")]
    items = []
    for entry in entries[:100]:
        values = {local(child): (child.text or "").strip() for child in entry if local(child) != "link"}
        category = next((plain_text(child.attrib.get("term") or child.text or "")[:48]
                         for child in entry if local(child) == "category"
                         and plain_text(child.attrib.get("term") or child.text or "")), "")
        link = next((child.attrib.get("href", "") for child in entry
                     if local(child) == "link" and child.attrib.get("href")), "")
        if not link:
            link = next(((child.text or "").strip() for child in entry
                         if local(child) == "link" and (child.text or "").strip()), "")
        published = values.get("pubdate") or values.get("published") or values.get("updated") or values.get("date")
        timestamp = None
        if published:
            try:
                parsed = parsedate_to_datetime(published)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamp = parsed.astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                try:
                    parsed = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    timestamp = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
                except ValueError:
                    timestamp = None
        items.append({"id": values.get("guid", "") or values.get("id", ""),
                      "title": plain_text(values.get("title", ""))[:240],
                      "summary": plain_text(values.get("description", "") or values.get("summary", "") or values.get("content", ""))[:1000],
                      "url": link, "published_at": timestamp,
                      "source": plain_text(feed_title)[:100] or source_label,
                      "category": category})
    return parse_news_response({"items": items})


def parse_bilibili_news(payload, *, uid):
    news_uid(uid)
    if type(payload) is not dict or type(payload.get("code")) is not int:
        raise NewsFetchError("news_payload_invalid")
    if payload["code"] != 0:
        raise NewsFetchError("news_provider_error", provider_code=payload["code"])
    data = payload.get("data")
    if type(data) is not dict or type(data.get("items")) is not list:
        raise NewsFetchError("news_payload_invalid")
    items = []
    for item in data["items"][:100]:
        if type(item) is not dict:
            items.append({})
            continue
        modules = item.get("modules") or {}
        if type(modules) is not dict:
            items.append({})
            continue
        author, dynamic = modules.get("module_author") or {}, modules.get("module_dynamic") or {}
        if (type(author) is not dict or type(dynamic) is not dict
                or str(author.get("mid")) != uid):
            items.append({})
            continue
        desc = dynamic.get("desc") or {}
        text = desc.get("text", "") if type(desc) is dict else ""
        major = dynamic.get("major") or {}
        archive = (major.get("archive") or {}) if type(major) is dict else {}
        title = archive.get("title", "") if type(archive) is dict else ""
        summary = text or (archive.get("desc", "") if type(archive) is dict else "")
        if not title:
            title = text.splitlines()[0] if type(text) is str and text.strip() else ""
        published = author.get("pub_ts")
        identifier = item.get("id_str")
        timestamp = None
        if type(published) is int and 0 < published < 253402300800:
            timestamp = datetime.fromtimestamp(published, timezone.utc).isoformat()
        valid_id = type(identifier) is str and identifier.isascii() and identifier.isdecimal()
        items.append({"id": identifier if valid_id else "",
                      "title": plain_text(title)[:240], "summary": plain_text(summary)[:1000],
                      "url": "https://t.bilibili.com/" + identifier if valid_id else "",
                      "published_at": timestamp,
                      "source": "B站 · " + (plain_text(author.get("name", ""))[:80] or uid)})
    return parse_news_response({"items": items})
