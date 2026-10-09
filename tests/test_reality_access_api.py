"""Reality data reaches a V2 turn only after its own scoped consent."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from tests import test_astrbot_staging_host as support
from tests.multi_host_support import MultiFixture
from tests.native_adapter_support import completion, final_text
from tests.staging_bootstrap_support import wait_for_batch
from tests.test_reality_together_native import REALITY

from astrbot.api.web import PluginRequest, bind_request_context
from astrbot_host.management_identity import dashboard_operator
from astrbot_host.reality_access_api import CAPABILITY_PATHS, PREFIX
from astrbot_host.native_perception_api import PREFIX as PERCEPTION_PREFIX
from companion_v2.capabilities.reality_access import ACTION
from companion_v2.capabilities.reality_camera import ACTION as CAMERA_ACTION
from companion_v2.adapters.astrbot.model_wire import tool_alias
from companion_v2.execution.models import TaskContext
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from starlette.requests import Request


class MobileSnapshot:
    def __init__(self):
        self.users = []
        self.camera_calls = []
        self.device_calls = []
        self.mihome_web_api = self

    def extension_control_preflight(self, alias, *, native=False):
        if not native or alias != "desk-lamp":
            raise ValueError("device alias or native policy mismatch")
        return "private-device-id"

    async def extension_control_power(self, alias, is_on, *, native=False):
        if not native:
            raise ValueError("native policy required")
        self.device_calls.append((alias, is_on))
        return {"alias": alias, "is_on": is_on, "confirmed": True}

    def mobile_context(self, user_id):
        self.users.append(user_id)
        return {"available": True, "user_id": user_id,
                "location": {"available": True, "latitude": 31.23, "longitude": 121.474,
                             "place": {"matched": True, "name": "合成测试地点", "area_label": "测试市·测试区"},
                             "captured_at": 1790848200, "age_seconds": 1},
                "device": {"available": True, "app_state": "foreground", "battery_percent": 82,
                           "charging": True, "last_report_at": 1790848200, "age_seconds": 1},
                "activity": {"available": True, "display_title": "代码编辑器", "category": "work",
                             "last_report_at": 1790848200, "age_seconds": 1, "stale": False},
                "telemetry": {"available": True, "captured_at": 1790848200, "age_seconds": 1,
                              "measurements": [{"type": "heart_rate", "label": "心率", "value": 72,
                                                "unit": "次/分", "captured_at": 1790848200}],
                               "activity": {"state": "resting", "label": "休息"}}}

    async def camera_snapshot(self, user_id, purpose, *, source):
        self.camera_calls.append((user_id, purpose, source))
        return {"status": "success", "captured": True, "answer_available": True,
                "message": "已完成一次单帧观察",
                "observation": {"summary": "桌面上有打开的笔记本电脑。", "confidence": 0.9,
                                "visible_evidence": ["打开的笔记本电脑"],
                                "image_base64": "must-never-enter-V2"}}


def install_provider(native, root):
    mobile = MobileSnapshot()
    provider = REALITY.NativeRealityProvider(mobile, root / "provider")
    star = NS(root_dir_name=REALITY.PLUGIN_ID, version=REALITY.VERSION, activated=True,
              star_cls=NS(extension_api=NS(companion_v2_native=lambda: provider)))
    native.get_all_stars = lambda: (star,)
    return mobile


async def request_api(native, path=PREFIX, *, body=None, username="admin", query=b""):
    method = "GET" if body is None else "POST"
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    route = path if method == "GET" else path + "/configure"
    request = Request({"type":"http", "method":method, "path":route,
                       "headers":[], "query_string":query}, receive=receive)
    handler = next(handler for registered, handler, methods, _ in native.registered_web_apis
                   if registered == route and method in methods)
    with bind_request_context(PluginRequest(request, username=username)):
        return await handler()


def command(status, enabled, key):
    return {"edit_token":status["edit_token"], "enabled":enabled, "operation_key":key}


class RealityAccessSingleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="v2-reality-access-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = support.WebContext()
        self.mobile = install_provider(self.native, self.root)
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                           NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(staging={
            "profile_id": "reality-native-access", "delivery_mode": "onebot_private"}), self.root,
            native_types=types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()

    async def start(self):
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.authorize_delivery()).unwrap()
        (await self.controller.start()).unwrap()

    async def test_enable_read_model_context_revoke_and_replay(self):
        await self.start()
        initial = (await request_api(self.native))["data"]
        self.assertFalse(initial["invokable"])
        enabled_command = command(initial, True, "enable-first")
        enabled = await request_api(self.native, body=enabled_command)
        self.assertEqual(enabled["status"], "ok", enabled)
        self.assertTrue(enabled["data"]["status"]["invokable"])
        again = await request_api(self.native, body=enabled_command)
        self.assertTrue(again["data"]["replayed"], again)

        async def model(payload, tools):
            if not self.mobile.users:
                self.assertIn(tool_alias(ACTION), [tool.name for tool in tools.tools])
                return completion(tools=[NS(id="location-read", type="function",
                    function=NS(name=tool_alias(ACTION), arguments="{}"))])
            self.assertIn("snapshot", json.dumps(payload, ensure_ascii=False))
            self.assertIn("31.23", json.dumps(payload, ensure_ascii=False))
            return completion(final_text("我看到这次读取的结果了。"))

        self.native.provider.client.state.behavior = model
        event = support.FakeEvent(NS(platform=self.native.platform), event_id="location-event",
                                  sender="200", login="100", text="读一下我手机上报的位置")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        app = self.controller.session.application
        receipt = (await self.controller.inspect(batch)).unwrap()
        self.assertTrue(receipt["confirmed_delivery"], receipt)
        self.assertEqual(len(self.native.provider.client.state.calls), 2)
        sent = self.native.platform.client._api._wsr_api.calls
        self.assertEqual(len(sent), 1)
        self.assertIn("我看到这次读取的结果了。", json.dumps(sent[0], ensure_ascii=False))
        self.assertEqual(self.mobile.users, ["200"])
        invocation = app.runtime.read_one("SELECT state, action FROM extension_tool_invocations", ())
        self.assertEqual((invocation["state"], invocation["action"]), ("succeeded", ACTION))
        runtime = (await request_api(self.native, PERCEPTION_PREFIX + "/runtime"))["data"]
        self.assertEqual(runtime["reality"]["state"], "available")
        mobile = runtime["reality"]["snapshot"]
        self.assertEqual(mobile["location"]["label"], "测试市·测试区")
        self.assertNotIn("latitude", mobile["location"])
        self.assertEqual(mobile["health"]["measurements"][0]["label"], "心率")
        self.assertEqual(mobile["device"]["battery_percent"], 82)
        latest = (await request_api(self.native))["data"]
        revoked = await request_api(self.native, body=command(latest, False, "revoke-first"))
        self.assertFalse(revoked["data"]["status"]["invokable"], revoked)
        self.assertTrue(revoked["data"]["status"]["role_enabled"])
        hidden = (await request_api(self.native, PERCEPTION_PREFIX + "/runtime"))["data"]
        self.assertEqual(hidden["reality"]["state"], "blocked")
        self.assertNotIn("snapshot", hidden["reality"])
        old_enable = await request_api(self.native, body=enabled_command)
        self.assertTrue(old_enable["data"]["replayed"])
        self.assertFalse(old_enable["data"]["status"]["invokable"])
        stale = await request_api(self.native, body=command(latest, True, "stale-enable"))
        self.assertEqual(stale["data"]["code"], "reality_access_changed")
        fresh = (await request_api(self.native))["data"]
        restored = await request_api(self.native, body=command(fresh, True, "restore-first"))
        self.assertTrue(restored["data"]["status"]["invokable"], restored)
        (await self.controller.stop()).unwrap()
        (await self.controller.start()).unwrap()
        self.assertTrue((await request_api(self.native))["data"]["invokable"])

    async def test_authentication_identity_and_body_cannot_grant_device_control(self):
        await self.start()
        initial = (await request_api(self.native))["data"]
        body = command(initial, True, "enable-safe")
        for username in (None, "", "api_key:synthetic"):
            denied = await request_api(self.native, body=body, username=username)
            self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        denied = await request_api(self.native, query=b"target_id=someone-else")
        self.assertEqual(denied["data"]["code"], "reality_request_invalid")
        denied = await request_api(self.native, body={**body, "capability_id":"reality.device.control"})
        self.assertEqual(denied["data"]["code"], "reality_request_invalid")
        enabled = await request_api(self.native, body=body)
        self.assertEqual(enabled["status"], "ok", enabled)
        app = self.controller.session.application
        self.assertEqual([tool.action for tool in app.external.catalog_for(self.controller.session.profile.target)],
                         [ACTION])
        await self.controller.terminate()
        self.assertFalse(any(path.startswith(PREFIX) for path, *_ in self.native.registered_web_apis))

    async def test_read_only_status_does_not_acquire_or_read_location(self):
        await self.start()
        for _ in range(2):
            status = await request_api(self.native)
            self.assertFalse(status["data"]["installed"], status)
        self.assertEqual(self.mobile.users, [])

    async def test_view_only_operator_gets_read_only_status_and_cannot_submit_consent(self):
        await self.start()
        operator = dashboard_operator(self.controller.runtime, "admin", at=support.NOW)
        original = self.controller.session.profile.target
        target = TaskContext(operator, original.role_binding, AudienceRef(original.scope, (operator.subject,)))
        self.controller.session.profile = NS(target=target)
        policy = ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
            expected_revision=policy.revision, observed_at=support.NOW)

        with patch.object(self.controller.session.application.tasks, "authorize_context",
                          return_value=Outcome.success(True)):
            readonly = await request_api(self.native)
            self.assertEqual(readonly["status"], "ok", readonly)
            self.assertFalse(readonly["data"]["can_manage"])
            for suffix in CAPABILITY_PATHS.values():
                status = await request_api(self.native, PREFIX + suffix)
                self.assertEqual(status["status"], "ok", status)
                self.assertFalse(status["data"]["can_manage"], status)
            denied = await request_api(self.native, body=command(
                readonly["data"], True, "read-only-enable"))
        self.assertEqual(denied["data"]["code"], "core_access_required")

    async def test_all_native_actions_have_fixed_scoped_access_routes(self):
        await self.start()
        paths = {action: PREFIX + suffix for action, suffix in CAPABILITY_PATHS.items()}
        self.assertEqual(len(paths), 8)
        enabled_actions = set()
        for index, (action, path) in enumerate(paths.items()):
            with self.subTest(action=action):
                response = await request_api(self.native, path)
                self.assertEqual(response["status"], "ok", response)
                self.assertEqual(response["data"]["action"], action)
                self.assertFalse(response["data"]["invokable"])
                self.assertTrue(response["data"]["can_manage"])
                granted = await request_api(self.native, path, body=command(
                    response["data"], True, f"enable-action-{index}"))
                self.assertTrue(granted["data"]["status"]["invokable"], granted)
                enabled_actions.add(action)
                catalog = {tool.action for tool in self.controller.session.application.external.catalog_for(
                    self.controller.session.profile.target)}
                self.assertEqual(catalog, enabled_actions)

                current = (await request_api(self.native, path))["data"]
                revoked = await request_api(self.native, path, body=command(
                    current, False, f"revoke-action-{index}"))
                self.assertFalse(revoked["data"]["status"]["invokable"], revoked)
                enabled_actions.remove(action)
                catalog = {tool.action for tool in self.controller.session.application.external.catalog_for(
                    self.controller.session.profile.target)}
                self.assertEqual(catalog, enabled_actions)

    async def test_device_control_requires_its_own_consent_and_reaches_the_native_tool(self):
        await self.start()
        path = PREFIX + CAPABILITY_PATHS["reality.device.control"]
        initial = (await request_api(self.native, path))["data"]
        self.assertFalse(initial["invokable"])
        enabled = await request_api(self.native, path, body=command(initial, True, "enable-device-control"))
        self.assertTrue(enabled["data"]["status"]["invokable"], enabled)
        self.assertFalse((await request_api(self.native, PREFIX))["data"]["consented"])
        self.assertEqual([tool.action for tool in self.controller.session.application.external.catalog_for(
            self.controller.session.profile.target)], ["reality.device.control"])

        async def model(payload, tools):
            if not self.mobile.device_calls:
                self.assertIn(tool_alias("reality.device.control"), [tool.name for tool in tools.tools])
                return completion(tools=[NS(id="device-switch", type="function",
                    function=NS(name=tool_alias("reality.device.control"), arguments=json.dumps(
                        {"alias":"desk-lamp", "is_on":True})))])
            self.assertIn("confirmed", json.dumps(payload, ensure_ascii=False))
            return completion(final_text("书桌灯已经收到开启确认。"))

        self.native.provider.client.state.behavior = model
        event = support.FakeEvent(NS(platform=self.native.platform), event_id="device-control-event",
                                  sender="200", login="100", text="打开书桌灯")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        receipt = (await self.controller.inspect(batch)).unwrap()
        self.assertTrue(receipt["confirmed_delivery"], receipt)
        sent = self.native.platform.client._api._wsr_api.calls
        self.assertEqual(len(sent), 1)
        self.assertIn("书桌灯已经收到开启确认。", json.dumps(sent[0], ensure_ascii=False))
        self.assertEqual(self.mobile.device_calls, [("desk-lamp", True)])
        invocation = self.controller.session.application.runtime.read_one(
            "SELECT state, action FROM extension_tool_invocations", ())
        self.assertEqual((invocation["state"], invocation["action"]), ("succeeded", "reality.device.control"))

        current = (await request_api(self.native, path))["data"]
        revoked = await request_api(self.native, path, body=command(current, False, "revoke-device-control"))
        self.assertFalse(revoked["data"]["status"]["invokable"])
        self.assertEqual(self.controller.session.application.external.catalog_for(
            self.controller.session.profile.target), ())
        self.assertEqual(self.mobile.device_calls, [("desk-lamp", True)])

    async def test_camera_has_independent_consent_and_only_recent_sanitized_private_result(self):
        await self.start()
        camera_path = PREFIX + "/camera"
        initial = (await request_api(self.native, camera_path))["data"]
        self.assertEqual(initial["action"], CAMERA_ACTION)
        self.assertFalse(initial["invokable"])
        enabled = await request_api(self.native, camera_path,
                                    body=command(initial, True, "enable-camera"))
        self.assertTrue(enabled["data"]["status"]["invokable"], enabled)
        self.assertFalse((await request_api(self.native))["data"]["consented"])
        model_payloads = []

        async def model(payload, tools):
            model_payloads.append(payload)
            alias = tool_alias(CAMERA_ACTION)
            if not self.mobile.camera_calls:
                self.assertIn(alias, [tool.name for tool in tools.tools])
                return completion(tools=[NS(id="camera-read", type="function",
                    function=NS(name=alias, arguments=json.dumps(
                        {"purpose":"看看我现在在做什么"}, ensure_ascii=False)))])
            return completion(final_text("我看到桌面上有一台打开的笔记本电脑。"))

        self.native.provider.client.state.behavior = model
        event = support.FakeEvent(NS(platform=self.native.platform), event_id="camera-event",
                                  sender="200", login="100", text="请看看摄像头现在拍到什么")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        app = self.controller.session.application
        batch_state = app.runtime.read_one("SELECT state FROM conversation_batches WHERE batch_id = ?", (batch,))
        invocation = app.runtime.read_one(
            "SELECT state, error_code, action FROM extension_tool_invocations WHERE batch_id = ?", (batch,))
        flow = app.runtime.read_one("SELECT state, reason FROM conversation_flows WHERE batch_id = ?", (batch,))
        generation = app.runtime.read_one("""SELECT t.state, t.record_json FROM conversation_batches b
            JOIN execution_tasks t ON t.task_id = b.generation_task_id WHERE b.batch_id = ?""", (batch,))
        tool_calls = app.runtime.read_all("""SELECT state, action, result_json FROM conversation_tool_calls
            WHERE task_id = (SELECT generation_task_id FROM conversation_batches WHERE batch_id = ?)""", (batch,))
        diagnostic = {"flow": dict(flow or {}), "generation": dict(generation or {}),
                      "invocation": dict(invocation or {}), "tool_calls": [dict(item) for item in tool_calls],
                      "camera_calls": self.mobile.camera_calls}
        self.assertEqual(batch_state["state"], "ready", diagnostic)
        receipt = (await self.controller.inspect(batch)).unwrap()
        self.assertTrue(receipt["confirmed_delivery"], receipt)
        sent = self.native.platform.client._api._wsr_api.calls
        self.assertEqual(len(sent), 1)
        self.assertIn("我看到桌面上有一台打开的笔记本电脑。", json.dumps(sent[0], ensure_ascii=False))
        request_context = json.loads(next(message["content"] for message in model_payloads[-1]["messages"]
                                          if message["role"] == "user"))
        camera_material = next(material for material in request_context["materials"]
                               if material["owner"] == "reality.native"
                               and material["purpose"] == "tool_source:camera-read")
        camera_result = json.loads(camera_material["text"])["native"]["result"]
        self.assertEqual(camera_result["observation"]["summary"], "桌面上有打开的笔记本电脑。")
        self.assertNotIn("must-never-enter-V2", camera_material["text"])
        self.assertEqual(self.mobile.users, [])
        self.assertEqual(self.mobile.camera_calls,
                         [("200", "看看我现在在做什么", "assistant_tool_private")])

        runtime = (await request_api(self.native, PERCEPTION_PREFIX + "/runtime"))["data"]
        camera = runtime["camera"]
        self.assertEqual(camera["state"], "available")
        self.assertEqual(camera["observation"]["summary"], "桌面上有打开的笔记本电脑。")
        self.assertNotIn("image_base64", json.dumps(camera, ensure_ascii=False))

        current = (await request_api(self.native, camera_path))["data"]
        revoked = await request_api(self.native, camera_path,
                                    body=command(current, False, "revoke-camera"))
        self.assertFalse(revoked["data"]["status"]["invokable"])
        hidden = (await request_api(self.native, PERCEPTION_PREFIX + "/runtime"))["data"]["camera"]
        self.assertEqual(hidden["state"], "blocked")
        self.assertNotIn("observation", hidden)

        mobile = (await request_api(self.native))["data"]
        mobile_enabled = await request_api(self.native, body=command(mobile, True, "enable-mobile"))
        self.assertTrue(mobile_enabled["data"]["status"]["invokable"])
        self.assertFalse((await request_api(self.native, camera_path))["data"]["consented"])

    async def test_camera_is_not_dispatched_without_an_explicit_current_request(self):
        await self.start()
        camera_path = PREFIX + "/camera"
        initial = (await request_api(self.native, camera_path))["data"]
        enabled = await request_api(self.native, camera_path,
                                    body=command(initial, True, "enable-camera-without-request"))
        self.assertTrue(enabled["data"]["status"]["invokable"], enabled)
        model_rounds = 0
        tool_catalogs = []

        async def model(payload, tools):
            nonlocal model_rounds
            model_rounds += 1
            tool_catalogs.append([tool.name for tool in tools.tools])
            if model_rounds == 1:
                return completion(tools=[NS(id="camera-without-request", type="function",
                    function=NS(name=tool_alias(CAMERA_ACTION), arguments=json.dumps(
                        {"purpose":"看看我现在在做什么"}, ensure_ascii=False)))])
            return completion(final_text("仅凭这条消息无法判断你现在在做什么。"))

        self.native.provider.client.state.behavior = model
        event = support.FakeEvent(NS(platform=self.native.platform), event_id="camera-no-request",
                                  sender="200", login="100", text="你知道我现在在做什么吗")
        batch = (await self.controller.receive_claimed(event)).unwrap()
        await wait_for_batch(self.controller.session, batch)
        app = self.controller.session.application
        self.assertEqual(app.messages.batch(batch)["state"], "ready")
        self.assertIn(tool_alias(CAMERA_ACTION), tool_catalogs[0])
        self.assertEqual(self.mobile.camera_calls, [])
        self.assertEqual(self.mobile.users, [])
        runtime = (await request_api(self.native, PERCEPTION_PREFIX + "/runtime"))["data"]
        self.assertEqual(runtime["camera"]["state"], "ready")
        self.assertNotIn("observation", runtime["camera"])


class RealityAccessMultiTests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    async def test_bot_and_persona_scopes_remain_independent_after_revocation(self):
        mobile = install_provider(self.native, self.root)
        self.controller.register_routes()
        await self.start_host()
        roles = self.controller.web_api.target_inventory()
        paths = { (target["target_id"], role["role_id"]): role["reality_access_api"]
                 for target in roles for role in target["roles"] }
        first = paths[("first", "role-a")]
        initial = (await request_api(self.native, first))["data"]
        enabled = await request_api(self.native, first, body=command(initial, True, "enable-first"))
        self.assertTrue(enabled["data"]["status"]["invokable"], enabled)
        for key in (("first", "role-b"), ("second", "role-a"), ("second", "role-b")):
            self.assertFalse((await request_api(self.native, paths[key]))["data"]["invokable"])
        second = paths[("second", "role-a")]
        second_status = (await request_api(self.native, second))["data"]
        enabled_second = await request_api(self.native, second,
            body=command(second_status, True, "enable-second"))
        self.assertTrue(enabled_second["data"]["status"]["invokable"], enabled_second)
        # A token from one Bot/role cannot grant the other path.
        wrong = await request_api(self.native, first,
            body=command(enabled_second["data"]["status"], False, "wrong-scope"))
        self.assertEqual(wrong["data"]["code"], "reality_access_changed")
        latest = (await request_api(self.native, first))["data"]
        revoked = await request_api(self.native, first, body=command(latest, False, "revoke-first"))
        self.assertFalse(revoked["data"]["status"]["invokable"])
        self.assertTrue((await request_api(self.native, second))["data"]["invokable"])
        self.assertEqual(mobile.users, [])
