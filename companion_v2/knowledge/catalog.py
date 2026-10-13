"""Versioned, invalidatable storage for imported worldbook and knowledge sources.

V2 adds no table and no schema version for this capability.  One reused
``memory_views`` row per (source, binding) holds the current import revision: its
parsed entries, its member entries and its import outcome.  The owner key lives
in its own namespace, so the memory recall projection and the experience query
never see these rows -- they are a knowledge catalogue, not memories.

Three properties matter and are enforced here rather than by convention:

* **Versioned.**  A new revision is written only when the parsed content digest
  changes, so re-reading an unchanged file cannot churn revisions.
* **Invalidatable.**  ``retire`` marks a row ``retracted``; a retired or missing
  source contributes nothing, so stale entries can never be injected after the
  operator removed the source.
* **Unreadable rows are skipped.**  A row whose document cannot be decoded is
  dropped from the snapshot instead of failing the turn that reads it.

Member entries stay in this catalogue as attribution clues and are never turned
into a fact, a permission or a member profile.
"""

from __future__ import annotations

import json

from companion_v2.execution.models import digest, encode, stamp
from companion_v2.foundation.refs import ScopeKind, ScopeRef

from .retrieval import KnowledgeCandidate
from .member_profiles import member_memories


KIND = "knowledge.source.v1"
OWNER = "knowledge.v2"
SCHEMA = "knowledge.source.v1"
ACTIVE = "active"
RETRACTED = "retracted"
INSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision, state = excluded.state,
        document_json = excluded.document_json, source_json = excluded.source_json,
        updated_at = excluded.updated_at"""


def _text(value, field, *, limit=512, empty=False):
    if value is None and empty:
        return None
    if type(value) is not str or not value or value != value.strip() or len(value) > limit:
        raise ValueError(f"{field} must be a bounded non-blank string")
    return value


def _strings(values, field, *, limit=64):
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    cleaned = []
    for value in values:
        if type(value) is not str:
            raise ValueError(f"{field} must contain text")
        text = value.strip()
        if text and text not in cleaned:
            cleaned.append(text[:limit])
    return tuple(cleaned)


def installation_owner_key(installation_id: str) -> str:
    """One catalogue namespace per installation, separate from every memory owner."""
    return digest([SCHEMA, _text(installation_id, "installation_id")])


class SourceBinding:
    """Which role and windows one imported source is allowed to serve.

    ``role_id`` narrows a source to one companion role; ``native_scope_ids`` with
    ``scope_kind`` narrows it to named windows (for example one group).  An empty
    binding means installation-wide reference material.
    """

    __slots__ = ("installation_id", "role_id", "persona_id", "native_scope_ids", "scope_kind",
                 "scope_route")

    def __init__(self, installation_id, *, role_id=None, persona_id=None,
                 native_scope_ids=(), scope_kind=None, scope_route=None):
        self.installation_id = _text(installation_id, "installation_id")
        self.role_id = _text(role_id, "role_id", empty=True)
        self.persona_id = _text(persona_id, "persona_id", empty=True)
        self.native_scope_ids = _strings(native_scope_ids, "native_scope_ids", limit=256)
        if self.native_scope_ids and not isinstance(scope_kind, ScopeKind):
            raise ValueError("bounding a source to named windows needs an explicit scope kind")
        if scope_kind is not None and not isinstance(scope_kind, ScopeKind):
            raise ValueError("scope_kind must be a ScopeKind")
        self.scope_kind = scope_kind
        if scope_route is None:
            self.scope_route = None
        else:
            if (not isinstance(scope_route, (list, tuple)) or len(scope_route) != 3
                    or not all(type(value) is str and value.strip() for value in scope_route)
                    or not self.native_scope_ids or not isinstance(scope_kind, ScopeKind)):
                raise ValueError("scope_route requires a bounded native scope and explicit scope kind")
            self.scope_route = tuple(value.strip() for value in scope_route)

    @property
    def document(self) -> dict:
        result = {"installation_id": self.installation_id, "role_id": self.role_id,
                  "persona_id": self.persona_id, "native_scope_ids": list(self.native_scope_ids),
                  "scope_kind": self.scope_kind.value if self.scope_kind else None}
        if self.scope_route:
            result["scope_route"] = list(self.scope_route)
        return result

    @property
    def key(self) -> str:
        return digest(self.document)

    @classmethod
    def restore(cls, document) -> "SourceBinding":
        if not isinstance(document, dict):
            raise ValueError("binding must be an object")
        kind = document.get("scope_kind")
        return cls(document.get("installation_id"), role_id=document.get("role_id"),
                   persona_id=document.get("persona_id"),
                   native_scope_ids=document.get("native_scope_ids") or (),
                   scope_kind=ScopeKind(kind) if kind else None,
                   scope_route=document.get("scope_route"))

    def __eq__(self, other) -> bool:
        return isinstance(other, SourceBinding) and self.document == other.document

    def __hash__(self) -> int:
        return hash(self.key)


class EntryDocument:
    """One imported background entry, normalized at import time."""

    __slots__ = ("entry_id", "content", "name", "gender", "priority", "enabled", "keywords",
                 "aliases", "template", "native_scope_ids", "knowledge_base_id", "document_id",
                 "document_name", "chunk_index")

    def __init__(self, entry_id, content, *, name="", gender="", priority=100, enabled=True,
                 keywords=(), aliases=(), template="", native_scope_ids=(), knowledge_base_id="",
                 document_id="", document_name="", chunk_index=0):
        self.entry_id = _text(entry_id, "entry_id", limit=256)
        self.content = _text(content, "content", limit=20000)
        self.name = (name or "").strip()[:120]
        self.gender = (gender or "").strip()[:40]
        if type(priority) is not int or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        self.priority = priority
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        self.enabled = enabled
        self.keywords = _strings(keywords, "keywords", limit=120)
        self.aliases = _strings(aliases, "aliases", limit=120)
        self.template = (template or "").strip().lower()[:40]
        self.native_scope_ids = _strings(native_scope_ids, "native_scope_ids", limit=256)
        self.knowledge_base_id = (knowledge_base_id or "").strip()[:256]
        self.document_id = (document_id or "").strip()[:256]
        self.document_name = (document_name or "").strip()[:256]
        if type(chunk_index) is not int or isinstance(chunk_index, bool) or chunk_index < 0:
            raise ValueError("chunk_index must be a non-negative integer")
        self.chunk_index = chunk_index

    @property
    def document(self) -> dict:
        return {"entry_id": self.entry_id, "content": self.content, "name": self.name,
                "gender": self.gender, "priority": self.priority, "enabled": self.enabled,
                "keywords": list(self.keywords), "aliases": list(self.aliases),
                "template": self.template, "native_scope_ids": list(self.native_scope_ids),
                "knowledge_base_id": self.knowledge_base_id, "document_id": self.document_id,
                "document_name": self.document_name, "chunk_index": self.chunk_index}

    @classmethod
    def restore(cls, document) -> "EntryDocument":
        if not isinstance(document, dict):
            raise ValueError("entry must be an object")
        return cls(document["entry_id"], document["content"], name=document.get("name", ""),
                   gender=document.get("gender", ""), priority=document.get("priority", 100),
                   enabled=document.get("enabled", True), keywords=document.get("keywords") or (),
                   aliases=document.get("aliases") or (), template=document.get("template", ""),
                   native_scope_ids=document.get("native_scope_ids") or (),
                   knowledge_base_id=document.get("knowledge_base_id", ""),
                   document_id=document.get("document_id", ""),
                   document_name=document.get("document_name", ""),
                   chunk_index=document.get("chunk_index", 0))

    def __eq__(self, other) -> bool:
        return isinstance(other, EntryDocument) and self.document == other.document

    def __hash__(self) -> int:
        return hash(self.entry_id)


class MemberEntry:
    """One recorded social profile, without identity or permission authority.

    ``declared_account_ids`` are written in the imported file by whoever wrote
    it.  They are operator material, not an authenticated binding, so nothing
    here may grant access, rewrite a member profile or assert an identity.
    """

    __slots__ = ("entry_id", "name", "aliases", "declared_account_ids", "gender", "content",
                 "priority", "group_ids", "identity_note", "boundary_note", "important_memories")

    def __init__(self, entry_id, *, name="", aliases=(), declared_account_ids=(), gender="",
                 content="", priority=100, group_ids=(), identity_note="", boundary_note="",
                 important_memories=()):
        self.entry_id = _text(entry_id, "entry_id", limit=256)
        self.name = (name or "").strip()[:120]
        self.aliases = _strings(aliases, "aliases", limit=120)
        self.declared_account_ids = _strings(declared_account_ids, "declared_account_ids", limit=64)
        self.gender = (gender or "").strip()[:40]
        self.content = (content or "").strip()[:20000]
        if type(priority) is not int or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        self.priority = priority
        self.group_ids = _strings(group_ids, "group_ids", limit=256)
        self.identity_note = (identity_note or "").strip()[:20000]
        self.boundary_note = (boundary_note or "").strip()[:20000]
        self.important_memories = member_memories(important_memories)

    @property
    def document(self) -> dict:
        return {"entry_id": self.entry_id, "name": self.name, "aliases": list(self.aliases),
                "declared_account_ids": list(self.declared_account_ids), "gender": self.gender,
                "content": self.content, "priority": self.priority, "group_ids": list(self.group_ids),
                "identity_note": self.identity_note, "boundary_note": self.boundary_note,
                "important_memories": [item.document for item in self.important_memories]}

    @classmethod
    def restore(cls, document) -> "MemberEntry":
        if not isinstance(document, dict):
            raise ValueError("member entry must be an object")
        return cls(document["entry_id"], name=document.get("name", ""),
                   aliases=document.get("aliases") or (),
                   declared_account_ids=document.get("declared_account_ids") or (),
                   gender=document.get("gender", ""), content=document.get("content", ""),
                   priority=document.get("priority", 100), group_ids=document.get("group_ids") or (),
                   identity_note=document.get("identity_note", ""),
                   boundary_note=document.get("boundary_note", ""),
                   important_memories=document.get("important_memories") or ())

    @property
    def labels(self) -> tuple[str, ...]:
        """Display labels only; a label is never an identity."""
        values = [self.name, *self.aliases]
        return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))

    def __eq__(self, other) -> bool:
        return isinstance(other, MemberEntry) and self.document == other.document

    def __hash__(self) -> int:
        return hash(self.entry_id)


class SourceVersion:
    """One stored import revision of one source for one binding."""

    __slots__ = ("view_id", "owner_key", "binding", "source_id", "locator", "format", "revision",
                 "state", "digest", "imported_at", "entries", "members", "issues", "code")

    def __init__(self, view_id, owner_key, binding, source_id, locator, format, revision, state,
                 digest_value, imported_at, entries, members, issues, code=""):
        self.view_id = view_id
        self.owner_key = owner_key
        self.binding = binding
        self.source_id = source_id
        self.locator = locator
        self.format = format
        self.revision = revision
        self.state = state
        self.digest = digest_value
        self.imported_at = imported_at
        self.entries = entries
        self.members = members
        self.issues = issues
        self.code = code

    @property
    def active(self) -> bool:
        return self.state == ACTIVE

    @property
    def document(self) -> dict:
        return {"schema": SCHEMA, "source_id": self.source_id, "locator": self.locator,
                "format": self.format, "digest": self.digest, "imported_at": self.imported_at,
                "binding": self.binding.document, "entries": [item.document for item in self.entries],
                "members": [item.document for item in self.members],
                "issues": [list(item) for item in self.issues]}

    def summary(self) -> dict:
        return {"source_id": self.source_id, "locator": self.locator, "format": self.format,
                "revision": self.revision, "state": self.state, "digest": self.digest,
                "imported_at": self.imported_at, "entry_count": len(self.entries),
                "member_entry_count": len(self.members), "issue_count": len(self.issues),
                "issue_code": self.code}


def _row_version(row) -> SourceVersion | None:
    """Decode one catalogue row; a damaged row is skipped, never raised."""
    try:
        document = json.loads(row["document_json"])
        stored = json.loads(row["source_json"])
        if not isinstance(document, dict) or document.get("schema") != SCHEMA:
            return None
        binding = SourceBinding.restore(document["binding"])
        return SourceVersion(
            row["view_id"], row["owner_key"], binding, document["source_id"],
            document.get("locator", ""), document.get("format", ""), int(row["revision"]),
            row["state"], document.get("digest", ""), document.get("imported_at", ""),
            tuple(EntryDocument.restore(item) for item in document.get("entries") or ()),
            tuple(MemberEntry.restore(item) for item in document.get("members") or ()),
            tuple((int(item[0]), str(item[1])) for item in document.get("issues") or ()
                  if isinstance(item, (list, tuple)) and len(item) == 2),
            str(stored.get("code", "")) if isinstance(stored, dict) else "")
    except (KeyError, TypeError, ValueError):
        return None


def source_view_id(binding: SourceBinding, source_id: str) -> str:
    return "knowledge-source-" + digest([SCHEMA, binding.key, source_id])


class KnowledgeCatalog:
    """The only writer and reader of the imported knowledge catalogue."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime

    # -- reads ---------------------------------------------------------------

    def get(self, binding: SourceBinding, source_id: str) -> SourceVersion | None:
        row = self.runtime.read_one(
            "SELECT * FROM memory_views WHERE view_id = ? AND owner_key = ? AND kind = ?",
            (source_view_id(binding, source_id), installation_owner_key(binding.installation_id), KIND))
        return None if row is None else _row_version(row)

    def list(self, installation_id: str, *, limit: int) -> tuple[SourceVersion, ...]:
        """Current catalogue rows, most recently updated first, bounded by limit."""
        if type(limit) is not int or limit < 1:
            raise ValueError("catalogue page size must be a positive integer")
        rows = self.runtime.read_all(
            """SELECT * FROM memory_views WHERE owner_key = ? AND kind = ?
               ORDER BY updated_at DESC, view_id ASC LIMIT ?""",
            (installation_owner_key(installation_id), KIND, limit))
        versions = []
        for row in rows:
            version = _row_version(row)
            if version is not None:
                versions.append(version)
        return tuple(versions)

    def active(self, installation_id: str, *, limit: int) -> tuple[SourceVersion, ...]:
        return tuple(version for version in self.list(installation_id, limit=limit) if version.active)

    # -- writes --------------------------------------------------------------

    def save(self, binding: SourceBinding, *, source_id, locator, format, content_digest, entries,
             members, issues, at, code="") -> SourceVersion:
        """Write the next revision of one source; the previous revision is replaced."""
        current = self.get(binding, source_id)
        revision = (current.revision if current is not None else 0) + 1
        version = SourceVersion(source_view_id(binding, source_id),
                                installation_owner_key(binding.installation_id), binding,
                                _text(source_id, "source_id", limit=512),
                                (locator or "").strip()[:1024], (format or "").strip()[:40],
                                revision, ACTIVE, content_digest, stamp(at), tuple(entries),
                                tuple(members), tuple(issues), code)
        provenance = {"code": code, "previous_revision": revision - 1 if current is not None else None,
                      "previous_digest": current.digest if current is not None else None}
        with self.runtime.transaction() as connection:
            connection.execute(INSERT, (version.view_id, version.owner_key, KIND, revision, ACTIVE,
                                        encode(version.document), encode(provenance), stamp(at)))
        return version

    def retire(self, binding: SourceBinding, source_id: str, *, at, reason="source_absent") -> bool:
        """Invalidate one source so no further turn can inject its entries."""
        current = self.get(binding, source_id)
        if current is None or not current.active:
            return False
        document = {**current.document, "entries": [], "members": []}
        with self.runtime.transaction() as connection:
            connection.execute(INSERT, (current.view_id, current.owner_key, KIND, current.revision + 1,
                                        RETRACTED, encode(document),
                                        encode({"code": reason, "retired_at": stamp(at)}), stamp(at)))
        return True

    # -- projections ---------------------------------------------------------

    def _matching(self, version: SourceVersion, *, role_id, scope_ids, scope_kind, scope) -> bool:
        """Pre-filter with caller hints only; the retriever stays the authority.

        A hint never removes a row the retriever would have authorized, so a
        bounded read can drop clearly unrelated roles and windows while the exact
        boundary check remains in one place.
        """
        binding = version.binding
        if (version.code == "legacy_v1_imported" and binding.scope_kind is ScopeKind.GROUP
                and binding.native_scope_ids and binding.scope_route is None):
            return False
        if role_id is not None and binding.role_id is not None and binding.role_id != role_id:
            return False
        if scope_kind is not None and binding.scope_kind is not None and binding.scope_kind is not scope_kind:
            return False
        if scope_ids and binding.native_scope_ids:
            if binding.scope_kind is not scope_kind:
                return False
            if not set(binding.native_scope_ids) & set(scope_ids):
                return False
        if binding.scope_route:
            if not isinstance(scope, ScopeRef) or scope.kind is not binding.scope_kind:
                return False
            if (scope.platform, scope.bot_id, scope.account_id) != binding.scope_route:
                return False
        return True

    def background_candidates(self, *, installation_id, source_limit, char_budget):
        """Bounded, deterministic candidate snapshot for one installation.

        The provider behind :class:`~companion_v2.knowledge.retrieval.KnowledgeRetriever`
        needs a detached snapshot without knowing the turn, so no role or window
        hint is applied here: every stored boundary travels on the candidate and
        the retriever enforces it exactly.
        """
        if type(char_budget) is not int or char_budget < 1:
            raise ValueError("candidate character budget must be positive")
        candidates, characters = [], 0
        for version in self.list(installation_id, limit=source_limit):
            if not version.active:
                continue
            for entry in version.entries:
                candidate = self._candidate(version, entry)
                if candidate is None or not candidate.enabled:
                    continue
                if characters + len(candidate.text) > char_budget:
                    return tuple(candidates)
                candidates.append(candidate)
                characters += len(candidate.text)
        return tuple(candidates)

    def member_entries(self, *, installation_id, source_limit, role_id=None, scope_ids=(),
                       scope_kind=None, scope=None) -> tuple[MemberEntry, ...]:
        entries = []
        for version in self.list(installation_id, limit=source_limit):
            if not version.active or not self._matching(version, role_id=role_id, scope_ids=scope_ids,
                                                         scope_kind=scope_kind, scope=scope):
                continue
            entries.extend(entry for entry in version.members
                           if not entry.group_ids or not scope_ids
                           or scope_kind is ScopeKind.GROUP and set(entry.group_ids) & set(scope_ids))
        return tuple(entries)

    @staticmethod
    def _candidate(version: SourceVersion, entry: EntryDocument) -> KnowledgeCandidate | None:
        if not entry.content or not entry.enabled:
            return None
        scope_ids = entry.native_scope_ids or version.binding.native_scope_ids
        scope_kind = ScopeKind.GROUP if entry.native_scope_ids else version.binding.scope_kind
        if (version.code == "legacy_v1_imported" and scope_kind is ScopeKind.GROUP
                and scope_ids and version.binding.scope_route is None):
            return None
        return KnowledgeCandidate(
            entry.entry_id, entry.content, scope_kind=scope_kind,
            role_id=version.binding.role_id, persona_id=version.binding.persona_id,
            enabled=entry.enabled, priority=entry.priority, name=entry.name,
            keywords=entry.keywords, aliases=entry.aliases, template=entry.template,
            native_scope_ids=scope_ids, scope_route=version.binding.scope_route,
            knowledge_base_id=entry.knowledge_base_id,
            document_id=entry.document_id, document_name=entry.document_name,
            chunk_index=entry.chunk_index)


