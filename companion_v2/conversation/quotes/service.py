"""Publish quoted text separately; reuse image originals and source dependencies."""

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.dependencies import link
from companion_v2.sources.models import SourceRecord
from companion_v2.conversation.forwards.service import prepare_forward

from .models import CapturedQuote, QuoteDescriptor, QuoteImageEvent, OWNER
from .forward_models import (ForwardQuoteDescriptor, ForwardQuoteMediaDescriptor, QuoteMediaDescriptor,
                             QuotedForwardEvent)
from .originals import original_sources


def quote_reference(parent, position):
    identifier = "input-quote-" + digest([parent, position])
    return SourceRef(identifier, OWNER, parent.scope, VersionRef(identifier, 1), parent.issued_at, parent.expires_at)


def prepare_quote(sources, parent, audience, captured):
    if not isinstance(captured, CapturedQuote):
        raise TaskError("quote_manifest_invalid", "quote needs a trusted immutable capture")
    images = tuple(i.descriptor for i in captured.images)
    forwards = tuple(prepare_forward(sources, quote_reference(parent, captured.position), audience, f)[0]
                     for f in getattr(captured, "forwards", ()))
    audios = tuple(i.descriptor for i in getattr(captured, "audios", ()))
    videos = tuple(i.descriptor for i in getattr(captured, "videos", ()))
    original_hash = digest([captured.position, captured.message_id, captured.sender_id, captured.sent_at, captured.text, images])
    if forwards:
        original_hash = digest([original_hash, forwards])
    if audios or videos:
        original_hash = digest([original_hash, audios, videos])
    record = sources.prepare_message(SourceRecord(quote_reference(parent, captured.position), audience, original_hash, captured.text))
    kind = (ForwardQuoteMediaDescriptor if forwards and (audios or videos) else ForwardQuoteDescriptor if forwards
            else QuoteMediaDescriptor if audios or videos else QuoteDescriptor)
    values = (captured.position, captured.message_id, captured.sender_id, captured.sent_at,
              record.content_hash, digest(record.payload), images)
    extra = {"forwards": forwards} if forwards else {}
    if audios or videos:
        extra.update(audios=audios, videos=videos)
    descriptor = kind(*values, **extra)
    return descriptor, record


