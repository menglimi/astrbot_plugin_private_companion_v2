"""Additive event shape; existing text, image, quote and forward hashes stay stable."""

from dataclasses import dataclass, fields

from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.conversation.media.models import ImageConversationEvent, ImageDescriptor
from companion_v2.conversation.quotes.models import QuoteConversationEvent, QuoteDescriptor, event_images, event_audios, event_videos
from companion_v2.conversation.forwards.models import ForwardConversationEvent, ForwardDescriptor
from companion_v2.execution.models import TaskError
from .models import AudioDescriptor, check_audio_manifest, fits_audio_budget


@dataclass(frozen=True)
class AudioConversationEvent(InboundConversationEvent):
    images: tuple[ImageDescriptor, ...] = ()
    quotes: tuple[QuoteDescriptor, ...] = ()
    forwards: tuple[ForwardDescriptor, ...] = ()
    audios: tuple[AudioDescriptor, ...] = ()

    @property
    def forward_attribution(self):
        return {"forwarded_by": self.principal.native_account_id}

    def __post_init__(self):
        super().__post_init__()
        # Reuse each established attachment contract without modifying its old
        # serialized shape or relaxing the requirement for its own attachment.
        values = {f.name: getattr(self, f.name) for f in fields(InboundConversationEvent)}
        if self.forwards:
            ForwardConversationEvent(**values, images=self.images, quotes=self.quotes, forwards=self.forwards)
        elif self.quotes:
            QuoteConversationEvent(**values, images=self.images, quotes=self.quotes)
        elif self.images:
            ImageConversationEvent(**values, images=self.images)
        if any(not isinstance(value, tuple) for value in (self.images, self.quotes, self.forwards)):
            raise TaskError("audio_manifest_invalid", "attachments must retain their immutable manifests")
        check_audio_manifest(self.audios)
        positions = [i.position for i in (*self.images, *self.quotes, *self.forwards, *self.audios)]
        from companion_v2.conversation.media.video.models import fits_video_budget
        images, audios, videos = event_images(self), event_audios(self), event_videos(self)
        if (len(set(positions)) != len(positions) or not fits_audio_budget(audios, images)
                or not fits_video_budget(videos, images, audios)):
            raise TaskError("audio_turn_limit", "audio and visual attachments share one intake budget")