class CatalogKnowledgeProvider:
    """Bounded snapshot provider over the catalogue, cached per stored revision."""

    def __init__(self, catalog: KnowledgeCatalog, *, installation_id, source_limit, char_budget) -> None:
        self.catalog = catalog
        self.installation_id = installation_id
        self.source_limit = source_limit
        self.char_budget = char_budget
        self._fingerprint = None
        self._candidates = ()

    def apply_limits(self, *, source_limit, char_budget) -> None:
        """Adopt this turn's configured bounds; a change rebuilds the snapshot."""
        if (source_limit, char_budget) != (self.source_limit, self.char_budget):
            self.source_limit, self.char_budget = source_limit, char_budget
            self._fingerprint, self._candidates = None, ()

    def snapshot(self) -> tuple[KnowledgeCandidate, ...]:
        versions = self.catalog.list(self.installation_id, limit=self.source_limit)
        fingerprint = (self.source_limit, self.char_budget,
                       tuple((version.view_id, version.revision, version.state) for version in versions))
        if fingerprint == self._fingerprint:
            return self._candidates
        candidates = self.catalog.background_candidates(
            installation_id=self.installation_id, source_limit=self.source_limit,
            char_budget=self.char_budget)
        self._fingerprint, self._candidates = fingerprint, candidates
        return candidates


__all__ = [
    "ACTIVE", "CatalogKnowledgeProvider", "EntryDocument", "KIND", "KnowledgeCatalog",
    "MemberEntry", "OWNER", "RETRACTED", "SCHEMA", "SourceBinding", "SourceVersion",
    "installation_owner_key", "source_view_id",
]
