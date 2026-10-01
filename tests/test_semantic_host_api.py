"""Semantic catalog through authenticated AstrBot Dashboard requests."""

import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from urllib.parse import urlencode

from astrbot.api.web import PluginRequest, bind_request_context
from PIL import Image
from starlette.requests import Request

from astrbot_host.management_identity import dashboard_operator
from astrbot_host.semantic_api import PREFIX
from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.execution.models import TaskContext, encode
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from tests import test_astrbot_staging_host as support
from tests.group_memory_management_support import GroupMemoryManagementFixture
from tests.native_adapter_support import completion, final_text
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_semantic_integration import SemanticPort


class VocabularyPort(SemanticPort):
    def __init__(self):
        super().__init__()
        self.analysis_calls = 0
        self.failures = 0

    async def analyze(self, identifier, prompt, images=()):
        self.analysis_calls += 1
        if self.failures:
            self.failures -= 1
            raise RuntimeError("analysis unavailable")
        return [{"term": "小灯", "meaning": "今晚集合", "usage": "群内约见", "evidence": [0]}]


class SemanticRequests:
    def register_semantic(self):
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler for path, handler, methods, _ in self.native.registered_web_apis}

    async def semantic_request(self, selection, *, action=None, username="admin", **values):
        query = urlencode({**selection, **values}) if action is None else ""
        body = json.dumps({**selection, "action": action, **values}, ensure_ascii=False).encode("utf-8") if action else b""
        method = "POST" if action else "GET"

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        native = Request({"type": "http", "method": method, "path": PREFIX,
                          "headers": [], "query_string": query.encode("utf-8")}, receive=receive)
        with bind_request_context(PluginRequest(native, username=username)):
            return await self.routes[(PREFIX, method)]()


