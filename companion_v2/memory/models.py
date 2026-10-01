"""Internal memory profile; host context supplies identity and authority.

This is not a second public RuntimeScope or a claim to implement the draft
memory.*.v1 wire. The capability adapter translates its supported profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math

from companion_v2.execution.models import TaskContext, TaskError, digest
from companion_v2.foundation.refs import SourceRef, normalize_utc


def text(value, name, maximum=4096, *, empty=False):
    if type(value) is not str or (not empty and not value.strip()) or len(value) > maximum:
        raise ValueError(f"{name} must be bounded text")
    return value


def integer(value, name, lower=1, upper=1000000):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")
    return value


def timestamp(value):
    if value is None:
        return None
    return normalize_utc(datetime.fromisoformat(value) if isinstance(value, str) else value, field="memory time")


@dataclass(frozen=True)
class Evidence:
    source: SourceRef
    content_hash: str
    start: int
    end: int
    span_hash: str
    speaker_id: str | None = None
    source_kind: str = "source"

    def __post_init__(self):
        if not isinstance(self.source, SourceRef):
            raise ValueError("evidence needs the original SourceRef")
        integer(self.start, "start", 0, 100000000)
        integer(self.end, "end", self.start + 1, 100000000)
        text(self.content_hash, "content_hash", 512)
        text(self.span_hash, "span_hash", 512)
        if self.source_kind not in ("human_message", "bot_message", "source", "observation"):
            raise ValueError("source kind must be supplied by a trusted producer")


@dataclass(frozen=True)
class AtomRef:
    atom_id: str
    revision: int

    def __post_init__(self):
        text(self.atom_id, "atom_id", 512)
        integer(self.revision, "revision")


@dataclass(frozen=True)
class Proposal:
    operation: str
    namespace: str = "personal"
    subject: str = "self"
    predicate: str = ""
    object: str = ""
    representation: str = ""
    qualifiers: dict = field(default_factory=dict)
    polarity: str = "positive"
    attribution: str = "user"
    retention: str = "durable"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = 1.0
    evidence: tuple[Evidence, ...] = ()
    target: AtomRef | None = None
    single_value: bool = False
    defer_until_boundary: bool = False
    reason: str = ""
    stability_estimate: str = ""
    purpose: str = "reply"
    visibility: str = "private"
    dependencies: tuple[AtomRef, ...] = ()
    context_mode: str = "relevant"

    def __post_init__(self):
        if self.operation not in ("add", "correct", "retract", "no_op"):
            raise ValueError("unsupported memory operation")
        for name, limit in (("namespace", 128), ("subject", 512), ("purpose", 128)):
            text(getattr(self, name), name, limit)
        if self.visibility != "private":
            raise TaskError("memory_visibility_unavailable", "this provider profile supports private memory only")
        if self.retention not in ("session", "short", "durable", "protected"):
            raise ValueError("unsupported retention")
        if self.context_mode not in ("relevant", "pinned"):
            raise ValueError("context mode must be relevant or pinned")
        if self.polarity not in ("positive", "negative", "uncertain"):
            raise ValueError("unsupported polarity")
        if self.attribution not in ("user", "third_party", "bot", "unknown", "observed"):
            raise ValueError("unsupported attribution")
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite and in 0..1")
        if type(self.single_value) is not bool or type(self.defer_until_boundary) is not bool:
            raise ValueError("proposal flags must be boolean")
        if type(self.qualifiers) is not dict or len(self.qualifiers) > 32:
            raise ValueError("qualifiers must be a bounded string mapping")
        for key, value in self.qualifiers.items():
            text(key, "qualifier", 128)
            text(value, "qualifier value", 1024, empty=True)
        for name in ("reason", "stability_estimate"):
            text(getattr(self, name), name, 2048, empty=True)
        if not isinstance(self.evidence, tuple) or len(self.evidence) > 32 or any(not isinstance(e, Evidence) for e in self.evidence):
            raise ValueError("evidence must be a bounded tuple")
        if not isinstance(self.dependencies, tuple) or len(self.dependencies) > 32 or any(not isinstance(r, AtomRef) for r in self.dependencies):
            raise ValueError("dependencies must be original atom revisions")
        if self.operation != "no_op" and not self.evidence:
            raise ValueError("a mutation must name actual evidence")
        if self.operation in ("correct", "retract") and not isinstance(self.target, AtomRef):
            raise ValueError("correction or retraction requires an exact target revision")
        if self.operation in ("add", "no_op") and self.target is not None:
            raise ValueError("this operation does not take a target")
        if self.operation in ("add", "correct"):
            for name in ("predicate", "object", "representation"):
                text(getattr(self, name), name, 8192)
        for name in ("valid_from", "valid_to"):
            object.__setattr__(self, name, timestamp(getattr(self, name)))
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("validity end must follow start")
        if self.retention == "short" and self.valid_to is None:
            raise ValueError("short retention requires an explicit expiry")

    @property
    def fact_key(self):
        return digest([self.namespace, self.subject, self.predicate, self.qualifiers])


def owner_key(context: TaskContext):
    # Stable across authenticated account/session changes; never derived from a nickname.
    return digest([context.scope.installation_id, context.scope.bot_id,
                   context.role_binding.role.subject_id, context.actor.subject.subject_id, "private"])


@dataclass(frozen=True)
class MemoryPolicy:
    enabled: bool = True
    automatic_context: bool = True
    context_items: int = 4
    context_chars: int = 6000
    query_items: int = 20
    query_chars: int = 20000
    source_chars: int = 8000
    turn_chars: int = 64000
    turn_calls: int = 24
    core_items: int = 4
    core_chars: int = 6000
    inclusion_chars: int = 24000

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.automatic_context) is not bool:
            raise ValueError("memory enabled flags must be explicit")
        integer(self.context_items, "context_items", 0, 16)
        integer(self.context_chars, "context_chars", 256, 24000)
        integer(self.query_items, "query_items", 1, 50)
        integer(self.query_chars, "query_chars", 256, 48000)
        integer(self.source_chars, "source_chars", 256, 24000)
        integer(self.turn_chars, "turn_chars", 1024, 200000)
        integer(self.turn_calls, "turn_calls", 1, 32)
        integer(self.core_items, "core_items", 0, 16)
        integer(self.core_chars, "core_chars", 256, 24000)
        integer(self.inclusion_chars, "inclusion_chars", 512, 96000)
