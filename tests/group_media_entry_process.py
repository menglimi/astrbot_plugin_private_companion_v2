"""Run separately: real SDK group media, targeted history, local ACKs and teardown."""

import asyncio
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch


def run(*, deliver_images=False):
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="v2-group-media-native-") as temporary:
        os.environ["ASTRBOT_ROOT"] = temporary
        from tests.group_host_support import GroupContext, group_config
        from tests.group_media_support import group_raw, sdk_image
        from tests.image_delivery_support import image_reply
        from tests.native_adapter_support import FakeProvider, completion, final_text
        from tests.staging_bootstrap_support import wait_for_batch
        from tests.test_management_access import NOW
        from astrbot_host.native import installed_native_types
        from companion_v2.execution.models import TaskContext
        from companion_v2.foundation.clock import DeterministicClock
        from aiocqhttp import Event
        from aiocqhttp.api_impl import WebSocketReverseApi, ResultStore
        from astrbot.api.message_components import Image, Plain, Reply
        from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        logging.disable(logging.CRITICAL)
        assert Path(get_astrbot_data_path()).resolve() == Path(temporary).resolve() / "data"
        package = types.ModuleType("v2_group_media_fixture")
        package.__path__ = [str(repo)]
        sys.modules[package.__name__] = package
        spec = importlib.util.spec_from_file_location(package.__name__ + ".main", repo / "main.py")
        entry = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = entry
        spec.loader.exec_module(entry)
        native, clock = GroupContext(), DeterministicClock.at(NOW)

        async def model(payload, tools):
            content = next(m["content"] for m in payload["messages"] if m["role"] == "user")
            if deliver_images and isinstance(content, str):
                history = [json.loads(m["text"]) for m in json.loads(content)["materials"]
                           if m["purpose"] == "group_conversation_history"]
                replies = [item for item in history if item["type"] == "confirmed_group_reply"]
                assert len(replies) == 2 and all(len(item["images"]) == 1 for item in replies)
                assert all(image["view"] == "historical_metadata_only" for item in replies for image in item["images"])
                assert "base64" not in content
                return completion(final_text("接着聊刚才的群话题。"))
            assert len([c for c in content if c["type"] == "image_url"]) == 1
            materials = json.loads(content[0]["text"])["materials"]
            note = next(m for m in materials if m["purpose"].startswith(("quoted_image:", "input_image:")))
            if note["purpose"].startswith("quoted_image:"):
                attribution = json.loads(note["text"])
                assert attribution["sender"] == ("100" if deliver_images else "777") and attribution["quoted_by"] == "778"
            if deliver_images:
                return image_reply(payload, text="把原图附在这里。")
            return completion(final_text("图里有红色。", evidence=note["evidence"]))

        native.provider.client.state.behavior = model

        class LocalSocket:
            def __init__(self):
                self.frames = []
                self.records = {}

            async def send(self, payload):
                frame = json.loads(payload)
                self.frames.append(frame)
                if frame["action"] == "get_group_msg_history":
                    identifier = "8001" if deliver_images else "4501"
                    assert frame["params"] == dict(self_id="100", group_id="300", message_seq=identifier, count=1, reverse_order=False, parse_mult_msg=True)
                    data = {"messages": [self.records[identifier] if deliver_images
                                         else group_raw(message_id="4501", sender="777", text="原图")]}
                else:
                    assert frame["action"] == "send_group_msg" and frame["params"]["group_id"] == 300
                    data = {"message_id": 8000 + len(self.frames)}
                    record = group_raw(message_id=str(data["message_id"]), sender="100", count=0)
                    record["message"] = deepcopy(frame["params"]["message"])
                    self.records[str(data["message_id"])] = record
                asyncio.get_running_loop().call_soon(ResultStore.add,
                    {"echo": frame["echo"], "status": "ok", "retcode": 0, "data": data})

        socket = LocalSocket()
        platform = native.platform
        platform.client._wsr_api_clients = {"100": socket}
        platform.client._api._wsr_api = WebSocketReverseApi(platform.client._wsr_api_clients, set(), 0.2)
        sdk = replace(installed_native_types(), provider=FakeProvider,
                      function_tool=types.SimpleNamespace, tool_set=types.SimpleNamespace)
        controller_type = entry.AstrBotMultiController

        def controller(context, config, root):
            return controller_type(context, config, root, native_types=sdk, now=clock.now)

        def event_for(sender, identifier, parts):
            message = AstrBotMessage()
            message.type, message.self_id = MessageType.GROUP_MESSAGE, "100"
            message.group_id = message.session_id = "300"
            message.sender, message.message_id = MessageMember(sender, "合成群成员"), identifier
            message.message, message.message_str = parts, "群图片验证"
            raw_parts = []
            for part in parts:
                if isinstance(part, Plain):
                    raw_parts.append({"type": "text", "data": {"text": part.text}})
                elif isinstance(part, Image):
                    raw_parts.append({"type": "image", "data": {"file": part.file, "url": part.url}})
                elif isinstance(part, Reply):
                    raw_parts.append({"type": "reply", "data": {"id": part.id}})
                else:
                    raise AssertionError("unexpected SDK fixture component")
            message.raw_message = Event(post_type="message", message_type="group", sub_type="normal", anonymous=None,
                self_id=100, user_id=int(sender), sender={"user_id": int(sender)}, group_id=300,
                message_id=int(identifier), message=raw_parts)
            event = sdk.event(message.message_str, message, platform.meta(), "300", platform.client)
            event.created_at = clock.now().timestamp()
            return event

        async def verify():
            with patch.object(entry.StarTools, "get_data_dir", return_value=Path(temporary) / "v2"), \
                    patch.object(entry, "AstrBotMultiController", controller):
                plugin = entry.PrivateCompanionV2StagingPlugin(native, group_config(group_delivery_mode="onebot_group"))
            try:
                await plugin.initialize()
                ctrl = plugin.staging
                (await ctrl.initialize_profile()).unwrap()
                (await ctrl.authorize_group_delivery("group-a")).unwrap()
                (await ctrl.start()).unwrap()
                app, batches = ctrl.session.application, []
                turns = [("777", "4501", [Plain("原图"), sdk_image()]),
                         ("778", "4502", [Reply(id="8001" if deliver_images else "4501"), Plain("接着聊")])]
                if deliver_images:
                    turns.append(("779", "4503", [Plain("继续群话题")]))
                for sender, identifier, parts in turns:
                    event = event_for(sender, identifier, parts)
                    await plugin.receive_companion_message(event)
                    assert event.is_stopped()
                    batch = app.runtime.read_all("SELECT * FROM conversation_batches ORDER BY rowid", ())[-1]
                    batches.append(batch["batch_id"])
                    await wait_for_batch(ctrl.session, batch["batch_id"], timeout_seconds=15 if deliver_images else 4)
                    assert app.runtime.read_one("SELECT state FROM conversation_parts WHERE batch_id = ?", (batch["batch_id"],))[0] == "delivered"
                row = app.messages.batch(batches[-1])
                context = TaskContext.restore(json.loads(row["context_json"]))
                request = app.messages._request(row, context, clock.now())
                history = [json.loads(m.payload) for m in request.context.materials if m.purpose == "group_conversation_history"]
                assert history[0]["speaker_id"] == "777" and history[0]["attachments"][0]["view"] == "historical_metadata_only"
                if deliver_images:
                    assert not request.images and not request.reply_images
                    sends = [f["params"]["message"] for f in socket.frames if f["action"] == "send_group_msg"]
                    assert [[p["type"] for p in message] for message in sends] == [["text", "image"], ["text", "image"], ["text"]]
                    assert sends[0] == sends[1]
                else:
                    assert len(request.images) == 1 and request.reply_images is True
                actions = ["send_group_msg", "get_group_msg_history", "send_group_msg"]
                assert [f["action"] for f in socket.frames] == actions + (["send_group_msg"] if deliver_images else [])
                assert app.runtime.read_one("SELECT COUNT(*) FROM memory_atoms", ())[0] == 0
                assert ResultStore._futures == {}
            finally:
                await plugin.terminate()
            assert plugin.staging._terminated and plugin.staging.runtime is None and not native.registered_web_apis
            assert not any(name == "companion_v2" or name.startswith("companion_v2.") for name in sys.modules)
            if deliver_images:
                print("PASS: real SDK group image delivery, confirmed Bot image quote, metadata-only history, local WS ACKs, termination and route cleanup; no real model or QQ traffic.")
            else:
                print("PASS: SDK plugin import, two group members, direct and quoted images, original attribution and evidence, targeted history with local WS ACKs, termination and route cleanup; no real model or QQ traffic.")

        asyncio.run(verify())


if __name__ == "__main__":
    run()
