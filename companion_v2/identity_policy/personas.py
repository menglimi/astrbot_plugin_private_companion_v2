"""Trusted route registration and deterministic, time-aware persona selection.

Binding history is append-only. Resolution replays only matching selectors so a
switch away and back fences an old turn even when no reader observed the switch.
It is a read operation and composes with domain read snapshots and transactions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import Enum
import hashlib
import json

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import (
    ReferenceValidationError, RoleOwnerRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef, normalize_utc,
)
from companion_v2.storage.codec import scope_values
from companion_v2.storage.runtime import StorageRuntime

from .models import RoleBinding, _opaque


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


class SelectorKind(str, Enum):
    INSTALLATION = "installation"
    BOT = "bot"
    USER = "user"
    CONVERSATION = "conversation"
    CONVERSATION_USER = "conversation_user"
    GROUP = "group"
    SESSION = "session"


@dataclass(frozen=True)
class PersonaSelector:
    installation_id: str
    kind: SelectorKind
    bot_id: str | None = None
    platform: str | None = None
    account_id: str | None = None
    conversation_kind: ScopeKind | None = None
    conversation_id: str | None = None
    user_id: str | None = None
    group_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        _opaque(self.installation_id, field="installation_id")
        if not isinstance(self.kind, SelectorKind):
            raise ReferenceValidationError("explicit selector kind required")
        for name in ("bot_id", "platform", "account_id", "conversation_id", "user_id", "group_id", "session_id"):
            if getattr(self, name) is not None:
                _opaque(getattr(self, name), field=name)
        if (self.platform is None) != (self.account_id is None):
            raise ReferenceValidationError("selector platform and account must be supplied together")
        if self.kind is SelectorKind.INSTALLATION:
            if self.bot_id is not None:
                raise ReferenceValidationError("installation selector must not name a bot")
        elif self.bot_id is None:
            raise ReferenceValidationError("selector requires a logical bot")
        if self.kind not in (SelectorKind.INSTALLATION, SelectorKind.BOT) and self.platform is None:
            raise ReferenceValidationError("specific selectors require the platform/account namespace")
        required = {
            SelectorKind.INSTALLATION: set(), SelectorKind.BOT: set(),
            SelectorKind.USER: {"user_id"}, SelectorKind.GROUP: {"group_id"},
            SelectorKind.CONVERSATION: {"conversation_kind", "conversation_id"},
            SelectorKind.CONVERSATION_USER: {"conversation_kind", "conversation_id", "user_id"},
            SelectorKind.SESSION: {"conversation_kind", "conversation_id", "session_id"},
        }[self.kind]
        present = {name for name in ("conversation_kind", "conversation_id", "user_id", "group_id", "session_id")
                   if getattr(self, name) is not None}
        if required != present:
            raise ReferenceValidationError("selector contains missing or inapplicable dimensions")
        if self.conversation_kind is not None and self.conversation_kind not in (
            ScopeKind.PRIVATE, ScopeKind.GROUP, ScopeKind.THREAD,
        ):
            raise ReferenceValidationError("selector needs a conversation kind")
        if self.kind is SelectorKind.CONVERSATION_USER and self.conversation_kind is ScopeKind.GROUP:
            raise ReferenceValidationError("group member persona selection is not enabled")

    @property
    def key(self) -> str:
        return hashlib.sha256(_json(asdict(self)).encode("utf-8")).hexdigest()

    @classmethod
    def restore(cls, data: dict) -> PersonaSelector:
        data = {**data, "kind": SelectorKind(data["kind"])}
        if data["conversation_kind"] is not None:
            data["conversation_kind"] = ScopeKind(data["conversation_kind"])
        return cls(**data)


@dataclass(frozen=True)
class ConversationRoute:
    """Host-registered participants; a group's speaker is not its private owner."""

    scope: ScopeRef
    user: SubjectRef | None = None
    group_id: str | None = None
    thread_parent_kind: ScopeKind | None = None
    initial_revision: int = 0

    def __post_init__(self) -> None:
        if not self.scope.is_resolved or self.scope.kind not in (ScopeKind.PRIVATE, ScopeKind.GROUP, ScopeKind.THREAD):
            raise ReferenceValidationError("scope_unresolved")
        if type(self.initial_revision) is not int or self.initial_revision < 0:
            raise ReferenceValidationError("invalid route revision baseline")
        if self.scope.kind is ScopeKind.THREAD:
            if self.thread_parent_kind not in (ScopeKind.PRIVATE, ScopeKind.GROUP):
                raise ReferenceValidationError("thread requires its explicit parent scene kind")
        elif self.thread_parent_kind is not None:
            raise ReferenceValidationError("only threads have a parent scene kind")
        if self.scene_kind is ScopeKind.PRIVATE:
            if (self.user is None or self.user.kind is not SubjectKind.HUMAN
                    or self.user.installation_id != self.scope.installation_id or self.group_id is not None):
                raise ReferenceValidationError("private route requires one registered human participant")
        elif self.user is not None or self.group_id is None:
            raise ReferenceValidationError("group route requires a group and must not retain its speaker as owner")
        if self.group_id is not None:
            _opaque(self.group_id, field="group_id")

    @property
    def scene_kind(self) -> ScopeKind:
        return self.thread_parent_kind or self.scope.kind

    def document(self) -> dict:
        return {**asdict(self), "scope": self.scope.document()}

    @classmethod
    def restore(cls, data: dict) -> ConversationRoute:
        data = {**data, "scope": ScopeRef.restore(data["scope"])}
        if data["user"] is not None:
            data["user"] = SubjectRef(**{**data["user"], "kind": SubjectKind(data["user"]["kind"])})
        if data["thread_parent_kind"] is not None:
            data["thread_parent_kind"] = ScopeKind(data["thread_parent_kind"])
        return cls(**data)

    def selectors(self) -> tuple[tuple[PersonaSelector, int], ...]:
        s = self.scope
        common = {"installation_id": s.installation_id, "bot_id": s.bot_id,
                  "platform": s.platform, "account_id": s.account_id}
        result = [
            (PersonaSelector(s.installation_id, SelectorKind.INSTALLATION), 0),
            (PersonaSelector(s.installation_id, SelectorKind.INSTALLATION,
                             platform=s.platform, account_id=s.account_id), 0),
            (PersonaSelector(s.installation_id, SelectorKind.BOT, bot_id=s.bot_id), 2),
            (PersonaSelector(kind=SelectorKind.BOT, **common), 2),
        ]
        conversation = {**common, "conversation_kind": s.kind, "conversation_id": s.conversation_id}
        result.append((PersonaSelector(kind=SelectorKind.CONVERSATION, **conversation), 5))
        result.append((PersonaSelector(kind=SelectorKind.SESSION, session_id=s.session_id, **conversation), 7))
        if self.scene_kind is ScopeKind.PRIVATE:
            result.append((PersonaSelector(kind=SelectorKind.USER, user_id=self.user.subject_id, **common), 4))
            result.append((PersonaSelector(kind=SelectorKind.CONVERSATION_USER,
                                           user_id=self.user.subject_id, **conversation), 6))
        else:
            result.append((PersonaSelector(kind=SelectorKind.GROUP, group_id=self.group_id, **common), 5))
        return tuple(result)


