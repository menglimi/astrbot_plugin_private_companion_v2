"""Bounded HTTPS JSON balance adapter; credentials stay in the host environment."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
import re
from urllib.parse import urlsplit

import aiohttp

from companion_v2.proactive.balance_events import BalanceObservation


PREFIX = "COMPANION_V2_BALANCE_"
MAX_RESPONSE_BYTES = 65536
HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}\Z")


def _path(value):
    if type(value) is not str or not value or len(value) > 128:
        raise ValueError("balance JSON path must be a short dotted path")
    parts = value.split(".")
    if any(not part or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*|[0-9]+", part) for part in parts):
        raise ValueError("balance JSON path has an invalid component")
    return tuple(parts)


def _read_path(payload, path):
    value = payload
    for part in path:
        if type(value) is dict and part in value:
            value = value[part]
        elif type(value) is list and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError("balance JSON path is missing")
    return value


def _amount(value, divisor):
    if type(value) is bool or type(value) not in (str, int, float, Decimal):
        raise ValueError("balance JSON value is not numeric")
    try:
        amount = Decimal(str(value)) / divisor
    except (InvalidOperation, ZeroDivisionError) as error:
        raise ValueError("balance JSON value is invalid") from error
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000000000"):
        raise ValueError("balance JSON value is outside the accepted range")
    return amount


class ServiceBalancePort:
    def __init__(self, *, url, api_key="", auth_header="Authorization", auth_scheme="Bearer",
                 headers=None, balance_path="balance", total_path="", used_path="",
                 divisor="1", timeout_seconds=6, now=None):
        headers = {} if headers is None else headers
        if type(url) is not str or len(url) > 2048:
            raise ValueError("service balance URL is invalid")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment or any(ord(char) < 33 for char in url)):
            raise ValueError("service balance URL must be an absolute HTTPS URL without embedded credentials")
        if (type(api_key) is not str or any(ord(char) < 32 for char in api_key)
                or type(auth_header) is not str or not HEADER_NAME.fullmatch(auth_header)
                or type(auth_scheme) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{0,32}", auth_scheme)):
            raise ValueError("service balance authorization settings are invalid")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 10:
            raise ValueError("service balance timeout must be 1-10 seconds")
        if type(headers) is not dict or len(headers) > 8:
            raise ValueError("service balance custom headers must be a small JSON object")
        for name, value in headers.items():
            if (type(name) is not str or not HEADER_NAME.fullmatch(name) or type(value) is not str
                    or len(value) > 2048 or any(ord(char) < 32 for char in value)):
                raise ValueError("service balance custom header is invalid")
        if api_key and auth_header.lower() in {name.lower() for name in headers}:
            raise ValueError("service balance authorization header is duplicated")
        try:
            divisor_value = Decimal(str(divisor))
        except InvalidOperation as error:
            raise ValueError("service balance divisor is invalid") from error
        if not divisor_value.is_finite() or divisor_value <= 0:
            raise ValueError("service balance divisor must be positive")
        self.url, self.timeout_seconds = url, timeout_seconds
        self.headers = dict(headers)
        if api_key:
            self.headers[auth_header] = (auth_scheme + " " if auth_scheme else "") + api_key
        self.balance_path = _path(balance_path) if balance_path else None
        self.total_path = _path(total_path) if total_path else None
        self.used_path = _path(used_path) if used_path else None
        if self.balance_path is None and (self.total_path is None or self.used_path is None):
            raise ValueError("service balance requires a balance path or total and used paths")
        self.divisor, self.now = divisor_value, now or (lambda: datetime.now(timezone.utc))

    def parse(self, payload, observed_at):
        total = _amount(_read_path(payload, self.total_path), self.divisor) if self.total_path else None
        if self.balance_path:
            balance = _amount(_read_path(payload, self.balance_path), self.divisor)
        else:
            used = _amount(_read_path(payload, self.used_path), self.divisor)
            balance = max(Decimal(0), total - used)
        return BalanceObservation(balance, total, observed_at)

    async def fetch(self):
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            async with session.get(self.url, headers=self.headers, allow_redirects=False) as response:
                if (response.status != 200 or response.content_length is not None
                        and response.content_length > MAX_RESPONSE_BYTES):
                    raise ValueError("service balance response is unavailable")
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("service balance response exceeds the limit")
        return self.parse(json.loads(raw, parse_float=Decimal), self.now())


def configured_balance_port():
    names = ("URL", "API_KEY", "AUTH_HEADER", "AUTH_SCHEME", "CUSTOM_HEADERS",
             "JSON_PATH", "TOTAL_JSON_PATH", "USED_JSON_PATH", "VALUE_DIVISOR", "TIMEOUT_SECONDS")
    values = {name: os.environ.get(PREFIX + name, "") for name in names}
    if not any(values.values()):
        return None
    if not values["URL"]:
        raise ValueError("service balance URL is required when balance environment settings are present")
    try:
        custom_headers = json.loads(values["CUSTOM_HEADERS"] or "{}")
        timeout = int(values["TIMEOUT_SECONDS"] or "6")
    except (ValueError, TypeError) as error:
        raise ValueError("service balance environment settings are invalid") from error
    return ServiceBalancePort(url=values["URL"], api_key=values["API_KEY"],
        auth_header=values["AUTH_HEADER"] or "Authorization",
        auth_scheme=values["AUTH_SCHEME"] or "Bearer", headers=custom_headers,
        balance_path=values["JSON_PATH"] or ("" if values["TOTAL_JSON_PATH"] and values["USED_JSON_PATH"] else "balance"),
        total_path=values["TOTAL_JSON_PATH"], used_path=values["USED_JSON_PATH"],
        divisor=values["VALUE_DIVISOR"] or "1", timeout_seconds=timeout)
