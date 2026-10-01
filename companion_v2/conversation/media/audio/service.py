"""Atomic voice intake and authorized original rereads at every use boundary."""

import base64

from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import AssetRef, SourceRef, VersionRef
from companion_v2.sources.dependencies import key, link
from companion_v2.sources.models import AssetRecord, SourceRecord
from companion_v2.sources.repositories import AssetRepository
from .models import CapturedAudio, OWNER, PromptAudio, fits_audio_budget


def asset_key(asset):
    return asset.asset_id, asset.version.lineage_id, asset.version.revision


class ConversationAudio:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime
        self.assets = AssetRepository(self.runtime)

    @staticmethod
    def references(event, descriptor):
        identifier = "input-audio-" + digest([event.source, descriptor.position])
        version = VersionRef(identifier, 1)
        return (SourceRef(identifier, OWNER, event.scope, version, event.source.issued_at, event.source.expires_at),
                AssetRef(identifier, OWNER, event.scope, version, descriptor.content_hash),
                AssetRef(identifier + "-wave", OWNER, event.scope, VersionRef(identifier + "-wave", 1), descriptor.wave_hash))

    @staticmethod
    def metadata(event, descriptor):
        payload = {"audio": descriptor, "parent_source_id": event.source.source_id,
            "sender": event.principal.native_account_id, "attribution": "sender_only",
            "original_author": "unknown", "speaker_identity": "unknown", "recording_time": "unknown",
            "coverage": "complete_attachment", "duration_ms": descriptor.duration_ms,
            "listening_view": "pcm_s16le_mono_wav", "normalization": "pcm-mono-v1", "transcript": "not_provided"}
        payload.update(getattr(event, "audio_attribution", {}))
        return encode(payload)

    def contribution(self, event, audio, *, purpose="input_audio"):
        from companion_v2.conversation.foreground import ContextContribution, ContributionState
        return ContextContribution(audio.source.source_id, OWNER,
            purpose + ":" + audio.parent.source_id + ":" + str(audio.descriptor.position), ContributionState.READY,
            self.metadata(event, audio.descriptor), audio.source, True)

    def _parent(self, context, event, at):
        self.messages.authorize(context, at)
        parent = self.messages._read_source(event.source, context, event.capability, at)
        if event.principal != context.actor.principal or parent.content_hash != event.input_hash:
            raise TaskError("audio_owner_mismatch", "audio must retain its admitted sender and original input")

    def publish(self, context, event, audios):
        if (not isinstance(audios, tuple) or not audios or any(type(a) is not CapturedAudio for a in audios)
                or tuple(a.descriptor for a in audios) != getattr(event, "audios", ())):
            raise TaskError("audio_manifest_invalid", "publish only the original host-captured audio manifest")
        with self.runtime.transaction() as connection:
            self._parent(context, event, self.messages.tasks.now())
            for audio in audios:
                reference, original, waveform = self.references(event, audio.descriptor)
                payload = self.metadata(event, audio.descriptor)
                require(self.messages.sources.publish(SourceRecord(reference, context.audience, digest(payload), payload),
                                                      observed_at=event.received_at))
                link(self.runtime, reference, (event.source,), event.received_at)
                for asset in (original, waveform):
                    require(self.assets.publish(AssetRecord(asset, context.audience), observed_at=event.received_at))
                values = (*key(event.source), audio.descriptor.position, *key(reference), *asset_key(original),
                          *asset_key(waveform), encode(audio.descriptor), audio.content, audio.waveform)
                old = connection.execute("""SELECT * FROM conversation_audio_payloads
                    WHERE parent_id = ? AND parent_lineage = ? AND parent_revision = ? AND position = ?""", values[:4]).fetchone()
                if old is not None and tuple(old) != values:
                    raise TaskError("audio_version_conflict", "the original voice attachment cannot be replaced")
                connection.execute("INSERT OR IGNORE INTO conversation_audio_payloads VALUES (" + ",".join("?" * 16) + ")", values)

    def read(self, context, events, at):
        manifest = [(e, d) for e in events for d in getattr(e, "audios", ())]
        if not fits_audio_budget(tuple(d for _, d in manifest)):
            raise TaskError("audio_turn_limit", "this turn exceeds its declared voice budget")
        result = []
        with self.runtime.read_snapshot():
            for event, descriptor in manifest:
                self._parent(context, event, at)
                reference, original, waveform = self.references(event, descriptor)
                record = self.messages._read_source(reference, context, event.capability, at)
                payload = self.metadata(event, descriptor)
                if record.payload != payload or record.content_hash != digest(payload):
                    raise TaskError("audio_content_changed", "audio metadata differs from the original manifest")
                for asset in (original, waveform):
                    record = require(self.assets.read(asset, resolved=context.actor, capability=event.capability,
                                                      observed_at=at, authorizer=self.messages.tasks.identity))
                    if not set(context.audience.recipients).issubset(record.audience.recipients):
                        raise TaskError("audio_audience_denied", "audio is unavailable to the original audience")
                row = self.runtime.read_one("""SELECT * FROM conversation_audio_payloads
                    WHERE parent_id = ? AND parent_lineage = ? AND parent_revision = ? AND position = ?""",
                    (*key(event.source), descriptor.position))
                if row is None:
                    raise TaskError("audio_original_unavailable", "original voice bytes are unavailable")
                expected = (*key(event.source), descriptor.position, *key(reference), *asset_key(original),
                            *asset_key(waveform), encode(descriptor))
                if tuple(row)[:14] != expected:
                    raise TaskError("audio_content_changed", "audio body is bound to another original")
                captured = CapturedAudio(descriptor, row["content"], row["waveform"])
                result.append(PromptAudio(reference, event.source, descriptor, base64.b64encode(captured.waveform).decode("ascii")))
        return tuple(result)
