"""The first V2 vertical slice: local input through local outbox, without effects."""

from __future__ import annotations

import hashlib

from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import OperationRef, PartRef, VersionRef
from companion_v2.identity_policy.directory import IdentityDirectory
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.repositories import InboxRepository, OperationRepository

from .models import (
    ConversationReceipt,
    DeterministicFakeRenderer,
    ExpressionPlan,
    ExternalEffectCounters,
    InboundConversationEvent,
    InteractionPlan,
)


class IsolatedConversationKernel:
    """A replayable G3 loop with no model, host, or delivery adapter dependency."""

    def __init__(
        self,
        *,
        identities: IdentityDirectory,
        sources: SourceRepository,
        inbox: InboxRepository,
        operations: OperationRepository,
        renderer: DeterministicFakeRenderer,
        external_effects: ExternalEffectCounters,
    ) -> None:
        self._identities = identities
        self._sources = sources
        self._inbox = inbox
        self._operations = operations
        self._renderer = renderer
        self._external_effects = external_effects

    def process(
        self,
        event: InboundConversationEvent,
        *,
        cancelled: bool = False,
    ) -> Outcome[ConversationReceipt]:
        if cancelled:
            return Outcome.failed("cancelled", "event was cancelled before local processing")

        inbox = self._inbox.accept(
            consumer="conversation.g3",
            event_id=event.scoped_key,
            payload_hash=event.input_hash,
            observed_at=event.received_at,
        )
        if not inbox.is_success:
            return Outcome(failure=inbox.failure)

        resolved = self._identities.resolve_authenticated(
            event.principal,
            observed_at=event.received_at,
        )
        if not resolved.is_success:
            return Outcome(failure=resolved.failure)

        source = self._sources.read(
            event.source,
            resolved=resolved.unwrap(),
            capability=event.capability,
            observed_at=event.received_at,
            authorizer=self._identities,
        )
        if not source.is_success:
            return Outcome(failure=source.failure)

        interaction = InteractionPlan(
            event_id=event.event_id,
            intent="acknowledge_available_source",
            source=source.unwrap().reference,
        )
        operation = _operation_for(event)
        part = PartRef(
            part_id=_part_id(event.event_id),
            operation=operation,
            sequence=1,
        )
        expression = self._renderer.render(
            ExpressionPlan(operation=operation, part=part, interaction=interaction)
        )
        receipt = self._operations.reserve(
            operation,
            parameter_hash=event.input_hash,
            observed_at=event.received_at,
            outbox_part_id=part.part_id,
            outbox_payload_hash=expression.payload_hash,
        )
        if not receipt.is_success:
            return Outcome(failure=receipt.failure)
        return Outcome.success(
            ConversationReceipt(
                event=event,
                operation_receipt=receipt.unwrap(),
                expression=expression,
                inbox_replayed=inbox.unwrap().replayed,
            )
        )

    @property
    def external_effects(self) -> ExternalEffectCounters:
        return self._external_effects


def _operation_for(event: InboundConversationEvent) -> OperationRef:
    digest = hashlib.sha256(
        "\x1f".join(
            (
                event.event_id,
                event.scope.installation_id,
                event.scope.platform,
                event.scope.kind.value,
                event.scope.native_scope_id,
            ) + ((event.scope.key,) if event.scope.is_resolved else ())
        ).encode("utf-8")
    ).hexdigest()
    return OperationRef(
        operation_id=f"conversation-operation-{digest[:24]}",
        owner="conversation",
        scope=event.scope,
        version=VersionRef(lineage_id=f"conversation-event-{digest[:24]}", revision=1),
        idempotency_key=f"inbound-event-{event.event_id}",
    )


def _part_id(event_id: str) -> str:
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    return f"conversation-part-{digest[:24]}"
