"""Persisted execution intent on a role activity, separate from its completion."""

from dataclasses import dataclass
from datetime import datetime

from companion_v2.foundation.refs import SourceRef, normalize_utc


@dataclass(frozen=True)
class RoleWorkSpec:
    kind: str
    context_key: str
    request_id: str
    source: SourceRef | None = None
    content_hash: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    due_at: datetime | None = None

    def __post_init__(self):
        if self.kind not in ("reading", "sleep"):
            raise ValueError("unknown role execution kind")
        for value in (self.context_key, self.request_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError("role execution needs stable authority and request identities")
        if self.kind == "reading":
            if (not isinstance(self.source, SourceRef) or not self.content_hash or self.due_at is not None
                    or type(self.start_offset) is not int or type(self.end_offset) is not int
                    or not 0 <= self.start_offset < self.end_offset):
                raise ValueError("reading execution must identify an original text span")
        elif (self.source is not None or self.content_hash is not None or self.start_offset is not None
              or self.end_offset is not None or self.due_at is None):
            raise ValueError("sleep execution needs an explicit wake time")
        if self.due_at is not None:
            object.__setattr__(self, "due_at", normalize_utc(self.due_at, field="planned wake time"))
