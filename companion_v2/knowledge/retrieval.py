"""Authorized, deterministic retrieval for worldbook and character knowledge.

The retriever deliberately stays provider agnostic.  AstrBot adapters can turn a
worldbook or knowledge-base response into :class:`KnowledgeCandidate` values,
while tests and the local host can use :class:`InMemoryKnowledgeProvider`.
Selection never grants read access by itself; callers that want durable prompt
material must publish and later read the returned source references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from typing import Iterable, Protocol, Sequence

from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SourceRef, SubjectRef, VersionRef
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository

from .parsing import KnowledgeChunk, WorldbookEntry


_TOKEN_RE = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


def _clean(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> tuple[str, ...]:
    normalized = _clean(value)
    if not normalized:
        return ()
    result = list(_TOKEN_RE.findall(normalized))
    # Chinese text is often entered without separators.  Keeping the complete
    # phrase preserves exact matching while one-character terms avoid making a
    # Chinese query entirely dependent on a tokenizer installed by the host.
    for character in normalized:
        if "\u3400" <= character <= "\u9fff" and character not in result:
            result.append(character)
    return tuple(dict.fromkeys(result))


def _tuple_text(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))


@dataclass(frozen=True)
class KnowledgeCandidate:
    """A normalized piece of worldbook or knowledge-base content.

    A missing scope/role/audience means the item is installation-wide.  This is
    useful for imported worldbooks, but any supplied boundary is enforced
    exactly by :class:`KnowledgeRetriever`.

    ``native_scope_ids`` is the one boundary an imported entry can carry without
    knowing the runtime window: a group entry records the group ids it belongs
    to, so it is injected into exactly those groups instead of every group of the
    same kind.  It requires an explicit ``scope_kind`` and is only ever compared
    against the current window's native scope id.
    """

    candidate_id: str
    text: str
    scope: ScopeRef | None = None
    scope_kind: ScopeKind | None = None
    role_id: str | None = None
    persona_id: str | None = None
    subject: SubjectRef | None = None
    audience: tuple[SubjectRef, ...] = ()
    enabled: bool = True
    priority: int = 100
    knowledge_base_id: str = ""
    document_id: str = ""
    document_name: str = ""
    chunk_index: int = 0
    name: str = ""
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    template: str = ""
    native_scope_ids: tuple[str, ...] = ()
    scope_route: tuple[str, str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be non-blank")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("candidate text must be non-blank")
        if type(self.enabled) is not bool:
            raise ValueError("candidate enabled must be boolean")
        if type(self.priority) is not int or isinstance(self.priority, bool):
            raise ValueError("candidate priority must be an integer")
        if type(self.chunk_index) is not int or self.chunk_index < 0:
            raise ValueError("candidate chunk_index must be a non-negative integer")
        if self.scope_kind is not None and not isinstance(self.scope_kind, ScopeKind):
            raise ValueError("candidate scope_kind must be a ScopeKind")
        if self.scope is not None and self.scope_kind is not None and self.scope.kind is not self.scope_kind:
            raise ValueError("candidate scope kind does not match its scope")
        if self.subject is not None and self.subject not in self.audience and self.audience:
            # A subject-specific item may be audience-limited, but never to an
            # audience that excludes its declared subject.
            raise ValueError("candidate subject must be in its audience")
        if self.native_scope_ids and self.scope_kind is None:
            raise ValueError("candidate native scope ids require an explicit scope kind")
        if self.scope_route is not None:
            if (not isinstance(self.scope_route, (tuple, list)) or len(self.scope_route) != 3
                    or not all(type(value) is str and value.strip() for value in self.scope_route)
                    or not self.native_scope_ids or self.scope_kind is not ScopeKind.GROUP):
                raise ValueError("candidate scope route requires a group-scoped native id")
            object.__setattr__(self, "scope_route", tuple(value.strip() for value in self.scope_route))
        object.__setattr__(self, "candidate_id", self.candidate_id.strip())
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "role_id", self.role_id.strip() if isinstance(self.role_id, str) and self.role_id.strip() else None)
        object.__setattr__(self, "persona_id", self.persona_id.strip() if isinstance(self.persona_id, str) and self.persona_id.strip() else None)
        object.__setattr__(self, "audience", tuple(dict.fromkeys(self.audience)))
        object.__setattr__(self, "keywords", _tuple_text(self.keywords))
        object.__setattr__(self, "aliases", _tuple_text(self.aliases))
        object.__setattr__(self, "native_scope_ids", _tuple_text(self.native_scope_ids))

    @classmethod
    def from_worldbook(
        cls,
        entry: WorldbookEntry,
        *,
        candidate_id: str | None = None,
        scope: ScopeRef | None = None,
        role_id: str | None = None,
        audience: tuple[SubjectRef, ...] = (),
        native_scope_ids: tuple[str, ...] = (),
        scope_kind: ScopeKind | None = None,
    ) -> "KnowledgeCandidate":
        identifier = candidate_id or entry.entry_id or entry.name or hashlib.sha256(entry.content.encode("utf-8")).hexdigest()[:20]
        return cls(identifier, entry.content, scope=scope, role_id=role_id, audience=audience,
                   enabled=entry.enabled, priority=entry.priority, name=entry.name,
                   keywords=entry.keywords, aliases=entry.aliases, template=entry.template,
                   native_scope_ids=native_scope_ids, scope_kind=scope_kind)

    @classmethod
    def from_chunk(
        cls,
        chunk: KnowledgeChunk,
        *,
        candidate_id: str | None = None,
        scope: ScopeRef | None = None,
        scope_kind: ScopeKind | None = None,
        role_id: str | None = None,
        audience: tuple[SubjectRef, ...] = (),
        priority: int = 100,
        keywords: tuple[str, ...] = (),
        aliases: tuple[str, ...] = (),
        native_scope_ids: tuple[str, ...] = (),
    ) -> "KnowledgeCandidate":
        identifier = candidate_id or ":".join((chunk.knowledge_base_id, chunk.document_id, str(chunk.chunk_index)))
        return cls(identifier, chunk.text, scope=scope, scope_kind=scope_kind, role_id=role_id,
                   audience=audience, priority=priority, knowledge_base_id=chunk.knowledge_base_id,
                   document_id=chunk.document_id, document_name=chunk.document_name,
                   chunk_index=chunk.chunk_index, keywords=keywords, aliases=aliases,
                   native_scope_ids=native_scope_ids)


@dataclass(frozen=True)
class KnowledgeQuery:
    text: str
    scope: ScopeRef
    role_id: str | None = None
    persona_id: str | None = None
    subject: SubjectRef | None = None
    audience: tuple[SubjectRef, ...] = ()
    max_hits: int = 8
    max_chars: int = 6000
    max_per_document: int = 2
    allow_sampling: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("knowledge query text must be text")
        if not isinstance(self.scope, ScopeRef):
            raise ValueError("knowledge query scope must be explicit")
        for field_name in ("max_hits", "max_chars", "max_per_document"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field_name} must be positive")
        if type(self.allow_sampling) is not bool:
            raise ValueError("allow_sampling must be boolean")
        object.__setattr__(self, "role_id", self.role_id.strip() if isinstance(self.role_id, str) and self.role_id.strip() else None)
        object.__setattr__(self, "persona_id", self.persona_id.strip() if isinstance(self.persona_id, str) and self.persona_id.strip() else None)
        object.__setattr__(self, "audience", tuple(dict.fromkeys(self.audience)))


@dataclass(frozen=True)
class KnowledgeHit:
    candidate: KnowledgeCandidate
    score: int
    sampled: bool = False
    source: SourceRef | None = None

    @property
    def text(self) -> str:
        return self.candidate.text


@dataclass(frozen=True)
class KnowledgeSelection:
    query: KnowledgeQuery
    hits: tuple[KnowledgeHit, ...]
    sampled: bool = False
    characters: int = 0

    @property
    def empty(self) -> bool:
        return not self.hits

    @property
    def prompt(self) -> str:
        if not self.hits:
            return ""
        parts = [
            "以下资料仅作为角色背景参考，可能不完整或已过期。不要把资料自动当成当前事实；需要确认时请提问或使用带证据的表达。",
        ]
        for hit in self.hits:
            candidate = hit.candidate
            title = candidate.document_name or candidate.name or candidate.candidate_id
            parts.append(f"[{title}]\n{candidate.text}")
        return "\n\n".join(parts)


class KnowledgeProvider(Protocol):
    def snapshot(self) -> tuple[KnowledgeCandidate, ...]:
        """Return a detached, deterministic candidate snapshot."""


class InMemoryKnowledgeProvider:
    """Small provider used by the local host and synthetic acceptance tests."""

    def __init__(self, candidates: Iterable[KnowledgeCandidate] = ()) -> None:
        self._candidates = tuple(candidates)

    def snapshot(self) -> tuple[KnowledgeCandidate, ...]:
        return self._candidates

    def replace(self, candidates: Iterable[KnowledgeCandidate]) -> None:
        self._candidates = tuple(candidates)


def authorized(candidate: KnowledgeCandidate, query: KnowledgeQuery) -> bool:
    """Exact boundary check shared by background material and member clues.

    Imported entries narrow their own visibility with the same rules the query
    uses, so one group's entry can never be selected for another group, another
    role or another installation.
    """
    if not candidate.enabled:
        return False
    if candidate.scope is not None and candidate.scope != query.scope:
        return False
    if candidate.scope_kind is not None and candidate.scope_kind is not query.scope.kind:
        return False
    if candidate.native_scope_ids and query.scope.native_scope_id not in candidate.native_scope_ids:
        return False
    if candidate.scope_route and (query.scope.kind is not ScopeKind.GROUP
            or (query.scope.platform, query.scope.bot_id, query.scope.account_id) != candidate.scope_route):
        return False
    role_values = {value for value in (query.role_id, query.persona_id) if value}
    candidate_roles = {value for value in (candidate.role_id, candidate.persona_id) if value}
    if candidate_roles and not (role_values & candidate_roles):
        return False
    if candidate.subject is not None and candidate.subject != query.subject:
        return False
    if candidate.audience:
        query_recipients = set(query.audience or ((query.subject,) if query.subject is not None else ()))
        if not query_recipients.issubset(set(candidate.audience)):
            return False
    return True


_authorized = authorized  # kept as the private name earlier callers may import


def _score(candidate: KnowledgeCandidate, query_text: str) -> int:
    query = _clean(query_text)
    if not query:
        return 0
    terms = _tokens(query)
    fields = (
        (candidate.name, 7),
        (" ".join(candidate.aliases), 9),
        (" ".join(candidate.keywords), 10),
        (candidate.document_name, 5),
        (candidate.text, 2),
    )
    score = 0
    for value, weight in fields:
        normalized = _clean(value)
        if query in normalized:
            score += weight * 3
        score += sum(weight for term in terms if term and term in normalized)
    return score


def publish_material(
    sources: SourceRepository,
    *,
    text: str,
    audience: AudienceRef,
    observed_at: datetime,
    key: str,
    owner: str = "knowledge.v2",
    source_prefix: str = "knowledge",
) -> SourceRef:
    """Publish one bounded knowledge text as an immutable governed source.

    Both background material and member clues use this path so a sealed turn
    always carries a re-readable reference instead of an unbacked string.  A
    stable key that conflicts with different content stops the turn rather than
    silently reusing either version.
    """
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    suffix = f"{audience.scope.key}:{key}:{content_hash}"
    source_id = f"{source_prefix}:{hashlib.sha256(suffix.encode('utf-8')).hexdigest()}"
    lineage = hashlib.sha256((source_id + ":lineage").encode("utf-8")).hexdigest()
    reference = SourceRef(source_id, owner, audience.scope, VersionRef(lineage, 1), observed_at)
    published = sources.publish(SourceRecord(reference, audience, content_hash, text), observed_at=observed_at)
    if not published.is_success:
        from companion_v2.execution.models import require
        require(published)
    return reference


class KnowledgeRetriever:
    """Filter, rank, budget and optionally publish knowledge candidates."""

    def __init__(self, provider: KnowledgeProvider | Iterable[KnowledgeCandidate]) -> None:
        self.provider = provider if hasattr(provider, "snapshot") else InMemoryKnowledgeProvider(provider)

    def candidates(self) -> tuple[KnowledgeCandidate, ...]:
        return tuple(self.provider.snapshot())

    def select(self, query: KnowledgeQuery) -> KnowledgeSelection:
        authorized_candidates = [candidate for candidate in self.candidates() if authorized(candidate, query)]
        ranked = sorted(
            ((candidate, _score(candidate, query.text), index) for index, candidate in enumerate(authorized_candidates)),
            key=lambda item: (-item[1], -item[0].priority, item[0].knowledge_base_id,
                              item[0].document_id, item[0].chunk_index, item[0].candidate_id, item[2]),
        )
        matched = [item for item in ranked if item[1] > 0]
        sampled = False
        if not matched and query.allow_sampling:
            # Keep one representative per document so a broad role still gets
            # a small amount of context without turning a miss into a dump.
            matched = ranked
            sampled = bool(matched)
        selected: list[KnowledgeHit] = []
        per_document: dict[tuple[str, str], int] = {}
        seen_text: set[str] = set()
        characters = 0
        for candidate, score, _ in matched:
            key = (candidate.knowledge_base_id, candidate.document_id or candidate.candidate_id)
            normalized_text = _clean(candidate.text)
            if normalized_text in seen_text:
                continue
            # AstrBot chunks frequently overlap by one neighboring chunk.  Do
            # not spend the budget twice on an adjacent chunk from one document.
            if selected and candidate.document_id and selected[-1].candidate.document_id == candidate.document_id:
                previous = selected[-1].candidate.chunk_index
                if abs(candidate.chunk_index - previous) <= 1:
                    continue
            if per_document.get(key, 0) >= query.max_per_document:
                continue
            if len(selected) >= query.max_hits:
                break
            separator = 2 if selected else 0
            if characters + separator + len(candidate.text) > query.max_chars:
                continue
            selected.append(KnowledgeHit(candidate, score, sampled=sampled))
            seen_text.add(normalized_text)
            per_document[key] = per_document.get(key, 0) + 1
            characters += separator + len(candidate.text)
        return KnowledgeSelection(query, tuple(selected), sampled=sampled, characters=characters)

    def publish_selection(
        self,
        selection: KnowledgeSelection,
        *,
        sources: SourceRepository,
        audience: AudienceRef,
        observed_at: datetime,
        owner: str = "knowledge.v2",
        source_prefix: str = "knowledge",
    ) -> KnowledgeSelection:
        published: list[KnowledgeHit] = []
        for hit in selection.hits:
            candidate = hit.candidate
            reference = publish_material(
                sources,
                text=candidate.text,
                audience=audience,
                observed_at=observed_at,
                key=f"{candidate.knowledge_base_id}:{candidate.document_id}:{candidate.chunk_index}:{candidate.candidate_id}",
                owner=owner,
                source_prefix=source_prefix,
            )
            published.append(KnowledgeHit(candidate, hit.score, hit.sampled, reference))
        return KnowledgeSelection(selection.query, tuple(published), selection.sampled, selection.characters)

    def retrieve(
        self,
        query: KnowledgeQuery,
        *,
        sources: SourceRepository | None = None,
        audience: AudienceRef | None = None,
        observed_at: datetime | None = None,
        owner: str = "knowledge.v2",
        source_prefix: str = "knowledge",
    ) -> KnowledgeSelection:
        selection = self.select(query)
        if sources is None or not selection.hits:
            return selection
        if audience is None or observed_at is None:
            raise ValueError("publishing knowledge requires audience and observed_at")
        return self.publish_selection(selection, sources=sources, audience=audience,
                                      observed_at=observed_at, owner=owner, source_prefix=source_prefix)


def query_for_context(
    text: str,
    *,
    scope: ScopeRef,
    role_id: str | None = None,
    persona_id: str | None = None,
    subject: SubjectRef | None = None,
    audience: Sequence[SubjectRef] = (),
    max_hits: int = 8,
    max_chars: int = 6000,
    max_per_document: int = 2,
) -> KnowledgeQuery:
    """Construct a bounded query without exposing host identity to the provider."""

    return KnowledgeQuery(text, scope, role_id=role_id, persona_id=persona_id, subject=subject,
                          audience=tuple(audience), max_hits=max_hits, max_chars=max_chars,
                          max_per_document=max_per_document)


__all__ = [
    "InMemoryKnowledgeProvider",
    "KnowledgeCandidate",
    "KnowledgeHit",
    "KnowledgeProvider",
    "KnowledgeQuery",
    "KnowledgeRetriever",
    "KnowledgeSelection",
    "authorized",
    "publish_material",
    "query_for_context",
]
