"""Direct voice coexists with quoted/forwarded image originals and provenance."""

import unittest

from astrbot_host.audio.loader import load_native_audio
from companion_v2.execution.models import TaskError
from tests.audio_support import FakeRecord
from tests.forward_support import ForwardFixture
from tests.test_conversation_quotes import FakeReply


class MixedAudioTests(ForwardFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.bridge.audio_type, self.bridge.audio_loader = FakeRecord, load_native_audio

    async def test_quote_forward_and_voice_keep_distinct_sources_after_restore(self):
        host = await self.quiet_host()
        event = self.forward_event()
        event.message_obj.message.extend((FakeReply(), FakeRecord()))
        batch = host.receive(await self.capture(event)).unwrap()
        request = self.request(host.application, batch)
        self.assertEqual(len(request.images), 2)
        self.assertEqual(len(request.audios), 1)
        self.assertEqual(request.audios[0].descriptor.position, 3)
        self.assertEqual(len({a.source for a in (*request.images, *request.audios)}), 3)
        self.assertIn(request.audios[0].source, request.context.evidence_sources)
        original = self.original(host.application, batch)
        self.assertEqual((len(original.quotes), len(original.forwards), len(original.audios)), (1, 1, 1))
        context = self.context(host.application, batch)
        host.application.withdraw(context, original.scoped_key).unwrap()
        with self.assertRaises(TaskError):
            self.request(host.application, batch)
