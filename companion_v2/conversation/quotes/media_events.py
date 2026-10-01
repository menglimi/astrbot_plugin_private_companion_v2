"""Internal media parents retain the verified sender claim of a quoted message."""

from dataclasses import dataclass

from companion_v2.conversation.media.audio.events import AudioConversationEvent
from companion_v2.conversation.media.video.events import VideoConversationEvent


@dataclass(frozen=True)
class QuotedAudioEvent(AudioConversationEvent):
    original_sender: str = ""
    original_message_id: str = ""

    @property
    def audio_attribution(self):
        return {"sender": self.original_sender, "attribution": "sending_account_only",
                "quoted_by": self.principal.native_account_id, "original_message_id": self.original_message_id,
                "original_author": "unknown"}


@dataclass(frozen=True)
class QuotedVideoEvent(VideoConversationEvent):
    original_sender: str = ""
    original_message_id: str = ""

    @property
    def video_attribution(self):
        return {"sender": self.original_sender, "attribution": "sending_account_only",
                "quoted_by": self.principal.native_account_id, "original_message_id": self.original_message_id,
                "original_author": "unknown"}
