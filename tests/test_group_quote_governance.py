"""Original group media authority is rechecked even when a quote holds a copy."""

import json
import unittest

from companion_v2.conversation.quotes.service import quote_reference
from companion_v2.execution.models import TaskError
from tests.audio_support import audio_bytes
from tests.forward_support import node_raw
from tests.group_quote_media_support import GroupQuoteMediaFixture, Forward, Plain, Reply, FakeRecord, FakeVideo
from tests.video_support import video_bytes


class GroupQuoteGovernanceTests(GroupQuoteMediaFixture, unittest.IsolatedAsyncioTestCase):
    async def test_original_media_revocation_blocks_quotes_and_saved_history_after_restart(self):
        await self.start_host()
        sequence = 2000
        for nested in (False, True):
            for mode in ("waveform", "video", "frame", "audio_source"):
                with self.subTest(nested=nested, mode=mode):
                    sequence += 1
                    identifier = str(sequence)
                    parts = [Forward(id="group-quoted-forward")] if nested else [FakeRecord(), FakeVideo()]
                    a, first = await self.original(identifier, parts=parts,
                        nodes=[node_raw(audios=(audio_bytes(),), videos=(video_bytes(),))])
                    b, quoted = await self.quoted(identifier)
                    c, later = await self.receive_parts([Plain("下一条消息")], sender="202")
                    original = self.input(a, first)
                    audio_parent = video_parent = original
                    audio_descriptor, video_descriptor = None, None
                    if nested:
                        forward, node = original.forwards[0], original.forwards[0].nodes[0]
                        audio_parent = self.app.messages.forwards.audio_event(original, forward, node)
                        video_parent = self.app.messages.forwards.video_event(original, forward, node)
                        audio_descriptor, video_descriptor = node.audios[0], node.videos[0]
                    else:
                        audio_descriptor, video_descriptor = original.audios[0], original.videos[0]
                    audio_source, _, waveform = self.app.messages.audio.references(audio_parent, audio_descriptor)
                    video_source, video_asset = self.app.messages.videos.references(video_parent, video_descriptor)
                    frame_parent = self.app.messages.videos.frame_event(video_parent, video_descriptor)
                    frame_source, frame_asset = self.app.messages.images.references(frame_parent, frame_parent.images[0])
                    quoted_event = self.input(b, quoted)
                    root = quote_reference(quoted_event.source, quoted_event.quotes[0].position)
                    dependencies = {row[0] for row in self.app.runtime.read_all(
                        "SELECT input_id FROM source_dependencies WHERE dependent_id = ?", (root.source_id,))}
                    self.assertTrue({original.source.source_id, audio_source.source_id, video_source.source_id,
                                     frame_source.source_id}.issubset(dependencies))
                    owner, reference = {
                        "waveform": (self.app.messages.audio.assets, waveform),
                        "video": (self.app.messages.videos.assets, video_asset),
                        "frame": (self.app.messages.images.assets, frame_asset),
                        "audio_source": (self.app.messages.sources, audio_source),
                    }[mode]
                    owner.revoke(reference, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
                    await self.restart()
                    for context, batch in ((b, quoted), (c, later)):
                        with self.assertRaises(TaskError):
                            self.request(context, batch)
                    result = await self.controller.receive_claimed(self.media_event([Reply(id=identifier)]))
                    self.assertFalse(result.is_success)

    async def test_corrupt_original_waveform_cannot_be_hidden_by_an_intact_quote_copy(self):
        await self.start_host()
        a, first = await self.original(parts=[FakeRecord()])
        b, quoted = await self.quoted()
        original = self.input(a, first)
        with self.app.runtime.transaction() as connection:
            connection.execute("UPDATE conversation_audio_payloads SET waveform = ? WHERE parent_id = ?",
                               (b"changed", original.source.source_id))
        await self.restart()
        with self.assertRaises(TaskError):
            self.request(b, quoted)

    async def test_unknown_original_keeps_quote_authority_and_cascades_its_withdrawal(self):
        await self.start_host()
        self.store(parts=[FakeRecord(), FakeVideo()])
        b, quoted = await self.quoted()
        request = self.request(b, quoted)
        a, later = await self.receive_parts([Plain("讨论引用")], sender="202")
        history = [json.loads(m.payload) for m in self.request(a, later).context.materials if m.purpose == "group_conversation_history"]
        self.assertEqual((history[0]["speaker_id"], history[0]["quotations"][0]["sender"]), ("200", "201"))
        self.app.withdraw(b, self.input(b, quoted).scoped_key).unwrap()
        await self.restart()
        self.assertEqual(self.app.messages.sources.validate_reference(request.audios[0].source,
            observed_at=self.clock.now()).failure.code, "source_revoked")
        with self.assertRaises(TaskError):
            self.request(a, later)
