"""Core reply hooks preserve AstrBot generation and gate only event sending."""

from dataclasses import dataclass
import inspect
from types import SimpleNamespace
import unittest

from astrbot_host.core_reply import (
    activate_core_reply_delivery_guard,
    inject_core_reply_prompt,
    prepare_core_reply_event,
    restore_core_reply_event,
)
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome


CONTEXT_EXTRA_KEY = "_companion_v2_core_reply_context"


@dataclass
class PreparedContext:
    instruction: str
    context: object = None
    target_id: str = "target-1"
    channel: str = "private"
    prompt_instruction: str = ""
    stable_prompt_instruction: str = ""


class FakeEvent:
    def __init__(self):
        self.extra = {}
        self.sent = []
        self.streamed = []
        self.send = self._send
        self.send_streaming = self._send_streaming

    def set_extra(self, key, value):
        self.extra[key] = value

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    async def _send(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return "sent"

    async def _send_streaming(self, *args, **kwargs):
        self.streamed.append((args, kwargs))
        return "streamed"


class FakeRequest:
    def __init__(self):
        self.system_prompt = "base system prompt"
        self.prompt = "user prompt"


async def resolve(value):
    if inspect.isawaitable(value):
        return await value
    return value


class AstrBotCoreReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_stores_context_and_preserves_core_streaming(self):
        event = FakeEvent()
        prepared = PreparedContext("Speak naturally.", context={"text": "hello"})

        await resolve(prepare_core_reply_event(event, prepared, authorize=_allow))

        state = event.get_extra(CONTEXT_EXTRA_KEY)
        self.assertIs(state["prepared"], prepared)
        self.assertIs(state["prepared"].context, prepared.context)
        self.assertEqual(event.get_extra("enable_streaming"), None)

    async def test_send_authorization_precedes_and_allows_original_send_once(self):
        event = FakeEvent()
        order = []

        prepared = PreparedContext("Instruction.")

        async def authorize(actual):
            self.assertIs(actual, prepared)
            order.append("authorize")
            return Outcome.success(True)

        await resolve(prepare_core_reply_event(event, prepared, authorize=authorize))
        await event.send("plugin notice")
        activate_core_reply_delivery_guard(event)
        await event.send("reply")

        self.assertEqual(order, ["authorize"])
        self.assertEqual(event.sent, [(("plugin notice",), {}), (("reply",), {})])
        restore_core_reply_event(event)
        self.assertIs(event.send.__self__, event)
        self.assertIs(event.send.__func__, FakeEvent._send)

    async def test_denied_send_never_calls_original_and_notifies_denial(self):
        event = FakeEvent()
        denied = []

        prepared = PreparedContext("Instruction.")

        async def authorize(actual):
            self.assertIs(actual, prepared)
            return Outcome.failed("reply_denied", "delivery is not authorized")

        async def on_denied(*args, **kwargs):
            denied.append((args, kwargs))

        await resolve(prepare_core_reply_event(
            event,
            prepared,
            authorize=authorize,
            on_denied=on_denied,
        ))
        activate_core_reply_delivery_guard(event)
        with self.assertRaises(TaskError) as denied_error:
            await event.send("reply")

        self.assertEqual(event.sent, [])
        self.assertEqual(len(denied), 1)
        self.assertIs(denied[0][0][0], prepared)
        self.assertEqual(denied[0][0][1].code, "reply_denied")
        self.assertEqual(denied_error.exception.code, "reply_denied")

    async def test_unexpected_authorization_result_fails_closed(self):
        event = FakeEvent()

        await resolve(prepare_core_reply_event(
            event,
            PreparedContext("Instruction."),
            authorize=lambda _prepared: _none(),
        ))
        activate_core_reply_delivery_guard(event)
        with self.assertRaisesRegex(TypeError, "must return an Outcome"):
            await event.send("reply")

        self.assertEqual(event.sent, [])

    async def test_streaming_delivery_is_authorized_before_original(self):
        event = FakeEvent()
        order = []

        async def authorize(_prepared):
            order.append("authorize")
            return Outcome.success(True)

        await resolve(prepare_core_reply_event(event, PreparedContext("Instruction."), authorize=authorize))
        activate_core_reply_delivery_guard(event)
        result = await event.send_streaming("stream", use_fallback=True)

        self.assertEqual(order, ["authorize"])
        self.assertEqual(event.streamed, [(("stream",), {"use_fallback": True})])
        self.assertEqual(result, "streamed")

    async def test_denied_streaming_never_calls_original(self):
        event = FakeEvent()

        async def authorize(_prepared):
            return Outcome.failed("reply_denied", "delivery is not authorized")

        await resolve(prepare_core_reply_event(event, PreparedContext("Instruction."), authorize=authorize))
        activate_core_reply_delivery_guard(event)
        with self.assertRaises(TaskError) as denied_error:
            await event.send_streaming("stream")

        self.assertEqual(event.streamed, [])
        self.assertEqual(denied_error.exception.code, "reply_denied")

    async def test_core_stream_is_guarded_and_restored_without_decorating_hook(self):
        event = FakeEvent()
        event.get_result = lambda: SimpleNamespace(result_content_type=SimpleNamespace(name="STREAMING_RESULT"))
        authorizations = []

        async def authorize(prepared):
            authorizations.append(prepared)
            return Outcome.success(True)

        prepared = PreparedContext("Instruction.")
        prepare_core_reply_event(event, prepared, authorize=authorize)
        await event.send_streaming("stream")

        self.assertEqual(authorizations, [prepared])
        self.assertEqual(event.streamed, [(("stream",), {})])
        self.assertIs(event.send.__func__, FakeEvent._send)
        self.assertIs(event.send_streaming.__func__, FakeEvent._send_streaming)

    async def test_prompt_injection_requires_event_context_and_is_idempotent(self):
        request = FakeRequest()
        original = (request.system_prompt, request.prompt)

        await resolve(inject_core_reply_prompt(FakeEvent(), request))

        self.assertEqual((request.system_prompt, request.prompt), original)

        event = FakeEvent()
        instruction = "Use the companion's current private context."
        stable_instruction = "Keep the configured companion voice."
        await resolve(prepare_core_reply_event(
            event,
            PreparedContext("Captured native persona", context={"text": "private context"},
                            prompt_instruction=instruction, stable_prompt_instruction=stable_instruction),
            authorize=_allow,
        ))
        await resolve(inject_core_reply_prompt(event, request))
        injected = request.system_prompt + "\n" + request.prompt

        self.assertIn(stable_instruction, injected)
        self.assertNotIn(instruction, injected)
        self.assertNotIn("Captured native persona", injected)
        await resolve(inject_core_reply_prompt(event, request))
        self.assertEqual(request.system_prompt + "\n" + request.prompt, injected)
        self.assertEqual(injected.count(stable_instruction), 1)

    async def test_stable_prompt_instruction_is_supported_when_instruction_is_empty(self):
        event = FakeEvent()
        prepared = PreparedContext("", stable_prompt_instruction="Use this stable reply instruction.")
        request = FakeRequest()

        await resolve(prepare_core_reply_event(event, prepared, authorize=_allow))
        await resolve(inject_core_reply_prompt(event, request))

        self.assertIn("Use this stable reply instruction.", request.system_prompt + request.prompt)

    async def test_core_stream_observes_only_successful_native_parts_and_counts_each_once(self):
        event = FakeEvent()
        event.get_result = lambda: SimpleNamespace(result_content_type=SimpleNamespace(name="STREAMING_RESULT"))
        sent, stages = [], []

        async def fallback_stream(generator, **kwargs):
            async for part in generator:
                await event.send(part)

        event.send_streaming = fallback_stream
        prepare_core_reply_event(event, PreparedContext("Persona"), authorize=_allow,
                                 on_sent=lambda _, text: sent.append(text), on_delivery=stages.append)

        async def parts():
            yield "first paragraph"
            yield "second paragraph"

        await event.send_streaming(parts())
        state = event.get_extra(CONTEXT_EXTRA_KEY)
        self.assertEqual(sent, ["first paragraph", "second paragraph"])
        self.assertEqual((state["send_attempts"], state["send_returns"], state["send_unknown"]), (2, 2, 0))
        self.assertEqual(stages, ["stream_started", "started", "returned", "started", "returned", "finished"])
        self.assertIs(event.send.__func__, FakeEvent._send)

    async def test_core_stream_keeps_successful_part_when_later_native_send_is_unknown(self):
        event = FakeEvent()
        event.get_result = lambda: SimpleNamespace(result_content_type=SimpleNamespace(name="STREAMING_RESULT"))
        sent = []

        async def native_send(text):
            if text == "unconfirmed paragraph":
                raise TimeoutError

        async def fallback_stream(generator):
            async for part in generator:
                await event.send(part)

        event.send, event.send_streaming = native_send, fallback_stream
        prepare_core_reply_event(event, PreparedContext("Persona"), authorize=_allow,
                                 on_sent=lambda _, text: sent.append(text))

        async def parts():
            yield "sent paragraph"
            yield "unconfirmed paragraph"

        with self.assertRaises(TimeoutError):
            await event.send_streaming(parts())
        state = event.get_extra(CONTEXT_EXTRA_KEY)
        self.assertEqual(sent, ["sent paragraph"])
        self.assertEqual((state["send_attempts"], state["send_returns"], state["send_unknown"]), (2, 1, 1))

    async def test_empty_and_metadata_streams_do_not_claim_a_send_return(self):
        from astrbot.core.message.message_event_result import MessageChain

        cases = [[], [MessageChain()], [MessageChain().message("  ")],
                 [MessageChain(type="tool_result").message("internal result")]]
        for chunks in cases:
            with self.subTest(chunks=chunks):
                event = FakeEvent()
                event.get_result = lambda: SimpleNamespace(result_content_type=SimpleNamespace(name="STREAMING_RESULT"))
                sent, stages = [], []

                async def consume(generator):
                    async for _ in generator:
                        pass
                    # AstrBot's base method sets this even when nothing went out.
                    event._has_send_oper = True

                async def parts():
                    for chunk in chunks:
                        yield chunk

                event.send_streaming = consume
                prepare_core_reply_event(event, PreparedContext("Persona"), authorize=_allow,
                                         on_sent=lambda _, text: sent.append(text), on_delivery=stages.append)
                await event.send_streaming(parts())
                state = event.get_extra(CONTEXT_EXTRA_KEY)
                self.assertEqual((state["send_attempts"], state["send_returns"], state["send_unknown"]), (0, 0, 0))
                self.assertEqual(sent, [])
                self.assertEqual(stages, ["finished"])

    async def test_media_only_native_stream_records_a_send_return(self):
        from astrbot.core.message.components import Image
        from astrbot.core.message.message_event_result import MessageChain

        event = FakeEvent()
        stages = []

        async def consume(generator):
            async for _ in generator:
                pass

        async def parts():
            yield MessageChain(chain=[Image.fromURL("https://example.invalid/image.png")])

        event.send_streaming = consume
        prepare_core_reply_event(event, PreparedContext("Persona"), authorize=_allow, on_delivery=stages.append)
        activate_core_reply_delivery_guard(event)
        await event.send_streaming(parts())
        state = event.get_extra(CONTEXT_EXTRA_KEY)
        self.assertEqual((state["send_attempts"], state["send_returns"], state["send_unknown"]), (1, 1, 0))
        self.assertEqual(stages, ["stream_started", "returned", "finished"])

    async def test_stream_failure_before_any_content_does_not_claim_unknown_delivery(self):
        event = FakeEvent()

        async def consume(generator):
            async for _ in generator:
                pass

        async def parts():
            raise ValueError("generation failed before any reply")
            yield

        event.send_streaming = consume
        prepare_core_reply_event(event, PreparedContext("Persona"), authorize=_allow)
        activate_core_reply_delivery_guard(event)
        with self.assertRaises(ValueError):
            await event.send_streaming(parts())
        state = event.get_extra(CONTEXT_EXTRA_KEY)
        self.assertEqual((state["send_attempts"], state["send_returns"], state["send_unknown"]), (0, 0, 0))


async def _allow(_prepared):
    return Outcome.success(True)


async def _none():
    return None
