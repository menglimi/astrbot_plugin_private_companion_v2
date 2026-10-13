"""Real private SDK events and reverse-WebSocket ACKs on synthetic local sockets."""

import asyncio
import base64
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests.multi_host_support import MultiFixture, multi_config
from aiocqhttp import Event
from aiocqhttp.api_impl import ResultStore, WebSocketReverseApi
from astrbot.core.message.components import Forward, Image, Plain, Reply
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot_host.forwards import load_native_forwards
from astrbot_host.media import load_native_image
from astrbot_host.quotes import load_native_quote
from companion_v2.conversation.media.reply import OWNER
from companion_v2.execution.models import TaskContext
from tests.forward_support import outer_raw
from tests.image_delivery_support import attach_originals
from tests.image_delivery_support import image_reply
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_conversation_images import image_bytes
from tests.test_conversation_quotes import quote_raw
from companion_v2.conversation.segmentation import LLM_SEGMENT_MARKER


class ImageSocket:
    def __init__(self, message_id):
        self.message_id, self.frames, self.status = message_id, [], "ok"

    async def send(self, payload):
        frame = json.loads(payload)
        self.frames.append(frame)
        if self.status == "timeout":
            return
        if frame["action"] == "get_friend_msg_history":
            identifier = frame["params"]["message_seq"]
            data = {"messages": [outer_raw() if identifier == "678" else quote_raw()]}
        else:
            data = {"message_id": self.message_id}
            self.message_id += 1
        asyncio.get_running_loop().call_soon(ResultStore.add,
            {"echo": frame["echo"], "status": self.status,
             "retcode": 0 if self.status == "ok" else 100, "data": data})


class NativeImageDeliveryTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.types = replace(self.types, event=AiocqhttpMessageEvent, reverse_api=WebSocketReverseApi,
            image=Image, image_loader=load_native_image, reply=Reply, quote_loader=load_native_quote,
            forward=Forward, forward_loader=load_native_forwards)
        self.sockets = {}
        for name, platform in self.native.platforms.items():
            clients = {"100": ImageSocket(456), "101": ImageSocket(789)}
            platform.client._wsr_api_clients = clients
            platform.client._api._wsr_api = WebSocketReverseApi(clients, set(), 1)
            self.sockets[name] = clients
        self.native.provider.client.state.behavior = attach_originals
        self.config = multi_config(delivery_mode="onebot_private")
        self.controller = self.make_controller(self.config)

    def event_for(self, target="first", identifier="451", *, components=None):
        configured = self.controller.settings.target(target)
        platform = self.native.platforms[configured.platform_id]
        message = AstrBotMessage()
        message.type, message.self_id = MessageType.FRIEND_MESSAGE, configured.account_id
        message.group_id, message.session_id = "", configured.participant_id
        message.sender = MessageMember(configured.participant_id, "测试好友")
        message.message_id, message.message_str = identifier, "请附上这张原图"
        message.message = components or [Plain(message.message_str), Image.fromBytes(image_bytes())]
        message.raw_message = Event(post_type="message", message_type="private", sub_type="friend",
            self_id=int(configured.account_id), user_id=int(configured.participant_id),
            sender={"user_id": int(configured.participant_id)}, message_id=int(identifier))
        event = self.types.event(message.message_str, message, platform.meta(), configured.participant_id, platform.client)
        event.created_at = self.clock.now().timestamp()
        return event

    async def reply(self, target="first", identifier="451", *, components=None, advance_part_clock=False):
        batch = (await self.controller.receive_claimed(self.event_for(target, identifier, components=components))).unwrap()
        if advance_part_clock:
            async def advance_spacing():
                flow = self.controller.session.application.flow
                while flow.row(batch)["state"] not in ("complete", "blocked", "closed"):
                    await asyncio.sleep(0.05)
                    row = flow.row(batch)
                    if row["reason"] == "part_spacing":
                        self.clock.advance(timedelta(seconds=0.05))
            await asyncio.wait_for(advance_spacing(), timeout=20)
            return self.controller.preview(target, batch).unwrap()
        await wait_for_batch(self.controller.session, batch)
        return self.controller.preview(target, batch).unwrap()

    def sends(self, target="first"):
        configured = self.controller.settings.target(target)
        return [f for f in self.sockets[configured.platform_id][configured.account_id].frames if f["action"] == "send_private_msg"]

    async def test_native_images_use_exact_account_and_one_combined_wire_ack(self):
        app = await self.start_host()
        for target in ("first", "second"):
            (await self.controller.authorize_delivery(target)).unwrap()
            report = await self.reply(target)
            configured = self.controller.settings.target(target)
            frame = self.sends(target)[0]
            self.assertEqual(frame["params"], {"self_id": configured.account_id, "user_id": 200,
                "message": [{"type": "text", "data": {"text": "把这张原图附在这里。"}},
                    {"type": "image", "data": {"file": "base64://" + base64.b64encode(image_bytes()).decode("ascii")}}]})
            self.assertIsInstance(frame["echo"]["seq"], int)
            self.assertTrue(report["sent"])
            self.assertEqual(len(report["parts"][0]["images"]), 1)
            context = TaskContext.restore(json.loads(app.messages.batch(report["batch_id"])["context_json"]))
            self.assertEqual(len(app.messages.history(context).unwrap()["items"]), 1)
            other = "second" if target == "first" else "first"
            self.assertEqual(self.controller.preview(other, report["batch_id"]).failure.code, "host_target_mismatch")
        self.assertEqual(self.sockets["qq-main"]["101"].frames, [])
        self.assertEqual(self.sockets["qq-second"]["100"].frames, [])
        self.assertEqual(ResultStore._futures, {})

    async def test_native_image_only_reply_omits_the_text_component(self):
        async def sticker_only(payload, _):
            wire = " ".join(str(message.get("content", "")) for message in payload["messages"])
            self.assertIn("图片本身足以回应", wire)
            return image_reply(payload, text="")

        self.native.provider.client.state.behavior = sticker_only
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        report = await self.reply(identifier="450")

        self.assertTrue(report["sent"], report)
        self.assertEqual(report["parts"][0]["text"], "")
        self.assertEqual(len(report["parts"][0]["images"]), 1)
        self.assertEqual([item["type"] for item in self.sends()[0]["params"]["message"]], ["image"])

    async def test_voice_follows_each_segment_and_last_image_on_each_target(self):
        self.config = multi_config(delivery_mode="onebot_private")
        self.config["voice_reply"] = {"enabled": True}
        self.config["segmentation"] = {"enabled": True, "llm_controlled": True}
        self.controller = self.make_controller(self.config)
        audio_root = self.root / "native-temp"
        audio_root.mkdir()
        audio_file = audio_root / "reply.wav"
        audio_file.write_bytes(b"RIFFsynthetic-audio")
        selected, spoken = [], []

        def select(umo):
            selected.append(umo)

            async def synthesize(text):
                spoken.append((umo, text))
                return str(audio_file)

            return NS(get_audio=synthesize)

        async def segmented(payload, _):
            return image_reply(payload, text="先看看这张图。\n" + LLM_SEGMENT_MARKER + "\n再补一句。")

        self.native.get_using_tts_provider = select
        self.native.provider.client.state.behavior = segmented
        with patch("astrbot_host.voice.get_astrbot_temp_path", return_value=str(audio_root)):
            await self.start_host()
            for target, identifier in (("first", "851"), ("second", "852")):
                (await self.controller.authorize_delivery(target)).unwrap()
                report = await self.reply(target, identifier=identifier, advance_part_clock=True)
                self.assertTrue(report["sent"])
                self.assertEqual([part["state"] for part in report["parts"]], ["delivered", "delivered"])
                messages = [frame["params"]["message"] for frame in self.sends(target)]
                self.assertEqual([[segment["type"] for segment in message] for message in messages],
                    [["text", "record"], ["text", "image", "record"]])
                self.assertEqual([message[0]["data"]["text"] for message in messages],
                    ["先看看这张图。", "再补一句。"])
                self.assertEqual([message[-1]["data"]["file"] for message in messages],
                    ["base64://" + base64.b64encode(audio_file.read_bytes()).decode("ascii")] * 2)
        self.assertEqual(selected, ["qq-main:FriendMessage:200"] * 2 + ["qq-second:FriendMessage:200"] * 2)
        self.assertEqual([text for _, text in spoken], ["先看看这张图。", "再补一句。"] * 2)
        self.assertEqual(ResultStore._futures, {})

    async def test_model_tag_translation_seals_each_voice_plan_and_delivers_ordered_components(self):
        self.config = multi_config(delivery_mode="onebot_private")
        self.config["segmentation"] = {"enabled": True, "llm_controlled": True}
        self.config["voice_reply"] = {"enabled": True, "generation_mode": "model_tag", "language": "en",
            "foreign_text_mode": "translation", "en_provider_id": "english-tts",
            "position": "before_text", "cooldown_seconds": 90}
        self.controller = self.make_controller(self.config)
        audio_root = self.root / "tagged-voice-temp"
        audio_root.mkdir()
        audio_file = audio_root / "reply.wav"
        audio_file.write_bytes(b"RIFFsynthetic-audio")
        spoken = []

        async def synthesize(text):
            spoken.append(text)
            return str(audio_file)

        tts = NS(get_audio=synthesize)
        model_lookup = self.native.get_provider_by_id
        self.native.get_provider_by_id = lambda identifier: tts if identifier == "english-tts" else model_lookup(identifier)
        self.native.get_all_tts_providers = lambda: [tts]

        async def tagged(payload, _):
            instruction = " ".join(str(message.get("content", "")) for message in payload["messages"])
            self.assertIn("<pc_tts>", instruction)
            text = ("<pc_tts>Hello there.</pc_tts>你好。\n" + LLM_SEGMENT_MARKER +
                    "\n<pc_tts>See you.</pc_tts>再见。")
            return image_reply(payload, text=text)

        self.native.provider.client.state.behavior = tagged
        with patch("astrbot_host.voice.get_astrbot_temp_path", return_value=str(audio_root)):
            app = await self.start_host()
            (await self.controller.authorize_delivery("first")).unwrap()
            report = await self.reply(identifier="855", advance_part_clock=True)

        self.assertTrue(report["sent"], report)
        self.assertEqual([part["state"] for part in report["parts"]], ["delivered", "delivered"])
        self.assertEqual([part["text"] for part in report["parts"]], ["你好。", "再见。"])
        plans = app.runtime.read_all("""SELECT p.sequence, v.speech, v.provider_id, v.position
            FROM conversation_parts p JOIN conversation_voice_parts v ON v.part_id = p.part_id
            WHERE p.batch_id = ? ORDER BY p.sequence""", (report["batch_id"],))
        self.assertEqual([(row["sequence"], row["speech"], row["provider_id"], row["position"])
                          for row in plans], [(1, "Hello there.", "english-tts", "before_text"),
                                             (2, "See you.", "english-tts", "before_text")])
        messages = [frame["params"]["message"] for frame in self.sends()]
        self.assertEqual([[part["type"] for part in message] for message in messages],
                         [["record", "text"], ["record", "text", "image"]])
        self.assertEqual([message[1]["data"]["text"] for message in messages], ["你好。", "再见。"])
        self.assertEqual(spoken, ["Hello there.", "See you."])
        self.assertEqual(ResultStore._futures, {})

    async def test_tts_failure_keeps_original_text_and_image(self):
        self.config = multi_config(delivery_mode="onebot_private")
        self.config["voice_reply"] = {"enabled": True}
        self.controller = self.make_controller(self.config)

        async def failed(_):
            raise RuntimeError("synthetic TTS failure")

        self.native.get_using_tts_provider = lambda _: NS(get_audio=failed)
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        report = await self.reply(identifier="853")
        self.assertTrue(report["sent"])
        self.assertEqual([segment["type"] for segment in self.sends()[0]["params"]["message"]],
            ["text", "image"])

    async def test_unknown_first_voice_segment_does_not_send_following_image(self):
        self.config = multi_config(delivery_mode="onebot_private")
        self.config["voice_reply"] = {"enabled": True}
        self.config["segmentation"] = {"enabled": True, "llm_controlled": True}
        self.controller = self.make_controller(self.config)
        audio_root = self.root / "unknown-voice-temp"
        audio_root.mkdir()
        audio_file = audio_root / "reply.wav"
        audio_file.write_bytes(b"RIFFsynthetic-audio")
        spoken = []

        async def synthesize(text):
            spoken.append(text)
            return str(audio_file)

        async def segmented(payload, _):
            return image_reply(payload, text="第一段。\n" + LLM_SEGMENT_MARKER + "\n第二段。")

        self.native.get_using_tts_provider = lambda _: NS(get_audio=synthesize)
        self.native.provider.client.state.behavior = segmented
        self.sockets["qq-main"]["100"].status = "timeout"
        with patch("astrbot_host.voice.get_astrbot_temp_path", return_value=str(audio_root)):
            await self.start_host()
            (await self.controller.authorize_delivery("first")).unwrap()
            report = await self.reply(identifier="854")
        self.assertFalse(report["sent"])
        self.assertEqual([part["state"] for part in report["parts"]], ["unknown", "pending"])
        self.assertEqual([[segment["type"] for segment in frame["params"]["message"]]
                          for frame in self.sends()], [["text", "record"]])
        self.assertEqual(spoken, ["第一段。"])

    async def test_native_forward_and_reply_images_reuse_pinned_history_then_send(self):
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        report = await self.reply(identifier="678", components=[Forward(id="forward-resource"), Reply(id="345")])
        self.assertTrue(report["sent"])
        frames = self.sockets["qq-main"]["100"].frames
        reads = [f for f in frames if f["action"] == "get_friend_msg_history"]
        self.assertEqual({f["params"]["message_seq"] for f in reads}, {"678", "345"})
        self.assertTrue(all(f["params"]["self_id"] == "100" and f["params"]["user_id"] == "200" for f in reads))
        self.assertEqual([p["type"] for p in self.sends()[0]["params"]["message"]], ["text", "image", "image"])
        self.assertEqual(len(report["parts"][0]["images"]), 2)
        self.assertEqual(ResultStore._futures, {})

    async def test_missing_and_failed_ack_remain_unknown_after_restart_without_retry(self):
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        reports = []
        for index, status in enumerate(("failed", "timeout")):
            self.sockets["qq-main"]["100"].status = status
            report = await self.reply(identifier=str(900 + index))
            reports.append(report)
            self.assertFalse(report["sent"])
            self.assertEqual(report["parts"][0]["state"], "unknown")
        self.assertEqual(ResultStore._futures, {})
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
        self.sockets["qq-main"]["100"].status = "ok"
        for index, previous in enumerate(reports):
            report = await self.reply(identifier=str(900 + index))
            self.assertEqual(report["batch_id"], previous["batch_id"])
            self.assertEqual(report["parts"][0]["images"], previous["parts"][0]["images"])
        self.assertEqual(len(self.sends()), 2)
        app = self.controller.session.application
        self.assertEqual(app.runtime.read_one("SELECT COUNT(*) n FROM conversation_sent_history", ())["n"], 0)

    async def test_configured_private_targets_send_images_on_their_exact_accounts(self):
        await self.start_host()
        first = await self.reply("first", identifier="901")
        second = await self.reply("second", identifier="902")
        self.assertTrue(first["sent"])
        self.assertTrue(second["sent"])
        self.assertEqual(len(self.sends("first")), 1)
        self.assertEqual(len(self.sends("second")), 1)
        self.assertEqual(self.sends("first")[0]["params"]["self_id"], "100")
        self.assertEqual(self.sends("second")[0]["params"]["self_id"], "101")
        self.clock.advance(timedelta(minutes=16))
        after_legacy_grant_ttl = await self.reply(identifier="903")
        self.assertTrue(after_legacy_grant_ttl["sent"])
        self.assertEqual(len(self.sends("first")), 2)

    async def test_role_switch_while_preparing_images_cannot_send_as_another_persona(self):
        app = await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        switched = False
        async def change(_):
            nonlocal switched
            if not switched and app.runtime.read_one("SELECT 1 FROM sources WHERE owner = ?", (OWNER,)):
                switched = True
                self.native.selections["qq-main"] = "second"
        self.native.before_resolve = change
        report = await self.reply()
        self.assertTrue(switched)
        self.assertFalse(report["sent"])
        self.assertEqual(self.sends(), [])

    async def test_legacy_delivery_revocation_does_not_disable_configured_private_target(self):
        app = await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        revoked = False
        async def change(_):
            nonlocal revoked
            if not revoked and app.runtime.read_one("SELECT 1 FROM sources WHERE owner = ?", (OWNER,)):
                revoked = True
                (await self.controller.revoke_delivery("first")).unwrap()
        self.native.before_resolve = change
        report = await self.reply()
        self.assertTrue(revoked)
        self.assertTrue(report["sent"])
        self.assertEqual(len(self.sends("first")), 1)
        self.assertEqual(self.sends("second"), [])

    async def test_disconnected_original_account_never_uses_another_socket_for_images(self):
        app = await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        disconnected = False
        async def change(_):
            nonlocal disconnected
            if not disconnected and app.runtime.read_one("SELECT 1 FROM sources WHERE owner = ?", (OWNER,)):
                disconnected = True
                self.native.platforms["qq-main"].client._wsr_api_clients.pop("100")
        self.native.before_resolve = change
        report = await self.reply()
        self.assertTrue(disconnected)
        self.assertFalse(report["sent"])
        self.assertTrue(all(not socket.frames for clients in self.sockets.values() for socket in clients.values()))

    async def test_private_delivery_retains_image_receipt_metadata_across_restart(self):
        self.config = multi_config()
        self.controller = self.make_controller(self.config)
        await self.start_host()
        reports = [await self.reply(target) for target in ("first", "second")]
        await self.controller.terminate()
        self.controller = self.make_controller(self.config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
        for target, prior in zip(("first", "second"), reports):
            current = self.controller.preview(target, prior["batch_id"]).unwrap()
            self.assertEqual(current, prior)
            self.assertEqual(len(current["parts"][0]["images"]), 1)
            self.assertTrue(current["sent"])
            self.assertNotIn("base64", str(current))
            self.assertEqual(len(self.sends(target)), 1)
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
