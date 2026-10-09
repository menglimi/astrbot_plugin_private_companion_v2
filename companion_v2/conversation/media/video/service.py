"""Atomic video originals and sampled frame publication; authorized rereads only."""

import hashlib

from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import AssetRef, SourceRef, VersionRef
from companion_v2.sources.dependencies import key, link
from companion_v2.sources.models import AssetRecord, SourceRecord
from companion_v2.sources.repositories import AssetRepository
from .events import VideoFrameEvent
from .models import CapturedVideo, PromptVideo, OWNER, fits_video_budget


class ConversationVideos:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime
        self.assets = AssetRepository(self.runtime)

    @staticmethod
    def references(event, descriptor):
        identifier = "input-video-" + digest([event.source, descriptor.position])
        version = VersionRef(identifier, 1)
        return (SourceRef(identifier, OWNER, event.scope, version, event.source.issued_at, event.source.expires_at),
                AssetRef(identifier, OWNER, event.scope, version, descriptor.content_hash))

    @staticmethod
    def metadata(event, descriptor):
        payload = {"video": descriptor, "parent_source_id": event.source.source_id,
            "sender": event.principal.native_account_id, "attribution": "sender_only",
            "original_author": "unknown", "capture_time": "unknown", "coverage": descriptor.coverage,
            "audio_status": "not_inspected", "duration_basis": "container_media_timeline",
            "sampling": "uniform_decoded_frame_indices", "original_integrity": "container_bounds_and_decodable_frames"}
        payload.update(getattr(event, "video_attribution", {}))
        return encode(payload)

    def frame_event(self, event, descriptor):
        reference, _ = self.references(event, descriptor)
        return VideoFrameEvent(event.event_id, event.principal, event.scope, reference, event.capability,
            digest(self.metadata(event, descriptor)), event.received_at, event.runtime_scope,
            tuple(f.image for f in descriptor.frames), descriptor)

    def contributions(self, event, video, *, purpose="input_video"):
        from companion_v2.conversation.foreground import ContextContribution, ContributionState
        result = [ContextContribution(video.source.source_id, OWNER,
            purpose + ":" + video.parent.source_id + ":" + str(video.descriptor.position), ContributionState.READY,
            self.metadata(event, video.descriptor), video.source, True)]
        parent = self.frame_event(event, video.descriptor)
        for frame in video.frames:
            result.extend(self.messages.images.contributions(parent, frame, purpose="video_frame:"))
        return tuple(result)

    def _parent(self, context, event, at):
        self.messages.authorize(context, at)
        parent = self.messages._read_source(event.source, context, event.capability, at)
        if event.principal != context.actor.principal or parent.content_hash != event.input_hash:
            raise TaskError("video_owner_mismatch", "video must retain its admitted original sender and source")

    def publish(self, context, event, videos):
        if (not isinstance(videos, tuple) or not videos or any(type(v) is not CapturedVideo for v in videos)
                or tuple(v.descriptor for v in videos) != getattr(event, "videos", ())):
            raise TaskError("video_manifest_invalid", "publish only the original host-captured video manifest")
        with self.runtime.transaction() as connection:
            self._parent(context, event, self.messages.tasks.now())
            for video in videos:
                reference, asset = self.references(event, video.descriptor)
                payload = self.metadata(event, video.descriptor)
                require(self.messages.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload),
                                                      observed_at=event.received_at))
                link(self.runtime, reference, (event.source,), event.received_at)
                require(self.assets.publish(AssetRecord(asset, context.audience), observed_at=event.received_at))
                values = (*key(event.source), video.descriptor.position, *key(reference),
                    asset.asset_id, asset.version.lineage_id, asset.version.revision, encode(video.descriptor), video.content)
                old = connection.execute("""SELECT * FROM conversation_video_payloads
                    WHERE parent_id = ? AND parent_lineage = ? AND parent_revision = ? AND position = ?""", values[:4]).fetchone()
                if old is not None and tuple(old) != values:
                    raise TaskError("video_version_conflict", "the original video attachment cannot be replaced")
                connection.execute("INSERT OR IGNORE INTO conversation_video_payloads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
                self.messages.images.publish(context, self.frame_event(event, video.descriptor), video.frames)

    def read(self, context, events, at):
        manifest = [(e, d) for e in events for d in getattr(e, "videos", ())]
        if not fits_video_budget(tuple(d for _, d in manifest)):
            raise TaskError("video_turn_limit", "this turn exceeds the declared video budget")
        result = []
        with self.runtime.read_snapshot():
            for event, descriptor in manifest:
                self._parent(context, event, at)
                reference, asset = self.references(event, descriptor)
                record = self.messages._read_source(reference, context, event.capability, at)
                payload = self.metadata(event, descriptor)
                if record.payload != payload or record.content_hash != digest(payload):
                    raise TaskError("video_content_changed", "video metadata differs from its original manifest")
                asset_record = require(self.assets.read(asset, resolved=context.actor, capability=event.capability,
                                                       observed_at=at, authorizer=self.messages.tasks.identity))
                if not set(context.audience.recipients).issubset(asset_record.audience.recipients):
                    raise TaskError("video_audience_denied", "video is unavailable to the original audience")
                row = self.runtime.read_one("""SELECT * FROM conversation_video_payloads
                    WHERE parent_id = ? AND parent_lineage = ? AND parent_revision = ? AND position = ?""",
                    (*key(event.source), descriptor.position))
                if row is None:
                    raise TaskError("video_original_unavailable", "original video bytes are unavailable")
                expected = (*key(event.source), descriptor.position, *key(reference),
                    asset.asset_id, asset.version.lineage_id, asset.version.revision, encode(descriptor))
                if (tuple(row)[:11] != expected or type(row["content"]) is not bytes
                        or len(row["content"]) != descriptor.byte_count
                        or hashlib.sha256(row["content"]).hexdigest() != descriptor.content_hash):
                    raise TaskError("video_content_changed", "video body differs from the captured original")
                frames = self.messages.images.read(context, (self.frame_event(event, descriptor),), at)
                result.append(PromptVideo(reference, event.source, descriptor, frames, row["content"]))
        return tuple(result)
