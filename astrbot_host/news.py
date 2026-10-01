"""Host transports for explicit HTTPS JSON, RSS/Atom and Bilibili news sources."""

import json
import os
import re
import asyncio
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl

import aiohttp

from companion_v2.execution.models import digest
from companion_v2.proactive.external_materials import NewsItem, ParseBatch, parse_news_response
from companion_v2.proactive.news_sources import NewsFetchError, NewsSource, news_uid, news_url

from .news_parsing import parse_bilibili_news, parse_rss_news


MAX_RESPONSE_BYTES = 524288
HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}\Z")


class NewsJsonPort:
    kind = "json"

    def __init__(self, *, url, api_key="", auth_header="Authorization", auth_scheme="Bearer"):
        self.url = news_url(url)
        if (type(api_key) is not str or len(api_key) > 4096 or any(ord(char) < 32 for char in api_key)
                or type(auth_header) is not str or HEADER_NAME.fullmatch(auth_header) is None
                or type(auth_scheme) is not str or re.fullmatch(r"[A-Za-z0-9_-]{0,32}", auth_scheme) is None):
            raise ValueError("news authorization settings are invalid")
        self.source_label = urlsplit(url).hostname.casefold()
        self.fingerprint = digest([self.kind, url, auth_header, auth_scheme, api_key])
        self.headers = {}
        if api_key:
            self.headers[auth_header] = (auth_scheme + " " if auth_scheme else "") + api_key

    async def _read(self, url=None):
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
                async with session.get(url or self.url, headers=self.headers, allow_redirects=False) as response:
                    if response.status != 200:
                        raise NewsFetchError("news_http_error", http_status=response.status)
                    if response.content_length is not None and response.content_length > MAX_RESPONSE_BYTES:
                        raise NewsFetchError("news_too_large")
                    raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise NewsFetchError("news_too_large")
                    return raw
        except TimeoutError as error:
            raise NewsFetchError("news_timeout") from error
        except aiohttp.ClientError as error:
            raise NewsFetchError("news_unavailable") from error

    async def fetch(self):
        raw = await self._read()
        try:
            return parse_news_response(json.loads(raw))
        except (ValueError, TypeError, UnicodeError) as error:
            raise NewsFetchError("news_payload_invalid") from error


class NewsRssPort(NewsJsonPort):
    kind = "rss"

    async def fetch(self):
        raw = await self._read()
        try:
            return parse_rss_news(raw, source_label=self.source_label)
        except NewsFetchError:
            raise
        except (ValueError, TypeError, UnicodeError, OverflowError) as error:
            raise NewsFetchError("news_payload_invalid") from error


class BilibiliNewsPort(NewsJsonPort):
    kind = "bilibili"

    def __init__(self, *, uid, cookie=""):
        self.uid = news_uid(uid)
        if (type(cookie) is not str or len(cookie) > 8192 or any(ord(char) < 32 for char in cookie)):
            raise ValueError("Bilibili cookie is invalid")
        super().__init__(url="https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid=" + uid)
        self.source_label = "B站动态 · UID " + uid
        self.fingerprint = digest([self.kind, uid, cookie])
        self.headers.update({"Referer": "https://space.bilibili.com/" + uid + "/dynamic",
                             "User-Agent": "Mozilla/5.0 CompanionV2/2.0"})
        if cookie:
            self.headers["Cookie"] = cookie

    async def fetch(self):
        raw = await self._read()
        try:
            return parse_bilibili_news(json.loads(raw), uid=self.uid)
        except NewsFetchError:
            raise
        except (ValueError, TypeError, UnicodeError, OverflowError) as error:
            raise NewsFetchError("news_payload_invalid") from error


class WebSearchNewsPort(NewsJsonPort):
    kind = "search"

    def __init__(self, *, url, query, result_count=8, api_key="", auth_header="Authorization", auth_scheme="Bearer"):
        super().__init__(url=url, api_key=api_key, auth_header=auth_header, auth_scheme=auth_scheme)
        self.query = query.strip()[:240] if type(query) is str else ""
        self.result_count = max(1, min(30, int(result_count)))
        self.source_label = "网页搜索"
        self.fingerprint = digest([self.kind, self.url, self.query, self.result_count, self.fingerprint])

    async def _read(self):
        parts = urlsplit(self.url)
        query = urlencode([*parse_qsl(parts.query, keep_blank_values=True),
                           ("q", self.query), ("count", str(self.result_count))])
        return await super()._read(urlunsplit((parts.scheme, parts.netloc, parts.path, query, "")))

    async def fetch(self):
        batch = await super().fetch()
        return ParseBatch(batch.items[:self.result_count], batch.warnings)