@dataclass(frozen=True)
class PersonaBinding:
    binding_id: str
    selector: PersonaSelector
    role: SubjectRef
    precedence: int
    effective_from: datetime
    source: str
    authority: str
    overridable: bool = True
    effective_until: datetime | None = None
    revision: int = 1
    revoked: bool = False

    def __post_init__(self) -> None:
        for name in ("binding_id", "source", "authority"):
            _opaque(getattr(self, name), field=name)
        if self.role.kind is not SubjectKind.BOT or self.role.installation_id != self.selector.installation_id:
            raise ReferenceValidationError("persona must belong to the selector installation")
        if type(self.precedence) is not int or type(self.revision) is not int or self.revision < 1:
            raise ReferenceValidationError("invalid persona precedence or revision")
        if type(self.overridable) is not bool or type(self.revoked) is not bool:
            raise ReferenceValidationError("persona flags must be booleans")
        object.__setattr__(self, "effective_from", normalize_utc(self.effective_from, field="effective_from"))
        if self.effective_until is not None:
            object.__setattr__(self, "effective_until", normalize_utc(self.effective_until, field="effective_until"))
            if self.effective_until <= self.effective_from:
                raise ReferenceValidationError("persona validity interval must be positive")

    def document(self) -> dict:
        return {**asdict(self), "effective_from": self.effective_from.isoformat(),
                "effective_until": self.effective_until.isoformat() if self.effective_until else None}

    @classmethod
    def restore(cls, data: dict) -> PersonaBinding:
        return cls(**{**data, "selector": PersonaSelector.restore(data["selector"]),
                      "role": SubjectRef(**{**data["role"], "kind": SubjectKind(data["role"]["kind"])}),
                      "effective_from": datetime.fromisoformat(data["effective_from"]),
                      "effective_until": datetime.fromisoformat(data["effective_until"]) if data["effective_until"] else None})


