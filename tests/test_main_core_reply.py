"""The V2 intake hands admitted turns to AstrBot's core response path."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock

from companion_v2.foundation.outcome import Outcome
from tests.test_main_no_reply import ENTRY


class CoreReplyEvent:
    def __init__(self):
        self.platform_meta = NS(name="aiocqhttp")
        self.message_obj = NS(type=NS(value="FriendMessage"), raw_message={"post_type": "message"})
        self.message_str = "摸摸"
        self.call_llm = False
        self.is_wake = False
        self.is_at_or_wake_command = False
        self._has_send_oper = False
        self.extra = {}
        self.sent = []
        self.unified_msg_origin = "qq-main:FriendMessage:200"
        self.send = self._send
        self.send_streaming = self._send_streaming

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value

    def should_call_llm(self, value):
        self.call_llm = value

    def stop_event(self):
        self.stopped = True

    async def _send(self, message):
        self.sent.append(message)
        self._has_send_oper = True

    async def _send_streaming(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class MainCoreReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_admitted_private_turn_uses_core_and_rechecks_before_delivery(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        event = CoreReplyEvent()
        target = NS(key="target", target_id="target")
        prepared = {
            "context": object(),
            "instruction": "Use this companion persona.",
            "prompt_instruction": "Reply conversationally.",
            "stable_prompt_instruction": "Use the configured companion voice.",
            "target_id": "target",
            "channel": "private",
            "event_id": "event-1",
        }
        staging = NS(
            runtime=None,
            now=lambda: None,
            claims=lambda _event: True,
            target_for_event=lambda _event: target,
            persona_mapping_for_event=AsyncMock(return_value=NS(role_id="persona")),
            settings=NS(enabled=True),
            session=NS(profile=NS(target=target)),
            session_topology=NS(
                reply_enabled=AsyncMock(return_value=True),
                schedule_observe=Mock(),
            ),
            prepare_core_reply=AsyncMock(return_value=Outcome.success(prepared)),
            authorize_core_reply=AsyncMock(return_value=Outcome.success(True)),
        )
        plugin.staging = staging
        staging.session.core_reply_observations = NS(phase=Mock())

        await plugin.receive_companion_message(event)

        staging.persona_mapping_for_event.assert_not_awaited()
        staging.prepare_core_reply.assert_awaited_once_with(event, target, group_admission=None)
        self.assertTrue(event.is_wake)
        self.assertTrue(event.is_at_or_wake_command)
        self.assertFalse(event.call_llm)

        request = NS(system_prompt="AstrBot base prompt")
        await plugin.prepare_companion_core_request(event, request)
        staging.session.core_reply_observations.phase.assert_called_once()
        self.assertEqual(staging.session.core_reply_observations.phase.call_args.args[1], "running")
        self.assertNotIn(prepared["instruction"], request.system_prompt)
        self.assertIn(prepared["stable_prompt_instruction"], request.system_prompt)
        self.assertNotIn(prepared["prompt_instruction"], request.system_prompt)
        self.assertIn(prepared["prompt_instruction"], request.extra_user_content_parts[-1].text)
        self.assertTrue(request.extra_user_content_parts[-1]._no_save)
        steps = event.get_extra(ENTRY.CORE_REPLY_CONTEXT_EXTRA)["_preparation_steps"]
        self.assertEqual([item["name"] for item in steps], ["request_authorization", "prompt_injection",
            "send_tool_injection", "perception_injection"])
        self.assertTrue(all(type(item["elapsed_ms"]) is int and item["elapsed_ms"] >= 0 for item in steps))
        staging.authorize_core_reply.assert_awaited_once()
        authorization_args = staging.authorize_core_reply.await_args.args
        self.assertEqual(authorization_args[:2], (event, target))
        prepared_for_core = authorization_args[2]
        self.assertEqual(prepared_for_core["event_id"], prepared["event_id"])
        self.assertEqual(prepared_for_core["channel"], "private")

        await event.send("Other plugin notice")
        self.assertEqual(staging.authorize_core_reply.await_count, 1)

        await plugin.guard_companion_core_delivery(event)
        await event.send("AstrBot core reply")
        self.assertEqual(staging.authorize_core_reply.await_count, 2)
        self.assertEqual(event.sent, ["Other plugin notice", "AstrBot core reply"])

        await plugin.observe_companion_core_reply_sent(event)
        self.assertIs(event.send.__self__, event)
        self.assertIs(event.send.__func__, CoreReplyEvent._send)

    async def test_core_request_injects_configured_model_route_perception(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        event = CoreReplyEvent()
        event.extra["selected_provider"] = "chat-route"
        target = NS(key="target", target_id="target")
        provider = NS(provider_config={"id": "chat-route", "modalities": ["text", "image"]},
                      meta=lambda: NS(id="chat-route"), get_model=lambda: "qwen-chat-alias")
        observations = NS(phase=Mock())
        staging = NS(
            runtime=None,
            now=lambda: None,
            claims=lambda _event: True,
            target_for_event=lambda _event: target,
            settings=NS(enabled=True),
            context=NS(get_provider_by_id=Mock(return_value=provider), get_using_provider_async=AsyncMock()),
            session=NS(profile=NS(target=target), core_reply_observations=observations),
            session_topology=NS(reply_enabled=AsyncMock(return_value=True), schedule_observe=Mock()),
            prepare_core_reply=AsyncMock(return_value=Outcome.success({
                "context": NS(scope=NS(platform="qq-main")),
                "instruction": "Use this companion persona.",
                "prompt_instruction": "Reply conversationally.",
                "stable_prompt_instruction": "Use the configured companion voice.",
                "perception_options": (True, True, True),
                "target_id": "target", "channel": "private", "event_id": "event-1",
            })),
            authorize_core_reply=AsyncMock(return_value=Outcome.success(True)),
        )
        plugin.staging = staging

        await plugin.receive_companion_message(event)
        request = NS(system_prompt="AstrBot base prompt", model=None, image_urls=[], audio_urls=[], func_tool=None)
        await plugin.prepare_companion_core_request(event, request)

        self.assertIn("自然地陪伴和交流", request.system_prompt)
        self.assertIn("Use the configured companion voice.", request.system_prompt)
        self.assertNotIn("Reply conversationally.", request.system_prompt)
        self.assertNotIn("chat-route", request.system_prompt)
        perception = request.extra_user_content_parts[-1].text
        self.assertIn("Reply conversationally.", perception)
        self.assertIn('"platform":"qq-main"', perception)
        self.assertIn('"provider_id":"chat-route"', perception)
        self.assertIn('"model":"qwen-chat-alias"', perception)
        self.assertIn('"values":["text","image"]', perception)
        staging.context.get_using_provider_async.assert_not_awaited()

    async def test_native_runner_completion_observes_assistant_empty_and_error_phases_without_awaiting_storage(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        phase = Mock()
        plugin.staging = NS(session=NS(core_reply_observations=NS(phase=phase)))
        event = CoreReplyEvent()
        prepared = {"event_id": "phase-event", "turn_id": "phase-turn", "context": object()}
        ENTRY.prepare_core_reply_event(event, prepared, authorize=AsyncMock(return_value=Outcome.success(True)))
        for response, expected in ((NS(role="assistant", completion_text=""), "completed"), (None, "failed"),
                                   (NS(role="err", completion_text="model failed"), "failed")):
            await plugin.observe_companion_core_agent_done(event, NS(), response)
            self.assertEqual(phase.call_args.args, (prepared, expected))
        event.get_result = lambda: NS(result_content_type=NS(name="AGENT_RUNNER_ERROR"))
        await plugin.observe_companion_core_reply_sent(event)
        self.assertEqual(phase.call_args.args, (prepared, "failed"))
        phase.side_effect = OSError("optional background unavailable")
        await plugin.observe_companion_core_agent_done(event, NS(), NS(role="assistant"))
        self.assertEqual(event.sent, [])

    async def test_admitted_group_turn_keeps_candidate_and_enables_core_wake(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        event = CoreReplyEvent()
        event.message_obj.type = NS(value="GroupMessage")
        event.message_str = "小星来看看"
        target = NS(key="group-target", target_id="group-target")
        group_admission = {
            "admitted": True,
            "reason": "direct_word",
            "mentioned": False,
            "context_key": "group-context",
            "event_id": "group-event-1",
        }
        prepared = {
            "context": object(),
            "instruction": "Use the group companion persona.",
            "prompt_instruction": "Reply only when appropriate.",
            "target_id": "group-target",
            "channel": "group",
            "event_id": "group-event-1",
        }
        staging = NS(
            runtime=None,
            now=lambda: None,
            claims=lambda _event: True,
            target_for_event=lambda _event: target,
            persona_mapping_for_event=AsyncMock(return_value=NS(role_id="persona")),
            settings=NS(enabled=True),
            session=NS(profile=NS(target=target)),
            session_topology=NS(
                reply_enabled=AsyncMock(return_value=True),
                schedule_observe=Mock(),
            ),
            group_reply_candidate=AsyncMock(return_value=NS(
                failure=None, unwrap=lambda: group_admission)),
            prepare_core_reply=AsyncMock(return_value=Outcome.success(prepared)),
            authorize_core_reply=AsyncMock(return_value=Outcome.success(True)),
        )
        plugin.staging = staging

        await plugin.receive_companion_message(event)

        staging.persona_mapping_for_event.assert_not_awaited()
        staging.prepare_core_reply.assert_awaited_once_with(
            event, target, group_admission=group_admission)
        self.assertTrue(event.is_wake)
        self.assertTrue(event.is_at_or_wake_command)
        state = event.get_extra("_companion_v2_core_reply_context")
        self.assertEqual(state["prepared"]["channel"], "group")

    async def test_slow_directory_observation_does_not_delay_intake_or_model_response(self):
        from astrbot_host.session_topology import SessionTopology

        temporary = TemporaryDirectory(prefix="companion-main-directory-")
        self.addCleanup(temporary.cleanup)
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        event = CoreReplyEvent()
        target = NS(key="target", target_id="target")
        staging = NS(data_root=Path(temporary.name), _terminated=False, runtime=None, now=lambda: None,
            claims=lambda event: True, target_for_event=lambda event: target,
            persona_mapping_for_event=AsyncMock(return_value=NS(role_id="persona")),
            session=NS(profile=NS(target=target)), settings=NS(enabled=True),
            prepare_core_reply=AsyncMock(return_value=Outcome.success({"event_id": "directory-slow"})),
            authorize_core_reply=AsyncMock(return_value=Outcome.success(True)))
        topology = SessionTopology(staging)
        staging.session_topology = topology
        topology.reply_enabled = AsyncMock(return_value=True)
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_observe(event):
            entered.set()
            await release.wait()

        topology.observe = slow_observe
        plugin.staging = staging
        try:
            await asyncio.wait_for(plugin.receive_companion_message(event), 2)
            await asyncio.wait_for(entered.wait(), 2)
            self.assertTrue(event.is_at_or_wake_command)
            self.assertTrue(topology._pending)
            await asyncio.wait_for(plugin.observe_companion_model_session(event,
                NS(role="assistant", completion_text="摸摸你")), 2)
        finally:
            release.set()
            await topology.close()
        self.assertFalse(topology._pending)


if __name__ == "__main__":
    unittest.main()
