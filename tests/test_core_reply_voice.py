"""The AstrBot-owned reply path still executes V2's configured voice policy."""

from types import SimpleNamespace as NS
import unittest

from astrbot.core.message.components import Plain, Record
from astrbot.core.message.message_event_result import MessageChain

from astrbot_host.core_reply import (
    activate_core_reply_delivery_guard,
    inject_core_reply_prompt,
    prepare_core_reply_event,
)
from astrbot_host.core_reply_voice import prepare_core_reply_voice_message, voice_prompt_instruction
from companion_v2.conversation.voice_reply import VoiceReplyPolicy
from companion_v2.foundation.outcome import Outcome


class FakeEvent:
    def __init__(self):
        self.extra = {}
        self.sent = []
        self.send = self._send
        self.send_streaming = None

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value

    async def _send(self, message, *args, **kwargs):
        self.sent.append(message)
        return True


class CoreReplyVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_send_authorizes_before_and_after_tts_then_sends_record(self):
        event = FakeEvent()
        context = object()
        prepared = {"context": context, "event_id": "event-1", "event_ref": "ref-1",
                    "voice_reply_policy": VoiceReplyPolicy(position="after_text")}
        order = []

        async def authorize(_):
            order.append("authorize")
            return Outcome.success(True)

        async def renderer(actual_context, text, *, provider_id, timeout_seconds):
            self.assertIs(actual_context, context)
            self.assertEqual((text, provider_id, timeout_seconds), ("你好", "", 30))
            order.append("render")
            return {"type": "record", "data": {"file": "base64://YQ=="}}

        async def prepare(current, message, check, segment_index, segment_count):
            return await prepare_core_reply_voice_message(
                event, current, message, renderer=renderer, delivery=None, authorize=check,
                segment_index=segment_index, segment_count=segment_count)

        prepare_core_reply_event(event, prepared, authorize=authorize, prepare_send=prepare)
        activate_core_reply_delivery_guard(event)
        await event.send(MessageChain(chain=[Plain("你好")]))

        self.assertEqual(order, ["authorize", "render", "authorize"])
        self.assertEqual(len(event.sent), 1)
        self.assertEqual([type(part) for part in event.sent[0].chain], [Plain, Record])
        self.assertEqual(event.sent[0].chain[1]._companion_v2_spoken_text, "你好")

    async def test_model_tags_speak_only_tagged_text_and_voice_only_keeps_translation(self):
        event = FakeEvent()
        policy = VoiceReplyPolicy(generation_mode="model_tag", language="en",
                                  foreign_text_mode="translation", delivery_mode="voice_only")
        prepared = {"context": object(), "event_id": "event-2", "voice_reply_policy": policy}
        rendered = []

        async def renderer(_, text, **__):
            rendered.append(text)
            return {"type": "record", "data": {"file": "base64://YQ=="}}

        output = await prepare_core_reply_voice_message(
            event, prepared, MessageChain(chain=[Plain("<pc_tts>Hello there.</pc_tts>你好。")]),
            renderer=renderer, delivery=None, authorize=_allow)

        self.assertEqual(rendered, ["Hello there."])
        self.assertEqual([type(part) for part in output.chain], [Plain, Record])
        self.assertEqual(output.chain[0].text, "你好。")

    async def test_failed_tts_keeps_clean_text_and_releases_cooldown_claim(self):
        event = FakeEvent()
        policy = VoiceReplyPolicy(cooldown_seconds=60)
        prepared = {"context": object(), "event_id": "event-3", "voice_reply_policy": policy}
        delivery = FakeDelivery()

        async def renderer(*_, **__):
            return None

        output = await prepare_core_reply_voice_message(
            event, prepared, MessageChain(chain=[Plain("<pc_tts>你好</pc_tts>")]),
            renderer=renderer, delivery=delivery, authorize=_allow)

        self.assertEqual([type(part) for part in output.chain], [Plain])
        self.assertEqual(output.chain[0].text, "你好")
        self.assertEqual(delivery.released, [("claim-1", "core:event")])

    async def test_active_policy_injects_rules_and_disables_streaming(self):
        event = FakeEvent()
        policy = VoiceReplyPolicy(generation_mode="model_tag", trigger_mode="adaptive")
        prepared = {"prompt_instruction": "Use the captured persona.\n\n" + voice_prompt_instruction(policy),
                    "voice_reply_policy": policy}
        prepare_core_reply_event(event, prepared, authorize=_allow)
        request = NS(system_prompt="base", prompt="hello")

        inject_core_reply_prompt(event, request)

        self.assertFalse(event.get_extra("enable_streaming"))
        self.assertIn("<pc_tts>", request.system_prompt)
        self.assertIn("Use the captured persona.", request.system_prompt)


class FakeDelivery:
    def __init__(self):
        self.released = []

    def claim_core_route(self, *_):
        return {"part_id": "core:event", "cooldown_key": "claim-1"}

    def release(self, claim, part_id):
        self.released.append((claim["cooldown_key"], part_id))


async def _allow(*_):
    return Outcome.success(True)
