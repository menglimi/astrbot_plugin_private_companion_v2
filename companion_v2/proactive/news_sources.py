"""Public source selection and sanitized failures for external news ports."""

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit


SOURCE_KINDS = ("host", "disabled", "bilibili", "rss", "json", "search", "hot")
SOURCE_FIELDS = ("news_source_kind", "news_source_uid", "news_source_url")


def news_url(value):
    if (type(value) is not str or not 1 <= len(value) <= 2048
            or any(ord(char) < 33 for char in value)):
        raise ValueError("news URL must be a short absolute HTTPS URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment):
        raise ValueError("news URL must be HTTPS without embedded credentials or fragments")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        host = parsed.hostname.casefold()
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError("news URL must name an external feed")
    else:
        raise ValueError("news URL must use a DNS hostname")
    if parsed.port is not None and parsed.port != 443:
        raise ValueError("news URL must use the standard HTTPS port")
    return value


def news_uid(value):
    if type(value) is not str or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None:
        raise ValueError("provide a Bilibili UID as decimal text")
    return value


@dataclass(frozen=True)
class NewsSource:
    kind: str
    uid: str = ""
    url: str = ""

    @classmethod
    def read(cls, values):
        kind = values.get("news_source_kind", "host")
        if kind not in SOURCE_KINDS:
            raise ValueError("unknown news source kind")
        if kind == "bilibili":
            return cls(kind, uid=news_uid(values.get("news_source_uid", "")))
        if kind in ("rss", "json"):
            return cls(kind, url=news_url(values.get("news_source_url", "")))
        return cls(kind)


class NewsFetchError(ValueError):
    def __init__(self, code, *, http_status=None, provider_code=None):
        super().__init__(code)
        self.code, self.http_status, self.provider_code = code, http_status, provider_code


def news_failure(error):
    if isinstance(error, NewsFetchError):
        return {"code": error.code, "http_status": error.http_status,
                "provider_code": error.provider_code}
    # Network exception messages may include source URLs or credentials.
    return {"code": "news_timeout" if isinstance(error, TimeoutError) else "news_unavailable",
            "http_status": None, "provider_code": None}
