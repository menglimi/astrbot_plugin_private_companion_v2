"""Video input and internal frame parents; existing input documents remain unchanged."""

from dataclasses import dataclass, fields

from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.conversation.media.models import ImageConversationEvent, ImageDescriptor
from companion_v2.conversation.media.audio.events import AudioConversationEvent
from companion_v2.conversation.media.audio.models import AudioDescriptor
from companion_v2.conversation.quotes.models import QuoteConversationEvent, QuoteDescriptor, event_images, event_audios, event_videos
from companion_v2.conversation.forwards.models import ForwardConversationEvent, ForwardDescriptor
from companion_v2.execution.models import TaskError
from .models import VideoDescriptor, check_video_manifest, fits_video_budget


@dataclass(frozen=True)
class VideoConversationEvent(InboundConversationEvent):
    images: tuple[ImageDescriptor, ...] = ()
    quotes: tuple[QuoteDescriptor, ...] = ()
    forwards: tuple[ForwardDescriptor, ...] = ()
    audios: tuple[AudioDescriptor, ...] = ()
    videos: tuple[VideoDescriptor, ...] = ()

    @property
    def forward_attribution(self):
        return {"forwarded_by": self.principal.native_account_id}

    def __post_init__(self):
        super().__post_init__()
        values = {f.name: getattr(self, f.name) for f in fields(InboundConversationEvent)}
        if self.audios:
            AudioConversationEvent(**values, images=self.images, quotes=self.quotes, forwards=self.forwards, audios=self.audios)
        elif self.forwards:
            ForwardConversationEvent(**values, images=self.images, quotes=self.quotes, forwards=self.forwards)
        elif self.quotes:
            QuoteConversationEvent(**values, images=self.images, quotes=self.quotes)
        elif self.images:
            ImageConversationEvent(**values, images=self.images)
        if any(not isinstance(v, tuple) for v in (self.images, self.quotes, self.forwards, self.audios)):
            raise TaskError("video_manifest_invalid", "attachments require immutable manifests")
        positions = [i.position for i in (*self.images, *self.quotes, *self.forwards, *self.audios, *self.videos)]
        check_video_manifest(self.videos)
        images, audios, videos = event_images(self), event_audios(self), event_videos(self)
        if len(set(positions)) != len(positions) or not fits_video_budget(videos, images, audios):
            raise TaskError("video_turn_limit", "all original attachments share one input budget")


@dataclass(frozen=True)
class VideoFrameEvent(ImageConversationEvent):
    """An internal original parent for the image store, never another message."""

    video: VideoDescriptor | None = None

    def frame_metadata(self, descriptor):
        frame = self.video.frames[descriptor.position]
        if frame.image != descriptor:
            raise TaskError("video_content_changed", "frame no longer belongs to its original video")
        return {"coverage": "video_frame", "frame_index": frame.index, "start_ms": frame.start_ms,
                "frame_count": self.video.frame_count, "video_coverage": self.video.coverage,
                "timing": self.video.timing, "audio_status": "not_inspected", "renderer": self.video.renderer}