class PrivateSemanticAPITests(SemanticRequests, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-semantic-api-")
        self.addCleanup(temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                          NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(), Path(temporary.name),
                                                          native_types=types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.selection = {"target_id": self.controller.settings.profile_id, "role_id": self.controller.settings.role_id}
        self.register_semantic()

    async def test_login_tier_config_cas_and_private_catalog_roundtrip(self):
        for username in (None, "", "api_key:synthetic"):
            denied = await self.semantic_request(self.selection, username=username)
            self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        self.assertEqual((await self.semantic_request(self.selection))["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.start()).unwrap()
        status = await self.semantic_request(self.selection)
        self.assertEqual(status["status"], "ok", status)
        self.assertTrue(status["data"]["selection_ready"])
        revision = status["data"]["settings"]["revision"]
        configured = await self.semantic_request(self.selection, action="configure",
                                                  changes={"vision_review": False,
                                                           "reactions_trigger_probability": 0.6,
                                                           "reactions_cooldown_seconds": 120,
                                                           "reactions_delivery_mode": "separate_before",
                                                           "reactions_image_format": "qq_emoji"}, revision=revision)
        self.assertEqual(configured["data"]["settings"]["revision"], revision + 1)
        self.assertEqual({key: configured["data"]["settings"][key] for key in (
            "reactions_trigger_probability", "reactions_cooldown_seconds",
            "reactions_delivery_mode", "reactions_image_format")}, {
            "reactions_trigger_probability": 0.6, "reactions_cooldown_seconds": 120,
            "reactions_delivery_mode": "separate_before", "reactions_image_format": "qq_emoji"})
        stale = await self.semantic_request(self.selection, action="configure",
                                             changes={"vision_review": True}, revision=revision)
        self.assertEqual(stale["data"]["code"], "semantic_conflict")

        output = io.BytesIO()
        Image.new("RGB", (3, 3), "red").save(output, format="PNG")
        content = output.getvalue()
        imported = await self.semantic_request(self.selection, action="import",
                                                content=base64.b64encode(content).decode("ascii"),
                                                metadata={"name": "抱抱", "description": "伸手安慰"})
        self.assertEqual(imported["status"], "ok", imported)
        item = imported["data"]["item"]
        listed = await self.semantic_request(self.selection, kind="reaction")
        self.assertEqual([row["id"] for row in listed["data"]["items"]], [item["id"]])
        detail = await self.semantic_request(self.selection, kind="reaction", id=item["id"])
        self.assertEqual(base64.b64decode(detail["data"]["image_url"].split(",", 1)[1]), content)
        edited = await self.semantic_request(self.selection, action="edit", kind="reaction", id=item["id"],
                                              revision=item["revision"], values={"intents": "安慰"}, enabled=True)
        self.assertEqual(edited["data"]["item"]["revision"], item["revision"] + 1)
        found = await self.semantic_request(self.selection, action="search", kind="reaction", query="抱抱")
        self.assertEqual([row["id"] for row in found["data"]["items"]], [item["id"]])

        operator = dashboard_operator(self.controller.runtime, "admin", at=support.NOW)
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
                        expected_revision=policy.revision, observed_at=support.NOW)
        self.assertEqual((await self.semantic_request(self.selection))["data"]["code"], "core_access_required")
        self.assertEqual((await self.semantic_request(self.selection, action="reindex"))["data"]["code"], "core_access_required")

    async def test_shutdown_unregisters_route_and_retained_handler_rejects_requests(self):
        (await self.controller.initialize_profile()).unwrap()
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.semantic_request(self.selection))["data"]["code"], "staging_host_terminated")


class GroupSemanticAPITests(SemanticRequests, GroupMemoryManagementFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.register_semantic()

    async def test_group_reaction_requires_scope_enablement(self):
        await self.start_host()
        context, _, _ = await self.conversation(remember=False, wording="说说今天的事")
        service = self.app.semantics
        settings = service.store.settings()
        self.assertTrue(settings["reactions_private_enabled"])
        self.assertFalse(service.reaction_enabled(context, settings))
        changed = service.store.configure({"reactions_group_enabled": True}, settings["revision"])
        self.assertTrue(service.reaction_enabled(context, changed))
        service.store.configure({"reactions_enabled": False}, changed["revision"])
        self.assertFalse(service.reaction_enabled(context, service.store.settings()))

    async def test_group_session_and_role_are_isolated(self):
        await self.start_host()
        selection = {"target_id": "group-a", "role_id": "role-a"}
        empty = await self.semantic_request(selection)
        self.assertFalse(empty["data"]["selection_ready"])
        context, _, _ = await self.conversation(remember=False, wording="这是本群的接头暗号")
        active = await self.semantic_request(selection, kind="slang")
        self.assertEqual(active["status"], "ok", active)
        self.assertTrue(active["data"]["selection_ready"], active)
        self.assertIn("300", active["data"]["sessions"])
        self.assertEqual(active["data"]["scope_kind"], "group")
        self.assertEqual((await self.semantic_request({**selection, "session_id": "missing"},
                                                       action="search", kind="slang", query="接头"))["data"]["code"],
                         "semantic_group_input_required")
        self.assertFalse((await self.semantic_request({"target_id": "group-b", "role_id": "role-a"}))["data"]["selection_ready"])
        self.assertEqual(context.scope.session_id, "300")
        other, _, _ = await self.conversation(remember=False, wording="仅在成员会话中出现", unique=True)
        self.assertEqual(other.scope.session_id, "201_300")
        sessions = (await self.semantic_request(selection))["data"]["sessions"]
        self.assertEqual(sessions[:2], ["201_300", "300"])
        selected = await self.semantic_request({**selection, "session_id": "201_300"})
        self.assertTrue(selected["data"]["selection_ready"])

    async def test_learning_retries_after_failure_and_source_withdrawal_hides_meaning(self):
        await self.start_host()
        port = VocabularyPort()
        port.failures = 1
        service = self.app.semantics
        service.gateway.port = port
        selection = {"target_id": "group-a", "role_id": "role-a"}
        await self.conversation(remember=False, wording="小灯是今晚集合的暗号")
        self.assertEqual(port.analysis_calls, 1)
        self.assertEqual((await self.semantic_request(selection, kind="slang"))["data"]["items"], [])
        context, batch, _ = await self.conversation(remember=False, wording="说小灯就是今晚集合")
        self.assertEqual(port.analysis_calls, 2)
        listed = await self.semantic_request(selection, kind="slang")
        self.assertEqual(listed["data"]["items"][0]["payload"]["meaning"], "今晚集合")
        result = await self.semantic_request(selection, action="search", kind="slang", query="小灯")
        self.assertEqual(len(result["data"]["items"]), 1)
        event = self.app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id=?", (batch,))
        self.app.withdraw(context, event[0]).unwrap()
        listed = await self.semantic_request(selection, kind="slang")
        self.assertFalse(listed["data"]["items"][0]["source_valid"])
        result = await self.semantic_request(selection, action="search", kind="slang", query="小灯")
        self.assertEqual(result["data"]["items"], [])
        current = service.store.settings()
        service.store.configure({"slang_learning": False}, current["revision"])
        next_context, next_batch, _ = await self.conversation(remember=False, wording="小灯是什么意思？")
        materials = self.app.messages._request(
            self.app.messages.batch(next_batch), next_context, self.clock.now()).context.materials
        self.assertFalse(any(m.purpose == "contextual_word_meanings" for m in materials))

    async def test_same_turn_correction_supersedes_old_search_and_context(self):
        await self.start_host()
        port = VocabularyPort()
        self.app.semantics.gateway.port = port
        await self.conversation(remember=False, wording="小灯代表今晚集合")

        async def model(payload, _):
            done = len([m for m in payload["messages"] if m["role"] == "tool"])
            if done < 2:
                action, arguments = [("slang.search", {"query": "小灯是什么意思"}),
                                     ("slang.learn", {"term": "小灯", "meaning": "提醒喝水",
                                                       "usage": "群内纠正", "input_handle": "group-input-1",
                                                       "correction": True})][done]
                return completion(tools=[NS(id="semantic-" + str(done), type="function",
                    function=NS(name=tool_alias(action), arguments=encode(arguments)))])
            return completion(final_text("按新说法理解。"))

        self.native.provider.client.state.behavior = model
        event = self.group_event(identifier="slang-correction", text="纠正：小灯是提醒喝水")
        result = await self.controller.receive_claimed(event)
        self.assertTrue(result.is_success, result.failure)
        batch = result.unwrap()
        await wait_for_batch(self.controller.session, batch)
        rows = self.app.tools._rows(batch)
        self.assertEqual([row["action"] for row in rows], ["slang.search", "slang.learn"])
        self.assertEqual([json.loads(row["result_json"])["state"] for row in rows], ["succeeded", "succeeded"])
        context = TaskContext.restore(json.loads(self.app.messages.batch(batch)["context_json"]))
        old = self.app.tools.semantic.validate(rows[0], context, json.loads(rows[0]["result_json"]))[0]
        self.assertEqual(old["state"], "superseded")
        materials = self.app.messages._request(self.app.messages.batch(batch), context, self.clock.now()).context.materials
        self.assertFalse(any(m.purpose == "contextual_word_meanings" and "今晚集合" in m.payload for m in materials))
        listed = await self.semantic_request({"target_id": "group-a", "role_id": "role-a"}, kind="slang")
        self.assertEqual(listed["data"]["items"][0]["payload"]["meaning"], "提醒喝水")
