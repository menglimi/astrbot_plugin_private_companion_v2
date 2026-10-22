"""The single cottage page manages internal services with Dashboard authority."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as support
from astrbot.api.web import PluginRequest, bind_request_context
from starlette.requests import Request
from astrbot_host.native_extension_api import PREFIX
from companion_v2.capabilities import CapabilityRepository


class NativeExtensionAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-native-api-")
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                          NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(),
            Path(self.temporary.name), native_types=types, now=lambda: support.NOW)
        self.controller.register_routes()
        self.routes = {(path, methods[0]): handler for path, handler, methods, _ in self.native.registered_web_apis}
        (await self.controller.initialize_profile()).unwrap()

    async def asyncTearDown(self):
        await self.controller.terminate()
        self.temporary.cleanup()

    async def call(self, path=PREFIX, *, body=None, username="admin", query=""):
        method = "GET" if body is None else "POST"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}
        req = Request({"type": "http", "method": method, "path": path,
                       "headers": [], "query_string": query.encode()}, receive=receive)
        with bind_request_context(PluginRequest(req, username=username)):
            return await self.routes[(path, method)]()

    async def enable(self, name):
        (await self.controller.start()).unwrap()
        registry = self.controller.native_extensions
        package = registry._lease(name).manifest.package
        CapabilityRepository(self.controller.runtime).acquire(extension_id=name,
            package_id=package.package_id, package_version=package.package_version,
            expected_revision=0, observed_at=support.NOW).unwrap()
        await registry.reconcile_service(name)
        await registry._lease(name).start()
        return registry.service(name)

    async def test_status_reads_offline_metadata_and_only_dashboard_can_save(self):
        reality = self.controller.native_extensions.service('reality')
        reality._reality_touch_query_audio_devices = lambda: self.fail('status must not scan devices')
        result = await self.call()
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(set(result["data"]["extensions"]), {"reality", "together", "game", "live"})
        self.assertIn("management", result["data"]["extensions"]["reality"])
        live = result["data"]["extensions"]["live"]
        self.assertFalse(live["management"]["connected"])
        for username in (None, "", "api_key:synthetic"):
            denied = await self.call(PREFIX + "/configure", body={"extension_id": "live",
                "updates": {"vts_port": 8002}, "revision": live["revision"]}, username=username)
            self.assertEqual(denied["data"]["code"], "dashboard_identity_required")
        saved = await self.call(PREFIX + "/configure", body={"extension_id": "live",
            "updates": {"vts_port": 8002}, "revision": live["revision"]})
        self.assertEqual(saved["status"], "ok", saved)
        self.assertEqual(saved["data"]["runtime"]["state"], "inactive")

    async def test_device_action_rejects_inactive_service(self):
        result = await self.call(PREFIX + "/action", body={"extension_id": "live",
            "action": "request_auth", "payload": {}})
        self.assertEqual(result["data"]["code"], "native_service_not_running")

    async def test_vts_authorization_and_hotkeys_use_internal_service_without_holding_reply_lock(self):
        service = await self.enable("live")
        async def request_token():
            self.assertFalse(self.controller._control_lock.locked())
            return "synthetic-private-token"
        service.vts.request_auth_token = request_token
        service.vts.authenticate = AsyncMock(return_value=True)
        service.vts.get_hotkeys = AsyncMock(return_value=[{"hotkeyID": "key-1", "name": "开心"}])
        authorized = await self.call(PREFIX + "/action", body={"extension_id": "live",
            "action": "request_auth", "payload": {}})
        self.assertEqual(authorized["status"], "ok", authorized)
        self.assertNotIn("synthetic-private-token", json.dumps(authorized))
        self.assertEqual(await service._load_token(), "synthetic-private-token")
        keys = await self.call(PREFIX + "/action", body={"extension_id": "live",
            "action": "list_hotkeys", "payload": {}})
        self.assertEqual(keys["data"]["management"]["hotkeys"][0]["name"], "开心")

    async def test_camera_confirmation_persists_for_only_the_selected_eligible_user(self):
        service = await self.enable("reality")
        service.authorized_user_ids.add("200")
        for user_id, confirmed in (("200", True), ("200", False)):
            result = await self.call(PREFIX + "/action", body={"extension_id": "reality",
                "action": "consent_camera", "payload": {"user_id": user_id, "confirmed": confirmed}})
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual(service._reality_touch_camera_consented(service._user(user_id)), confirmed)
            rows = result["data"]["management"]["users"]
            camera = next(row["camera"] for row in rows if row["user_id"] == user_id)
            self.assertEqual(camera["consented"], confirmed)
            self.assertEqual(camera["enabled"], confirmed)
        refused = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "consent_camera", "payload": {"user_id": "999", "confirmed": True}})
        self.assertEqual(refused["status"], "error")
        self.assertEqual(refused["message"], "camera_user_ineligible",
                         "the real Dashboard bridge forwards only message on rejection")
        self.assertIsNone(service._user("999", create=False))

    async def test_camera_only_user_policy_survives_snapshot_refresh_and_disk_reload(self):
        service = await self.enable("reality")
        service.authorized_user_ids.add("200")
        granted = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "consent_camera", "payload": {"user_id": "200", "confirmed": True}})
        self.assertEqual(granted["status"], "ok", granted)
        user = service._load_data()["users"]["200"]
        for field in ("umo", "reality_touch_consent", "reality_touch_policy", "wakeup_alarm"):
            self.assertFalse(user.get(field), field)
        saved = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "update_camera_policy", "payload": {"user_id": "200",
                "camera_enabled": True, "proactive_mode": "auto", "proactive_max_daily": -1}})
        self.assertEqual(saved["status"], "ok", saved)
        service.data = service._load_data()
        refreshed = await self.call()
        rows = refreshed["data"]["extensions"]["reality"]["management"]["users"]
        camera = next(row["camera"] for row in rows if row["user_id"] == "200")
        self.assertTrue(camera["consented"])
        self.assertTrue(camera["enabled"])
        self.assertEqual(camera["proactive_mode"], "auto")
        self.assertEqual(camera["proactive_max_daily"], -1)

    async def test_camera_policy_errors_keep_codes_through_message_only_bridge(self):
        service = await self.enable("reality")
        service.authorized_user_ids.add("200")
        command = {"extension_id": "reality", "action": "update_camera_policy",
                   "payload": {"user_id": "200", "camera_enabled": True}}
        missing = await self.call(PREFIX + "/action", body=command)
        self.assertEqual(missing["message"], "camera_user_not_configured")
        service._user("200")
        refused = await self.call(PREFIX + "/action", body=command)
        self.assertEqual(refused["message"], "camera_consent_required")
        self.assertEqual(refused["data"]["code"], refused["message"])
        self.assertFalse(service._reality_touch_camera_consented(service._user("200")))

    async def test_missing_mihome_is_unavailable_and_camera_consent_still_succeeds(self):
        service = await self.enable("reality")
        service.authorized_user_ids.add("200")
        with patch.object(service, "_mihome_api", return_value=None):
            status = await self.call()
            mi = status["data"]["extensions"]["reality"]["management"]["mihome"]
            self.assertIs(mi["available"], False)
            self.assertTrue(mi["reason"])
            login = await self.call(PREFIX + "/action", body={"extension_id": "reality",
                "action": "mihome_start_login", "payload": {}})
            self.assertEqual(login["message"], "native_mihome_unavailable")
            consent = await self.call(PREFIX + "/action", body={"extension_id": "reality",
                "action": "consent_camera", "payload": {"user_id": "200", "confirmed": True}})
            self.assertEqual(consent["status"], "ok", consent)
            self.assertTrue(consent["data"]["management"]["users"][0]["camera"]["consented"])

    async def test_camera_page_test_returns_only_an_ephemeral_preview(self):
        service = await self.enable("reality")
        service._reality_touch_camera_snapshot_for_user = AsyncMock(return_value={
            "status": "success", "message": "单帧分析完成", "captured": True,
            "observation": {"summary": "合成画面"}, "preview_data_url": "data:image/jpeg;base64,AA=="})

        response = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "test_camera", "payload": {"user_id": "200", "purpose": "拓展页摄像头单帧测试"}})

        self.assertEqual(response["status"], "ok", response)
        data = response["data"]
        self.assertTrue(data["result"]["captured"])
        self.assertNotIn("preview_data_url", data["result"])
        self.assertEqual(data["camera_preview"]["user_id"], "200")
        self.assertIsInstance(data["camera_preview"]["captured_at"], int)
        self.assertEqual(data["camera_preview"]["data_url"], "data:image/jpeg;base64,AA==")
        self.assertTrue(data["camera_preview"]["ephemeral"])
        service._reality_touch_camera_snapshot_for_user.assert_awaited_once_with(
            "200", "拓展页摄像头单帧测试", include_preview=True, source="page_test")

    async def test_shutdown_removes_new_routes_and_retained_handlers_reject_requests(self):
        await self.controller.terminate()
        self.assertEqual(self.native.registered_web_apis, [])
        self.assertEqual((await self.call())["data"]["code"], "staging_host_terminated")

    async def test_audio_playback_reports_failure_and_device_io_releases_reply_lock(self):
        service = await self.enable("reality")

        async def play(volume):
            self.assertFalse(self.controller._control_lock.locked())
            return volume == 25

        service._play_reality_touch_test_audio = play
        for volume, status in ((24, "error"), (25, "ok")):
            result = await self.call(PREFIX + "/action", body={"extension_id": "reality",
                "action": "test_audio", "payload": {"playback_volume": volume}})
            self.assertEqual(result["status"], status, result)
            if status == "error":
                self.assertEqual(result["data"]["code"], "native_reality_playback_failed")
            else:
                self.assertTrue(result["data"]["result"]["played"])

    async def test_audio_output_preserves_offline_selection_without_backend_and_survives_reload(self):
        service = await self.enable("reality")
        catalog = {"backend_available": False, "backend": "unavailable",
            "error": "audio dependencies unavailable", "devices": [{
                "id": "system_default", "name": "跟随系统默认输出", "is_default": True,
                "max_output_channels": 0, "sample_rate": 0}]}
        service.data["reality_touch"].update({
            "audio_output_device_id": "sd:offline-device",
            "audio_output_device_name": "已保存的 USB 输出",
            "playback_volume": 35})
        service._reality_touch_query_audio_devices = lambda: catalog

        result = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "select_audio", "payload": {
                "device_id": "sd:offline-device", "playback_volume": 62}})

        self.assertEqual(result["status"], "ok", result)
        saved = json.loads(service.data_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["reality_touch"]["audio_output_device_id"], "sd:offline-device")
        self.assertEqual(saved["reality_touch"]["audio_output_device_name"], "已保存的 USB 输出")
        self.assertEqual(saved["reality_touch"]["playback_volume"], 62)
        service.data = service._load_data()
        self.assertEqual(service._reality_touch_store()["audio_output_device_id"], "sd:offline-device")
        self.assertEqual(service._reality_touch_playback_volume(), 62)
        unknown = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "select_audio", "payload": {
                "device_id": "sd:unknown-device", "playback_volume": 24}})
        self.assertEqual(unknown["status"], "error")

    async def test_management_errors_keep_codes_for_message_only_dashboard_bridge(self):
        from astrbot_host.perception_api import PREFIX as perception_prefix
        from astrbot_host.integration_api import PREFIX as integration_prefix

        for path in (perception_prefix, integration_prefix + "/integration/manifest"):
            for username in (None, "", "api_key:synthetic"):
                denied = await self.call(path, username=username)
                self.assertEqual(denied["message"], "dashboard_identity_required")
                self.assertEqual(denied["data"]["code"], denied["message"])
                self.assertTrue(denied["reason"])
        invalid = await self.call(perception_prefix, body={"provider": "reality"})
        self.assertEqual(invalid["message"], "perception_request_invalid")
        invalid = await self.call(integration_prefix + "/integration/manifest", query="unexpected=1")
        self.assertEqual(invalid["message"], "integration_request_invalid")

    async def test_reminder_only_and_pending_consent_users_survive_snapshot_and_reload(self):
        service = await self.enable("reality")
        service.data["users"]["201"] = {"reality_touch_reminders": {"fixture-reminder": {
            "id": "fixture-reminder", "status": "scheduled", "topic": "合成提醒"}}}
        service.data["users"]["202"] = {"reality_touch_pending_consent": {
            "capability": "local_audio", "expires_at": 1}}
        service._save_data_sync()
        service.data = service._load_data()
        result = await self.call()
        users = {row["user_id"]: row for row in result["data"]["extensions"]["reality"]["management"]["users"]}
        self.assertIn("201", users)
        self.assertIn("202", users)
        self.assertEqual(users["201"]["custom_reminders"][0]["id"], "fixture-reminder")
        self.assertFalse(users["202"]["consent"]["confirmed"])

    async def test_failed_reminder_cancel_does_not_report_completion(self):
        service = await self.enable("reality")
        service._cancel_reality_touch_official_reminder = AsyncMock(return_value=False)
        result = await self.call(PREFIX + "/action", body={"extension_id": "reality",
            "action": "cancel_reminder", "payload": {"user_id": "200", "reminder_id": "missing"}})
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(result["data"]["code"], "native_reality_reminder_not_cancelled")
