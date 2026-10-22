"""Quoted forward manifests; ordinary quote documents retain their original shape."""

from dataclasses import dataclass

from companion_v2.conversation.forwards.models import CapturedForward, ForwardConversationEvent, ForwardDescriptor, fits_forwards
from companion_v2.conversation.media.codec import image_descriptor
from companion_v2.conversation.media.models import fits_budget
from companion_v2.execution.models import TaskError

from .models import (CapturedQuote, QuoteDescriptor, check_quote_media, event_images,
                     event_audios, event_videos)


INSTRUCTION = (
    "引用中的合并转发有三层归属：当前引用者、原消息的转发账号、节点显示的账号与昵称。原消息发送账号只证明谁转发过这份资料，不认证节点作者、原受众或本人经历；当前引用者没有因此成为原转发者，机器人账号转发过也不代表当前角色创作或亲历。引用原消息与转发节点的时间分别理解，不合并为本轮发生的事情；节点音视频继续保留节点归属，不推定原作者或拍摄/录音者。"
)


def check_forwards(quote, expected_type):
    forwards = quote.forwards
    if (not isinstance(forwards, tuple) or not forwards or any(type(f) is not expected_type for f in forwards)
            or tuple(f.position for f in forwards) != tuple(sorted({f.position for f in forwards}))):
        raise TaskError("quote_manifest_invalid", "quoted forwards require their immutable ordered manifests")
    positions = ([getattr(i, "descriptor", i).position for i in quote.images]
                 + [getattr(i, "descriptor", i).position for i in getattr(quote, "audios", ())]
                 + [getattr(i, "descriptor", i).position for i in getattr(quote, "videos", ())]
                 + [f.position for f in forwards])
    from companion_v2.conversation.media.audio.models import fits_audio_budget
    from companion_v2.conversation.media.video.models import fits_video_budget
    images = tuple(getattr(i, "descriptor", i) for i in event_images(quote))
    audios = tuple(getattr(i, "descriptor", i) for i in event_audios(quote))
    videos = tuple(getattr(i, "descriptor", i) for i in event_videos(quote))
    if (len(set(positions)) != len(positions) or not fits_forwards(forwards)
            or not fits_budget(images) or not fits_audio_budget(audios, images)
            or not fits_video_budget(videos, images, audios)):
        raise TaskError("quote_limit", "quoted media and forward nodes share one input budget")


@dataclass(frozen=True)
class CapturedForwardQuote(CapturedQuote):
    forwards: tuple[CapturedForward, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        check_forwards(self, CapturedForward)


@dataclass(frozen=True)
class CapturedQuoteMedia(CapturedQuote):
    audios: tuple = ()
    videos: tuple = ()

    def __post_init__(self):
        super().__post_init__()
        from companion_v2.conversation.media.audio.models import CapturedAudio
        from companion_v2.conversation.media.video.models import CapturedVideo
        if (not isinstance(self.audios, tuple) or any(type(item) is not CapturedAudio for item in self.audios)
                or not isinstance(self.videos, tuple) or any(type(item) is not CapturedVideo for item in self.videos)):
            raise TaskError("quote_manifest_invalid", "quoted audio and video need immutable original captures")
        check_quote_media(self.position, tuple(i.descriptor for i in self.images),
                          tuple(i.descriptor for i in self.audios), tuple(i.descriptor for i in self.videos))


@dataclass(frozen=True)
class CapturedForwardQuoteMedia(CapturedForwardQuote):
    audios: tuple = ()
    videos: tuple = ()

    def __post_init__(self):
        super().__post_init__()
        from companion_v2.conversation.media.audio.models import CapturedAudio
        from companion_v2.conversation.media.video.models import CapturedVideo
        if (not isinstance(self.audios, tuple) or any(type(item) is not CapturedAudio for item in self.audios)
                or not isinstance(self.videos, tuple) or any(type(item) is not CapturedVideo for item in self.videos)):
            raise TaskError("quote_manifest_invalid", "quoted audio and video need immutable original captures")
        check_quote_media(self.position, tuple(i.descriptor for i in self.images),
                          tuple(i.descriptor for i in self.audios), tuple(i.descriptor for i in self.videos))


@dataclass(frozen=True)
class ForwardQuoteDescriptor(QuoteDescriptor):
    forwards: tuple[ForwardDescriptor, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        check_forwards(self, ForwardDescriptor)

    @classmethod
    def restore(cls, data):
        kind = ForwardQuoteMediaDescriptor if "audios" in data or "videos" in data else cls
        values = {**data, "images": tuple(image_descriptor(i) for i in data["images"]),
                  "forwards": tuple(ForwardDescriptor.restore(f) for f in data["forwards"])}
        if kind is ForwardQuoteMediaDescriptor:
            values.update(audios=tuple(_audio_descriptor(i) for i in data.get("audios", ())),
                          videos=tuple(_video_descriptor(i) for i in data.get("videos", ())))
        return kind(**values)


def _audio_descriptor(data):
    from companion_v2.conversation.media.audio.models import AudioDescriptor
    return AudioDescriptor(**data)


def _video_descriptor(data):
    from companion_v2.conversation.media.video.models import VideoDescriptor
    return VideoDescriptor.restore(data)


@dataclass(frozen=True)
class QuoteMediaDescriptor(QuoteDescriptor):
    audios: tuple = ()
    videos: tuple = ()

    def __post_init__(self):
        super().__post_init__()
        check_quote_media(self.position, self.images, self.audios, self.videos)

    @classmethod
    def restore(cls, data):
        return cls(**{**data, "images": tuple(image_descriptor(i) for i in data["images"]),
                      "audios": tuple(_audio_descriptor(i) for i in data.get("audios", ())),
                      "videos": tuple(_video_descriptor(i) for i in data.get("videos", ()))})


@dataclass(frozen=True)
class ForwardQuoteMediaDescriptor(ForwardQuoteDescriptor):
    audios: tuple = ()
    videos: tuple = ()

    def __post_init__(self):
        super().__post_init__()
        check_quote_media(self.position, self.images, self.audios, self.videos)


@dataclass(frozen=True)
class QuotedForwardEvent(ForwardConversationEvent):
    """Internal parent view retaining the current actor, never a second input."""

    original_sender: str = ""
    original_message_id: str = ""

    @property
    def forward_attribution(self):
        return {"forwarded_by": self.original_sender, "quoted_by": self.principal.native_account_id,
                "original_message_id": self.original_message_id}