@dataclass(frozen=True)
class PersonaResolution:
    binding: RoleBinding
    selected: PersonaBinding
    route: ConversationRoute


@dataclass(frozen=True)
class RuntimeScope:
    """Invocation context, deliberately separate from stable role ownership."""

    ecosystem_id: str
    runtime_instance_id: str
    host_kind: str
    host_id: str
    route: ConversationRoute
    persona: RoleBinding

    def __post_init__(self) -> None:
        for name in ("ecosystem_id", "runtime_instance_id", "host_kind", "host_id"):
            _opaque(getattr(self, name), field=name)
        if self.persona.scope != self.route.scope:
            raise ReferenceValidationError("runtime persona and route differ")

    @property
    def owner(self) -> RoleOwnerRef:
        return RoleOwnerRef(self.route.scope.installation_id, self.route.scope.bot_id, self.persona.role.subject_id)


@dataclass(frozen=True)
class RuntimeIdentity:
    """Process identity supplied by assembly, never inferred from a chat event."""

    ecosystem_id: str
    runtime_instance_id: str
    host_kind: str
    host_id: str

    def __post_init__(self) -> None:
        for name in ("ecosystem_id", "runtime_instance_id", "host_kind", "host_id"):
            _opaque(getattr(self, name), field=name)

    def bind(self, route: ConversationRoute, persona: RoleBinding) -> RuntimeScope:
        return RuntimeScope(self.ecosystem_id, self.runtime_instance_id, self.host_kind, self.host_id,
                            route, persona)