class ConversationQuotes:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime

    @staticmethod
    def image_event(event, quote):
        return QuoteImageEvent(event.event_id, event.principal, event.scope, quote_reference(event.source, quote.position),
            event.capability, quote.content_hash, event.received_at, event.runtime_scope,
            quote.images, quote.sender_id, quote.message_id)

    @staticmethod
    def forward_event(event, quote):
        return QuotedForwardEvent(event.event_id, event.principal, event.scope, quote_reference(event.source, quote.position),
            event.capability, quote.content_hash, event.received_at, event.runtime_scope,
            forwards=quote.forwards, original_sender=quote.sender_id, original_message_id=quote.message_id)

    @staticmethod
    def audio_event(event, quote):
        from .media_events import QuotedAudioEvent
        return QuotedAudioEvent(event.event_id, event.principal, event.scope,
            quote_reference(event.source, quote.position), event.capability, quote.content_hash,
            event.received_at, event.runtime_scope, audios=quote.audios,
            original_sender=quote.sender_id, original_message_id=quote.message_id)

    @staticmethod
    def video_event(event, quote):
        from .media_events import QuotedVideoEvent
        return QuotedVideoEvent(event.event_id, event.principal, event.scope,
            quote_reference(event.source, quote.position), event.capability, quote.content_hash,
            event.received_at, event.runtime_scope, videos=quote.videos,
            original_sender=quote.sender_id, original_message_id=quote.message_id)

    @staticmethod
    def metadata(event, quote, text):
        return encode({"text": text, "original_message_id": quote.message_id, "sender": quote.sender_id,
            "sent_at_unix": quote.sent_at, "quoted_by": event.principal.native_account_id,
            "quoting_source_id": event.source.source_id, "position": quote.position,
            "attribution": "sending_account_only", "original_author": "unknown"})

    def _parent(self, context, event, at):
        self.messages.authorize(context, at)
        parent = self.messages._read_source(event.source, context, event.capability, at)
        if event.principal != context.actor.principal or parent.content_hash != event.input_hash:
            raise TaskError("quote_owner_mismatch", "quote must belong to the admitted current input")

    def publish(self, context, event, captured):
        if not isinstance(captured, tuple) or len(captured) != len(event.quotes):
            raise TaskError("quote_manifest_invalid", "quote capture does not match its durable manifest")
        with self.runtime.transaction():
            at = self.messages.tasks.now()
            self._parent(context, event, at)
            for item, expected in zip(captured, event.quotes):
                self.messages.recalls.check(event.scope, item.message_id, item.sender_id)
                descriptor, record = prepare_quote(self.messages.sources, event.source, context.audience, item)
                if descriptor != expected:
                    raise TaskError("quote_content_changed", "quote capture cannot replace the admitted manifest")
                dependencies = original_sources(self.messages, context, event, descriptor, record.payload, at, publish=True)
                require(self.messages.sources.publish(record, observed_at=event.received_at))
                link(self.runtime, record.reference, (event.source, *dependencies), at)
                if item.images:
                    self.messages.images.publish(context, self.image_event(event, descriptor), item.images)
                if getattr(item, "forwards", ()):
                    self.messages.forwards.publish(context, self.forward_event(event, descriptor), item.forwards)
                if getattr(item, "audios", ()):
                    self.messages.audio.publish(context, self.audio_event(event, descriptor), item.audios)
                if getattr(item, "videos", ()):
                    self.messages.videos.publish(context, self.video_event(event, descriptor), item.videos)

    def read(self, context, event, at):
        contributions, images, positions, audios, videos = self.read_all(context, event, at)
        return contributions, images, positions

    def read_all(self, context, event, at):
        contributions, images, positions, audios, videos = [], [], {}, [], []
        with self.runtime.read_snapshot():
            self._parent(context, event, at)
            for quote in event.quotes:
                self.messages.recalls.check(event.scope, quote.message_id, quote.sender_id)
                reference = quote_reference(event.source, quote.position)
                positions[reference] = (quote.position,)
                record = self.messages._read_source(reference, context, event.capability, at)
                if record.content_hash != quote.content_hash or digest(record.payload) != quote.text_hash:
                    raise TaskError("quote_content_changed", "quoted body differs from the original manifest")
                original_sources(self.messages, context, event, quote, record.payload, at, publish=False)
                contributions.append(ContextContribution(reference.source_id, OWNER, "quoted_message:" + event.source.source_id,
                    ContributionState.READY, self.metadata(event, quote, record.payload), reference, True))
                if quote.images:
                    parent = self.image_event(event, quote)
                    originals = self.messages.images.read(context, (parent,), at)
                    for image in originals:
                        contributions.extend(self.messages.images.contributions(parent, image, purpose="quoted_image:"))
                    images.extend(originals)
                if getattr(quote, "forwards", ()):
                    materials, originals, node_positions, quoted_audios, quoted_videos = self.messages.forwards.read_all(
                        context, self.forward_event(event, quote), at)
                    contributions.extend(materials)
                    images.extend(originals)
                    audios.extend(quoted_audios)
                    videos.extend(quoted_videos)
                    positions.update({source: (quote.position, *path) for source, path in node_positions.items()})
                if getattr(quote, "audios", ()):
                    parent = self.audio_event(event, quote)
                    originals = self.messages.audio.read(context, (parent,), at)
                    for audio in originals:
                        contributions.append(self.messages.audio.contribution(parent, audio, purpose="quoted_audio"))
                    audios.extend(originals)
                if getattr(quote, "videos", ()):
                    parent = self.video_event(event, quote)
                    originals = self.messages.videos.read(context, (parent,), at)
                    for video in originals:
                        contributions.extend(self.messages.videos.contributions(parent, video, purpose="quoted_video"))
                    videos.extend(originals)
        return tuple(contributions), tuple(images), positions, tuple(audios), tuple(videos)
