"""Internal audio/video parents preserve the claim boundaries of returned nodes."""

from dataclasses import dataclass

from companion_v2.conversation.media.audio.events import AudioConversationEvent
from companion_v2.conversation.media.video.events import VideoConversationEvent


@dataclass(frozen=True)
class ForwardAudioEvent(AudioConversationEvent):
    node_path: tuple = ()
    displayed_sender: str | None = None
    displayed_name: str = ""
    original_forwarder: str | None = None
    quoted_message_id: str | None = None

    @property
    def audio_attribution(self):
        result = {"sender": "unknown", "captured_by": self.principal.native_account_id,
                  "sender_claim": self.displayed_sender, "displayed_name": self.displayed_name,
                  "attribution": "forward_record_claim", "forwarded_by": self.original_forwarder,
                  "node_path": self.node_path, "original_author": "unknown", "original_audience": "unknown"}
        if self.quoted_message_id is not None:
            result.update(quoted_by=self.principal.native_account_id, original_message_id=self.quoted_message_id)
        return result


@dataclass(frozen=True)
class ForwardVideoEvent(VideoConversationEvent):
    node_path: tuple = ()
    displayed_sender: str | None = None
    displayed_name: str = ""
    original_forwarder: str | None = None
    quoted_message_id: str | None = None

    @property
    def video_attribution(self):
        result = {"sender": "unknown", "captured_by": self.principal.native_account_id,
                  "sender_claim": self.displayed_sender, "displayed_name": self.displayed_name,
                  "attribution": "forward_record_claim", "forwarded_by": self.original_forwarder,
                  "node_path": self.node_path, "original_author": "unknown", "original_audience": "unknown"}
        if self.quoted_message_id is not None:
            result.update(quoted_by=self.principal.native_account_id, original_message_id=self.quoted_message_id)
        return result
