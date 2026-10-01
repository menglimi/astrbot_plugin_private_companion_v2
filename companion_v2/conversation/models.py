"""Contracts for the G3 isolated conversation loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from companion_v2.foundation.refs import OperationRef, PartRef, ReferenceValidationError, ScopeRef, SourceRef, normalize_utc
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal
from companion_v2.identity_policy.personas import RuntimeScope
from companion_v2.storage.models import OperationReceipt


def _opaque(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReferenceValidationError(f"{field} must be a non-blank opaque string")
    return value


@dataclass(frozen=True)
class InboundConversationEvent:
    """A host-authenticated input envelope without a body-derived identity fallback."""

    event_id: str
    principal: AuthenticatedHostPrincipal
    scope: ScopeRef
    source: SourceRef
    capability: str
    input_hash: str
    received_at: datetime
    runtime_scope: RuntimeScope | None = None

    def __post_init__(self) -> None:
        _opaque(self.event_id, field="event_id")
        _opaque(self.capability, field="capability")
        _opaque(self.input_hash, field="input_hash")
        if self.scope != self.source.scope:
            raise ReferenceValidationError("event scope must match its source scope")
        if self.principal.installation_id != self.scope.installation_id:
            raise ReferenceValidationError("event principal crosses installation")
        if self.scope.is_resolved and (self.principal.platform != self.scope.platform
                                      or self.principal.bot_id != self.scope.bot_id
                                      or self.principal.account_id != self.scope.account_id):
            raise ReferenceValidationError("event principal does not match bot/account route")
        if self.runtime_scope is not None:
            if self.runtime_scope.route.scope != self.scope or self.runtime_scope.host_id != self.principal.host_id:
                raise ReferenceValidationError("event runtime scope does not match its trusted route")
        object.__setattr__(
            self,
            "received_at",
            normalize_utc(self.received_at, field="received_at"),
        )

    @property
    def scoped_key(self) -> str:
        """Namespace the native event by its trusted route, preserving old fixtures."""
        document = [self.scope.installation_id, self.scope.platform, self.scope.kind.value,
                    self.scope.native_scope_id, self.event_id]
        if self.scope.is_resolved:
            document.extend((self.scope.bot_id, self.scope.account_id, self.scope.conversation_id, self.scope.session_id))
        digest = hashlib.sha256(json.dumps(document, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return "scoped-event-" + digest


@dataclass(frozen=True)
class InteractionPlan:
    event_id: str
    intent: str
    source: SourceRef


@dataclass(frozen=True)
class ExpressionPlan:
    operation: OperationRef
    part: PartRef
    interaction: InteractionPlan


@dataclass(frozen=True)
class RenderedExpression:
    plan: ExpressionPlan
    text: str
    payload_hash: str


@dataclass(frozen=True)
class ConversationReceipt:
    event: InboundConversationEvent
    operation_receipt: OperationReceipt
    expression: RenderedExpression
    inbox_replayed: bool


@dataclass
class ExternalEffectCounters:
    """Proof object for G3: real external integrations remain unused."""

    model_calls: int = 0
    tool_calls: int = 0
    platform_sends: int = 0
    tts_calls: int = 0

    def all_zero(self) -> bool:
        return all(
            value == 0
            for value in (
                self.model_calls,
                self.tool_calls,
                self.platform_sends,
                self.tts_calls,
            )
        )


class DeterministicFakeRenderer:
    """Renders a stable local fixture; it is not a model, tool, TTS, or sender."""

    def __init__(self) -> None:
        self.render_calls = 0

    def render(self, plan: ExpressionPlan) -> RenderedExpression:
        self.render_calls += 1
        source = plan.interaction.source
        text = (
            "isolated-ack:"
            f"{plan.interaction.intent}:"
            f"{source.source_id}:"
            f"{source.version.revision}"
        )
        payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return RenderedExpression(plan=plan, text=text, payload_hash=payload_hash)
