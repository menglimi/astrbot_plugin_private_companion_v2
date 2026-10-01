"""Imported only by run_native_contracts after its isolation guards are active."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import inspect
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from aiocqhttp.api_impl import ResultStore, WebSocketReverseApi
from astrbot import __version__
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.message.components import Plain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
import httpx
from openai import AsyncOpenAI

from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.adapters.astrbot.native import HostAccount, HostPersona, NativePrivateBridge, persona_instruction
from companion_v2.adapters.astrbot.onebot import OneBotPrivateSender
from companion_v2.adapters.astrbot.provider import AstrBotTextProvider, UsageTariff
from companion_v2.adapters.astrbot.staging import AstrBotStagingSession, NativeAdapterTypes, StagingProfile
from companion_v2.adapters.astrbot.staging_bootstrap import AstrBotStagingBootstrap
from companion_v2.adapters.astrbot.staging_config import (
    DELIVERY_CAPABILITY,
    DELIVERY_GRANT_ID,
    StagingConfiguration,
)
from companion_v2.conversation.flow import ConversationPolicy
from companion_v2.execution.models import TaskContext, digest
from companion_v2.identity_policy.personas import RuntimeIdentity
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import Amount, BudgetPolicy
from companion_v2.model_gateway.failures import ModelFailure
from companion_v2.storage.runtime import StorageRuntime
from tests.native_adapter_support import NativeFixture, final_text
from tests.staging_bootstrap_support import database_contents, synthetic_configuration
from tests.test_management_access import INSTALLATION, NOW, ROLE


class MemoryPeer:
    def __init__(self):
        self.calls = []
        self.reply = {"status": "ok", "retcode": 0, "data": {"message_id": 987}}

    async def send(self, text):
        call = json.loads(text)
        self.calls.append(call)
        # The actual API installs ResultStore's waiter after send() returns.
        if self.reply is not None:
            asyncio.get_running_loop().call_soon(ResultStore.add, {**deepcopy(self.reply), "echo": call["echo"]})


class NativePersonaResolver:
    """Small resolver facade; the event/provider/platform classes remain native.

    PersonaManager imports the full AstrBot star graph and is intentionally not
    loaded by this contract harness. Its already-tested selection result is the
    only host value the V2 bridge consumes here.
    """
    def __init__(self, persona):
        self.persona = persona
        self.forced = None

    async def resolve_selected_persona(self, **_):
        selected = self.forced or self.persona["name"]
        persona = self.persona if selected == self.persona["name"] else None
        return selected, persona, self.forced, False


class NativeContractTests(NativeFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.peer = MemoryPeer()
        clients = {"100": self.peer, "101": MemoryPeer()}
        self.native.platform.metadata = PlatformMetadata("aiocqhttp", "isolated fixture", "qq-main")
        self.native.platform.client = NS(_wsr_api_clients=clients,
            _api=NS(_wsr_api=WebSocketReverseApi(clients, set(), 0.02)))
        self.native.persona_manager = NativePersonaResolver(self.native.persona)
        self.bridge = NativePrivateBridge(self.native, version=__version__, event_type=AiocqhttpMessageEvent,
            installation_id=INSTALLATION, host_id="host", identities=self.identity,
            accounts=(HostAccount("qq-main", "100", "bot-a"),),
            personas=(HostPersona("bot-a", "original", ROLE, digest(persona_instruction(self.native.persona))),))
        self.http_calls = []
        self.http_status = 200
        self.model_behavior = None
        self.native.provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
        self.native.provider.provider_config = {"id": "native-model", "type": "openai_chat_completion",
            "model": "fixture", "custom_extra_body": {"temperature": 0.2}}
        self.native.provider.model_name = "fixture"
        self.native.provider.reasoning_key = "reasoning_content"
        self.http_client = httpx.AsyncClient(transport=httpx.MockTransport(self.http_reply))
        self.sdk_client = AsyncOpenAI(api_key="isolated-test-key", base_url="https://fixture.invalid/v1",
            max_retries=2, http_client=self.http_client)
        self.addAsyncCleanup(self.sdk_client.close)
        self.native.provider.client = self.sdk_client
        self.native.provider.default_params = inspect.signature(self.sdk_client.chat.completions.create).parameters.keys()
        self.native_model = AstrBotTextProvider(self.native, bridge=self.bridge, binding=self.providers[0].binding,
            provider_id="native-model", version=__version__, provider_type=ProviderOpenAIOfficial,
            function_tool_type=FunctionTool, tool_set_type=ToolSet, tariff=UsageTariff(2000000, 1000000, 4000000),
            maximum_output_tokens=100)
        self.native_sender = OneBotPrivateSender(self.bridge, binding=self.sender.binding, version=__version__,
            reverse_api_type=WebSocketReverseApi, authorize=lambda: None, now=self.clock.now)

    async def http_reply(self, request):
        payload = json.loads(request.content)
        self.http_calls.append(payload)
        if self.http_status != 200:
            return httpx.Response(self.http_status, json={"error": {"message": "isolated service unavailable", "type": "fixture"}})
        result = {"id": "native-response-1", "object": "chat.completion", "created": 1, "model": "fixture",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": final_text()}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40, "prompt_tokens_details": {"cached_tokens": 10}}}
        if self.model_behavior:
            self.model_behavior(payload, result)
        return httpx.Response(200, json=result)

    def event(self, identifier="event-1", **_):
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "100"
        message.sender = MessageMember("200", "arbitrary nickname")
        message.message_id = identifier
        message.message = [Plain("你好")]
        message.message_str = "你好"
        message.raw_message = {"self_id": 100, "user_id": 200, "message_id": identifier}
        message.timestamp = int(NOW.timestamp())
        event = AiocqhttpMessageEvent("你好", message, self.native.platform.meta(), "200", self.native.platform.client)
        event.created_at = NOW.timestamp()
        return event

    async def capture(self, event=None):
        return await super().capture(event or self.event())

    async def test_installed_events_sdk_tools_and_websocket_complete_one_chain(self):
        snapshot = await self.capture()
        def tools(payload, result):
            if not any(m["role"] == "tool" for m in payload["messages"]):
                result["choices"][0].update(finish_reason="tool_calls", message={"role": "assistant", "content": None,
                    "tool_calls": [{"id": "native-call-1", "type": "function", "function": {
                        "name": tool_alias("memo.list"), "arguments": "{}"}}]})
        self.model_behavior = tools
        host = await self.setup_host()
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "complete")
        self.assertEqual(len(self.http_calls), 2)
        self.assertEqual(self.sdk_client.max_retries, 2)
        self.assertFalse(self.sdk_client.is_closed())
        self.assertEqual(self.http_calls[0]["max_tokens"], 100)
        self.assertEqual(self.http_calls[0]["messages"][0]["content"], snapshot.instruction)
        self.assertEqual(self.peer.calls[0]["params"]["self_id"], "100")
        self.assertEqual(self.peer.calls[0]["params"]["user_id"], 200)
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(len(host.application.messages.history(self.context(host.application, batch)).unwrap()["items"]), 1)

    async def test_real_sdk_and_host_retry_layers_make_only_one_request_on_503(self):
        envelope = await self.envelope()
        self.http_status = 503
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.failure, ModelFailure.TRANSPORT)
        self.assertIsNone(response.usage)
        self.assertEqual(len(self.http_calls), 1)

    async def test_native_parser_default_usage_is_not_reported_as_real_zero(self):
        envelope = await self.envelope()
        def no_usage(payload, result): result.pop("usage")
        self.model_behavior = no_usage
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "generated")
        self.assertIsNone(response.usage)

    async def test_native_parser_argument_repair_cannot_trigger_zero_argument_tool(self):
        from companion_v2.model_gateway.models import ToolSpec
        envelope = await self.envelope(tools=(ToolSpec("memo.list", "list", '{"type":"object"}'),))
        def invalid(payload, result):
            result["choices"][0].update(finish_reason="tool_calls", message={"role": "assistant", "content": None,
                "tool_calls": [{"id": "invalid-1", "type": "function", "function": {
                    "name": tool_alias("memo.list"), "arguments": "{invalid"}}]})
        self.model_behavior = invalid
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.failure, ModelFailure.WIRE_DECODE)
        self.assertEqual(response.tool_calls, ())
        self.assertEqual(response.usage, Amount(40, 90))

    async def test_host_empty_result_keeps_usage_even_when_native_parser_raises(self):
        envelope = await self.envelope()
        def empty(payload, result): result["choices"] = []
        self.model_behavior = empty
        response = await self.native_model.generate(envelope)
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.failure, ModelFailure.NATIVE_PARSE)
        self.assertEqual(response.usage, Amount(40, 90))
        self.assertEqual(len(self.http_calls), 1)

    async def test_reverse_websocket_timeout_stays_unknown_without_repeat(self):
        snapshot = await self.capture()
        self.peer.reply = None
        host = await self.setup_host()
        batch = host.receive(snapshot).unwrap()
        self.assertEqual((await self.done(host.application, batch))["state"], "blocked")
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(host.application.messages.history(self.context(host.application, batch)).unwrap()["items"], [])
        self.assertEqual(ResultStore._futures, {})

    async def test_native_session_forced_persona_cannot_fall_back_to_default_role(self):
        self.native.persona_manager.forced = "different"
        result = await self.bridge.capture(self.event())
        self.assertEqual(result.failure.code, "host_persona_unmapped")
        self.assertEqual(self.http_calls, [])
        self.assertEqual(self.peer.calls, [])

    async def staging_session(self, *, mode="preview", runtime=None, profile=None):
        if profile is None:
            snapshot = await self.capture()
            self.personas.register_route(snapshot.route, observed_at=NOW)
            actor = self.identity.resolve_authenticated(snapshot.principal, observed_at=NOW).unwrap()
            role = self.personas.resolve(snapshot.route.scope, observed_at=NOW).unwrap().binding
            profile = StagingProfile(TaskContext(actor, role, snapshot.recipients),
                RuntimeIdentity("companion", "native-staging-1", "astrbot", "host"),
                HostPersona("bot-a", "original", ROLE, digest(snapshot.instruction)), "native-model",
                UsageTariff(2000000, 1000000, 4000000), BudgetPolicy(*(Amount(10**8, 10**9) for _ in range(5))),
                "根据原角色和当前资料回复。", delivery_mode=mode, max_output_tokens=100,
                policy=ConversationPolicy(0, 0, 180, 0))
        session = AstrBotStagingSession(runtime or self.runtime, self.native, profile=profile,
            native_types=NativeAdapterTypes(__version__, AiocqhttpMessageEvent, ProviderOpenAIOfficial,
                FunctionTool, ToolSet, WebSocketReverseApi), now=self.clock.now)
        if mode == "onebot_private" and not any(
            grant.grant_id == DELIVERY_GRANT_ID for grant in self.identity.snapshot().grants
        ):
            self.identity.issue_grant(
                grant_id=DELIVERY_GRANT_ID,
                subject=session.profile.target.actor.subject,
                scope=session.profile.target.scope,
                capability=DELIVERY_CAPABILITY,
                tier=AuthorizationTier.STANDARD,
                valid_from=NOW,
                expires_at=NOW + timedelta(hours=1),
                expected_revision=self.identity.revision,
            )
        self.addAsyncCleanup(session.close)
        return session

    async def test_native_staging_preview_adopts_saved_config_without_platform_send(self):
        session = await self.staging_session()
        configuration = session.application.configuration
        snapshot = configuration.read(session.profile.target.actor, target=session.config_target,
            group_id=session.model_profile.group, observed_at=NOW).unwrap()
        configuration.patch(session.profile.target.actor, target=session.config_target,
            group_id=session.model_profile.group, expected_edit_token=snapshot.edit_token,
            operation=self.operation(session.profile.target.scope),
            changes={session.model_profile.group + ".max_output_tokens": 35}, observed_at=NOW).unwrap()
        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        self.assertNotEqual(session.inspect().unwrap()["configuration_application"], "applied")
        batch = (await session.receive(self.event())).unwrap()
        await self.done(session.application, batch)
        report = session.inspect(batch).unwrap()
        self.assertEqual(self.http_calls[0]["max_tokens"], 35)
        self.assertEqual(report["configuration_application"], "applied")
        self.assertEqual(report["model"]["transport"], "astrbot_openai")
        self.assertEqual(report["model"]["calls"][0]["actual_tokens"], 40)
        self.assertTrue(report["preview_ready"])
        self.assertFalse(report["confirmed_delivery"])
        self.assertEqual(session.preview(batch).unwrap()["parts"][0]["text"], "我在这里。")
        self.assertEqual(self.peer.calls, [])
        self.assertEqual(session.application.messages.history(session.profile.target).unwrap()["items"], [])

    async def test_native_staging_sender_keeps_message_id_and_known_usage(self):
        session = await self.staging_session(mode="onebot_private")
        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        batch = (await session.receive(self.event())).unwrap()
        await self.done(session.application, batch)
        report = session.inspect(batch).unwrap()
        self.assertTrue(report["confirmed_delivery"])
        self.assertTrue(report["delivery_receipts"][0]["platform_ref"].endswith(":987"))
        self.assertEqual(report["model"]["calls"][0]["actual_cost_microusd"], 90)
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(len(self.http_calls), 1)

    async def test_native_staging_timeout_survives_reopen_without_retry_or_new_spend(self):
        self.peer.reply = None
        session = await self.staging_session(mode="onebot_private")
        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        batch = (await session.receive(self.event())).unwrap()
        await self.done(session.application, batch)
        before = session.inspect(batch).unwrap()
        self.assertEqual(before["delivery_receipts"][0]["state"], "unknown")
        await session.close()
        other = await self.staging_session(runtime=self.open_runtime(), profile=replace(session.profile,
            runtime_identity=replace(session.profile.runtime_identity, runtime_instance_id="native-staging-2")))
        (await other.start(expected_task_generation=1, expected_model_generation=1)).unwrap()
        self.assertEqual((await other.receive(self.event())).unwrap(), batch)
        report = other.inspect(batch).unwrap()
        self.assertEqual(report["delivery_receipts"], before["delivery_receipts"])
        self.assertEqual(report["model"]["calls"], before["model"]["calls"])
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(len(self.http_calls), 1)
        self.assertEqual(ResultStore._futures, {})

    def configured_bootstrap(self, *, mode="preview"):
        # NativeFixture's original store already contains management data. The
        # trusted first-install path must receive a separate, empty test store.
        runtime = StorageRuntime.open(data_root=self.root.parent / "bootstrap-data", installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        config = StagingConfiguration.parse(json.dumps(synthetic_configuration(self.native, delivery_mode=mode).document()))
        return AstrBotStagingBootstrap(runtime, self.native, configuration=config,
            native_types=NativeAdapterTypes(__version__, AiocqhttpMessageEvent, ProviderOpenAIOfficial,
                FunctionTool, ToolSet, WebSocketReverseApi), now=self.clock.now)

    async def test_native_config_bootstrap_prepares_preview_without_implicit_network(self):
        bootstrap = self.configured_bootstrap()
        (await bootstrap.initialize()).unwrap()
        before = database_contents(bootstrap.runtime)
        session = bootstrap.load(runtime_instance_id="native-config-1").unwrap()
        self.addAsyncCleanup(session.close)
        self.assertEqual(database_contents(bootstrap.runtime), before)
        self.assertEqual(self.http_calls, [])
        self.assertEqual(self.peer.calls, [])
        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        batch = (await session.receive(self.event())).unwrap()
        await self.done(session.application, batch)
        self.assertEqual(session.preview(batch).unwrap()["parts"][0]["text"], "我在这里。")
        self.assertEqual(session.inspect(batch).unwrap()["model"]["calls"][0]["actual_tokens"], 40)
        self.assertEqual(len(self.http_calls), 1)
        self.assertEqual(self.peer.calls, [])
        await session.close()
        identity = bootstrap.identity
        identity.revoke_grant(bootstrap.grant_id("text"), revoked_at=NOW, expected_revision=identity.revision)
        before = database_contents(bootstrap.runtime)
        self.assertEqual((await bootstrap.initialize()).failure.code, "authorization_revoked")
        self.assertEqual(bootstrap.load(runtime_instance_id="native-config-2").failure.code, "authorization_revoked")
        self.assertEqual(database_contents(bootstrap.runtime), before)

    async def test_native_config_bootstrap_explicit_sender_records_native_ack(self):
        bootstrap = self.configured_bootstrap(mode="onebot_private")
        (await bootstrap.initialize()).unwrap()
        bootstrap.authorize_delivery(expires_at=NOW + timedelta(hours=1)).unwrap()
        session = bootstrap.load(runtime_instance_id="native-config-send").unwrap()
        self.addAsyncCleanup(session.close)
        (await session.start(expected_task_generation=0, expected_model_generation=0)).unwrap()
        batch = (await session.receive(self.event())).unwrap()
        await self.done(session.application, batch)
        report = session.inspect(batch).unwrap()
        self.assertTrue(report["confirmed_delivery"])
        self.assertTrue(report["delivery_receipts"][0]["platform_ref"].endswith(":987"))
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(len(self.http_calls), 1)
