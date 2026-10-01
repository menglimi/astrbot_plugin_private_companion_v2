"""Offline native-SDK coverage for replacement, tools, streaming and delivery."""

import asyncio
from dataclasses import replace
import json
import unittest

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

from companion_v2.adapters.astrbot.provider import AstrBotTextProvider, UsageTariff, provider_fingerprint
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.segmentation import LLM_SEGMENT_MARKER, SegmentationPolicy
from companion_v2.execution.models import ProviderBinding
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.adapters.astrbot.model_wire import tool_alias
from tests.native_adapter_support import FakeEvent, final_text
from tests.segmentation_stream_support import StreamingFixture, chunk, native_provider, text_chunks, USAGE


class NativeReplacementStreamTests(StreamingFixture, unittest.IsolatedAsyncioTestCase):
    async def start_routed_host(self):
        backup = native_provider()
        backup.provider_config["id"] = "native-backup"
        backup.provider_config["model"] = "backup-base"
        backup.model_name = "backup-base"
        primary = self.native.provider
        self.native.get_provider_by_id = lambda provider_id: {
            "native-model": primary, "native-backup": backup}.get(provider_id)
        backup_model = AstrBotTextProvider(self.native, bridge=self.bridge,
            binding=ProviderBinding("model.text", "backup", "4.27.2", provider_fingerprint(backup)),
            provider_id="native-backup", version="4.27.2", provider_type=ProviderOpenAIOfficial,
            function_tool_type=FunctionTool, tool_set_type=ToolSet,
            tariff=UsageTariff(3000000, 1000000, 5000000), maximum_output_tokens=100,
            streaming=True)
        rules = json.dumps([{"id": "private", "provider_id": "backup", "model": "creative",
                             "keywords": ["private"]}])
        self.profiles = (replace(self.profiles[0], replacement_rules=rules,
                                 capabilities=("text", "tools")),)
        self.registry = FieldRegistry(version="host.v1", fields=configuration_fields(self.profiles))
        host = await self.start(self.host(event_port=self.bridge.ports, identity_port=self.bridge.ports,
            role_port=self.bridge.ports, profiles=self.profiles, registry=self.registry,
            providers=(self.native_model.local_provider(), backup_model.local_provider()),
            sender=self.native_sender.local_sender(),
            budget=BudgetPolicy(*(Amount(10**8, 10**9) for _ in range(5))),
            policy=ConversationPolicy(0, 0, 180, 0), segmentation=SegmentationPolicy(enabled=True)))
        return host, backup

    def sent_texts(self):
        return [params["message"][0]["data"]["text"]
                for _, params in self.native.platform.client._api._wsr_api.calls]

    async def test_replacement_stream_tool_continuation_and_segments_share_one_route(self):
        host, backup = await self.start_routed_host()
        waiting, release = asyncio.Event(), asyncio.Event()

        async def pause():
            waiting.set()
            await release.wait()

        async def respond(payload):
            if not any(message["role"] == "tool" for message in payload["messages"]):
                return [chunk(tools=[dict(index=0, id="read", type="function",
                    function=dict(name=tool_alias("memo.list"), arguments="{}"))]),
                    chunk(finish="tool_calls"), chunk(usage=USAGE)]
            pieces = text_chunks(final_text(f"甲。\n{LLM_SEGMENT_MARKER}\n乙。"))
            return pieces[:-2] + [pause] + pieces[-2:]

        backup.client.state.behavior = respond
        snapshot = await self.capture(FakeEvent(self.native, text="private 便签"))
        batch = host.receive(snapshot).unwrap()
        app = host.application
        await asyncio.wait_for(waiting.wait(), 3)
        self.assertEqual(self.sent_texts(), [])
        self.assertEqual(app.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ?", (batch,)), ())
        release.set()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(self.sent_texts(), ["甲。\n", "乙。"])
        self.assertEqual([call["model"] for call in backup.client.state.calls], ["creative", "creative"])
        self.assertTrue(all(call["stream"] for call in backup.client.state.calls))
        self.assertEqual(primary_calls := self.native.provider.client.state.calls, [])
        self.assertEqual(backup.get_model(), "backup-base")
        self.assertEqual([row["actual_cost"] for row in app.runtime.read_all(
            "SELECT actual_cost FROM model_calls ORDER BY position", ())], [120, 120])
        plan = json.loads(app.runtime.read_one("SELECT plan_json FROM model_requests", ())["plan_json"])
        self.assertEqual(plan["replacement"]["rule_id"], "private")

    async def test_explicit_nonstream_setting_overrides_replacement_default(self):
        host, backup = await self.start_routed_host()
        app = host.application
        first = await self.capture(FakeEvent(self.native, event_id="first", text="ordinary"))
        first_batch = host.receive(first).unwrap()
        self.assertEqual((await self.done(app, first_batch))["state"], "complete")
        manager = ReplyManagement(app, self.context(app, first_batch))
        status = manager.status(self.core).unwrap()
        manager.configure(self.core, {"operation_key": "explicit-nonstream",
            "edit_token": status["edit_token"], "changes": {"streaming": False}}).unwrap()
        backup.client.state.text = final_text("按会话设置非流式回复。")
        second = await self.capture(FakeEvent(self.native, event_id="second", text="private 请求"))
        batch = host.receive(second).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual([call["stream"] for call in backup.client.state.calls], [False])
        self.assertEqual(backup.client.state.calls[0]["model"], "creative")
        captured = json.loads(app.messages.batch(batch)["contributions_json"])["reply_settings"]
        self.assertTrue(captured["streaming_explicit"])
        self.assertFalse(captured["settings"]["streaming"])
