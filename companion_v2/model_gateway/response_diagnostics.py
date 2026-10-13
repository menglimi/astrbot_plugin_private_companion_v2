"""Immutable response-stage summaries; never retain model bodies or error text."""

from dataclasses import asdict, dataclass
import hashlib
import html
import json
import re

from .failures import ModelFailure


_MARKUP = re.compile(r"<\s*(?:/?\s*[a-z_][\w.:-]*|\|)|&&[^&\r\n]{1,80}&&", re.I)
PARSE_STATES = frozenset({"not_received", "raw_observed", "native_parsed", "native_rejected",
    "stream_rejected", "contract_rejected", "validated", "tools", "captured", "refusal"})
FINISH_REASONS = frozenset({"missing", "stop", "length", "tool_calls", "function_call",
    "content_filter", "unknown"})


@dataclass(frozen=True)
class ResponseTextSummary:
    chars: int
    sha256: str
    shape: str
    has_internal_markers: bool

    def __post_init__(self):
        if (type(self.chars) is not int or not 0 <= self.chars <= 2**31 - 1
                or type(self.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
                or self.shape not in ("empty", "text", "json_object", "json_array", "json_scalar")
                or type(self.has_internal_markers) is not bool):
            raise ValueError("response text summaries require bounded metadata and a content fingerprint")

    @classmethod
    def from_text(cls, text):
        if type(text) is not str:
            return None
        shape = "text" if text.strip() else "empty"
        if shape == "text" and len(text) <= 65536:
            try:
                value = json.loads(text)
            except (ValueError, RecursionError):
                pass
            else:
                shape = "json_object" if type(value) is dict else "json_array" if type(value) is list else "json_scalar"
        markers = html.unescape(text).replace("\\u003c", "<").replace("\\u003C", "<")
        return cls(len(text), hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest(),
                   shape, bool(_MARKUP.search(markers)))


@dataclass(frozen=True)
class ResponseDiagnostics:
    completion_present: bool = False
    finish_reason: str = "missing"
    parse_state: str = "not_received"
    raw: ResponseTextSummary | None = None
    parsed: ResponseTextSummary | None = None
    visible: ResponseTextSummary | None = None
    failure: ModelFailure | None = None
    error_type: str | None = None
    error_code: str | None = None
    status_code: int | None = None

    def __post_init__(self):
        if (type(self.completion_present) is not bool or self.finish_reason not in FINISH_REASONS
                or self.parse_state not in PARSE_STATES
                or any(value is not None and not isinstance(value, ResponseTextSummary)
                       for value in (self.raw, self.parsed, self.visible))
                or self.failure is not None and not isinstance(self.failure, ModelFailure)
                or self.error_type is not None and (type(self.error_type) is not str
                    or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", self.error_type) is None)
                or self.error_code is not None and (type(self.error_code) is not str
                    or re.fullmatch(r"[a-z0-9_.-]{1,80}", self.error_code) is None)
                or self.status_code is not None and (type(self.status_code) is not int
                    or not 100 <= self.status_code <= 599)
                or not self.completion_present and any(value is not None for value in (self.raw, self.parsed, self.visible))):
            raise ValueError("response diagnostics require fixed classifications and body-free summaries")

    def to_record(self):
        return {"version": 2, "completion_present": self.completion_present,
            "finish_reason": self.finish_reason, "parse_state": self.parse_state,
            "raw": asdict(self.raw) if self.raw is not None else None,
            "parsed": asdict(self.parsed) if self.parsed is not None else None,
            "visible": asdict(self.visible) if self.visible is not None else None,
            "failure_code": self.failure.value if self.failure is not None else None,
            "error_type": self.error_type, "error_code": self.error_code, "status_code": self.status_code}


def checked_response_diagnostics(raw):
    """Project persisted metadata defensively, including older calls with no summary."""
    if raw is None:
        return None
    try:
        value = json.loads(raw)
        if type(value) is not dict or value.get("version") not in (1, 2):
            return None
        summaries = {name: ResponseTextSummary(**value[name]) if value[name] is not None else None
                     for name in ("raw", "parsed", "visible")}
        result = ResponseDiagnostics(value["completion_present"], value["finish_reason"], value["parse_state"],
            **summaries, failure=ModelFailure(value["failure_code"]) if value["failure_code"] is not None else None,
            error_type=value.get("error_type"), error_code=value.get("error_code"),
            status_code=value.get("status_code"))
        return result.to_record()
    except (KeyError, TypeError, ValueError, RecursionError):
        return None
