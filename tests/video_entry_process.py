"""Run the real plugin entry with an SDK Video component and local test adapters."""

import asyncio
import base64
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch


def run():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="v2-video-plugin-entry-") as temporary:
        os.environ["ASTRBOT_ROOT"] = temporary
        from tests import test_astrbot_staging_host as sdk_environment
        from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
        from tests.staging_bootstrap_support import wait_for_batch
        from tests.test_management_access import NOW
        from tests.test_astrbot_staging_host import host_config
        from tests.video_support import video_bytes
        from astrbot.api.message_components import Video
        from astrbot.api.star import StarTools
        from astrbot_host.native import installed_native_types
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        assert Path(get_astrbot_data_path()).resolve() == Path(temporary).resolve() / "data"
        package = types.ModuleType("v2_video_plugin_fixture")
        package.__path__ = [str(repo)]
        sys.modules[package.__name__] = package
        original_sys_path = tuple(sys.path)
        spec = importlib.util.spec_from_file_location(package.__name__ + ".main", repo / "main.py")
        entry = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = entry
        spec.loader.exec_module(entry)

        native = sdk_environment.WebContext()
        sdk = replace(installed_native_types(), event=FakeEvent, provider=FakeProvider,
                      function_tool=types.SimpleNamespace, tool_set=types.SimpleNamespace)
        original_controller = entry.AstrBotStagingController
        def controller(context, config, root):
            return original_controller(context, config, root, native_types=sdk, now=lambda: NOW)

        data_root = Path(temporary) / "private-companion-v2"
        plugin = None

        async def verify():
            nonlocal plugin
            with patch.object(StarTools, "get_data_dir", return_value=data_root), \
                    patch.object(entry, "AstrBotStagingController", controller):
                plugin = entry.PrivateCompanionV2StagingPlugin(native, host_config())
            try:
                await plugin.initialize()
                (await plugin.staging.initialize_profile()).unwrap()
                (await plugin.staging.start()).unwrap()

                content = video_bytes()
                locator = "base64://" + base64.b64encode(content).decode("ascii")
                event = FakeEvent(native, event_id="plugin-video")
                event.message_obj.message = [Video(file=locator)]
                event.message_obj.raw_message = dict(post_type="message", message_type="private", sub_type="friend",
                    self_id=100, user_id=200, sender={"user_id": 200}, message_id="plugin-video",
                    message=[{"type": "video", "data": {"file": locator}}])
                event.stopped = False
                event.stop_event = lambda: setattr(event, "stopped", True)
                await plugin.receive_companion_message(event)
                assert not event.stopped and event.call_llm
                batch = plugin.staging.latest_batch_id
                await wait_for_batch(plugin.staging.session, batch)
                preview = (await plugin.staging.preview(batch)).unwrap()
                assert preview["parts"][0]["text"] == "我在这里。" and not preview["sent"]
                payload = native.provider.client.state.calls[0][0]
                view = payload["messages"][2]["content"]
                assert len([part for part in view if part["type"] == "image_url"]) == 4
                notes = [json.loads(part["text"]) for part in view if part["type"] == "text"]
                assert [note["frame_index"] for note in notes if "video_evidence" in note] == [0, 3, 7, 11]
                assert native.platform.client._api._wsr_api.calls == []
            finally:
                await plugin.terminate()
            assert plugin.staging.status()["terminated"]
            assert not native.registered_web_apis
            assert tuple(sys.path) == original_sys_path
            assert not any(name == "companion_v2" or name.startswith("companion_v2.")
                           for name in sys.modules if getattr(sys.modules.get(name), "__file__", None)
                           and str(repo) in str(sys.modules[name].__file__))

        asyncio.run(verify())
        print("PASS: main.py plugin entry restored and admitted SDK Video, generated four sampled frames in preview, then stopped and unregistered owned routes; no real model or QQ traffic.")


if __name__ == "__main__":
    run()
