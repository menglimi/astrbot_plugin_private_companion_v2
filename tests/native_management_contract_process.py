"""Export synthetic real-handler receipts for the Dashboard bridge regression."""

import asyncio
import json
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch


async def receipts():
    from tests.test_native_extension_api import NativeExtensionAPITests, PREFIX

    case = NativeExtensionAPITests()
    await case.asyncSetUp()
    try:
        service = await case.enable("reality")
        service.authorized_user_ids.add("200")

        async def action(name, payload):
            return await case.call(PREFIX + "/action", body={"extension_id": "reality",
                "action": name, "payload": payload})

        result = {"initial": await case.call()}
        prefix = "/astrbot_plugin_private_companion"
        result["perception_denied"] = await case.call(prefix + "/perception", username="api_key:synthetic")
        result["manifest_denied"] = await case.call(prefix + "/integration/manifest", username="api_key:synthetic")
        result["perception_invalid"] = await case.call(prefix + "/perception", body={"provider": "reality"})
        result["manifest_invalid"] = await case.call(prefix + "/integration/manifest", query="unexpected=1")
        result["missing_user"] = await action("update_camera_policy", {"user_id": "200",
            "camera_enabled": True})
        result["consent"] = await action("consent_camera", {"user_id": "200", "confirmed": True})
        result["policy"] = await action("update_camera_policy", {"user_id": "200",
            "camera_enabled": True, "proactive_mode": "auto", "proactive_max_daily": -1})
        service.data = service._load_data()
        result["refreshed"] = await case.call()
        result["revoke"] = await action("consent_camera", {"user_id": "200", "confirmed": False})
        result["ineligible"] = await action("consent_camera", {"user_id": "999", "confirmed": True})
        with patch.object(service, "_mihome_api", return_value=None):
            result["no_mihome"] = await case.call()
            result["no_mihome_action"] = await action("mihome_start_login", {})
        # Seed existing consent in a synthetic store; no chat or device operation.
        service._user("200")["reality_touch_consent"] = {"confirmed": True,
            "version": 1, "granted_capabilities": ["local_audio"]}
        service._save_data_sync()
        result["audio_before"] = await case.call()
        result["audio_policy"] = await action("update_audio_policy", {"user_id": "200",
            "proactive_voice_enabled": True, "playback_volume": 47})
        alarm = {"user_id": "200", "enabled": True, "time": "08:45", "days": [0, 2, 4],
                 "message": "已保存的话题", "playback_volume": 52, "repeat_count": 3, "delivery_mode": "audio_only"}
        result["audio_alarm"] = await action("save", alarm)
        catalog = {"backend_available": False, "backend": "synthetic", "devices": [
            {"id": "system_default", "name": "合成默认输出", "is_default": True}]}
        with patch.object(service, "_reality_touch_query_audio_devices", return_value=catalog):
            result["audio_output"] = await action("select_audio", {"device_id": "system_default", "playback_volume": 64})
        service.data = service._load_data()
        result["audio_refreshed"] = await case.call()
        alarm.update(time="09:20", repeat_count=4)
        await action("save", alarm)
        result["audio_later"] = await case.call()
        alarm["message"] = "未保存的话题"
        result["audio_saved"] = await action("save", alarm)
        for name, receipt in result.items():
            if name.startswith("audio_"):
                assert receipt["status"] == "ok", (name, receipt)
        return result
    finally:
        await case.asyncTearDown()


if __name__ == "__main__":
    # AstrBot reads its root at SDK import time; never use the real user store.
    with TemporaryDirectory(prefix="v2-native-bridge-import-") as temporary:
        os.environ["ASTRBOT_ROOT"] = temporary
        print("NATIVE_MANAGEMENT_CONTRACT=" + json.dumps(asyncio.run(receipts()), ensure_ascii=False))