class HotTrendNewsPort:
    kind = "hot"
    source_label = "公开热点"

    def __init__(self, sources=("weibo", "hackernews"), limit=12):
        allowed = {"weibo", "hackernews"}
        self.sources = tuple(dict.fromkeys(item for item in sources if item in allowed))
        if not self.sources:
            raise ValueError("at least one supported hot source is required")
        self.limit = max(3, min(30, int(limit)))
        self.fingerprint = digest([self.kind, self.sources, self.limit])

    async def _weibo(self, session):
        async with session.get("https://weibo.com/ajax/side/hotSearch") as response:
            if response.status != 200:
                return []
            payload = await response.json(content_type=None)
        rows = payload.get("data", {}).get("realtime", []) if type(payload) is dict else []
        result = []
        for rank, row in enumerate(rows[:self.limit], 1):
            title = row.get("note") or row.get("word") if type(row) is dict else ""
            if type(title) is str and title.strip():
                result.append(NewsItem("微博热搜", str(rank), title.strip()[:240],
                    "https://s.weibo.com/weibo?q=" + quote("#" + title.strip() + "#"),
                    "微博热搜第 " + str(rank) + " 位", None))
        return result

    async def _hackernews(self, session):
        async with session.get("https://hacker-news.firebaseio.com/v0/topstories.json") as response:
            if response.status != 200:
                return []
            ids = await response.json()
        async def one(identifier):
            async with session.get(f"https://hacker-news.firebaseio.com/v0/item/{int(identifier)}.json") as response:
                if response.status != 200:
                    return None
                row = await response.json()
            if type(row) is not dict or not row.get("title") or not row.get("time"):
                return None
            return NewsItem("Hacker News", str(identifier), str(row["title"])[:240],
                str(row.get("url") or f"https://news.ycombinator.com/item?id={identifier}"),
                "Hacker News 热门讨论", datetime.fromtimestamp(int(row["time"]), timezone.utc))
        return [item for item in await asyncio.gather(*(one(identifier) for identifier in ids[:self.limit])) if item]

    async def fetch(self):
        timeout = aiohttp.ClientTimeout(total=12)
        headers = {"User-Agent": "AstrBotCompanionV2/2.0", "Accept": "application/json"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, trust_env=False) as session:
            calls = [self._weibo(session) if name == "weibo" else self._hackernews(session)
                     for name in self.sources]
            batches = await asyncio.gather(*calls, return_exceptions=True)
        items = [item for batch in batches if isinstance(batch, list) for item in batch]
        if not items:
            raise NewsFetchError("news_unavailable")
        return ParseBatch(tuple(items[:self.limit * len(self.sources)]), ())


class NewsSourceRouter:
    """Resolve each window's public selection without storing host credentials in V2."""

    def __init__(self, default_source, *, auth, bilibili_cookie="", search_url="", hot_sources=("weibo", "hackernews"), hot_result_count=10):
        self.default_source, self.auth, self.bilibili_cookie = default_source, auth, bilibili_cookie
        self.search_url, self.hot_sources = search_url, tuple(hot_sources)
        self.hot_result_count = max(3, min(30, int(hot_result_count)))

    def for_settings(self, values):
        source = NewsSource.read(values)
        if source.kind == "host":
            source = self.default_source
        if source.kind in ("host", "disabled"):
            return None
        if source.kind == "bilibili":
            return BilibiliNewsPort(uid=source.uid, cookie=self.bilibili_cookie)
        if source.kind == "search":
            query = values.get("web_exploration_interests", "").strip() or "有趣的新鲜事 科技 文化 生活"
            if not self.search_url:
                return None
            return WebSearchNewsPort(url=self.search_url, query=query,
                result_count=values.get("web_exploration_result_count", 8), **self.auth)
        if source.kind == "hot":
            configured = values.get("news_hot_sources", "")
            selected = tuple(item.strip().lower() for item in configured.split(",") if item.strip()) or self.hot_sources
            return HotTrendNewsPort(selected, values.get("news_hot_result_count", self.hot_result_count))
        auth = self.auth if source == self.default_source else {}
        return (NewsRssPort if source.kind == "rss" else NewsJsonPort)(url=source.url, **auth)


def configured_news_port(config=None):
    names = ("URL", "API_KEY", "AUTH_HEADER", "AUTH_SCHEME", "BILIBILI_COOKIE", "SEARCH_URL")
    values = {name: os.environ.get("COMPANION_V2_NEWS_" + name, "") for name in names}
    auth = {"api_key": values["API_KEY"], "auth_header": values["AUTH_HEADER"] or "Authorization",
            "auth_scheme": values["AUTH_SCHEME"] or "Bearer"}
    if config is None:
        if not any(values[name] for name in names if name != "BILIBILI_COOKIE"):
            return None
        if not values["URL"]:
            raise ValueError("news URL is required when news environment settings are present")
        return NewsJsonPort(url=values["URL"], **auth)
    settings = config.get("news", {}) or {}
    if type(settings) is not dict:
        raise ValueError("news host settings must be an object")
    source = NewsSource.read({"news_source_kind": settings.get("source_kind", "host"),
                             "news_source_uid": settings.get("bilibili_uid", ""),
                             "news_source_url": settings.get("feed_url", "")})
    if source.kind == "host" and values["URL"]:
        source = NewsSource("json", url=news_url(values["URL"]))
    hot_sources = settings.get("hot_sources", "weibo,hackernews")
    if type(hot_sources) is not str:
        raise ValueError("news hot sources must be comma-separated text")
    router = NewsSourceRouter(source, auth=auth, bilibili_cookie=values["BILIBILI_COOKIE"],
                              search_url=settings.get("search_url") or values["SEARCH_URL"],
                              hot_sources=tuple(item.strip().lower() for item in hot_sources.split(",")),
                              hot_result_count=settings.get("hot_result_count", 10))
    router.for_settings({})
    return router
