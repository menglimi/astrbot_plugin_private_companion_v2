"""Versioned credential redaction for durable message sources.

Offsets refer to the stored, redacted text. A keyed input fingerprint preserves
replay conflicts even when different credentials produce the same visible text.
"""

from dataclasses import replace
import hashlib
import hmac
import re
import secrets

from companion_v2.execution.models import encode


PROFILE = "redacted-text.v1"
REDACTED = "[REDACTED]"
_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(?:abk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{16,})(?![A-Za-z0-9_-])")
_SERVICE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:xox[baprs]-[A-Za-z0-9-]{10,}|mfa\.[A-Za-z0-9_-]{20,}|"
    r"[0-9]{6,}:[A-Za-z0-9_-]{25,}|(?:AKIA|ASIA)[A-Z0-9]{16})(?![A-Za-z0-9_-])"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PRIVATE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----", re.I | re.S)
_BEARER = re.compile(r"\bBearer[ \t]+[A-Za-z0-9._~+/=-]{8,}", re.I)
_URL = re.compile(r"((?:https?|ftp|postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?|amqps?)://[^:/\s]+:)([^@/\s]+)(@)", re.I)
_ASSIGN = re.compile(
    r"""(?P<prefix>["']?(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|client[_-]?secret|private[_-]?key|token|密码|口令|验证码|令牌|密钥|秘钥)["']?\s*(?:[:：=]|是|为)\s*)"""
    r"""(?P<value>"(?:[^"\\\r\n]|\\.)*"|'(?:[^'\\\r\n]|\\.)*'|\[REDACTED\]|[^\s,;，。；&"'{}\[\]\r\n]+)""", re.I)


def redact_text(value):
    if not isinstance(value, str):
        raise ValueError("source text must be a string")
    value = _PRIVATE.sub(REDACTED, value)
    value = _TOKEN.sub(REDACTED, value)
    value = _SERVICE_TOKEN.sub(REDACTED, value)
    value = _JWT.sub(REDACTED, value)
    value = _BEARER.sub("Bearer " + REDACTED, value)
    value = _URL.sub(lambda m: m[1] + REDACTED + m[3], value)
    def assignment(match):
        raw = match["value"]
        if raw[:1] in ('"', "'") and raw[-1:] == raw[:1]:
            replacement = raw[0] + REDACTED + raw[-1]
        elif match["prefix"].startswith('"') and ":" in match["prefix"]:
            replacement = '"' + REDACTED + '"'
        else:
            replacement = REDACTED
        return match["prefix"] + replacement
    return _ASSIGN.sub(assignment, value)


def prepare_message(runtime, record):
    safe = redact_text(record.payload)
    if safe == record.payload:
        return record
    # The installation metadata contains only a random local key, never input.
    # This does not create a second source store or a reversible credential index.
    with runtime.transaction() as connection:
        key_name = "sources." + PROFILE + ".key"
        row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key_name,)).fetchone()
        if row is None:
            secret = secrets.token_hex(32)
            connection.execute("INSERT INTO runtime_metadata VALUES (?, ?)", (key_name, secret))
        else:
            secret = row["value"]
        fingerprint = hmac.new(bytes.fromhex(secret),
            encode([PROFILE, record.payload, record.content_hash]).encode("utf-8"), hashlib.sha256).hexdigest()
    return replace(record, payload=safe, content_hash=PROFILE + ":" + fingerprint)


def redact_fields(values):
    """Clean semantic text fields; identity and source references stay untouched."""
    result = {}
    for key, value in values.items():
        clean_key = redact_text(key)
        if redact_text(key + "=" + value) != key + "=" + value:
            result[clean_key] = REDACTED
        else:
            result[clean_key] = redact_text(value)
    return result
