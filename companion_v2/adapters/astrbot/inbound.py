"""Normalize a trusted AstrBot event into a V2 governed source and input envelope.

This G4 module intentionally uses a narrow protocol instead of importing AstrBot. A later
host assembly supplies the protocol implementation after it has authenticated event fields.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Protocol

from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.conversation.media.models import CapturedImage, ImageConversationEvent
from companion_v2.conversation.quotes.models import QuoteConversationEvent
from companion_v2.conversation.quotes.service import prepare_quote
from companion_v2.conversation.forwards.models import ForwardConversationEvent, MAX_FORWARDS
from companion_v2.conversation.forwards.service import prepare_forward
from companion_v2.conversation.media.audio.models import CapturedAudio
from companion_v2.conversation.media.audio.events import AudioConversationEvent
from companion_v2.conversation.media.video.models import CapturedVideo
from companion_v2.conversation.media.video.events import VideoConversationEvent
from companion_v2.execution.models import digest
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import AudienceRef, ReferenceValidationError, ScopeKind, ScopeRef, SourceRef, VersionRef
from companion_v2.identity_policy.personas import ConversationRoute, PersonaDirectory, RuntimeIdentity
from companion_v2.identity_policy.ports import IdentityAuthorizationPort, TrustedHostIdentityPort
from companion_v2.sources.models import SourceRecord
from companion_v2.sources.repositories import SourceRepository


class AstrBotEventPort(Protocol):
    """Supplies only host-verified event routing and immutable content fields."""

    def event_id(self, host_event: object) -> str:
        """Return the native event identity supplied by the host."""

    def scope(self, host_event: object) -> ScopeRef:
        """Return a trusted normalized conversation scope."""

    def audience(self, host_event: object) -> AudienceRef:
        """Return the host-derived recipients for the normalized scope."""

    def payload(self, host_event: object) -> str:
        """Return raw event content as source material, never as identity evidence."""

    def payload_hash(self, host_event: object) -> str:
        """Return the host-derived stable content hash for idempotency and diagnostics."""

    def received_at(self, host_event: object) -> datetime:
        """Return the host-received timestamp."""

    def conversation_route(self, host_event: object) -> ConversationRoute:
        """Return host-derived participants without display-name or content inference."""


class AstrBotInboundAdapter:
    """Create V2 input records after trusted identity and route checks succeed."""

    def __init__(
        self,
        *,
        event_port: AstrBotEventPort,
        identity_port: TrustedHostIdentityPort,
        identities: IdentityAuthorizationPort,
        personas: PersonaDirectory,
        runtime_identity: RuntimeIdentity,
        sources: SourceRepository,
    ) -> None:
        self._event_port = event_port
        self._identity_port = identity_port
        self._identities = identities
        self._personas = personas
        self._runtime_identity = runtime_identity
        self._sources = sources

    def ingest(self, host_event: object, *, capability: str) -> Outcome[InboundConversationEvent]:
        principal = self._identity_port.authenticated_principal(host_event)
        if not principal.is_success:
            return Outcome(failure=principal.failure)
        scope = self._event_port.scope(host_event)
        if not scope.is_resolved:
            return Outcome.failed("scope_unresolved", "host must resolve bot, login account, conversation and session")
        authenticated = principal.unwrap()
        if (authenticated.bot_id != scope.bot_id or authenticated.account_id != scope.account_id
                or authenticated.platform != scope.platform):
            return Outcome.failed("host_account_scope_mismatch", "authenticated sender belongs to a different bot/account route")
        if authenticated.host_id != self._runtime_identity.host_id:
            return Outcome.failed("host_runtime_mismatch", "authenticated event belongs to another host instance")
        audience = self._event_port.audience(host_event)
        received_at = self._event_port.received_at(host_event)
        event_id = self._event_port.event_id(host_event)
        payload_hash = self._event_port.payload_hash(host_event)
        resolved = self._identities.resolve_authenticated(
            principal.unwrap(),
            observed_at=received_at,
        )
        if not resolved.is_success:
            return Outcome(failure=resolved.failure)
        if audience.scope != scope:
            return Outcome.failed("host_audience_scope_mismatch", "host audience does not match event scope")
        if resolved.unwrap().subject not in audience.recipients:
            return Outcome.failed(
                "host_audience_sender_missing",
                "authenticated sender is absent from host-derived audience",
            )
        if principal.unwrap().installation_id != scope.installation_id:
            return Outcome.failed(
                "host_scope_installation_mismatch",
                "trusted host identity and scope use different installations",
            )
        route_provider = getattr(self._event_port, "conversation_route", None)
        if route_provider is None:
            return Outcome.failed("host_conversation_route_invalid", "host did not provide one consistent trusted route")
        try:
            route = route_provider(host_event)
            if route.scope != scope:
                return Outcome.failed("host_conversation_route_mismatch", "host route does not match the normalized scope")
            if route.scene_kind is ScopeKind.PRIVATE and route.user != resolved.unwrap().subject:
                return Outcome.failed("host_private_participant_mismatch", "private route participant is not the authenticated sender")
            self._personas.register_route(route, observed_at=received_at)
        except ReferenceValidationError:
            return Outcome.failed("host_conversation_route_invalid", "host did not provide one consistent trusted route")
        persona = self._personas.resolve(scope, observed_at=received_at)
        if persona.failure is not None:
            return Outcome(failure=persona.failure)
        runtime_scope = self._runtime_identity.bind(route, persona.unwrap().binding)
        source = _source_for_host_event(event_id=event_id, scope=scope, received_at=received_at)
        quote_port = getattr(self._event_port, "quotes", None)
        captured_quotes = quote_port(host_event) if quote_port is not None else ()
        if not isinstance(captured_quotes, tuple) or len(captured_quotes) > 1:
            return Outcome.failed("quote_manifest_invalid", "one immutable quote is supported per input")
        quotes = tuple(prepare_quote(self._sources, source, audience, item)[0] for item in captured_quotes)
        if quotes:
            # Include the redacted/keyed quote fingerprints, never raw quote bodies,
            # in the input identity. Existing non-quote replay hashes stay unchanged.
            payload_hash = digest([payload_hash, quotes])
        forward_port = getattr(self._event_port, "forwards", None)
        captured_forwards = forward_port(host_event) if forward_port is not None else ()
        if not isinstance(captured_forwards, tuple) or len(captured_forwards) > MAX_FORWARDS:
            return Outcome.failed("forward_manifest_invalid", "input requires an immutable forward capture")
        forwards = tuple(prepare_forward(self._sources, source, audience, item)[0] for item in captured_forwards)
        if forwards:
            payload_hash = digest([payload_hash, forwards])
        prepared = self._sources.prepare_message(
            SourceRecord(
                reference=source,
                audience=audience,
                content_hash=payload_hash,
                payload=self._event_port.payload(host_event),
            )
        )
        published = self._sources.publish(prepared, observed_at=received_at)
        image_port = getattr(self._event_port, "images", None)
        images = image_port(host_event) if image_port is not None else ()
        if not isinstance(images, tuple) or any(not isinstance(image, CapturedImage) for image in images):
            return Outcome.failed("host_image_invalid", "images require an immutable host-captured manifest")
        audio_port = getattr(self._event_port, "audios", None)
        audios = audio_port(host_event) if audio_port is not None else ()
        if not isinstance(audios, tuple) or any(type(audio) is not CapturedAudio for audio in audios):
            return Outcome.failed("host_audio_invalid", "audio requires immutable host-captured originals")
        video_port = getattr(self._event_port, "videos", None)
        videos = video_port(host_event) if video_port is not None else ()
        if not isinstance(videos, tuple) or any(type(video) is not CapturedVideo for video in videos):
            return Outcome.failed("host_video_invalid", "video requires immutable host-captured originals")
        event_type = VideoConversationEvent if videos else AudioConversationEvent if audios else ForwardConversationEvent if forwards else QuoteConversationEvent if quotes else ImageConversationEvent if images else InboundConversationEvent
        event = event_type(
            event_id=event_id,
            principal=principal.unwrap(),
            scope=scope,
            source=source,
            capability=capability,
            input_hash=prepared.content_hash,
            received_at=received_at,
            runtime_scope=runtime_scope,
            **({"images": tuple(image.descriptor for image in images)} if images else {}),
            **({"quotes": quotes} if quotes else {}),
            **({"forwards": forwards} if forwards else {}),
            **({"audios": tuple(a.descriptor for a in audios)} if audios else {}),
            **({"videos": tuple(v.descriptor for v in videos)} if videos else {}),
        )
        if not published.is_success and published.failure.code != "source_version_conflict":
            return Outcome(failure=published.failure)
        # A native event may be replayed after its author withdrew it. Let the
        # durable message owner resolve the existing tombstone/conflict; never
        # replace the original governed source version.
        return Outcome.success(event)


def _source_for_host_event(*, event_id: str, scope: ScopeRef, received_at: datetime) -> SourceRef:
    digest = hashlib.sha256(
        "\x1f".join(
            (
                event_id,
                scope.installation_id,
                scope.platform,
                scope.kind.value,
                scope.native_scope_id,
                scope.key,
            )
        ).encode("utf-8")
    ).hexdigest()
    return SourceRef(
        source_id=f"host-event-{digest[:24]}",
        owner="conversation.host_input",
        scope=scope,
        version=VersionRef(lineage_id=f"host-event-{digest[:24]}", revision=1),
        issued_at=received_at,
    )
