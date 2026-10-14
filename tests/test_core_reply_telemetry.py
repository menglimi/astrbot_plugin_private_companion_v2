"""Core measurements preserve native behavior and report only observed evidence."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from astrbot.core.provider.entities import TokenUsage
from astrbot.core.pipeline.process_stage.follow_up import _ACTIVE_AGENT_RUNNERS
from astrbot_host.core_reply import (
    CORE_REPLY_CONTEXT_EXTRA, activate_core_reply_delivery_guard, prepare_core_reply_event,
    inject_core_reply_prompt,
)
from astrbot_host.core_reply_preparation import measure_core_preparation
from astrbot_host.core_reply_perception import inject_core_reply_perception_context
from astrbot_host.core_reply_telemetry import (
    CORE_REPLY_TELEMETRY_EXTRA, _usage, finish_core_reply_telemetry,
    observe_core_agent_begin, observe_core_agent_done, observe_core_llm_response,
    observe_core_reply_delivery, observe_core_tool_finished, observe_core_tool_started,
    observe_core_waiting_llm_request, prepare_core_reply_telemetry,
)
from companion_v2.execution.models import digest
from companion_v2.foundation.outcome import Outcome
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.model_gateway.core_observations import observations_for_role, record_observation
from companion_v2.model_gateway.management import ModelManagement
from companion_v2.model_gateway.reply_efficiency import _core_sample
from tests.multi_host_support import MultiFixture


def response(inputs=100, output=20, *, cached=None, chunk=False):
    raw = {"usage": {"prompt_tokens": inputs, "completion_tokens": output}}
    if cached is not None:
        raw["usage"]["prompt_tokens_details"] = {"cached_tokens": cached}
    return NS(role="assistant", is_chunk=chunk, completion_text="private response body",
              usage=TokenUsage(input_other=inputs - (cached or 0), input_cached=cached or 0, output=output), raw_completion=raw)


class NativeRunnerFixture:
    def __init__(self, event, req, rounds):
        self.run_context = NS(context=NS(event=event), messages=[
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": "private history"},
            {"role": "assistant", "content": "private historical reply"},
            {"role": "user", "content": req.prompt}])
        self.req, self.rounds = req, list(rounds)
        self.provider = NS(provider_config={"id": "real-core-provider"}, get_model=lambda: "real-model")
        self.stats = NS(token_usage=TokenUsage(), duration=0.2, time_to_first_token=0.03)
        self.final_llm_resp = None
        self._done = False

    async def _iter_llm_responses(self, *, include_model=True):
        result = self.rounds.pop(0)
        if isinstance(result, BaseException):
            raise result
        for item in result:
            yield item

    async def step(self):
        async for item in self._iter_llm_responses():
            if not item.is_chunk:
                self.stats.token_usage += item.usage
                self.final_llm_resp = item
            yield item
        self._done = not self.rounds

    def done(self):
        return self._done


class UsageAvailabilityTests(unittest.TestCase):
    def test_efficiency_separates_observed_requests_tools_and_agent_duration(self):
        def at(seconds):
            return (datetime.fromisoformat("2026-10-10T00:00:00+00:00") + timedelta(seconds=seconds)).isoformat()
        record = {"turn_id": "timed-core-turn", "received_at": at(0), "waiting_llm_at": at(0.5),
            "request_hook_at": at(1),
            "agent_started_at": at(1.2), "generation_finished_at": at(3), "runner_duration_ms": 1800,
            "generation_state": "completed", "requests": [
                {"position": 1, "state": "returned", "started_at": at(1.5), "finished_at": at(2), "latency_ms": 500},
                {"position": 2, "state": "returned", "started_at": at(2.3), "finished_at": at(2.7), "latency_ms": 400},
                {"position": 3, "state": "returned", "started_at": at(2.2), "finished_at": at(2.8), "latency_ms": 600,
                 "measurement_basis": "last_tool_requery_only"}],
            "tools": [{"action": "read", "state": "returned", "started_at": at(2), "finished_at": at(2.3)}],
            "preparation_steps": [{"elapsed_ms": 180}, {"elapsed_ms": 0}, {"elapsed_ms": 20}],
            "delivery": {"state": "returned", "attempts": 1, "returned": 1,
                "first_started_at": at(2.8), "first_returned_at": at(3.2), "last_returned_at": at(3.2)}}
        sample = _core_sample(record)
        self.assertEqual(sample["stages"]["model_request_ms"], 900)
        self.assertEqual(sample["stages"]["model_ms"], 1200)
        self.assertEqual(sample["stages"]["tool_ms"], 300)
        self.assertEqual(sample["stages"]["agent_ms"], 1800)
        self.assertEqual(sample["stages"]["plugin_preparation_ms"], 200)
        self.assertEqual(sample["stages"]["waiting_llm_to_request_hook_ms"], 500)
        self.assertEqual(sample["stages"]["request_hook_to_agent_ms"], 200)
        self.assertEqual(sample["stages"]["send_ms"], 400)
        self.assertEqual(sample["timestamps"]["last_model_finished_at"], at(2.7))
        self.assertEqual(sample["timestamps"]["agent_finished_at"], at(3))
        self.assertIsNone(sample["stages"]["post_model_ms"])  # Streaming sent before the agent ended.
        fallback = _core_sample({**record, "requests": [record["requests"][-1]], "runner_duration_ms": 0})
        self.assertIsNone(fallback["stages"]["model_request_ms"])
        self.assertIsNone(fallback["timestamps"]["first_model_started_at"])
        self.assertEqual(fallback["stages"]["agent_ms"], 0)

    def test_deepseek_cache_hit_and_anthropic_creation_breakdown_follow_legacy_telemetry(self):
        deepseek = _usage(NS(usage=None, raw_completion={"usage": {
            "prompt_tokens": 100, "completion_tokens": 10, "prompt_cache_hit_tokens": 40}}))
        self.assertEqual((deepseek["tokens"], deepseek["cached_input_tokens"]), (110, 40))
        anthropic = _usage(NS(usage=None, raw_completion={"usage": {
            "input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 50,
            "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 5}}}))
        self.assertEqual((anthropic["tokens"], anthropic["cache_creation_tokens"]), (185, 25))

    def test_inconsistent_cache_metadata_does_not_discard_reported_token_totals(self):
        measured = _usage(response(cached=101))
        self.assertEqual(measured["tokens"], 120)
        self.assertIsNone(measured["cached_input_tokens"])

    def test_fallback_usage_observations_do_not_invent_model_calls(self):
        requests = [{"position": index, "state": "returned", **fields} for index, fields in enumerate((
            {"measurement_basis": "provider_response"}, {"measurement_basis": "runner_aggregate"},
            {"measurement_basis": "last_tool_requery_only"}, {}), start=1)]
        sample = _core_sample({"turn_id": "observed-core-turn", "received_at": "2026-10-10T00:00:00+00:00",
                               "requests": requests})
        self.assertEqual(sample["model_calls"], 2)
        self.assertEqual(sample["usage_observation_count"], 4)
        self.assertEqual(len(sample["trace"]["model_calls"]), 4)

    def test_missing_cache_is_unknown_but_explicit_zero_remains_zero(self):
        self.assertIsNone(_usage(response())['cached_input_tokens'])
        zero = _usage(response(cached=0))
        self.assertEqual(zero["cached_input_tokens"], 0)
        self.assertEqual(zero["cache_availability"], "provider_report")
        self.assertIsNone(_usage(NS(usage=TokenUsage(), raw_completion=None))["tokens"])

    def test_anthropic_cache_creation_and_gemini_inclusive_inputs(self):
        anthropic = _usage(NS(usage=None, raw_completion={"usage": {
            "input_tokens": 100, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 25, "output_tokens": 10}}))
        self.assertEqual(anthropic["input_tokens"], 175)
        self.assertEqual(anthropic["tokens"], 185)
        gemini = _usage(NS(usage=TokenUsage(input_other=100, input_cached=50, output=10),
            raw_completion={"usage_metadata": {"prompt_token_count": 100,
                "cached_content_token_count": 50, "candidates_token_count": 10}}))
        self.assertEqual(gemini["input_tokens"], 100)
        self.assertEqual(gemini["tokens"], 110)


class CoreReplyTelemetryTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = await self.start_host()
        self.queued = []

    async def test_actual_media_request_presence_persists_without_prompt_bodies(self):
        from astrbot_host.core_reply_media_prompt import finalize_core_reply_media_prompt
        from companion_v2.conversation.voice_reply import VoiceReplyPolicy
        event, prepared, req = await self.prepare("media-presence-observation")
        prepared["voice_reply_policy"] = VoiceReplyPolicy(generation_mode="model_tag", language="ja")
        event.get_extra(CORE_REPLY_CONTEXT_EXTRA)["_reaction_reply"] = {"enabled": True}
        runner = NativeRunnerFixture(event, req, [[response()]])
        finalize_core_reply_media_prompt(event, runner.run_context)
        self.register(event, runner)
        async for _ in runner.step():
            pass
        self.flush()
        saved = observations_for_role(self.app.runtime, prepared["context"])[0]
        media = saved["requests"][0]["media"]
        self.assertEqual(media["voice_mode"], "always")
        self.assertTrue(media["voice_prompt_present"])
        self.assertTrue(media["reaction_prompt_present"])
        self.assertNotIn("private system prompt", json.dumps(saved))
        for malformed in ({**media, "body": "private prompt"}, {**media, "presentation_present": "private prompt"}):
            bad = {**saved, "requests": [{**saved["requests"][0], "media": malformed}]}
            # Stored projections add role/context keys outside the raw record.
            bad.pop("context_key", None)
            bad.pop("context_json", None)
            with self.assertRaises(ValueError):
                record_observation(self.app.runtime, prepared["context"], bad)

    async def test_voice_formatting_stays_in_core_usage_and_does_not_spend_plugin_budget(self):
        from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
        from astrbot.core.provider.entities import ProviderRequest
        from astrbot_host.core_reply_voice_authoring import bind_core_voice_authoring
        from companion_v2.conversation.voice_reply import VoiceReplyPolicy
        from tests.test_core_reply_voice_authoring import Hooks, Provider

        event, prepared, _ = await self.prepare("core-voice-formatting-accounting")
        prepared["voice_reply_policy"] = VoiceReplyPolicy(generation_mode="model_tag", language="ja",
            foreign_text_mode="translation")
        runner = ToolLoopAgentRunner()
        req = ProviderRequest(prompt="在干嘛呢", system_prompt="当前角色")
        await runner.reset(provider=Provider("我在陪你。", "<pc_tts>君と話してる。</pc_tts>我在陪你。"),
            request=req, run_context=NS(context=NS(event=event), messages=[]),
            tool_executor=None, agent_hooks=Hooks())
        bind_core_voice_authoring(event, runner)
        self.register(event, runner)
        async for _ in runner.step():
            pass
        self.flush()
        saved = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(len(saved["requests"]), 2)
        self.assertTrue(all(request["measurement_basis"] == "provider_response" for request in saved["requests"]))
        self.assertEqual(sum(request["usage"]["tokens"] for request in saved["requests"]), 220)
        self.assertEqual(self.report(prepared["context"])["budget"]["spent_tokens"], 0)
        self.assertEqual(self.app.runtime.read_one("SELECT COUNT(*) n FROM model_rounds", ())["n"], 0)
        self.assertNotIn("君と話してる", json.dumps(saved, ensure_ascii=False))

    async def prepare(self, identifier="core-observation", *, inject=False):
        event = self.event(identifier=identifier, text="private latest prompt")
        prepared = (await self.controller.prepare_core_reply(event)).unwrap()
        event.set_extra(CORE_REPLY_CONTEXT_EXTRA, {"prepared": prepared})
        observe_core_waiting_llm_request(event, now=self.clock.now)
        req = NS(system_prompt="private system prompt", prompt="private latest prompt", contexts=[],
                 model="real-model", func_tool=NS(tools=[NS(name="read_file", description="private tool description",
                     parameters={"type": "object"}, active=True)]), image_urls=["https://private.example/image"],
                 audio_urls=[], extra_user_content_parts=[])
        if inject:
            with measure_core_preparation(event, "prompt_injection", now=self.clock.now):
                inject_core_reply_prompt(event, req)
            await inject_core_reply_perception_context(event, req, native_context=self.controller.context)
            if prepared.get("prompt_instruction"):
                self.assertTrue(event.get_extra(CORE_REPLY_CONTEXT_EXTRA).get("_perception_background_injected"))
        prepare_core_reply_telemetry(event, req, application=self.app, submit=self.queued.append, now=self.clock.now)
        return event, prepared, req

    def register(self, event, runner):
        _ACTIVE_AGENT_RUNNERS[event.unified_msg_origin] = runner
        self.addCleanup(_ACTIVE_AGENT_RUNNERS.pop, event.unified_msg_origin, None)
        observe_core_agent_begin(event, runner.run_context)

    def flush(self, *, reversed_order=False):
        queued = list(self.queued)
        self.queued.clear()
        for work in reversed(queued) if reversed_order else queued:
            work()

    def report(self, context):
        policy = ObjectAccessPolicy(self.app.runtime)
        policy.set_tier(context.actor.subject, AuthorizationTier.CORE,
                        expected_revision=policy.revision, observed_at=self.clock.now())
        result = ModelManagement(self.app, context).maintenance(context.actor)
        self.assertTrue(result.is_success, result.failure)
        return result.unwrap()

    async def test_real_context_and_request_preparation_reach_efficiency_without_bodies_or_inline_writes(self):
        event, prepared, req = await self.prepare("preparation-observation", inject=True)
        with patch("astrbot_host.core_reply_preparation.time.monotonic", side_effect=[10, 10.2]):
            with measure_core_preparation(event, "tool_injection", now=self.clock.now):
                pass
        with measure_core_preparation(event, "perception_injection", now=self.clock.now):
            pass
        with measure_core_preparation(event, "telemetry_capture", now=self.clock.now):
            pass
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"]), [])
        observe_core_llm_response(event, response())
        self.flush(reversed_order=True)
        report = self.report(prepared["context"])
        sample = report["reply_efficiency"]["recent"][0]
        steps = sample["trace"]["preparation_steps"]
        self.assertEqual([item["name"] for item in steps], ["context_build", "prompt_injection", "tool_injection",
            "perception_injection", "telemetry_capture"])
        self.assertEqual(steps[2]["elapsed_ms"], 200)
        self.assertEqual(sample["timestamps"]["waiting_llm_at"], sample["received_at"])
        self.assertEqual(sample["trace"]["offered_tools"], ["read_file"])
        self.assertGreaterEqual(len(sample["trace"]["materials"]), 1)
        self.assertTrue(any(item["state"] == "ready" for item in sample["trace"]["materials"]),
            f"background_injected={event.get_extra(CORE_REPLY_CONTEXT_EXTRA).get('_perception_background_injected')} "
            f"instruction_chars={len(prepared.get('prompt_instruction', ''))} materials={sample['trace']['materials']!r}")
        self.assertTrue(all(type(item["elapsed_ms"]) is int for item in sample["trace"]["materials"]))
        self.assertEqual(report["reply_efficiency"]["coverage"]["core_preparation"], 1)
        self.assertEqual(report["budget"]["spent_tokens"], 0)
        encoded = json.dumps(report)
        for private in ("private system prompt", "private latest prompt", "private tool description", req.system_prompt):
            self.assertNotIn(private, encoded)

    async def native_buffered_stream(self, identifier, *, preceding_send=False):
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

        fixture, prepared, _ = await self.prepare(identifier)
        event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
        event._extras = {}
        event.platform_meta = NS(name="aiocqhttp")
        event.get_result = lambda: NS(result_content_type=NS(name="STREAMING_RESULT"))
        state = fixture.get_extra(CORE_REPLY_TELEMETRY_EXTRA)
        event.set_extra(CORE_REPLY_TELEMETRY_EXTRA, state)
        started, bodies, stages = [], [], []

        async def native_send(message):
            started.append(self.clock.now())
            bodies.append(message.get_plain_text())
            self.clock.advance(timedelta(seconds=1))

        async def authorize(_prepared):
            return Outcome.success(True)

        def delivery(stage):
            stages.append(stage)
            if stage == "finished":
                finish_core_reply_telemetry(event)
            else:
                observe_core_reply_delivery(event, stage)

        event.send = native_send
        prepare_core_reply_event(event, prepared, authorize=authorize, on_delivery=delivery)
        activate_core_reply_delivery_guard(event)
        if preceding_send:
            await event.send(MessageChain([Plain("preceding tool message")]))
            self.clock.advance(timedelta(seconds=1))
        stream_start = self.clock.now()

        async def chunks():
            yield MessageChain([Plain("first")])
            self.clock.advance(timedelta(seconds=5))
            yield MessageChain([Plain("second")])

        async def no_metric(**kwargs):
            return None

        # The QQ adapter itself buffers t0..t5, calls event.send at t5, then
        # invokes the base streaming bookkeeping. No platform or metric IO.
        with patch("astrbot.core.platform.astr_message_event.Metric.upload", new=no_metric):
            await event.send_streaming(chunks(), use_fallback=False)
            await asyncio.sleep(0)
        self.flush()
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertNotIn("_stream_first_started_at", state)
        self.assertEqual(bodies[-1], "firstsecond")
        self.assertEqual(started[-1], stream_start + timedelta(seconds=5))
        return record, started, stream_start, stages

    async def test_real_qq_buffered_stream_records_native_send_time_instead_of_first_chunk(self):
        record, started, stream_start, stages = await self.native_buffered_stream("qq-buffered-send-clock")
        delivery = record["delivery"]
        self.assertEqual(stages, ["started", "returned", "finished"])
        self.assertEqual(datetime.fromisoformat(delivery["first_started_at"]), started[0])
        self.assertNotEqual(datetime.fromisoformat(delivery["first_started_at"]), stream_start)
        self.assertEqual(datetime.fromisoformat(delivery["first_returned_at"]), stream_start + timedelta(seconds=6))
        self.assertEqual((delivery["attempts"], delivery["returned"]), (1, 1))
        self.assertEqual(delivery["state"], "returned")
        self.assertEqual(datetime.fromisoformat(_core_sample(record)["timestamps"]["first_dispatched_at"]), started[0])

    async def test_real_qq_buffered_stream_keeps_preceding_real_send_first_time(self):
        record, started, stream_start, stages = await self.native_buffered_stream(
            "qq-buffered-after-tool-clock", preceding_send=True)
        delivery = record["delivery"]
        self.assertEqual(stages, ["started", "returned", "started", "returned", "finished"])
        self.assertEqual(datetime.fromisoformat(delivery["first_started_at"]), started[0])
        self.assertEqual(datetime.fromisoformat(delivery["first_returned_at"]), started[0] + timedelta(seconds=1))
        self.assertEqual(datetime.fromisoformat(delivery["last_returned_at"]), stream_start + timedelta(seconds=6))
        self.assertEqual((delivery["attempts"], delivery["returned"]), (2, 2))

    async def test_native_stream_without_nested_send_keeps_chunk_time_and_cleans_marker(self):
        event, prepared, _ = await self.prepare("native-stream-clock")
        state = event.get_extra(CORE_REPLY_TELEMETRY_EXTRA)
        started = self.clock.now()
        observe_core_reply_delivery(event, "stream_started")
        self.assertIn("_stream_first_started_at", state)
        self.assertEqual(state["record"]["delivery"]["state"], "started")
        self.clock.advance(timedelta(seconds=6))
        observe_core_reply_delivery(event, "returned")
        finish_core_reply_telemetry(event, {"send_attempts": 1, "send_returns": 1})
        self.assertNotIn("_stream_first_started_at", state)
        self.flush()
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(datetime.fromisoformat(record["delivery"]["first_started_at"]), started)
        self.assertEqual(datetime.fromisoformat(record["delivery"]["first_returned_at"]), self.clock.now())

    async def test_tool_rounds_keep_actual_usage_delivery_and_body_free_reports(self):
        event, prepared, req = await self.prepare()
        first, final = response(1500, 20, cached=1000), response(1700, 30)
        runner = NativeRunnerFixture(event, req, [[first], [final]])
        original_iter = runner._iter_llm_responses.__func__
        self.register(event, runner)
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"]), [])
        self.assertEqual([item async for item in runner.step()], [first])
        observe_core_reply_delivery(event, "started")
        self.clock.advance(timedelta(seconds=1))
        observe_core_reply_delivery(event, "returned")
        finish_core_reply_telemetry(event, {"send_attempts": 1, "send_returns": 1, "unknown_sends": 0})
        observe_core_tool_started(event, req.func_tool.tools[0])
        self.clock.advance(timedelta(seconds=2))
        observe_core_tool_finished(event, req.func_tool.tools[0])
        self.assertEqual([item async for item in runner.step()], [final])
        observe_core_agent_done(event, runner.run_context, final)
        observe_core_llm_response(event, final)
        observe_core_reply_delivery(event, "started")
        self.clock.advance(timedelta(seconds=1))
        observe_core_reply_delivery(event, "returned")
        finish_core_reply_telemetry(event, {"send_attempts": 2, "send_returns": 2, "unknown_sends": 0})
        self.assertIs(runner._iter_llm_responses.__func__, original_iter)
        self.flush(reversed_order=True)
        report = self.report(prepared["context"])
        core = report["usage_sources"]["astrbot_core"]
        self.assertEqual(core["summary"]["calls"], 2)
        self.assertEqual(core["summary"]["tokens"], 3250)
        self.assertIsNone(core["summary"]["cost_microusd"])
        self.assertIsNone(core["daily"][-1]["cost_microusd"])
        self.assertIsNone(core["by_provider"][0]["cost_microusd"])
        self.assertEqual(report["cost_availability"], "partial")
        self.assertEqual(core["summary"]["cache_reported_calls"], 1)
        self.assertEqual(core["summary"]["cached_input_tokens"], 1000)
        self.assertEqual(report["budget"]["spent_tokens"], 0)
        self.assertEqual(report["usage_sources"]["plugin"]["summary"]["calls"], 0)
        sample = report["reply_efficiency"]["recent"][0]
        self.assertEqual(sample["execution_path"], "astrbot_core")
        self.assertEqual(sample["outcome"], "completed")
        self.assertEqual(sample["delivery"]["returned"], 2)
        self.assertFalse(sample["delivery"]["platform_confirmed"])
        self.assertIsNone(sample["stages"]["end_to_end_ms"])
        self.assertEqual(sample["stages"]["end_to_end_send_returned_ms"], 4000)
        self.assertEqual(report["reply_efficiency"]["summary"]["median_end_to_end_send_returned_ms"], 4000)
        self.assertEqual(sample["trace"]["tool_calls"][0]["elapsed_ms"], 2000)
        from companion_v2.conversation.reply_management import ReplyManagement
        reply_status = ReplyManagement(self.app, prepared["context"]).status(prepared["context"].actor).unwrap()
        recent = reply_status["recent"][0]
        self.assertEqual(recent["batch_id"], prepared["turn_id"])
        self.assertEqual((recent["execution_path"], recent["state"], recent["send_returns"]), ("astrbot_core", "complete", 2))
        self.assertEqual(len(recent["calls"]), 2)
        self.assertNotIn("private system prompt", json.dumps(report))
        self.assertNotIn("private latest prompt", json.dumps(report))
        self.assertNotIn("https://private.example/image", json.dumps(report))
        self.assertNotIn("private tool description", json.dumps(report))
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM model_requests", ()), ())
        self.assertEqual(self.app.runtime.read_all("SELECT * FROM conversation_batches", ()), ())

    async def test_incompatible_runner_falls_back_without_changing_native_methods(self):
        event, prepared, req = await self.prepare("fallback-observation")
        runner = NS(run_context=NS(context=NS(event=event)), provider=NS(provider_config={"id": "fallback-provider"}),
                    stats=NS(token_usage=TokenUsage(input_other=200, output=30), duration=0.2, time_to_first_token=0))
        _ACTIVE_AGENT_RUNNERS[event.unified_msg_origin] = runner
        self.addCleanup(_ACTIVE_AGENT_RUNNERS.pop, event.unified_msg_origin, None)
        observe_core_agent_begin(event, runner.run_context)
        observe_core_llm_response(event, response(100, 20))
        observe_core_agent_done(event, runner.run_context, response(100, 20))
        self.flush()
        report = self.report(prepared["context"])["usage_sources"]["astrbot_core"]
        self.assertEqual(report["summary"]["tokens"], 230)
        self.assertEqual(report["summary"]["calls"], 0)
        self.assertEqual(report["recent"][0]["usage_scope"], "runner_aggregate")
        self.assertEqual(report["coverage"]["fallback_usage_observations"], 1)
        self.assertIsNone(report["recent"][0]["cached_input_tokens"])

    async def test_telemetry_owner_rejects_extra_prompt_or_tool_payload_fields(self):
        event, prepared, req = await self.prepare("body-free-owner")
        observe_core_llm_response(event, response())
        record = event.get_extra(CORE_REPLY_TELEMETRY_EXTRA)["record"]
        with self.assertRaises(ValueError):
            record_observation(self.app.runtime, prepared["context"], {**record, "prompt": "must never persist"})
        malformed = {**record, "request_hook_signature": {**record["request_hook_signature"], "prompt": "must never persist"}}
        with self.assertRaises(ValueError):
            record_observation(self.app.runtime, prepared["context"], malformed)
        malformed = {**record, "tools": [{"sequence": 1, "action": "read", "arguments": "must never persist"}]}
        with self.assertRaises(ValueError):
            record_observation(self.app.runtime, prepared["context"], malformed)
        for field, value in (("materials", [{"owner": "private_companion.v2", "purpose": "memory", "state": "ready", "payload": "private body"}]),
                             ("preparation_steps", [{"name": "prompt_injection", "state": "returned", "prompt": "private body"}]),
                             ("offered_tools", [{"name": "read", "arguments": "private body"}])):
            with self.assertRaises(ValueError):
                record_observation(self.app.runtime, prepared["context"], {**record, field: value})
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"]), [])

    async def test_request_failure_and_unknown_send_are_never_reported_as_delivered(self):
        event, prepared, req = await self.prepare("failed-observation")
        error = TimeoutError("private provider failure body")
        runner = NativeRunnerFixture(event, req, [error])
        self.register(event, runner)
        with self.assertRaises(TimeoutError) as raised:
            _ = [item async for item in runner.step()]
        self.assertIs(raised.exception, error)
        self.assertNotIn("step", runner.__dict__)
        observe_core_reply_delivery(event, "started")
        observe_core_reply_delivery(event, "unknown")
        observe_core_reply_delivery(event, "returned")
        finish_core_reply_telemetry(event, {"send_attempts": 1, "send_returns": 0, "unknown_sends": 1})
        self.flush()
        report = self.report(prepared["context"])
        sample = report["reply_efficiency"]["recent"][0]
        self.assertEqual(sample["outcome"], "unknown")
        self.assertEqual(sample["delivery"]["returned"], 0)
        self.assertFalse(sample["observed"]["final_delivered"])
        self.assertNotIn("private provider failure body", json.dumps(report))
        self.assertEqual(report["usage_sources"]["astrbot_core"]["summary"]["unconfirmed_calls"], 1)

    async def test_same_umo_runner_for_another_event_is_never_wrapped(self):
        event, prepared, req = await self.prepare("own-event")
        other = self.event(identifier="concurrent-other-event")
        runner = NativeRunnerFixture(other, req, [[response()]])
        _ACTIVE_AGENT_RUNNERS[event.unified_msg_origin] = runner
        self.addCleanup(_ACTIVE_AGENT_RUNNERS.pop, event.unified_msg_origin, None)
        observe_core_agent_begin(event, runner.run_context)
        self.assertNotIn("_iter_llm_responses", runner.__dict__)
        observe_core_llm_response(event, response(cached=0))
        self.flush()
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"])[0]["usage_scope"], "last_response_only")

    async def test_known_no_send_failure_is_failed_and_later_native_reply_is_partial(self):
        event, prepared, req = await self.prepare("known-send-failure")
        runner = NativeRunnerFixture(event, req, [[response()]])
        self.register(event, runner)
        _ = [item async for item in runner.step()]
        observe_core_reply_delivery(event, "started")
        observe_core_reply_delivery(event, "failed")
        finish_core_reply_telemetry(event, {"send_attempts": 1, "send_returns": 0, "send_unknown": 0, "send_failed": 1})
        self.flush()
        report = self.report(prepared["context"])["reply_efficiency"]
        sample = report["recent"][0]
        self.assertEqual(sample["outcome"], "failed")
        self.assertEqual((sample["failed_parts"], sample["send_returned_parts"], sample["unknown_parts"], sample["pending_parts"]),
                         (1, 0, 0, 0))
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertIsNone(sample["timestamps"]["first_send_returned_at"])
        self.assertFalse(sample["observed"]["send_returned"])
        observe_core_reply_delivery(event, "started")
        self.clock.advance(timedelta(seconds=1))
        observe_core_reply_delivery(event, "returned")
        finish_core_reply_telemetry(event, {"send_attempts": 2, "send_returns": 1, "send_unknown": 0, "send_failed": 1})
        self.flush()
        sample = self.report(prepared["context"])["reply_efficiency"]["recent"][0]
        self.assertEqual(sample["outcome"], "partial")
        self.assertEqual((sample["failed_parts"], sample["send_returned_parts"], sample["unknown_parts"], sample["pending_parts"]),
                         (1, 1, 0, 0))
        self.assertFalse(sample["observed"]["final_delivered"])

    async def test_background_store_failure_never_changes_native_result_and_revision_fences(self):
        event, prepared, req = await self.prepare("store-failure")
        final = response()
        runner = NativeRunnerFixture(event, req, [[final]])
        self.register(event, runner)
        state = event.get_extra(CORE_REPLY_TELEMETRY_EXTRA)
        observer = self.controller.session.core_reply_observations
        state["submit"] = observer.submit
        with patch("astrbot_host.core_reply_telemetry.record_observation", side_effect=OSError("store unavailable")):
            self.assertEqual([item async for item in runner.step()], [final])
            await asyncio.gather(*tuple(observer._pending), return_exceptions=True)
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"]), [])
        record_observation(self.app.runtime, prepared["context"], state["record"])
        older = {**state["record"], "revision": 0, "generation_state": "prepared"}
        record_observation(self.app.runtime, prepared["context"], older)
        self.assertEqual(observations_for_role(self.app.runtime, prepared["context"])[0]["generation_state"], "completed")
        state["submit"] = lambda work: (_ for _ in ()).throw(OSError("submit failed"))
        finish_core_reply_telemetry(event)
        self.assertNotIn("step", runner.__dict__)

    async def test_cached_image_observation_preserves_native_tool_results_on_failure(self):
        event, prepared, req = await self.prepare("tool-cached-image")
        runner = NativeRunnerFixture(event, req, [[response()]])
        cached, untouched = NS(content_hash="native-image-hash"), NS(kind="tool_result")
        item = NS(kind="cached_image", cached_image=cached)
        async def native_tools(*args, **kwargs):
            yield item
            yield untouched
        runner._handle_function_tools = native_tools
        self.register(event, runner)
        with patch("astrbot_host.core_reply_reactions.observe_core_cached_image", side_effect=OSError("optional record unavailable")) as observe:
            results = [result async for result in runner._handle_function_tools(llm_response=response())]
        self.assertEqual(results, [item, untouched])
        self.assertIs(results[0], item)
        observe.assert_called_once_with(event, cached)
        _ = [result async for result in runner.step()]
        self.assertIs(runner._handle_function_tools, native_tools)

    async def test_cancelled_runner_restores_its_methods_and_keeps_cancellation(self):
        event, prepared, req = await self.prepare("cancelled-observation")
        entered, release = asyncio.Event(), asyncio.Event()
        chunk = response(chunk=True)
        runner = NativeRunnerFixture(event, req, [])
        async def original_stream(**kwargs):
            yield chunk
            entered.set()
            await release.wait()
        runner._iter_llm_responses = original_stream
        self.register(event, runner)
        async def run():
            return [item async for item in runner.step()]
        task = asyncio.create_task(run())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIs(runner._iter_llm_responses, original_stream)
        self.assertNotIn("step", runner.__dict__)
        self.flush()
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(record["generation_state"], "failed")
        self.assertEqual(record["requests"][0]["state"], "unknown")
        self.assertIsNone(record["requests"][0]["usage"]["tokens"])

    async def test_core_closing_completed_provider_iterator_keeps_tools_round_active(self):
        event, prepared, req = await self.prepare("closed-round")
        first, final = response(100, 10), response(150, 20)
        runner = NativeRunnerFixture(event, req, [[first], [final]])
        self.register(event, runner)
        iterator = runner._iter_llm_responses()
        self.assertIs(await anext(iterator), first)
        # AstrBot exits the provider iterator immediately after its final
        # response; closing that generator is a normal tool-round boundary.
        await iterator.aclose()
        state = event.get_extra(CORE_REPLY_TELEMETRY_EXTRA)
        self.assertIs(state["runner"], runner)
        self.assertEqual(state["record"]["generation_state"], "running")
        self.assertEqual(state["record"]["requests"][0]["state"], "returned")
        self.assertEqual([item async for item in runner.step()], [final])
        self.flush()
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(record["generation_state"], "completed")
        self.assertEqual(len(record["requests"]), 2)

    async def test_real_astrbot_runner_preserves_response_and_restores_observation_methods(self):
        from astrbot.core.agent.hooks import BaseAgentRunHooks
        from astrbot.core.agent.run_context import ContextWrapper
        from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
        from astrbot.core.provider.entities import LLMResponse, ProviderRequest
        event, prepared, _ = await self.prepare("real-runner")
        req = ProviderRequest(system_prompt="private system prompt", prompt="private latest prompt", model="real-model")
        final = LLMResponse(role="assistant", completion_text="native core response", usage=TokenUsage(input_other=100, output=20),
                            raw_completion={"usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                "prompt_tokens_details": {"cached_tokens": 0}}})
        calls = []
        async def text_chat(**kwargs):
            calls.append(kwargs)
            return final
        provider = NS(provider_config={"id": "actual-core"}, get_model=lambda: "real-model", text_chat=text_chat)
        class Hooks(BaseAgentRunHooks):
            async def on_agent_begin(inner, context):
                observe_core_agent_begin(event, context)
            async def on_agent_done(inner, context, response):
                from astrbot_host.core_reply_tool_dispatch import restore_core_tool_dispatch
                restore_core_tool_dispatch(event, context)
                observe_core_agent_done(event, context, response)
        runner = ToolLoopAgentRunner()
        await runner.reset(provider=provider, request=req, run_context=ContextWrapper(context=NS(event=event)),
                           tool_executor=NS(), agent_hooks=Hooks())
        _ACTIVE_AGENT_RUNNERS[event.unified_msg_origin] = runner
        self.addCleanup(_ACTIVE_AGENT_RUNNERS.pop, event.unified_msg_origin, None)
        results = [item async for item in runner.step()]
        self.assertTrue(runner.done())
        self.assertIs(runner.get_final_llm_resp(), final)
        self.assertEqual(len(calls), 1)
        self.assertEqual(results[-1].data["chain"].get_plain_text(), "native core response")
        self.assertNotIn("_iter_llm_responses", runner.__dict__)
        self.assertNotIn("_handle_function_tools", runner.__dict__)
        self.assertNotIn("_resolve_tool_exec", runner.__dict__)
        self.flush()
        record = observations_for_role(self.app.runtime, prepared["context"])[0]
        self.assertEqual(record["requests"][0]["usage"]["tokens"], 120)
        self.assertEqual(record["requests"][0]["usage"]["cached_input_tokens"], 0)
        self.assertEqual(record["requests"][0]["provider"], "actual-core")
        self.assertEqual(record["generation_state"], "completed")

    async def test_role_account_and_session_signatures_are_isolated(self):
        event, prepared, req = await self.prepare("scope-a")
        response_a = response(cached=0)
        observe_core_llm_response(event, response_a)
        self.flush()
        first = prepared["context"]
        other_bot_scope = replace(first.scope, account_id="another-account", bot_id="another-bot")
        other_bot = replace(first, role_binding=replace(first.role_binding, scope=other_bot_scope),
                            audience=replace(first.audience, scope=other_bot_scope))
        self.assertEqual(observations_for_role(self.app.runtime, other_bot), [])
        another_role = replace(first.role_binding.role, subject_id="another-role")
        other_role = replace(first, role_binding=replace(first.role_binding, role=another_role))
        self.assertEqual(observations_for_role(self.app.runtime, other_role), [])
        scope = replace(first.scope, native_scope_id="other-window", conversation_id="other-conversation", session_id="other-session")
        other_session = replace(first, role_binding=replace(first.role_binding, scope=scope), audience=replace(first.audience, scope=scope))
        original = observations_for_role(self.app.runtime, first)[0]
        record = {key: value for key, value in original.items() if key not in ("context_key", "context_json")}
        record = {**record, "turn_id": "core-reply:" + digest([other_session.key, "scope-b"]), "revision": 100}
        record["requests"] = [{**record["requests"][0], "signature": {**record["requests"][0]["signature"],
            "system_hash": "f" * 64, "system_parts": ["f" * 64]}}]
        record_observation(self.app.runtime, other_session, record)
        report = self.report(first)["usage_sources"]["astrbot_core"]
        self.assertEqual(report["cache_diagnostics"]["daily"][0]["baseline_calls"], 2)
        self.assertEqual(report["cache_diagnostics"]["daily"][0]["compared_calls"], 0)


if __name__ == "__main__":
    unittest.main()
