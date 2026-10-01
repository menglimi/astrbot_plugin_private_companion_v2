"""Shared host with real SDK private events and local-only OneBot ACKs."""

import base64
from dataclasses import replace
import json
import unittest

from tests.multi_host_support import MultiFixture, multi_config
from aiocqhttp.api_impl import WebSocketReverseApi
from astrbot.core.message.components import Plain, Record
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot_host.audio.components import private_components
from astrbot_host.audio.loader import load_native_audio
from companion_v2.execution.models import TaskContext
from tests.audio_support import audio_bytes
from tests.staging_bootstrap_support import wait_for_batch
from tests import test_astrbot_image_delivery_native as image_native


class NativeAudioTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    event_for = image_native.NativeImageDeliveryTests.event_for

    def setUp(self):
        super().setUp()
        self.types = replace(self.types, event=AiocqhttpMessageEvent, reverse_api=WebSocketReverseApi,
            audio=Record, audio_loader=load_native_audio, component_reader=private_components)
        self.sockets = {}
        for name, platform in self.native.platforms.items():
            clients = {"100": image_native.ImageSocket(456), "101": image_native.ImageSocket(789)}
            platform.client._wsr_api_clients = clients
            platform.client._api._wsr_api = WebSocketReverseApi(clients, set(), 0.02)
            self.sockets[name] = clients
        self.controller = self.make_controller(multi_config(delivery_mode="onebot_private"))

    async def test_two_accounts_keep_original_voice_owners_and_one_confirmed_text_reply_each(self):
        app = await self.start_host()
        sources = []
        for target in ("first", "second"):
            (await self.controller.authorize_delivery(target)).unwrap()
            config = self.controller.settings.target(target)
            # Use the real post-STT SDK shape, retaining the same original OneBot event.
            event = self.event_for(target, "451", components=[Plain("自动转写不作原文")])
            event.message_obj.raw_message["message"] = [{"type": "record", "data": {
                "file": "base64://" + base64.b64encode(audio_bytes()).decode("ascii")}}]
            batch = (await self.controller.receive_claimed(event)).unwrap()
            await wait_for_batch(self.controller.session, batch)
            context = TaskContext.restore(json.loads(app.messages.batch(batch)["context_json"]))
            request = app.messages._request(app.messages.batch(batch), context, self.clock.now())
            sources.append(request.audios[0].source)
            self.assertEqual(request.audios[0].source.scope.account_id, config.account_id)
            self.assertNotIn("自动转写", request.context.materials[0].payload)
            self.assertTrue(self.controller.preview(target, batch).unwrap()["sent"])
            sends = self.sockets[config.platform_id][config.account_id].frames
            self.assertEqual(len(sends), 1)
            self.assertEqual(sends[0]["action"], "send_private_msg")
            self.assertEqual(sends[0]["params"]["self_id"], config.account_id)
            self.assertEqual(len(app.messages.history(context).unwrap()["items"]), 1)
        self.assertNotEqual(sources[0], sources[1])
        self.assertEqual(self.sockets["qq-main"]["101"].frames, [])
        self.assertEqual(self.sockets["qq-second"]["100"].frames, [])