class PersonaDirectory:
    """Trusted control-plane primitives; public routes must authorize management."""

    def __init__(self, runtime: StorageRuntime) -> None:
        self.runtime = runtime

    def route(self, scope: ScopeRef) -> ConversationRoute | None:
        self._installation(scope.installation_id)
        row = self.runtime.read_one("SELECT record_json FROM conversation_routes WHERE scope_key = ?", (scope.key,))
        return ConversationRoute.restore(json.loads(row["record_json"])) if row else None

    def _installation(self, installation_id: str) -> None:
        if installation_id != self.runtime.installation_id:
            raise ReferenceValidationError("scope_installation_mismatch")

    def register_route(self, route: ConversationRoute, *, observed_at: datetime,
                       adopt_exact_revision: int | None = None) -> ConversationRoute:
        """Register immutable participants; adoption of an existing exact binding is explicit."""
        self._installation(route.scope.installation_id)
        if route.initial_revision != 0:
            raise ReferenceValidationError("route baseline is assigned only by exact-binding adoption")
        with self.runtime.transaction() as connection:
            current = self.route(route.scope)
            if current is not None:
                if replace(current, initial_revision=0) != route:
                    raise ReferenceValidationError("conversation_route_conflict")
                return current
            exact = connection.execute(
                """SELECT role_id, revision FROM role_bindings WHERE installation_id = ? AND platform = ?
                   AND scope_kind = ? AND native_scope_id = ? AND bot_id = ? AND account_id = ?
                   AND conversation_id = ? AND session_id = ?""", scope_values(route.scope),
            ).fetchone()
            if exact is not None:
                if type(adopt_exact_revision) is not int or adopt_exact_revision != exact["revision"]:
                    raise ReferenceValidationError("role_binding_adoption_required")
                # Replaying the adopted selection adds one transition, so start
                # immediately before the exact row's established revision.
                route = replace(route, initial_revision=exact["revision"] - 1)
            elif adopt_exact_revision is not None:
                raise ReferenceValidationError("role_binding_revision_conflict")
            connection.execute("INSERT INTO conversation_routes VALUES (?, ?)", (route.scope.key, _json(route.document())))
            if exact is not None:
                self.set_binding(PersonaBinding(
                    self.window_binding_id(route.scope), dict((selector.kind, selector) for selector, _ in route.selectors())[SelectorKind.SESSION],
                    SubjectRef(route.scope.installation_id, SubjectKind.BOT, exact["role_id"]), 0, observed_at,
                    "exact-window-adoption", "trusted-control-plane",
                ), expected_revision=0, observed_at=observed_at)
            return route

    @staticmethod
    def window_binding_id(scope: ScopeRef) -> str:
        return "window:" + scope.key

    def binding(self, binding_id: str) -> PersonaBinding | None:
        row = self.runtime.read_one(
            "SELECT record_json FROM persona_binding_events WHERE binding_id = ? ORDER BY revision DESC LIMIT 1", (binding_id,),
        )
        return PersonaBinding.restore(json.loads(row["record_json"])) if row else None

    def set_binding(self, binding: PersonaBinding, *, expected_revision: int, observed_at: datetime) -> PersonaBinding:
        self._installation(binding.selector.installation_id)
        now = normalize_utc(observed_at, field="observed_at")
        with self.runtime.transaction() as connection:
            current = self.binding(binding.binding_id)
            revision = current.revision if current else 0
            if type(expected_revision) is not int or expected_revision != revision or binding.revision != revision + 1:
                raise ReferenceValidationError("persona_binding_revision_conflict")
            if current and current.selector != binding.selector:
                raise ReferenceValidationError("selector is immutable; revoke and register a new binding")
            if (current and not current.overridable
                    and (current.authority != binding.authority or current.source != binding.source)):
                raise ReferenceValidationError("persona_binding_override_denied")
            latest = connection.execute("SELECT recorded_at FROM persona_binding_events ORDER BY sequence DESC LIMIT 1").fetchone()
            if latest and now < datetime.fromisoformat(latest["recorded_at"]):
                raise ReferenceValidationError("persona_history_clock_regressed")
            connection.execute(
                """INSERT INTO persona_binding_events(binding_id, revision, selector_key, recorded_at, record_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (binding.binding_id, binding.revision, binding.selector.key, now.isoformat(), _json(binding.document())),
            )
            return binding

    def revoke_binding(self, binding_id: str, *, expected_revision: int, observed_at: datetime) -> PersonaBinding:
        with self.runtime.transaction():
            current = self.binding(binding_id)
            if current is None:
                raise ReferenceValidationError("persona_binding_not_found")
            return self.set_binding(replace(current, revision=current.revision + 1, revoked=True),
                                    expected_revision=expected_revision, observed_at=observed_at)

    @staticmethod
    def _select(current: dict[str, PersonaBinding], ranks: dict[str, int], at: datetime):
        active = [b for b in current.values() if not b.revoked and b.effective_from <= at
                  and (b.effective_until is None or at < b.effective_until)]
        if not active:
            return ("role_binding_missing",), None
        protected = [b for b in active if not b.overridable]
        if protected:
            # Multiple protected authorities require a management decision, even
            # when they happen to name the same persona.
            winners = protected
        else:
            priority = max((ranks[b.selector.key], b.precedence) for b in active)
            winners = [b for b in active if (ranks[b.selector.key], b.precedence) == priority]
        if len(winners) != 1:
            return ("persona_binding_conflict", *sorted((b.binding_id, b.revision) for b in winners)), None
        selected = winners[0]
        return ("selected", selected.binding_id, selected.revision), selected

    def resolve(self, scope: ScopeRef, *, observed_at: datetime) -> Outcome[PersonaResolution]:
        now = normalize_utc(observed_at, field="observed_at")
        if scope.installation_id != self.runtime.installation_id:
            return Outcome.failed("scope_installation_mismatch", "persona belongs to another installation")
        with self.runtime.read_snapshot():
            route = self.route(scope)
            if route is None:
                return Outcome.failed("scope_unresolved", "conversation participants have not been registered")
            ranks = {selector.key: rank for selector, rank in route.selectors()}
            placeholders = ",".join("?" for _ in ranks)
            rows = self.runtime.read_all(
                f"SELECT * FROM persona_binding_events WHERE selector_key IN ({placeholders}) ORDER BY sequence", tuple(ranks),
            )
            points = []
            for row in rows:
                recorded = datetime.fromisoformat(row["recorded_at"])
                binding = PersonaBinding.restore(json.loads(row["record_json"]))
                points.append((recorded, row["sequence"], 0, binding))
                for boundary in (binding.effective_from, binding.effective_until):
                    if boundary is not None and boundary > recorded:
                        points.append((boundary, row["sequence"], 1, binding))
            current: dict[str, PersonaBinding] = {}
            signature, selected = ("role_binding_missing",), None
            revision = route.initial_revision
            for at, _, boundary, binding in sorted(points, key=lambda point: point[:3]):
                if at > now:
                    break
                if boundary:
                    if current.get(binding.binding_id) != binding:
                        continue
                else:
                    current[binding.binding_id] = binding
                next_signature, selected = self._select(current, ranks, at)
                if signature != next_signature:
                    revision += 1
                    signature = next_signature
            if selected is None:
                return Outcome.failed(signature[0], "no unambiguous active persona binding for this conversation")
            return Outcome.success(PersonaResolution(RoleBinding(scope, selected.role, revision), selected, route))
